// Sustituto minimo del nucleo Arduino para ejecutar los .ino en la PC (solo pruebas).
#pragma once
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <deque>
#include <string>

#define HIGH 1
#define LOW 0
#define OUTPUT 1
enum { D0, D1, D2, D3, D4, D5, D6, D7, D8, D9, D10, D11, D12, D13 };
enum { LED_RED = 46, LED_GREEN = 40, LED_BLUE = 45 };
#define RTC_NOINIT_ATTR

extern uint32_t g_ahora;
void banco_evento(const char *fmt, ...);

inline uint32_t millis() { return g_ahora; }
inline void pinMode(uint8_t, uint8_t) {}
inline void digitalWrite(uint8_t pin, uint8_t v) {
  if (pin != LED_RED && pin != LED_GREEN && pin != LED_BLUE) banco_evento("DW %u %u", pin, v);
}
inline void analogWrite(uint8_t pin, int v) { banco_evento("PWM %u %d", pin, v); }
inline void vTaskDelay(int) {}
inline void setCpuFrequencyMhz(int) {}
template <typename T, typename L, typename H>
inline T constrain(T x, L a, H b) { return x < (T)a ? (T)a : (x > (T)b ? (T)b : x); }
inline long map(long x, long a, long b, long c, long d) { return (x - a) * (d - c) / (b - a) + c; }

class SerieBanco {
 public:
  std::deque<char> entrada;
  void begin(int) {}
  operator bool() const { return true; }
  int availableForWrite() const { return 4096; }
  int available() const { return (int)entrada.size(); }
  int read() { char c = entrada.front(); entrada.pop_front(); return (uint8_t)c; }
  size_t write(const uint8_t *d, size_t n);
};
extern SerieBanco Serial;
