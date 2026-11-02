#pragma once
#include <Arduino.h>
class IPAddress {
 public:
  uint8_t o[4];
  IPAddress(uint8_t a = 0, uint8_t b = 0, uint8_t c = 0, uint8_t d = 0) { o[0] = a; o[1] = b; o[2] = c; o[3] = d; }
};
enum { WIFI_AP = 2, WIFI_STA = 1 };
enum { WL_CONNECTED = 3, WL_DISCONNECTED = 6 };
enum wifi_power_t { WIFI_POWER_8_5dBm = 34 };
class WiFiBanco {
 public:
  bool conectado = false;
  int estaciones = 0;
  void mode(int m) { banco_evento("WIFI mode %d", m); }
  void softAP(const char *s, const char *p, int c, int h, int n) { banco_evento("WIFI softAP %s %d %d %d", s, c, h, n); }
  void setSleep(bool) {}
  void config(IPAddress a, IPAddress, IPAddress) { banco_evento("WIFI config %u.%u.%u.%u", a.o[0], a.o[1], a.o[2], a.o[3]); }
  void begin(const char *s, const char *, int c) { banco_evento("WIFI begin %s %d", s, c); }
  void setTxPower(wifi_power_t p) { banco_evento("WIFI power %d", (int)p); }
  void reconnect() { banco_evento("WIFI reconnect"); }
  int status() const { return conectado ? WL_CONNECTED : WL_DISCONNECTED; }
  int RSSI() const { return -55; }
  int softAPgetStationNum() const { return estaciones; }
};
extern WiFiBanco WiFi;
