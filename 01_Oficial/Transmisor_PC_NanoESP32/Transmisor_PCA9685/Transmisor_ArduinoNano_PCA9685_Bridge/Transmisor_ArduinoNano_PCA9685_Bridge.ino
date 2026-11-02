// Arduino Nano ESP32 – Transmisor vía Serial
// ------------------------------------------------------------
// Recibe comandos del PC (HMI) y los reenvía al Receptor
// Formato de comando: S<id>:<angulo>  (ejemplo: S2:135)
// ------------------------------------------------------------

#include <Arduino.h>

// Configuración de baudios
const unsigned long BAUD_HMI      = 9600;   // Serial con la HMI (PC)
const unsigned long BAUD_RECEPTOR = 115200; // Serial con el Receptor (otro Nano ESP32)

String line = ""; // Acumulador de la línea completa

void setup() {
  // Puerto con la HMI (PC)
  Serial.begin(BAUD_HMI);
  while (!Serial) { ; }

  // Puerto con el Receptor (ESP32) – usa Serial1 en el Nano ESP32
  Serial1.begin(BAUD_RECEPTOR);
  while (!Serial1) { ; }

  Serial.println(F("\n*** Transmisor PCA9685 listo ***"));
  Serial.println(F("Formato de comando: S<id>:<angulo>  (ej. S2:135)"));
}

/* -------------------------------------------------------------------------
   Envía una línea completa recibida por Serial al Receptor sin cambios.
   ------------------------------------------------------------------------- */
void forwardCommand(const String &cmd) {
  if (cmd.length() == 0) return;               // nada que enviar
  // Validación mínima (debe comenzar con S y contener ':')
  if ((cmd[0] != 'S' && cmd[0] != 's') || cmd.indexOf(':') == -1) {
    Serial.println(F("comando inválido – se ignora"));
    return;
  }

  // Re‑envío sin cambios (el Receptor reparará el formato)
  Serial1.print(cmd);
  Serial1.print("\n"); // garantiza fin de línea
  Serial.print(F("Enviado al receptor → "));
  Serial.println(cmd);
}

/* -------------------------------------------------------------------------
   Bucle principal – lee del PC, acumula hasta \r o \n y llama a forward().
   ------------------------------------------------------------------------- */
void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      forwardCommand(line);
      line = "";
    } else {
      line += c;
    }
  }
}
