/*
 * =====================================================================================
 * PROYECTO: ROVER LUNAR V2.0 — MANDO JOYSTICK AUTÓNOMO CON TRANSMISOR NRF24L01
 * ARCHIVO: Joystick_Arduino_Nano.ino
 * HARDWARE: Arduino Nano (ATmega328P) o Arduino Nano ESP32 + Módulo NRF24L01+
 * AUTOR: Equipo de Desarrollo Rover Lunar CEPIT
 * =====================================================================================
 *
 * DESCRIPCIÓN:
 *   Mando de radiocontrol físico 100% autónomo para el Rover Lunar.
 *   NO REQUIERE DE UNA PC PARA FUNCIONAR: Transmite directamente los paquetes de control
 *   por radiofrecuencia (2.4 GHz) al receptor de a bordo (Arduino MKR 1310).
 *
 *   Si se conecta a una computadora por cable USB, el mando envía telemetría de
 *   depuración continua en formato CSV para visualización en tiempo real en la HMI.
 *
 * ASIGNACIÓN DE PINES (COMPATIBLE CON NANO AVR Y NANO ESP32):
 *   -------------------------------------------------------------------------
 *   Módulo NRF24L01+:
 *     - VCC:  3.3V REGULADO (¡NUNCA 5V! Capacitor 10-100µF entre VCC y GND)
 *     - GND:  Tierra común
 *     - CE:   Pin Digital 9
 *     - CSN:  Pin Digital 10
 *     - MOSI: Pin Digital 11 (SPI Hardware)
 *     - MISO: Pin Digital 12 (SPI Hardware)
 *     - SCK:  Pin Digital 13 (SPI Hardware)
 *
 *   Entradas Analógicas:
 *     - A0: Stick 1 (Izquierdo) - Eje X (Giro / Strafe lateral)
 *     - A1: Stick 1 (Izquierdo) - Eje Y (Avance / Retroceso)
 *     - A2: Stick 2 (Derecho)   - Eje X (Rotación sobre su eje / Point Turn)
 *     - A3: Stick 2 (Derecho)   - Eje Y (Control auxiliar / Cámara)
 *     - A4: Potenciómetro Maestro de Potencia (0 a 100% PWM)
 *
 *   Entradas Digitales (Pulsadores con INPUT_PULLUP -> Activos en LOW):
 *     - D2: SW Stick 1 (Alternar Modo: ACKERMANN <-> CANGREJO)
 *     - D3: SW Stick 2 (Recentrar todos los servos a 90°)
 *     - D4: Botón E-STOP (Parada de Emergencia física de golpe)
 *     - D5: Switch / Botón Modo Servos (Estándar [10°-170°] <-> 360°)
 *     - D6: Macro Giro sobre eje Izquierda (↺)
 *     - D7: Macro Giro sobre eje Derecha   (↻)
 *     - D8: LED de Estado / Latido TX
 * =====================================================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>

// -----------------------------------------------------------------------------
// DEFINICIÓN DE PINES
// -----------------------------------------------------------------------------
// NRF24L01
const uint8_t PIN_RF_CE  = 9;
const uint8_t PIN_RF_CSN = 10;

// Entradas Analógicas
const uint8_t PIN_STICK1_X   = A0;
const uint8_t PIN_STICK1_Y   = A1;
const uint8_t PIN_STICK2_X   = A2;
const uint8_t PIN_STICK2_Y   = A3;
const uint8_t PIN_POT_MASTER = A4;

// Entradas Digitales (INPUT_PULLUP)
const uint8_t PIN_SW_STICK1  = 2;
const uint8_t PIN_SW_STICK2  = 3;
const uint8_t PIN_BTN_ESTOP  = 4;
const uint8_t PIN_SW_360     = 5;
const uint8_t PIN_BTN_PIV_IZQ= 6;
const uint8_t PIN_BTN_PIV_DER= 7;

// Salida de Estado / Heartbeat
const uint8_t PIN_LED_STATUS = 8;

// -----------------------------------------------------------------------------
// CONFIGURACIÓN DE RADIOFRECUENCIA (IDÉNTICA A RECEPTOR MKR 1310)
// -----------------------------------------------------------------------------
RF24 radio(PIN_RF_CE, PIN_RF_CSN);
const byte DIRECCION_RF[6] = "ROVER";

// Estructura estrictamente empaquetada (8 bytes) idéntica al receptor MKR
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255 (Lado Izquierdo)
  int16_t traccion_der;  // -255 a 255 (Lado Derecho)
  uint8_t angulo_s1;     // S1: Delantero Izq
  uint8_t angulo_s2;     // S2: Delantero Der
  uint8_t angulo_s3;     // S3: Trasero Izq
  uint8_t angulo_s4;     // S4: Trasero Der
};

PaqueteControl paqueteTX = {0, 0, 90, 90, 90, 90};

// -----------------------------------------------------------------------------
// PARÁMETROS DE CALIBRACIÓN Y FILTRADO
// -----------------------------------------------------------------------------
const int DEADZONE = 45;            // Umbral de zona muerta en ADC (~4.5% del recorrido)
const float EMA_ALPHA = 0.35f;      // Factor de suavizado EMA para ruido ADC
const unsigned long INTERVALO_RF_MS = 35; // Transmisión continua a ~28 Hz

// Detección automática de resolución ADC (Nano AVR = 10 bits [1023], ESP32 = 12 bits [4095])
#if defined(ESP32) || defined(ARDUINO_NANO_ESP32)
  const int ADC_MAX = 4095;
  const int ADC_MID = 2048;
#else
  const int ADC_MAX = 1023;
  const int ADC_MID = 512;
#endif

// -----------------------------------------------------------------------------
// VARIABLES GLOBALES DE ESTADO
// -----------------------------------------------------------------------------
float filt_s1_x = ADC_MID;
float filt_s1_y = ADC_MID;
float filt_s2_x = ADC_MID;
float filt_s2_y = ADC_MID;
float filt_pot  = 0;

bool modo_cangrejo = false;
bool servos_360 = false;
bool estop_activo = false;
bool radio_ok = false;

// Tiempos para no-bloqueo y antirrebote
unsigned long ultimo_envio_rf = 0;
unsigned long ultimo_rebote_sw1 = 0;
unsigned long ultimo_rebote_sw2 = 0;
unsigned long ultimo_rebote_estop = 0;
unsigned long ultimo_rebote_360 = 0;
unsigned long paquetes_tx_count = 0;

// -----------------------------------------------------------------------------
// PROCESAMIENTO ANALÓGICO CON ZONA MUERTA
// -----------------------------------------------------------------------------
int calcular_eje_normalizado(float val_adc) {
  float diff = val_adc - ADC_MID;
  if (abs(diff) <= DEADZONE) {
    return 0;
  }
  if (diff > 0) {
    return (int)constrain(((diff - DEADZONE) / (ADC_MAX - ADC_MID - DEADZONE)) * 100.0f, 0.0f, 100.0f);
  } else {
    return -(int)constrain(((-diff - DEADZONE) / (ADC_MID - DEADZONE)) * 100.0f, 0.0f, 100.0f);
  }
}

// -----------------------------------------------------------------------------
// SETUP
// -----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(100);

  // Configuración de Pines Analógicos
  pinMode(PIN_STICK1_X, INPUT);
  pinMode(PIN_STICK1_Y, INPUT);
  pinMode(PIN_STICK2_X, INPUT);
  pinMode(PIN_STICK2_Y, INPUT);
  pinMode(PIN_POT_MASTER, INPUT);

  // Configuración de Pines Digitales con Pull-up
  pinMode(PIN_SW_STICK1, INPUT_PULLUP);
  pinMode(PIN_SW_STICK2, INPUT_PULLUP);
  pinMode(PIN_BTN_ESTOP, INPUT_PULLUP);
  pinMode(PIN_SW_360, INPUT_PULLUP);
  pinMode(PIN_BTN_PIV_IZQ, INPUT_PULLUP);
  pinMode(PIN_BTN_PIV_DER, INPUT_PULLUP);

  pinMode(PIN_LED_STATUS, OUTPUT);
  digitalWrite(PIN_LED_STATUS, LOW);

  // Precargar lecturas para inicializar filtros
  filt_s1_x = analogRead(PIN_STICK1_X);
  filt_s1_y = analogRead(PIN_STICK1_Y);
  filt_s2_x = analogRead(PIN_STICK2_X);
  filt_s2_y = analogRead(PIN_STICK2_Y);
  filt_pot  = analogRead(PIN_POT_MASTER);

  // Inicialización de la radio NRF24L01+ integrada en el mando
  if (!radio.begin()) {
    radio_ok = false;
    Serial.println(F("[ERROR] NRF24L01 no detectado en el mando. Verifique conexionado 3.3V y SPI."));
  } else {
    radio_ok = true;
    radio.setPayloadSize(sizeof(PaqueteControl)); // 8 bytes exactos
    radio.setPALevel(RF24_PA_MAX);
    radio.setDataRate(RF24_250KBPS);
    radio.setChannel(108);
    radio.setAutoAck(false); // Streaming continuo idéntico a la arquitectura del Rover
    radio.openWritingPipe(DIRECCION_RF);
    radio.stopListening();
    Serial.println(F("[OK] Mando Joystick NRF24L01 listo. Canal: 108 | 250kbps | PA_MAX"));
  }

  Serial.println(F("# MANDO AUTONOMO INICIADO"));
  Serial.println(F("# FORMATO TELEMETRIA DEBUG: JOY:s1_x,s1_y,s2_x,s2_y,master_pwm,sw1,sw2,estop,s360,piv_izq,piv_der,tx_ok"));
}

// -----------------------------------------------------------------------------
// LOOP PRINCIPAL (NO BLOQUEANTE)
// -----------------------------------------------------------------------------
void loop() {
  unsigned long t_actual = millis();

  // 1. LECTURA Y FILTRADO ANALÓGICO (EMA Filter)
  int raw_s1_x = analogRead(PIN_STICK1_X);
  int raw_s1_y = analogRead(PIN_STICK1_Y);
  int raw_s2_x = analogRead(PIN_STICK2_X);
  int raw_s2_y = analogRead(PIN_STICK2_Y);
  int raw_pot  = analogRead(PIN_POT_MASTER);

  filt_s1_x += EMA_ALPHA * (raw_s1_x - filt_s1_x);
  filt_s1_y += EMA_ALPHA * (raw_s1_y - filt_s1_y);
  filt_s2_x += EMA_ALPHA * (raw_s2_x - filt_s2_x);
  filt_s2_y += EMA_ALPHA * (raw_s2_y - filt_s2_y);
  filt_pot  += EMA_ALPHA * (raw_pot - filt_pot);

  // 2. LECTURA DE PULSADORES CON DEBOUNCING
  bool btn_sw1     = (digitalRead(PIN_SW_STICK1) == LOW);
  bool btn_sw2     = (digitalRead(PIN_SW_STICK2) == LOW);
  bool btn_estop   = (digitalRead(PIN_BTN_ESTOP) == LOW);
  bool btn_360     = (digitalRead(PIN_SW_360) == LOW);
  bool btn_piv_izq = (digitalRead(PIN_BTN_PIV_IZQ) == LOW);
  bool btn_piv_der = (digitalRead(PIN_BTN_PIV_DER) == LOW);

  // Toggle de Modo Cangrejo / Ackermann con SW1
  if (btn_sw1 && (t_actual - ultimo_rebote_sw1 > 350)) {
    modo_cangrejo = !modo_cangrejo;
    ultimo_rebote_sw1 = t_actual;
  }

  // Toggle de Servos 360° con SW_360
  if (btn_360 && (t_actual - ultimo_rebote_360 > 350)) {
    servos_360 = !servos_360;
    ultimo_rebote_360 = t_actual;
  }

  // Toggle de E-STOP
  if (btn_estop && (t_actual - ultimo_rebote_estop > 350)) {
    estop_activo = !estop_activo;
    ultimo_rebote_estop = t_actual;
  }

  // 3. NORMALIZACIÓN DE EJES (-100 a +100%)
  int norm_s1_x = calcular_eje_normalizado(filt_s1_x);
  int norm_s1_y = -calcular_eje_normalizado(filt_s1_y); // Arriba es avance (+100)

  int norm_s2_x = calcular_eje_normalizado(filt_s2_x);
  int norm_s2_y = -calcular_eje_normalizado(filt_s2_y);

  int master_pwm = map((int)filt_pot, 0, ADC_MAX, 0, 255);
  master_pwm = constrain(master_pwm, 0, 255);

  // 4. RESOLUCIÓN CINEMÁTICA EN EL PROPIO MANDO (AUTÓNOMO)
  if (estop_activo) {
    paqueteTX.traccion_izq = 0;
    paqueteTX.traccion_der = 0;
    paqueteTX.angulo_s1 = 90;
    paqueteTX.angulo_s2 = 90;
    paqueteTX.angulo_s3 = 90;
    paqueteTX.angulo_s4 = 90;
  }
  else if (btn_sw2) {
    // Recentrado solicitado por el operador
    paqueteTX.traccion_izq = 0;
    paqueteTX.traccion_der = 0;
    paqueteTX.angulo_s1 = 90;
    paqueteTX.angulo_s2 = 90;
    paqueteTX.angulo_s3 = 90;
    paqueteTX.angulo_s4 = 90;
  }
  else if (btn_piv_izq || norm_s2_x < -30) {
    // Rotación sobre su propio eje Antihoraria (↺):
    // Ruedas tangenciales concéntricas: S1=45°, S2=135°, S3=135°, S4=45°
    paqueteTX.angulo_s1 = 45;
    paqueteTX.angulo_s2 = 135;
    paqueteTX.angulo_s3 = 135;
    paqueteTX.angulo_s4 = 45;
    paqueteTX.traccion_izq = -master_pwm;
    paqueteTX.traccion_der = master_pwm;
  }
  else if (btn_piv_der || norm_s2_x > 30) {
    // Rotación sobre su propio eje Horaria (↻):
    paqueteTX.angulo_s1 = 45;
    paqueteTX.angulo_s2 = 135;
    paqueteTX.angulo_s3 = 135;
    paqueteTX.angulo_s4 = 45;
    paqueteTX.traccion_izq = master_pwm;
    paqueteTX.traccion_der = -master_pwm;
  }
  else if (modo_cangrejo) {
    // --- MODO CANGREJO ---
    if (servos_360) {
      if (norm_s1_x < -25) {
        // Desplazamiento lateral puro hacia la izquierda (180°)
        paqueteTX.angulo_s1 = 180; paqueteTX.angulo_s2 = 180;
        paqueteTX.angulo_s3 = 180; paqueteTX.angulo_s4 = 180;
        paqueteTX.traccion_izq = master_pwm;
        paqueteTX.traccion_der = master_pwm;
      } else if (norm_s1_x > 25) {
        // Desplazamiento lateral puro hacia la derecha (0°)
        paqueteTX.angulo_s1 = 0; paqueteTX.angulo_s2 = 0;
        paqueteTX.angulo_s3 = 0; paqueteTX.angulo_s4 = 0;
        paqueteTX.traccion_izq = master_pwm;
        paqueteTX.traccion_der = master_pwm;
      } else if (norm_s1_y > 25) {
        // Avance recto
        paqueteTX.angulo_s1 = 90; paqueteTX.angulo_s2 = 90;
        paqueteTX.angulo_s3 = 90; paqueteTX.angulo_s4 = 90;
        paqueteTX.traccion_izq = master_pwm;
        paqueteTX.traccion_der = master_pwm;
      } else if (norm_s1_y < -25) {
        // Reversa recta
        paqueteTX.angulo_s1 = 90; paqueteTX.angulo_s2 = 90;
        paqueteTX.angulo_s3 = 90; paqueteTX.angulo_s4 = 90;
        paqueteTX.traccion_izq = -master_pwm;
        paqueteTX.traccion_der = -master_pwm;
      } else {
        paqueteTX.traccion_izq = 0;
        paqueteTX.traccion_der = 0;
      }
    } else {
      // Cangrejo estándar acotado a [10°, 170°]
      if (norm_s1_x < -25) {
        paqueteTX.angulo_s1 = 135; paqueteTX.angulo_s2 = 135;
        paqueteTX.angulo_s3 = 135; paqueteTX.angulo_s4 = 135;
        paqueteTX.traccion_izq = master_pwm;
        paqueteTX.traccion_der = master_pwm;
      } else if (norm_s1_x > 25) {
        paqueteTX.angulo_s1 = 45; paqueteTX.angulo_s2 = 45;
        paqueteTX.angulo_s3 = 45; paqueteTX.angulo_s4 = 45;
        paqueteTX.traccion_izq = master_pwm;
        paqueteTX.traccion_der = master_pwm;
      } else if (norm_s1_y > 25) {
        paqueteTX.angulo_s1 = 90; paqueteTX.angulo_s2 = 90;
        paqueteTX.angulo_s3 = 90; paqueteTX.angulo_s4 = 90;
        paqueteTX.traccion_izq = master_pwm;
        paqueteTX.traccion_der = master_pwm;
      } else if (norm_s1_y < -25) {
        paqueteTX.angulo_s1 = 90; paqueteTX.angulo_s2 = 90;
        paqueteTX.angulo_s3 = 90; paqueteTX.angulo_s4 = 90;
        paqueteTX.traccion_izq = -master_pwm;
        paqueteTX.traccion_der = -master_pwm;
      } else {
        paqueteTX.traccion_izq = 0;
        paqueteTX.traccion_der = 0;
      }
    }
  }
  else {
    // --- MODO ACKERMANN (CONDUCCIÓN ESTÁNDAR) ---
    // Cálculo proporcional de curvatura según el eje X del stick
    int delta_ang = map(norm_s1_x, -100, 100, -35, 35);
    int s_del = constrain(90 - delta_ang, 10, 170);
    int s_tras = constrain(90 + delta_ang, 10, 170); // Contragiro trasero

    paqueteTX.angulo_s1 = s_del;
    paqueteTX.angulo_s2 = s_del;
    paqueteTX.angulo_s3 = s_tras;
    paqueteTX.angulo_s4 = s_tras;

    if (norm_s1_y > 20) {
      // Avance
      if (norm_s1_x < -20) {
        // Curva a la izquierda: motor interno desacelera
        paqueteTX.traccion_izq = (int16_t)(master_pwm * 0.7f);
        paqueteTX.traccion_der = master_pwm;
      } else if (norm_s1_x > 20) {
        // Curva a la derecha: motor interno desacelera
        paqueteTX.traccion_izq = master_pwm;
        paqueteTX.traccion_der = (int16_t)(master_pwm * 0.7f);
      } else {
        paqueteTX.traccion_izq = master_pwm;
        paqueteTX.traccion_der = master_pwm;
      }
    } else if (norm_s1_y < -20) {
      // Reversa
      if (norm_s1_x < -20) {
        paqueteTX.traccion_izq = -(int16_t)(master_pwm * 0.7f);
        paqueteTX.traccion_der = -master_pwm;
      } else if (norm_s1_x > 20) {
        paqueteTX.traccion_izq = -master_pwm;
        paqueteTX.traccion_der = -(int16_t)(master_pwm * 0.7f);
      } else {
        paqueteTX.traccion_izq = -master_pwm;
        paqueteTX.traccion_der = -master_pwm;
      }
    } else {
      // Neutro / Detenido
      paqueteTX.traccion_izq = 0;
      paqueteTX.traccion_der = 0;
    }
  }

  // 5. TRANSMISIÓN RF PERIÓDICA DIRECTA AL ROVER (SIN PASAR POR LA PC)
  if (t_actual - ultimo_envio_rf >= INTERVALO_RF_MS) {
    ultimo_envio_rf = t_actual;

    bool exito_rf = false;
    if (radio_ok) {
      exito_rf = radio.write(&paqueteTX, sizeof(paqueteTX));
      paquetes_tx_count++;
    }

    // Parpadeo LED de estado si hay transmisión
    digitalWrite(PIN_LED_STATUS, (paquetes_tx_count % 2 == 0) ? HIGH : LOW);

    // 6. TELEMETRÍA SERIAL PARA DEPURE / MONITOREO EN PC (SI ESTÁ CONECTADA)
    // Formato estructurado para HMI:
    // JOY:s1_x,s1_y,s2_x,s2_y,master_pwm,sw1,sw2,estop,s360,piv_izq,piv_der,tx_ok
    Serial.print(F("JOY:"));
    Serial.print(norm_s1_x); Serial.print(',');
    Serial.print(norm_s1_y); Serial.print(',');
    Serial.print(norm_s2_x); Serial.print(',');
    Serial.print(norm_s2_y); Serial.print(',');
    Serial.print(master_pwm); Serial.print(',');
    Serial.print(modo_cangrejo ? 1 : 0); Serial.print(',');
    Serial.print(btn_sw2 ? 1 : 0); Serial.print(',');
    Serial.print(estop_activo ? 1 : 0); Serial.print(',');
    Serial.print(servos_360 ? 1 : 0); Serial.print(',');
    Serial.print(btn_piv_izq ? 1 : 0); Serial.print(',');
    Serial.print(btn_piv_der ? 1 : 0); Serial.print(',');
    Serial.println(exito_rf ? 1 : 0);
  }
}
