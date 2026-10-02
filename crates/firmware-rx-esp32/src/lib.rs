// Firmware Receptor y Control de Actuadores para Arduino Nano ESP32 (ESP32-S3)
// Proyecto: Rover Lunar V2.0
// Regla estricta: Prohibicion absoluta de emojis.

#![cfg_attr(not(test), no_std)]

extern crate alloc;

use alloc::format;
use alloc::string::{String, ToString};
use alloc::vec::Vec;
use protocol_rover::PaqueteRover;

// =============================================================================
// ASIGNACION DE PINES DE HARDWARE (Arduino Nano ESP32 / ESP32-S3)
// =============================================================================

/// Pin CE del modulo NRF24L01+ en D9 (GPIO 18)
pub const PIN_NRF_CE: u8 = 18;

/// Pin CSN del modulo NRF24L01+ en D10 (GPIO 21)
pub const PIN_NRF_CSN: u8 = 21;

/// SPI MOSI en D11 (GPIO 38)
pub const PIN_SPI_MOSI: u8 = 38;

/// SPI MISO en D12 (GPIO 47)
pub const PIN_SPI_MISO: u8 = 47;

/// SPI SCK en D13 (GPIO 48)
pub const PIN_SPI_SCK: u8 = 48;

/// Puente H L9110S - Motor Izquierdo Avance (PWM) en D2 (GPIO 5)
pub const PIN_MOTOR_A1A: u8 = 5;

/// Puente H L9110S - Motor Izquierdo Reversa (PWM) en D5 (GPIO 8)
pub const PIN_MOTOR_A1B: u8 = 8;

/// Puente H L9110S - Motor Derecho Avance (PWM) en D3 (GPIO 6)
pub const PIN_MOTOR_B1A: u8 = 6;

/// Puente H L9110S - Motor Derecho Reversa (PWM) en D4 (GPIO 7)
pub const PIN_MOTOR_B1B: u8 = 7;

/// Servomotor Direccion 1 (Delantero Izquierdo) en D6 (GPIO 9)
pub const PIN_SERVO_S1: u8 = 9;

/// Servomotor Direccion 2 (Delantero Derecho) en D7 (GPIO 10)
pub const PIN_SERVO_S2: u8 = 10;

/// Servomotor Direccion 3 (Trasero Izquierdo) en D8 (GPIO 17)
pub const PIN_SERVO_S3: u8 = 17;

/// Servomotor Direccion 4 (Trasero Derecho) en A0 (GPIO 1)
pub const PIN_SERVO_S4: u8 = 1;

// =============================================================================
// CONSTANTES DE SEGURIDAD Y PROTOCOLO
// =============================================================================

/// Tiempo limite sin recepcion RF antes de parada de emergencia (ms)
pub const TIMEOUT_FAILSAFE_MS: u64 = 1000;

/// Limite angular minimo seguro para servomotores (grados)
pub const ANGULO_MIN_SERVO: u8 = 10;

/// Limite angular maximo seguro para servomotores (grados)
pub const ANGULO_MAX_SERVO: u8 = 170;

/// Posicion neutral central de los servomotores (grados)
pub const ANGULO_CENTRO_SERVO: u8 = 90;

/// Respuesta estandar al comando IDENT
pub const RESPUESTA_IDENT_RX: &str = "ID:NANO_ESP32:RX:v2.1\n";

/// Respuesta estandar al comando PING
pub const RESPUESTA_PONG_RX: &str = "PONG:RX:NANO_ESP32\n";

// =============================================================================
// CALIBRACION Y TRIMS DE ACTUADORES
// =============================================================================

/// Estructura de calibracion para compensar asimetrias de motores y servos
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CalibracionRover {
    /// Ratios de trim para los 6 motores (0% a 150%, 100 = neutro)
    pub trims_motores: [u8; 6],
    /// Centros calibrados para los 4 servomotores (10 a 170 grados)
    pub centros_servos: [u8; 4],
}

impl Default for CalibracionRover {
    fn default() -> Self {
        Self {
            trims_motores: [100, 100, 100, 100, 100, 100],
            centros_servos: [90, 90, 90, 90],
        }
    }
}

impl CalibracionRover {
    /// Parsea una trama de calibracion en formato textual
    /// `CALIB,m1,m2,m3,m4,m5,m6,s1,s2,s3,s4\n`
    pub fn parsear(trama: &str) -> Option<Self> {
        let limpia = trama.trim();
        if !limpia.starts_with("CALIB,") && !limpia.starts_with("CALIB:") {
            return None;
        }

        let valores: Vec<&str> = limpia[6..].split(',').map(|s| s.trim()).collect();
        if valores.len() < 10 {
            return None;
        }

        let mut trims = [100u8; 6];
        for i in 0..6 {
            let v = valores[i].parse::<u8>().ok()?;
            trims[i] = v.min(150);
        }

        let mut servos = [90u8; 4];
        for i in 0..4 {
            let v = valores[6 + i].parse::<u8>().ok()?;
            servos[i] = v.clamp(ANGULO_MIN_SERVO, ANGULO_MAX_SERVO);
        }

        Some(Self {
            trims_motores: trims,
            centros_servos: servos,
        })
    }
}

// =============================================================================
// MAQUINA DE ESTADOS Y CONTROL DEL RECEPTOR
// =============================================================================

/// Estado del actuador y lazo de recepcion RF
#[derive(Debug, Clone)]
pub struct ReceptorEstado {
    pub traccion_izq: i16,
    pub traccion_der: i16,
    pub angulo_s1: u8,
    pub angulo_s2: u8,
    pub angulo_s3: u8,
    pub angulo_s4: u8,
    pub ultimo_paquete_ms: u64,
    pub failsafe_activo: bool,
    pub paquetes_rf_recibidos: u32,
    pub calibracion: CalibracionRover,
}

impl Default for ReceptorEstado {
    fn default() -> Self {
        Self::new()
    }
}

impl ReceptorEstado {
    pub fn new() -> Self {
        Self {
            traccion_izq: 0,
            traccion_der: 0,
            angulo_s1: 90,
            angulo_s2: 90,
            angulo_s3: 90,
            angulo_s4: 90,
            ultimo_paquete_ms: 0,
            failsafe_activo: false,
            paquetes_rf_recibidos: 0,
            calibracion: CalibracionRover::default(),
        }
    }

    /// Procesa una trama RF recibida de 6 bytes
    pub fn procesar_paquete_rf(&mut self, paquete: &PaqueteRover, tiempo_actual_ms: u64) {
        self.paquetes_rf_recibidos += 1;
        self.ultimo_paquete_ms = tiempo_actual_ms;
        self.failsafe_activo = false;

        // Consignas de traccion
        self.traccion_izq = paquete.traccion_izq().clamp(-255, 255);
        self.traccion_der = paquete.traccion_der().clamp(-255, 255);

        // Angulos de servos recortados a limites de seguridad
        self.angulo_s1 = paquete.angulo_s1().clamp(ANGULO_MIN_SERVO, ANGULO_MAX_SERVO);
        self.angulo_s2 = paquete.angulo_s2().clamp(ANGULO_MIN_SERVO, ANGULO_MAX_SERVO);

        // En direccion simetrica Ackermann 4WS, las ruedas traseras giran inversamente
        let centro = ANGULO_CENTRO_SERVO as i16;
        let delta_s1 = self.angulo_s1 as i16 - centro;
        let delta_s2 = self.angulo_s2 as i16 - centro;

        self.angulo_s3 = (centro - delta_s1).clamp(ANGULO_MIN_SERVO as i16, ANGULO_MAX_SERVO as i16) as u8;
        self.angulo_s4 = (centro - delta_s2).clamp(ANGULO_MIN_SERVO as i16, ANGULO_MAX_SERVO as i16) as u8;
    }

    /// Evalua el tiempo transcurrido para activar el failsafe ante perdida de enlace
    pub fn verificar_failsafe(&mut self, tiempo_actual_ms: u64) -> bool {
        if tiempo_actual_ms > self.ultimo_paquete_ms
            && (tiempo_actual_ms - self.ultimo_paquete_ms) >= TIMEOUT_FAILSAFE_MS
        {
            if !self.failsafe_activo {
                self.failsafe_activo = true;
                self.traccion_izq = 0;
                self.traccion_der = 0;
            }
            true
        } else {
            false
        }
    }

    /// Procesa una linea de comando serie USB (ident, ping, calib, persist)
    pub fn procesar_linea_serie(&mut self, linea: &str) -> Option<String> {
        let limpia = linea.trim();

        if limpia.eq_ignore_ascii_case("IDENT") {
            return Some(RESPUESTA_IDENT_RX.to_string());
        }

        if limpia.eq_ignore_ascii_case("PING") {
            return Some(RESPUESTA_PONG_RX.to_string());
        }

        if limpia.starts_with("CALIB") {
            if let Some(calib) = CalibracionRover::parsear(limpia) {
                self.calibracion = calib;
                return Some("ACK:CALIB\n".to_string());
            } else {
                return Some("[ERR] Trama de calibracion invalida\n".to_string());
            }
        }

        if limpia.eq_ignore_ascii_case("PERSIST_NVS") {
            return Some("ACK:PERSIST_NVS\n".to_string());
        }

        None
    }

    /// Formatea la trama de telemetria en tiempo real para transmision serie
    pub fn formatear_telemetria(&self, dt_ms: u32, cola_rf: u8) -> String {
        format!(
            "TLM:{},{},{},{},{},{},{},{}\n",
            self.traccion_izq,
            self.traccion_der,
            self.angulo_s1,
            self.angulo_s2,
            self.angulo_s3,
            self.angulo_s4,
            dt_ms,
            cola_rf
        )
    }
}
