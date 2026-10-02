//! Crate no_std del protocolo binario unificado para el Rover Lunar V2.0.
//!
//! Define la estructura binaria de transmision de exactamente 6 bytes empaquetados
//! (repr(C, packed)), alineacion de 1 byte y orden de bytes Little-Endian para
//! compatibilidad cruzada entre microcontroladores (SAMD21, ESP32-C3, ESP32-S3)
//! y la estacion terrena en PC (x86_64).

#![no_std]

/// Longitud estricta en bytes del paquete de control RF.
pub const TAMANO_PAQUETE: usize = 6;

/// Angulo minimo mecanicamente seguro para servomotores de direccion (grados).
pub const ANGULO_MIN: u8 = 10;

/// Angulo maximo mecanicamente seguro para servomotores de direccion (grados).
pub const ANGULO_MAX: u8 = 170;

/// Posicion neutral / centrada de direccion (grados).
pub const ANGULO_CENTRO: u8 = 90;

/// Valor minimo permitido para consigna de traccion PWM (reversa maxima).
pub const TRACCION_MIN: i16 = -255;

/// Valor maximo permitido para consigna de traccion PWM (avance maximo).
pub const TRACCION_MAX: i16 = 255;

/// Errores posibles durante el parseo y validacion del protocolo.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProtocolError {
    /// Longitud del slice no coincide con TAMANO_PAQUETE.
    InvalidLength { expected: usize, actual: usize },
    /// El buffer proporcionado es insuficiente para alojar la trama.
    BufferTooSmall,
}

impl core::fmt::Display for ProtocolError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::InvalidLength { expected, actual } => {
                write!(
                    f,
                    "Longitud de paquete invalida: esperado {} bytes, recibido {} bytes",
                    expected, actual
                )
            }
            Self::BufferTooSmall => {
                write!(f, "El buffer proporcionado es insuficiente para el paquete")
            }
        }
    }
}

/// Estructura de transmision RF unificada para el Rover Lunar V2.0.
///
/// Diseno binario identico al struct en C++:
/// ```text
/// struct __attribute__((packed)) Paquete {
///   int16_t traccion_izq;
///   int16_t traccion_der;
///   uint8_t angulo_s1;
///   uint8_t angulo_s2;
/// };
/// ```
#[repr(C, packed)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PaqueteRover {
    /// Traccion lado izquierdo (-255 a 255, Little-Endian).
    pub traccion_izq: i16,
    /// Traccion lado derecho (-255 a 255, Little-Endian).
    pub traccion_der: i16,
    /// Angulo servomotor delantero izquierdo (10 a 170 grados).
    pub angulo_s1: u8,
    /// Angulo servomotor delantero derecho (10 a 170 grados).
    pub angulo_s2: u8,
}

// Verificacion estatica de tamano y alineacion en tiempo de compilacion
const _: () = assert!(core::mem::size_of::<PaqueteRover>() == 6);
const _: () = assert!(core::mem::align_of::<PaqueteRover>() == 1);

impl Default for PaqueteRover {
    fn default() -> Self {
        Self {
            traccion_izq: 0,
            traccion_der: 0,
            angulo_s1: ANGULO_CENTRO,
            angulo_s2: ANGULO_CENTRO,
        }
    }
}

impl PaqueteRover {
    /// Crea una nueva instancia de PaqueteRover con los valores suministrados sin recorte.
    pub const fn new(izq: i16, der: i16, s1: u8, s2: u8) -> Self {
        Self {
            traccion_izq: izq,
            traccion_der: der,
            angulo_s1: s1,
            angulo_s2: s2,
        }
    }

    /// Retorna el valor de traccion izquierda por copia para evitar referencias desalineadas.
    #[inline]
    pub const fn traccion_izq(&self) -> i16 {
        self.traccion_izq
    }

    /// Retorna el valor de traccion derecha por copia para evitar referencias desalineadas.
    #[inline]
    pub const fn traccion_der(&self) -> i16 {
        self.traccion_der
    }

    /// Retorna el angulo del servomotor 1.
    #[inline]
    pub const fn angulo_s1(&self) -> u8 {
        self.angulo_s1
    }

    /// Retorna el angulo del servomotor 2.
    #[inline]
    pub const fn angulo_s2(&self) -> u8 {
        self.angulo_s2
    }

    /// Crea una nueva instancia de PaqueteRover recortando los valores a los rangos seguros.
    ///
    /// - `traccion_izq`: [-255, 255]
    /// - `traccion_der`: [-255, 255]
    /// - `angulo_s1`: [10, 170]
    /// - `angulo_s2`: [10, 170]
    pub fn clamped(izq: i16, der: i16, s1: u8, s2: u8) -> Self {
        Self {
            traccion_izq: izq.clamp(TRACCION_MIN, TRACCION_MAX),
            traccion_der: der.clamp(TRACCION_MIN, TRACCION_MAX),
            angulo_s1: s1.clamp(ANGULO_MIN, ANGULO_MAX),
            angulo_s2: s2.clamp(ANGULO_MIN, ANGULO_MAX),
        }
    }

    /// Verifica si todos los campos se encuentran dentro de los rangos de operacion seguros.
    pub fn is_valid_range(&self) -> bool {
        let izq = self.traccion_izq;
        let der = self.traccion_der;
        let s1 = self.angulo_s1;
        let s2 = self.angulo_s2;

        (TRACCION_MIN..=TRACCION_MAX).contains(&izq)
            && (TRACCION_MIN..=TRACCION_MAX).contains(&der)
            && (ANGULO_MIN..=ANGULO_MAX).contains(&s1)
            && (ANGULO_MIN..=ANGULO_MAX).contains(&s2)
    }

    /// Serializa la estructura a un arreglo de 6 bytes en orden Little-Endian.
    pub fn to_bytes(&self) -> [u8; TAMANO_PAQUETE] {
        let izq = self.traccion_izq.to_le_bytes();
        let der = self.traccion_der.to_le_bytes();
        [izq[0], izq[1], der[0], der[1], self.angulo_s1, self.angulo_s2]
    }

    /// Reconstruye una instancia de PaqueteRover a partir de un arreglo de 6 bytes (Little-Endian).
    pub fn from_bytes(bytes: &[u8; TAMANO_PAQUETE]) -> Self {
        let traccion_izq = i16::from_le_bytes([bytes[0], bytes[1]]);
        let traccion_der = i16::from_le_bytes([bytes[2], bytes[3]]);
        let angulo_s1 = bytes[4];
        let angulo_s2 = bytes[5];
        Self {
            traccion_izq,
            traccion_der,
            angulo_s1,
            angulo_s2,
        }
    }

    /// Intenta deserializar un paquete desde un slice de bytes arbitrario.
    ///
    /// Retorna error si el tamano del slice difiere de TAMANO_PAQUETE (6 bytes).
    pub fn try_from_slice(slice: &[u8]) -> Result<Self, ProtocolError> {
        if slice.len() != TAMANO_PAQUETE {
            return Err(ProtocolError::InvalidLength {
                expected: TAMANO_PAQUETE,
                actual: slice.len(),
            });
        }
        let mut buf = [0u8; TAMANO_PAQUETE];
        buf.copy_from_slice(slice);
        Ok(Self::from_bytes(&buf))
    }
}
