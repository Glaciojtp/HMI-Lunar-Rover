#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

#define NUM_SERVOS 4
#define SERVO_MIN 150
#define SERVO_MAX 550

// Registro de las posiciones actuales para movimientos suaves
int posActual[NUM_SERVOS] = {90, 90, 90, 90};

// Mueve un servo directamente a un ángulo
void moverServo(uint8_t canal, int angulo) {
  angulo = constrain(angulo, 0, 180);
  int pulso = map(angulo, 0, 180, SERVO_MIN, SERVO_MAX);
  pca.setPWM(canal, 0, pulso);
  posActual[canal] = angulo;
}

// Mueve los 4 servos de manera simultánea y suave
void moverCuatroServosSuave(int a0, int a1, int a2, int a3, int velocidadMs) {
  int objetivos[NUM_SERVOS] = {
    constrain(a0, 0, 180),
    constrain(a1, 0, 180),
    constrain(a2, 0, 180),
    constrain(a3, 0, 180)
  };

  bool enMovimiento = true;
  while (enMovimiento) {
    enMovimiento = false;
    for (int i = 0; i < NUM_SERVOS; i++) {
      if (posActual[i] < objetivos[i]) {
        posActual[i]++;
        int pulso = map(posActual[i], 0, 180, SERVO_MIN, SERVO_MAX);
        pca.setPWM(i, 0, pulso);
        enMovimiento = true;
      } else if (posActual[i] > objetivos[i]) {
        posActual[i]--;
        int pulso = map(posActual[i], 0, 180, SERVO_MIN, SERVO_MAX);
        pca.setPWM(i, 0, pulso);
        enMovimiento = true;
      }
    }
    delay(velocidadMs);
  }
}

// Función para mover al lado A: S0,S1 -> 120 | S2,S3 -> 60
void ejecutarSecuenciaGrupoA() {
  Serial.println("-> Ejecutando grupo (+): S0=120, S1=120, S2=60, S3=60");
  moverCuatroServosSuave(180, 180, 180, 180, 15);
  Serial.println("-> Posicion alcanzada.");
}



// Función para mover al lado B (inverso): S0,S1 -> 60 | S2,S3 -> 120
void ejecutarSecuenciaGrupoB() {
  Serial.println("-> Ejecutando grupo (-): S0=60, S1=60, S2=120, S3=120");
  moverCuatroServosSuave(10, 10, 120, 120, 15);
  Serial.println("-> Posicion alcanzada.");
}

void setup() {
  Serial.begin(9600);
  Wire.begin();

  pca.begin();
  pca.setPWMFreq(50);
  delay(500);

  Serial.println("--- CONTROL DE 4 SERVOS ---");
  Serial.println("Comandos disponibles:");
  Serial.println("  1) Manual:   canal,angulo    (Ej: 0,45 o 2,180)");
  Serial.println("  2) Grupo +:  g o grupo       (S0,S1 -> 120 | S2,S3 -> 60)");
  Serial.println("  3) Grupo -:  -g o -grupo     (S0,S1 -> 60  | S2,S3 -> 120)");
  Serial.println("---------------------------");

  // Posición inicial de reposo
  for (int i = 0; i < NUM_SERVOS; i++) {
    moverServo(i, 90);
    delay(100);
  }
  Serial.println("Servos listos en 90 grados.");
}

void loop() {
  if (Serial.available() > 0) {
    String entrada = Serial.readStringUntil('\n');
    entrada.trim();

    if (entrada.length() == 0) return;

    // Comando para mover al lado original
    if (entrada.equalsIgnoreCase("grupo") || entrada.equalsIgnoreCase("g")) {
      ejecutarSecuenciaGrupoA();
    }
    // Comando para mover hacia el lado inverso
    else if (entrada.equalsIgnoreCase("-grupo") || entrada.equalsIgnoreCase("-g")) {
      ejecutarSecuenciaGrupoB();
    } 
    // Control individual por formato: canal,angulo
    else {
      int separador = entrada.indexOf(',');
      
      if (separador != -1) {
        int canal = entrada.substring(0, separador).toInt();
        int angulo = entrada.substring(separador + 1).toInt();

        if (canal >= 0 && canal < NUM_SERVOS) {
          if (angulo >= 0 && angulo <= 180) {
            moverServo(canal, angulo);
            Serial.print("Servo ");
            Serial.print(canal);
            Serial.print(" -> ");
            Serial.print(angulo);
            Serial.println("°");
          } else {
            Serial.println("Error: El angulo debe estar entre 0 y 180.");
          }
        } else {
          Serial.println("Error: Canal invalido (usa 0, 1, 2 o 3).");
        }
      } else {
        Serial.println("Comando no reconocido. Usa 'canal,angulo', 'g' o '-g'.");
      }
    }
  }
}