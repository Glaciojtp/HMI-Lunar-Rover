/*
 * =====================================================================================
 *  RECEPTOR ARDUINO MKR 1310 — ROVER LUNAR V2.0 (ELECTRÓNICA A BORDO)
 *  Soporte Completo Rocker-Bogie: 6 Motores + 4 Servos Independientes
 * =====================================================================================
 *  Hardware: Arduino MKR 1310 + NRF24L01+ + Puente H L9110S + 4 Servomotores
 *  Asignación de Pines:
 *    - NRF24L01 CE:   Pin Digital 0
 *    - NRF24L01 CSN:  Pin Digital 1
 *    - NRF24L01 MOSI: Pin Digital 8 (SPI Hardware)
 *    - NRF24L01 SCK:  Pin Digital 9 (SPI Hardware)
 *    - NRF24L01 MISO: Pin Digital 10 (SPI Hardware)
 *    - Puente H Izq:  Pin 2 (A1A - Avance), Pin 5 (A1B - Reversa) -> M1, M2, M3
 *    - Puente H Der:  Pin 3 (B1A - Avance), Pin 4 (B1B - Reversa) -> M4, M5, M6
 *    - Servo S1:      Pin Digital 6 (Delantero Izquierdo)
 *    - Servo S2:      Pin Digital 7 (Delantero Derecho)
 *    - Servo S3:      Pin A1 / Pin 16 (Trasero Izquierdo)
 *    - Servo S4:      Pin A2 / Pin 17 (Trasero Derecho)
 * =====================================================================================
 */

#include <SPI.h>
#include <RF24.h>
#include <Servo.h>

#define PIN_CE  0
#define PIN_CSN 1

RF24 radio(PIN_CE, PIN_CSN);
const byte DIRECCION_RF[6] = "ROVER";

// Estructura estrictamente empaquetada (8 bytes) idéntica al ESP32
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255 (Lado Izquierdo)
  int16_t traccion_der;  // -255 a 255 (Lado Derecho)
  uint8_t angulo_s1;     // S1: Delantero Izq
  uint8_t angulo_s2;     // S2: Delantero Der
  uint8_t angulo_s3;     // S3: Trasero Izq
  uint8_t angulo_s4;     // S4: Trasero Der
};

// Instancias de los 4 Servos de Dirección
Servo servo1; // Delantero Izquierdo
Servo servo2; // Delantero Derecho
Servo servo3; // Trasero Izquierdo
Servo servo4; // Trasero Derecho

const int pinServo1 = 6;
const int pinServo2 = 7;
const int pinServo3 = A1; // Pin analógico A1 usado como salida digital PWM
const int pinServo4 = A2; // Pin analógico A2 usado como salida digital PWM

// Pines del Puente H L9110S
const int pinA1A = 2; // Izquierda Avance
const int pinA1B = 5; // Izquierda Reversa
const int pinB1A = 3; // Derecha Avance
const int pinB1B = 4; // Derecha Reversa

// Temporizador Failsafe
unsigned long ultimaRecepcion = 0;
const unsigned long TIMEOUT_MS = 1000;

void pararMotores() {
  analogWrite(pinA1A, 0);
  analogWrite(pinA1B, 0);
  analogWrite(pinB1A, 0);
  analogWrite(pinB1B, 0);
}

void aplicarControlMotores(int16_t pwmIzq, int16_t pwmDer) {
  // Lado Izquierdo (M1, M2, M3)
  if (pwmIzq > 0) {
    analogWrite(pinA1B, 0);
    analogWrite(pinA1A, constrain(pwmIzq, 0, 255));
  } else if (pwmIzq < 0) {
    analogWrite(pinA1A, 0);
    analogWrite(pinA1B, constrain(abs(pwmIzq), 0, 255));
  } else {
    analogWrite(pinA1A, 0);
    analogWrite(pinA1B, 0);
  }

  // Lado Derecho (M4, M5, M6)
  if (pwmDer > 0) {
    analogWrite(pinB1B, 0);
    analogWrite(pinB1A, constrain(pwmDer, 0, 255));
  } else if (pwmDer < 0) {
    analogWrite(pinB1A, 0);
    analogWrite(pinB1B, constrain(abs(pwmDer), 0, 255));
  } else {
    analogWrite(pinB1A, 0);
    analogWrite(pinB1B, 0);
  }
}

void setup() {
  Serial.begin(115200);

  // Inicializar los 4 servomotores centrados a 90°
  servo1.attach(pinServo1);
  servo2.attach(pinServo2);
  servo3.attach(pinServo3);
  servo4.attach(pinServo4);

  servo1.write(90);
  servo2.write(90);
  servo3.write(90);
  servo4.write(90);

  // Configurar pines de tracción
  pinMode(pinA1A, OUTPUT);
  pinMode(pinA1B, OUTPUT);
  pinMode(pinB1A, OUTPUT);
  pinMode(pinB1B, OUTPUT);
  pararMotores();

  // Inicialización de la Radio NRF24L01
  if (!radio.begin()) {
    Serial.println("ERROR: No se detectó NRF24L01 en Arduino MKR.");
    while (true) { delay(500); }
  }

  radio.setPayloadSize(sizeof(PaqueteControl)); // 8 bytes exactos
  radio.setPALevel(RF24_PA_MAX);
  radio.setDataRate(RF24_250KBPS);
  radio.setChannel(108);
  radio.setAutoAck(false); // Modo streaming continuo (sin ACK)
  radio.openReadingPipe(1, DIRECCION_RF);
  radio.startListening();

  ultimaRecepcion = millis();
  Serial.println("SYS:MKR_RECEPTOR_4SERVOS_LISTO");
}

void loop() {
  if (radio.available()) {
    PaqueteControl paquete;

    // Vaciado rápido de buffer FIFO
    while (radio.available()) {
      radio.read(&paquete, sizeof(paquete));
    }
    ultimaRecepcion = millis();

    // Aplicar tracción
    aplicarControlMotores(paquete.traccion_izq, paquete.traccion_der);

    // Mover independientemente los 4 servos con restricción de seguridad (10°-170°)
    servo1.write(constrain(paquete.angulo_s1, 10, 170));
    servo2.write(constrain(paquete.angulo_s2, 10, 170));
    servo3.write(constrain(paquete.angulo_s3, 10, 170));
    servo4.write(constrain(paquete.angulo_s4, 10, 170));
  }

  // Failsafe Watchdog: frenar si no hay señal en 1 segundo
  if (millis() - ultimaRecepcion > TIMEOUT_MS) {
    pararMotores();
  }
}
