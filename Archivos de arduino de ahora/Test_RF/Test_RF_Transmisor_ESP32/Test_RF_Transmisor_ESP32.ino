/*
 * =====================================================================================
 *  TEST RF TRANSMISOR — ESP32-C3 SUPERMINI / LOLIN C3 MINI
 *  Rover Lunar V2.0 — Prueba de enlace por Monitor Serie (100% independiente de Python)
 * =====================================================================================
 *  Conexión física del módulo NRF24L01+ al ESP32-C3:
 *    - VCC:  3.3V (¡NUNCA 5V! Con capacitor 10uF - 100uF a GND)
 *    - GND:  GND común
 *    - CE:   GPIO 4
 *    - CSN:  GPIO 7
 *    - SCK:  GPIO 6
 *    - MOSI: GPIO 3
 *    - MISO: GPIO 5
 *    - LED:  GPIO 8 (LED azul en placa, activo en LOW)
 * =====================================================================================
 *  Instrucciones:
 *    1. Subir al ESP32-C3 con Arduino IDE (Herramientas -> USB CDC On Boot: "Enabled").
 *    2. Abrir Monitor Serie de Arduino IDE a 115200 baudios (ajustar a "Ambos NL y CR").
 *    3. Escribir comandos en el monitor:
 *         'w' -> Avance (PWM 200, Servos 90°)
 *         's' -> Reversa (PWM -200, Servos 90°)
 *         'a' -> Giro Izquierda (PWM 150, Servos 120°)
 *         'd' -> Giro Derecha (PWM 150, Servos 60°)
 *         'x' -> Parada (PWM 0, Servos 90°)
 *         'p' -> Alternar potencia (LOW <-> MAX)
 * =====================================================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>
#include <nRF24L01.h>
#include <stdarg.h>

#define PIN_CE   4
#define PIN_CSN  7
#define PIN_LED  8

RF24 radio(PIN_CE, PIN_CSN);
const byte DIRECCION_RF[6] = "ROVER";

// Compatibilidad con USB CDC Nativo y UART0
#if !ARDUINO_USB_CDC_ON_BOOT && (defined(USBCON) || SOC_USB_SERIAL_JTAG_SUPPORTED)
  #include <HWCDC.h>
  #define TIENE_USBSERIAL 1
#else
  #define TIENE_USBSERIAL 0
#endif

// Trama unificada de 6 bytes según AGENTS.md
struct __attribute__((packed)) PaqueteRover {
  int16_t traccion_izq;  // -255 a 255
  int16_t traccion_der;  // -255 a 255
  uint8_t angulo_s1;     // 10 a 170
  uint8_t angulo_s2;     // 10 a 170
};

PaqueteRover datosPrueba = {0, 0, 90, 90};

unsigned long contadorEnvios = 0;
unsigned long contadorExitos = 0;
unsigned long contadorFallos = 0;
unsigned long ultimoEnvioAuto = 0;
const unsigned long INTERVALO_AUTO_MS = 1000; // Envío automático cada 1 seg

bool radioOk = false;
bool potenciaAlta = false;

void imprimir(const char *format, ...) {
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

void enviarTramaRF() {
  contadorEnvios++;

  digitalWrite(PIN_LED, LOW); // Destello LED azul (activo en LOW)
  unsigned long t0 = micros();
  bool exito = radio.write(&datosPrueba, sizeof(datosPrueba));
  unsigned long dt = micros() - t0;
  digitalWrite(PIN_LED, HIGH);

  if (exito) {
    contadorExitos++;
    imprimir("   ✅ [TX #%lu OK] ACK recibido del MKR! (dt: %lu us) | Trac:[%d, %d] | S:[%d, %d]\n",
             contadorEnvios, dt, datosPrueba.traccion_izq, datosPrueba.traccion_der,
             datosPrueba.angulo_s1, datosPrueba.angulo_s2);
  } else {
    contadorFallos++;
    imprimir("   ❌ [TX #%lu FALLO] Sin ACK del MKR (dt: %lu us) | ¿MKR encendido y en canal 108?\n",
             contadorEnvios, dt);
  }
}

void procesarEntradaUsuario(char c) {
  c = tolower(c);
  if (c == '\r' || c == '\n' || c == ' ') return;

  imprimir("\n[TECLADO] Comando recibido: '%c' -> ", c);

  if (c == 'w') {
    datosPrueba.traccion_izq = 200;
    datosPrueba.traccion_der = 200;
    datosPrueba.angulo_s1 = 90;
    datosPrueba.angulo_s2 = 90;
    imprimir("AVANCE ADELANTE (PWM: 200, Servos: 90°)\n");
  } else if (c == 's') {
    datosPrueba.traccion_izq = -200;
    datosPrueba.traccion_der = -200;
    datosPrueba.angulo_s1 = 90;
    datosPrueba.angulo_s2 = 90;
    imprimir("REVERSA (PWM: -200, Servos: 90°)\n");
  } else if (c == 'a') {
    datosPrueba.traccion_izq = 150;
    datosPrueba.traccion_der = 150;
    datosPrueba.angulo_s1 = 120;
    datosPrueba.angulo_s2 = 120;
    imprimir("GIRO IZQUIERDA (PWM: 150, Servos: 120°)\n");
  } else if (c == 'd') {
    datosPrueba.traccion_izq = 150;
    datosPrueba.traccion_der = 150;
    datosPrueba.angulo_s1 = 60;
    datosPrueba.angulo_s2 = 60;
    imprimir("GIRO DERECHA (PWM: 150, Servos: 60°)\n");
  } else if (c == 'x') {
    datosPrueba.traccion_izq = 0;
    datosPrueba.traccion_der = 0;
    datosPrueba.angulo_s1 = 90;
    datosPrueba.angulo_s2 = 90;
    imprimir("PARADA (PWM: 0, Servos: 90°)\n");
  } else if (c == 'p') {
    potenciaAlta = !potenciaAlta;
    radio.setPALevel(potenciaAlta ? RF24_PA_MAX : RF24_PA_LOW);
    imprimir("POTENCIA CAMBIADA A: %s\n", potenciaAlta ? "RF24_PA_MAX (Máximo alcance)" : "RF24_PA_LOW (Banco de trabajo)");
    return;
  } else {
    imprimir("Comando no reconocido. Use w, s, a, d, x, p.\n");
    return;
  }

  // Enviar inmediatamente tras pulsar la tecla
  enviarTramaRF();
}

void setup() {
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW); // LED ON al arrancar

  Serial.begin(115200);
#if TIENE_USBSERIAL
  USBSerial.begin(115200);
#endif

  // Espera para dar tiempo a abrir el Monitor Serie
  delay(1000);

  imprimir("\n\n");
  imprimir("=================================================================\n");
  imprimir("🛰️  TEST RF TRANSMISOR — ESP32-C3 SUPERMINI (MONITOR SERIE)     \n");
  imprimir("=================================================================\n");
  imprimir("ESP32 Chip: %s | Rev: %d | Frecuencia: %d MHz\n",
           ESP.getChipModel(), ESP.getChipRevision(), getCpuFrequencyMhz());
  imprimir("Iniciando bus SPI (SCK=6, MISO=5, MOSI=3, CSN=7, CE=4)...\n");

  pinMode(PIN_CE, OUTPUT);
  pinMode(PIN_CSN, OUTPUT);
  digitalWrite(PIN_CSN, HIGH);
  digitalWrite(PIN_CE, LOW);

  SPI.begin(6, 5, 3, 7);
  delay(100);

  imprimir("Iniciando radio NRF24L01+...\n");
  if (!radio.begin()) {
    imprimir("❌ ERROR GRAVE: radio.begin() retorno FALSE.\n");
    imprimir("   -> Compruebe conexion a 3.3V (¡NUNCA 5V!)\n");
    imprimir("   -> Compruebe capacitor 10uF-100uF entre VCC y GND del NRF24\n");
    imprimir("   -> Compruebe pines: CE(GPIO4), CSN(GPIO7), SCK(GPIO6), MOSI(GPIO3), MISO(GPIO5)\n");
    radioOk = false;
  } else {
    radioOk = true;
    radio.setPayloadSize(sizeof(PaqueteRover)); // 6 bytes exactos
    radio.setPALevel(RF24_PA_LOW);              // LOW para evitar saturación en mesa
    radio.setDataRate(RF24_250KBPS);            // 250 kbps
    radio.setChannel(108);                      // Canal 108 (2.508 GHz)
    radio.setAutoAck(true);                     // Esperar confirmación ACK
    radio.setRetries(5, 15);                    // 5x250us delay, 15 reintentos
    radio.openWritingPipe(DIRECCION_RF);        // Pipe "ROVER"
    radio.stopListening();                      // Modo Transmisor

    imprimir("✅ NRF24L01 detectado y configurado correctamente!\n");
    imprimir("   -> Chip Conectado?: %s\n", radio.isChipConnected() ? "SI (SPI Hardware OK)" : "NO (Revisar cables)");
    imprimir("   -> Canal: 108 | Velocidad: 250 KBPS | Potencia: RF24_PA_LOW\n");
    imprimir("   -> Direccion Pipe TX: \"ROVER\" | Paquete: %d Bytes\n", sizeof(PaqueteRover));
    imprimir("-----------------------------------------------------------------\n");
    imprimir("Escriba en este monitor: 'w', 's', 'a', 'd', 'x' para comandar.\n");
    imprimir("Se enviara un paquete automatico cada 1 segundo.\n");
    imprimir("=================================================================\n\n");
  }

  digitalWrite(PIN_LED, HIGH); // LED OFF (listo)
}

void loop() {
  // Leer caracteres desde el Monitor Serie de Arduino IDE
  while (Serial.available() > 0) {
    procesarEntradaUsuario(Serial.read());
  }
#if TIENE_USBSERIAL
  while (USBSerial.available() > 0) {
    procesarEntradaUsuario(USBSerial.read());
  }
#endif

  unsigned long ahora = millis();

  // Envío periódico automático de prueba a 1 Hz
  if (radioOk && (ahora - ultimoEnvioAuto >= INTERVALO_AUTO_MS)) {
    ultimoEnvioAuto = ahora;
    enviarTramaRF();
  }

  // Si la radio falló físicamente, parpadear rápido el LED de la placa
  if (!radioOk) {
    digitalWrite(PIN_LED, (millis() / 200) % 2);
  }
}
