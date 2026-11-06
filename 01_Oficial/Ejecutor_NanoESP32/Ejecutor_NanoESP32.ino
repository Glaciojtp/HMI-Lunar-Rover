/*
 * ROVER LUNAR - FIRMWARE EJECUTOR (Arduino Nano ESP32, a bordo del rover)
 * Version: v3.0
 *
 * Cadena de control:  HMI (PC) --USB--> TRANSMISOR --WiFi UDP--> EJECUTOR
 *
 * Funcion:
 *   - Se conecta a la red del transmisor, recibe consignas y mueve los actuadores:
 *       Motores de CC -> Puente H (2 canales: lado izquierdo y lado derecho)
 *       Servos S1..S4 -> PCA9685 por I2C (canales 0..3)
 *   - Devuelve telemetria al transmisor a 5 Hz, incluida la causa del ultimo reinicio.
 *
 * Reduccion de picos de corriente (los reinicios del ejecutor son brownouts):
 *   1. Rampa de PWM en motores: nunca se pasa de 0 a la consigna de golpe.
 *   2. Inversion de giro pasando por cero, con pausa.
 *   3. Arranque desfasado: los dos lados no salen de cero en el mismo instante.
 *   4. Servos escalonados: una sola escritura por tick y velocidad limitada.
 *   5. Pulsos del PCA9685 con fase distinta en cada canal, para que no coincidan.
 *   6. Arranque secuencial: servos de a uno y recien despues la radio WiFi.
 *   7. Potencia WiFi reducida, sin AP propio y con telemetria de baja frecuencia.
 *   8. Limite de angulo [10, 170]: un pulso fuera de rango deja al servo forzando
 *      contra su tope mecanico, consumiendo corriente de bloqueo.
 *   Esto reduce el pico pero no reemplaza una alimentacion correcta: ver
 *   03_Documentacion_y_Guias/Esquematicos/ESQUEMATICO_NANO_ESP32.md.
 *
 * Protocolo USB (115200 bps, opcional, para la HMI Debug):
 *   PC -> placa:  IDENT | PING
 *   placa -> PC:  ID:NANO_ESP32:RX:v3.0
 *                 PONG:RX
 *                 BOOT,causa,reinicios
 *                 RX,seq,izq,der,s1,s2,s3,s4,dt_ms,aIzq,aDer,a1,a2,a3,a4
 *                 TLM,...  (mismo formato que reenvia el transmisor)
 *                 WARN:... / ERR:... / SYS:...
 *
 * LED RGB: azul = sin enlace; verde = operacion; rojo = failsafe.
 *
 * Bibliotecas: Adafruit PWM Servo Driver Library (y su dependencia Adafruit BusIO).
 * Las estructuras PaqueteControl y PaqueteTelemetria deben ser identicas a las de
 * Transmisor_NanoESP32.ino. tests/test_firmware.py lo comprueba.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <esp_attr.h>
#include <esp_system.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VERSION_FW "v3.0"

// ---------------------------------------------------------------------------
// Puente H: 0 = L9110S (el montado en el rover), 1 = L298N
// ---------------------------------------------------------------------------
#ifndef PUENTE_H_L298N
#define PUENTE_H_L298N 0
#endif

#if PUENTE_H_L298N
const uint8_t PIN_ENA = D2;  // PWM lado izquierdo
const uint8_t PIN_IN1 = D3;
const uint8_t PIN_IN2 = D4;
const uint8_t PIN_ENB = D5;  // PWM lado derecho
const uint8_t PIN_IN3 = D6;
const uint8_t PIN_IN4 = D7;
#else
const uint8_t PIN_A1A = D2;  // Izquierda avance
const uint8_t PIN_A1B = D5;  // Izquierda reversa
const uint8_t PIN_B1A = D3;  // Derecha avance
const uint8_t PIN_B1B = D4;  // Derecha reversa
#endif

// Sentido de giro segun el cableado de los motores
const bool INVERTIR_IZQ = false;
const bool INVERTIR_DER = false;

// ---------------------------------------------------------------------------
// Red
// ---------------------------------------------------------------------------
const char *WIFI_SSID = "ROVER_NET";
const char *WIFI_PASS = "rover1234";
const int WIFI_CANAL = 6;  // Debe coincidir con el transmisor (evita el barrido de canales)
const IPAddress IP_LOCAL(192, 168, 4, 2);
const IPAddress IP_TRANSMISOR(192, 168, 4, 1);
const IPAddress MASCARA(255, 255, 255, 0);
const uint16_t PUERTO_UDP = 4210;
const wifi_power_t POTENCIA_WIFI = WIFI_POWER_8_5dBm;  // Subir si hace falta mas alcance

// ---------------------------------------------------------------------------
// Temporizacion y limitadores de corriente
// ---------------------------------------------------------------------------
const uint32_t TIMEOUT_MS = 1000;           // Failsafe por perdida de enlace
const uint32_t PERIODO_TICK_MS = 10;        // Periodo de actualizacion de actuadores
const uint32_t PERIODO_TELEMETRIA_MS = 200; // 5 Hz
const uint32_t PERIODO_REINTENTO_WIFI_MS = 3000;

const int PASO_RAMPA_PWM = 4;               // Por tick: 0 a 255 en unos 640 ms
const uint32_t PAUSA_EN_CERO_MS = 80;       // Espera en cero antes de invertir el giro
const uint32_t DESFASE_ARRANQUE_MS = 60;    // Separacion entre arranques de cada lado

const int PASO_SERVO_GRADOS = 3;            // Grados por paso de cada servo
const uint32_t INTERVALO_SERVO_MS = 40;     // Entre pasos del mismo servo (75 grados/s)
const uint32_t ARRANQUE_SERVO_MS = 300;     // Separacion al centrar en el arranque

// ---------------------------------------------------------------------------
// Limites de seguridad
// ---------------------------------------------------------------------------
const int PWM_MAX = 255;
const int ANGULO_MIN = 10;
const int ANGULO_MAX = 170;
const int ANGULO_CENTRO = 90;

// ---------------------------------------------------------------------------
// PCA9685
// ---------------------------------------------------------------------------
const uint8_t PCA_DIRECCION = 0x40;
const int SERVO_TICKS_0 = 150;    // Calibracion validada en banco con los servos actuales
const int SERVO_TICKS_180 = 550;
const uint16_t FASE_CANAL[4] = {0, 1024, 2048, 3072};  // Pulsos sin superposicion

// ---------------------------------------------------------------------------
// Protocolo binario UDP (identico en ambos firmwares)
// ---------------------------------------------------------------------------
const uint8_t MAGIC_CONTROL = 0xA5;
const uint8_t MAGIC_TELEMETRIA = 0x5A;
const uint8_t FLAG_EMERGENCIA = 0x01;

struct __attribute__((packed)) PaqueteControl {
  uint8_t magic;
  uint8_t flags;
  uint16_t seq;
  int16_t izq;
  int16_t der;
  uint8_t servo[4];
  uint8_t crc;
};

struct __attribute__((packed)) PaqueteTelemetria {
  uint8_t magic;
  uint8_t estado;       // 0 arranque, 1 sin enlace, 2 operacion, 3 failsafe
  uint8_t diag;         // bit 0: PCA9685 responde
  uint8_t resetCausa;   // esp_reset_reason_t
  uint16_t ultimoSeq;
  int16_t aplIzq;
  int16_t aplDer;
  uint8_t aplServo[4];
  int8_t rssi;
  uint16_t reinicios;
  uint32_t uptimeMs;
  uint32_t rxOk;
  uint32_t perdidos;
  uint16_t crcMalos;
  uint16_t failsafes;
  uint8_t crc;
};

static_assert(sizeof(PaqueteControl) == 13, "PaqueteControl debe medir 13 bytes");
static_assert(sizeof(PaqueteTelemetria) == 34, "PaqueteTelemetria debe medir 34 bytes");

uint8_t calcularCrc8(const uint8_t *datos, size_t largo) {
  uint8_t crc = 0;
  for (size_t i = 0; i < largo; i++) {
    crc ^= datos[i];
    for (uint8_t b = 0; b < 8; b++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------
enum Estado : uint8_t { ARRANQUE = 0, SIN_ENLACE = 1, OPERACION = 2, FAILSAFE = 3 };

Adafruit_PWMServoDriver pca(PCA_DIRECCION);
WiFiUDP udp;

Estado estado = ARRANQUE;
bool pcaOk = false;
bool wifiIniciado = false;
uint8_t servoArrancado = 0;
uint32_t ultimoArranqueServoMs = 0;

int objetivoMotor[2] = {0, 0};   // 0 = izquierda, 1 = derecha
int aplicadoMotor[2] = {0, 0};
uint32_t instanteCeroMs[2] = {0, 0};
uint32_t ultimoArranqueMotorMs = 0;

int objetivoServo[4] = {ANGULO_CENTRO, ANGULO_CENTRO, ANGULO_CENTRO, ANGULO_CENTRO};
int aplicadoServo[4] = {ANGULO_CENTRO, ANGULO_CENTRO, ANGULO_CENTRO, ANGULO_CENTRO};
uint32_t ultimoPasoServoMs[4] = {0, 0, 0, 0};
uint8_t turnoServo = 0;

bool haySecuencia = false;
uint16_t ultimoSeq = 0;
uint32_t ultimaRecepcionMs = 0;
uint32_t rxOk = 0;
uint32_t perdidos = 0;
uint16_t crcMalos = 0;
uint16_t failsafes = 0;

uint32_t ultimoTickMs = 0;
uint32_t ultimaTelemetriaMs = 0;
uint32_t ultimoReintentoWifiMs = 0;

uint8_t causaReset = 0;
RTC_NOINIT_ATTR uint32_t rtcMarca;
RTC_NOINIT_ATTR uint32_t rtcReinicios;
const uint32_t RTC_MARCA_VALIDA = 0x524F5652;

char bufferSerie[32];
size_t largoBuffer = 0;

// ---------------------------------------------------------------------------
// Salida USB que nunca bloquea: sin PC conectada, las lineas se descartan.
// Imprimir de forma bloqueante retrasa el lazo y dispara el failsafe.
// ---------------------------------------------------------------------------
void imprimir(const char *linea) {
  size_t largo = strlen(linea);
  if (!Serial || (size_t)Serial.availableForWrite() < largo) {
    return;
  }
  Serial.write((const uint8_t *)linea, largo);
}

// ---------------------------------------------------------------------------
// Motores
// ---------------------------------------------------------------------------
void escribirMotor(int lado, int valor) {
  if (lado == 0 ? INVERTIR_IZQ : INVERTIR_DER) {
    valor = -valor;
  }
  int magnitud = abs(valor);
#if PUENTE_H_L298N
  uint8_t pinEn = (lado == 0) ? PIN_ENA : PIN_ENB;
  uint8_t pinA = (lado == 0) ? PIN_IN1 : PIN_IN3;
  uint8_t pinB = (lado == 0) ? PIN_IN2 : PIN_IN4;
  digitalWrite(pinA, valor > 0 ? HIGH : LOW);
  digitalWrite(pinB, valor < 0 ? HIGH : LOW);
  analogWrite(pinEn, magnitud);
#else
  uint8_t pinAvance = (lado == 0) ? PIN_A1A : PIN_B1A;
  uint8_t pinReversa = (lado == 0) ? PIN_A1B : PIN_B1B;
  analogWrite(pinAvance, valor > 0 ? magnitud : 0);
  analogWrite(pinReversa, valor < 0 ? magnitud : 0);
#endif
}

void pararMotores(uint32_t ahora) {
  for (int lado = 0; lado < 2; lado++) {
    objetivoMotor[lado] = 0;
    if (aplicadoMotor[lado] != 0) {
      instanteCeroMs[lado] = ahora;
    }
    aplicadoMotor[lado] = 0;
    escribirMotor(lado, 0);
  }
}

void actualizarMotores(uint32_t ahora) {
  for (int lado = 0; lado < 2; lado++) {
    int aplicado = aplicadoMotor[lado];
    int objetivo = objetivoMotor[lado];
    if (aplicado == objetivo) {
      continue;
    }

    if (aplicado == 0) {
      if (ahora - instanteCeroMs[lado] < PAUSA_EN_CERO_MS) {
        continue;
      }
      if (ahora - ultimoArranqueMotorMs < DESFASE_ARRANQUE_MS) {
        continue;
      }
      ultimoArranqueMotorMs = ahora;
    }

    bool invierte = (aplicado > 0 && objetivo < 0) || (aplicado < 0 && objetivo > 0);
    int destino = invierte ? 0 : objetivo;
    int nuevo = aplicado + constrain(destino - aplicado, -PASO_RAMPA_PWM, PASO_RAMPA_PWM);

    if (nuevo == 0) {
      instanteCeroMs[lado] = ahora;
    }
    aplicadoMotor[lado] = nuevo;
    escribirMotor(lado, nuevo);
  }
}

// ---------------------------------------------------------------------------
// Servos
// ---------------------------------------------------------------------------
void escribirServo(int canal, int angulo) {
  if (!pcaOk) {
    return;
  }
  angulo = constrain(angulo, ANGULO_MIN, ANGULO_MAX);
  uint16_t ticks = (uint16_t)map(angulo, 0, 180, SERVO_TICKS_0, SERVO_TICKS_180);
  uint16_t inicio = FASE_CANAL[canal];
  pca.setPWM(canal, inicio, inicio + ticks);
}

void actualizarServos(uint32_t ahora) {
  for (int i = 0; i < 4; i++) {
    int canal = (turnoServo + i) % 4;
    if (aplicadoServo[canal] == objetivoServo[canal]) {
      continue;
    }
    if (ahora - ultimoPasoServoMs[canal] < INTERVALO_SERVO_MS) {
      continue;
    }
    int delta = constrain(objetivoServo[canal] - aplicadoServo[canal], -PASO_SERVO_GRADOS, PASO_SERVO_GRADOS);
    aplicadoServo[canal] += delta;
    escribirServo(canal, aplicadoServo[canal]);
    ultimoPasoServoMs[canal] = ahora;
    turnoServo = (uint8_t)((canal + 1) % 4);
    return;  // Una sola escritura por tick
  }
}

void centrarServos() {
  for (int i = 0; i < 4; i++) {
    objetivoServo[i] = ANGULO_CENTRO;
  }
}

// ---------------------------------------------------------------------------
// Recepcion
// ---------------------------------------------------------------------------
void aplicarPaquete(const PaqueteControl &p, uint32_t ahora) {
  uint32_t dt = (estado == OPERACION) ? ahora - ultimaRecepcionMs : 0;

  if (haySecuencia) {
    int16_t salto = (int16_t)(p.seq - ultimoSeq);
    if (salto <= 0 && salto > -100) {
      return;  // Duplicada o fuera de orden. Un salto mayor es un transmisor reiniciado
    }
    if (salto > 1) {
      perdidos += (uint32_t)(salto - 1);
    }
  }
  haySecuencia = true;
  ultimoSeq = p.seq;
  ultimaRecepcionMs = ahora;
  rxOk++;
  estado = OPERACION;

  objetivoMotor[0] = constrain((int)p.izq, -PWM_MAX, PWM_MAX);
  objetivoMotor[1] = constrain((int)p.der, -PWM_MAX, PWM_MAX);
  for (int i = 0; i < 4; i++) {
    objetivoServo[i] = constrain((int)p.servo[i], ANGULO_MIN, ANGULO_MAX);
  }
  if (p.flags & FLAG_EMERGENCIA) {
    pararMotores(ahora);
  }

  char linea[96];
  snprintf(linea, sizeof(linea), "RX,%u,%d,%d,%u,%u,%u,%u,%lu,%d,%d,%d,%d,%d,%d\n", p.seq, p.izq,
           p.der, p.servo[0], p.servo[1], p.servo[2], p.servo[3], (unsigned long)dt, aplicadoMotor[0],
           aplicadoMotor[1], aplicadoServo[0], aplicadoServo[1], aplicadoServo[2], aplicadoServo[3]);
  imprimir(linea);
}

void recibirPaquetes(uint32_t ahora) {
  int tamano;
  while ((tamano = udp.parsePacket()) > 0) {
    PaqueteControl p;
    if (tamano != (int)sizeof(p)) {
      crcMalos++;
      udp.flush();
      continue;
    }
    udp.read((char *)&p, sizeof(p));
    if (p.magic != MAGIC_CONTROL || calcularCrc8((const uint8_t *)&p, sizeof(p) - 1) != p.crc) {
      crcMalos++;
      continue;
    }
    aplicarPaquete(p, ahora);
  }
}

// ---------------------------------------------------------------------------
// Telemetria
// ---------------------------------------------------------------------------
void enviarTelemetria(uint32_t ahora) {
  PaqueteTelemetria t;
  t.magic = MAGIC_TELEMETRIA;
  t.estado = (uint8_t)estado;
  t.diag = pcaOk ? 1 : 0;
  t.resetCausa = causaReset;
  t.ultimoSeq = ultimoSeq;
  t.aplIzq = (int16_t)aplicadoMotor[0];
  t.aplDer = (int16_t)aplicadoMotor[1];
  for (int i = 0; i < 4; i++) {
    t.aplServo[i] = (uint8_t)aplicadoServo[i];
  }
  t.rssi = (WiFi.status() == WL_CONNECTED) ? (int8_t)WiFi.RSSI() : 0;
  t.reinicios = (uint16_t)rtcReinicios;
  t.uptimeMs = ahora;
  t.rxOk = rxOk;
  t.perdidos = perdidos;
  t.crcMalos = crcMalos;
  t.failsafes = failsafes;
  t.crc = calcularCrc8((const uint8_t *)&t, sizeof(t) - 1);

  if (WiFi.status() == WL_CONNECTED) {
    udp.beginPacket(IP_TRANSMISOR, PUERTO_UDP);
    udp.write((const uint8_t *)&t, sizeof(t));
    udp.endPacket();
  }

  char linea[128];
  snprintf(linea, sizeof(linea), "TLM,%u,%d,%d,%u,%u,%u,%u,%d,%u,%u,%lu,%lu,%lu,%u,%u,%u,%u\n",
           t.ultimoSeq, t.aplIzq, t.aplDer, t.aplServo[0], t.aplServo[1], t.aplServo[2],
           t.aplServo[3], t.rssi, t.resetCausa, t.reinicios, (unsigned long)t.uptimeMs,
           (unsigned long)t.rxOk, (unsigned long)t.perdidos, t.crcMalos, t.failsafes, t.estado,
           t.diag);
  imprimir(linea);
}

// ---------------------------------------------------------------------------
// Comandos USB
// ---------------------------------------------------------------------------
void leerSerie() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (largoBuffer > 0) {
        bufferSerie[largoBuffer] = '\0';
        if (strcmp(bufferSerie, "IDENT") == 0) {
          imprimir("ID:NANO_ESP32:RX:" VERSION_FW "\n");
        } else if (strcmp(bufferSerie, "PING") == 0) {
          imprimir("PONG:RX\n");
        }
        largoBuffer = 0;
      }
    } else if (largoBuffer < sizeof(bufferSerie) - 1) {
      bufferSerie[largoBuffer++] = c;
    } else {
      largoBuffer = 0;
    }
  }
}

// ---------------------------------------------------------------------------
// Arranque por etapas, sin bloquear: servos de a uno y despues WiFi
// ---------------------------------------------------------------------------
void iniciarWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // Sin ahorro de energia: evita latencia variable en las tramas
  WiFi.config(IP_LOCAL, IP_TRANSMISOR, MASCARA);
  WiFi.begin(WIFI_SSID, WIFI_PASS, WIFI_CANAL);
  WiFi.setTxPower(POTENCIA_WIFI);
  udp.begin(PUERTO_UDP);
  wifiIniciado = true;
  estado = SIN_ENLACE;
  imprimir("SYS:WIFI_INICIADO\n");
}

void avanzarArranque(uint32_t ahora) {
  if (servoArrancado < 4) {
    if (servoArrancado == 0 || ahora - ultimoArranqueServoMs >= ARRANQUE_SERVO_MS) {
      escribirServo(servoArrancado, ANGULO_CENTRO);
      ultimoArranqueServoMs = ahora;
      servoArrancado++;
    }
    return;
  }
  if (ahora - ultimoArranqueServoMs >= ARRANQUE_SERVO_MS) {
    iniciarWifi();
  }
}

// ---------------------------------------------------------------------------
// Arduino
// ---------------------------------------------------------------------------
void setup() {
  // Primero los motores: apagados antes de cualquier otra cosa
#if PUENTE_H_L298N
  pinMode(PIN_ENA, OUTPUT);
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_ENB, OUTPUT);
  pinMode(PIN_IN3, OUTPUT);
  pinMode(PIN_IN4, OUTPUT);
#else
  pinMode(PIN_A1A, OUTPUT);
  pinMode(PIN_A1B, OUTPUT);
  pinMode(PIN_B1A, OUTPUT);
  pinMode(PIN_B1B, OUTPUT);
#endif
  escribirMotor(0, 0);
  escribirMotor(1, 0);

  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  digitalWrite(LED_RED, HIGH);
  digitalWrite(LED_GREEN, HIGH);
  digitalWrite(LED_BLUE, LOW);

  setCpuFrequencyMhz(160);  // Menor consumo base; suficiente para WiFi y control
  Serial.begin(115200);

  causaReset = (uint8_t)esp_reset_reason();
  if (rtcMarca != RTC_MARCA_VALIDA || causaReset == ESP_RST_POWERON) {
    rtcMarca = RTC_MARCA_VALIDA;
    rtcReinicios = 0;
  } else {
    rtcReinicios++;
  }

  Wire.begin();
  Wire.beginTransmission(PCA_DIRECCION);
  pcaOk = (Wire.endTransmission() == 0);
  if (pcaOk) {
    pca.begin();
    pca.setPWMFreq(50);
  }

  char linea[32];
  snprintf(linea, sizeof(linea), "BOOT,%u,%lu\n", causaReset, (unsigned long)rtcReinicios);
  imprimir(linea);
  if (!pcaOk) {
    imprimir("ERR:PCA9685_NO_RESPONDE\n");
  }
}

void loop() {
  uint32_t ahora = millis();

  leerSerie();

  if (!wifiIniciado) {
    avanzarArranque(ahora);
  } else {
    recibirPaquetes(ahora);

    if (estado == OPERACION && ahora - ultimaRecepcionMs > TIMEOUT_MS) {
      estado = FAILSAFE;
      failsafes++;
      haySecuencia = false;  // Tras un corte se acepta cualquier secuencia del transmisor
      pararMotores(ahora);
      centrarServos();
      imprimir("WARN:FAILSAFE\n");
    }

    if (WiFi.status() != WL_CONNECTED && ahora - ultimoReintentoWifiMs >= PERIODO_REINTENTO_WIFI_MS) {
      ultimoReintentoWifiMs = ahora;
      WiFi.reconnect();
    }

    if (ahora - ultimoTickMs >= PERIODO_TICK_MS) {
      ultimoTickMs = ahora;
      actualizarMotores(ahora);
      actualizarServos(ahora);
    }

    if (ahora - ultimaTelemetriaMs >= PERIODO_TELEMETRIA_MS) {
      ultimaTelemetriaMs = ahora;
      enviarTelemetria(ahora);
    }

    digitalWrite(LED_RED, estado == FAILSAFE ? LOW : HIGH);
    digitalWrite(LED_GREEN, estado == OPERACION ? LOW : HIGH);
    digitalWrite(LED_BLUE, (estado == SIN_ENLACE) ? LOW : HIGH);
  }

  vTaskDelay(1);  // Cede CPU a la pila WiFi sin frenar la logica
}
