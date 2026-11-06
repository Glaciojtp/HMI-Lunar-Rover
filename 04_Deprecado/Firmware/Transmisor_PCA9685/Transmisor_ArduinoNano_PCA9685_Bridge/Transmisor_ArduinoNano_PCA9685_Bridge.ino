#include <WiFi.h>
#include <WiFiUdp.h>

// ----- Wi‑Fi credentials (same network as the executor) -----
const char* ssid = "YOUR_SSID";        // <-- replace
const char* password = "YOUR_PASSWORD"; // <-- replace

// IP address of the executor board (static or DHCP‑assigned)
const char* executorIP = "192.168.4.2"; // <-- adjust to your executor IP
const uint16_t executorPort = 4210;      // UDP port used by the executor

WiFiUDP udp;

void setup() {
  Serial.begin(115200);
  while (!Serial) {}
  Serial.println("[TX] Transmitter starting …");

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();
  Serial.print("[TX] Wi‑Fi connected, IP: ");
  Serial.println(WiFi.localIP());

  udp.begin(0); // any local port
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() == 0) return;

    // forward the command via UDP
    udp.beginPacket(executorIP, executorPort);
    udp.print(cmd);
    udp.endPacket();

    Serial.print("[TX] Sent → ");
    Serial.println(cmd);
  }
}
