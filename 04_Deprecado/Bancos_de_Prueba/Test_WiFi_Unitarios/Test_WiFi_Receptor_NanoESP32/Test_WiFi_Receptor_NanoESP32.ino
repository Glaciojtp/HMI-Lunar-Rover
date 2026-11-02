/*
 * =====================================================================================
 *  TEST WIFI RECEPTOR (SoftAP + UDP) — ARDUINO NANO ESP32 (COM21)
 *  Rover Lunar V2.0 — Diagnostico de enlace Wi-Fi nativo sin NRF24L01
 * =====================================================================================
 *  Hardware: Arduino Nano ESP32 (ESP32-S3 con Wi-Fi 2.4 GHz integrado)
 *  Funcion:
 *    - Levanta una red Wi-Fi propia (SoftAP): SSID "ROVER_NET", Pass "rover1234"
 *    - Escucha tramas UDP en el puerto 4210
 *    - No requiere router externo ni cables SPI
 * =====================================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

const char* AP_SSID = "ROVER_NET";
const char* AP_PASS = "rover1234";
const unsigned int PUERTO_UDP = 4210;

WiFiUDP udp;

// Trama oficial de 8 bytes
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255
  int16_t traccion_der;  // -255 a 255
  uint8_t angulo_s1;     // 10 a 170
  uint8_t angulo_s2;     // 10 a 170
  uint8_t angulo_s3;     // 10 a 170
  uint8_t angulo_s4;     // 10 a 170
};

unsigned long totalPaquetes = 0;
unsigned long ultimaRecepcion = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.println();
  Serial.println("=======================================================");
  Serial.println("   DIAGNOSTICO WIFI RECEPTOR (SoftAP) - ARDUINO NANO ESP32");
  Serial.println("=======================================================");
  Serial.println("[INFO] Configurando punto de acceso Wi-Fi...");

  WiFi.mode(WIFI_AP);
  bool apOk = WiFi.softAP(AP_SSID, AP_PASS);

  if (apOk) {
    IPAddress ip = WiFi.softAPIP();
    Serial.println("[OK] Red Wi-Fi iniciada correctamente.");
    Serial.print("   SSID:       "); Serial.println(AP_SSID);
    Serial.print("   Password:   "); Serial.println(AP_PASS);
    Serial.print("   IP Rover:   "); Serial.println(ip);
    Serial.print("   Puerto UDP: "); Serial.println(PUERTO_UDP);
    Serial.println("-------------------------------------------------------");
    Serial.println("La red 'ROVER_NET' deberia ser visible desde tu PC o celular.");
  } else {
    Serial.println("[ERROR] No se pudo iniciar el punto de acceso Wi-Fi.");
  }

  udp.begin(PUERTO_UDP);
  Serial.println("[INFO] Socket UDP escuchando. Esperando conexion del ESP32-C3...");
  Serial.println("=======================================================");
}

void loop() {
  int tamanoPaquete = udp.parsePacket();

  if (tamanoPaquete >= sizeof(PaqueteControl)) {
    PaqueteControl paquete;
    udp.read((char*)&paquete, sizeof(paquete));

    totalPaquetes++;
    unsigned long ahora = millis();
    unsigned long dt = (ultimaRecepcion > 0) ? (ahora - ultimaRecepcion) : 0;
    ultimaRecepcion = ahora;

    digitalWrite(LED_BUILTIN, HIGH);

    Serial.print("[UDP RX #");
    Serial.print(totalPaquetes);
    Serial.print(" | Desde: ");
    Serial.print(udp.remoteIP());
    Serial.print(" | dt: ");
    Serial.print(dt);
    Serial.print(" ms] Trac:[");
    Serial.print(paquete.traccion_izq);
    Serial.print(", ");
    Serial.print(paquete.traccion_der);
    Serial.print("] | Servos:[");
    Serial.print(paquete.angulo_s1);
    Serial.print(", ");
    Serial.print(paquete.angulo_s2);
    Serial.print(", ");
    Serial.print(paquete.angulo_s3);
    Serial.print(", ");
    Serial.print(paquete.angulo_s4);
    Serial.println("]");

    delay(5);
    digitalWrite(LED_BUILTIN, LOW);
  }

  // Notificar clientes conectados
  static unsigned long ultimoChequeo = 0;
  if (millis() - ultimoChequeo > 3000) {
    ultimoChequeo = millis();
    int estaciones = WiFi.softAPgetStationNum();
    if (estaciones == 0 && totalPaquetes == 0) {
      Serial.println("[ESPERANDO] Esperando que el ESP32-C3 se conecte a 'ROVER_NET'...");
    }
  }
}
