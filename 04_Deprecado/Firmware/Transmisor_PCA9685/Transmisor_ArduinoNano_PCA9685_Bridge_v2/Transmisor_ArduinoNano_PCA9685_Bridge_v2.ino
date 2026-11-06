/**
 * TRANSMISOR — Arduino Nano ESP32
 * ================================
 * Recibe tramas de la HMI (PC) por Serial USB y las reenvía al ejecutor
 * del rover mediante WiFi UDP.
 *
 * Protocolo: CMD,PWM_IZQ,PWM_DER,S1,S2,S3,S4\n
 * Ej: W,150,150,90,90,90,90
 */

#include <WiFi.h>
#include <WiFiUdp.h>

// ---------------------------------------------------------------------------
// Configuración
// ---------------------------------------------------------------------------
const char*    SSID          = "RoverCEPIT";
const char*    PASSWORD      = "rover2024";
const char*    EXECUTOR_IP   = "192.168.4.2";   // <-- IP del ejecutor
const uint16_t EXECUTOR_PORT = 4210;
const uint32_t SERIAL_BAUD   = 115200;

// ---------------------------------------------------------------------------
// LED de estado
// ---------------------------------------------------------------------------
#define LED_PIN LED_BUILTIN

// ---------------------------------------------------------------------------
// Objetos globales
// ---------------------------------------------------------------------------
WiFiUDP udp;
bool wifiListo = false;

// ---------------------------------------------------------------------------
// setup() — NO bloquea. Inicia WiFi y sale inmediatamente.
// ---------------------------------------------------------------------------
void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.begin(SERIAL_BAUD);
  delay(1000); // dar tiempo al USB para enumerar antes de cualquier otra cosa

  Serial.println("[TX] Transmisor iniciando...");

  // Iniciar WiFi sin esperar conexion (no bloquea)
  WiFi.begin(SSID, PASSWORD);
  Serial.print("[TX] Conectando a WiFi: ");
  Serial.println(SSID);

  // Abrir socket UDP
  udp.begin(0);
}

// ---------------------------------------------------------------------------
// loop()
// ---------------------------------------------------------------------------
void loop() {
  // Verificar estado WiFi y actualizar LED
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiListo) {
      wifiListo = true;
      digitalWrite(LED_PIN, HIGH);
      Serial.print("[TX] WiFi conectado. IP: ");
      Serial.println(WiFi.localIP());
      Serial.println("[TX] Listo para recibir tramas de la HMI.");
    }
  } else {
    if (wifiListo) {
      wifiListo = false;
      digitalWrite(LED_PIN, LOW);
      Serial.println("[TX] WiFi desconectado. Reconectando...");
      WiFi.begin(SSID, PASSWORD);
    }
  }

  // Leer trama de la HMI y reenviar por UDP
  if (Serial.available()) {
    String trama = Serial.readStringUntil('\n');
    trama.trim();
    if (trama.length() == 0) return;

    if (wifiListo) {
      udp.beginPacket(EXECUTOR_IP, EXECUTOR_PORT);
      udp.print(trama);
      udp.endPacket();
      Serial.print("[TX] UDP -> ");
      Serial.println(trama);
    } else {
      Serial.println("[TX] WARN: WiFi no conectado, trama descartada.");
    }
  }
}
