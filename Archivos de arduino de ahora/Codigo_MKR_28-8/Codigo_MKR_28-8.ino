#include <SPI.h>
#include <RF24.h>
#include <Servo.h>

// --- Configuración NRF24L01 ---
#define PIN_CE 0
#define PIN_CSN 1
RF24 radio(PIN_CE, PIN_CSN);
const byte DIRECCION[6] = "ROVER";

struct Paquete {
  uint8_t pwm_invertido;
  float voltaje;
};

unsigned long ultimaRecepcion = 0;
bool motorActivo = false;
#define TIMEOUT_MS 3000

// --- Pines de Dirección (Servos) ---
Servo servo1;
Servo servo2;
const int pinServo1 = 6;
const int pinServo2 = 7;
int posActualS1 = 90; 
int posActualS2 = 90;
int velocidadActual = 15; 

// --- Pines de Tracción (Puente H L9110S) ---
const int pinA1A = 5; 
const int pinA1B = 2; 
const int pinB1A = 3; 
const int pinB1B = 4; 
int potenciaMotor = 150; 

void pararMotores() {
  analogWrite(pinA1A, 0);
  analogWrite(pinA1B, 0);
  analogWrite(pinB1A, 0);
  analogWrite(pinB1B, 0);
  motorActivo = false;
}

void moverServosSuave(int s1Target, int s2Target) {
  s1Target = constrain(s1Target, 10, 170); // Protección mecánica
  s2Target = constrain(s2Target, 10, 170);

  while (posActualS1 != s1Target || posActualS2 != s2Target) {
    if (posActualS1 < s1Target) posActualS1++;
    else if (posActualS1 > s1Target) posActualS1--;
    
    if (posActualS2 < s2Target) posActualS2++;
    else if (posActualS2 > s2Target) posActualS2--;

    servo1.write(posActualS1);
    servo2.write(posActualS2);
    delay(velocidadActual); 
  }
}

void setup() {
  Serial.begin(115200);

  servo1.attach(pinServo1);
  servo2.attach(pinServo2);
  servo1.write(posActualS1);
  servo2.write(posActualS2);

  pinMode(pinA1A, OUTPUT);
  pinMode(pinA1B, OUTPUT);
  pinMode(pinB1A, OUTPUT);
  pinMode(pinB1B, OUTPUT);
  pararMotores();

  if (!radio.begin()) {
    Serial.println("ERROR: No se detecto NRF24L01.");
    while (true);
  }
  
  radio.setPALevel(RF24_PA_MAX);
  radio.setDataRate(RF24_250KBPS);
  radio.setChannel(108);
  radio.setAutoAck(true);
  radio.setRetries(5, 15);
  radio.openReadingPipe(1, DIRECCION);
  radio.startListening();
  
  ultimaRecepcion = millis();
  Serial.println("Control Vehiculo MKR 1310 (RF + L9110S Iniciado)");
}

void loop() {
  // 1. CONTROL POR RADIO (NRF24L01)
  if (radio.available()) {
    Paquete paquete;
    radio.read(&paquete, sizeof(paquete));
    ultimaRecepcion = millis();
    motorActivo = true;

    // Traducir PWM invertido a L9110S
    if (paquete.pwm_invertido == 255) {
      pararMotores();
    } else {
      // 0 = Máxima potencia, 254 = Mínima potencia
      int potenciaCalculada = 255 - paquete.pwm_invertido;
      analogWrite(pinA1B, 0);
      analogWrite(pinB1B, 0);
      analogWrite(pinA1A, potenciaCalculada); 
      analogWrite(pinB1A, potenciaCalculada);
    }
  }

  // 2. TIMEOUT DE SEGURIDAD
  if (motorActivo && (millis() - ultimaRecepcion > TIMEOUT_MS)) {
    pararMotores();
    Serial.println("TIMEOUT: Radio perdida. Motores detenidos.");
  }

  // 3. CONTROL POR SERIAL
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();
    comando.toUpperCase(); 

    if (comando.startsWith("S1")) {
      int spaceIndex = comando.indexOf(' '); 
      if (spaceIndex != -1) moverServosSuave(comando.substring(spaceIndex + 1).toInt(), posActualS2);
    } 
    else if (comando.startsWith("S2")) {
      int spaceIndex = comando.indexOf(' '); 
      if (spaceIndex != -1) moverServosSuave(posActualS1, comando.substring(spaceIndex + 1).toInt());
    } 
    else if (comando.startsWith("VELOCIDAD")) {
      int spaceIndex = comando.indexOf(' '); 
      if (spaceIndex != -1) velocidadActual = constrain(comando.substring(spaceIndex + 1).toInt(), 1, 100);
    }
    else if (comando == "ADELANTE") {
      analogWrite(pinA1B, 0); analogWrite(pinB1B, 0);
      analogWrite(pinA1A, potenciaMotor); analogWrite(pinB1A, potenciaMotor);
    }
    else if (comando == "ATRAS") {
      analogWrite(pinA1A, 0); analogWrite(pinB1A, 0);
      analogWrite(pinA1B, potenciaMotor); analogWrite(pinB1B, potenciaMotor);
    }
    else if (comando == "PARAR") {
      pararMotores();
    }
    else if (comando.startsWith("POTENCIA")) {
      int spaceIndex = comando.indexOf(' '); 
      if (spaceIndex != -1) potenciaMotor = constrain(comando.substring(spaceIndex + 1).toInt(), 0, 255);
    }
    else if (comando == "BAILAR") {
      for (int i = 0; i < 2; i++) {
        moverServosSuave(170, 10); moverServosSuave(90, 90);
        moverServosSuave(10, 170); moverServosSuave(90, 90);
      }
    }
    else if (comando == "DEMO") {
      moverServosSuave(135, 135); 
      analogWrite(pinA1B, 0); analogWrite(pinB1B, 0);
      analogWrite(pinA1A, potenciaMotor); analogWrite(pinB1A, potenciaMotor);
      delay(2000); 
      pararMotores(); delay(500);
      moverServosSuave(60, 60);
      analogWrite(pinA1B, potenciaMotor); analogWrite(pinB1B, potenciaMotor);
      delay(2000); 
      pararMotores();
      moverServosSuave(90, 90);
    }
  }
}