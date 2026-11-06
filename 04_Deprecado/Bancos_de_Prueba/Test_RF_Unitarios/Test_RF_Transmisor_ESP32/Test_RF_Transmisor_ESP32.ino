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
 *  Comandos interactivos desde Monitor Serie (115200 baudios):
 *    'w' -> Avance (PWM 200, Servos 90°)
 *    's' -> Reversa (PWM -200, Servos 90°)
 *    'a' -> Giro Izquierda (PWM 150, Servos 120°)
 *    'd' -> Giro Derecha (PWM 150, Servos 60°)
 *    'x' -> Parada (PWM 0, Servos 90°)
 *    'k' -> Alternar Auto-ACK (ON / OFF)
 *    '1' -> Cambiar velocidad a 1 MBPS
 *    '2' -> Cambiar velocidad a 250 KBPS (por defecto)
 *    'c' -> Cambiar canal RF (108 <-> 76 <-> 90)
 *    'p' -> Alternar potencia (LOW <-> MAX)
 *    'm' -> Alternar envío periódico automático de 1 Hz (ON / OFF)
 *    '?' -> Imprimir configuración actual y menú de ayuda
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
bool envioAutoHabilitado = true;

bool radioOk = false;

// Opciones dinámicas de RF
bool autoAckHabilitado = true;
uint8_t canalActual = 108;
rf24_datarate_e datarateActual = RF24_250KBPS;
rf24_pa_dbm_e paActual = RF24_PA_LOW;

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

void imprimirConfiguracion() {
  imprimir("\n---------------- CONFIGURACION ACTUAL TRANSMISOR ESP32 ----------------\n");
  imprimir("   Chip Conectado?: %s\n", radio.isChipConnected() ? "SI (SPI OK)" : "NO (¡REVISAR CABLES!)");
  imprimir("   Canal RF:        %d (%d MHz)\n", canalActual, 2400 + canalActual);
  imprimir("   Velocidad:       %s\n", datarateActual == RF24_250KBPS ? "250 KBPS" : "1 MBPS");
  imprimir("   Auto-ACK:        %s\n", autoAckHabilitado ? "HABILITADO" : "DESHABILITADO (Broadcast)");
  imprimir("   Potencia PA:     %s\n", paActual == RF24_PA_LOW ? "RF24_PA_LOW (Banco)" : "RF24_PA_MAX");
  imprimir("   Tamano Trama:    %d Bytes FIJOS (Dynamic Payloads: OFF)\n", sizeof(PaqueteRover));
  imprimir("   Pipe TX:         \"ROVER\"\n");
  imprimir("   Envio Auto 1Hz:  %s\n", envioAutoHabilitado ? "ACTIVO" : "PAUSADO");
  imprimir("   Estadisticas:    Total TX:%lu | Exitos (ACK):%lu | Fallos:%lu\n",
           contadorEnvios, contadorExitos, contadorFallos);
  imprimir("---------------- COMANDOS DISPONIBLES EN CONSOLA ----------------------\n");
  imprimir("   'w','s','a','d','x' -> Conducir Rover\n");
  imprimir("   'k' -> Toggle Auto-ACK | '1' -> 1 Mbps | '2' -> 250 Kbps\n");
  imprimir("   'c' -> Rotar Canal     | 'p' -> Toggle PA Potencia\n");
  imprimir("   'm' -> Toggle Auto-TX  | '?' -> Ver este menu\n");
  imprimir("-----------------------------------------------------------------------\n\n");
}

void reconfigurarRadio() {
  radio.setChannel(canalActual);
  radio.setDataRate(datarateActual);
  radio.setPALevel(paActual);
  radio.setAutoAck(autoAckHabilitado);
  radio.setPayloadSize(sizeof(PaqueteRover));
  // A 250kbps el delay de reintento debe ser >= 1500us; usamos 15*250us = 4000us para evitar colisiones con ACK
  radio.setRetries(15, 15);
  radio.openWritingPipe(DIRECCION_RF);
  radio.stopListening();
}

void enviarTramaRF() {
  contadorEnvios++;

  digitalWrite(PIN_LED, LOW); // Destello LED azul (activo en LOW)
  unsigned long t0 = micros();
  bool exito = radio.write(&datosPrueba, sizeof(datosPrueba));
  unsigned long dt = micros() - t0;
  digitalWrite(PIN_LED, HIGH);

  if (autoAckHabilitado) {
    if (exito) {
      contadorExitos++;
      imprimir("   ✅ [TX #%lu OK] ACK recibido del MKR! (dt: %lu us) | Trac:[%d, %d] | S:[%d, %d]\n",
               contadorEnvios, dt, datosPrueba.traccion_izq, datosPrueba.traccion_der,
               datosPrueba.angulo_s1, datosPrueba.angulo_s2);
    } else {
      contadorFallos++;
      imprimir("   ❌ [TX #%lu FALLO] Sin ACK del MKR (dt: %lu us) | ¿MKR encendido y en canal %d?\n"
               "      -> Tip: Si el MKR no responde con ACK, presione 'k' en ambos monitores para probar enlace sin ACK,\n"
               "              o presione '1' en ambos para probar 1 Mbps (modo nativo de clones Si24R1).\n",
               contadorEnvios, dt, canalActual);
    }
  } else {
    contadorExitos++;
    imprimir("   📡 [TX #%lu ENVIADO] Transmitido sin esperar ACK (dt: %lu us) | Trac:[%d, %d] | S:[%d, %d]\n",
             contadorEnvios, dt, datosPrueba.traccion_izq, datosPrueba.traccion_der,
             datosPrueba.angulo_s1, datosPrueba.angulo_s2);
  }
}

void procesarEntradaUsuario(char c) {
  c = tolower(c);
  if (c == '\r' || c == '\n' || c == ' ') return;

  if (c == 'w') {
    datosPrueba.traccion_izq = 200;
    datosPrueba.traccion_der = 200;
    datosPrueba.angulo_s1 = 90;
    datosPrueba.angulo_s2 = 90;
    imprimir("\n[TECLADO] 'w' -> AVANCE ADELANTE (PWM: 200, Servos: 90°)\n");
    enviarTramaRF();
  } else if (c == 's') {
    datosPrueba.traccion_izq = -200;
    datosPrueba.traccion_der = -200;
    datosPrueba.angulo_s1 = 90;
    datosPrueba.angulo_s2 = 90;
    imprimir("\n[TECLADO] 's' -> REVERSA (PWM: -200, Servos: 90°)\n");
    enviarTramaRF();
  } else if (c == 'a') {
    datosPrueba.traccion_izq = 150;
    datosPrueba.traccion_der = 150;
    datosPrueba.angulo_s1 = 120;
    datosPrueba.angulo_s2 = 120;
    imprimir("\n[TECLADO] 'a' -> GIRO IZQUIERDA (PWM: 150, Servos: 120°)\n");
    enviarTramaRF();
  } else if (c == 'd') {
    datosPrueba.traccion_izq = 150;
    datosPrueba.traccion_der = 150;
    datosPrueba.angulo_s1 = 60;
    datosPrueba.angulo_s2 = 60;
    imprimir("\n[TECLADO] 'd' -> GIRO DERECHA (PWM: 150, Servos: 60°)\n");
    enviarTramaRF();
  } else if (c == 'x') {
    datosPrueba.traccion_izq = 0;
    datosPrueba.traccion_der = 0;
    datosPrueba.angulo_s1 = 90;
    datosPrueba.angulo_s2 = 90;
    imprimir("\n[TECLADO] 'x' -> PARADA (PWM: 0, Servos: 90°)\n");
    enviarTramaRF();
  } else if (c == 'k') {
    autoAckHabilitado = !autoAckHabilitado;
    reconfigurarRadio();
    imprimir("\n[CONFIG] Auto-ACK cambiado a: %s\n", autoAckHabilitado ? "HABILITADO (Espera confirmacion)" : "DESHABILITADO (Transmision ciega)");
  } else if (c == '1') {
    datarateActual = RF24_1MBPS;
    reconfigurarRadio();
    imprimir("\n[CONFIG] Velocidad cambiada a: 1 MBPS (Mayor compatibilidad con clones Si24R1)\n");
  } else if (c == '2') {
    datarateActual = RF24_250KBPS;
    reconfigurarRadio();
    imprimir("\n[CONFIG] Velocidad cambiada a: 250 KBPS (Mayor alcance y sensibilidad)\n");
  } else if (c == 'c') {
    if (canalActual == 108) canalActual = 76;
    else if (canalActual == 76) canalActual = 90;
    else canalActual = 108;
    reconfigurarRadio();
    imprimir("\n[CONFIG] Canal RF cambiado a: %d (%d MHz)\n", canalActual, 2400 + canalActual);
  } else if (c == 'p') {
    paActual = (paActual == RF24_PA_LOW) ? RF24_PA_MAX : RF24_PA_LOW;
    reconfigurarRadio();
    imprimir("\n[CONFIG] Potencia PA cambiada a: %s\n", paActual == RF24_PA_LOW ? "RF24_PA_LOW" : "RF24_PA_MAX");
  } else if (c == 'm') {
    envioAutoHabilitado = !envioAutoHabilitado;
    imprimir("\n[CONFIG] Envio automatico 1Hz: %s\n", envioAutoHabilitado ? "ACTIVADO" : "PAUSADO");
  } else if (c == '?' || c == 'h') {
    imprimirConfiguracion();
  } else {
    imprimir("\n[AVISO] Tecla '%c' no reconocida. Use 'w','s','a','d','x','k','1','2','c','p','m' o '?'.\n", c);
  }
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
    reconfigurarRadio();

    imprimir("✅ NRF24L01 detectado y configurado correctamente!\n");
    imprimirConfiguracion();
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
  if (radioOk && envioAutoHabilitado && (ahora - ultimoEnvioAuto >= INTERVALO_AUTO_MS)) {
    ultimoEnvioAuto = ahora;
    enviarTramaRF();
  }

  // Si la radio falló físicamente, parpadear rápido el LED de la placa
  if (!radioOk) {
    digitalWrite(PIN_LED, (millis() / 200) % 2);
  }
}
