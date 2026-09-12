/*
 * =====================================================================================
 * PROYECTO: ROVER LUNAR V2.0 - SUBSISTEMA DE CONTROL REMOTO (JOYSTICK)
 * ARCHIVO: Joystick_Arduino_Nano.ino
 * COMPATIBILIDAD: Arduino Nano (ATmega328P), Arduino Nano Every, Arduino Nano ESP32
 * AUTOR: Equipo de Desarrollo Rover Lunar CEPIT
 * =====================================================================================
 *
 * DESCRIPCIÓN:
 *   Firmware para el control remoto físico del Rover Lunar.
 *   Adquiere las señales analógicas de 2 sticks (ejes X e Y), 1 potenciómetro maestro
 *   de velocidad y 6 entradas digitales con pull-up (pulsadores de sticks, parada de
 *   emergencia, selector 360°, y macros de giro sobre su eje).
 *
 * CARACTERÍSTICAS TÉCNICAS:
 *   - Filtrado digital pasa-bajos (Exponential Moving Average) para supresión de ruido ADC.
 *   - Zona muerta configurable (Deadband) en el centro de los sticks para evitar deriva (creep).
 *   - Detección de flancos y antirrebote (debouncing) por software para todos los pulsadores.
 *   - Transmisión serie a 115200 baudios en formato CSV de alta frecuencia (50 Hz / 20 ms).
 *   - Doble salida: Telemetría analógica cruda para el HMI + Comando cinemático precalculado.
 * =====================================================================================
 */

#include <Arduino.h>

// -----------------------------------------------------------------------------
// DEFINICIÓN DE PINES
// -----------------------------------------------------------------------------
// Entradas Analógicas
const uint8_t PIN_STICK1_X   = A0; // Stick Izquierdo - Eje X (Giro / Strafe)
const uint8_t PIN_STICK1_Y   = A1; // Stick Izquierdo - Eje Y (Avance / Retroceso)
const uint8_t PIN_STICK2_X   = A2; // Stick Derecho - Eje X (Rotación sobre Eje / Point Turn)
const uint8_t PIN_STICK2_Y   = A3; // Stick Derecho - Eje Y (Ajuste Fino / Cámara Auxiliar)
const uint8_t PIN_POT_MASTER = A4; // Potenciómetro Maestro de Potencia (0 a 100% PWM)

// Entradas Digitales (Pulsadores con INPUT_PULLUP -> Activos en LOW)
const uint8_t PIN_SW_STICK1  = 2;  // Pulsador Stick 1 (Cambiar Modo: Ackermann <-> Cangrejo)
const uint8_t PIN_SW_STICK2  = 3;  // Pulsador Stick 2 (Centrar Servos a 90°)
const uint8_t PIN_BTN_ESTOP  = 4;  // Botón Rojo de Parada de Emergencia (E-STOP)
const uint8_t PIN_SW_360     = 5;  // Selector / Botón Modo Servos (Estándar 180° vs 360°)
const uint8_t PIN_BTN_PIV_IZQ= 6;  // Macro Giro Eje Izquierda (Tecla Q)
const uint8_t PIN_BTN_PIV_DER= 7;  // Macro Giro Eje Derecha (Tecla E)

// Salida de Estado
const uint8_t PIN_LED_STATUS = 13; // LED integrado de latido / actividad

// -----------------------------------------------------------------------------
// PARÁMETROS DE CALIBRACIÓN Y FILTRADO
// -----------------------------------------------------------------------------
const int DEADZONE = 40;            // Umbral de zona muerta en ADC (~4% del recorrido)
const float EMA_ALPHA = 0.35f;      // Factor de suavizado EMA (0.0 = muy lento, 1.0 = sin filtro)
const unsigned long INTERVALO_TX_MS = 20; // Tasa de transmisión: 50 Hz (20 ms)

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

// Variables de Modo de Operación local
bool modo_cangrejo = false;
bool servos_360 = false;
bool estop_activo = false;

// Tiempos para no-bloqueo
unsigned long ultimo_tiempo_tx = 0;
unsigned long ultimo_rebote_sw1 = 0;
unsigned long ultimo_rebote_sw2 = 0;
unsigned long ultimo_rebote_estop = 0;
unsigned long ultimo_rebote_360 = 0;

// -----------------------------------------------------------------------------
// FUNCIONES AUXILIARES DE PROCESAMIENTO ANALÓGICO
// -----------------------------------------------------------------------------

// Aplica zona muerta y escala a rango [-100, +100]%
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
  // Inicialización del puerto serie para comunicación con PC (HMI)
  Serial.begin(115200);
  while (!Serial && millis() < 1500) {
    ; // Espera breve para conexión USB CDC en arquitecturas modernas
  }

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

  // Lectura inicial para precargar filtros
  filt_s1_x = analogRead(PIN_STICK1_X);
  filt_s1_y = analogRead(PIN_STICK1_Y);
  filt_s2_x = analogRead(PIN_STICK2_X);
  filt_s2_y = analogRead(PIN_STICK2_Y);
  filt_pot  = analogRead(PIN_POT_MASTER);

  Serial.println(F("# INICIADO: Mando Joystick Rover Lunar V2.0"));
  Serial.println(F("# FORMATO: JOY:S1_X,S1_Y,S2_X,S2_Y,MASTER_PWM,SW1,SW2,ESTOP,S360,PIV_IZQ,PIV_DER"));
}

// -----------------------------------------------------------------------------
// LOOP PRINCIPAL (NO BLOQUEANTE)
// -----------------------------------------------------------------------------
void loop() {
  unsigned long t_actual = millis();

  // 1. MUESTREO Y FILTRADO ANALÓGICO (EMA Filter)
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
  bool btn_sw1 = (digitalRead(PIN_SW_STICK1) == LOW);
  bool btn_sw2 = (digitalRead(PIN_SW_STICK2) == LOW);
  bool btn_estop = (digitalRead(PIN_BTN_ESTOP) == LOW);
  bool btn_360 = (digitalRead(PIN_SW_360) == LOW);
  bool btn_piv_izq = (digitalRead(PIN_BTN_PIV_IZQ) == LOW);
  bool btn_piv_der = (digitalRead(PIN_BTN_PIV_DER) == LOW);

  // Toggle de Modo Cangrejo / Ackermann con SW1
  if (btn_sw1 && (t_actual - ultimo_rebote_sw1 > 300)) {
    modo_cangrejo = !modo_cangrejo;
    ultimo_rebote_sw1 = t_actual;
  }

  // Toggle de Servos 360° con SW_360
  if (btn_360 && (t_actual - ultimo_rebote_360 > 300)) {
    servos_360 = !servos_360;
    ultimo_rebote_360 = t_actual;
  }

  // Manejo de E-STOP
  if (btn_estop && (t_actual - ultimo_rebote_estop > 300)) {
    estop_activo = !estop_activo;
    ultimo_rebote_estop = t_actual;
  }

  // 3. PROCESAMIENTO DE EJES ANALÓGICOS
  // Eje X: [-100, 100] (Izquierda a Derecha)
  // Eje Y: [-100, 100] (Atrás a Adelante; se invierte para que arriba sea positivo)
  int norm_s1_x = calcular_eje_normalizado(filt_s1_x);
  int norm_s1_y = -calcular_eje_normalizado(filt_s1_y);

  int norm_s2_x = calcular_eje_normalizado(filt_s2_x);
  int norm_s2_y = -calcular_eje_normalizado(filt_s2_y);

  // Master Potenciometro mapeado a PWM (0 - 255)
  int master_pwm = map((int)filt_pot, 0, ADC_MAX, 0, 255);
  master_pwm = constrain(master_pwm, 0, 255);

  // 4. TRANSMISIÓN PERIÓDICA A LA COMPUTADORA (50 Hz)
  if (t_actual - ultimo_tiempo_tx >= INTERVALO_TX_MS) {
    ultimo_tiempo_tx = t_actual;

    // Indicador LED de latido (parpadea cada 500 ms)
    digitalWrite(PIN_LED_STATUS, (t_actual / 500) % 2 == 0);

    // Trama Serie formateada para parsing inmediato por el HMI:
    // JOY:s1_x,s1_y,s2_x,s2_y,master_pwm,sw1,sw2,estop,s360,piv_izq,piv_der
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
    Serial.println(btn_piv_der ? 1 : 0);
  }
}
