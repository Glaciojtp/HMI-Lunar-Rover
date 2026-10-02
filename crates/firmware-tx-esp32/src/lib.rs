// Firmware Transmisor RF para Arduino Nano ESP32 (ESP32-S3)
// Proyecto: Rover Lunar V2.0
// Regla estricta: Prohibicion absoluta de emojis.

#![cfg_attr(not(test), no_std)]

extern crate alloc;

use alloc::string::{String, ToString};
use alloc::vec::Vec;
use protocol_rover::PaqueteRover;

// =============================================================================
// ASIGNACION DE PINES DE HARDWARE (Arduino Nano ESP32 / ESP32-S3)
// =============================================================================

/// Pin CE del modulo NRF24L01+ conectado a D9 (GPIO 18)
pub const PIN_NRF_CE: u8 = 18;

/// Pin CSN del modulo NRF24L01+ conectado a D10 (GPIO 21)
pub const PIN_NRF_CSN: u8 = 21;

/// Bus SPI Hardware - Transmision de datos MOSI en D11 (GPIO 38)
pub const PIN_SPI_MOSI: u8 = 38;

/// Bus SPI Hardware - Recepcion de datos MISO en D12 (GPIO 47)
pub const PIN_SPI_MISO: u8 = 47;

/// Bus SPI Hardware - Reloj serie SCK en D13 (GPIO 48)
pub const PIN_SPI_SCK: u8 = 48;

/// LED RGB integrado en la placa - Canal Rojo (GPIO 46, activo en bajo)
pub const PIN_LED_RED: u8 = 46;

/// LED RGB integrado en la placa - Canal Verde (GPIO 0, activo en bajo)
pub const PIN_LED_GREEN: u8 = 0;

/// LED RGB integrado en la placa - Canal Azul (GPIO 45, activo en bajo)
pub const PIN_LED_BLUE: u8 = 45;

// =============================================================================
// PARAMETROS DE RADIOFRECUENCIA NRF24L01+
// =============================================================================

/// Canal de radiofrecuencia (2.508 GHz, fuera del rango Wi-Fi convencional)
pub const RF_CHANNEL: u8 = 108;

/// Direccion fija del pipe de radio (5 bytes)
pub const RF_PIPE_ADDRESS: [u8; 5] = [0xE1, 0xF0, 0xF0, 0xF0, 0xF0];

/// Tasa de datos en kilobits por segundo
pub const RF_DATARATE_KBPS: u32 = 250;

/// Respuesta estandar al comando IDENT
pub const RESPUESTA_IDENT: &str = "ID:NANO_ESP32:TX:v2.1\n";

/// Respuesta estandar al comando PING
pub const RESPUESTA_PONG: &str = "PONG:TX:NANO_ESP32\n";

// =============================================================================
// TIPOS DE COMANDO SERIE Y ACCIONES
// =============================================================================

/// Comandos interpretados desde el puerto serie USB CDC
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ComandoSerieTx {
    /// Solicitud de identificacion de placa y rol
    Ident,
    /// Diagnostico de latencia y conexion
    Ping,
    /// Consigna de movimiento estructurada en texto (izq, der, s1, s2)
    ConsignaTexto(PaqueteRover),
    /// Parada inmediata de motores
    Parada,
    /// Paquete binario directo recibido
    PaqueteBinario(PaqueteRover),
    /// Trama no reconocida
    Desconocido(String),
}

/// Acciones a ejecutar por el lazo de control
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AccionTx {
    /// Transmitir respuesta de texto por el puerto serie
    ResponderSerie(String),
    /// Transmitir paquete por radiofrecuencia NRF24L01
    TransmitirRf(PaqueteRover),
    /// Ninguna accion requerida
    Ninguna,
}

// =============================================================================
// PARSEO DE COMANDOS
// =============================================================================

/// Parsea una linea recibida por el puerto serie USB
pub fn parsear_linea_serie(linea: &str) -> ComandoSerieTx {
    let limpia = linea.trim();

    if limpia.is_empty() {
        return ComandoSerieTx::Desconocido("".to_string());
    }

    if limpia.eq_ignore_ascii_case("IDENT") {
        return ComandoSerieTx::Ident;
    }

    if limpia.eq_ignore_ascii_case("PING") {
        return ComandoSerieTx::Ping;
    }

    if limpia.eq_ignore_ascii_case("STOP") {
        return ComandoSerieTx::Parada;
    }

    if limpia.starts_with("CMD,") || limpia.starts_with("CMD:") {
        let partes: Vec<&str> = limpia[4..].split(',').map(|s| s.trim()).collect();
        if partes.len() >= 4 {
            if let (Ok(izq), Ok(der), Ok(s1), Ok(s2)) = (
                partes[0].parse::<i16>(),
                partes[1].parse::<i16>(),
                partes[2].parse::<u8>(),
                partes[3].parse::<u8>(),
            ) {
                let paquete = PaqueteRover::clamped(izq, der, s1, s2);
                return ComandoSerieTx::ConsignaTexto(paquete);
            }
        }
        return ComandoSerieTx::Desconocido(limpia.to_string());
    }

    ComandoSerieTx::Desconocido(limpia.to_string())
}

/// Parsea un buffer de bytes binarios directos
pub fn parsear_bytes_binarios(bytes: &[u8]) -> Option<PaqueteRover> {
    if bytes.len() == 6 {
        PaqueteRover::try_from_slice(bytes).ok()
    } else {
        None
    }
}

// =============================================================================
// MAQUINA DE ESTADOS DEL TRANSMISOR
// =============================================================================

/// Gestor de estado del transmisor RF
#[derive(Debug, Clone)]
pub struct TransmisorEstado {
    pub paquetes_transmitidos: u32,
    pub pings_respondidos: u32,
    pub idents_respondidos: u32,
    pub errores_trama: u32,
    pub ultimo_paquete: PaqueteRover,
}

impl Default for TransmisorEstado {
    fn default() -> Self {
        Self::new()
    }
}

impl TransmisorEstado {
    pub fn new() -> Self {
        Self {
            paquetes_transmitidos: 0,
            pings_respondidos: 0,
            idents_respondidos: 0,
            errores_trama: 0,
            ultimo_paquete: PaqueteRover::new(0, 0, 90, 90),
        }
    }

    /// Procesa una linea de texto entrante y produce la accion correspondiente
    pub fn procesar_texto(&mut self, linea: &str) -> AccionTx {
        let cmd = parsear_linea_serie(linea);
        match cmd {
            ComandoSerieTx::Ident => {
                self.idents_respondidos += 1;
                AccionTx::ResponderSerie(RESPUESTA_IDENT.to_string())
            }
            ComandoSerieTx::Ping => {
                self.pings_respondidos += 1;
                AccionTx::ResponderSerie(RESPUESTA_PONG.to_string())
            }
            ComandoSerieTx::ConsignaTexto(paquete) => {
                self.paquetes_transmitidos += 1;
                self.ultimo_paquete = paquete;
                AccionTx::TransmitirRf(paquete)
            }
            ComandoSerieTx::Parada => {
                let paquete_stop = PaqueteRover::new(
                    0,
                    0,
                    self.ultimo_paquete.angulo_s1(),
                    self.ultimo_paquete.angulo_s2(),
                );
                self.paquetes_transmitidos += 1;
                self.ultimo_paquete = paquete_stop;
                AccionTx::TransmitirRf(paquete_stop)
            }
            ComandoSerieTx::PaqueteBinario(paquete) => {
                self.paquetes_transmitidos += 1;
                self.ultimo_paquete = paquete;
                AccionTx::TransmitirRf(paquete)
            }
            ComandoSerieTx::Desconocido(_) => {
                self.errores_trama += 1;
                AccionTx::ResponderSerie("[ERR] Comando no reconocido\n".to_string())
            }
        }
    }

    /// Procesa un bloque de bytes binarios recibido
    pub fn procesar_binario(&mut self, bytes: &[u8]) -> AccionTx {
        if let Some(paquete) = parsear_bytes_binarios(bytes) {
            self.paquetes_transmitidos += 1;
            self.ultimo_paquete = paquete;
            AccionTx::TransmitirRf(paquete)
        } else {
            self.errores_trama += 1;
            AccionTx::ResponderSerie("[ERR] Longitud de trama binaria invalida\n".to_string())
        }
    }
}
