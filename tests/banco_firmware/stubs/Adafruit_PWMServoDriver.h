#pragma once
#include <Arduino.h>
class Adafruit_PWMServoDriver {
 public:
  explicit Adafruit_PWMServoDriver(uint8_t) {}
  bool begin() { return true; }
  void setPWMFreq(float) {}
  void setPWM(uint8_t c, uint16_t on, uint16_t off) { banco_evento("PCA %u %u %u", c, on, off); }
};
