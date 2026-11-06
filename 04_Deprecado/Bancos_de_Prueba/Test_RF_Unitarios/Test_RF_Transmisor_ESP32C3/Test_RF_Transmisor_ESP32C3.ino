/*
 * =====================================================================================
 *  TEST RF TRANSMISOR — ESP32-C3 (COM4)
 *  Rover Lunar V2.0 — Emision periodica e interactiva para diagnostico de enlace RF
 * =====================================================================================
 *  Hardware: ESP32-C3 SuperMini / LOLIN C3 Mini + NRF24L01+
 *
 *  CONEXIONADO DE PINES:
 *    - NRF24 VCC:  3.3V (¡NUNCA 5V! Con capacitor 10uF a 100uF entre VCC y GND)
 *    - NRF24 GND:  GND comun
 *    - NRF24 CE:   GPIO 4
 *    - NRF24 CSN:  GPIO 7
 *    - NRF24 SCK:  GPIO 6
 *    - NRF24 MOSI: GPIO 3
 *    - NRF24 MISO: GPIO 5
 * =====================================================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>

#define PIN_RF_CE   4
#define PIN_RF_CSN  7

RF24 radio(PIN_RF_CE, PIN_RF_CSN);
const byte DIRECCION_RF[6] = "ROVER";

// Estructura oficial de 8 bytes empaquetados
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255
  int16_t traccion_der;  // -255 a 255
  uint8_t angulo_s1;     // 10 a 170
  uint8_t angulo_s2;     // 10 a 170
  uint8_t angulo_s3;     // 10 a 170
  uint8_t angulo_s4;     // 10 a 170
};

PaqueteControl datosEnvio = {100, 100, 90, 90, 90, 90};

unsigned long totalEnvios = 0;
unsigned long ultimoEnvio = 0;
const unsigned long INTERVALO_ENVIO_MS = 1000;
const uint8_t CANAL_RF = 108;
bool envioAutomatico = true;

void imprimirConfiguracion() {
  Serial.println();
  Serial.println("=======================================================");
  Serial.println("   DIAGNOSTICO RF TRANSMISOR - ESP32-C3 (COM4)");
  Serial.println("=======================================================");
  Serial.print("   Chip NRF24 detectado: ");
  if (radio.isChipConnected()) {
    Serial.println("SI (Comunicacion SPI correcta)");
  } else {
    Serial.println("NO (ERROR: Revisar cables SPI GPIO 3,4,5,6,7 y 3.3V)");
  }
  Serial.print("   Canal RF:             "); Serial.print(CANAL_RF); Serial.println(" (2.508 GHz)");
  Serial.println("   Velocidad de datos:   250 KBPS");
  Serial.println("   Potencia PA:          RF24_PA_MAX");
  Serial.println("   Auto-ACK:             DESHABILITADO (Streaming continuo)");
  Serial.print("   Tamano de payload:    "); Serial.print(sizeof(PaqueteControl)); Serial.println(" bytes");
  Serial.println("   Pipe de transmision:  \"ROVER\"");
  Serial.println("-------------------------------------------------------");
  Serial.println("Comandos por teclado en Monitor Serie (115200 baudios):");
  Serial.println("   'w' -> Avance adelante (Trac 180, Servos 90)");
  Serial.println("   's' -> Reversa (Trac -180, Servos 90)");
  Serial.println("   'a' -> Giro izquierda (Trac 120, Servos 120)");
  Serial.println("   'd' -> Giro derecha (Trac 120, Servos 60)");
  Serial.println("   'x' -> Parada (Trac 0, Servos 90)");
  Serial.println("   'm' -> Alternar envio automatico 1 Hz (ON/OFF)");
  Serial.println("   '?' -> Reimprimir esta configuracion");
  Serial.println("=======================================================");
  Serial.println();
}

void enviarTrama() {
  totalEnvios++;
  radio.write(&datosEnvio, sizeof(datosEnvio));

  Serial.print("[TX #");
  Serial.print(totalEnvios);
  Serial.print("] Enviado por RF -> Trac:[");
  Serial.print(datosEnvio.traccion_izq);
  Serial.print(", ");
  Serial.print(datosEnvio.traccion_der);
  Serial.print("] | Servos:[");
  Serial.print(datosEnvio.angulo_s1);
  Serial.print(", ");
  Serial.print(datosEnvio.angulo_s2);
  Serial.print(", ");
  Serial.print(datosEnvio.angulo_s3);
  Serial.print(", ");
  Serial.print(datosEnvio.angulo_s4);
  Serial.println("]");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  // Inicializacion del bus SPI hardware en ESP32-C3
  // SCK: 6, MISO: 5, MOSI: 3, SS: 7
  SPI.begin(6, 5, 3, 7);

  if (!radio.begin()) {
    Serial.println("[ERROR] radio.begin() fallo en ESP32-C3.");
    Serial.println("[CHECK] Verifica: GPIO4(CE), GPIO7(CSN), GPIO6(SCK), GPIO3(MOSI), GPIO5(MISO) y 3.3V.");
  } else {
    radio.setPayloadSize(sizeof(PaqueteControl));
    radio.setPALevel(RF24_PA_MAX);
    radio.setDataRate(RF24_250KBPS);
    radio.setChannel(CANAL_RF);
    radio.setAutoAck(false);
    radio.openWritingPipe(DIRECCION_RF);
    radio.stopListening();
  }

  imprimirConfiguracion();
}

void loop() {
  if (envioAutomatico && (millis() - ultimoEnvio >= INTERVALO_ENVIO_MS)) {
    ultimoEnvio = millis();
    enviarTrama();
  }

  if (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n') return;

    if (c == 'w' || c == 'W') {
      datosEnvio.traccion_izq = 180;
      datosEnvio.traccion_der = 180;
      datosEnvio.angulo_s1 = 90;
      datosEnvio.angulo_s2 = 90;
      datosEnvio.angulo_s3 = 90;
      datosEnvio.angulo_s4 = 90;
      enviarTrama();
    } else if (c == 's' || c == 'S') {
      datosEnvio.traccion_izq = -180;
      datosEnvio.traccion_der = -180;
      datosEnvio.angulo_s1 = 90;
      datosEnvio.angulo_s2 = 90;
      datosEnvio.angulo_s3 = 90;
      datosEnvio.angulo_s4 = 90;
      enviarTrama();
    } else if (c == 'a' || c == 'A') {
      datosEnvio.traccion_izq = 120;
      datosEnvio.traccion_der = 120;
      datosEnvio.angulo_s1 = 120;
      datosEnvio.angulo_s2 = 120;
      datosEnvio.angulo_s3 = 120;
      datosEnvio.angulo_s4 = 120;
      enviarTrama();
    } else if (c == 'd' || c == 'D') {
      datosEnvio.traccion_izq = 120;
      datosEnvio.traccion_der = 120;
      datosEnvio.angulo_s1 = 60;
      datosEnvio.angulo_s2 = 60;
      datosEnvio.angulo_s3 = 60;
      datosEnvio.angulo_s4 = 60;
      enviarTrama();
    } else if (c == 'x' || c == 'X') {
      datosEnvio.traccion_izq = 0;
      datosEnvio.traccion_der = 0;
      datosEnvio.angulo_s1 = 90;
      datosEnvio.angulo_s2 = 90;
      datosEnvio.angulo_s3 = 90;
      datosEnvio.angulo_s4 = 90;
      enviarTrama();
    } else if (c == 'm' || c == 'M') {
      envioAutomatico = !envioAutomatico;
      Serial.print("[CONFIG] Envio automatico 1 Hz: ");
      Serial.println(envioAutomatico ? "ACTIVADO" : "DESACTIVADO");
    } else if (c == '?' || c == 'h' || c == 'H') {
      imprimirConfiguracion();
    }
  }
}
