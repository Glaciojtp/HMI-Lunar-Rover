/*
 * =====================================================================================
 *  TRANSMISOR ESP32 LOLIN C3 MINI / SUPERMINI — ROVER LUNAR V2.1 OFICIAL
 *  Puente USB-Serie a Transmision Inalambrica (HMI PC a Rover Rocker-Bogie 6x6)
 * =====================================================================================
 *  Hardware: ESP32-C3 SuperMini / LOLIN C3 Mini conectado por USB a la PC
 *  Comunicaciones soportadas:
 *    - Wi-Fi Nativo (Cliente STA + UDP) [MODO PREDETERMINADO]
 *    - NRF24L01+ (Radiofrecuencia 2.4 GHz SPI) [Modo de respaldo]
 *
 *  CARACTERISTICAS:
 *    - Compatible al 100% con HMI Python (HMI_Rover_V2.py) y HMI Rust (hmi-gui).
 *    - Baudios Serial USB: 115200.
 *    - Soporta Handshake activo "IDENT" -> "ID:ESP32_C3:TX:v2.1".
 *    - Streaming continuo a 20 Hz (cada 50 ms) y envio inmediato al recibir comando.
 * =====================================================================================
 */

#include <Arduino.h>

// ==========================================
// SELECCION DE MODO DE COMUNICACION
// 1 = Wi-Fi Nativo STA + UDP (Sin cables SPI ni modulos externos)
// 0 = Radiofrecuencia NRF24L01+ externa
// ==========================================
#define MODO_CONEXION_WIFI 1

#if MODO_CONEXION_WIFI
  #include <WiFi.h>
  #include <WiFiUdp.h>
  const char* TARGET_SSID = "ROVER_NET";
  const char* TARGET_PASS = "rover1234";
  const IPAddress IP_ROVER(192, 168, 4, 1);
  const unsigned int PUERTO_UDP = 4210;
  WiFiUDP udp;
#else
  #include <SPI.h>
  #include <RF24.h>
  #define PIN_CE   4
  #define PIN_CSN  7
  RF24 radio(PIN_CE, PIN_CSN);
  const byte DIRECCION_RF[6] = "ROVER";
#endif

// Estructura de transmision unificada (8 bytes empaquetados)
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255 (Lado Izquierdo: M1, M2, M3)
  int16_t traccion_der;  // -255 a 255 (Lado Derecho:   M4, M5, M6)
  uint8_t angulo_s1;     // S1: Delantero Izquierdo (10° a 170°)
  uint8_t angulo_s2;     // S2: Delantero Derecho   (10° a 170°)
  uint8_t angulo_s3;     // S3: Trasero Izquierdo   (10° a 170°)
  uint8_t angulo_s4;     // S4: Trasero Derecho     (10° a 170°)
};

PaqueteControl datosControl = {0, 0, 90, 90, 90, 90};

// Temporizadores no bloqueantes
unsigned long ultimoEnvio = 0;
const unsigned long INTERVALO_ENVIO_MS = 50; // 20 Hz continuo

// Buffer Serial no bloqueante
char bufferSerial[128];
byte indiceBuffer = 0;

void enviarPaqueteInalambrico() {
#if MODO_CONEXION_WIFI
  if (WiFi.status() == WL_CONNECTED) {
    udp.beginPacket(IP_ROVER, PUERTO_UDP);
    udp.write((const uint8_t*)&datosControl, sizeof(datosControl));
    udp.endPacket();
  }
#else
  radio.write(&datosControl, sizeof(datosControl));
#endif
}

void procesarComando(char* cmdStr) {
  String trama = String(cmdStr);
  trama.trim();
  if (trama.length() == 0) return;

  // Handshake de autodeteccion del perfil de hardware
  if (trama.equalsIgnoreCase("IDENT")) {
    Serial.println("ID:ESP32_C3:TX:v2.1");
    return;
  }
  if (trama.equalsIgnoreCase("PING")) {
    Serial.println("PONG:ESP32_C3_OK");
    return;
  }

  // Comando de Parada de Emergencia
  if (trama.equalsIgnoreCase("STOP") || trama.equalsIgnoreCase("PARAR") || trama.equals(" ")) {
    datosControl.traccion_izq = 0;
    datosControl.traccion_der = 0;
    datosControl.angulo_s1 = 90;
    datosControl.angulo_s2 = 90;
    datosControl.angulo_s3 = 90;
    datosControl.angulo_s4 = 90;
    enviarPaqueteInalambrico();
    Serial.println("STATUS:STOP");
    Serial.println("TLM_TX:0,0,90,90,90,90");
    Serial.println("[TX C3] Trac:[0,0] | S:[90,90,90,90]");
    return;
  }

  // Parseo de trama CSV
  // Formato HMI extendido: "CMD,PotIzq,PotDer,S1,S2,S3,S4"
  // Ejemplo: "W,150,150,90,90,90,90"
  int partes[7];
  int contadorPartes = 0;

  for (int i = 0; i < trama.length() && contadorPartes < 6; i++) {
    if (trama.charAt(i) == ',') {
      partes[contadorPartes++] = i;
    }
  }

  if (contadorPartes >= 6) {
    String cmd = trama.substring(0, partes[0]);
    cmd.toUpperCase();

    int potIzq = trama.substring(partes[0] + 1, partes[1]).toInt();
    int potDer = trama.substring(partes[1] + 1, partes[2]).toInt();
    int s1     = trama.substring(partes[2] + 1, partes[3]).toInt();
    int s2     = trama.substring(partes[3] + 1, partes[4]).toInt();
    int s3     = trama.substring(partes[4] + 1, partes[5]).toInt();
    int s4     = trama.substring(partes[5] + 1).toInt();

    datosControl.angulo_s1 = constrain(s1, 10, 170);
    datosControl.angulo_s2 = constrain(s2, 10, 170);
    datosControl.angulo_s3 = constrain(s3, 10, 170);
    datosControl.angulo_s4 = constrain(s4, 10, 170);

    if (cmd == "W") {
      datosControl.traccion_izq = potIzq;
      datosControl.traccion_der = potDer;
    } else if (cmd == "S") {
      datosControl.traccion_izq = -potIzq;
      datosControl.traccion_der = -potDer;
    } else if (cmd == "PIVOT_IZQ") {
      datosControl.traccion_izq = -potIzq;
      datosControl.traccion_der = potDer;
    } else if (cmd == "PIVOT_DER") {
      datosControl.traccion_izq = potIzq;
      datosControl.traccion_der = -potDer;
    } else if (cmd == "A" || cmd == "D" || cmd == "CRAB") {
      datosControl.traccion_izq = potIzq;
      datosControl.traccion_der = potDer;
    } else {
      datosControl.traccion_izq = 0;
      datosControl.traccion_der = 0;
    }

    enviarPaqueteInalambrico();

    static int16_t prevIzqTx = -999, prevDerTx = -999;
    static uint8_t prevS1Tx = 0, prevS2Tx = 0, prevS3Tx = 0, prevS4Tx = 0;
    if (datosControl.traccion_izq != prevIzqTx || datosControl.traccion_der != prevDerTx ||
        datosControl.angulo_s1 != prevS1Tx || datosControl.angulo_s2 != prevS2Tx ||
        datosControl.angulo_s3 != prevS3Tx || datosControl.angulo_s4 != prevS4Tx) {
      prevIzqTx = datosControl.traccion_izq; prevDerTx = datosControl.traccion_der;
      prevS1Tx = datosControl.angulo_s1; prevS2Tx = datosControl.angulo_s2;
      prevS3Tx = datosControl.angulo_s3; prevS4Tx = datosControl.angulo_s4;

      Serial.println("STATUS:OK_4SERVO");
      Serial.print("TLM_TX:");
      Serial.print(datosControl.traccion_izq); Serial.print(",");
      Serial.print(datosControl.traccion_der); Serial.print(",");
      Serial.print(datosControl.angulo_s1); Serial.print(",");
      Serial.print(datosControl.angulo_s2); Serial.print(",");
      Serial.print(datosControl.angulo_s3); Serial.print(",");
      Serial.println(datosControl.angulo_s4);

      Serial.print("[TX C3] Trac:[");
      Serial.print(datosControl.traccion_izq); Serial.print(",");
      Serial.print(datosControl.traccion_der); Serial.print("] | S:[");
      Serial.print(datosControl.angulo_s1); Serial.print(",");
      Serial.print(datosControl.angulo_s2); Serial.print(",");
      Serial.print(datosControl.angulo_s3); Serial.print(",");
      Serial.print(datosControl.angulo_s4); Serial.println("]");
    }
    return;
  }

#if MODO_CONEXION_WIFI
  // Reenvio transparente de comandos de calibracion y test al Rover por UDP
  if (WiFi.status() == WL_CONNECTED) {
    udp.beginPacket(IP_ROVER, PUERTO_UDP);
    udp.write((const uint8_t*)cmdStr, strlen(cmdStr));
    udp.endPacket();
    Serial.print("[TX C3 FWD] "); Serial.println(cmdStr);
  } else {
    Serial.println("[TX C3] Error: Wi-Fi desconectado, comando no enviado.");
  }
#endif
}

void leerSerialNoBloqueante() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (indiceBuffer > 0) {
        bufferSerial[indiceBuffer] = '\0';
        procesarComando(bufferSerial);
        indiceBuffer = 0;
      }
    } else {
      if (indiceBuffer < sizeof(bufferSerial) - 1) {
        bufferSerial[indiceBuffer++] = c;
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

#if MODO_CONEXION_WIFI
  WiFi.mode(WIFI_STA);
  WiFi.begin(TARGET_SSID, TARGET_PASS);
  udp.begin(0);

  Serial.println("SYS:ESP32_C3_WIFI_TX_READY");
#else
  SPI.begin(6, 5, 3, 7);

  if (!radio.begin()) {
    Serial.println("ERROR: NRF24L01 no detectado en ESP32.");
  } else {
    radio.setPayloadSize(sizeof(PaqueteControl));
    radio.setPALevel(RF24_PA_MAX);
    radio.setDataRate(RF24_250KBPS);
    radio.setChannel(108);
    radio.setAutoAck(false);
    radio.openWritingPipe(DIRECCION_RF);
    radio.stopListening();
    Serial.println("SYS:ESP32_TX_4SERVO_READY");
  }
#endif
}

void loop() {
  leerSerialNoBloqueante();

#if MODO_CONEXION_WIFI
  static bool wifiConectadoPrevio = false;
  if (WiFi.status() == WL_CONNECTED && !wifiConectadoPrevio) {
    wifiConectadoPrevio = true;
    Serial.print(F("SYS:WIFI_CONECTADO_IP="));
    Serial.println(WiFi.localIP());
  } else if (WiFi.status() != WL_CONNECTED && wifiConectadoPrevio) {
    wifiConectadoPrevio = false;
    Serial.println(F("WARN:WIFI_DESCONECTADO"));
  }

  // Gestion no bloqueante de reconexion Wi-Fi si se pierde el enlace
  static unsigned long ultimoIntentoWifi = 0;
  if (WiFi.status() != WL_CONNECTED && millis() - ultimoIntentoWifi > 3000) {
    ultimoIntentoWifi = millis();
    WiFi.disconnect();
    WiFi.begin(TARGET_SSID, TARGET_PASS);
  }
#endif

  // Envio continuo a 20 Hz
  if (millis() - ultimoEnvio >= INTERVALO_ENVIO_MS) {
    ultimoEnvio = millis();
    enviarPaqueteInalambrico();
  }

  // Ceder CPU y alimentar Task Watchdog del ESP32-C3
  delay(2);
}
