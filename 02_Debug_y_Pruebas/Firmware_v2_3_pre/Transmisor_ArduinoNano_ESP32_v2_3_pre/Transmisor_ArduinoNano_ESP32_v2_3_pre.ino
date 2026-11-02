/*
 * =====================================================================================
 *  TRANSMISOR ARDUINO NANO ESP32 — ROVER LUNAR V2.3-PRE
 *  Puente USB-Serie CDC a Transmision Inalambrica (HMI PC a Rover Rocker-Bogie 6x6)
 * =====================================================================================
 *  Hardware: Arduino Nano ESP32 (ESP32-S3 a 3.3V nativo) conectado por USB a la PC
 *  Comunicaciones soportadas:
 *    - Wi-Fi Nativo (Cliente STA + Sockets UDP en puerto 4210) [MODO PREDETERMINADO]
 *    - NRF24L01+ (Radiofrecuencia 2.4 GHz SPI Hardware) [Modo alternativo]
 *
 *  CARACTERISTICAS:
 *    - Sin joysticks analogicos: Todo el control cinemático proviene de la PC (Dongle USB puro).
 *    - Control angular absoluto directo para servomotores: consignas en grados [10, 170].
 *    - Compatible con HMI Python (HMI_Rover_V2.py / HMI_Rover_Debug.py) y HMI Rust (hmi-gui).
 *    - Trama binaria unificada estricta de 8 bytes empaquetados (__attribute__((packed))).
 *    - Handshake activo: "IDENT" -> "ID:NANO_ESP32:TX:v2.3", "PING" -> "PONG:TX:NANO_ESP32".
 *    - Streaming continuo a 20 Hz (cada 50 ms) para alimentar watchdog failsafe del Rover.
 *    - Envio inmediato al recibir nueva consigna serie para latencia minima.
 *    - Telemetria visual no bloqueante con LED RGB integrado (GPIO 46, 0, 45, anodo comun).
 *    - Reenvio transparente de comandos ASCII de calibracion y test.
 * =====================================================================================
 */

#include <Arduino.h>
#include <stdint.h>
#include <string.h>
#include "PaqueteControl.h"

// ==========================================
// SELECCION DE MODO DE COMUNICACION
// 1 = Wi-Fi Nativo STA + UDP (Sin cables SPI ni modulos externos)
// 0 = Radiofrecuencia NRF24L01+ externa por bus SPI Hardware
// ==========================================
#define MODO_CONEXION_WIFI 1

#if MODO_CONEXION_WIFI
  #include <WiFi.h>
  #include <WiFiUdp.h>
  const char* TARGET_SSID = "ROVER_NET";
  const char* TARGET_PASS = "rover1234";
  const IPAddress IP_ROVER(192, 168, 4, 1);
  const unsigned int PUERTO_UDP = 4210;
  WiFiUDP udp;
#else
  #include <SPI.h>
  #include <RF24.h>
  // Asignacion oficial de pines SPI Hardware para Arduino Nano ESP32
  #define PIN_RF_CE   D9   // GPIO 18
  #define PIN_RF_CSN  D10  // GPIO 21
  #define PIN_RF_MOSI D11  // GPIO 38
  #define PIN_RF_MISO D12  // GPIO 47
  #define PIN_RF_SCK  D13  // GPIO 48
  RF24 radio(PIN_RF_CE, PIN_RF_CSN);
  const byte DIRECCION_RF[6] = "ROVER";
  bool radioInicializada = false;
#endif

// ==========================================
// ASIGNACION DE LED RGB INTEGRADO
// ==========================================
#if defined(LED_RED) && defined(LED_GREEN) && defined(LED_BLUE)
  #define PIN_LED_RED   LED_RED
  #define PIN_LED_GREEN LED_GREEN
  #define PIN_LED_BLUE  LED_BLUE
#else
  #define PIN_LED_RED   46
  #define PIN_LED_GREEN 0
  #define PIN_LED_BLUE  45
#endif

// El LED RGB en Arduino Nano ESP32 es de anodo comun (activo en nivel BAJO)
#define LED_ENCENDIDO LOW
#define LED_APAGADO   HIGH

// Verificacion estatica de tamano de trama
static_assert(sizeof(PaqueteControl) == 8, "PaqueteControl debe tener exactamente 8 bytes");

// Estado actual de consignas cinematicas (angulos absolutos en grados)
PaqueteControl datosControl = {0, 0, 90, 90, 90, 90};

// Temporizadores no bloqueantes
unsigned long ultimoEnvioMs = 0;
const unsigned long INTERVALO_ENVIO_MS = 50; // 20 Hz continuo

#if MODO_CONEXION_WIFI
  unsigned long ultimoIntentoWifiMs = 0;
  const unsigned long INTERVALO_RECONEXION_WIFI_MS = 3000;
#endif

// ==========================================
// CONTROL VISUAL NO BLOQUEANTE (LED RGB)
// ==========================================
unsigned long tiempoInicioPulsoLed = 0;
unsigned long duracionPulsoLed = 0;
bool pulsoLedActivo = false;

void establecerLedRgb(bool r, bool g, bool b) {
  digitalWrite(PIN_LED_RED,   r ? LED_ENCENDIDO : LED_APAGADO);
  digitalWrite(PIN_LED_GREEN, g ? LED_ENCENDIDO : LED_APAGADO);
  digitalWrite(PIN_LED_BLUE,  b ? LED_ENCENDIDO : LED_APAGADO);
}

void dispararPulsoLed(bool r, bool g, bool b, unsigned long duracionMs) {
  establecerLedRgb(r, g, b);
  tiempoInicioPulsoLed = millis();
  duracionPulsoLed = duracionMs;
  pulsoLedActivo = true;
}

void actualizarLed() {
  if (pulsoLedActivo && (millis() - tiempoInicioPulsoLed >= duracionPulsoLed)) {
    pulsoLedActivo = false;
#if MODO_CONEXION_WIFI
    if (WiFi.status() == WL_CONNECTED) {
      establecerLedRgb(false, false, true); // Azul solido: Wi-Fi conectado
    } else {
      establecerLedRgb(true, false, false); // Rojo solido: Wi-Fi desconectado
    }
#else
    if (radioInicializada) {
      establecerLedRgb(false, false, true); // Azul solido: NRF24 activo
    } else {
      establecerLedRgb(true, false, false); // Rojo solido: Error NRF24
    }
#endif
  }
}

// ==========================================
// TRANSMISION INALAMBRICA (WIFI O RF)
// ==========================================
bool enviarPaqueteInalambrico() {
#if MODO_CONEXION_WIFI
  if (WiFi.status() != WL_CONNECTED) {
    dispararPulsoLed(true, false, false, 40);
    return false;
  }
  udp.beginPacket(IP_ROVER, PUERTO_UDP);
  udp.write((const uint8_t*)&datosControl, sizeof(datosControl));
  bool ok = (udp.endPacket() == 1);
  if (ok) {
    dispararPulsoLed(false, true, false, 25);
  } else {
    dispararPulsoLed(true, false, false, 40);
  }
  return ok;
#else
  if (!radioInicializada) {
    dispararPulsoLed(true, false, false, 40);
    return false;
  }
  bool ok = radio.write(&datosControl, sizeof(datosControl));
  if (ok) {
    dispararPulsoLed(false, true, false, 25);
  } else {
    dispararPulsoLed(true, false, false, 40);
  }
  return ok;
#endif
}

void reenviarComandoTexto(const char* texto) {
#if MODO_CONEXION_WIFI
  if (WiFi.status() == WL_CONNECTED) {
    udp.beginPacket(IP_ROVER, PUERTO_UDP);
    udp.write((const uint8_t*)texto, strlen(texto));
    udp.endPacket();
    Serial.print(F("[TX NANO FWD] "));
    Serial.println(texto);
    dispararPulsoLed(false, true, true, 35);
  } else {
    Serial.println(F("[TX NANO] Error: Wi-Fi desconectado, comando no transmitido."));
    dispararPulsoLed(true, false, false, 50);
  }
#else
  Serial.print(F("[TX NANO RF] Comando texto recibido (no reenviable por RF raw): "));
  Serial.println(texto);
#endif
}

// ==========================================
// PARSEO Y PROCESAMIENTO DE COMANDOS SERIE
// ==========================================
char bufferSerial[128];
uint8_t indiceBuffer = 0;

void procesarComando(char* cmdStr) {
  while (*cmdStr == ' ' || *cmdStr == '\t') cmdStr++;
  int len = strlen(cmdStr);
  while (len > 0 && (cmdStr[len - 1] == ' ' || cmdStr[len - 1] == '\t' || cmdStr[len - 1] == '\r' || cmdStr[len - 1] == '\n')) {
    cmdStr[--len] = '\0';
  }
  if (len == 0) return;

  // Handshake de autodeteccion de perfil de hardware
  if (strcasecmp(cmdStr, "IDENT") == 0) {
    Serial.println(F("ID:NANO_ESP32:TX:v2.3"));
    return;
  }
  if (strcasecmp(cmdStr, "PING") == 0) {
    Serial.println(F("PONG:TX:NANO_ESP32"));
    return;
  }
  if (strcasecmp(cmdStr, "STATUS") == 0) {
#if MODO_CONEXION_WIFI
    Serial.print(F("STATUS:WIFI="));
    Serial.println(WiFi.status() == WL_CONNECTED ? F("CONNECTED") : F("DISCONNECTED"));
#else
    Serial.print(F("STATUS:NRF24="));
    Serial.println(radioInicializada ? F("READY") : F("ERROR"));
#endif
    return;
  }

  // Parada de emergencia directa
  if (strcasecmp(cmdStr, "STOP") == 0 || strcasecmp(cmdStr, "PARAR") == 0) {
    datosControl.traccion_izq = 0;
    datosControl.traccion_der = 0;
    datosControl.angulo_s1 = 90;
    datosControl.angulo_s2 = 90;
    datosControl.angulo_s3 = 90;
    datosControl.angulo_s4 = 90;
    enviarPaqueteInalambrico();
    Serial.println(F("STATUS:STOP"));
    Serial.println(F("TLM_TX:0,0,90,90,90,90"));
    return;
  }

  // Tokenizacion CSV delimitada por coma
  char copia[128];
  strncpy(copia, cmdStr, sizeof(copia) - 1);
  copia[sizeof(copia) - 1] = '\0';

  char* tokens[8];
  int numTokens = 0;
  char* saveptr = NULL;
  char* tok = strtok_r(copia, ",", &saveptr);
  while (tok != NULL && numTokens < 8) {
    while (*tok == ' ') tok++;
    int tlen = strlen(tok);
    while (tlen > 0 && tok[tlen - 1] == ' ') tok[--tlen] = '\0';
    tokens[numTokens++] = tok;
    tok = strtok_r(NULL, ",", &saveptr);
  }

  // Si no es una trama CSV de consignas, reenviar como texto transparente
  if (numTokens < 5) {
    reenviarComandoTexto(cmdStr);
    return;
  }

  char* comando = tokens[0];
  int potIzq = atoi(tokens[1]);
  int potDer = atoi(tokens[2]);
  int s1     = atoi(tokens[3]);
  int s2     = atoi(tokens[4]);

  // Si la trama incluye 4 servos explicitos (Python HMI / Rust extendido)
  int s3, s4;
  if (numTokens >= 7) {
    s3 = atoi(tokens[5]);
    s4 = atoi(tokens[6]);
  } else if (numTokens >= 6) {
    s3 = atoi(tokens[5]);
    s4 = 180 - s2;
  } else {
    // Si la trama incluye solo S1 y S2 (Rust protocol-rover legado),
    // calcular los angulos traseros simetricos de Ackermann (180 - s)
    s3 = 180 - s1;
    s4 = 180 - s2;
  }

  // Asignacion estricta de angulos absolutos con restriccion mecanica segura [10 deg, 170 deg]
  datosControl.angulo_s1 = (uint8_t)constrain(s1, 10, 170);
  datosControl.angulo_s2 = (uint8_t)constrain(s2, 10, 170);
  datosControl.angulo_s3 = (uint8_t)constrain(s3, 10, 170);
  datosControl.angulo_s4 = (uint8_t)constrain(s4, 10, 170);

  // Mapeo cinematico de traccion
  if (strcasecmp(comando, "CMD") == 0) {
    // Rust HMI transmite valores de traccion directamente con signo (-255 a 255)
    datosControl.traccion_izq = (int16_t)constrain(potIzq, -255, 255);
    datosControl.traccion_der = (int16_t)constrain(potDer, -255, 255);
  } else if (strcasecmp(comando, "W") == 0) {
    datosControl.traccion_izq = (int16_t)constrain(potIzq, -255, 255);
    datosControl.traccion_der = (int16_t)constrain(potDer, -255, 255);
  } else if (strcasecmp(comando, "S") == 0) {
    datosControl.traccion_izq = (int16_t)-constrain(potIzq, -255, 255);
    datosControl.traccion_der = (int16_t)-constrain(potDer, -255, 255);
  } else if (strcasecmp(comando, "PIVOT_IZQ") == 0) {
    datosControl.traccion_izq = (int16_t)-constrain(potIzq, -255, 255);
    datosControl.traccion_der = (int16_t)constrain(potDer, -255, 255);
  } else if (strcasecmp(comando, "PIVOT_DER") == 0) {
    datosControl.traccion_izq = (int16_t)constrain(potIzq, -255, 255);
    datosControl.traccion_der = (int16_t)-constrain(potDer, -255, 255);
  } else if (strcasecmp(comando, "A") == 0 || strcasecmp(comando, "D") == 0 || strcasecmp(comando, "CRAB") == 0) {
    datosControl.traccion_izq = (int16_t)constrain(potIzq, -255, 255);
    datosControl.traccion_der = (int16_t)constrain(potDer, -255, 255);
  } else {
    datosControl.traccion_izq = 0;
    datosControl.traccion_der = 0;
  }

  // Disparo inmediato para minima latencia
  enviarPaqueteInalambrico();

  static int16_t prevIzqTx = -999, prevDerTx = -999;
  static uint8_t prevS1Tx = 0, prevS2Tx = 0, prevS3Tx = 0, prevS4Tx = 0;
  if (datosControl.traccion_izq != prevIzqTx || datosControl.traccion_der != prevDerTx ||
      datosControl.angulo_s1 != prevS1Tx || datosControl.angulo_s2 != prevS2Tx ||
      datosControl.angulo_s3 != prevS3Tx || datosControl.angulo_s4 != prevS4Tx) {
    prevIzqTx = datosControl.traccion_izq; prevDerTx = datosControl.traccion_der;
    prevS1Tx = datosControl.angulo_s1; prevS2Tx = datosControl.angulo_s2;
    prevS3Tx = datosControl.angulo_s3; prevS4Tx = datosControl.angulo_s4;

    Serial.println(F("STATUS:OK_4SERVO"));
    Serial.print(F("TLM_TX:"));
    Serial.print(datosControl.traccion_izq); Serial.print(F(","));
    Serial.print(datosControl.traccion_der); Serial.print(F(","));
    Serial.print(datosControl.angulo_s1); Serial.print(F(","));
    Serial.print(datosControl.angulo_s2); Serial.print(F(","));
    Serial.print(datosControl.angulo_s3); Serial.print(F(","));
    Serial.println(datosControl.angulo_s4);
  }
}

void leerSerialNoBloqueante() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (indiceBuffer > 0) {
        bufferSerial[indiceBuffer] = '\0';
        procesarComando(bufferSerial);
        indiceBuffer = 0;
      }
    } else {
      if (indiceBuffer < sizeof(bufferSerial) - 1) {
        bufferSerial[indiceBuffer++] = c;
      }
    }
  }
}

// ==========================================
// CONFIGURACION Y BUCLE PRINCIPAL
// ==========================================
void setup() {
  Serial.begin(115200);

  // Inicializacion del LED RGB integrado
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_BLUE, OUTPUT);
  establecerLedRgb(false, false, true); // Azul inicial

#if MODO_CONEXION_WIFI
  WiFi.mode(WIFI_STA);
  WiFi.begin(TARGET_SSID, TARGET_PASS);
  udp.begin(0);
  Serial.println(F("SYS:ARDUINO_NANO_ESP32_WIFI_TX_V2_3_INICIADO"));
#else
  SPI.begin(PIN_RF_SCK, PIN_RF_MISO, PIN_RF_MOSI, PIN_RF_CSN);

  if (!radio.begin()) {
    Serial.println(F("[ERROR] Modulo NRF24L01 no detectado en Arduino Nano ESP32."));
    establecerLedRgb(true, false, false); // Rojo
    radioInicializada = false;
  } else {
    radioInicializada = true;
    radio.setPayloadSize(sizeof(PaqueteControl));
    radio.setPALevel(RF24_PA_MAX);
    radio.setDataRate(RF24_250KBPS);
    radio.setChannel(108);
    radio.setAutoAck(false);
    radio.openWritingPipe(DIRECCION_RF);
    radio.stopListening();
    establecerLedRgb(false, false, true); // Azul
    Serial.println(F("SYS:ARDUINO_NANO_ESP32_NRF24_TX_V2_3_INICIADO"));
  }
#endif
}

void loop() {
  // 1. Lectura no bloqueante del buffer serie USB
  leerSerialNoBloqueante();

  // 2. Gestion de estado y reconexion no bloqueante
#if MODO_CONEXION_WIFI
  static bool wifiConectadoPrevio = false;
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiConectadoPrevio) {
      wifiConectadoPrevio = true;
      establecerLedRgb(false, false, true);
      Serial.print(F("SYS:WIFI_CONECTADO_IP="));
      Serial.println(WiFi.localIP());
    }
  } else {
    if (wifiConectadoPrevio) {
      wifiConectadoPrevio = false;
      establecerLedRgb(true, false, false);
      Serial.println(F("WARN:WIFI_DESCONECTADO"));
    }
    if (millis() - ultimoIntentoWifiMs >= INTERVALO_RECONEXION_WIFI_MS) {
      ultimoIntentoWifiMs = millis();
      WiFi.disconnect();
      WiFi.begin(TARGET_SSID, TARGET_PASS);
    }
  }
#endif

  // 3. Temporizador no bloqueante de pulsos de LED
  actualizarLed();

  // 4. Streaming continuo a 20 Hz para alimentar watchdog del Rover
  if (millis() - ultimoEnvioMs >= INTERVALO_ENVIO_MS) {
    ultimoEnvioMs = millis();
    enviarPaqueteInalambrico();
  }
}
