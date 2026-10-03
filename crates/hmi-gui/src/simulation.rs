//! Modulo de Simulacion Cinematica 2D en Entorno Plano para Rover Lunar Rocker-Bogie 6x6.
//!
//! Modela la odometria, trayectoria y dinamica de guiñada en condiciones ideales:
//! - Superficie plana horizontal libre de irregularidades (plano XY).
//! - Hipotesis de rodadura pura sin deslizamiento longitudinal ni lateral.
//! - Cinematica inversa y directa para direccion coordinada 4WS (Ackermann simetrico),
//!   giro sobre el eje (Point Turn) y traslacion diagonal/lateral (Crab).
//! - Estimacion de pose: X [m], Y [m], Yaw Theta [rad/deg], Velocidad Lineal [m/s], Yaw Rate [rad/s].
//! - Registro de estela historica de navegacion para visualizacion en tiempo real.

use egui::Pos2;
use crate::kinematics::EstadoChasis;

/// Parametros geometricos y fisicos de la plataforma Rocker-Bogie.
#[derive(Debug, Clone, Copy)]
pub struct ParametrosRover {
    /// Semidistancia entre el eje medio y los ejes extremos (L) en metros.
    pub semi_longitud_l: f32,
    /// Semiancho de via entre ruedas izquierdas y derechas (W) en metros.
    pub semi_ancho_w: f32,
    /// Radio nominal de las ruedas en metros.
    pub radio_rueda: f32,
    /// Velocidad lineal maxima nominal a 255 PWM (m/s).
    pub vel_max_lineal: f32,
}

impl Default for ParametrosRover {
    fn default() -> Self {
        Self {
            semi_longitud_l: 0.22, // 220 mm
            semi_ancho_w: 0.18,    // 180 mm
            radio_rueda: 0.045,    // 45 mm (rueda 90 mm)
            vel_max_lineal: 0.35,  // 0.35 m/s (~1.26 km/h)
        }
    }
}

/// Estado instantaneo de la pose y dinamica del vehiculo en el plano del mundo.
#[derive(Debug, Clone, Copy)]
pub struct PoseSimulada {
    /// Posicion X en metros (este / derecha en el plano).
    pub x: f32,
    /// Posicion Y en metros (norte / adelante en el plano).
    pub y: f32,
    /// Orientacion de guiñada (yaw) en radianes. 0 = Apuntando al Norte (+Y).
    pub theta_rad: f32,
    /// Modulo de la velocidad lineal neta en m/s.
    pub vel_lineal: f32,
    /// Velocidad angular de guiñada (yaw rate) en rad/s.
    pub omega_rad_s: f32,
    /// Radio de curvatura instantaneo en metros (infinito si es movimiento rectilineo).
    pub radio_giro: f32,
}

impl Default for PoseSimulada {
    fn default() -> Self {
        Self {
            x: 0.0,
            y: 0.0,
            theta_rad: 0.0,
            vel_lineal: 0.0,
            omega_rad_s: 0.0,
            radio_giro: f32::INFINITY,
        }
    }
}

/// Simulador cinematico 2D para navegacion en entorno plano ideal.
pub struct SimuladorPlano {
    pub parametros: ParametrosRover,
    pub pose: PoseSimulada,
    pub trayectoria: Vec<Pos2>,
    pub activo: bool,
    pub distancia_acumulada_m: f32,
    ultimo_tiempo_tick: Option<std::time::Instant>,
}

impl Default for SimuladorPlano {
    fn default() -> Self {
        Self::new()
    }
}

impl SimuladorPlano {
    pub fn new() -> Self {
        let mut sim = Self {
            parametros: ParametrosRover::default(),
            pose: PoseSimulada::default(),
            trayectoria: Vec::with_capacity(2000),
            activo: true,
            distancia_acumulada_m: 0.0,
            ultimo_tiempo_tick: None,
        };
        sim.trayectoria.push(Pos2::new(0.0, 0.0));
        sim
    }

    /// Reinicia la pose al origen (0, 0) con orientacion neutra y borra la trayectoria.
    pub fn reiniciar(&mut self) {
        self.pose = PoseSimulada::default();
        self.distancia_acumulada_m = 0.0;
        self.trayectoria.clear();
        self.trayectoria.push(Pos2::new(0.0, 0.0));
        self.ultimo_tiempo_tick = None;
    }

    /// Limpia unicamente la traza historica de puntos sin alterar la posicion actual.
    pub fn limpiar_trayectoria(&mut self) {
        self.trayectoria.clear();
        self.trayectoria.push(Pos2::new(self.pose.x, self.pose.y));
    }

    /// Integra un paso de tiempo cinematico a partir del estado de consigna actual.
    pub fn tick(&mut self, estado: &EstadoChasis, dt_manual: Option<f32>) {
        if !self.activo {
            return;
        }

        let dt = if let Some(dt_val) = dt_manual {
            dt_val
        } else {
            let ahora = std::time::Instant::now();
            let dt_calculado = if let Some(ant) = self.ultimo_tiempo_tick {
                ahora.duration_since(ant).as_secs_f32().clamp(0.001, 0.1)
            } else {
                0.033
            };
            self.ultimo_tiempo_tick = Some(ahora);
            dt_calculado
        };

        // Velocidad lineal ideal de cada lateral (m/s)
        let v_izq = (estado.traccion_izq as f32 / 255.0) * self.parametros.vel_max_lineal;
        let v_der = (estado.traccion_der as f32 / 255.0) * self.parametros.vel_max_lineal;

        let l = self.parametros.semi_longitud_l;
        let w = self.parametros.semi_ancho_w;

        // Angulos de las 4 esquinas convertidos a desviacion respecto al frente (radianes)
        // 90 deg = 0 rad, <90 deg (ej 60) = giro a derecha (+rad), >90 deg (ej 120) = giro a izquierda (-rad)
        let delta_s1 = (90.0 - estado.servos.s1 as f32).to_radians(); // FL
        let delta_s2 = (90.0 - estado.servos.s2 as f32).to_radians(); // FR
        let _delta_s3 = (90.0 - estado.servos.s3 as f32).to_radians(); // RL
        let _delta_s4 = (90.0 - estado.servos.s4 as f32).to_radians(); // RR

        let cmd = estado.comando_nombre;

        if cmd == "STOP" || (v_izq.abs() < 1e-4 && v_der.abs() < 1e-4) {
            // Vehiculo detenido
            self.pose.vel_lineal = 0.0;
            self.pose.omega_rad_s = 0.0;
            self.pose.radio_giro = f32::INFINITY;
            return;
        }

        let (vx_local, vy_local, omega, radio) = if cmd == "PIVOT_IZQ" || cmd == "PIVOT_DER" || cmd == "POINT_IZQ" || cmd == "POINT_DER" {
            // 1. Giro sobre el propio eje (Point Turn): ICR en (0, 0)
            // Horario (CW, Der): v_izq > 0, v_der < 0 => om > 0
            // Antihorario (CCW, Izq): v_izq < 0, v_der > 0 => om < 0
            let r_esquina = (l * l + w * w).sqrt();
            let om = (v_izq - v_der) / (2.0 * r_esquina);
            (0.0f32, 0.0f32, om, 0.0f32)
        } else if cmd.starts_with("CRAB") {
            // 2. Modo Cangrejo: traslacion en paralelo sin rotacion
            let v_avg = (v_izq + v_der) / 2.0;
            let ang_marcha = delta_s1;
            (v_avg * ang_marcha.sin(), v_avg * ang_marcha.cos(), 0.0f32, f32::INFINITY)
        } else {
            // 3. Conduccion coordinada Ackermann 4WS o marcha recta
            let v_avg = (v_izq + v_der) / 2.0;
            let delta_delantero_promedio = (delta_s1 + delta_s2) / 2.0;

            if delta_delantero_promedio.abs() < 0.015 {
                // Marcha recta
                let om = (v_izq - v_der) / (2.0 * w); // Correccion diferencial por trims
                (0.0f32, v_avg, om, f32::INFINITY)
            } else {
                // Curva Ackermann 4WS: centro de rotacion en eje medio (y = 0)
                let r_centro = l / delta_delantero_promedio.tan();
                let om = v_avg / r_centro;
                (0.0f32, v_avg, om, r_centro.abs())
            }
        };

        // Actualizar pose en el mundo (integracion numerica Euler)
        let theta_ant = self.pose.theta_rad;
        self.pose.theta_rad += omega * dt;

        // Normalizar rumbo a [-PI, PI]
        while self.pose.theta_rad > std::f32::consts::PI {
            self.pose.theta_rad -= 2.0 * std::f32::consts::PI;
        }
        while self.pose.theta_rad < -std::f32::consts::PI {
            self.pose.theta_rad += 2.0 * std::f32::consts::PI;
        }

        // Transformar velocidad local a marco del mundo:
        // +Y mundo es Norte (adelante cuando theta = 0)
        // +X mundo es Este (derecha cuando theta = 0)
        let theta_medio = theta_ant + omega * (dt * 0.5);
        let cos_t = theta_medio.cos();
        let sin_t = theta_medio.sin();

        let dx_mundo = vx_local * cos_t + vy_local * sin_t;
        let dy_mundo = -vx_local * sin_t + vy_local * cos_t;

        self.pose.x += dx_mundo * dt;
        self.pose.y += dy_mundo * dt;

        let dist_paso = (dx_mundo * dx_mundo + dy_mundo * dy_mundo).sqrt() * dt;
        self.distancia_acumulada_m += dist_paso;

        self.pose.vel_lineal = (vx_local * vx_local + vy_local * vy_local).sqrt();
        self.pose.omega_rad_s = omega;
        self.pose.radio_giro = radio;

        // Almacenar punto en trayectoria si se desplazo al menos 2 cm
        let ultimo_pos = self.trayectoria.last().copied().unwrap_or(Pos2::new(0.0, 0.0));
        let dx_hist = self.pose.x - ultimo_pos.x;
        let dy_hist = self.pose.y - ultimo_pos.y;
        if (dx_hist * dx_hist + dy_hist * dy_hist).sqrt() >= 0.02 {
            if self.trayectoria.len() >= 2000 {
                self.trayectoria.remove(0);
            }
            self.trayectoria.push(Pos2::new(self.pose.x, self.pose.y));
        }
    }
}
