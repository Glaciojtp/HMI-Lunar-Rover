// Arduino Nano ESP32 – Receptor UART → PCA9685
// ------------------------------------------------------------
// Recibe por UART los comandos "S<id>:<angulo>" enviados por el
// transmisor y los traduce a PWM mediante la placa PCA9685.
// ------------------------------------------------------------

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// Configuración UART con el transmisor
const unsigned long BAUD_TRANSMIT = 115200; // debe coincidir con el transmisor

// Configuración PCA9685
#define PCA_I2C_ADDR 0x40      // dirección I2C por defecto
#define SERVO_FREQ   50        // 50 Hz para servos
#define SERVO_MIN    150       // 1 ms -> 0°
#define SERVO_MAX    550       // 2 ms -> 180°

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(PCA_I2C_ADDR);

// Mapeo de id de servo (1‑4) → canal de la PCA (0‑3)
const uint8_t channelMap[4] = {0, 1, 2, 3};

// -------------------------------------------------------------------
// Convierte ángulo (0‑180) a pulso PWM (150‑550)
// -------------------------------------------------------------------
uint16_t angleToPulse(int angle) {
  if (angle < 0)   angle = 0;
  if (angle > 180) angle = 180;
  long pulse = map(angle, 0, 180, SERVO_MIN, SERVO_MAX);
  return (uint16_t)pulse;
}

// -------------------------------------------------------------------
// Maneja una cadena del tipo "S<id>:<angulo>"
// -------------------------------------------------------------------
void handleCommand(const char *cmd) {
  if (cmd[0] != 'S' && cmd[0] != 's') return; // formato básico
  const char *colon = strchr(cmd, ':');
  if (!colon) return;

  int id    = atoi(&cmd[1]);          // 1‑4
  int angle = atoi(colon + 1);        // 0‑180
  if (id < 1 || id > 4) return;      // fuera de rango

  uint8_t channel = channelMap[id - 1];
  uint16_t pulse  = angleToPulse(angle);
  pca.setPWM(channel, 0, pulse);

  // Mensaje de depuración (opcional)
  Serial.print(F("Servo ")); Serial.print(id);
  Serial.print(F(" -> canal ")); Serial.print(channel);
  Serial.print(F(", ángulo ")); Serial.print(angle);
  Serial.print(F(", pulso ")); Serial.println(pulse);
}

void setup() {
  Serial.begin(115200);          // consola de depuración
  while (!Serial) { ; }

  // UART con el transmisor (Nano ESP32) – usa Serial1
  Serial1.begin(BAUD_TRANSMIT);
  Serial.println(F("\n*** Receptor PCA9685 listo ***"));

  // I2C y PCA9685
  Wire.begin();
  pca.begin();
  pca.setPWMFreq(SERVO_FREQ);
}

void loop() {
  static String line = "";
  while (Serial1.available()) {
    char c = Serial1.read();
    if (c == '\n' || c == '\r') {
      handleCommand(line.c_str());
      line = "";
    } else {
      line += c;
    }
  }
}
