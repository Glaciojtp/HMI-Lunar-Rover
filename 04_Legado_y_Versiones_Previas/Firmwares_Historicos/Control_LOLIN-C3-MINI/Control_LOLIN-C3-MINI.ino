/*
 * ============================================================
 *  TRANSMISOR NRF24L01 — Control WASD
 * ============================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>

#define PIN_CE   4
#define PIN_CSN  7
RF24 radio(PIN_CE, PIN_CSN);
const byte DIRECCION[6] = "ROVER";
int potenciaCalibrada = 150; // Variable global para guardar la calibración

struct Paquete {
  int traccion;      
  uint8_t angulo_s1; 
  uint8_t angulo_s2; 
};

Paquete datosControl = {0, 90, 90}; 
unsigned long ultimoEnvio = 0;
const int INTERVALO_ENVIO = 100;

void enviarPaquete() {
  radio.write(&datosControl, sizeof(datosControl));
}

void setup() {
  setCpuFrequencyMhz(80);
  Serial.begin(115200);
  delay(1000);

  SPI.begin(6, 5, 3, 7);

  if (!radio.begin()) {
    Serial.println("ERROR: No NRF24L01 en ESP32.");
    while (1) { delay(500); }
  }

  radio.setPALevel(RF24_PA_MAX);
  radio.setDataRate(RF24_250KBPS);
  radio.setChannel(108);
  radio.setAutoAck(true);
  radio.setRetries(5, 15);
  radio.openWritingPipe(DIRECCION);
  radio.stopListening();

  Serial.println("Transmisor WASD Listo.");
  Serial.println("W = Adelante | S = Atras | A = Pulso Izq | D = Pulso Der | Espacio = Parar");
}



void loop() {
  if (Serial.available() > 0) {
    String entrada = Serial.readStringUntil('\n');
    entrada.trim();
    entrada.toUpperCase();

    // 1. Comando de calibración de velocidad
    if (entrada.startsWith("V")) {
      potenciaCalibrada = entrada.substring(1).toInt();
      Serial.print("Velocidad calibrada a: ");
      Serial.println(potenciaCalibrada);
    } 
    // 2. Comandos de movimiento
    else if (entrada == "W") {
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
      datosControl.traccion = potenciaCalibrada;
    } 
    else if (entrada == "S") {
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
      datosControl.traccion = -potenciaCalibrada;
    } 
    else if (entrada == "A") {
      datosControl.angulo_s1 = 120; datosControl.angulo_s2 = 120;
      datosControl.traccion = 0;
      enviarPaquete();
      delay(300); 
      datosControl.traccion = potenciaCalibrada;
      enviarPaquete();
      delay(500); 
      datosControl.traccion = 0;
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
    } 
    else if (entrada == "D") {
      datosControl.angulo_s1 = 60; datosControl.angulo_s2 = 60;
      datosControl.traccion = 0;
      enviarPaquete();
      delay(300); 
      datosControl.traccion = potenciaCalibrada;
      enviarPaquete();
      delay(500); 
      datosControl.traccion = 0;
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
    }
    else if (entrada == " " || entrada == "") {
      datosControl.traccion = 0;
    }
  }

  // Transmisión continua
  if (millis() - ultimoEnvio > INTERVALO_ENVIO) {
    enviarPaquete();
    ultimoEnvio = millis();
  }
}