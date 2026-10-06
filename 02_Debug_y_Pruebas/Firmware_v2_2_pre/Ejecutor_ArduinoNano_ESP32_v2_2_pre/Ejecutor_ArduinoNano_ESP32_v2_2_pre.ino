/*
 * =====================================================================================
 *  RECEPTOR ARDUINO NANO ESP32 — ROVER LUNAR V2.2-PRE (ELECTRONICA A BORDO)
 *  Soporte Completo Rocker-Bogie: 6 Motores Traccion + 4 Servos 360 con Calibracion NVS
 * =====================================================================================
 *  Hardware: Arduino Nano ESP32 (ESP32-S3 a 3.3V) + Puente H L9110S + 4 Servomotores 360
 *  Comunicaciones soportadas:
 *    - Wi-Fi Nativo (SoftAP + UDP) [MODO ACTIVO DE LABORATORIO]
 *    - NRF24L01+ (Radiofrecuencia 2.4 GHz SPI) [Modo alternativo]
 *
 *  CARACTERISTICAS EXPERIMENTALES V2.2-PRE:
 *    - Calibracion en tiempo real de neutro para servos de rotacion continua MG90S 360.
 *    - Almacenamiento no volatil en memoria Flash NVS (<Preferences.h>).
 *    - Maquina de estados de pulsos temporizados para viraje no continuo simetrico.
 *    - Ajuste de direccion individual (dirS1..dirS4) e inversion global.
 * =====================================================================================
 */

#include <Arduino.h>
#include <Preferences.h>
#include "PaqueteControl.h"

// ==========================================
// SELECCION DE MODO DE COMUNICACION
// 1 = Wi-Fi Nativo SoftAP + UDP [MODO ACTIVO DE LABORATORIO]
// 0 = Radiofrecuencia NRF24L01+ externa
// ==========================================
#define MODO_CONEXION_WIFI 1

#if MODO_CONEXION_WIFI
  #include <WiFi.h>
  #include <WiFiUdp.h>
  const char* AP_SSID = "ROVER_NET";
  const char* AP_PASS = "rover1234";
  const unsigned int PUERTO_UDP = 4210;
  WiFiUDP udp;
#else
  #include <SPI.h>
  #include <RF24.h>
  #define PIN_RF_CE   D9
  #define PIN_RF_CSN  D10
  RF24 radio(PIN_RF_CE, PIN_RF_CSN);
  const byte DIRECCION_RF[6] = "ROVER";
  bool radioInicializada = false;
#endif

// Prototipos explicitos de funciones
void procesarControl(int16_t traccionIzq, int16_t traccionDer, uint8_t s1, uint8_t s2, uint8_t s3, uint8_t s4);
void procesarPaquete(const PaqueteControl& paquete);
void pararMotores();
void aplicarControlMotores(int16_t pwmIzq, int16_t pwmDer);
void frenarServosNeutro();
void actualizarPulsosDireccion360();
void aplicarDireccion360(uint8_t s1, uint8_t s2, uint8_t s3, uint8_t s4);
void cargarCalibracionNVS();
void guardarCalibracionNVS();
void procesarComandoSerial(const String& cmd);
void procesarTramaCsv(const String& trama);

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

// ==========================================
// CONFIGURACION DE PINES DE ACTUADORES
// ==========================================
// Puente H L9110S (Control PWM de Traccion)
const int pinA1A = D2; // Izquierda Avance (GPIO 4)
const int pinA1B = D5; // Izquierda Reversa (GPIO 7)
const int pinB1A = D3; // Derecha Avance   (GPIO 5)
const int pinB1B = D4; // Derecha Reversa  (GPIO 6)

// Canales Hardware LEDC dedicados para Traccion (ESP32-S3)
// Canales 0-3 reservados para Servos. Canales 4-7 asignados a traccion (1000 Hz, 8 bits: 0-255).
const int CH_MOT_A1A = 4;
const int CH_MOT_A1B = 5;
const int CH_MOT_B1A = 6;
const int CH_MOT_B1B = 7;

inline void setPwmA1A(int duty) { ledcWrite(CH_MOT_A1A, constrain(duty, 0, 255)); }
inline void setPwmA1B(int duty) { ledcWrite(CH_MOT_A1B, constrain(duty, 0, 255)); }
inline void setPwmB1A(int duty) { ledcWrite(CH_MOT_B1A, constrain(duty, 0, 255)); }
inline void setPwmB1B(int duty) { ledcWrite(CH_MOT_B1B, constrain(duty, 0, 255)); }

// Servomotores de Direccion (Rocker-Bogie 4WS)
const int pinServo1 = D6; // S1: Delantero Izquierdo
const int pinServo2 = D7; // S2: Delantero Derecho
const int pinServo3 = D8; // S3: Trasero Izquierdo
const int pinServo4 = A0; // S4: Trasero Derecho


// Instancias de los 4 Servos
Servo servo1;
Servo servo2;
Servo servo3;
Servo servo4;

// Estado de seguridad de actuadores
bool motoresHabilitados = true;
bool invertirDirIzq = true;    // Por defecto TRUE: invierte PWM lado izquierdo para sentido de marcha correcto
bool invertirDirDer = false;   // Por defecto FALSE: lado derecho estandar
bool invertirLogicaPwm = false;// Por defecto FALSE: logica estandar directa (0 = STOP, PWM = marcha)

// ==========================================
// CONFIGURACION Y CALIBRACION DE SERVOS (MODO DUAL 180 / 360)
// ==========================================
Preferences nvsPrefs;

// Modo de operacion de los servomotores:
// false = Servos de rotacion continua 360 (pulsos temporizados y freno a neutro en microsegundos)
// true  = Servos posicionales estandar 180 (angulo directo [10, 170] grados via write)
bool modoServos180 = false;

// Microsegundos de neutro exacto (STOP absoluto) para cada servo (calibrables en modo 360)
int neutroS1 = 1500;
int neutroS2 = 1500;
int neutroS3 = 1500;
int neutroS4 = 1500;

// Sentido individual de rotacion para cada servo (+1 o -1 segun orientacion mecanica)
int dirS1 = 1;
int dirS2 = 1;
int dirS3 = -1; // Ruedas traseras rotan opuestas en 4WS
int dirS4 = -1;

// Offset de velocidad en microsegundos durante el giro temporizado
int deltaVelGiro = 90;

// Duracion del pulso temporizado en ms para alcanzar el angulo de giro (ej. ~30 deg)
unsigned long duracionGiroMs = 140;

// Inversion global de sentido del tren de direccion
bool invertirSentidoServos = false;

// Maquina de estados de direccion por pulsos temporizados
enum EstadoDireccion {
  DIR_CENTRO,  // Ruedas orientadas al frente
  DIR_IZQ,     // Ruedas viradas a la izquierda
  DIR_DER      // Ruedas viradas a la derecha
};

EstadoDireccion estadoDirActual = DIR_CENTRO;
EstadoDireccion estadoDirObjetivo = DIR_CENTRO;

bool pulsoGiroEnProgreso = false;
unsigned long tiempoInicioPulsoGiro = 0;
unsigned long tiempoDuracionPulsoActual = 0;

void frenarServosNeutro() {
  if (modoServos180) {
    servo1.write(90);
    servo2.write(90);
    servo3.write(90);
    servo4.write(90);
  } else {
    servo1.writeMicroseconds(neutroS1);
    servo2.writeMicroseconds(neutroS2);
    servo3.writeMicroseconds(neutroS3);
    servo4.writeMicroseconds(neutroS4);
  }
  pulsoGiroEnProgreso = false;
}

void cargarCalibracionNVS() {
  nvsPrefs.begin("rover_calib", true);
  modoServos180 = nvsPrefs.getBool("m180", false);
  neutroS1 = nvsPrefs.getInt("s1", 1500);
  neutroS2 = nvsPrefs.getInt("s2", 1500);
  neutroS3 = nvsPrefs.getInt("s3", 1500);
  neutroS4 = nvsPrefs.getInt("s4", 1500);
  duracionGiroMs = nvsPrefs.getULong("dur", 140);
  deltaVelGiro = nvsPrefs.getInt("vel", 90);
  dirS1 = nvsPrefs.getInt("ds1", 1);
  dirS2 = nvsPrefs.getInt("ds2", 1);
  dirS3 = nvsPrefs.getInt("ds3", -1);
  dirS4 = nvsPrefs.getInt("ds4", -1);
  invertirSentidoServos = nvsPrefs.getBool("inv", false);
  nvsPrefs.end();

  Serial.println(F("[NVS] Calibracion de Servos cargada desde Flash:"));
  Serial.print(F("      Modo Servos: ")); Serial.println(modoServos180 ? F("180 POSICIONAL") : F("360 CONTINUO"));
  Serial.print(F("      S1: ")); Serial.print(neutroS1); Serial.print(F(" us (dir=")); Serial.print(dirS1);
  Serial.print(F(") | S2: ")); Serial.print(neutroS2); Serial.print(F(" us (dir=")); Serial.print(dirS2);
  Serial.print(F(") | S3: ")); Serial.print(neutroS3); Serial.print(F(" us (dir=")); Serial.print(dirS3);
  Serial.print(F(") | S4: ")); Serial.print(neutroS4); Serial.print(F(" us (dir=")); Serial.print(dirS4);
  Serial.print(F(") | Duracion: ")); Serial.print(duracionGiroMs);
  Serial.print(F(" ms | VelOffset: ")); Serial.print(deltaVelGiro);
  Serial.print(F(" us | InvertirGlobal: ")); Serial.println(invertirSentidoServos ? F("SI") : F("NO"));
}

void guardarCalibracionNVS() {
  nvsPrefs.begin("rover_calib", false);
  nvsPrefs.putBool("m180", modoServos180);
  nvsPrefs.putInt("s1", neutroS1);
  nvsPrefs.putInt("s2", neutroS2);
  nvsPrefs.putInt("s3", neutroS3);
  nvsPrefs.putInt("s4", neutroS4);
  nvsPrefs.putULong("dur", duracionGiroMs);
  nvsPrefs.putInt("vel", deltaVelGiro);
  nvsPrefs.putInt("ds1", dirS1);
  nvsPrefs.putInt("ds2", dirS2);
  nvsPrefs.putInt("ds3", dirS3);
  nvsPrefs.putInt("ds4", dirS4);
  nvsPrefs.putBool("inv", invertirSentidoServos);
  nvsPrefs.end();

  Serial.println(F("[NVS] Calibracion guardada exitosamente en memoria Flash."));
}

void ejecutarPulsoGiro(int sentido, unsigned long duracion) {
  // sentido: -1 = hacia izquierda, +1 = hacia derecha
  int modS1 = sentido * dirS1 * deltaVelGiro;
  int modS2 = sentido * dirS2 * deltaVelGiro;
  int modS3 = sentido * dirS3 * deltaVelGiro;
  int modS4 = sentido * dirS4 * deltaVelGiro;

  if (invertirSentidoServos) {
    modS1 = -modS1;
    modS2 = -modS2;
    modS3 = -modS3;
    modS4 = -modS4;
  }

  servo1.writeMicroseconds(neutroS1 + modS1);
  servo2.writeMicroseconds(neutroS2 + modS2);
  servo3.writeMicroseconds(neutroS3 + modS3);
  servo4.writeMicroseconds(neutroS4 + modS4);

  pulsoGiroEnProgreso = true;
  tiempoInicioPulsoGiro = millis();
  tiempoDuracionPulsoActual = duracion;
}

void actualizarPulsosDireccion360() {
  if (!pulsoGiroEnProgreso) return;

  if (millis() - tiempoInicioPulsoGiro >= tiempoDuracionPulsoActual) {
    frenarServosNeutro();
    estadoDirActual = estadoDirObjetivo;
  }
}

void aplicarDireccion360(uint8_t s1, uint8_t s2, uint8_t s3, uint8_t s4) {
  // En modo WASD/Ackermann:
  // s1 > 100 indica giro a la izquierda (A = 120)
  // s1 < 80  indica giro a la derecha (D = 60)
  // s1 entre 80 y 100 indica posicion recta / neutro (W, S o reposo = 90)
  EstadoDireccion objetivo = DIR_CENTRO;
  if (s1 > 100) {
    objetivo = DIR_IZQ;
  } else if (s1 < 80) {
    objetivo = DIR_DER;
  } else {
    objetivo = DIR_CENTRO;
  }

  if (objetivo == estadoDirActual && !pulsoGiroEnProgreso) {
    frenarServosNeutro();
    return;
  }

  if (pulsoGiroEnProgreso) return; // Esperar a que concluya el pulso activo

  estadoDirObjetivo = objetivo;

  if (estadoDirActual == DIR_CENTRO && objetivo == DIR_IZQ) {
    ejecutarPulsoGiro(-1, duracionGiroMs);
  } else if (estadoDirActual == DIR_IZQ && objetivo == DIR_CENTRO) {
    ejecutarPulsoGiro(+1, duracionGiroMs);
  } else if (estadoDirActual == DIR_CENTRO && objetivo == DIR_DER) {
    ejecutarPulsoGiro(+1, duracionGiroMs);
  } else if (estadoDirActual == DIR_DER && objetivo == DIR_CENTRO) {
    ejecutarPulsoGiro(-1, duracionGiroMs);
  } else if (estadoDirActual == DIR_IZQ && objetivo == DIR_DER) {
    ejecutarPulsoGiro(+1, 2 * duracionGiroMs);
  } else if (estadoDirActual == DIR_DER && objetivo == DIR_IZQ) {
    ejecutarPulsoGiro(-1, 2 * duracionGiroMs);
  }
}

unsigned long ultimaRecepcion = 0;
unsigned long ultimoAvisoFailsafe = 0;
const unsigned long TIMEOUT_MS = 1000; // 1 segundo sin senal = Parada total

// Parada inmediata de todos los motores
void pararMotores() {
  if (invertirLogicaPwm) {
    // Logica activa en bajo: 255 (HIGH / 3.3V) apaga la conduccion del puente H
    setPwmA1A(255);
    setPwmA1B(255);
    setPwmB1A(255);
    setPwmB1B(255);
  } else {
    // Logica directa estandar: 0 (LOW / 0V) apaga la conduccion del puente H
    setPwmA1A(0);
    setPwmA1B(0);
    setPwmB1A(0);
    setPwmB1B(0);
  }
}

// Aplicacion de control de velocidad y sentido en el Puente H
void aplicarControlMotores(int16_t pwmIzq, int16_t pwmDer) {
  if (!motoresHabilitados) {
    pararMotores();
    return;
  }

  if (invertirDirIzq) pwmIzq = -pwmIzq;
  if (invertirDirDer) pwmDer = -pwmDer;

  int valIzq = constrain(abs(pwmIzq), 0, 255);
  int valDer = constrain(abs(pwmDer), 0, 255);

  if (!invertirLogicaPwm) {
    // Modo directo (0 = apagado / 0V, 255 = 100% potencia / 3.3V)
    // --- Control Lado Izquierdo (M1, M2, M3) ---
    if (pwmIzq > 0) {
      setPwmA1B(0);
      setPwmA1A(valIzq);
    } else if (pwmIzq < 0) {
      setPwmA1A(0);
      setPwmA1B(valIzq);
    } else {
      setPwmA1A(0);
      setPwmA1B(0);
    }

    // --- Control Lado Derecho (M4, M5, M6) ---
    if (pwmDer > 0) {
      setPwmB1B(0);
      setPwmB1A(valDer);
    } else if (pwmDer < 0) {
      setPwmB1A(0);
      setPwmB1B(valDer);
    } else {
      setPwmB1A(0);
      setPwmB1B(0);
    }
  } else {
    // Modo invertido (255 = apagado / 3.3V, 0 = 100% potencia / 0V)
    // Previene que los motores giren sin control en reposo (STOP)
    if (pwmIzq > 0) {
      setPwmA1B(255);
      setPwmA1A(255 - valIzq);
    } else if (pwmIzq < 0) {
      setPwmA1A(255);
      setPwmA1B(255 - valIzq);
    } else {
      setPwmA1A(255);
      setPwmA1B(255);
    }

    if (pwmDer > 0) {
      setPwmB1B(255);
      setPwmB1A(255 - valDer);
    } else if (pwmDer < 0) {
      setPwmB1A(255);
      setPwmB1B(255 - valDer);
    } else {
      setPwmB1A(255);
      setPwmB1B(255);
    }
  }
}

void procesarControl(int16_t traccionIzq, int16_t traccionDer, uint8_t s1, uint8_t s2, uint8_t s3, uint8_t s4) {
  unsigned long ahora = millis();
  unsigned long dt = (ultimaRecepcion > 0) ? (ahora - ultimaRecepcion) : 0;
  ultimaRecepcion = ahora;

  // 1. Aplicar traccion y direccion segun el modo de servomotores configurado
  aplicarControlMotores(traccionIzq, traccionDer);
  if (modoServos180) {
    servo1.write(constrain(s1, 10, 170));
    servo2.write(constrain(s2, 10, 170));
    servo3.write(constrain(s3, 10, 170));
    servo4.write(constrain(s4, 10, 170));
  } else {
    aplicarDireccion360(s1, s2, s3, s4);
  }

  // 2. Telemetria estructurada hacia el puerto USB Serie (para HMI Debug en COM21)
  Serial.print(F("TLM:"));
  Serial.print(motoresHabilitados ? traccionIzq : 0); Serial.print(F(","));
  Serial.print(motoresHabilitados ? traccionDer : 0); Serial.print(F(","));
  Serial.print(s1); Serial.print(F(","));
  Serial.print(s2); Serial.print(F(","));
  Serial.print(s3); Serial.print(F(","));
  Serial.print(s4); Serial.print(F(","));
  Serial.print(dt); Serial.print(F(","));
  Serial.println(0);

  // 3. Log legible en consola de depuracion (solo si cambiaron los valores para evitar saturar el puerto)
  static int16_t prevIzq = -999, prevDer = -999;
  static uint8_t prevS1 = 0, prevS2 = 0, prevS3 = 0, prevS4 = 0;
  if (traccionIzq != prevIzq || traccionDer != prevDer ||
      s1 != prevS1 || s2 != prevS2 || s3 != prevS3 || s4 != prevS4) {
    prevIzq = traccionIzq; prevDer = traccionDer;
    prevS1 = s1; prevS2 = s2; prevS3 = s3; prevS4 = s4;

    Serial.print(F("[RX] Trac:["));
    Serial.print(traccionIzq); Serial.print(F(","));
    Serial.print(traccionDer); Serial.print(F("] | S:["));
    Serial.print(s1); Serial.print(F(","));
    Serial.print(s2); Serial.print(F(","));
    Serial.print(s3); Serial.print(F(","));
    Serial.print(s4); Serial.println(F("]"));
  }
}

void procesarPaquete(const PaqueteControl& paquete) {
  procesarControl(paquete.traccion_izq, paquete.traccion_der,
                  paquete.angulo_s1, paquete.angulo_s2, paquete.angulo_s3, paquete.angulo_s4);
}

void procesarComandoSerial(const String& cmd) {
  ultimaRecepcion = millis(); // Mantener vivo el watchdog ante comandos manuales e interactivos

  if (cmd == "IDENT") {
    Serial.println(F("ID:NANO_ESP32:RX:v2.2"));
  } else if (cmd == "PING") {
    Serial.println(F("PONG:NANO_ESP32_OK"));
  } else if (cmd.startsWith("MODO:SERVOS,")) {
    int m = cmd.substring(12).toInt();
    modoServos180 = (m == 180);
    if (modoServos180) {
      Serial.println(F("[MODO] Servos configurados en: MODO 180 POSICIONAL (write angulo directo)."));
      servo1.write(90); servo2.write(90); servo3.write(90); servo4.write(90);
    } else {
      Serial.println(F("[MODO] Servos configurados en: MODO 360 CONTINUO (pulsos temporizados y neutro us)."));
      frenarServosNeutro();
    }
  } else if (cmd == "MODO:SERVOS?" || cmd == "MODO?") {
    Serial.print(F("[MODO] Servos actuales: "));
    Serial.println(modoServos180 ? F("180 POSICIONAL") : F("360 CONTINUO"));
  } else if (cmd.startsWith("MOT:IZQ,")) {
    int pwm = cmd.substring(8).toInt();
    aplicarControlMotores(pwm, 0);
    Serial.print(F("[MOT] Motor Izquierdo fijado a PWM ")); Serial.println(pwm);
  } else if (cmd.startsWith("MOT:DER,")) {
    int pwm = cmd.substring(8).toInt();
    aplicarControlMotores(0, pwm);
    Serial.print(F("[MOT] Motor Derecho fijado a PWM ")); Serial.println(pwm);
  } else if (cmd.startsWith("MOT:AMBOS,")) {
    int sep = cmd.indexOf(',', 10);
    if (sep > 0) {
      int pI = cmd.substring(10, sep).toInt();
      int pD = cmd.substring(sep + 1).toInt();
      aplicarControlMotores(pI, pD);
      Serial.print(F("[MOT] Traccion fijada Izq=")); Serial.print(pI);
      Serial.print(F(" Der=")); Serial.println(pD);
    }
  } else if (cmd == "MOT:PARAR") {
    pararMotores();
    Serial.println(F("[MOT] Traccion detenida."));
  } else if (cmd == "MOTORES:OFF") {
    motoresHabilitados = false;
    pararMotores();
    Serial.println(F("[SEGURIDAD] Motores de traccion DESHABILITADOS por software."));
  } else if (cmd == "MOTORES:ON") {
    motoresHabilitados = true;
    Serial.println(F("[SEGURIDAD] Motores de traccion HABILITADOS."));
  } else if (cmd == "STOP" || cmd == "PARAR") {
    pararMotores();
    frenarServosNeutro();
    estadoDirActual = DIR_CENTRO;
    estadoDirObjetivo = DIR_CENTRO;
    Serial.println(F("[OK] Parada total aplicada y servos frenados en neutro."));
  } else if (cmd.startsWith("TEST:M_IZQ,")) {
    int pwm = cmd.substring(11).toInt();
    Serial.print(F("[TEST] Motor Izquierdo a PWM ")); Serial.print(pwm); Serial.println(F(" por 1.5s..."));
    aplicarControlMotores(pwm, 0);
    delay(1500);
    pararMotores();
    Serial.println(F("[TEST] Motor Izquierdo detenido."));
  } else if (cmd.startsWith("TEST:M_DER,")) {
    int pwm = cmd.substring(11).toInt();
    Serial.print(F("[TEST] Motor Derecho a PWM ")); Serial.print(pwm); Serial.println(F(" por 1.5s..."));
    aplicarControlMotores(0, pwm);
    delay(1500);
    pararMotores();
    Serial.println(F("[TEST] Motor Derecho detenido."));
  } else if (cmd.startsWith("INV:LOGICA,")) {
    invertirLogicaPwm = (cmd.substring(11).toInt() != 0);
    pararMotores();
    Serial.print(F("[CONFIG] Inversion logica PWM establecida en: "));
    Serial.println(invertirLogicaPwm ? F("ACTIVADA (255 - PWM)") : F("DESACTIVADA"));
  } else if (cmd.startsWith("INV:DIR_IZQ,")) {
    invertirDirIzq = (cmd.substring(12).toInt() != 0);
    Serial.print(F("[CONFIG] Inversion direccion izquierda: "));
    Serial.println(invertirDirIzq ? F("ACTIVADA") : F("DESACTIVADA"));
  } else if (cmd.startsWith("INV:DIR_DER,")) {
    invertirDirDer = (cmd.substring(12).toInt() != 0);
    Serial.print(F("[CONFIG] Inversion direccion derecha: "));
    Serial.println(invertirDirDer ? F("ACTIVADA") : F("DESACTIVADA"));
  } else if (cmd.startsWith("TEST:PIN_RAW,")) {
    String resto = cmd.substring(13);
    int sep = resto.indexOf(',');
    if (sep > 0) {
      String pinNom = resto.substring(0, sep);
      pinNom.toUpperCase();
      int val = constrain(resto.substring(sep + 1).toInt(), 0, 255);
      int duty = val;
      if (invertirLogicaPwm) {
        duty = 255 - val;
      }
      if (pinNom == "D2" || pinNom == "A1A") {
        setPwmA1A(duty);
        Serial.print(F("[TEST PIN] A1A (D2) fijado a Potencia ")); Serial.print(val);
        Serial.print(F(" (Duty LEDC ")); Serial.print(duty); Serial.println(F(")"));
      } else if (pinNom == "D5" || pinNom == "A1B") {
        setPwmA1B(duty);
        Serial.print(F("[TEST PIN] A1B (D5) fijado a Potencia ")); Serial.print(val);
        Serial.print(F(" (Duty LEDC ")); Serial.print(duty); Serial.println(F(")"));
      } else if (pinNom == "D3" || pinNom == "B1A") {
        setPwmB1A(duty);
        Serial.print(F("[TEST PIN] B1A (D3) fijado a Potencia ")); Serial.print(val);
        Serial.print(F(" (Duty LEDC ")); Serial.print(duty); Serial.println(F(")"));
      } else if (pinNom == "D4" || pinNom == "B1B") {
        setPwmB1B(duty);
        Serial.print(F("[TEST PIN] B1B (D4) fijado a Potencia ")); Serial.print(val);
        Serial.print(F(" (Duty LEDC ")); Serial.print(duty); Serial.println(F(")"));
      } else {
        Serial.println(F("[ERROR PIN] Pin no reconocido. Use D2, D5, D3 o D4."));
      }
    }
  } else if (cmd.startsWith("S1") || cmd.startsWith("S2") || cmd.startsWith("S3") || cmd.startsWith("S4")) {
    int servoNum = cmd.substring(1, 2).toInt();
    String op = cmd.substring(2);
    op.trim();
    int* targetNeutro = nullptr;
    Servo* targetServo = nullptr;
    if (servoNum == 1) { targetNeutro = &neutroS1; targetServo = &servo1; }
    else if (servoNum == 2) { targetNeutro = &neutroS2; targetServo = &servo2; }
    else if (servoNum == 3) { targetNeutro = &neutroS3; targetServo = &servo3; }
    else if (servoNum == 4) { targetNeutro = &neutroS4; targetServo = &servo4; }

    if (targetNeutro && targetServo) {
      if (op == "+" || op == "") {
        *targetNeutro += 1;
      } else if (op == "++") {
        *targetNeutro += 5;
      } else if (op == "-") {
        *targetNeutro -= 1;
      } else if (op == "--") {
        *targetNeutro -= 5;
      } else if (op.startsWith("+")) {
        *targetNeutro += op.substring(1).toInt();
      } else if (op.startsWith("-")) {
        *targetNeutro -= op.substring(1).toInt();
      } else if (op.startsWith("=") || op.startsWith(",")) {
        *targetNeutro = op.substring(1).toInt();
      }
      *targetNeutro = constrain(*targetNeutro, 1000, 2000);
      targetServo->writeMicroseconds(*targetNeutro);
      Serial.print(F("[CALIB] S")); Serial.print(servoNum);
      Serial.print(F(" Neutro actualizado a: ")); Serial.print(*targetNeutro);
      Serial.println(F(" us (aplicado inmediatamente)."));
    }
  } else if (cmd == "GUARDAR" || cmd == "GUARDAR:CALIB" || cmd == "SAVE" || cmd == "CALIB:SAVE") {
    guardarCalibracionNVS();
  } else if (cmd == "VER" || cmd == "VER:CALIB" || cmd == "CALIB:VER" || cmd == "AYUDA" || cmd == "HELP") {
    Serial.println(F("=== ESTADO ACTUAL DE CALIBRACION SERVOS ==="));
    Serial.print(F("  Modo Servos   : ")); Serial.println(modoServos180 ? F("180 POSICIONAL (angulo directo)") : F("360 CONTINUO (pulsos/neutro)"));
    Serial.print(F("  S1 (Del. Izq) : ")); Serial.print(neutroS1); Serial.print(F(" us | dir: ")); Serial.println(dirS1);
    Serial.print(F("  S2 (Del. Der) : ")); Serial.print(neutroS2); Serial.print(F(" us | dir: ")); Serial.println(dirS2);
    Serial.print(F("  S3 (Tras. Izq): ")); Serial.print(neutroS3); Serial.print(F(" us | dir: ")); Serial.println(dirS3);
    Serial.print(F("  S4 (Tras. Der): ")); Serial.print(neutroS4); Serial.print(F(" us | dir: ")); Serial.println(dirS4);
    Serial.print(F("  Duracion Pulso: ")); Serial.print(duracionGiroMs); Serial.println(F(" ms"));
    Serial.print(F("  Velocidad Giro: ")); Serial.print(deltaVelGiro); Serial.println(F(" us offset"));
    Serial.print(F("  Invertir Global: ")); Serial.println(invertirSentidoServos ? F("SI") : F("NO"));
    Serial.println(F("Comandos disponibles:"));
    Serial.println(F("  S1+, S1-, S1++, S1--, S1=1510 (ajuste fino de neutro)"));
    Serial.println(F("  INVS1, INVS2, INVS3, INVS4 (invierte sentido de giro del servo)"));
    Serial.println(F("  DUR,140 (fija duracion de pulso en ms)"));
    Serial.println(F("  VEL,90 (fija offset de velocidad en us)"));
    Serial.println(F("  TEST:IZQ / TEST:DER / TEST:CENTRO (prueba movimiento de viraje)"));
    Serial.println(F("  GUARDAR (guarda en memoria flash NVS permanente)"));
    Serial.println(F("==============================================="));
  } else if (cmd == "INVS1") {
    dirS1 = -dirS1;
    Serial.print(F("[CALIB] dirS1 invertido a: ")); Serial.println(dirS1);
  } else if (cmd == "INVS2") {
    dirS2 = -dirS2;
    Serial.print(F("[CALIB] dirS2 invertido a: ")); Serial.println(dirS2);
  } else if (cmd == "INVS3") {
    dirS3 = -dirS3;
    Serial.print(F("[CALIB] dirS3 invertido a: ")); Serial.println(dirS3);
  } else if (cmd == "INVS4") {
    dirS4 = -dirS4;
    Serial.print(F("[CALIB] dirS4 invertido a: ")); Serial.println(dirS4);
  } else if (cmd == "INV:SERVOS" || cmd == "INV:DIR") {
    invertirSentidoServos = !invertirSentidoServos;
    Serial.print(F("[CALIB] Inversion global de servos: "));
    Serial.println(invertirSentidoServos ? F("ACTIVADA") : F("DESACTIVADA"));
  } else if (cmd.startsWith("DUR,") || cmd.startsWith("CALIB:DUR,")) {
    int idx = cmd.indexOf(',');
    duracionGiroMs = cmd.substring(idx + 1).toInt();
    Serial.print(F("[CALIB] Duracion de pulso de giro fijada a: ")); Serial.print(duracionGiroMs); Serial.println(F(" ms"));
  } else if (cmd.startsWith("VEL,") || cmd.startsWith("CALIB:VEL,")) {
    int idx = cmd.indexOf(',');
    deltaVelGiro = cmd.substring(idx + 1).toInt();
    Serial.print(F("[CALIB] Offset de velocidad de giro fijado a: ")); Serial.print(deltaVelGiro); Serial.println(F(" us"));
  } else if (cmd.startsWith("NEUTRO,")) {
    int p1 = cmd.indexOf(',', 7);
    int p2 = (p1 > 0) ? cmd.indexOf(',', p1 + 1) : -1;
    int p3 = (p2 > 0) ? cmd.indexOf(',', p2 + 1) : -1;
    if (p1 > 0 && p2 > 0 && p3 > 0) {
      neutroS1 = constrain(cmd.substring(7, p1).toInt(), 1000, 2000);
      neutroS2 = constrain(cmd.substring(p1 + 1, p2).toInt(), 1000, 2000);
      neutroS3 = constrain(cmd.substring(p2 + 1, p3).toInt(), 1000, 2000);
      neutroS4 = constrain(cmd.substring(p3 + 1).toInt(), 1000, 2000);
      frenarServosNeutro();
      Serial.println(F("[CALIB] 4 Neutros fijados y aplicados."));
    }
  } else if (cmd == "TEST:IZQ" || cmd == "IZQ") {
    Serial.println(F("[TEST] Ejecutando pulso viraje hacia IZQUIERDA..."));
    ejecutarPulsoGiro(-1, duracionGiroMs);
  } else if (cmd == "TEST:DER" || cmd == "DER") {
    Serial.println(F("[TEST] Ejecutando pulso viraje hacia DERECHA..."));
    ejecutarPulsoGiro(+1, duracionGiroMs);
  } else if (cmd == "TEST:CENTRO" || cmd == "CENTRO") {
    frenarServosNeutro();
    estadoDirActual = DIR_CENTRO;
    estadoDirObjetivo = DIR_CENTRO;
    Serial.println(F("[TEST] Servos frenados en neutro y reiniciados a CENTRO."));
  } else if (cmd.startsWith("TEST:S1,")) {
    int val = cmd.substring(8).toInt();
    if (val > 500) servo1.writeMicroseconds(val);
    else servo1.write(val);
    Serial.print(F("[TEST] Servo 1 a ")); Serial.println(val);
  } else if (cmd.startsWith("TEST:S2,")) {
    int val = cmd.substring(8).toInt();
    if (val > 500) servo2.writeMicroseconds(val);
    else servo2.write(val);
    Serial.print(F("[TEST] Servo 2 a ")); Serial.println(val);
  } else if (cmd.startsWith("TEST:S3,")) {
    int val = cmd.substring(8).toInt();
    if (val > 500) servo3.writeMicroseconds(val);
    else servo3.write(val);
    Serial.print(F("[TEST] Servo 3 a ")); Serial.println(val);
  } else if (cmd.startsWith("TEST:S4,")) {
    int val = cmd.substring(8).toInt();
    if (val > 500) servo4.writeMicroseconds(val);
    else servo4.write(val);
    Serial.print(F("[TEST] Servo 4 a ")); Serial.println(val);
  } else if (cmd == "TEST:SERVOS_CENTRO") {
    frenarServosNeutro();
    Serial.println(F("[TEST] Servos frenados en su valor neutro calibrado."));
  } else if (cmd == "TEST:SWEEP") {
    Serial.println(F("[TEST] Viraje Izquierda (140 ms) -> Neutro -> Viraje Derecha (140 ms) -> Neutro"));
    ejecutarPulsoGiro(-1, duracionGiroMs);
    delay(duracionGiroMs + 500);
    frenarServosNeutro();
    delay(500);
    ejecutarPulsoGiro(+1, duracionGiroMs);
    delay(duracionGiroMs + 500);
    frenarServosNeutro();
    Serial.println(F("[TEST] Prueba de viraje completada."));
  }
}

void procesarTramaCsv(const String& trama) {
  int partes[7];
  int contadorPartes = 0;
  for (int i = 0; i < trama.length() && contadorPartes < 6; i++) {
    if (trama.charAt(i) == ',') {
      partes[contadorPartes++] = i;
    }
  }
  if (contadorPartes >= 6) {
    String cmd = trama.substring(0, partes[0]);
    cmd.toUpperCase();
    int potIzq = trama.substring(partes[0] + 1, partes[1]).toInt();
    int potDer = trama.substring(partes[1] + 1, partes[2]).toInt();
    int s1     = constrain(trama.substring(partes[2] + 1, partes[3]).toInt(), 10, 170);
    int s2     = constrain(trama.substring(partes[3] + 1, partes[4]).toInt(), 10, 170);
    int s3     = constrain(trama.substring(partes[4] + 1, partes[5]).toInt(), 10, 170);
    int s4     = constrain(trama.substring(partes[5] + 1).toInt(), 10, 170);

    PaqueteControl p;
    p.angulo_s1 = s1; p.angulo_s2 = s2; p.angulo_s3 = s3; p.angulo_s4 = s4;
    if (cmd == "W") { p.traccion_izq = potIzq; p.traccion_der = potDer; }
    else if (cmd == "S") { p.traccion_izq = -potIzq; p.traccion_der = -potDer; }
    else if (cmd == "PIVOT_IZQ") { p.traccion_izq = -potIzq; p.traccion_der = potDer; }
    else if (cmd == "PIVOT_DER") { p.traccion_izq = potIzq; p.traccion_der = -potDer; }
    else if (cmd == "A" || cmd == "D" || cmd == "CRAB") { p.traccion_izq = potIzq; p.traccion_der = potDer; }
    else { p.traccion_izq = 0; p.traccion_der = 0; }
    procesarPaquete(p);
  }
}

void setup() {
  Serial.begin(115200);

  // Inicializacion de canales PWM hardware LEDC dedicados para traccion (1000 Hz, 8 bits)
  ledcSetup(CH_MOT_A1A, 1000, 8);
  ledcAttachPin(pinA1A, CH_MOT_A1A);

  ledcSetup(CH_MOT_A1B, 1000, 8);
  ledcAttachPin(pinA1B, CH_MOT_A1B);

  ledcSetup(CH_MOT_B1A, 1000, 8);
  ledcAttachPin(pinB1A, CH_MOT_B1A);

  ledcSetup(CH_MOT_B1B, 1000, 8);
  ledcAttachPin(pinB1B, CH_MOT_B1B);

  pararMotores();

  // Inicializacion de los 4 Servomotores estandar de Arduino (LEDC 50 Hz, 14 bits)
  servo1.attach(pinServo1);
  servo2.attach(pinServo2);
  servo3.attach(pinServo3);
  servo4.attach(pinServo4);

  // Cargar calibracion de neutros y parametros NVS desde memoria Flash y frenar inmediatamente
  cargarCalibracionNVS();
  frenarServosNeutro();

#if MODO_CONEXION_WIFI
  // Inicializacion del enlace Wi-Fi SoftAP
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);
  udp.begin(PUERTO_UDP);

  Serial.println(F("SYS:ARDUINO_NANO_ESP32_WIFI_RECEPTOR_LISTO"));
  Serial.print(F("INFO:AP_SSID=")); Serial.println(AP_SSID);
  Serial.print(F("INFO:AP_IP=")); Serial.println(WiFi.softAPIP());
  Serial.print(F("INFO:UDP_PORT=")); Serial.println(PUERTO_UDP);
#else
  // Inicializacion del enlace Radiofrecuencia NRF24L01+
  SPI.begin(SCK, MISO, MOSI, SS);

  if (!radio.begin()) {
    Serial.println(F("[ERROR] No se detecto el modulo NRF24L01 en Arduino Nano ESP32."));
    Serial.println(F("[CHECK] Verifica conexion SPI: D11, D12, D13, D9, D10, 3.3V y GND."));
    Serial.println(F("[WARN] Operando en modo degradado USB Serie (diagnostico disponible)."));
    radioInicializada = false;
  } else {
    radioInicializada = true;
    radio.setPayloadSize(sizeof(PaqueteControl));
    radio.setPALevel(RF24_PA_MAX);
    radio.setDataRate(RF24_250KBPS);
    radio.setChannel(108);
    radio.setAutoAck(false);
    radio.openReadingPipe(1, DIRECCION_RF);
    radio.startListening();
    Serial.println(F("SYS:ARDUINO_NANO_ESP32_NRF24_RECEPTOR_LISTO"));
  }
#endif

  ultimaRecepcion = millis();
}

void loop() {
  // Actualizar temporizacion no bloqueante de viraje de servos 360
  actualizarPulsosDireccion360();

#if MODO_CONEXION_WIFI
  // Deteccion de paquetes entrantes por socket Wi-Fi UDP
  int tamanoPaquete = udp.parsePacket();
  if (tamanoPaquete > 0) {
    if (tamanoPaquete == sizeof(PaqueteControl)) {
      // Paquete binario estricto (8 bytes)
      PaqueteControl paquete;
      udp.read((char*)&paquete, sizeof(paquete));
      procesarPaquete(paquete);
    } else {
      // Trama de texto ASCII (CSV de control o comandos directos)
      char bufUdp[128];
      int len = udp.read(bufUdp, sizeof(bufUdp) - 1);
      if (len > 0) {
        bufUdp[len] = '\0';
        String msg = String(bufUdp);
        msg.trim();
        int comas = 0;
        for (int i = 0; i < msg.length(); i++) {
          if (msg.charAt(i) == ',') comas++;
        }
        if (comas >= 6) {
          procesarTramaCsv(msg);
        } else {
          procesarComandoSerial(msg);
        }
      }
    }
  }
#else
  // Deteccion de paquetes entrantes por Radiofrecuencia NRF24L01+
  if (radioInicializada && radio.available()) {
    PaqueteControl paquete;
    while (radio.available()) {
      radio.read(&paquete, sizeof(paquete));
    }
    procesarPaquete(paquete);
  }
#endif

  // Watchdog Failsafe de Seguridad: Parada si transcurre mas de 1 seg sin paquete
  if (millis() - ultimaRecepcion > TIMEOUT_MS) {
    pararMotores();
    frenarServosNeutro();
    if (millis() - ultimoAvisoFailsafe > 1000) {
      ultimoAvisoFailsafe = millis();
      Serial.println(F("TLM:FAILSAFE,0,90,90,90,90,1000,0"));
    }
  }

  // Recepcion de comandos por puerto USB Serial (COM19 / consola)
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      int comas = 0;
      for (int i = 0; i < cmd.length(); i++) {
        if (cmd.charAt(i) == ',') comas++;
      }
      if (comas >= 6) {
        procesarTramaCsv(cmd);
      } else {
        procesarComandoSerial(cmd);
      }
    }
  }
}
