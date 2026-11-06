/*
 * ROVER LUNAR - FIRMWARE TRANSMISOR (Arduino Nano ESP32, conectado a la PC)
 * Version: v3.0
 *
 * Cadena de control:  HMI (PC) --USB--> TRANSMISOR --WiFi UDP--> EJECUTOR
 *
 * Funcion:
 *   - Crea la red WiFi del rover (Access Point). El AP esta aca porque esta placa
 *     se alimenta del USB de la PC; el ejecutor queda libre del consumo de emitir
 *     beacons de forma permanente con la bateria compartida con los motores.
 *   - Recibe consignas de la HMI por USB y las retransmite a 20 Hz fijos.
 *   - Si la HMI deja de enviar durante HMI_TIMEOUT_MS, ordena parada. Sin esto el
 *     rover seguiria ejecutando la ultima consigna con la HMI cerrada.
 *   - Reenvia a la HMI la telemetria que llega del ejecutor.
 *
 * Protocolo USB (115200 bps, lineas de texto):
 *   PC -> placa:  CMD,izq,der,s1,s2,s3,s4 | STOP | IDENT | PING
 *   placa -> PC:  ID:NANO_ESP32:TX:v3.0
 *                 PONG:TX
 *                 TX,seq,izq,der,s1,s2,s3,s4,ok       (una linea por trama)
 *                 LINK,clientes,hmi,edad_tlm_ms       (1 Hz)
 *                 TLM,...                             (ver imprimirTelemetria)
 *                 WARN:... / ERR:... / SYS:...
 *
 * LED RGB: azul = esperando al ejecutor; verde = ejecutor con telemetria reciente;
 *          rojo = la HMI dejo de enviar con el ejecutor conectado.
 *
 * Las estructuras PaqueteControl y PaqueteTelemetria deben ser identicas a las de
 * Ejecutor_NanoESP32.ino. tests/test_firmware.py lo comprueba.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <stdio.h>
#include <string.h>

#define VERSION_FW "v3.0"

// ---------------------------------------------------------------------------
// Red
// ---------------------------------------------------------------------------
const char *WIFI_SSID = "ROVER_NET";
const char *WIFI_PASS = "rover1234";
const int WIFI_CANAL = 6;  // Debe coincidir con el ejecutor (evita el barrido de canales)
const IPAddress IP_EJECUTOR(192, 168, 4, 2);
const uint16_t PUERTO_UDP = 4210;

// ---------------------------------------------------------------------------
// Temporizacion
// ---------------------------------------------------------------------------
const uint32_t PERIODO_ENVIO_MS = 50;     // 20 Hz
const uint32_t PERIODO_LINK_MS = 1000;
const uint32_t HMI_TIMEOUT_MS = 500;      // Sin consignas de la HMI: parada
const uint32_t TLM_VIGENTE_MS = 1000;     // Telemetria considerada reciente

// ---------------------------------------------------------------------------
// Limites de seguridad
// ---------------------------------------------------------------------------
const int PWM_MAX = 255;
const int ANGULO_MIN = 10;
const int ANGULO_MAX = 170;
const int ANGULO_CENTRO = 90;

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
WiFiUDP udp;

int16_t consignaIzq = 0;
int16_t consignaDer = 0;
uint8_t consignaServo[4] = {ANGULO_CENTRO, ANGULO_CENTRO, ANGULO_CENTRO, ANGULO_CENTRO};
uint8_t flagsConsigna = 0;
uint16_t secuencia = 0;

bool hmiActiva = false;
uint32_t ultimoCmdHmiMs = 0;
uint32_t ultimoEnvioMs = 0;
uint32_t ultimoLinkMs = 0;
uint32_t ultimaTelemetriaMs = 0;
bool hayTelemetria = false;

char bufferSerie[64];
size_t largoBuffer = 0;

// ---------------------------------------------------------------------------
// Salida USB que nunca bloquea: si la PC no lee, la linea se descarta
// ---------------------------------------------------------------------------
void imprimir(const char *linea) {
  size_t largo = strlen(linea);
  if (!Serial || (size_t)Serial.availableForWrite() < largo) {
    return;
  }
  Serial.write((const uint8_t *)linea, largo);
}

// ---------------------------------------------------------------------------
// Consignas
// ---------------------------------------------------------------------------
void consignaDeParada(uint8_t flags) {
  consignaIzq = 0;
  consignaDer = 0;
  for (int i = 0; i < 4; i++) {
    consignaServo[i] = ANGULO_CENTRO;
  }
  flagsConsigna = flags;
}

void enviarTrama() {
  PaqueteControl p;
  p.magic = MAGIC_CONTROL;
  p.flags = flagsConsigna;
  p.izq = consignaIzq;
  p.der = consignaDer;
  memcpy(p.servo, consignaServo, sizeof(p.servo));

  bool ok = false;
  if (WiFi.softAPgetStationNum() > 0) {
    p.seq = ++secuencia;
    p.crc = calcularCrc8((const uint8_t *)&p, sizeof(p) - 1);
    udp.beginPacket(IP_EJECUTOR, PUERTO_UDP);
    udp.write((const uint8_t *)&p, sizeof(p));
    ok = (udp.endPacket() == 1);
  } else {
    p.seq = secuencia;
  }

  char linea[64];
  snprintf(linea, sizeof(linea), "TX,%u,%d,%d,%u,%u,%u,%u,%d\n", p.seq, p.izq, p.der,
           p.servo[0], p.servo[1], p.servo[2], p.servo[3], ok ? 1 : 0);
  imprimir(linea);
}

void procesarLinea(char *linea, uint32_t ahora) {
  if (strcmp(linea, "IDENT") == 0) {
    imprimir("ID:NANO_ESP32:TX:" VERSION_FW "\n");
    return;
  }
  if (strcmp(linea, "PING") == 0) {
    imprimir("PONG:TX\n");
    return;
  }
  if (strcmp(linea, "STOP") == 0) {
    consignaDeParada(FLAG_EMERGENCIA);
    hmiActiva = true;
    ultimoCmdHmiMs = ahora;
    enviarTrama();  // La parada no espera al siguiente periodo
    ultimoEnvioMs = ahora;
    imprimir("SYS:STOP\n");
    return;
  }

  int izq, der, s1, s2, s3, s4;
  char sobrante;
  int campos = sscanf(linea, "CMD,%d,%d,%d,%d,%d,%d%c", &izq, &der, &s1, &s2, &s3, &s4, &sobrante);
  if (campos != 6) {
    imprimir("ERR:TRAMA\n");
    return;
  }

  consignaIzq = (int16_t)constrain(izq, -PWM_MAX, PWM_MAX);
  consignaDer = (int16_t)constrain(der, -PWM_MAX, PWM_MAX);
  consignaServo[0] = (uint8_t)constrain(s1, ANGULO_MIN, ANGULO_MAX);
  consignaServo[1] = (uint8_t)constrain(s2, ANGULO_MIN, ANGULO_MAX);
  consignaServo[2] = (uint8_t)constrain(s3, ANGULO_MIN, ANGULO_MAX);
  consignaServo[3] = (uint8_t)constrain(s4, ANGULO_MIN, ANGULO_MAX);
  flagsConsigna = 0;
  hmiActiva = true;
  ultimoCmdHmiMs = ahora;
}

void leerSerie(uint32_t ahora) {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (largoBuffer > 0) {
        bufferSerie[largoBuffer] = '\0';
        procesarLinea(bufferSerie, ahora);
        largoBuffer = 0;
      }
    } else if (largoBuffer < sizeof(bufferSerie) - 1) {
      bufferSerie[largoBuffer++] = c;
    } else {
      largoBuffer = 0;  // Linea demasiado larga: se descarta entera
    }
  }
}

// ---------------------------------------------------------------------------
// Telemetria del ejecutor
// ---------------------------------------------------------------------------
void imprimirTelemetria(const PaqueteTelemetria &t) {
  // TLM,seq,aIzq,aDer,a1,a2,a3,a4,rssi,causa,reinicios,uptime,rxOk,perdidos,crc,failsafes,estado,diag
  char linea[128];
  snprintf(linea, sizeof(linea), "TLM,%u,%d,%d,%u,%u,%u,%u,%d,%u,%u,%lu,%lu,%lu,%u,%u,%u,%u\n",
           t.ultimoSeq, t.aplIzq, t.aplDer, t.aplServo[0], t.aplServo[1], t.aplServo[2],
           t.aplServo[3], t.rssi, t.resetCausa, t.reinicios, (unsigned long)t.uptimeMs,
           (unsigned long)t.rxOk, (unsigned long)t.perdidos, t.crcMalos, t.failsafes, t.estado,
           t.diag);
  imprimir(linea);
}

void recibirTelemetria(uint32_t ahora) {
  int tamano;
  while ((tamano = udp.parsePacket()) > 0) {
    PaqueteTelemetria t;
    if (tamano != (int)sizeof(t)) {
      udp.flush();
      continue;
    }
    udp.read((char *)&t, sizeof(t));
    if (t.magic != MAGIC_TELEMETRIA || calcularCrc8((const uint8_t *)&t, sizeof(t) - 1) != t.crc) {
      continue;
    }
    ultimaTelemetriaMs = ahora;
    hayTelemetria = true;
    imprimirTelemetria(t);
  }
}

// ---------------------------------------------------------------------------
// LED RGB (anodo comun: activo en bajo)
// ---------------------------------------------------------------------------
void ponerLed(bool rojo, bool verde, bool azul) {
  digitalWrite(LED_RED, rojo ? LOW : HIGH);
  digitalWrite(LED_GREEN, verde ? LOW : HIGH);
  digitalWrite(LED_BLUE, azul ? LOW : HIGH);
}

void actualizarLed(uint32_t ahora) {
  bool ejecutorVivo = hayTelemetria && (ahora - ultimaTelemetriaMs < TLM_VIGENTE_MS);
  if (!ejecutorVivo) {
    ponerLed(false, false, true);
  } else if (!hmiActiva) {
    ponerLed(true, false, false);
  } else {
    ponerLed(false, true, false);
  }
}

// ---------------------------------------------------------------------------
// Arduino
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);

  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  ponerLed(false, false, true);

  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_SSID, WIFI_PASS, WIFI_CANAL, 0, 1);  // IP por defecto: 192.168.4.1
  WiFi.setSleep(false);
  udp.begin(PUERTO_UDP);

  imprimir("SYS:TRANSMISOR_LISTO\n");
}

void loop() {
  uint32_t ahora = millis();

  leerSerie(ahora);
  recibirTelemetria(ahora);

  if (hmiActiva && (ahora - ultimoCmdHmiMs > HMI_TIMEOUT_MS)) {
    hmiActiva = false;
    consignaDeParada(FLAG_EMERGENCIA);
    imprimir("WARN:HMI_TIMEOUT\n");
    enviarTrama();
    ultimoEnvioMs = ahora;
  }

  if (ahora - ultimoEnvioMs >= PERIODO_ENVIO_MS) {
    ultimoEnvioMs = ahora;
    enviarTrama();
  }

  if (ahora - ultimoLinkMs >= PERIODO_LINK_MS) {
    ultimoLinkMs = ahora;
    char linea[48];
    long edad = hayTelemetria ? (long)(ahora - ultimaTelemetriaMs) : -1;
    snprintf(linea, sizeof(linea), "LINK,%d,%d,%ld\n", WiFi.softAPgetStationNum(), hmiActiva ? 1 : 0, edad);
    imprimir(linea);
  }

  actualizarLed(ahora);
  vTaskDelay(1);  // Cede CPU a la pila WiFi sin frenar la logica
}
