/**
 * EJECUTOR — Arduino Nano ESP32 (en el rover)
 * =============================================
 * Recibe tramas del transmisor por WiFi UDP y las ejecuta:
 *   - Motores DC  → Puente H L298N (2 canales: izq / der)
 *   - Servos      → PCA9685 I2C (canales 0..3)
 *
 * Protocolo: CMD,PWM_IZQ,PWM_DER,S1,S2,S3,S4\n
 * Ej: W,150,150,90,90,90,90
 *
 * Pines puente H (L298N):
 *   ENA → GPIO 14  (PWM izquierdo)
 *   IN1 → GPIO 27
 *   IN2 → GPIO 26
 *   ENB → GPIO 25  (PWM derecho)
 *   IN3 → GPIO 33
 *   IN4 → GPIO 32
 *
 * PCA9685 → SDA/SCL por I2C por defecto (A4/A5)
 *   S1 → canal 0  |  S2 → canal 1
 *   S3 → canal 2  |  S4 → canal 3
 */

#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ---------------------------------------------------------------------------
// Configuración
// ---------------------------------------------------------------------------
const char*    SSID       = "RoverCEPIT";
const char*    PASSWORD   = "rover2024";
const uint16_t LOCAL_PORT = 4210;

// Timeout de seguridad: frena motores si no llegan paquetes en X ms
const uint32_t SAFETY_TIMEOUT_MS = 500;

// ---------------------------------------------------------------------------
// LED de estado
// ---------------------------------------------------------------------------
#define LED_PIN LED_BUILTIN

// ---------------------------------------------------------------------------
// PCA9685
// ---------------------------------------------------------------------------
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);
const int SERVO_FREQ    = 50;    // Hz
const int SERVO_MIN_US  = 500;   // µs → 0°
const int SERVO_MAX_US  = 2500;  // µs → 180°

// ---------------------------------------------------------------------------
// Puente H (L298N)
// ---------------------------------------------------------------------------
const int ENA = 14;
const int IN1 = 27;
const int IN2 = 26;
const int ENB = 25;
const int IN3 = 33;
const int IN4 = 32;

// ---------------------------------------------------------------------------
// Estado global
// ---------------------------------------------------------------------------
WiFiUDP udp;
bool     wifiListo     = false;
uint32_t ultimoPaquete = 0;
bool     modoSeguro    = false;

// ---------------------------------------------------------------------------
// Motores DC
// ---------------------------------------------------------------------------
void setMotorIzq(int speed) {
  speed = constrain(speed, -255, 255);
  if (speed > 0)      { digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW); }
  else if (speed < 0) { digitalWrite(IN1, LOW);  digitalWrite(IN2, HIGH); speed = -speed; }
  else                { digitalWrite(IN1, LOW);  digitalWrite(IN2, LOW); }
  analogWrite(ENA, speed);
  Serial.printf("[RX] Motor IZQ: %d\n", speed);
}

void setMotorDer(int speed) {
  speed = constrain(speed, -255, 255);
  if (speed > 0)      { digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW); }
  else if (speed < 0) { digitalWrite(IN3, LOW);  digitalWrite(IN4, HIGH); speed = -speed; }
  else                { digitalWrite(IN3, LOW);  digitalWrite(IN4, LOW); }
  analogWrite(ENB, speed);
  Serial.printf("[RX] Motor DER: %d\n", speed);
}

void frenarMotores() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW); analogWrite(ENA, 0);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW); analogWrite(ENB, 0);
}

// ---------------------------------------------------------------------------
// Servos PCA9685
// ---------------------------------------------------------------------------
void setServo(uint8_t canal, int angulo) {
  if (canal > 15) return;
  angulo = constrain(angulo, 0, 360);
  uint32_t pulsoUs = map(angulo, 0, 180, SERVO_MIN_US, SERVO_MAX_US);
  uint16_t ticks   = (uint16_t)((pulsoUs * 4096UL) / 20000UL);
  pca.setPWM(canal, 0, ticks);
  Serial.printf("[RX] Servo ch%u: %d deg\n", canal, angulo);
}

void centrarServos() {
  for (uint8_t i = 0; i < 4; i++) setServo(i, 90);
}

// ---------------------------------------------------------------------------
// Parser: CMD,IZQ,DER,S1,S2,S3,S4
// ---------------------------------------------------------------------------
void parsearYEjecutar(const String& trama) {
  // Tokenizar por comas
  String tokens[7];
  int nTokens = 0, inicio = 0;
  for (int i = 0; i <= (int)trama.length() && nTokens < 7; i++) {
    if (i == (int)trama.length() || trama[i] == ',') {
      tokens[nTokens++] = trama.substring(inicio, i);
      inicio = i + 1;
    }
  }

  if (nTokens < 7) {
    if (trama == "IDENT" || trama == "PING") {
      Serial.println("[RX] IDENT/PING recibido.");
      return;
    }
    Serial.printf("[RX] Trama incompleta (%d tokens): %s\n", nTokens, trama.c_str());
    return;
  }

  String cmd = tokens[0];
  int pwmIzq = tokens[1].toInt();
  int pwmDer = tokens[2].toInt();
  int s1     = tokens[3].toInt();
  int s2     = tokens[4].toInt();
  int s3     = tokens[5].toInt();
  int s4     = tokens[6].toInt();

  Serial.printf("[RX] %s  IZQ=%d DER=%d  S=%d,%d,%d,%d\n",
                cmd.c_str(), pwmIzq, pwmDer, s1, s2, s3, s4);

  // Motores
  if (cmd == "STOP") {
    frenarMotores();
  } else {
    setMotorIzq(pwmIzq);
    setMotorDer(pwmDer);
  }

  // Servos
  setServo(0, s1);
  setServo(1, s2);
  setServo(2, s3);
  setServo(3, s4);
}

// ---------------------------------------------------------------------------
// setup() — NO bloquea en WiFi. Inicia todo y sale rápido.
// ---------------------------------------------------------------------------
void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Puente H — configurar pines primero
  pinMode(ENA, OUTPUT); pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(ENB, OUTPUT); pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
  frenarMotores();

  Serial.begin(115200);
  delay(1000); // dar tiempo al USB para enumerar

  Serial.println("[RX] Ejecutor iniciando...");

  // PCA9685
  Wire.begin();
  pca.begin();
  pca.setPWMFreq(SERVO_FREQ);
  centrarServos();
  Serial.println("[RX] PCA9685 listo. Servos centrados.");

  // Iniciar WiFi sin bloquear
  WiFi.begin(SSID, PASSWORD);
  Serial.print("[RX] Conectando a WiFi: ");
  Serial.println(SSID);

  // UDP (se usará cuando WiFi conecte)
  udp.begin(LOCAL_PORT);

  ultimoPaquete = millis();
  Serial.println("[RX] Setup completo. Esperando WiFi...");
}

// ---------------------------------------------------------------------------
// loop()
// ---------------------------------------------------------------------------
void loop() {
  // Estado WiFi
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiListo) {
      wifiListo = true;
      digitalWrite(LED_PIN, HIGH);
      Serial.print("[RX] WiFi conectado. IP: ");
      Serial.println(WiFi.localIP());
      Serial.printf("[RX] Escuchando UDP en puerto %d\n", LOCAL_PORT);
      ultimoPaquete = millis();
    }
  } else {
    if (wifiListo) {
      wifiListo = false;
      digitalWrite(LED_PIN, LOW);
      Serial.println("[RX] WiFi perdido. Reconectando...");
      frenarMotores();
      WiFi.begin(SSID, PASSWORD);
    }
  }

  // Timeout de seguridad
  if (wifiListo && !modoSeguro &&
      (millis() - ultimoPaquete > SAFETY_TIMEOUT_MS)) {
    Serial.println("[RX] SAFETY: sin paquetes. Frenando.");
    frenarMotores();
    centrarServos();
    modoSeguro = true;
  }

  // Leer paquete UDP
  if (wifiListo) {
    int packetSize = udp.parsePacket();
    if (packetSize > 0) {
      char buffer[128];
      int len = udp.read(buffer, sizeof(buffer) - 1);
      if (len > 0) buffer[len] = '\0';

      String trama = String(buffer);
      trama.trim();
      if (trama.length() == 0) return;

      ultimoPaquete = millis();
      modoSeguro    = false;

      parsearYEjecutar(trama);
    }
  }
}
