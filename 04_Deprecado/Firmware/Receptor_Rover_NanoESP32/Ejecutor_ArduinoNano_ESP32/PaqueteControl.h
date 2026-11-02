#ifndef PAQUETE_CONTROL_H
#define PAQUETE_CONTROL_H

#include <stdint.h>

// ==========================================
// ESTRUCTURA BINARIA ESTRICTA DE CONTROL (8 BYTES)
// Rover Lunar V2.0 — Protocolo Rocker-Bogie 4WS
// ==========================================
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255 (Lado Izquierdo: M1, M2, M3)
  int16_t traccion_der;  // -255 a 255 (Lado Derecho:   M4, M5, M6)
  uint8_t angulo_s1;     // S1: Delantero Izq [10 - 170 deg]
  uint8_t angulo_s2;     // S2: Delantero Der [10 - 170 deg]
  uint8_t angulo_s3;     // S3: Trasero Izq   [10 - 170 deg]
  uint8_t angulo_s4;     // S4: Trasero Der   [10 - 170 deg]
};

#endif // PAQUETE_CONTROL_H
