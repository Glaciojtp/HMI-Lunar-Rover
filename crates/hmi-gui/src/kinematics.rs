//! Modulo de Cinematica y Control de Actuadores para Rover Rocker-Bogie 6x6.
//!
//! Gestiona:
//! - 6 Motores de traccion: M1 (FL), M2 (ML), M3 (RL), M4 (FR), M5 (MR), M6 (RR).
//! - 4 Servos de direccion: S1 (FL), S2 (FR), S3 (RL), S4 (RR).
//! - Modos de conduccion: Ackermann, PointTurn (Giro 360), Crab (Cangrejo), Manual.
//! - Rango estricto de seguridad mecanica de servos: [10, 170] grados (centro en 90).

use protocol_rover::{ANGULO_CENTRO, ANGULO_MAX, ANGULO_MIN, PaqueteRover, TRACCION_MAX, TRACCION_MIN};

/// Modo de conduccion seleccionado por el operador.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModoConduccion {
    Ackermann,
    PointTurn,
    Crab,
    Manual,
}

impl Default for ModoConduccion {
    fn default() -> Self {
        Self::Ackermann
    }
}

impl ModoConduccion {
    pub const fn as_str(&self) -> &'static str {
        match self {
            Self::Ackermann => "ACKERMANN",
            Self::PointTurn => "POINT_TURN",
            Self::Crab => "CRAB",
            Self::Manual => "MANUAL",
        }
    }
}

/// Estado de las teclas de conduccion activas.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct TeclasEstado {
    pub w: bool,
    pub a: bool,
    pub s: bool,
    pub d: bool,
    pub q: bool,
    pub e: bool,
    pub space: bool,
}

impl TeclasEstado {
    pub fn hay_movimiento(&self) -> bool {
        self.w || self.a || self.s || self.d || self.q || self.e
    }
}

/// Configuracion de calibracion y trims porcentuales para los 6 motores.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TrimsMotores {
    pub m1: u16, // Delantero Izq (%)
    pub m2: u16, // Medio Izq Fijo (%)
    pub m3: u16, // Trasero Izq (%)
    pub m4: u16, // Delantero Der (%)
    pub m5: u16, // Medio Der Fijo (%)
    pub m6: u16, // Trasero Der (%)
    pub master_izq: u8,
    pub master_der: u8,
}

impl Default for TrimsMotores {
    fn default() -> Self {
        Self {
            m1: 100,
            m2: 100,
            m3: 100,
            m4: 100,
            m5: 100,
            m6: 100,
            master_izq: 150,
            master_der: 150,
        }
    }
}

impl TrimsMotores {
    /// Resetea los trims porcentuales a 100% neutro.
    pub fn reset_trims(&mut self) {
        self.m1 = 100;
        self.m2 = 100;
        self.m3 = 100;
        self.m4 = 100;
        self.m5 = 100;
        self.m6 = 100;
    }

    /// Calcula la potencia efectiva de un motor especifico aplicando trim al master.
    pub fn calcular_pwm_motor(&self, motor_idx: usize) -> i16 {
        let (master, trim) = match motor_idx {
            1 => (self.master_izq, self.m1),
            2 => (self.master_izq, self.m2),
            3 => (self.master_izq, self.m3),
            4 => (self.master_der, self.m4),
            5 => (self.master_der, self.m5),
            6 => (self.master_der, self.m6),
            _ => (0, 0),
        };

        let raw = (master as u32 * trim as u32) / 100;
        raw.min(255) as i16
    }

    /// Retorna la potencia promedio del lado izquierdo (M1, M2, M3).
    pub fn potencia_media_izq(&self) -> i16 {
        let p1 = self.calcular_pwm_motor(1) as i32;
        let p2 = self.calcular_pwm_motor(2) as i32;
        let p3 = self.calcular_pwm_motor(3) as i32;
        ((p1 + p2 + p3) / 3).clamp(0, 255) as i16
    }

    /// Retorna la potencia promedio del lado derecho (M4, M5, M6).
    pub fn potencia_media_der(&self) -> i16 {
        let p4 = self.calcular_pwm_motor(4) as i32;
        let p5 = self.calcular_pwm_motor(5) as i32;
        let p6 = self.calcular_pwm_motor(6) as i32;
        ((p4 + p5 + p6) / 3).clamp(0, 255) as i16
    }
}

/// Angulos de orientacion para los 4 servomotores independientes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AngulosServos {
    pub s1: u16, // Delantero Izquierdo
    pub s2: u16, // Delantero Derecho
    pub s3: u16, // Trasero Izquierdo
    pub s4: u16, // Trasero Derecho
}

impl Default for AngulosServos {
    fn default() -> Self {
        Self {
            s1: ANGULO_CENTRO as u16,
            s2: ANGULO_CENTRO as u16,
            s3: ANGULO_CENTRO as u16,
            s4: ANGULO_CENTRO as u16,
        }
    }
}

impl AngulosServos {
    /// Crea una nueva configuracion con valores explicitos sin clamping.
    pub fn new(s1: u16, s2: u16, s3: u16, s4: u16) -> Self {
        Self { s1, s2, s3, s4 }
    }

    /// Crea una nueva configuracion aplicando restriccion estricta a [10, 170] grados.
    pub fn clamped(s1: u16, s2: u16, s3: u16, s4: u16) -> Self {
        Self {
            s1: s1.clamp(ANGULO_MIN as u16, ANGULO_MAX as u16),
            s2: s2.clamp(ANGULO_MIN as u16, ANGULO_MAX as u16),
            s3: s3.clamp(ANGULO_MIN as u16, ANGULO_MAX as u16),
            s4: s4.clamp(ANGULO_MIN as u16, ANGULO_MAX as u16),
        }
    }

    /// Crea una nueva configuracion permitiendo rango continuo 360 grados [0, 360].
    pub fn clamped_360(s1: u16, s2: u16, s3: u16, s4: u16) -> Self {
        Self {
            s1: s1.clamp(0, 360),
            s2: s2.clamp(0, 360),
            s3: s3.clamp(0, 360),
            s4: s4.clamp(0, 360),
        }
    }

    /// Devuelve una copia asegurando los limites segun este habilitado o no el modo 360 grados.
    pub fn asegurar_limites(&self, modo_360: bool) -> Self {
        if modo_360 {
            Self {
                s1: self.s1.clamp(0, 360),
                s2: self.s2.clamp(0, 360),
                s3: self.s3.clamp(0, 360),
                s4: self.s4.clamp(0, 360),
            }
        } else {
            Self {
                s1: self.s1.clamp(ANGULO_MIN as u16, ANGULO_MAX as u16),
                s2: self.s2.clamp(ANGULO_MIN as u16, ANGULO_MAX as u16),
                s3: self.s3.clamp(ANGULO_MIN as u16, ANGULO_MAX as u16),
                s4: self.s4.clamp(ANGULO_MIN as u16, ANGULO_MAX as u16),
            }
        }
    }

    /// Centra todos los servomotores a 90 grados.
    pub fn centrar(&mut self) {
        self.s1 = ANGULO_CENTRO as u16;
        self.s2 = ANGULO_CENTRO as u16;
        self.s3 = ANGULO_CENTRO as u16;
        self.s4 = ANGULO_CENTRO as u16;
    }

    /// Configura la orientacion tangencial al circulo para rotacion 360 grados sobre el eje.
    pub fn preset_point_turn(&mut self) {
        // Ruedas formando el rectangulo tangencial: S1=45, S2=135, S3=135, S4=45
        self.s1 = 45;
        self.s2 = 135;
        self.s3 = 135;
        self.s4 = 45;
    }

    /// Configura las 4 ruedas en paralelo (45 deg en estandar, o 180 deg en servos 360 para lateral puro).
    pub fn preset_crab(&mut self, servos_360: bool) {
        if servos_360 {
            self.s1 = 180;
            self.s2 = 180;
            self.s3 = 180;
            self.s4 = 180;
        } else {
            self.s1 = 45;
            self.s2 = 45;
            self.s3 = 45;
            self.s4 = 45;
        }
    }

    /// Invierte los angulos respetando el centro de 90 grados o 360 grados.
    pub fn invertir(&mut self, servos_360: bool) {
        if servos_360 {
            self.s1 = (360 - self.s1 as i32).rem_euclid(360) as u16;
            self.s2 = (360 - self.s2 as i32).rem_euclid(360) as u16;
            self.s3 = (360 - self.s3 as i32).rem_euclid(360) as u16;
            self.s4 = (360 - self.s4 as i32).rem_euclid(360) as u16;
        } else {
            self.s1 = (180 - self.s1 as i16).clamp(ANGULO_MIN as i16, ANGULO_MAX as i16) as u16;
            self.s2 = (180 - self.s2 as i16).clamp(ANGULO_MIN as i16, ANGULO_MAX as i16) as u16;
            self.s3 = (180 - self.s3 as i16).clamp(ANGULO_MIN as i16, ANGULO_MAX as i16) as u16;
            self.s4 = (180 - self.s4 as i16).clamp(ANGULO_MIN as i16, ANGULO_MAX as i16) as u16;
        }
    }
}

/// Estado calculado del chasis listo para transmision y visualizacion.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EstadoChasis {
    pub traccion_izq: i16,
    pub traccion_der: i16,
    pub servos: AngulosServos,
    pub pwms_motores: [i16; 6], // M1..M6 (con signo segun sentido)
    pub comando_nombre: &'static str,
}

/// Calcula el estado del chasis a partir de las teclas, modo, trims y servos manuales.
pub fn calcular_cinematica(
    teclas: &TeclasEstado,
    modo: ModoConduccion,
    trims: &TrimsMotores,
    servos_manuales: &AngulosServos,
    invertir_servos: bool,
    servos_360: bool,
) -> EstadoChasis {
    // Parada de emergencia prioritaria
    if teclas.space {
        let mut s = *servos_manuales;
        s.centrar();
        return EstadoChasis {
            traccion_izq: 0,
            traccion_der: 0,
            servos: s,
            pwms_motores: [0; 6],
            comando_nombre: "STOP",
        };
    }

    // Estado neutro: sin teclas de navegacion activas (preserva angulos de servos)
    if !teclas.hay_movimiento() {
        return EstadoChasis {
            traccion_izq: 0,
            traccion_der: 0,
            servos: *servos_manuales,
            pwms_motores: [0; 6],
            comando_nombre: "NEUTRO",
        };
    }

    let p_izq = trims.potencia_media_izq();
    let p_der = trims.potencia_media_der();

    let mut servos = *servos_manuales;
    let mut traccion_izq = 0i16;
    let mut traccion_der = 0i16;
    let mut comando_nombre = "CMD";

    // 1. Manejo de rotacion sobre el eje (Q / E) o modo PointTurn
    if teclas.q {
        // Giro antihorario (CCW): Izquierda reversa, Derecha avance
        servos.preset_point_turn();
        traccion_izq = -p_izq;
        traccion_der = p_der;
        comando_nombre = "PIVOT_IZQ";
    } else if teclas.e {
        // Giro horario (CW): Izquierda avance, Derecha reversa
        servos.preset_point_turn();
        traccion_izq = p_izq;
        traccion_der = -p_der;
        comando_nombre = "PIVOT_DER";
    } else {
        match modo {
            ModoConduccion::Ackermann => {
                if teclas.w {
                    if teclas.a {
                        // Avance con curva a la izquierda
                        servos.s1 = 120;
                        servos.s2 = 120;
                        servos.s3 = 60;
                        servos.s4 = 60;
                        traccion_izq = (p_izq as i32 * 7 / 10) as i16;
                        traccion_der = p_der;
                        comando_nombre = "W_A";
                    } else if teclas.d {
                        // Avance con curva a la derecha
                        servos.s1 = 60;
                        servos.s2 = 60;
                        servos.s3 = 120;
                        servos.s4 = 120;
                        traccion_izq = p_izq;
                        traccion_der = (p_der as i32 * 7 / 10) as i16;
                        comando_nombre = "W_D";
                    } else {
                        // Avance recto
                        servos.centrar();
                        traccion_izq = p_izq;
                        traccion_der = p_der;
                        comando_nombre = "W";
                    }
                } else if teclas.s {
                    if teclas.a {
                        // Reversa con curva a la izquierda
                        servos.s1 = 60;
                        servos.s2 = 60;
                        servos.s3 = 120;
                        servos.s4 = 120;
                        traccion_izq = -(p_izq as i32 * 7 / 10) as i16;
                        traccion_der = -p_der;
                        comando_nombre = "S_A";
                    } else if teclas.d {
                        // Reversa con curva a la derecha
                        servos.s1 = 120;
                        servos.s2 = 120;
                        servos.s3 = 60;
                        servos.s4 = 60;
                        traccion_izq = -p_izq;
                        traccion_der = -(p_der as i32 * 7 / 10) as i16;
                        comando_nombre = "S_D";
                    } else {
                        // Reversa recta
                        servos.centrar();
                        traccion_izq = -p_izq;
                        traccion_der = -p_der;
                        comando_nombre = "S";
                    }
                } else if teclas.a {
                    // Giro estacionario o curva pronunciada izquierda
                    servos.s1 = 120;
                    servos.s2 = 120;
                    servos.s3 = 60;
                    servos.s4 = 60;
                    traccion_izq = (p_izq as i32 * 7 / 10) as i16;
                    traccion_der = p_der;
                    comando_nombre = "A";
                } else if teclas.d {
                    // Giro estacionario o curva pronunciada derecha
                    servos.s1 = 60;
                    servos.s2 = 60;
                    servos.s3 = 120;
                    servos.s4 = 120;
                    traccion_izq = p_izq;
                    traccion_der = (p_der as i32 * 7 / 10) as i16;
                    comando_nombre = "D";
                }
            }
            ModoConduccion::PointTurn => {
                servos.preset_point_turn();
                if teclas.a {
                    traccion_izq = -p_izq;
                    traccion_der = p_der;
                    comando_nombre = "POINT_IZQ";
                } else if teclas.d {
                    traccion_izq = p_izq;
                    traccion_der = -p_der;
                    comando_nombre = "POINT_DER";
                } else if teclas.w {
                    traccion_izq = p_izq;
                    traccion_der = p_der;
                    comando_nombre = "POINT_FWD";
                } else if teclas.s {
                    traccion_izq = -p_izq;
                    traccion_der = -p_der;
                    comando_nombre = "POINT_REV";
                }
            }
            ModoConduccion::Crab => {
                servos.preset_crab(servos_360);
                if teclas.w || teclas.d {
                    traccion_izq = p_izq;
                    traccion_der = p_der;
                    comando_nombre = "CRAB_FWD";
                    if servos_360 {
                        let ang = if !invertir_servos { 180 } else { 0 };
                        servos.s1 = ang; servos.s2 = ang; servos.s3 = ang; servos.s4 = ang;
                    } else {
                        let ang = if !invertir_servos { 45 } else { 135 };
                        servos.s1 = ang; servos.s2 = ang; servos.s3 = ang; servos.s4 = ang;
                    }
                } else if teclas.s || teclas.a {
                    traccion_izq = -p_izq;
                    traccion_der = -p_der;
                    comando_nombre = "CRAB_REV";
                    if servos_360 {
                        let ang = if !invertir_servos { 0 } else { 180 };
                        servos.s1 = ang; servos.s2 = ang; servos.s3 = ang; servos.s4 = ang;
                    } else {
                        let ang = if !invertir_servos { 135 } else { 45 };
                        servos.s1 = ang; servos.s2 = ang; servos.s3 = ang; servos.s4 = ang;
                    }
                }
            }
            ModoConduccion::Manual => {
                // Conserva los angulos suministrados por los sliders manuales
                if teclas.w {
                    traccion_izq = p_izq;
                    traccion_der = p_der;
                    comando_nombre = "MANUAL_W";
                } else if teclas.s {
                    traccion_izq = -p_izq;
                    traccion_der = -p_der;
                    comando_nombre = "MANUAL_S";
                } else if teclas.a {
                    traccion_izq = (p_izq as i32 * 7 / 10) as i16;
                    traccion_der = p_der;
                    comando_nombre = "MANUAL_A";
                } else if teclas.d {
                    traccion_izq = p_izq;
                    traccion_der = (p_der as i32 * 7 / 10) as i16;
                    comando_nombre = "MANUAL_D";
                }
            }
        }
    }

    if invertir_servos && modo != ModoConduccion::Manual && modo != ModoConduccion::Crab {
        servos.invertir(servos_360);
    }

    // Calcular PWMs individuales para M1..M6
    let mut pwms_motores = [0i16; 6];
    let sentido_izq: i16 = if traccion_izq > 0 { 1 } else if traccion_izq < 0 { -1 } else { 0 };
    let sentido_der: i16 = if traccion_der > 0 { 1 } else if traccion_der < 0 { -1 } else { 0 };

    pwms_motores[0] = sentido_izq * trims.calcular_pwm_motor(1);
    pwms_motores[1] = sentido_izq * trims.calcular_pwm_motor(2);
    pwms_motores[2] = sentido_izq * trims.calcular_pwm_motor(3);
    pwms_motores[3] = sentido_der * trims.calcular_pwm_motor(4);
    pwms_motores[4] = sentido_der * trims.calcular_pwm_motor(5);
    pwms_motores[5] = sentido_der * trims.calcular_pwm_motor(6);

    let servos_finales = if servos_360 {
        AngulosServos::clamped_360(servos.s1, servos.s2, servos.s3, servos.s4)
    } else {
        AngulosServos::clamped(servos.s1, servos.s2, servos.s3, servos.s4)
    };

    EstadoChasis {
        traccion_izq: traccion_izq.clamp(TRACCION_MIN, TRACCION_MAX),
        traccion_der: traccion_der.clamp(TRACCION_MIN, TRACCION_MAX),
        servos: servos_finales,
        pwms_motores,
        comando_nombre,
    }
}

/// Convierte el estado calculado del chasis al paquete binario estricto de 6 bytes.
pub fn generar_paquete_rover(estado: &EstadoChasis) -> PaqueteRover {
    PaqueteRover::clamped(
        estado.traccion_izq,
        estado.traccion_der,
        estado.servos.s1.min(255) as u8,
        estado.servos.s2.min(255) as u8,
    )
}
