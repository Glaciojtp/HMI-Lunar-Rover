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
    char tecla = Serial.read();
    tecla = toLowerCase(tecla); // Convertir a minúscula para no lidiar con Mayus

    if (tecla == 'w') {
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
      datosControl.traccion = 250;
      Serial.println("Avanzando...");
    } 
    else if (tecla == 's') {
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
      datosControl.traccion = -250;
      Serial.println("Retrocediendo...");

    } 
    else if (tecla == ' ' || tecla == 'x') { // Barra espaciadora o 'X' para detener
      datosControl.traccion = 0;
      Serial.println("Detenido.");
    } 
    else if (tecla == 'a') {
      Serial.println("Pulso Izquierda");
      // 1. Girar servos
      datosControl.angulo_s1 = 120; datosControl.angulo_s2 = 120;
      datosControl.traccion = 0;
      enviarPaquete();
      delay(300); // Tiempo para que el servo llegue a la posicion
      
      // 2. Pulso de tracción
     
      datosControl.traccion = 250;
      enviarPaquete();
      delay(500); // Tiempo avanzando
      
      // 3. Frenar y centrar
      datosControl.traccion = 0;
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
    } 
    else if (tecla == 'd') {
      Serial.println("Pulso Derecha");
      // 1. Girar servos
      datosControl.angulo_s1 = 60; datosControl.angulo_s2 = 60;
      datosControl.traccion = 0;
      enviarPaquete();
      delay(300); 
      
      // 2. Pulso de tracción
      datosControl.traccion = 250;
      enviarPaquete();
      delay(500); 
      
      // 3. Frenar y centrar
      datosControl.traccion = 0;
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
    }
  }

  // Transmisión continua para que el MKR no active el Timeout
  if (millis() - ultimoEnvio > INTERVALO_ENVIO) {
    enviarPaquete();
    ultimoEnvio = millis();
  }
}