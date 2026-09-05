/*
 * =====================================================================================
 *  TRANSMISOR ESP32-C3 LOLIN / SUPERMINI — VERSION DE DEPURACION Y TELEMETRIA (DEBUG)
 *  Rover Lunar V2.0 (Rocker-Bogie 6x6: 6 Motores + 4 Servos Independientes)
 * =====================================================================================
 *  Hardware: ESP32-C3 SuperMini + Transceptor NRF24L01+
 *  Pines SPI Hardware:
 *    - CE:   GPIO 4
 *    - CSN:  GPIO 7
 *    - SCK:  GPIO 6
 *    - MOSI: GPIO 3
 *    - MISO: GPIO 5
 * =====================================================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>
#include <nRF24L01.h>
#include <printf.h>

#define PIN_CE   4
#define PIN_CSN  7

RF24 radio(PIN_CE, PIN_CSN);
const byte DIRECCION_RF[6] = "ROVER";

// Estructura estrictamente empaquetada (8 bytes)
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255 (Lado Izquierdo: M1, M2, M3)
  int16_t traccion_der;  // -255 a 255 (Lado Derecho:   M4, M5, M6)
  uint8_t angulo_s1;     // S1: Delantero Izquierdo (10° a 170°)
  uint8_t angulo_s2;     // S2: Delantero Derecho   (10° a 170°)
  uint8_t angulo_s3;     // S3: Trasero Izquierdo   (10° a 170°)
  uint8_t angulo_s4;     // S4: Trasero Derecho     (10° a 170°)
};

PaqueteControl datosControl = {0, 0, 90, 90, 90, 90};

// Temporizadores y cadencia
unsigned long ultimoEnvioRF = 0;
const unsigned long INTERVALO_RF_MS = 50; // 20 Hz
unsigned long ultimoReporteStats = 0;
const unsigned long INTERVALO_STATS_MS = 1000; // 1 Hz para resumen

// Contadores y métricas de diagnóstico
unsigned long contadorTotalEnvios = 0;
unsigned long contadorEnviosExitosos = 0;
unsigned long contadorEnviosFallidos = 0;
unsigned long tiempoTotalTxMicros = 0;
unsigned long ultimoTiempoTxMicros = 0;
bool radioOnline = false;

// Buffer Serial para comandos entrantes
char bufferSerial[128];
byte indiceBuffer = 0;

void volcarPaqueteHex(const PaqueteControl &p) {
  const uint8_t* bytes = (const uint8_t*)&p;
  Serial.print("HEX:[ ");
  for (size_t i = 0; i < sizeof(PaqueteControl); i++) {
    if (bytes[i] < 0x10) Serial.print("0");
    Serial.print(bytes[i], HEX);
    Serial.print(" ");
  }
  Serial.print("]");
}

void procesarComando(char* cmdStr) {
  String trama = String(cmdStr);
  trama.trim();
  if (trama.length() == 0) return;

  Serial.print("[SERIAL_RX] (");
  Serial.print(trama.length());
  Serial.print(" B): \"");
  Serial.print(trama);
  Serial.println("\"");

  // Comando de Parada de Emergencia
  if (trama.equalsIgnoreCase("STOP") || trama.equalsIgnoreCase("PARAR") || trama.equals(" ")) {
    datosControl.traccion_izq = 0;
    datosControl.traccion_der = 0;
    datosControl.angulo_s1 = 90;
    datosControl.angulo_s2 = 90;
    datosControl.angulo_s3 = 90;
    datosControl.angulo_s4 = 90;
    Serial.println("[PARSE_OK] STOP GENERAL -> Motores=0, Servos=90° (Centrados)");
    Serial.println("STATUS:STOP");
    return;
  }

  // Parseo de trama CSV extendida: "CMD,PotIzq,PotDer,S1,S2,S3,S4"
  int partes[7];
  int contadorComas = 0;

  for (int i = 0; i < trama.length() && contadorComas < 6; i++) {
    if (trama.charAt(i) == ',') {
      partes[contadorComas++] = i;
    }
  }

  if (contadorComas >= 6) {
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

    Serial.print("[PARSE_OK] CMD: ");
    Serial.print(cmd);
    Serial.print(" | PWM_Izq: ");
    Serial.print(datosControl.traccion_izq);
    Serial.print(" | PWM_Der: ");
    Serial.print(datosControl.traccion_der);
    Serial.print(" | S1:");
    Serial.print(datosControl.angulo_s1);
    Serial.print("° S2:");
    Serial.print(datosControl.angulo_s2);
    Serial.print("° S3:");
    Serial.print(datosControl.angulo_s3);
    Serial.print("° S4:");
    Serial.print(datosControl.angulo_s4);
    Serial.print("° | ");
    volcarPaqueteHex(datosControl);
    Serial.println();

    Serial.println("STATUS:OK_4SERVO");
  } else {
    Serial.print("[PARSE_WARN] Trama con formato invalido (se esperaban 6 comas): \"");
    Serial.print(trama);
    Serial.println("\"");
  }
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
  setCpuFrequencyMhz(80);
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("===============================================================");
  Serial.println("🛰️ TRANSMISOR ESP32-C3 SUPERMINI — DEBUG & TELEMETRIA ACTIVA");
  Serial.println("===============================================================");
  Serial.printf("ESP32 Chip Model: %s | Rev: %d | Cores: %d\n", ESP.getChipModel(), ESP.getChipRevision(), ESP.getChipCores());
  Serial.printf("CPU Freq: %d MHz | Free Heap: %d Bytes\n", getCpuFrequencyMhz(), ESP.getFreeHeap());
  Serial.println("Configurando SPI: SCK=GPIO 6, MISO=GPIO 5, MOSI=GPIO 3, CSN=GPIO 7...");

  SPI.begin(6, 5, 3, 7);

  Serial.println("Iniciando transceptor NRF24L01+...");
  if (!radio.begin()) {
    Serial.println("❌ ERROR FATAL: radio.begin() fallo. El modulo NRF24L01 no responde.");
    Serial.println("   -> Verifique alimentacion 3.3V (NUNCA 5V)");
    Serial.println("   -> Verifique capacitor de 10uF-100uF entre VCC y GND de la radio");
    Serial.println("   -> Verifique conexion de pines CE(4), CSN(7), SCK(6), MOSI(3), MISO(5)");
    radioOnline = false;
  } else {
    radioOnline = true;
    radio.setPALevel(RF24_PA_MAX);
    radio.setDataRate(RF24_250KBPS);
    radio.setChannel(108);
    radio.setAutoAck(true);
    radio.setRetries(5, 15);
    radio.openWritingPipe(DIRECCION_RF);
    radio.stopListening();

    Serial.println("✅ NRF24L01 detectado e inicializado correctamente.");
    Serial.print("   -> Chip conectado?: ");
    Serial.println(radio.isChipConnected() ? "SI (Comunicacion SPI OK)" : "NO (Posible falso contacto)");
    Serial.println("   -> Canal RF: 108 (2.508 GHz)");
    Serial.println("   -> Data Rate: 250 KBPS (Max sensibilidad)");
    Serial.println("   -> Potencia: RF24_PA_MAX");
    Serial.println("   -> Auto-ACK: Habilitado (Retries: 5 delay / 15 intentos)");
    Serial.println("   -> Direccion Pipe TX: \"ROVER\"");
    Serial.printf("   -> Tamano de paquete: %d Bytes\n", sizeof(PaqueteControl));
  }

  Serial.println("===============================================================");
  Serial.println("Listo para recibir comandos por puerto Serial.");
  Serial.println("===============================================================");
}

void loop() {
  leerSerialNoBloqueante();

  unsigned long ahora = millis();

  if (ahora - ultimoEnvioRF >= INTERVALO_RF_MS) {
    ultimoEnvioRF = ahora;
    contadorTotalEnvios++;

    if (radioOnline) {
      unsigned long tInicio = micros();
      bool exito = radio.write(&datosControl, sizeof(datosControl));
      unsigned long tFin = micros();
      ultimoTiempoTxMicros = tFin - tInicio;

      if (exito) {
        contadorEnviosExitosos++;
      } else {
        contadorEnviosFallidos++;
        // Advertencia en consola de fallo de paquete
        Serial.printf("[RF_WARN] Fallo transmision paquete #%lu (sin ACK receptor)\n", contadorTotalEnvios);
      }
    }
  }

  // Reporte periodico de estadisticas a 1 Hz
  if (ahora - ultimoReporteStats >= INTERVALO_STATS_MS) {
    ultimoReporteStats = ahora;
    float tasaExito = (contadorTotalEnvios > 0) ? ((float)contadorEnviosExitosos / contadorTotalEnvios * 100.0) : 0.0;

    Serial.printf("[STATS_TX] Tot:%lu | OK:%lu | Fail:%lu | Tasa:%.1f%% | Ultimo_dt:%lu us | ",
                  contadorTotalEnvios, contadorEnviosExitosos, contadorEnviosFallidos, tasaExito, ultimoTiempoTxMicros);
    volcarPaqueteHex(datosControl);
    Serial.println();
  }
}
