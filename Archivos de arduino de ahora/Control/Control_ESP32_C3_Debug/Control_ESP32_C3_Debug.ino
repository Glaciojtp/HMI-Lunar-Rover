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
 *    - LED:  GPIO 8 (LED azul integrado en la placa, activo en nivel BAJO)
 * =====================================================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>
#include <nRF24L01.h>
#include <stdarg.h>

// Definición de pines fijos
#define PIN_CE   4
#define PIN_CSN  7
#define PIN_LED  8

RF24 radio(PIN_CE, PIN_CSN);
const byte DIRECCION_RF[6] = "ROVER";

// Detección y compatibilidad con USB CDC Nativo y UART0
#if !ARDUINO_USB_CDC_ON_BOOT && (defined(USBCON) || SOC_USB_SERIAL_JTAG_SUPPORTED)
  #include <HWCDC.h>
  #define TIENE_USBSERIAL 1
#else
  #define TIENE_USBSERIAL 0
#endif

// Estructura estrictamente empaquetada (8 bytes exactos)
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
unsigned long ultimoParpadeoHeartbeat = 0;

// Contadores y métricas de diagnóstico
unsigned long contadorTotalEnvios = 0;
unsigned long contadorEnviosExitosos = 0;
unsigned long contadorEnviosFallidos = 0;
unsigned long ultimoTiempoTxMicros = 0;
bool radioOnline = false;

// Buffer Serial para comandos entrantes
char bufferSerial[128];
byte indiceBuffer = 0;

// Función de log universal que escribe simultáneamente a Serial y a USBSerial (si existe)
void logMsg(const char *format, ...) {
  char buf[256];
  va_list args;
  va_start(args, format);
  vsnprintf(buf, sizeof(buf), format, args);
  va_end(args);

  Serial.print(buf);
#if TIENE_USBSERIAL
  USBSerial.print(buf);
#endif
}

void volcarPaqueteHex(const PaqueteControl &p) {
  const uint8_t* bytes = (const uint8_t*)&p;
  logMsg("HEX:[ ");
  for (size_t i = 0; i < sizeof(PaqueteControl); i++) {
    if (bytes[i] < 0x10) logMsg("0");
    logMsg("%X ", bytes[i]);
  }
  logMsg("]");
}

void procesarComando(char* cmdStr) {
  String trama = String(cmdStr);
  trama.trim();
  if (trama.length() == 0) return;

  // Comando de Diagnóstico PING / STATUS desde HMI o monitor
  if (trama.equalsIgnoreCase("PING") || trama.equalsIgnoreCase("STATUS") || trama.equalsIgnoreCase("TEST")) {
    logMsg("PONG:ESP32_C3_SUPERMINI_OK | Radio:%s | Canal:108 | PktsTx:%lu | Exitos:%lu | Uptime:%lu s\n",
           radioOnline ? "ONLINE" : "ERROR", contadorTotalEnvios, contadorEnviosExitosos, millis() / 1000);
    return;
  }

  logMsg("[SERIAL_RX] (%d B): \"%s\"\n", trama.length(), trama.c_str());

  // Comando de Parada de Emergencia
  if (trama.equalsIgnoreCase("STOP") || trama.equalsIgnoreCase("PARAR") || trama.equals(" ")) {
    datosControl.traccion_izq = 0;
    datosControl.traccion_der = 0;
    datosControl.angulo_s1 = 90;
    datosControl.angulo_s2 = 90;
    datosControl.angulo_s3 = 90;
    datosControl.angulo_s4 = 90;
    logMsg("[PARSE_OK] STOP GENERAL -> Motores=0, Servos=90° (Centrados)\n");
    logMsg("STATUS:STOP\n");
    return;
  }

  // Contar comas para admitir formato completo de 4 servos (6 comas) o formato base (2 comas)
  int partes[7];
  int contadorComas = 0;

  for (int i = 0; i < (int)trama.length() && contadorComas < 6; i++) {
    if (trama.charAt(i) == ',') {
      partes[contadorComas++] = i;
    }
  }

  if (contadorComas >= 6) {
    // Formato extendido: "CMD,PotIzq,PotDer,S1,S2,S3,S4"
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

    logMsg("[PARSE_OK] CMD:%s | TracIzq:%d | TracDer:%d | S:[%d,%d,%d,%d] | ",
           cmd.c_str(), datosControl.traccion_izq, datosControl.traccion_der,
           datosControl.angulo_s1, datosControl.angulo_s2, datosControl.angulo_s3, datosControl.angulo_s4);
    volcarPaqueteHex(datosControl);
    logMsg("\nSTATUS:OK_4SERVO\n");

  } else if (contadorComas >= 2) {
    // Formato base: "CMD,PotIzq,PotDer"
    String cmd = trama.substring(0, partes[0]);
    cmd.toUpperCase();
    int potIzq = trama.substring(partes[0] + 1, partes[1]).toInt();
    int potDer = trama.substring(partes[1] + 1).toInt();

    if (cmd == "W") {
      datosControl.traccion_izq = potIzq; datosControl.traccion_der = potDer;
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
      datosControl.angulo_s3 = 90; datosControl.angulo_s4 = 90;
    } else if (cmd == "S") {
      datosControl.traccion_izq = -potIzq; datosControl.traccion_der = -potDer;
      datosControl.angulo_s1 = 90; datosControl.angulo_s2 = 90;
      datosControl.angulo_s3 = 90; datosControl.angulo_s4 = 90;
    } else if (cmd == "A") {
      datosControl.traccion_izq = potIzq; datosControl.traccion_der = potDer;
      datosControl.angulo_s1 = 120; datosControl.angulo_s2 = 120;
      datosControl.angulo_s3 = 60;  datosControl.angulo_s4 = 60;
    } else if (cmd == "D") {
      datosControl.traccion_izq = potIzq; datosControl.traccion_der = potDer;
      datosControl.angulo_s1 = 60;  datosControl.angulo_s2 = 60;
      datosControl.angulo_s3 = 120; datosControl.angulo_s4 = 120;
    } else {
      datosControl.traccion_izq = 0; datosControl.traccion_der = 0;
    }

    logMsg("[PARSE_OK_BASE] CMD:%s | TracIzq:%d | TracDer:%d | ",
           cmd.c_str(), datosControl.traccion_izq, datosControl.traccion_der);
    volcarPaqueteHex(datosControl);
    logMsg("\nSTATUS:OK_BASE\n");
  } else {
    logMsg("[PARSE_WARN] Trama con formato desconocido: \"%s\"\n", trama.c_str());
  }
}

void procesarCharEntrante(char c) {
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

void leerSerialNoBloqueante() {
  while (Serial.available() > 0) {
    procesarCharEntrante(Serial.read());
  }
#if TIENE_USBSERIAL
  while (USBSerial.available() > 0) {
    procesarCharEntrante(USBSerial.read());
  }
#endif
}

void setup() {
  // Configuración de pin LED integrado (GPIO 8)
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW); // Enciende LED durante arranque (activo en LOW)

  // Inicializar puertos Seriales (Hardware y USB CDC)
  Serial.begin(115200);
#if TIENE_USBSERIAL
  USBSerial.begin(115200);
#endif

  delay(500);

  logMsg("\n===============================================================\n");
  logMsg("🛰️ TRANSMISOR ESP32-C3 SUPERMINI — DEBUG & TELEMETRIA ACTIVA\n");
  logMsg("===============================================================\n");
  logMsg("ESP32 Chip Model: %s | Rev: %d | Cores: %d\n", ESP.getChipModel(), ESP.getChipRevision(), ESP.getChipCores());
  logMsg("CPU Freq: %d MHz | Free Heap: %d Bytes\n", getCpuFrequencyMhz(), ESP.getFreeHeap());
  logMsg("Pines NRF24: CE=GPIO 4 | CSN=GPIO 7 | SCK=GPIO 6 | MOSI=GPIO 3 | MISO=GPIO 5\n");

  pinMode(PIN_CE, OUTPUT);
  pinMode(PIN_CSN, OUTPUT);
  digitalWrite(PIN_CSN, HIGH);
  digitalWrite(PIN_CE, LOW);

  // Iniciar bus SPI en pines especificados en AGENTS.md
  SPI.begin(6, 5, 3, 7); // SCK=6, MISO=5, MOSI=3, CSN=7
  delay(50);

  logMsg("Iniciando transceptor NRF24L01+...\n");
  if (!radio.begin()) {
    logMsg("❌ ERROR FATAL: radio.begin() fallo. El modulo NRF24L01 no responde.\n");
    logMsg("   -> Verifique alimentacion 3.3V (¡NUNCA 5V!)\n");
    logMsg("   -> Verifique capacitor de 10uF-100uF entre VCC y GND de la radio\n");
    logMsg("   -> Verifique conexion de pines CE(4), CSN(7), SCK(6), MOSI(3), MISO(5)\n");
    radioOnline = false;
  } else {
    radioOnline = true;
    radio.setPayloadSize(sizeof(PaqueteControl)); // 8 bytes exactos
    radio.enableDynamicPayloads();                // Habilitar dynamic payloads
    radio.setPALevel(RF24_PA_LOW);               // Nivel LOW para banco de pruebas (evita saturación LNA)
    radio.setDataRate(RF24_250KBPS);
    radio.setChannel(108);
    radio.setAutoAck(true);
    radio.setRetries(5, 15);
    radio.openWritingPipe(DIRECCION_RF);
    radio.stopListening();

    logMsg("✅ NRF24L01 detectado e inicializado correctamente.\n");
    logMsg("   -> Chip conectado?: %s\n", radio.isChipConnected() ? "SI (SPI Hardware OK)" : "NO (Falso contacto)");
    logMsg("   -> Canal RF: 108 (2.508 GHz) | Data Rate: 250 KBPS\n");
    logMsg("   -> Potencia: RF24_PA_LOW (Banco de pruebas)\n");
    logMsg("   -> Auto-ACK: Habilitado (Retries: 5 delay / 15 intentos)\n");
    logMsg("   -> Direccion Pipe TX: \"ROVER\"\n");
    logMsg("   -> Tamano de paquete: %d Bytes\n", sizeof(PaqueteControl));
  }

  digitalWrite(PIN_LED, HIGH); // Apaga LED indicando arranque completado
  logMsg("===============================================================\n");
  logMsg("Listo para recibir comandos por puerto Serial USB.\n");
  logMsg("===============================================================\n");
}

void loop() {
  leerSerialNoBloqueante();

  unsigned long ahora = millis();

  // Transmisión periódica a 20 Hz
  if (ahora - ultimoEnvioRF >= INTERVALO_RF_MS) {
    ultimoEnvioRF = ahora;
    contadorTotalEnvios++;

    if (radioOnline) {
      digitalWrite(PIN_LED, LOW); // Breve destello LED en TX
      unsigned long tInicio = micros();
      bool exito = radio.write(&datosControl, sizeof(datosControl));
      unsigned long tFin = micros();
      digitalWrite(PIN_LED, HIGH);
      ultimoTiempoTxMicros = tFin - tInicio;

      if (exito) {
        contadorEnviosExitosos++;
      } else {
        contadorEnviosFallidos++;
        logMsg("[RF_WARN] Fallo transmision paquete #%lu (sin ACK del MKR)\n", contadorTotalEnvios);
      }
    }
  }

  // Reporte periódico de estadísticas a 1 Hz
  if (ahora - ultimoReporteStats >= INTERVALO_STATS_MS) {
    ultimoReporteStats = ahora;
    float tasaExito = (contadorTotalEnvios > 0) ? ((float)contadorEnviosExitosos / contadorTotalEnvios * 100.0) : 0.0;

    logMsg("[STATS_TX] Tot:%lu | OK:%lu | Fail:%lu | Tasa:%.1f%% | dt:%lu us | ",
           contadorTotalEnvios, contadorEnviosExitosos, contadorEnviosFallidos, tasaExito, ultimoTiempoTxMicros);
    volcarPaqueteHex(datosControl);
    logMsg("\n");
  }

  // Si la radio falló al arrancar, parpadear LED en patrón de alerta continuo
  if (!radioOnline) {
    if (ahora - ultimoParpadeoHeartbeat >= 200) {
      ultimoParpadeoHeartbeat = ahora;
      digitalWrite(PIN_LED, !digitalRead(PIN_LED));
    }
  }
}
