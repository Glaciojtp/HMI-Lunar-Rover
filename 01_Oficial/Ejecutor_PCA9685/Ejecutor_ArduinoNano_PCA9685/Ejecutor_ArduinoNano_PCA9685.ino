#include <WiFi.h>
#include <WiFiUdp.h>
#include <Adafruit_PWMServoDriver.h>

// ----- Wi‑Fi credentials (same as transmitter) -----
const char* ssid = "YOUR_SSID";        // <-- replace
const char* password = "YOUR_PASSWORD"; // <-- replace

const uint16_t localPort = 4210; // UDP port we listen on
WiFiUDP udp;

// ----- PCA9685 setup -----
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();
const int SERVO_FREQ = 50;            // 50 Hz for hobby servos
const int SERVO_MIN_PULSE = 500;      // µs
const int SERVO_MAX_PULSE = 2500;     // µs

// ----- H‑bridge (L298N) pinout -----
const int ENA = 14; // PWM for motor A speed
const int IN1 = 27;
const int IN2 = 26;
const int ENB = 25; // PWM for motor B speed
const int IN3 = 33;
const int IN4 = 32;

void setup() {
  Serial.begin(115200);
  Serial.println("[RX] Executor starting …");

  // Wi‑Fi connection
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();
  Serial.print("[RX] Wi‑Fi connected, IP: ");
  Serial.println(WiFi.localIP());

  // UDP listener
  udp.begin(localPort);
  Serial.printf("[RX] Listening UDP port %d\n", localPort);

  // PCA9685 init
  pwm.begin();
  pwm.setPWMFreq(SERVO_FREQ);
  delay(10);

  // H‑bridge pins
  pinMode(ENA, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
}

// Convert angle (0‑180) → pulse‑width ticks for PCA9685
void setServo(uint8_t channel, uint16_t angle) {
  if (channel > 15) return; // PCA9685 has 16 channels
  uint16_t pulse = map(angle, 0, 180, SERVO_MIN_PULSE, SERVO_MAX_PULSE);
  uint16_t ticks = (pulse * 4096L) / (1000000L / SERVO_FREQ);
  pwm.setPWM(channel, 0, ticks);
  Serial.printf("[RX] Servo ch%u → %u° (ticks %u)\n", channel, angle, ticks);
}

void setMotorA(int speed) { // speed -255 … 255
  if (speed > 0) {
    digitalWrite(IN1, HIGH);
    digitalWrite(IN2, LOW);
  } else if (speed < 0) {
    digitalWrite(IN1, LOW);
    digitalWrite(IN2, HIGH);
    speed = -speed;
  } else {
    digitalWrite(IN1, LOW);
    digitalWrite(IN2, LOW);
  }
  analogWrite(ENA, constrain(speed, 0, 255));
}

void setMotorB(int speed) {
  if (speed > 0) {
    digitalWrite(IN3, HIGH);
    digitalWrite(IN4, LOW);
  } else if (speed < 0) {
    digitalWrite(IN3, LOW);
    digitalWrite(IN4, HIGH);
    speed = -speed;
  } else {
    digitalWrite(IN3, LOW);
    digitalWrite(IN4, LOW);
  }
  analogWrite(ENB, constrain(speed, 0, 255));
}

void loop() {
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char buffer[64];
    int len = udp.read(buffer, sizeof(buffer) - 1);
    if (len > 0) buffer[len] = '\0';
    String cmd = String(buffer);
    cmd.trim();
    Serial.print("[RX] Received: ");
    Serial.println(cmd);

    if (cmd.startsWith("S")) {
      // format: S<channel>:<angle>
      int colon = cmd.indexOf(':');
      if (colon > 1) {
        uint8_t ch = cmd.substring(1, colon).toInt();
        uint16_t ang = cmd.substring(colon + 1).toInt();
        setServo(ch, ang);
      }
    } else if (cmd.startsWith("M")) {
      // format: M<motor>:<speed>   motor 1 → A, 2 → B
      int colon = cmd.indexOf(':');
      if (colon > 1) {
        int motor = cmd.substring(1, colon).toInt();
        int sp = cmd.substring(colon + 1).toInt();
        sp = constrain(sp, -255, 255);
        if (motor == 1) setMotorA(sp);
        else if (motor == 2) setMotorB(sp);
      }
    }
  }
}
