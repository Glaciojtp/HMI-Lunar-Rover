#include <SPI.h>
#include <RF24.h>
#include <Servo.h>

#define PIN_CE 0
#define PIN_CSN 1
RF24 radio(PIN_CE, PIN_CSN);
const byte DIRECCION[6] = "ROVER";

// Misma estructura empaquetada
struct __attribute__((packed)) Paquete {
  int16_t traccion_izq;      
  int16_t traccion_der;      
  uint8_t angulo_s1; 
  uint8_t angulo_s2; 
};

Servo servo1;
Servo servo2;
const int pinServo1 = 6;
const int pinServo2 = 7;

const int pinA1A = 2; 
const int pinA1B = 5; 
const int pinB1A = 3; 
const int pinB1B = 4; 

unsigned long ultimaRecepcion = 0;
#define TIMEOUT_MS 1000 

void pararMotores() {
  analogWrite(pinA1A, 0); analogWrite(pinA1B, 0);
  analogWrite(pinB1A, 0); analogWrite(pinB1B, 0);
}

void setup() {
  Serial.begin(115200);

  servo1.attach(pinServo1);
  servo2.attach(pinServo2);
  servo1.write(90);
  servo2.write(90);

  pinMode(pinA1A, OUTPUT); pinMode(pinA1B, OUTPUT);
  pinMode(pinB1A, OUTPUT); pinMode(pinB1B, OUTPUT);
  pararMotores();

  if (!radio.begin()) {
    while (true);
  }
  
  radio.setPALevel(RF24_PA_MAX);
  radio.setDataRate(RF24_250KBPS);
  radio.setChannel(108);
  radio.setAutoAck(true);
  radio.openReadingPipe(1, DIRECCION);
  radio.startListening();
  ultimaRecepcion = millis();
}

void loop() {
  if (radio.available()) {
    Paquete paquete;
    // Bucle para vaciar el búfer completamente y evitar congelamiento
    while (radio.available()) {
      radio.read(&paquete, sizeof(paquete));
    }
    ultimaRecepcion = millis();

    // Motor Izquierdo
    if (paquete.traccion_izq > 0) {
      analogWrite(pinA1B, 0); analogWrite(pinA1A, paquete.traccion_izq);
    } else if (paquete.traccion_izq < 0) {
      analogWrite(pinA1A, 0); analogWrite(pinA1B, abs(paquete.traccion_izq));
    } else {
      analogWrite(pinA1A, 0); analogWrite(pinA1B, 0);
    }

    // Motor Derecho
    if (paquete.traccion_der > 0) {
      analogWrite(pinB1B, 0); analogWrite(pinB1A, paquete.traccion_der);
    } else if (paquete.traccion_der < 0) {
      analogWrite(pinB1A, 0); analogWrite(pinB1B, abs(paquete.traccion_der));
    } else {
      analogWrite(pinB1A, 0); analogWrite(pinB1B, 0);
    }

    // Restricción de seguridad 10-170 para no forzar engranajes
    servo1.write(constrain(paquete.angulo_s1, 10, 170));
    servo2.write(constrain(paquete.angulo_s2, 10, 170));
  }

  if (millis() - ultimaRecepcion > TIMEOUT_MS) {
    pararMotores();
  }
}