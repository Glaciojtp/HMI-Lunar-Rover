/*
 * =====================================================================================
 *  RECEPTOR ARDUINO NANO ESP32 — ROVER LUNAR V2.0 (ELECTRÓNICA A BORDO)
 *  Soporte Completo Rocker-Bogie: 6 Motores Tracción + 4 Servos Dirección Independientes
 * =====================================================================================
 *  Hardware: Arduino Nano ESP32 (ESP32-S3 a 3.3V) + NRF24L01+ + Puente H L9110S + 4 Servos
 * 
 *  ASIGNACIÓN DE PINES:
 *    - NRF24L01 CE:   Pin D9  (GPIO 18)
 *    - NRF24L01 CSN:  Pin D10 (GPIO 21)
 *    - NRF24L01 MOSI: Pin D11 (GPIO 38 - SPI Hardware)
 *    - NRF24L01 MISO: Pin D12 (GPIO 47 - SPI Hardware)
 *    - NRF24L01 SCK:  Pin D13 (GPIO 48 - SPI Hardware)
 *    - NRF24L01 VCC:  Salida 3.3V regulada (Capacitor 10–100 µF obligatorio a GND)
 *
 *    - Puente H Izq:  Pin D2 (A1A - Avance), Pin D5 (A1B - Reversa) -> Tracción Izq (M1, M2, M3)
 *    - Puente H Der:  Pin D3 (B1A - Avance), Pin D4 (B1B - Reversa) -> Tracción Der (M4, M5, M6)
 *
 *    - Servo S1:      Pin D6  (Delantero Izquierdo)
 *    - Servo S2:      Pin D7  (Delantero Derecho)
 *    - Servo S3:      Pin D8  (Trasero Izquierdo)
 *    - Servo S4:      Pin A0  (Trasero Derecho)
 *
 *  PINES DISPONIBLES PARA EXPANSIÓN FUTURA:
 *    - D0 (RX) / D1 (TX): Puerto Serie UART auxiliar (módulo ESP32-CAM / GPS / Telemetría externa)
 *    - A1, A2, A3:        Entradas Analógicas libres (Lectura de batería LiPo con divisor resistivo)
 *    - A4 (SDA) / A5 (SCL): Bus I2C Hardware libre (IMU / Giroscopio MPU6050 para rampa 20°)
 *    - A6, A7, AREF:      Pines analógicos y referencias libres
 *
 *  REGLAS DE SEGURIDAD ELÉCTRICA:
 *    1. ¡NUNCA alimentar el NRF24L01 a 5V! Solo a 3.3V con capacitor electrolítico.
 *    2. Servos alimentados EXCLUSIVAMENTE mediante regulador Step-Down a 5V-6V (GND común).
 *    3. Límite de ángulo por software: [10°, 170°] para proteger piñonería de servos.
 * =====================================================================================
 */

#include <SPI.h>
#include <RF24.h>

#if defined(ARDUINO_ARCH_ESP32)
  #include <ESP32Servo.h>
#else
  #include <Servo.h>
#endif

// ==========================================
// CONFIGURACIÓN DE PINES
// ==========================================
#define PIN_RF_CE   9
#define PIN_RF_CSN 10

// Puente H L9110S (Control PWM de Tracción)
const int pinA1A = 2; // Izquierda Avance
const int pinA1B = 5; // Izquierda Reversa
const int pinB1A = 3; // Derecha Avance
const int pinB1B = 4; // Derecha Reversa

// Servomotores de Dirección (Rocker-Bogie 4WS)
const int pinServo1 = 6;  // S1: Delantero Izquierdo
const int pinServo2 = 7;  // S2: Delantero Derecho
const int pinServo3 = 8;  // S3: Trasero Izquierdo
const int pinServo4 = A0; // S4: Trasero Derecho

// ==========================================
// RADIOFRECUENCIA NRF24L01
// ==========================================
RF24 radio(PIN_RF_CE, PIN_RF_CSN);
const byte DIRECCION_RF[6] = "ROVER";

// Estructura estrictamente empaquetada (8 bytes) idéntica al Mando Joystick y PC HMI
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255 (Lado Izquierdo)
  int16_t traccion_der;  // -255 a 255 (Lado Derecho)
  uint8_t angulo_s1;     // S1: Delantero Izq [10°-170°]
  uint8_t angulo_s2;     // S2: Delantero Der [10°-170°]
  uint8_t angulo_s3;     // S3: Trasero Izq   [10°-170°]
  uint8_t angulo_s4;     // S4: Trasero Der   [10°-170°]
};

// Instancias de los 4 Servos
Servo servo1;
Servo servo2;
Servo servo3;
Servo servo4;

// ==========================================
// WATCHDOG FAILSAFE DE SEGURIDAD
// ==========================================
unsigned long ultimaRecepcion = 0;
const unsigned long TIMEOUT_MS = 1000; // 1 segundo sin señal = Parada total preventiva

// Parada inmediata de todos los motores
void pararMotores() {
  analogWrite(pinA1A, 0);
  analogWrite(pinA1B, 0);
  analogWrite(pinB1A, 0);
  analogWrite(pinB1B, 0);
}

// Aplicación de control de velocidad y sentido en el Puente H
void aplicarControlMotores(int16_t pwmIzq, int16_t pwmDer) {
  // --- Control Lado Izquierdo (M1, M2, M3) ---
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

  // --- Control Lado Derecho (M4, M5, M6) ---
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

  // Configuración de Servos (Asignación de temporizadores y pulso estándar 500-2500 µs)
  #if defined(ARDUINO_ARCH_ESP32)
    ESP32PWM::allocateTimer(0);
    ESP32PWM::allocateTimer(1);
    ESP32PWM::allocateTimer(2);
    ESP32PWM::allocateTimer(3);
    servo1.setPeriodHertz(50);
    servo2.setPeriodHertz(50);
    servo3.setPeriodHertz(50);
    servo4.setPeriodHertz(50);
  #endif

  servo1.attach(pinServo1);
  servo2.attach(pinServo2);
  servo3.attach(pinServo3);
  servo4.attach(pinServo4);

  // Centrar dirección a 90° (Línea recta) al iniciar
  servo1.write(90);
  servo2.write(90);
  servo3.write(90);
  servo4.write(90);

  // Configuración de pines de tracción
  pinMode(pinA1A, OUTPUT);
  pinMode(pinA1B, OUTPUT);
  pinMode(pinB1A, OUTPUT);
  pinMode(pinB1B, OUTPUT);
  pararMotores();

  // Inicialización de la Radio NRF24L01+
  if (!radio.begin()) {
    Serial.println(F("[ERROR] No se detecto el modulo NRF24L01 en Arduino Nano ESP32."));
    Serial.println(F("[CHECK] Verifica conexion SPI: D11(MOSI), D12(MISO), D13(SCK), D9(CE), D10(CSN), 3.3V y GND."));
    while (true) {
      delay(500);
    }
  }

  radio.setPayloadSize(sizeof(PaqueteControl)); // 8 bytes exactos
  radio.setPALevel(RF24_PA_MAX);               // Máxima potencia de recepción/emisión
  radio.setDataRate(RF24_250KBPS);             // 250 kbps (Máxima penetración y alcance)
  radio.setChannel(108);                       // Canal 108 (2.508 GHz, fuera del Wi-Fi doméstico)
  radio.setAutoAck(false);                     // Streaming continuo de alta velocidad
  radio.openReadingPipe(1, DIRECCION_RF);
  radio.startListening();

  ultimaRecepcion = millis();
  Serial.println(F("SYS:ARDUINO_NANO_ESP32_RECEPTOR_LISTO"));
}

void loop() {
  // Detección de tramas entrantes por Radiofrecuencia
  if (radio.available()) {
    PaqueteControl paquete;

    // Vaciado rápido del buffer FIFO para procesar siempre la trama más reciente
    while (radio.available()) {
      radio.read(&paquete, sizeof(paquete));
    }
    ultimaRecepcion = millis();

    // 1. Aplicar velocidad y dirección a los motores DC
    aplicarControlMotores(paquete.traccion_izq, paquete.traccion_der);

    // 2. Posicionar los 4 servomotores con restricción estricta de seguridad [10°, 170°]
    servo1.write(constrain(paquete.angulo_s1, 10, 170));
    servo2.write(constrain(paquete.angulo_s2, 10, 170));
    servo3.write(constrain(paquete.angulo_s3, 10, 170));
    servo4.write(constrain(paquete.angulo_s4, 10, 170));

    #if 0 // Cambiar a 1 para ver telemetría de depuración en consola Serial
      Serial.print("RX -> Izq: "); Serial.print(paquete.traccion_izq);
      Serial.print(" | Der: "); Serial.print(paquete.traccion_der);
      Serial.print(" | S1: "); Serial.print(paquete.angulo_s1);
      Serial.print(" | S2: "); Serial.print(paquete.angulo_s2);
      Serial.print(" | S3: "); Serial.print(paquete.angulo_s3);
      Serial.print(" | S4: "); Serial.println(paquete.angulo_s4);
    #endif
  }

  // Watchdog Failsafe: Si transcurre más de 1 segundo sin señal, frenar motores
  if (millis() - ultimaRecepcion > TIMEOUT_MS) {
    pararMotores();
  }
}
