/*
 * =====================================================================================
 *  RECEPTOR ARDUINO MKR 1310 — VERSION DE DEPURACION Y TELEMETRIA (DEBUG)
 *  Rover Lunar V2.0 (Rocker-Bogie 6x6: 6 Motores + 4 Servos Independientes)
 * =====================================================================================
 *  Hardware: Arduino MKR 1310 + NRF24L01+ + Puente H L9110S + 4 Servomotores
 *  Asignacion de Pines:
 *    - NRF24L01 CE:   Pin Digital 0
 *    - NRF24L01 CSN:  Pin Digital 1
 *    - NRF24L01 MOSI: Pin Digital 8 (SPI Hardware)
 *    - NRF24L01 SCK:  Pin Digital 9 (SPI Hardware)
 *    - NRF24L01 MISO: Pin Digital 10 (SPI Hardware)
 *    - Puente H Izq:  Pin 2 (A1A - Avance), Pin 5 (A1B - Reversa) -> M1, M2, M3
 *    - Puente H Der:  Pin 3 (B1A - Avance), Pin 4 (B1B - Reversa) -> M4, M5, M6
 *    - Servo S1:      Pin Digital 6 (Delantero Izquierdo)
 *    - Servo S2:      Pin Digital 7 (Delantero Derecho)
 *    - Servo S3:      Pin A1 / Pin 16 (Trasero Izquierdo)
 *    - Servo S4:      Pin A2 / Pin 17 (Trasero Derecho)
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

// Helper printf para Arduino SAMD21 (el core SAMD no implementa Serial.printf nativo)
void debugPrintf(const char *format, ...) {
  char buffer[256];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  Serial.print(buffer);
}

// Estructura estrictamente empaquetada (8 bytes)
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255 (Lado Izquierdo)
  int16_t traccion_der;  // -255 a 255 (Lado Derecho)
  uint8_t angulo_s1;     // S1: Delantero Izq
  uint8_t angulo_s2;     // S2: Delantero Der
  uint8_t angulo_s3;     // S3: Trasero Izq
  uint8_t angulo_s4;     // S4: Trasero Der
};

// Servos de Direccion
Servo servo1;
Servo servo2;
Servo servo3;
Servo servo4;

const int pinServo1 = 6;
const int pinServo2 = 7;
const int pinServo3 = A1;
const int pinServo4 = A2;

// Pines de Traccion L9110S
const int pinA1A = 2; // Izq Avance
const int pinA1B = 5; // Izq Reversa
const int pinB1A = 3; // Der Avance
const int pinB1B = 4; // Der Reversa

// Temporizadores de Failsafe y Diagnostico
unsigned long ultimaRecepcion = 0;
const unsigned long TIMEOUT_MS = 1000;
unsigned long ultimoAvisoWatchdog = 0;
unsigned long ultimoReporteStats = 0;
const unsigned long INTERVALO_STATS_MS = 1000;

// Metricas de Telemetria
unsigned long contadorPaquetesRx = 0;
unsigned long contadorPaquetesDescartados = 0;
unsigned long contadorActivacionesFailsafe = 0;
bool enFailsafe = false;
bool radioOnline = false;

// Estado actual de actuadores para detectar cambios
int16_t actualPwmIzq = 0;
int16_t actualPwmDer = 0;
uint8_t actualS1 = 90, actualS2 = 90, actualS3 = 90, actualS4 = 90;

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

void pararMotores() {
  analogWrite(pinA1A, 0);
  analogWrite(pinA1B, 0);
  analogWrite(pinB1A, 0);
  analogWrite(pinB1B, 0);
  actualPwmIzq = 0;
  actualPwmDer = 0;
}

void aplicarControlMotores(int16_t pwmIzq, int16_t pwmDer) {
  actualPwmIzq = pwmIzq;
  actualPwmDer = pwmDer;

  // Lado Izquierdo
  if (pwmIzq > 0) {
    analogWrite(pinA1B, 0);
    analogWrite(pinA1A, constrain(pwmIzq, 0, 255));
  } else if (pwmIzq < 0) {
    analogWrite(pinA1A, 0);
    analogWrite(pinA1B, constrain(abs(pwmIzq), 0, 255));
  } else {
    analogWrite(pinA1A, 0);
    analogWrite(pinA1B, 0);
  }

  // Lado Derecho
  if (pwmDer > 0) {
    analogWrite(pinB1B, 0);
    analogWrite(pinB1A, constrain(pwmDer, 0, 255));
  } else if (pwmDer < 0) {
    analogWrite(pinB1A, 0);
    analogWrite(pinB1B, constrain(abs(pwmDer), 0, 255));
  } else {
    analogWrite(pinB1A, 0);
    analogWrite(pinB1B, 0);
  }
}

void setup() {
  Serial.begin(115200);

  // Espera no bloqueante al puerto Serial (hasta 2 seg) para ver los logs en PC,
  // pero permite arrancar inmediatamente con bateria en el terreno.
  unsigned long tInicioSerial = millis();
  while (!Serial && (millis() - tInicioSerial < 2000)) {
    delay(10);
  }

  Serial.println();
  Serial.println("===============================================================");
  Serial.println("🤖 RECEPTOR ARDUINO MKR 1310 — DEBUG Y TELEMETRIA ACTIVA");
  Serial.println("===============================================================");
  Serial.println("Iniciando actuadores y pines...");

  // Inicializar servomotores
  servo1.attach(pinServo1);
  servo2.attach(pinServo2);
  servo3.attach(pinServo3);
  servo4.attach(pinServo4);

  servo1.write(90);
  servo2.write(90);
  servo3.write(90);
  servo4.write(90);
  Serial.println(" -> 4 Servomotores centrados a 90° (Pines: S1=6, S2=7, S3=A1, S4=A2).");

  // Configurar pines de traccion
  pinMode(pinA1A, OUTPUT);
  pinMode(pinA1B, OUTPUT);
  pinMode(pinB1A, OUTPUT);
  pinMode(pinB1B, OUTPUT);
  pararMotores();
  Serial.println(" -> Pines de traccion configurados y frenados (A1A=2, A1B=5, B1A=3, B1B=4).");

  // Inicializar NRF24L01
  Serial.println("Iniciando transceptor NRF24L01+...");
  if (!radio.begin()) {
    Serial.println("❌ ERROR FATAL: radio.begin() fallo en Arduino MKR 1310.");
    Serial.println("   -> Verifique conexion de 3.3V (NUNCA 5V)");
    Serial.println("   -> Verifique capacitor de 10uF-100uF entre VCC y GND de la radio");
    Serial.println("   -> Verifique pines CE(0), CSN(1), SCK(9), MOSI(8), MISO(10)");
    radioOnline = false;
  } else {
    radioOnline = true;
    radio.setPALevel(RF24_PA_MAX);
    radio.setDataRate(RF24_250KBPS);
    radio.setChannel(108);
    radio.setAutoAck(true);
    radio.openReadingPipe(1, DIRECCION_RF);
    radio.startListening();

    Serial.println("✅ NRF24L01 receptor configurado y escuchando.");
    Serial.print("   -> Chip conectado?: ");
    Serial.println(radio.isChipConnected() ? "SI (SPI Hardware OK)" : "NO (Falso contacto)");
    Serial.println("   -> Canal RF: 108 | Velocidad: 250 KBPS | AutoAck: SI");
    Serial.println("   -> Escuchando en Pipe 1 con direccion: \"ROVER\"");
  }

  ultimaRecepcion = millis();
  Serial.println("===============================================================");
  Serial.println("Sistema listo. Esperando tramas RF desde el transmisor...");
  Serial.println("===============================================================");
}

void loop() {
  unsigned long ahora = millis();

  if (radioOnline && radio.available()) {
    PaqueteControl paquete;
    int contadorCola = 0;

    // Drenaje rapido de la cola FIFO para quedarse siempre con el paquete mas fresco
    while (radio.available()) {
      radio.read(&paquete, sizeof(paquete));
      contadorCola++;
    }

    if (contadorCola > 1) {
      contadorPaquetesDescartados += (contadorCola - 1);
    }

    unsigned long dt = ahora - ultimaRecepcion;
    ultimaRecepcion = ahora;
    contadorPaquetesRx++;

    if (enFailsafe) {
      enFailsafe = false;
      debugPrintf("[RESTAURADO] Enlace RF recuperado despues de %lu ms.\n", dt);
    }

    // Aplicar traccion y direccion
    aplicarControlMotores(paquete.traccion_izq, paquete.traccion_der);

    uint8_t s1_val = constrain(paquete.angulo_s1, 10, 170);
    uint8_t s2_val = constrain(paquete.angulo_s2, 10, 170);
    uint8_t s3_val = constrain(paquete.angulo_s3, 10, 170);
    uint8_t s4_val = constrain(paquete.angulo_s4, 10, 170);

    servo1.write(s1_val);
    servo2.write(s2_val);
    servo3.write(s3_val);
    servo4.write(s4_val);

    actualS1 = s1_val; actualS2 = s2_val; actualS3 = s3_val; actualS4 = s4_val;

    // Log detallado de recepcion
    debugPrintf("[RF_RX #%lu] dt:%lu ms | Cola:%d | TracIzq:%d | TracDer:%d | S:[%d, %d, %d, %d] | ",
                contadorPaquetesRx, dt, contadorCola, paquete.traccion_izq, paquete.traccion_der,
                s1_val, s2_val, s3_val, s4_val);
    volcarPaqueteHex(paquete);
    Serial.println();
  }

  // Failsafe Watchdog: advertencia a los 500 ms y corte de seguridad a los 1000 ms
  unsigned long tiempoSinSenal = ahora - ultimaRecepcion;

  if (tiempoSinSenal > 500 && tiempoSinSenal <= TIMEOUT_MS) {
    if (ahora - ultimoAvisoWatchdog > 250) {
      ultimoAvisoWatchdog = ahora;
      debugPrintf("[WATCHDOG_WARN] Sin paquetes RF hace %lu ms (umbral: %lu ms)...\n", tiempoSinSenal, TIMEOUT_MS);
    }
  }

  if (tiempoSinSenal > TIMEOUT_MS) {
    if (!enFailsafe) {
      enFailsafe = true;
      contadorActivacionesFailsafe++;
      pararMotores();
      debugPrintf("[FAILSAFE ACTIVADO] Perdida de enlace RF (>%lu ms). MOTORES APAGADOS A 0.\n", TIMEOUT_MS);
    }
  }

  // Estadisticas periodicas a 1 Hz
  if (ahora - ultimoReporteStats >= INTERVALO_STATS_MS) {
    ultimoReporteStats = ahora;
    debugPrintf("[ESTADO_MKR] TotalRx:%lu | DescartadosFIFO:%lu | Failsafes:%lu | SinSenal:%lu ms | Estado:%s\n",
                contadorPaquetesRx, contadorPaquetesDescartados, contadorActivacionesFailsafe,
                tiempoSinSenal, enFailsafe ? "FAILSAFE (Frenado)" : "OPERATIVO");
  }
}
