/*
 * =====================================================================================
 *  TRANSMISOR ARDUINO NANO ESP32 — ROVER LUNAR V2.0 (PUENTE USB-CDC A RF24)
 *  Plataforma Oficial de Transmision Terrena (Dongle PC / Control Remoto)
 * =====================================================================================
 *  Hardware: Arduino Nano ESP32 (ESP32-S3 a 3.3V) + Transceptor NRF24L01+
 *
 *  ASIGNACION DE PINES:
 *    - NRF24L01 CE:   Pin D9  (GPIO 18)
 *    - NRF24L01 CSN:  Pin D10 (GPIO 21)
 *    - NRF24L01 MOSI: Pin D11 (GPIO 38 - SPI Hardware)
 *    - NRF24L01 MISO: Pin D12 (GPIO 47 - SPI Hardware)
 *    - NRF24L01 SCK:  Pin D13 (GPIO 48 - SPI Hardware)
 *    - NRF24L01 VCC:  Salida 3.3V regulada (Capacitor 10-100 uF obligatorio a GND)
 *
 *  TELEMETRIA VISUAL (LED RGB INTEGRADO):
 *    - Azul solido: Transmisor en espera de enlace USB o reposo (idle).
 *    - Pulso verde (30 ms): Paquete RF transmitido exitosamente.
 *    - Pulso rojo (50 ms): Falla de transmision o saturacion de FIFO de radio.
 *
 *  PROTOCOLOS Y ESPECIFICACIONES:
 *    - Puerto Serie: 115200 bps (USB CDC nativo), lectura no bloqueante.
 *    - Canal RF: 108 (2.508 GHz).
 *    - Velocidad RF: 250 kbps (RF24_250KBPS).
 *    - Potencia RF: RF24_PA_MAX.
 *    - Direccion de enlace (Pipe): 0xF0F0F0F0E1LL.
 *    - Trama binaria: 6 bytes exactos (__attribute__((packed))).
 *    - Restriccion temporal: Cero llamadas a delay(), sincronizacion con millis().
 * =====================================================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>
#include <nRF24L01.h>
#include <stdint.h>
#include <string.h>

// ==========================================
// CONFIGURACION DE PINES DE HARDWARE
// ==========================================
#if defined(ARDUINO_NANO_ESP32) || defined(ARDUINO_ARCH_ESP32)
  #if defined(D9) && defined(D10) && defined(D11) && defined(D12) && defined(D13)
    #define PIN_RF_CE    D9
    #define PIN_RF_CSN   D10
    #define PIN_SPI_MOSI D11
    #define PIN_SPI_MISO D12
    #define PIN_SPI_SCK  D13
  #else
    #define PIN_RF_CE    18
    #define PIN_RF_CSN   21
    #define PIN_SPI_MOSI 38
    #define PIN_SPI_MISO 47
    #define PIN_SPI_SCK  48
  #endif
#else
  #define PIN_RF_CE   9
  #define PIN_RF_CSN  10
  #define PIN_SPI_MOSI 11
  #define PIN_SPI_MISO 12
  #define PIN_SPI_SCK  13
#endif

// LED RGB integrado de Arduino Nano ESP32 (ESP32-S3)
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
// ESTRUCTURA BINARIA ESTRICTA (6 BYTES)
// ==========================================
struct __attribute__((packed)) Paquete {
  int16_t traccion_izq;  // -255 a 255 (negativo: reversa, positivo: avance)
  int16_t traccion_der;  // -255 a 255 (control independiente)
  uint8_t angulo_s1;     // 10 a 170 grados (servomotor de direccion 1)
  uint8_t angulo_s2;     // 10 a 170 grados (servomotor de direccion 2)
};

static_assert(sizeof(Paquete) == 6, "El tamano de la estructura Paquete debe ser exactamente 6 bytes");

// ==========================================
// CONFIGURACION DE RADIOFRECUENCIA NRF24L01
// ==========================================
RF24 radio(PIN_RF_CE, PIN_RF_CSN);
const uint64_t DIRECCION_RF = 0xF0F0F0F0E1LL;

bool radioInicializada = false;
unsigned long ultimoIntentoRadio = 0;
const unsigned long INTERVALO_REINTENTO_RADIO_MS = 3000;

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
    establecerLedRgb(false, false, true); // Retornar a azul solido (espera/idle)
    pulsoLedActivo = false;
  }
}

// ==========================================
// GESTION DE RADIOFRECUENCIA
// ==========================================
void configurarRadio() {
  radio.setPayloadSize(sizeof(Paquete)); // 6 bytes exactos
  radio.setPALevel(RF24_PA_MAX);         // Maxima potencia de emision
  radio.setDataRate(RF24_250KBPS);       // 250 kbps (Maxima penetracion y sensibilidad)
  radio.setChannel(108);                 // Canal 108 (2.508 GHz, fuera del rango Wi-Fi)
  radio.setAutoAck(false);               // Modo streaming continuo de baja latencia
  radio.openWritingPipe(DIRECCION_RF);
  radio.stopListening();                 // Modo transmision activo
}

bool enviarPaqueteRF(const Paquete& paquete) {
  if (!radioInicializada) {
    dispararPulsoLed(true, false, false, 50); // Pulso rojo de 50 ms por falla de radio
    return false;
  }

  bool ok = radio.write(&paquete, sizeof(paquete));
  if (ok) {
    dispararPulsoLed(false, true, false, 30); // Pulso verde de 30 ms por transmision exitosa
  } else {
    dispararPulsoLed(true, false, false, 50); // Pulso rojo de 50 ms por error en bus RF
  }
  return ok;
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

  // Handshake de autodeteccion de hardware (Matriz de Perfiles)
  if (strcasecmp(cmdStr, "IDENT") == 0) {
    Serial.println(F("ID:NANO_ESP32:TX:v2.1"));
    return;
  }

  // Verificacion de conectividad basica
  if (strcasecmp(cmdStr, "PING") == 0) {
    Serial.println(F("PONG:TX:NANO_ESP32"));
    return;
  }

  // Parada de emergencia directa
  if (strcasecmp(cmdStr, "STOP") == 0 || strcasecmp(cmdStr, "PARAR") == 0) {
    Paquete paquete;
    paquete.traccion_izq = 0;
    paquete.traccion_der = 0;
    paquete.angulo_s1 = 90;
    paquete.angulo_s2 = 90;
    enviarPaqueteRF(paquete);
    Serial.println(F("STATUS:STOP"));
    return;
  }

  // Segmentacion de tramas delimitadas por coma (CSV)
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

  if (numTokens < 5) return;

  char* comando = tokens[0];
  int v1 = atoi(tokens[1]);
  int v2 = atoi(tokens[2]);
  int v3 = atoi(tokens[3]);
  int v4 = atoi(tokens[4]);

  Paquete paquete;

  // Comando oficial estandarizado: CMD,izq,der,s1,s2
  if (strcasecmp(comando, "CMD") == 0) {
    paquete.traccion_izq = (int16_t)constrain(v1, -255, 255);
    paquete.traccion_der = (int16_t)constrain(v2, -255, 255);
    paquete.angulo_s1    = (uint8_t)constrain(v3, 10, 170);
    paquete.angulo_s2    = (uint8_t)constrain(v4, 10, 170);

    bool ok = enviarPaqueteRF(paquete);
    if (ok) {
      Serial.println(F("STATUS:OK"));
    } else {
      Serial.println(F("STATUS:TX_ERROR"));
    }
    return;
  }

  // Compatibilidad con comandos de direccion directa (W, S, A, D, PIVOT, CRAB)
  paquete.angulo_s1 = (uint8_t)constrain(v3, 10, 170);
  paquete.angulo_s2 = (uint8_t)constrain(v4, 10, 170);

  if (strcasecmp(comando, "W") == 0) {
    paquete.traccion_izq = (int16_t)constrain(abs(v1), 0, 255);
    paquete.traccion_der = (int16_t)constrain(abs(v2), 0, 255);
  } else if (strcasecmp(comando, "S") == 0) {
    paquete.traccion_izq = (int16_t)-constrain(abs(v1), 0, 255);
    paquete.traccion_der = (int16_t)-constrain(abs(v2), 0, 255);
  } else if (strcasecmp(comando, "PIVOT_IZQ") == 0) {
    paquete.traccion_izq = (int16_t)-constrain(abs(v1), 0, 255);
    paquete.traccion_der = (int16_t)constrain(abs(v2), 0, 255);
  } else if (strcasecmp(comando, "PIVOT_DER") == 0) {
    paquete.traccion_izq = (int16_t)constrain(abs(v1), 0, 255);
    paquete.traccion_der = (int16_t)-constrain(abs(v2), 0, 255);
  } else if (strcasecmp(comando, "A") == 0 || strcasecmp(comando, "D") == 0 || strcasecmp(comando, "CRAB") == 0) {
    paquete.traccion_izq = (int16_t)constrain(v1, -255, 255);
    paquete.traccion_der = (int16_t)constrain(v2, -255, 255);
  } else {
    paquete.traccion_izq = 0;
    paquete.traccion_der = 0;
  }

  bool ok = enviarPaqueteRF(paquete);
  if (ok) {
    Serial.println(F("STATUS:OK"));
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
  establecerLedRgb(false, false, true); // Azul solido: Transmisor listo / En espera

  // Inicializacion de bus SPI de hardware
  #if defined(ARDUINO_ARCH_ESP32)
    SPI.begin(PIN_SPI_SCK, PIN_SPI_MISO, PIN_SPI_MOSI, PIN_RF_CSN);
  #else
    SPI.begin();
  #endif

  // Inicializacion del modulo de radiofrecuencia NRF24L01+
  radioInicializada = radio.begin();
  if (radioInicializada) {
    configurarRadio();
    Serial.println(F("SYS:ARDUINO_NANO_ESP32_TRANSMISOR_LISTO"));
  } else {
    Serial.println(F("ERROR:NRF24L01_NO_DETECTADO"));
    dispararPulsoLed(true, false, false, 1000); // Advertencia visual en rojo
  }
}

void loop() {
  // Lectura no bloqueante del buffer serie
  leerSerialNoBloqueante();

  // Actualizacion no bloqueante del temporizador de estado LED
  actualizarLed();

  // Rutina no bloqueante de recuperacion si la radio no estaba conectada al arrancar
  if (!radioInicializada && (millis() - ultimoIntentoRadio >= INTERVALO_REINTENTO_RADIO_MS)) {
    ultimoIntentoRadio = millis();
    if (radio.begin()) {
      configurarRadio();
      radioInicializada = true;
      establecerLedRgb(false, false, true); // Retornar a azul solido
      Serial.println(F("SYS:NRF24L01_RECUPERADO"));
    }
  }
}
