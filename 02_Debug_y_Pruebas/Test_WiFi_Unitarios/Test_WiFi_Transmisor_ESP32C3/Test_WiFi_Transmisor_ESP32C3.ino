/*
 * =====================================================================================
 *  TEST WIFI TRANSMISOR (STA + UDP) — ESP32-C3 (COM4)
 *  Rover Lunar V2.0 — Diagnostico de enlace Wi-Fi nativo sin NRF24L01
 * =====================================================================================
 *  Hardware: ESP32-C3 SuperMini / LOLIN C3 Mini (Wi-Fi 2.4 GHz integrado)
 *  Funcion:
 *    - Se conecta a la red Wi-Fi "ROVER_NET" emitida por el Arduino Nano ESP32
 *    - Envia paquetes de control por UDP al puerto 4210 de la IP 192.168.4.1
 * =====================================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

const char* TARGET_SSID = "ROVER_NET";
const char* TARGET_PASS = "rover1234";
const IPAddress IP_ROVER(192, 168, 4, 1);
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

PaqueteControl datosEnvio = {120, 120, 90, 90, 90, 90};

unsigned long totalEnvios = 0;
unsigned long ultimoEnvio = 0;
const unsigned long INTERVALO_ENVIO_MS = 1000;
bool envioAutomatico = true;

void enviarPaqueteUDP() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[AVISO] Wi-Fi desconectado. Esperando reconexion...");
    return;
  }

  totalEnvios++;
  udp.beginPacket(IP_ROVER, PUERTO_UDP);
  udp.write((const uint8_t*)&datosEnvio, sizeof(datosEnvio));
  udp.endPacket();

  Serial.print("[UDP TX #");
  Serial.print(totalEnvios);
  Serial.print("] Enviado a ");
  Serial.print(IP_ROVER);
  Serial.print(" -> Trac:[");
  Serial.print(datosEnvio.traccion_izq);
  Serial.print(", ");
  Serial.print(datosEnvio.traccion_der);
  Serial.print("] | Servos:[");
  Serial.print(datosEnvio.angulo_s1);
  Serial.print(", ");
  Serial.print(datosEnvio.angulo_s2);
  Serial.print(", ");
  Serial.print(datosEnvio.angulo_s3);
  Serial.print(", ");
  Serial.print(datosEnvio.angulo_s4);
  Serial.println("]");
}

void imprimirMenu() {
  Serial.println();
  Serial.println("=======================================================");
  Serial.println("   DIAGNOSTICO WIFI TRANSMISOR - ESP32-C3 (COM4)");
  Serial.println("=======================================================");
  Serial.print("   Estado Wi-Fi: ");
  Serial.println(WiFi.status() == WL_CONNECTED ? "CONECTADO" : "DESCONECTADO");
  Serial.print("   IP Local:     "); Serial.println(WiFi.localIP());
  Serial.print("   IP Destino:   "); Serial.println(IP_ROVER);
  Serial.print("   Puerto UDP:   "); Serial.println(PUERTO_UDP);
  Serial.println("-------------------------------------------------------");
  Serial.println("Comandos por teclado en Monitor Serie (115200 baudios):");
  Serial.println("   'w' -> Avance adelante (Trac 180, Servos 90)");
  Serial.println("   's' -> Reversa (Trac -180, Servos 90)");
  Serial.println("   'a' -> Giro izquierda (Trac 120, Servos 120)");
  Serial.println("   'd' -> Giro derecha (Trac 120, Servos 60)");
  Serial.println("   'x' -> Parada (Trac 0, Servos 90)");
  Serial.println("   'm' -> Alternar envio automatico 1 Hz (ON/OFF)");
  Serial.println("   '?' -> Reimprimir este menu");
  Serial.println("=======================================================");
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("=======================================================");
  Serial.println("   DIAGNOSTICO WIFI TRANSMISOR - ESP32-C3 (COM4)");
  Serial.println("=======================================================");
  Serial.print("[INFO] Conectando a la red Wi-Fi '");
  Serial.print(TARGET_SSID);
  Serial.println("'...");

  WiFi.mode(WIFI_STA);
  WiFi.begin(TARGET_SSID, TARGET_PASS);

  int reintentos = 0;
  while (WiFi.status() != WL_CONNECTED && reintentos < 20) {
    delay(500);
    Serial.print(".");
    reintentos++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[OK] Conectado exitosamente a 'ROVER_NET'.");
    Serial.print("   IP asignada: "); Serial.println(WiFi.localIP());
    Serial.print("   RSSI senal:  "); Serial.print(WiFi.RSSI()); Serial.println(" dBm");
  } else {
    Serial.println("[AVISO] No se pudo conectar aun. Se reintentara en segundo plano.");
    Serial.println("[CHECK] Asegurate de que el Arduino Nano ESP32 este encendido con su sketch.");
  }

  udp.begin(0); // Puerto local efimero para emision
  imprimirMenu();
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    if (envioAutomatico && (millis() - ultimoEnvio >= INTERVALO_ENVIO_MS)) {
      ultimoEnvio = millis();
      enviarPaqueteUDP();
    }
  } else {
    // Si se pierde la conexion, reintentar periodicamente
    static unsigned long ultimoReintento = 0;
    if (millis() - ultimoReintento > 3000) {
      ultimoReintento = millis();
      Serial.println("[RECONEXION] Buscando red 'ROVER_NET'...");
      WiFi.disconnect();
      WiFi.begin(TARGET_SSID, TARGET_PASS);
    }
  }

  if (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n') return;

    if (c == 'w' || c == 'W') {
      datosEnvio.traccion_izq = 180;
      datosEnvio.traccion_der = 180;
      datosEnvio.angulo_s1 = 90;
      datosEnvio.angulo_s2 = 90;
      datosEnvio.angulo_s3 = 90;
      datosEnvio.angulo_s4 = 90;
      enviarPaqueteUDP();
    } else if (c == 's' || c == 'S') {
      datosEnvio.traccion_izq = -180;
      datosEnvio.traccion_der = -180;
      datosEnvio.angulo_s1 = 90;
      datosEnvio.angulo_s2 = 90;
      datosEnvio.angulo_s3 = 90;
      datosEnvio.angulo_s4 = 90;
      enviarPaqueteUDP();
    } else if (c == 'a' || c == 'A') {
      datosEnvio.traccion_izq = 120;
      datosEnvio.traccion_der = 120;
      datosEnvio.angulo_s1 = 120;
      datosEnvio.angulo_s2 = 120;
      datosEnvio.angulo_s3 = 120;
      datosEnvio.angulo_s4 = 120;
      enviarPaqueteUDP();
    } else if (c == 'd' || c == 'D') {
      datosEnvio.traccion_izq = 120;
      datosEnvio.traccion_der = 120;
      datosEnvio.angulo_s1 = 60;
      datosEnvio.angulo_s2 = 60;
      datosEnvio.angulo_s3 = 60;
      datosEnvio.angulo_s4 = 60;
      enviarPaqueteUDP();
    } else if (c == 'x' || c == 'X') {
      datosEnvio.traccion_izq = 0;
      datosEnvio.traccion_der = 0;
      datosEnvio.angulo_s1 = 90;
      datosEnvio.angulo_s2 = 90;
      datosEnvio.angulo_s3 = 90;
      datosEnvio.angulo_s4 = 90;
      enviarPaqueteUDP();
    } else if (c == 'm' || c == 'M') {
      envioAutomatico = !envioAutomatico;
      Serial.print("[CONFIG] Envio automatico 1 Hz: ");
      Serial.println(envioAutomatico ? "ACTIVADO" : "DESACTIVADO");
    } else if (c == '?' || c == 'h' || c == 'H') {
      imprimirMenu();
    }
  }
}
