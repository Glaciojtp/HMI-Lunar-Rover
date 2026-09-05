/*
 * =====================================================================================
 *  TEST RF RECEPTOR — ARDUINO MKR WAN 1310
 *  Rover Lunar V2.0 — Prueba de enlace por Monitor Serie (100% independiente de Python)
 * =====================================================================================
 *  Pines físicos fijos:
 *    - NRF24 CE:   Pin Digital 0
 *    - NRF24 CSN:  Pin Digital 1
 *    - NRF24 MOSI: Pin Digital 8
 *    - NRF24 SCK:  Pin Digital 9
 *    - NRF24 MISO: Pin Digital 10
 *    - Puente H L9110S:
 *        * A1A: Pin 2 (Motor Izquierdo Avance)
 *        * A1B: Pin 5 (Motor Izquierdo Reversa)
 *        * B1A: Pin 3 (Motor Derecho Avance)
 *        * B1B: Pin 4 (Motor Derecho Reversa)
 *    - Servomotor S1: Pin Digital 6
 *    - Servomotor S2: Pin Digital 7
 * =====================================================================================
 *  Comandos interactivos desde Monitor Serie (115200 baudios):
 *    'k' -> Alternar Auto-ACK (ON / OFF)
 *    '1' -> Cambiar velocidad a 1 MBPS
 *    '2' -> Cambiar velocidad a 250 KBPS (por defecto)
 *    'c' -> Cambiar canal RF (108 <-> 76 <-> 90)
 *    'p' -> Alternar potencia (LOW <-> MAX)
 *    't' -> Test local de actuadores (gira motores y mueve servos por 1 seg)
 *    '?' -> Imprimir configuración actual y menú de ayuda
 * =====================================================================================
 */

#include <SPI.h>
#include <RF24.h>
#include <Servo.h>
#include <stdarg.h>

#define PIN_CE  0
#define PIN_CSN 1

RF24 radio(PIN_CE, PIN_CSN);
const byte DIRECCION_RF[6] = "ROVER";

// Estructura oficial de 6 bytes según AGENTS.md (empaquetado estricto)
struct __attribute__((packed)) PaqueteRover {
  int16_t traccion_izq;  // -255 a 255
  int16_t traccion_der;  // -255 a 255
  uint8_t angulo_s1;     // 10 a 170
  uint8_t angulo_s2;     // 10 a 170
};

// Prototipos explícitos para compatibilidad con preprocesador SAMD21
void debugPrintf(const char *format, ...);
void pararMotores();
void aplicarControlMotores(int16_t pwmIzq, int16_t pwmDer);
void imprimirConfiguracion();
void procesarEntradaUsuario(char c);

void debugPrintf(const char *format, ...) {
  char buffer[256];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  Serial.print(buffer);
}

// Actuadores
Servo servo1;
Servo servo2;
const int pinServo1 = 6;
const int pinServo2 = 7;

const int pinA1A = 2; 
const int pinA1B = 5; 
const int pinB1A = 3; 
const int pinB1B = 4; 

// Variables de estado
unsigned long ultimaRecepcion = 0;
const unsigned long TIMEOUT_MS = 1500;
unsigned long contadorPaquetesRx = 0;
bool radioOk = false;
bool enFailsafe = false;

// Opciones dinámicas de RF
bool autoAckHabilitado = true;
uint8_t canalActual = 108;
rf24_datarate_e datarateActual = RF24_250KBPS;
rf24_pa_dbm_e paActual = RF24_PA_LOW;

void pararMotores() {
  analogWrite(pinA1A, 0);
  analogWrite(pinA1B, 0);
  analogWrite(pinB1A, 0);
  analogWrite(pinB1B, 0);
}

void aplicarControlMotores(int16_t pwmIzq, int16_t pwmDer) {
  pwmIzq = constrain(pwmIzq, -255, 255);
  pwmDer = constrain(pwmDer, -255, 255);

  if (pwmIzq > 0) {
    analogWrite(pinA1A, pwmIzq);
    analogWrite(pinA1B, 0);
  } else if (pwmIzq < 0) {
    analogWrite(pinA1A, 0);
    analogWrite(pinA1B, abs(pwmIzq));
  } else {
    analogWrite(pinA1A, 0);
    analogWrite(pinA1B, 0);
  }

  if (pwmDer > 0) {
    analogWrite(pinB1A, pwmDer);
    analogWrite(pinB1B, 0);
  } else if (pwmDer < 0) {
    analogWrite(pinB1A, 0);
    analogWrite(pinB1B, abs(pwmDer));
  } else {
    analogWrite(pinB1A, 0);
    analogWrite(pinB1B, 0);
  }
}

void volcarHex(const void* ptr, size_t len) {
  const uint8_t* b = (const uint8_t*)ptr;
  Serial.print("HEX:[ ");
  for (size_t i = 0; i < len; i++) {
    if (b[i] < 0x10) Serial.print("0");
    Serial.print(b[i], HEX);
    Serial.print(" ");
  }
  Serial.print("]");
}

void testLocalActuadores() {
  debugPrintf("\n[TEST ACTUADORES] Iniciando secuencia de prueba fisica...\n");
  
  // Test Servos
  debugPrintf(" -> Moviendo Servos a 60° (Giro Derecha)...\n");
  servo1.write(60);
  servo2.write(60);
  delay(500);

  debugPrintf(" -> Moviendo Servos a 120° (Giro Izquierda)...\n");
  servo1.write(120);
  servo2.write(120);
  delay(500);

  debugPrintf(" -> Centrando Servos a 90°...\n");
  servo1.write(90);
  servo2.write(90);
  delay(300);

  // Test Motores
  debugPrintf(" -> Probando Avance suave (PWM 120) por 400 ms...\n");
  aplicarControlMotores(120, 120);
  delay(400);

  debugPrintf(" -> Probando Reversa suave (PWM -120) por 400 ms...\n");
  aplicarControlMotores(-120, -120);
  delay(400);

  pararMotores();
  debugPrintf(" -> Motores detenidos. Test completado exitosamente.\n\n");
}

void imprimirConfiguracion() {
  debugPrintf("\n---------------- CONFIGURACION ACTUAL NRF24 ----------------\n");
  debugPrintf("   Chip Conectado?: %s\n", radio.isChipConnected() ? "SI (SPI OK)" : "NO (¡REVISAR CABLES!)");
  debugPrintf("   Canal RF:        %d (%d MHz)\n", canalActual, 2400 + canalActual);
  debugPrintf("   Velocidad:       %s\n", datarateActual == RF24_250KBPS ? "250 KBPS" : "1 MBPS");
  debugPrintf("   Auto-ACK:        %s\n", autoAckHabilitado ? "HABILITADO" : "DESHABILITADO (Broadcast)");
  debugPrintf("   Potencia PA:     %s\n", paActual == RF24_PA_LOW ? "RF24_PA_LOW (Banco)" : "RF24_PA_MAX");
  debugPrintf("   Tamano Trama:    %d Bytes FIJOS (Dynamic Payloads: OFF)\n", sizeof(PaqueteRover));
  debugPrintf("   Pipe 1 RX:       \"ROVER\"\n");
  debugPrintf("---------------- COMANDOS DISPONIBLES EN CONSOLA -----------\n");
  debugPrintf("   'k' -> Toggle Auto-ACK | '1' -> 1 Mbps | '2' -> 250 Kbps\n");
  debugPrintf("   'c' -> Rotar Canal     | 'p' -> Toggle PA Potencia\n");
  debugPrintf("   't' -> Test Motores/Servos locales | '?' -> Ver este menu\n");
  debugPrintf("------------------------------------------------------------\n\n");
}

void reconfigurarRadio() {
  radio.stopListening();
  radio.setChannel(canalActual);
  radio.setDataRate(datarateActual);
  radio.setPALevel(paActual);
  radio.setAutoAck(autoAckHabilitado);
  radio.setPayloadSize(sizeof(PaqueteRover));
  radio.openReadingPipe(1, DIRECCION_RF);
  radio.startListening();
}

void procesarEntradaUsuario(char c) {
  c = tolower(c);
  if (c == '\r' || c == '\n' || c == ' ') return;

  if (c == 'k') {
    autoAckHabilitado = !autoAckHabilitado;
    reconfigurarRadio();
    debugPrintf("\n[CONFIG] Auto-ACK cambiado a: %s\n", autoAckHabilitado ? "HABILITADO (Receptor envia ACK)" : "DESHABILITADO (Sin ACK)");
  } else if (c == '1') {
    datarateActual = RF24_1MBPS;
    reconfigurarRadio();
    debugPrintf("\n[CONFIG] Velocidad cambiada a: 1 MBPS (Mayor compatibilidad con clones Si24R1)\n");
  } else if (c == '2') {
    datarateActual = RF24_250KBPS;
    reconfigurarRadio();
    debugPrintf("\n[CONFIG] Velocidad cambiada a: 250 KBPS (Mayor alcance y sensibilidad)\n");
  } else if (c == 'c') {
    if (canalActual == 108) canalActual = 76;
    else if (canalActual == 76) canalActual = 90;
    else canalActual = 108;
    reconfigurarRadio();
    debugPrintf("\n[CONFIG] Canal RF cambiado a: %d (%d MHz)\n", canalActual, 2400 + canalActual);
  } else if (c == 'p') {
    paActual = (paActual == RF24_PA_LOW) ? RF24_PA_MAX : RF24_PA_LOW;
    reconfigurarRadio();
    debugPrintf("\n[CONFIG] Potencia PA cambiada a: %s\n", paActual == RF24_PA_LOW ? "RF24_PA_LOW" : "RF24_PA_MAX");
  } else if (c == 't') {
    testLocalActuadores();
  } else if (c == '?' || c == 'h') {
    imprimirConfiguracion();
  } else {
    debugPrintf("\n[AVISO] Tecla '%c' no reconocida. Use 'k', '1', '2', 'c', 'p', 't', o '?'.\n", c);
  }
}

void setup() {
  Serial.begin(115200);

  // Inicializar pines de motores
  pinMode(pinA1A, OUTPUT);
  pinMode(pinA1B, OUTPUT);
  pinMode(pinB1A, OUTPUT);
  pinMode(pinB1B, OUTPUT);
  pararMotores();

  // Inicializar servomotores
  servo1.attach(pinServo1);
  servo2.attach(pinServo2);
  servo1.write(90);
  servo2.write(90);

  // Espera breve para dar tiempo a abrir el Monitor Serie
  delay(1000);

  Serial.println();
  Serial.println("=================================================================");
  Serial.println("🤖  TEST RF RECEPTOR — ARDUINO MKR 1310 (MONITOR SERIE)          ");
  Serial.println("=================================================================");
  Serial.println("Pines NRF24: CE=0, CSN=1, MOSI=8, SCK=9, MISO=10");
  Serial.println("Iniciando radio NRF24L01+...");

  if (!radio.begin()) {
    Serial.println("❌ ERROR FATAL: radio.begin() fallo en Arduino MKR 1310.");
    Serial.println("   -> Verifique alimentacion 3.3V (¡NUNCA 5V!)");
    Serial.println("   -> Verifique capacitor de 10uF-100uF entre VCC y GND de la radio");
    Serial.println("   -> Verifique conexion de pines CE(0), CSN(1), SCK(9), MOSI(8), MISO(10)");
    radioOk = false;
  } else {
    radioOk = true;

    // Configuración estricta de tamaño fijo (6 bytes)
    radio.setPayloadSize(sizeof(PaqueteRover)); // 6 bytes exactos
    // NOTA CLAVE: Dynamic Payloads se deja DESHABILITADO para máxima robustez con clones
    radio.setPALevel(paActual);
    radio.setDataRate(datarateActual);
    radio.setChannel(canalActual);
    radio.setAutoAck(autoAckHabilitado);
    radio.openReadingPipe(1, DIRECCION_RF);
    radio.startListening();

    imprimirConfiguracion();
    Serial.println("Esperando paquetes transmitidos desde el ESP32...");
    Serial.println("=================================================================");
  }

  ultimaRecepcion = millis();
}

void loop() {
  unsigned long ahora = millis();

  // Escucha de comandos de depuración desde el Monitor Serie de Arduino IDE
  while (Serial.available() > 0) {
    procesarEntradaUsuario((char)Serial.read());
  }

  // Recepción RF
  if (radioOk && radio.available()) {
    PaqueteRover paqueteRecibido = {0, 0, 90, 90};

    // Drenar el búfer leyendo el paquete más reciente (regla AGENTS.md 5.3.2)
    while (radio.available()) {
      radio.read(&paqueteRecibido, sizeof(PaqueteRover));
    }

    unsigned long dt = ahora - ultimaRecepcion;
    ultimaRecepcion = ahora;
    contadorPaquetesRx++;

    if (enFailsafe) {
      enFailsafe = false;
      debugPrintf("\n🎉 [ENLACE RECUPERADO] Comunicacion restablecida despues de %lu ms!\n", dt);
    }

    // Aplicar a actuadores
    aplicarControlMotores(paqueteRecibido.traccion_izq, paqueteRecibido.traccion_der);

    uint8_t s1 = constrain(paqueteRecibido.angulo_s1, 10, 170);
    uint8_t s2 = constrain(paqueteRecibido.angulo_s2, 10, 170);
    servo1.write(s1);
    servo2.write(s2);

    // Mensaje de éxito claro en monitor serie
    debugPrintf("🎉 [RX #%lu] dt:%lu ms | Trac:[%d, %d] | S1:%d° | S2:%d° | ",
                contadorPaquetesRx, dt, paqueteRecibido.traccion_izq, paqueteRecibido.traccion_der, s1, s2);
    volcarHex(&paqueteRecibido, sizeof(PaqueteRover));
    Serial.println();
  }

  // Failsafe por pérdida de enlace (>1500 ms)
  if (radioOk && (ahora - ultimaRecepcion > TIMEOUT_MS)) {
    if (!enFailsafe) {
      enFailsafe = true;
      pararMotores();
      debugPrintf("\n⚠️  [FAILSAFE ACTIVO] Sin senal RF hace >%lu ms. Motores frenados.\n", TIMEOUT_MS);
    }
  }
}
