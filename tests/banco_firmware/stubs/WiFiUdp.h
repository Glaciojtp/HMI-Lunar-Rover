#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <vector>
class WiFiUDP {
 public:
  std::deque<std::vector<uint8_t>> cola;
  std::vector<uint8_t> actual, salida;
  IPAddress destino;
  uint16_t puerto = 0;
  int begin(uint16_t) { return 1; }
  int parsePacket() {
    if (cola.empty()) return 0;
    actual = cola.front();
    cola.pop_front();
    return (int)actual.size();
  }
  int read(char *b, size_t n) {
    size_t k = n < actual.size() ? n : actual.size();
    memcpy(b, actual.data(), k);
    actual.clear();
    return (int)k;
  }
  void flush() { actual.clear(); }
  int beginPacket(IPAddress ip, uint16_t p) { destino = ip; puerto = p; salida.clear(); return 1; }
  size_t write(const uint8_t *d, size_t n) { salida.insert(salida.end(), d, d + n); return n; }
  int endPacket();
};
extern WiFiUDP *g_udp;
