/*
 * =====================================================================================
 *  TRANSMISOR ESP32 LOLIN C3 MINI / SUPERMINI — ROVER LUNAR V2.0
 *  Soporte Completo para Rocker-Bogie 6x6: 6 Motores + 4 Servos Independientes
 * =====================================================================================
 *  Hardware: ESP32-C3 + NRF24L01+
 *  Pines SPI Hardware:
 *    - CE:   GPIO 4
 *    - CSN:  GPIO 7
 *    - SCK:  GPIO 6
 *    - MOSI: GPIO 3
 *    - MISO: GPIO 5
 * =====================================================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>

#define PIN_CE   4
#define PIN_CSN  7

RF24 radio(PIN_CE, PIN_CSN);
const byte DIRECCION_RF[6] = "ROVER";

// Estructura de transmisión unificada (8 bytes empaquetados)
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255 (Lado Izquierdo: M1, M2, M3)
  int16_t traccion_der;  // -255 a 255 (Lado Derecho:   M4, M5, M6)
  uint8_t angulo_s1;     // S1: Delantero Izquierdo (10° a 170°)
  uint8_t angulo_s2;     // S2: Delantero Derecho   (10° a 170°)
  uint8_t angulo_s3;     // S3: Trasero Izquierdo   (10° a 170°)
  uint8_t angulo_s4;     // S4: Trasero Derecho     (10° a 170°)
};

PaqueteControl datosControl = {0, 0, 90, 90, 90, 90};

// Temporizadores no bloqueantes
unsigned long ultimoEnvioRF = 0;
const unsigned long INTERVALO_RF_MS = 50; // 20 Hz continuo

// Buffer Serial no bloqueante
char bufferSerial[128];
byte indiceBuffer = 0;

void procesarComando(char* cmdStr) {
  String trama = String(cmdStr);
  trama.trim();
  if (trama.length() == 0) return;

  // Comando de Parada de Emergencia
  if (trama.equalsIgnoreCase("STOP") || trama.equalsIgnoreCase("PARAR") || trama.equals(" ")) {
    datosControl.traccion_izq = 0;
    datosControl.traccion_der = 0;
    datosControl.angulo_s1 = 90;
    datosControl.angulo_s2 = 90;
    datosControl.angulo_s3 = 90;
    datosControl.angulo_s4 = 90;
    Serial.println("STATUS:STOP");
    return;
  }

  // Parseo de trama CSV
  // Formato HMI V2 extendido: "CMD,PotIzq,PotDer,S1,S2,S3,S4"
  // Ejemplo: "W,150,150,90,90,90,90" o "PIVOT_IZQ,150,150,135,45,45,135"

  int partes[7];
  int ultimoIdx = 0;
  int contadorPartes = 0;

  for (int i = 0; i < trama.length() && contadorPartes < 6; i++) {
    if (trama.charAt(i) == ',') {
      partes[contadorPartes++] = i;
    }
  }

  // Si vienen los 4 servos explícitos (6 comas encontradas)
  if (contadorPartes >= 6) {
    String cmd = trama.substring(0, partes[0]);
    cmd.toUpperCase();

    int potIzq = trama.substring(partes[0] + 1, partes[1]).toInt();
    int potDer = trama.substring(partes[1] + 1, partes[2]).toInt();
    int s1     = trama.substring(partes[2] + 1, partes[3]).toInt();
    int s2     = trama.substring(partes[3] + 1, partes[4]).toInt();
    int s3     = trama.substring(partes[4] + 1, partes[5]).toInt();
    int s4     = trama.substring(partes[5] + 1).toInt();

    datosControl.angulo_s1 = constrain(s1, 10, 170);
    datosControl.angulo_s2 = constrain(s2, 10, 170);
    datosControl.angulo_s3 = constrain(s3, 10, 170);
    datosControl.angulo_s4 = constrain(s4, 10, 170);

    if (cmd == "W") {
      datosControl.traccion_izq = potIzq;
      datosControl.traccion_der = potDer;
    } else if (cmd == "S") {
      datosControl.traccion_izq = -potIzq;
      datosControl.traccion_der = -potDer;
    } else if (cmd == "PIVOT_IZQ") {
      // Giro sobre su eje: Lado Izq en reversa, Lado Der en avance
      datosControl.traccion_izq = -potIzq;
      datosControl.traccion_der = potDer;
    } else if (cmd == "PIVOT_DER") {
      // Giro sobre su eje: Lado Izq en avance, Lado Der en reversa
      datosControl.traccion_izq = potIzq;
      datosControl.traccion_der = -potDer;
    } else if (cmd == "A" || cmd == "D" || cmd == "CRAB") {
      datosControl.traccion_izq = potIzq;
      datosControl.traccion_der = potDer;
    } else {
      datosControl.traccion_izq = 0;
      datosControl.traccion_der = 0;
    }

    Serial.println("STATUS:OK_4SERVO");
    return;
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

void setup() {
  setCpuFrequencyMhz(80);
  Serial.begin(115200);
  delay(500);

  SPI.begin(6, 5, 3, 7);

  if (!radio.begin()) {
    Serial.println("ERROR: NRF24L01 no detectado en ESP32.");
  } else {
    radio.setPALevel(RF24_PA_MAX);
    radio.setDataRate(RF24_250KBPS);
    radio.setChannel(108);
    radio.setAutoAck(true);
    radio.setRetries(5, 15);
    radio.openWritingPipe(DIRECCION_RF);
    radio.stopListening();
    Serial.println("SYS:ESP32_TX_4SERVO_READY");
  }
}

void loop() {
  leerSerialNoBloqueante();

  if (millis() - ultimoEnvioRF >= INTERVALO_RF_MS) {
    ultimoEnvioRF = millis();
    radio.write(&datosControl, sizeof(datosControl));
  }
}
