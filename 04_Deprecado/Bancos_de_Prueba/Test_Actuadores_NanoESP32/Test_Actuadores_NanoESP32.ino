/*
 * =====================================================================================
 *  TEST DE ACTUADORES — ARDUINO NANO ESP32 (COM21)
 *  Rover Lunar V2.0 — Verificacion individual de Motores DC y Servomotores (Sin RF)
 * =====================================================================================
 *  Hardware: Arduino Nano ESP32 + Puente H L9110S + 4 Servomotores Rocker-Bogie
 *
 *  ASIGNACION DE PINES:
 *    - Puente H Izquierdo: Pin D2 (A1A - Avance), Pin D5 (A1B - Reversa)
 *    - Puente H Derecho:   Pin D3 (B1A - Avance), Pin D4 (B1B - Reversa)
 *    - Servo S1 (Delantero Izquierdo): Pin D6
 *    - Servo S2 (Delantero Derecho):   Pin D7
 *    - Servo S3 (Trasero Izquierdo):    Pin D8
 *    - Servo S4 (Trasero Derecho):      Pin A0
 *
 *  REGLAS DE SEGURIDAD:
 *    - Rango angular seguro de servos: [10°, 170°] (prohibido forzar topes mecanicos).
 *    - Servos alimentados EXCLUSIVAMENTE mediante Step-Down a 5V-6V con GND comun.
 * =====================================================================================
 */

#include <Arduino.h>

// ==========================================
// CONTROLADOR DE SERVOMOTORES INTEGRADO (STANDARD ARDUINO SERVO API)
// Implementa la interfaz estandar de Servo de Arduino (attach, write, read, etc.)
// utilizando los temporizadores de hardware LEDC nativos del ESP32-S3 a 50 Hz.
// Evita colisiones con librerias externas no estandar (ESP32_ESP32S2_AnalogWrite).
// ==========================================
class Servo {
private:
  int _pin;
  int _canal;
  int _minUs;
  int _maxUs;
  int _angulo;
  bool _attached;
  static uint8_t _proximoCanal;

public:
  Servo() : _pin(-1), _canal(-1), _minUs(500), _maxUs(2500), _angulo(90), _attached(false) {}

  uint8_t attach(int pin, int minUs = 500, int maxUs = 2500) {
    if (_canal < 0) {
      if (_proximoCanal >= 4) return 0; // Canales 0 a 3 reservados para Servos (50 Hz, 14 bits)
      _canal = _proximoCanal++;
    }
    _pin = pin;
    _minUs = minUs;
    _maxUs = maxUs;

    // Hardware ESP32-S3 LEDC: 50 Hz (periodo 20000 us), resolucion maxima de 14 bits (0 a 16383)
    ledcSetup(_canal, 50, 14);
    ledcAttachPin(_pin, _canal);
    _attached = true;
    write(90); // Posicion inicial centrada segura
    return _canal + 1;
  }

  void detach() {
    if (_attached && _canal >= 0) {
      ledcDetachPin(_pin);
      _attached = false;
    }
  }

  void writeMicroseconds(int us) {
    if (!_attached) return;
    us = constrain(us, _minUs, _maxUs);
    // Periodo 20000 us a 14 bits (16383): duty = (us * 16383UL) / 20000UL
    uint32_t duty = ((uint32_t)us * 16383UL) / 20000UL;
    ledcWrite(_canal, duty);
  }

  void write(int angulo) {
    if (!_attached) return;
    angulo = constrain(angulo, 10, 170); // Limite mecanico estricto de seguridad
    _angulo = angulo;
    int us = map(angulo, 0, 180, _minUs, _maxUs);
    writeMicroseconds(us);
  }

  int read() const {
    return _angulo;
  }

  int readMicroseconds() const {
    return map(_angulo, 0, 180, _minUs, _maxUs);
  }

  bool attached() const {
    return _attached;
  }
};

uint8_t Servo::_proximoCanal = 0;

// Pines de Traccion (Puente H L9110S)
const int pinA1A = D2;
const int pinA1B = D5;
const int pinB1A = D3;
const int pinB1B = D4;

// Pines de Servomotores (Direccion Rocker-Bogie 4WS)
const int pinServo1 = D6;
const int pinServo2 = D7;
const int pinServo3 = D8;
const int pinServo4 = A0;

Servo servo1;
Servo servo2;
Servo servo3;
Servo servo4;

void pararMotores() {
  analogWrite(pinA1A, 0);
  analogWrite(pinA1B, 0);
  analogWrite(pinB1A, 0);
  analogWrite(pinB1B, 0);
}

void moverTraccion(int pwmIzq, int pwmDer) {
  // Motor Izquierdo
  if (pwmIzq > 0) {
    analogWrite(pinA1A, constrain(pwmIzq, 0, 255));
    analogWrite(pinA1B, 0);
  } else if (pwmIzq < 0) {
    analogWrite(pinA1A, 0);
    analogWrite(pinA1B, constrain(abs(pwmIzq), 0, 255));
  } else {
    analogWrite(pinA1A, 0);
    analogWrite(pinA1B, 0);
  }

  // Motor Derecho
  if (pwmDer > 0) {
    analogWrite(pinB1A, constrain(pwmDer, 0, 255));
    analogWrite(pinB1B, 0);
  } else if (pwmDer < 0) {
    analogWrite(pinB1A, 0);
    analogWrite(pinB1B, constrain(abs(pwmDer), 0, 255));
  } else {
    analogWrite(pinB1A, 0);
    analogWrite(pinB1B, 0);
  }
}

void centrarServos() {
  servo1.write(90);
  servo2.write(90);
  servo3.write(90);
  servo4.write(90);
}

void posicionarServos(int s1, int s2, int s3, int s4) {
  servo1.write(constrain(s1, 10, 170));
  servo2.write(constrain(s2, 10, 170));
  servo3.write(constrain(s3, 10, 170));
  servo4.write(constrain(s4, 10, 170));
}

void imprimirMenu() {
  Serial.println();
  Serial.println("=======================================================");
  Serial.println("   TEST DE ACTUADORES - ARDUINO NANO ESP32 (COM21)");
  Serial.println("=======================================================");
  Serial.println("Comandos por teclado en Monitor Serie (115200 baudios):");
  Serial.println("   '1' -> Test Motores AVANCE (ambos al 60% por 2 seg)");
  Serial.println("   '2' -> Test Motores REVERSA (ambos al 60% por 2 seg)");
  Serial.println("   '3' -> Test Motor IZQUIERDO solo (Avance 2s -> Reversa 2s)");
  Serial.println("   '4' -> Test Motor DERECHO solo (Avance 2s -> Reversa 2s)");
  Serial.println("   '5' -> Test Servos BARRIDO (90 -> 45 -> 135 -> 90)");
  Serial.println("   '6' -> Test Servos INDIVIDUALES (S1 -> S2 -> S3 -> S4)");
  Serial.println("   '7' -> Secuencia AUTOMATICA completa");
  Serial.println("   'x' -> PARADA DE EMERGENCIA INMEDIATA");
  Serial.println("   '?' -> Reimprimir este menu");
  Serial.println("=======================================================");
  Serial.println();
}

void testMotoresAvance() {
  Serial.println("[TEST 1] Motores en AVANCE al 60% (PWM 150) por 2 segundos...");
  moverTraccion(150, 150);
  delay(2000);
  pararMotores();
  Serial.println("[TEST 1] Completado. Motores detenidos.");
}

void testMotoresReversa() {
  Serial.println("[TEST 2] Motores en REVERSA al 60% (PWM -150) por 2 segundos...");
  moverTraccion(-150, -150);
  delay(2000);
  pararMotores();
  Serial.println("[TEST 2] Completado. Motores detenidos.");
}

void testMotorIzquierdo() {
  Serial.println("[TEST 3] Motor IZQUIERDO solo: Avance 2s...");
  moverTraccion(150, 0);
  delay(2000);
  pararMotores();
  delay(500);
  Serial.println("[TEST 3] Motor IZQUIERDO solo: Reversa 2s...");
  moverTraccion(-150, 0);
  delay(2000);
  pararMotores();
  Serial.println("[TEST 3] Completado.");
}

void testMotorDerecho() {
  Serial.println("[TEST 4] Motor DERECHO solo: Avance 2s...");
  moverTraccion(0, 150);
  delay(2000);
  pararMotores();
  delay(500);
  Serial.println("[TEST 4] Motor DERECHO solo: Reversa 2s...");
  moverTraccion(0, -150);
  delay(2000);
  pararMotores();
  Serial.println("[TEST 4] Completado.");
}

void testServosBarrido() {
  Serial.println("[TEST 5] Servos en BARRIDO conjunto...");
  Serial.println("   -> Centro (90 grados)");
  posicionarServos(90, 90, 90, 90);
  delay(1000);

  Serial.println("   -> Izquierda (45 grados)");
  posicionarServos(45, 45, 45, 45);
  delay(1200);

  Serial.println("   -> Derecha (135 grados)");
  posicionarServos(135, 135, 135, 135);
  delay(1200);

  Serial.println("   -> Retorno a Centro (90 grados)");
  posicionarServos(90, 90, 90, 90);
  delay(800);
  Serial.println("[TEST 5] Completado.");
}

void testServosIndividuales() {
  Serial.println("[TEST 6] Prueba individual de cada servomotor...");

  // S1: Delantero Izquierdo
  Serial.println("   -> Servo 1 (Delantero Izquierdo, Pin D6): 60 grados");
  servo1.write(60);
  delay(1000);
  Serial.println("   -> Servo 1: 120 grados");
  servo1.write(120);
  delay(1000);
  servo1.write(90);
  delay(500);

  // S2: Delantero Derecho
  Serial.println("   -> Servo 2 (Delantero Derecho, Pin D7): 60 grados");
  servo2.write(60);
  delay(1000);
  Serial.println("   -> Servo 2: 120 grados");
  servo2.write(120);
  delay(1000);
  servo2.write(90);
  delay(500);

  // S3: Trasero Izquierdo
  Serial.println("   -> Servo 3 (Trasero Izquierdo, Pin D8): 60 grados");
  servo3.write(60);
  delay(1000);
  Serial.println("   -> Servo 3: 120 grados");
  servo3.write(120);
  delay(1000);
  servo3.write(90);
  delay(500);

  // S4: Trasero Derecho
  Serial.println("   -> Servo 4 (Trasero Derecho, Pin A0): 60 grados");
  servo4.write(60);
  delay(1000);
  Serial.println("   -> Servo 4: 120 grados");
  servo4.write(120);
  delay(1000);
  servo4.write(90);
  delay(500);

  Serial.println("[TEST 6] Completado. Todos los servos centrados a 90 grados.");
}

void testSecuenciaCompleta() {
  Serial.println("[TEST 7] Ejecutando secuencia automatica completa...");
  testMotoresAvance();
  delay(1000);
  testMotoresReversa();
  delay(1000);
  testServosBarrido();
  delay(1000);
  testServosIndividuales();
  Serial.println("[TEST 7] Secuencia completada exitosamente.");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  // Configuracion de pines de traccion
  pinMode(pinA1A, OUTPUT);
  pinMode(pinA1B, OUTPUT);
  pinMode(pinB1A, OUTPUT);
  pinMode(pinB1B, OUTPUT);
  pararMotores();

  // Inicializacion de los 4 Servomotores estandar de Arduino
  servo1.attach(pinServo1);
  servo2.attach(pinServo2);
  servo3.attach(pinServo3);
  servo4.attach(pinServo4);

  centrarServos();

  imprimirMenu();
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n' || c == ' ') return;

    switch (c) {
      case '1':
        testMotoresAvance();
        break;
      case '2':
        testMotoresReversa();
        break;
      case '3':
        testMotorIzquierdo();
        break;
      case '4':
        testMotorDerecho();
        break;
      case '5':
        testServosBarrido();
        break;
      case '6':
        testServosIndividuales();
        break;
      case '7':
        testSecuenciaCompleta();
        break;
      case 'x':
      case 'X':
        pararMotores();
        centrarServos();
        Serial.println("[PARADA] Motores detenidos y servos centrados a 90 grados.");
        break;
      case '?':
      case 'h':
      case 'H':
        imprimirMenu();
        break;
      default:
        Serial.print("[INFO] Comando no reconocido: '");
        Serial.print(c);
        Serial.println("'. Escriba '?' para ver el menu.");
        break;
    }
  }
}
