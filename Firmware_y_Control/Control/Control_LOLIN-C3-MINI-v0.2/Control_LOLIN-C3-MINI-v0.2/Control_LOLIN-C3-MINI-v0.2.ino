#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>

#define PIN_CE   4
#define PIN_CSN  7
RF24 radio(PIN_CE, PIN_CSN);
const byte DIRECCION[6] = "ROVER";

// Estructura estrictamente empaquetada y de tamaño fijo
struct __attribute__((packed)) Paquete {
  int16_t traccion_izq;      
  int16_t traccion_der;      
  uint8_t angulo_s1; 
  uint8_t angulo_s2; 
};

Paquete datosControl = {0, 0, 90, 90}; 

unsigned long ultimoEnvio = 0;
unsigned long tiempoSecuencia = 0;
int estadoSecuencia = 0; 
int potGuardadaIzq = 150;
int potGuardadaDer = 150;

void setup() {
  setCpuFrequencyMhz(80);
  Serial.begin(115200);
  SPI.begin(6, 5, 3, 7);
  
  radio.begin();
  radio.setPALevel(RF24_PA_MAX);
  radio.setDataRate(RF24_250KBPS);
  radio.setChannel(108);
  radio.setAutoAck(true);
  radio.setRetries(5, 15);
  radio.openWritingPipe(DIRECCION);
  radio.stopListening();
}

void loop() {
  if (Serial.available() > 0) {
    String trama = Serial.readStringUntil('\n');
    trama.trim();
    int p1 = trama.indexOf(',');
    int p2 = trama.lastIndexOf(',');

    if (p1 != -1 && p2 != -1 && p1 != p2) {
      String cmd = trama.substring(0, p1);
      potGuardadaIzq = trama.substring(p1 + 1, p2).toInt();
      potGuardadaDer = trama.substring(p2 + 1).toInt();

      if (cmd == "W") {
        estadoSecuencia = 0;
        datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
        datosControl.traccion_izq = potGuardadaIzq; 
        datosControl.traccion_der = potGuardadaDer;
      } 
      else if (cmd == "S") {
        estadoSecuencia = 0;
        datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
        datosControl.traccion_izq = -potGuardadaIzq; 
        datosControl.traccion_der = -potGuardadaDer;
      } 
      else if (cmd == " ") {
        estadoSecuencia = 0;
        datosControl.traccion_izq = 0; 
        datosControl.traccion_der = 0;
      } 
      else if (cmd == "A" && estadoSecuencia == 0) {
        estadoSecuencia = 1; 
        tiempoSecuencia = millis();
        // Límite de seguridad 10-170 aplicado a la inversa para girar
        datosControl.angulo_s1 = 120; datosControl.angulo_s2 = 120; 
        datosControl.traccion_izq = 0; datosControl.traccion_der = 0;
      } 
      else if (cmd == "D" && estadoSecuencia == 0) {
        estadoSecuencia = 2; 
        tiempoSecuencia = millis();
        datosControl.angulo_s1 = 60; datosControl.angulo_s2 = 60; 
        datosControl.traccion_izq = 0; datosControl.traccion_der = 0;
      }
    }
  }

  // Secuencia temporal no bloqueante
  if (estadoSecuencia == 1 || estadoSecuencia == 2) {
    unsigned long tiempoTranscurrido = millis() - tiempoSecuencia;
    if (tiempoTranscurrido > 300 && tiempoTranscurrido <= 800) {
      datosControl.traccion_izq = potGuardadaIzq;
      datosControl.traccion_der = potGuardadaDer;
    } else if (tiempoTranscurrido > 800) {
      datosControl.traccion_izq = 0; datosControl.traccion_der = 0;
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
      estadoSecuencia = 0; 
    }
  }

  if (millis() - ultimoEnvio > 100) {
    radio.write(&datosControl, sizeof(datosControl));
    ultimoEnvio = millis();
  }
}