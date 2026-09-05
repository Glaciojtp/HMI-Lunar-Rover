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
 *  Instrucciones:
 *    1. Subir al Arduino MKR 1310 con Arduino IDE.
 *    2. Abrir Monitor Serie de Arduino IDE a 115200 baudios.
 *    3. Observar la confirmación inmediata de paquetes recibidos desde el ESP32.
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

// Estructura oficial de 6 bytes según AGENTS.md
struct __attribute__((packed)) PaqueteRover {
  int16_t traccion_izq;  // -255 a 255
  int16_t traccion_der;  // -255 a 255
  uint8_t angulo_s1;     // 10 a 170
  uint8_t angulo_s2;     // 10 a 170
};

// Estructura de 8 bytes para compatibilidad si el emisor manda 4 servos
struct __attribute__((packed)) PaqueteRover8 {
  int16_t traccion_izq;
  int16_t traccion_der;
  uint8_t angulo_s1;
  uint8_t angulo_s2;
  uint8_t angulo_s3;
  uint8_t angulo_s4;
};

// Prototipos explícitos para compatibilidad con preprocesador SAMD21
void debugPrintf(const char *format, ...);
void pararMotores();
void aplicarControlMotores(int16_t pwmIzq, int16_t pwmDer);

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

unsigned long ultimaRecepcion = 0;
const unsigned long TIMEOUT_MS = 1500;
unsigned long contadorPaquetesRx = 0;
bool radioOk = false;
bool enFailsafe = false;

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
    radio.setPayloadSize(sizeof(PaqueteRover)); // 6 bytes exactos
    radio.enableDynamicPayloads();              // Aceptar también tramas de 8 bytes
    radio.setPALevel(RF24_PA_LOW);             // Nivel bajo para mesa de pruebas
    radio.setDataRate(RF24_250KBPS);           // 250 kbps
    radio.setChannel(108);                     // Canal 108
    radio.setAutoAck(true);                    // Auto-ACK habilitado
    radio.openReadingPipe(1, DIRECCION_RF);    // Escuchando pipe "ROVER"
    radio.startListening();                    // Modo Receptor

    Serial.println("✅ NRF24L01 configurado y escuchando correctamente!");
    Serial.print("   -> Chip Conectado?: ");
    Serial.println(radio.isChipConnected() ? "SI (SPI Hardware OK)" : "NO (Revisar cables)");
    Serial.println("   -> Canal: 108 (2.508 GHz) | Velocidad: 250 KBPS");
    Serial.println("   -> Escuchando en Pipe 1 con direccion: \"ROVER\"");
    Serial.println("-----------------------------------------------------------------");
    Serial.println("Esperando paquetes transmitidos desde el ESP32...");
    Serial.println("=================================================================");
  }

  ultimaRecepcion = millis();
}

void loop() {
  unsigned long ahora = millis();

  if (radioOk && radio.available()) {
    PaqueteRover paqueteRecibido = {0, 0, 90, 90};
    uint8_t len = radio.getDynamicPayloadSize();

    if (len == sizeof(PaqueteRover)) {
      radio.read(&paqueteRecibido, sizeof(PaqueteRover));
    } else if (len == sizeof(PaqueteRover8)) {
      PaqueteRover8 p8;
      radio.read(&p8, sizeof(PaqueteRover8));
      paqueteRecibido.traccion_izq = p8.traccion_izq;
      paqueteRecibido.traccion_der = p8.traccion_der;
      paqueteRecibido.angulo_s1 = p8.angulo_s1;
      paqueteRecibido.angulo_s2 = p8.angulo_s2;
    } else {
      radio.flush_rx();
      return;
    }

    unsigned long dt = ahora - ultimaRecepcion;
    ultimaRecepcion = ahora;
    contadorPaquetesRx++;

    if (enFailsafe) {
      enFailsafe = false;
      debugPrintf("\n[ENLACE RECUPERADO] Comunicacion restablecida despues de %lu ms!\n", dt);
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
