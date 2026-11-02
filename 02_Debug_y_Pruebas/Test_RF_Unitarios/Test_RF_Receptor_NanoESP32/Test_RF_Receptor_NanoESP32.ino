/*
 * =====================================================================================
 *  TEST RF RECEPTOR — ARDUINO NANO ESP32 (COM21)
 *  Rover Lunar V2.0 — Diagnostico de enlace NRF24L01+ sin dependencias de actuadores
 * =====================================================================================
 *  Hardware: Arduino Nano ESP32 (ESP32-S3 a 3.3V) + NRF24L01+
 *
 *  CONEXIONADO DE PINES:
 *    - NRF24 VCC:  3.3V (¡NUNCA 5V! Con capacitor 10uF a 100uF entre VCC y GND)
 *    - NRF24 GND:  GND comun
 *    - NRF24 CE:   Pin D9  (GPIO 18)
 *    - NRF24 CSN:  Pin D10 (GPIO 21)
 *    - NRF24 MOSI: Pin D11 (GPIO 38 - SPI Hardware)
 *    - NRF24 MISO: Pin D12 (GPIO 47 - SPI Hardware)
 *    - NRF24 SCK:  Pin D13 (GPIO 48 - SPI Hardware)
 *
 *  NOTA CRITICA:
 *    Se utilizan constantes D9, D10, D11, D12, D13 para compatibilidad absoluta
 *    tanto en modo 'By Arduino pin' como en modo 'By GPIO number'.
 * =====================================================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>

#define PIN_RF_CE   D9
#define PIN_RF_CSN  D10

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

unsigned long totalPaquetes = 0;
unsigned long ultimaRecepcion = 0;
unsigned long ultimoAvisoEspera = 0;
const uint8_t CANAL_RF = 108;

void imprimirConfiguracion() {
  Serial.println();
  Serial.println("=======================================================");
  Serial.println("   DIAGNOSTICO RF RECEPTOR - ARDUINO NANO ESP32");
  Serial.println("=======================================================");
  Serial.print("   Chip NRF24 detectado: ");
  if (radio.isChipConnected()) {
    Serial.println("SI (Comunicacion SPI correcta)");
  } else {
    Serial.println("NO (ERROR: Revisar cableado SPI y alimentacion 3.3V)");
  }
  Serial.print("   Canal RF:             "); Serial.print(CANAL_RF); Serial.println(" (2.508 GHz)");
  Serial.println("   Velocidad de datos:   250 KBPS");
  Serial.println("   Potencia PA:          RF24_PA_MAX");
  Serial.println("   Auto-ACK:             DESHABILITADO (Streaming continuo)");
  Serial.print("   Tamano de payload:    "); Serial.print(sizeof(PaqueteControl)); Serial.println(" bytes");
  Serial.println("   Pipe de lectura:      \"ROVER\"");
  Serial.println("=======================================================");
  Serial.println("Esperando paquetes desde el transmisor en COM4...");
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Inicializacion explicita del bus SPI con pines de Arduino Nano ESP32
  SPI.begin(SCK, MISO, MOSI, SS);

  if (!radio.begin()) {
    Serial.println("[ERROR] radio.begin() fallo en Arduino Nano ESP32.");
    Serial.println("[CHECK] Verifica: D9(CE), D10(CSN), D11(MOSI), D12(MISO), D13(SCK) y VCC a 3.3V.");
  } else {
    radio.setPayloadSize(sizeof(PaqueteControl));
    radio.setPALevel(RF24_PA_MAX);
    radio.setDataRate(RF24_250KBPS);
    radio.setChannel(CANAL_RF);
    radio.setAutoAck(false);
    radio.openReadingPipe(1, DIRECCION_RF);
    radio.startListening();
  }

  imprimirConfiguracion();
}

void loop() {
  if (radio.available()) {
    PaqueteControl paquete;

    while (radio.available()) {
      radio.read(&paquete, sizeof(paquete));
    }

    totalPaquetes++;
    unsigned long ahora = millis();
    unsigned long dt = (ultimaRecepcion > 0) ? (ahora - ultimaRecepcion) : 0;
    ultimaRecepcion = ahora;

    // Destello de LED al recibir paquete
    digitalWrite(LED_BUILTIN, HIGH);

    Serial.print("[RX #");
    Serial.print(totalPaquetes);
    Serial.print(" | dt: ");
    Serial.print(dt);
    Serial.print(" ms] TracIzq: ");
    Serial.print(paquete.traccion_izq);
    Serial.print(" | TracDer: ");
    Serial.print(paquete.traccion_der);
    Serial.print(" | S1: ");
    Serial.print(paquete.angulo_s1);
    Serial.print(" | S2: ");
    Serial.print(paquete.angulo_s2);
    Serial.print(" | S3: ");
    Serial.print(paquete.angulo_s3);
    Serial.print(" | S4: ");
    Serial.println(paquete.angulo_s4);

    delay(10);
    digitalWrite(LED_BUILTIN, LOW);
  }

  // Notificacion periodica si no se reciben paquetes
  if (millis() - ultimaRecepcion > 3000 && millis() - ultimoAvisoEspera > 3000) {
    ultimoAvisoEspera = millis();
    if (radio.isChipConnected()) {
      Serial.println("[ESPERANDO] Modulo RF OK. Sin paquetes recibidos en los ultimos 3 segundos...");
    } else {
      Serial.println("[ERROR] NRF24 perdio comunicacion SPI. Verificar cables y alimentacion.");
    }
  }

  // Lectura de comandos de depuracion por consola
  if (Serial.available()) {
    char c = Serial.read();
    if (c == '?' || c == 'h' || c == 'H') {
      imprimirConfiguracion();
    }
  }
}
