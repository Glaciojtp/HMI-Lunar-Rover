#pragma once
#include <Arduino.h>
class WireBanco {
 public:
  int resultado = 0;
  void begin() {}
  void beginTransmission(uint8_t) {}
  int endTransmission() { return resultado; }
};
extern WireBanco Wire;
