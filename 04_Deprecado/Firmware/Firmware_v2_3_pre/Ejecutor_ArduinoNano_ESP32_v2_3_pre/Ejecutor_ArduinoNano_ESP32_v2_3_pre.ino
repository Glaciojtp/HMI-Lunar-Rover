/*
 * =====================================================================================
 *  RECEPTOR ARDUINO NANO ESP32 — ROVER LUNAR V2.3-PRE (ELECTRONICA A BORDO)
 *  Soporte Completo Rocker-Bogie: 6 Motores Traccion + 4 Servomotores Posicionales Estandar
 * =====================================================================================
 *  Hardware: Arduino Nano ESP32 (ESP32-S3 a 3.3V) + Puente H L9110S + 4 Servos 180°
 *  Comunicaciones soportadas:
 *    - Wi-Fi Nativo (SoftAP + UDP en puerto 4210) [MODO ACTIVO DE LABORATORIO]
 *    - NRF24L01+ (Radiofrecuencia 2.4 GHz SPI Hardware) [Modo alternativo]
 *
 *  CARACTERISTICAS DE LA VERSION V2.3-PRE:
 *    - Control angular absoluto directo: cada servomotor se posiciona en el angulo exacto
 *      requerido [10, 170] grados via servo.write(), como un servomotor normal.
 *    - Eliminacion total de maquinas de estados temporizadas, pulsos de duracion fija y
 *      desplazamientos de neutro en microsegundos.
 *    - Posicion central neutra fija y estandar a 90 grados exactos.
 *    - Temporizadores Hardware LEDC dedicados para Servos (50 Hz, 14 bits) y Traccion (1000 Hz, 8 bits).
 *    - Watchdog failsafe automatico: tras 1000 ms sin paquetes validos, se detienen los motores
 *      y todos los servomotores se centran de forma segura a 90 grados.
 *    - Telemetria continua por USB Serial (COM19) compatible con HMI Python y HMI Rust.
 *    - Bloqueo de seguridad de traccion por software ("MOTORES:OFF" / "MOTORES:ON").
 * =====================================================================================
 */

#include <Arduino.h>
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
void centrarServos();
void aplicarControlMotores(int16_t pwmIzq, int16_t pwmDer);
void procesarComandoSerial(const String& cmd);
void procesarTramaCsv(const String& trama);

// ==========================================
// CONTROLADOR DE SERVOMOTORES INTEGRADO (STANDARD ARDUINO SERVO API)
// Implementa la interfaz estandar de Servo de Arduino (attach, write, read, etc.)
// utilizando los temporizadores de hardware LEDC nativos del ESP32-S3 a 50 Hz.
// Opera con mapeo angular directo sobre servomotores posicionales estandar (180 deg).
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

    // Hardware ESP32-S3 LEDC: 50 Hz (periodo 20000 us), resolucion de 14 bits (0 a 16383)
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
    angulo = constrain(angulo, 10, 170); // Limite mecanico estricto de seguridad del proyecto
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
bool invertirDirIzq = true;    // Por defecto TRUE: invierte PWM lado izquierdo para sentido de marcha colineal
bool invertirDirDer = false;   // Por defecto FALSE: lado derecho estandar
bool invertirLogicaPwm = false;// Por defecto FALSE: logica estandar directa (0 = STOP, 255 = maxima potencia)

// Temporizador Failsafe
unsigned long ultimaRecepcion = 0;
unsigned long ultimoAvisoFailsafe = 0;
const unsigned long TIMEOUT_MS = 1000; // 1 segundo sin senal = Parada total y centrado seguro

// Parada inmediata de todos los motores de traccion
void pararMotores() {
  if (invertirLogicaPwm) {
    setPwmA1A(255);
    setPwmA1B(255);
    setPwmB1A(255);
    setPwmB1B(255);
  } else {
    setPwmA1A(0);
    setPwmA1B(0);
    setPwmB1A(0);
    setPwmB1B(0);
  }
}

// Centrado neutro de todos los servomotores a 90 grados exactos
void centrarServos() {
  servo1.write(90);
  servo2.write(90);
  servo3.write(90);
  servo4.write(90);
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
    // Modo directo (0 = 0V / apagado, 255 = 100% potencia / 3.3V)
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

// Procesamiento principal de actuadores con angulos absolutos
void procesarControl(int16_t traccionIzq, int16_t traccionDer, uint8_t s1, uint8_t s2, uint8_t s3, uint8_t s4) {
  unsigned long ahora = millis();
  unsigned long dt = (ultimaRecepcion > 0) ? (ahora - ultimaRecepcion) : 0;
  ultimaRecepcion = ahora;

  // 1. Aplicar traccion en puente H
  aplicarControlMotores(traccionIzq, traccionDer);

  // 2. Aplicar servomotores como servos normales por angulo absoluto [10, 170] grados
  servo1.write(constrain(s1, 10, 170));
  servo2.write(constrain(s2, 10, 170));
  servo3.write(constrain(s3, 10, 170));
  servo4.write(constrain(s4, 10, 170));

  // 3. Telemetria estructurada hacia el puerto USB Serie (para HMI)
  Serial.print(F("TLM:"));
  Serial.print(motoresHabilitados ? traccionIzq : 0); Serial.print(F(","));
  Serial.print(motoresHabilitados ? traccionDer : 0); Serial.print(F(","));
  Serial.print(s1); Serial.print(F(","));
  Serial.print(s2); Serial.print(F(","));
  Serial.print(s3); Serial.print(F(","));
  Serial.print(s4); Serial.print(F(","));
  Serial.print(dt); Serial.print(F(","));
  Serial.println(0);

  // 4. Log legible en consola de depuracion (solo si cambiaron las consignas)
  static int16_t prevIzq = -999, prevDer = -999;
  static uint8_t prevS1 = 0, prevS2 = 0, prevS3 = 0, prevS4 = 0;
  if (traccionIzq != prevIzq || traccionDer != prevDer ||
      s1 != prevS1 || s2 != prevS2 || s3 != prevS3 || s4 != prevS4) {
    prevIzq = traccionIzq; prevDer = traccionDer;
    prevS1 = s1; prevS2 = s2; prevS3 = s3; prevS4 = s4;

    Serial.print(F("[RX v2.3] Trac:["));
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
  if (cmd == "IDENT") {
    Serial.println(F("ID:NANO_ESP32:RX:v2.3"));
  } else if (cmd == "PING") {
    Serial.println(F("PONG:NANO_ESP32_OK"));
  } else if (cmd == "STATUS") {
    Serial.println(F("STATUS:NANO_ESP32_RX_OK_ANGULAR"));
  } else if (cmd == "MOTORES:OFF") {
    motoresHabilitados = false;
    pararMotores();
    Serial.println(F("[SEGURIDAD] Motores de traccion DESHABILITADOS por software."));
  } else if (cmd == "MOTORES:ON") {
    motoresHabilitados = true;
    Serial.println(F("[SEGURIDAD] Motores de traccion HABILITADOS."));
  } else if (cmd == "STOP" || cmd == "PARAR") {
    pararMotores();
    centrarServos();
    Serial.println(F("[OK] Parada total aplicada y 4 servos centrados a 90 grados."));
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
  } else if (cmd.startsWith("TEST:PIN,")) {
    int coma1 = cmd.indexOf(',', 9);
    if (coma1 > 0) {
      String pinNom = cmd.substring(9, coma1);
      int val = cmd.substring(coma1 + 1).toInt();
      val = constrain(val, 0, 255);
      int duty = val;
      if (invertirLogicaPwm) {
        duty = 255 - val;
      }
      if (pinNom == "D2" || pinNom == "A1A") {
        setPwmA1A(duty);
        Serial.print(F("[TEST PIN] A1A (D2) fijado a Potencia ")); Serial.println(val);
      } else if (pinNom == "D5" || pinNom == "A1B") {
        setPwmA1B(duty);
        Serial.print(F("[TEST PIN] A1B (D5) fijado a Potencia ")); Serial.println(val);
      } else if (pinNom == "D3" || pinNom == "B1A") {
        setPwmB1A(duty);
        Serial.print(F("[TEST PIN] B1A (D3) fijado a Potencia ")); Serial.println(val);
      } else if (pinNom == "D4" || pinNom == "B1B") {
        setPwmB1B(duty);
        Serial.print(F("[TEST PIN] B1B (D4) fijado a Potencia ")); Serial.println(val);
      } else {
        Serial.println(F("[ERROR PIN] Pin no reconocido. Use D2, D5, D3 o D4."));
      }
    }
  } else if (cmd.startsWith("TEST:S1,")) {
    int ang = constrain(cmd.substring(8).toInt(), 10, 170);
    servo1.write(ang);
    Serial.print(F("[TEST] Servo 1 (Del. Izq) posicionado a ")); Serial.print(ang); Serial.println(F(" grados."));
  } else if (cmd.startsWith("TEST:S2,")) {
    int ang = constrain(cmd.substring(8).toInt(), 10, 170);
    servo2.write(ang);
    Serial.print(F("[TEST] Servo 2 (Del. Der) posicionado a ")); Serial.print(ang); Serial.println(F(" grados."));
  } else if (cmd.startsWith("TEST:S3,")) {
    int ang = constrain(cmd.substring(8).toInt(), 10, 170);
    servo3.write(ang);
    Serial.print(F("[TEST] Servo 3 (Tras. Izq) posicionado a ")); Serial.print(ang); Serial.println(F(" grados."));
  } else if (cmd.startsWith("TEST:S4,")) {
    int ang = constrain(cmd.substring(8).toInt(), 10, 170);
    servo4.write(ang);
    Serial.print(F("[TEST] Servo 4 (Tras. Der) posicionado a ")); Serial.print(ang); Serial.println(F(" grados."));
  } else if (cmd == "TEST:SERVOS_CENTRO" || cmd == "TEST:CENTRO") {
    centrarServos();
    Serial.println(F("[TEST] Los 4 servomotores centrados a 90 grados exactos."));
  } else if (cmd == "TEST:SWEEP") {
    Serial.println(F("[TEST] Barrido angular de los 4 servos: 90 -> 45 -> 135 -> 90 grados"));
    servo1.write(45); servo2.write(45); servo3.write(45); servo4.write(45);
    delay(1000);
    servo1.write(135); servo2.write(135); servo3.write(135); servo4.write(135);
    delay(1000);
    centrarServos();
    Serial.println(F("[TEST] Barrido completado exitosamente."));
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
    else if (cmd == "A" || cmd == "D" || cmd == "CRAB" || cmd == "CMD") { p.traccion_izq = potIzq; p.traccion_der = potDer; }
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

  // Centrar direccion de forma segura a 90 grados exactos
  centrarServos();

#if MODO_CONEXION_WIFI
  // Inicializacion del enlace Wi-Fi SoftAP
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);
  udp.begin(PUERTO_UDP);

  Serial.println(F("SYS:ARDUINO_NANO_ESP32_WIFI_RECEPTOR_V2_3_LISTO"));
  Serial.print(F("INFO:AP_SSID=")); Serial.println(AP_SSID);
  Serial.print(F("INFO:AP_IP=")); Serial.println(WiFi.softAPIP());
  Serial.print(F("INFO:UDP_PORT=")); Serial.println(PUERTO_UDP);
#else
  // Inicializacion del enlace Radiofrecuencia NRF24L01+
  SPI.begin(SCK, MISO, MOSI, SS);

  if (!radio.begin()) {
    Serial.println(F("[ERROR] No se detecto el modulo NRF24L01 en Arduino Nano ESP32."));
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
    Serial.println(F("SYS:ARDUINO_NANO_ESP32_NRF24_RECEPTOR_V2_3_LISTO"));
  }
#endif

  ultimaRecepcion = millis();
}

void loop() {
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

  // Watchdog Failsafe de Seguridad: Parada de motores y centrado de direccion si transcurre > 1000 ms
  if (millis() - ultimaRecepcion > TIMEOUT_MS) {
    pararMotores();
    centrarServos();
    if (millis() - ultimoAvisoFailsafe > 1000) {
      ultimoAvisoFailsafe = millis();
      Serial.println(F("TLM:FAILSAFE,0,90,90,90,90,1000,0"));
    }
  }

  // Recepcion de comandos por puerto USB Serial (COM19 / consola de depuracion)
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
