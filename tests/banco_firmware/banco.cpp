// Banco host: ejecuta setup()/loop() reales del .ino en la PC con hardware simulado.
//
// Comandos por stdin:
//   I            ejecuta setup()
//   A <ms>       avanza <ms> milisegundos llamando a loop() cada 1 ms
//   S <texto>    entrega <texto>\n por el puerto serie
//   U <hex>      entrega un datagrama UDP
//   W <0|1>      WiFi asociado (ejecutor) y estaciones conectadas (transmisor)
//   C <codigo>   causa de reset para el proximo setup()
//   P <0|1>      el PCA9685 responde
// Eventos por stdout: "<ms> <evento>"
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <iostream>
#include <string>

uint32_t g_ahora = 0;
int g_causa_reset = 1;
SerieBanco Serial;
WiFiBanco WiFi;
WireBanco Wire;
WiFiUDP *g_udp = nullptr;
extern WiFiUDP udp;
void setup();
void loop();

void banco_evento(const char *fmt, ...) {
  char b[256];
  va_list a;
  va_start(a, fmt);
  vsnprintf(b, sizeof(b), fmt, a);
  va_end(a);
  printf("%u %s\n", g_ahora, b);
}

size_t SerieBanco::write(const uint8_t *d, size_t n) {
  std::string s((const char *)d, n);
  while (!s.empty() && s.back() == '\n') s.pop_back();
  banco_evento("SER %s", s.c_str());
  return n;
}

int WiFiUDP::endPacket() {
  std::string h;
  char t[3];
  for (uint8_t v : salida) {
    snprintf(t, 3, "%02x", v);
    h += t;
  }
  banco_evento("UDP %u.%u.%u.%u:%u %s", destino.o[0], destino.o[1], destino.o[2], destino.o[3], puerto, h.c_str());
  return 1;
}

int main() {
  std::string l;
  while (std::getline(std::cin, l)) {
    if (l.empty()) continue;
    char c = l[0];
    std::string r = l.size() > 2 ? l.substr(2) : "";
    if (c == 'I') {
      setup();
    } else if (c == 'A') {
      for (int i = 0, n = std::stoi(r); i < n; i++) { g_ahora++; loop(); }
    } else if (c == 'S') {
      for (char x : r) Serial.entrada.push_back(x);
      Serial.entrada.push_back('\n');
    } else if (c == 'U') {
      std::vector<uint8_t> p;
      for (size_t i = 0; i + 1 < r.size(); i += 2) p.push_back((uint8_t)std::stoi(r.substr(i, 2), nullptr, 16));
      udp.cola.push_back(p);
    } else if (c == 'W') {
      WiFi.conectado = r == "1";
      WiFi.estaciones = r == "1" ? 1 : 0;
    } else if (c == 'C') {
      g_causa_reset = std::stoi(r);
    } else if (c == 'P') {
      Wire.resultado = r == "1" ? 0 : 2;
    }
  }
  return 0;
}
