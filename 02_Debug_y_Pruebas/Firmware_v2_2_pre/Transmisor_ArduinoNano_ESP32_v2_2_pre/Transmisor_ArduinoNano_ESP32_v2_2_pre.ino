/*
 * =====================================================================================
 *  TRANSMISOR ARDUINO NANO ESP32 — ROVER LUNAR V2.2-PRE (PUENTE USB CDC A WI-FI UDP)
 *  Dongle USB PC para Pilotaje sin Joysticks Fisicos
 * =====================================================================================
 *  Hardware: Arduino Nano ESP32 (ESP32-S3 a 3.3V nativo) conectado por USB a la PC
 *  Enlace Inalambrico: Wi-Fi Nativo (Modo Estacion STA + Sockets UDP en puerto 4210)
 *
 *  CARACTERISTICAS:
 *    - Sin joysticks analogicos ni potenciometros: Todo el control proviene de la PC.
 *    - Enlace Wi-Fi UDP directo hacia el SoftAP del Rover ("ROVER_NET" en 192.168.4.1:4210).
 *    - Streaming continuo a 20 Hz (cada 50 ms) para alimentar el watchdog failsafe del Rover.
 *    - Disparo inmediato de paquete ante nuevas consignas en puerto serie (baja latencia).
 *    - Reenvio transparente por UDP de comandos ASCII directos (calibracion y test).
 *    - Telemetria visual no bloqueante con LED RGB integrado (GPIO 46, 0, 45, anodo comun).
 *    - Reconexion Wi-Fi automatica no bloqueante ante perdidas transitorias de senal.
 *    - Handshake activo: "IDENT" -> "ID:NANO_ESP32:TX:v2.2"
 *    - Trama binaria estricta de 8 bytes empaquetados (__attribute__((packed))).
 * =====================================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <stdint.h>
#include <string.h>
#include "PaqueteControl.h"

// ==========================================
// CONFIGURACION DE RED WI-FI Y UDP
// ==========================================
const char* TARGET_SSID = "ROVER_NET";
const char* TARGET_PASS = "rover1234";
const IPAddress IP_ROVER(192, 168, 4, 1);
const unsigned int PUERTO_UDP = 4210;

WiFiUDP udp;

// ==========================================
// ASIGNACION DE LED RGB INTEGRADO
// ==========================================
// Pines del LED RGB integrado en Arduino Nano ESP32 (ESP32-S3)
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

// ==========================================
// ESTRUCTURA BINARIA ESTRICTA (8 BYTES)
// Definida en PaqueteControl.h
// ==========================================
static_assert(sizeof(PaqueteControl) == 8, "PaqueteControl debe tener exactamente 8 bytes");

// Estado actual de consignas cinematicas
PaqueteControl datosControl = {0, 0, 90, 90, 90, 90};

// Temporizadores no bloqueantes
unsigned long ultimoEnvioMs = 0;
const unsigned long INTERVALO_ENVIO_MS = 50; // 20 Hz continuo

unsigned long ultimoIntentoWifiMs = 0;
const unsigned long INTERVALO_RECONEXION_WIFI_MS = 3000;

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
    if (WiFi.status() == WL_CONNECTED) {
      establecerLedRgb(false, false, true); // Azul solido: Enlace Wi-Fi activo / reposo
    } else {
      establecerLedRgb(true, false, false); // Rojo solido: Desconectado de Wi-Fi
    }
  }
}

// ==========================================
// TRANSMISION INALAMBRICA WI-FI UDP
// ==========================================
bool enviarPaqueteUdp() {
  if (WiFi.status() != WL_CONNECTED) {
    dispararPulsoLed(true, false, false, 50); // Pulso rojo por falta de enlace
    return false;
  }

  udp.beginPacket(IP_ROVER, PUERTO_UDP);
  udp.write((const uint8_t*)&datosControl, sizeof(datosControl));
  bool ok = (udp.endPacket() == 1);

  if (ok) {
    dispararPulsoLed(false, true, false, 30); // Pulso verde por envio exitoso
  } else {
    dispararPulsoLed(true, false, false, 50); // Pulso rojo por error de socket
  }
  return ok;
}

void reenviarComandoTextoUdp(const char* texto) {
  if (WiFi.status() == WL_CONNECTED) {
    udp.beginPacket(IP_ROVER, PUERTO_UDP);
    udp.write((const uint8_t*)texto, strlen(texto));
    udp.endPacket();
    Serial.print(F("[TX NANO FWD] "));
    Serial.println(texto);
    dispararPulsoLed(false, true, true, 40); // Cian (Verde+Azul) por comando ASCII
  } else {
    Serial.println(F("[TX NANO] Error: Wi-Fi desconectado, comando no transmitido."));
    dispararPulsoLed(true, false, false, 60);
  }
}

// ==========================================
// PARSEO Y PROCESAMIENTO DE COMANDOS SERIE
// ==========================================
char bufferSerial[128];
uint8_t indiceBuffer = 0;

void procesarComando(char* cmdStr) {
  // Limpieza de espacios en blanco iniciales
  while (*cmdStr == ' ' || *cmdStr == '\t') {
    cmdStr++;
  }

  // Limpieza de caracteres de escape y espacios finales
  int len = strlen(cmdStr);
  while (len > 0 && (cmdStr[len - 1] == ' ' || cmdStr[len - 1] == '\t' || cmdStr[len - 1] == '\r' || cmdStr[len - 1] == '\n')) {
    cmdStr[--len] = '\0';
  }

  if (len == 0) return;

  // Handshake de identificacion activa para matriz de perfiles
  if (strcasecmp(cmdStr, "IDENT") == 0) {
    Serial.println(F("ID:NANO_ESP32:TX:v2.2"));
    return;
  }

  // Verificacion de conectividad basica
  if (strcasecmp(cmdStr, "PING") == 0) {
    Serial.println(F("PONG:TX:NANO_ESP32"));
    return;
  }

  // Consulta de estado de enlace
  if (strcasecmp(cmdStr, "STATUS") == 0) {
    Serial.print(F("STATUS:WIFI="));
    Serial.println(WiFi.status() == WL_CONNECTED ? F("CONNECTED") : F("DISCONNECTED"));
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
    enviarPaqueteUdp();
    Serial.println(F("STATUS:STOP"));
    Serial.println(F("TLM_TX:0,0,90,90,90,90"));
    return;
  }

  // Segmentacion de consignas delimitadas por coma (CSV)
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

  // Si no es una trama CSV de al menos 5 campos, se reenvia como texto directo al Rover
  if (numTokens < 5) {
    reenviarComandoTextoUdp(cmdStr);
    return;
  }

  char* comando = tokens[0];
  int v1 = atoi(tokens[1]);
  int v2 = atoi(tokens[2]);
  int v3 = atoi(tokens[3]);
  int v4 = atoi(tokens[4]);
  int v5 = (numTokens >= 6) ? atoi(tokens[5]) : v3;
  int v6 = (numTokens >= 7) ? atoi(tokens[6]) : v4;

  // Actualizar servomotores con restriccion estricta [10 deg, 170 deg]
  datosControl.angulo_s1 = (uint8_t)constrain(v3, 10, 170);
  datosControl.angulo_s2 = (uint8_t)constrain(v4, 10, 170);
  datosControl.angulo_s3 = (uint8_t)constrain(v5, 10, 170);
  datosControl.angulo_s4 = (uint8_t)constrain(v6, 10, 170);

  // Comando oficial HMI: CMD,izq,der,s1,s2,s3,s4
  if (strcasecmp(comando, "CMD") == 0) {
    datosControl.traccion_izq = (int16_t)constrain(v1, -255, 255);
    datosControl.traccion_der = (int16_t)constrain(v2, -255, 255);
  } else if (strcasecmp(comando, "W") == 0) {
    datosControl.traccion_izq = (int16_t)constrain(v1, -255, 255);
    datosControl.traccion_der = (int16_t)constrain(v2, -255, 255);
  } else if (strcasecmp(comando, "S") == 0) {
    datosControl.traccion_izq = (int16_t)-constrain(v1, -255, 255);
    datosControl.traccion_der = (int16_t)-constrain(v2, -255, 255);
  } else if (strcasecmp(comando, "PIVOT_IZQ") == 0) {
    datosControl.traccion_izq = (int16_t)-constrain(v1, -255, 255);
    datosControl.traccion_der = (int16_t)constrain(v2, -255, 255);
  } else if (strcasecmp(comando, "PIVOT_DER") == 0) {
    datosControl.traccion_izq = (int16_t)constrain(v1, -255, 255);
    datosControl.traccion_der = (int16_t)-constrain(v2, -255, 255);
  } else if (strcasecmp(comando, "A") == 0 || strcasecmp(comando, "D") == 0 || strcasecmp(comando, "CRAB") == 0) {
    datosControl.traccion_izq = (int16_t)constrain(v1, -255, 255);
    datosControl.traccion_der = (int16_t)constrain(v2, -255, 255);
  } else {
    datosControl.traccion_izq = 0;
    datosControl.traccion_der = 0;
  }

  // Disparo inmediato para minima latencia
  bool ok = enviarPaqueteUdp();
  if (ok) {
    Serial.println(F("STATUS:OK_4SERVO"));
    Serial.print(F("TLM_TX:"));
    Serial.print(datosControl.traccion_izq); Serial.print(F(","));
    Serial.print(datosControl.traccion_der); Serial.print(F(","));
    Serial.print(datosControl.angulo_s1); Serial.print(F(","));
    Serial.print(datosControl.angulo_s2); Serial.print(F(","));
    Serial.print(datosControl.angulo_s3); Serial.print(F(","));
    Serial.println(datosControl.angulo_s4);
  } else {
    Serial.println(F("STATUS:TX_ERROR"));
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
// RUTINAS PRINCIPALES ARDUINO
// ==========================================
void setup() {
  // Inicializacion del puerto serie USB CDC nativo
  Serial.begin(115200);

  // Inicializacion de pines de telemetria visual
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_BLUE, OUTPUT);
  establecerLedRgb(false, false, true); // Azul inicial

  // Inicializacion Wi-Fi en modo Estacion (STA)
  WiFi.mode(WIFI_STA);
  WiFi.begin(TARGET_SSID, TARGET_PASS);
  udp.begin(0); // Puerto local asignado dinamicamente

  Serial.println(F("SYS:ARDUINO_NANO_ESP32_WIFI_TX_INICIADO"));
}

void loop() {
  // 1. Lectura no bloqueante del buffer serie USB
  leerSerialNoBloqueante();

  // 2. Gestion de estado y reconexion no bloqueante de Wi-Fi
  static bool wifiConectadoPrevio = false;
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiConectadoPrevio) {
      wifiConectadoPrevio = true;
      establecerLedRgb(false, false, true); // Azul solido: Listo
      Serial.print(F("SYS:WIFI_CONECTADO_IP="));
      Serial.println(WiFi.localIP());
    }
  } else {
    if (wifiConectadoPrevio) {
      wifiConectadoPrevio = false;
      establecerLedRgb(true, false, false); // Rojo solido: Desconectado
      Serial.println(F("WARN:WIFI_DESCONECTADO"));
    }

    // Intento de reconexion periodica cada 3000 ms sin bloquear loop()
    if (millis() - ultimoIntentoWifiMs >= INTERVALO_RECONEXION_WIFI_MS) {
      ultimoIntentoWifiMs = millis();
      WiFi.disconnect();
      WiFi.begin(TARGET_SSID, TARGET_PASS);
    }
  }

  // 3. Actualizacion no bloqueante del temporizador de pulsos del LED
  actualizarLed();

  // 4. Streaming periodico continuo a 20 Hz para alimentar watchdog del Rover
  if (millis() - ultimoEnvioMs >= INTERVALO_ENVIO_MS) {
    ultimoEnvioMs = millis();
    enviarPaqueteUdp();
  }
}
