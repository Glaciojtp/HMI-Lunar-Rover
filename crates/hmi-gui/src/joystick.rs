//! Modulo de Monitor, Decodificacion y Simulacion Virtual de Joystick / Mandos.
//!
//! Permite:
//! - Visualizar y depurar los estados analógicos y digitales de mandos de radiocontrol.
//! - Simular interactivamente la deflexion de sticks con el raton o teclado antes de conectar el rover real.
//! - Decodificar en tiempo real que se recibe y que deberia hacer cada accion del vehiculo.
//! - Parsear telemetria serie proveniente de mandos fisicos autonomos (Arduino Nano).

use egui::{Color32, FontId, Pos2, Stroke, Vec2};
use crate::kinematics::{EstadoChasis, TeclasEstado};

/// Estado de los ejes analogicos y pulsadores del mando de radiocontrol.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct JoystickEstado {
    /// Stick 1 (Izquierdo) - Eje X: [-1.0 (Izq), +1.0 (Der)] (Direccion / Giro)
    pub stick1_x: f32,
    /// Stick 1 (Izquierdo) - Eje Y: [-1.0 (Reversa), +1.0 (Avance)] (Traccion)
    pub stick1_y: f32,
    /// Stick 2 (Derecho) - Eje X: [-1.0 (Giro Eje Izq), +1.0 (Giro Eje Der)] (Point Turn)
    pub stick2_x: f32,
    /// Stick 2 (Derecho) - Eje Y: [-1.0 (Bajar), +1.0 (Subir)] (Auxiliar / Pitch LiDAR)
    pub stick2_y: f32,
    /// Potenciometro Maestro de Potencia: [0.0, 1.0] (0% a 100% PWM)
    pub pot_master: f32,
    /// Pulsador Stick 1 (SW1): Alternar Modo Cangrejo
    pub sw_stick1: bool,
    /// Pulsador Stick 2 (SW2): Centrar Servos a 90 deg
    pub sw_stick2: bool,
    /// Boton E-STOP: Parada de Emergencia fisica
    pub btn_estop: bool,
    /// Switch 360: Servos 360 deg continuos
    pub sw_360: bool,
    /// Boton Macro Giro Sobre Eje Izquierda (Q)
    pub btn_piv_izq: bool,
    /// Boton Macro Giro Sobre Eje Derecha (E)
    pub btn_piv_der: bool,
}

impl Default for JoystickEstado {
    fn default() -> Self {
        Self {
            stick1_x: 0.0,
            stick1_y: 0.0,
            stick2_x: 0.0,
            stick2_y: 0.0,
            pot_master: 1.0,
            sw_stick1: false,
            sw_stick2: false,
            btn_estop: false,
            sw_360: false,
            btn_piv_izq: false,
            btn_piv_der: false,
        }
    }
}

impl JoystickEstado {
    /// Sincroniza el estado virtual del joystick a partir de las teclas de pilotaje.
    pub fn actualizar_desde_teclas(&mut self, teclas: &TeclasEstado) {
        if teclas.space {
            self.btn_estop = true;
            self.stick1_x = 0.0;
            self.stick1_y = 0.0;
            self.stick2_x = 0.0;
            self.btn_piv_izq = false;
            self.btn_piv_der = false;
            return;
        }

        self.btn_estop = false;

        // Stick 1: Y = Traccion (W/S), X = Direccion (A/D)
        let mut y = 0.0f32;
        if teclas.w { y += 1.0; }
        if teclas.s { y -= 1.0; }
        self.stick1_y = y;

        let mut x = 0.0f32;
        if teclas.d { x += 1.0; }
        if teclas.a { x -= 1.0; }
        self.stick1_x = x;

        // Stick 2: X = Giro sobre eje (Q/E)
        let mut x2 = 0.0f32;
        if teclas.e { x2 += 1.0; }
        if teclas.q { x2 -= 1.0; }
        self.stick2_x = x2;
        self.btn_piv_izq = teclas.q;
        self.btn_piv_der = teclas.e;
    }

    /// Intenta parsear una trama serie proveniente del mando fisico autonomo en formato CSV.
    /// Formato esperado: `JOY,s1_x,s1_y,s2_x,s2_y,pot,estop,sw1,sw2`
    pub fn parsear_linea_csv(&mut self, linea: &str) -> bool {
        let partes: Vec<&str> = linea.trim().split(',').collect();
        if partes.is_empty() || partes[0] != "JOY" {
            return false;
        }

        if partes.len() >= 6 {
            if let Ok(v) = partes[1].parse::<f32>() { self.stick1_x = (v / 512.0 - 1.0).clamp(-1.0, 1.0); }
            if let Ok(v) = partes[2].parse::<f32>() { self.stick1_y = (v / 512.0 - 1.0).clamp(-1.0, 1.0); }
            if let Ok(v) = partes[3].parse::<f32>() { self.stick2_x = (v / 512.0 - 1.0).clamp(-1.0, 1.0); }
            if let Ok(v) = partes[4].parse::<f32>() { self.stick2_y = (v / 512.0 - 1.0).clamp(-1.0, 1.0); }
            if let Ok(v) = partes[5].parse::<f32>() { self.pot_master = (v / 1023.0).clamp(0.0, 1.0); }
            if partes.len() >= 7 {
                self.btn_estop = partes[6] == "1";
            }
            return true;
        }
        false
    }

    /// Genera la descripcion tecnica de la accion que el rover deberia ejecutar con este estado.
    pub fn interpretar_accion(estado: &EstadoChasis, radio_icr: f32, vel_lineal: f32) -> String {
        let cmd = estado.comando_nombre;

        if cmd == "STOP" {
            return "PARADA INMEDIATA: Consigna 0 PWM en los 6 motores. Frenado activo.".to_string();
        }

        if cmd == "NEUTRO" {
            return "EN ESPERA: Sin consigna de traccion (0 PWM). Posicion de servos en reposo.".to_string();
        }

        if cmd == "PIVOT_IZQ" {
            return format!(
                "GIRO SOBRE EL EJE (ANTIHORARIO / IZQUIERDA): Traccion contrarrotativa (-{} / +{}). Servos en tangencia (45 deg / 135 deg). Arrastre lateral en ruedas M2 y M5.",
                estado.traccion_izq.abs(), estado.traccion_der.abs()
            );
        }

        if cmd == "PIVOT_DER" {
            return format!(
                "GIRO SOBRE EL EJE (HORARIO / DERECHA): Traccion contrarrotativa (+{} / -{}). Servos en tangencia (135 deg / 45 deg). Arrastre lateral en ruedas M2 y M5.",
                estado.traccion_izq.abs(), estado.traccion_der.abs()
            );
        }

        if cmd.starts_with("CRAB") {
            return format!(
                "MODO CANGREJO: Traslacion diagonal o transversal pura a {:.2} m/s. Rumbo constante. Servos paralelos a {} deg.",
                vel_lineal, estado.servos.s1
            );
        }

        if cmd == "W" {
            return format!("AVANCE RECTO: Traccion simetrica (+{} PWM) a {:.2} m/s. Eje longitudinal alineado.", estado.traccion_izq, vel_lineal);
        }

        if cmd == "S" {
            return format!("REVERSA RECTA: Traccion simetrica en retroceso (-{} PWM) a {:.2} m/s.", estado.traccion_izq.abs(), vel_lineal);
        }

        if cmd == "W_A" {
            let r_str = if radio_icr.is_infinite() { "Inf".to_string() } else { format!("{:.2} m", radio_icr) };
            return format!(
                "CURVA ACKERMANN IZQUIERDA: Avance a {:.2} m/s con radio ICR {}. Reduccion diferencial izquierda (+{} / +{}). Servos frontales a 120 deg, traseros a 60 deg.",
                vel_lineal, r_str, estado.traccion_izq, estado.traccion_der
            );
        }

        if cmd == "W_D" {
            let r_str = if radio_icr.is_infinite() { "Inf".to_string() } else { format!("{:.2} m", radio_icr) };
            return format!(
                "CURVA ACKERMANN DERECHA: Avance a {:.2} m/s con radio ICR {}. Reduccion diferencial derecha (+{} / +{}). Servos frontales a 60 deg, traseros a 120 deg.",
                vel_lineal, r_str, estado.traccion_izq, estado.traccion_der
            );
        }

        if cmd == "S_A" {
            return format!(
                "REVERSA CON CURVA IZQUIERDA: Retroceso con direccion Ackermann. Traccion (-{} / -{}).",
                estado.traccion_izq.abs(), estado.traccion_der.abs()
            );
        }

        if cmd == "S_D" {
            return format!(
                "REVERSA CON CURVA DERECHA: Retroceso con direccion Ackermann. Traccion (-{} / -{}).",
                estado.traccion_izq.abs(), estado.traccion_der.abs()
            );
        }

        format!("MANIOBRA: Modo {} | Comando [{}] | Traccion ({}/{})", estado.comando_nombre, cmd, estado.traccion_izq, estado.traccion_der)
    }

    /// Dibuja un widget de stick analogico interactivo con reticula y circulo de deflexion.
    pub fn dibujar_widget_stick(
        ui: &mut egui::Ui,
        radio: f32,
        val_x: &mut f32,
        val_y: &mut f32,
        titulo: &str,
        color_puck: Color32,
    ) -> bool {
        let diametro = radio * 2.0;
        let size = Vec2::new(diametro + 16.0, diametro + 24.0);
        let (response, painter) = ui.allocate_painter(size, egui::Sense::drag());
        let rect = response.rect;
        let center = Pos2::new(rect.center().x, rect.top() + radio + 4.0);

        // Control interactivo por arrastre del raton
        let mut interactuado = false;
        if response.dragged() {
            if let Some(pos_mouse) = response.interact_pointer_pos() {
                let dx = (pos_mouse.x - center.x) / radio;
                let dy = -(pos_mouse.y - center.y) / radio; // Invertir Y para que arriba sea +
                *val_x = dx.clamp(-1.0, 1.0);
                *val_y = dy.clamp(-1.0, 1.0);
                interactuado = true;
            }
        } else if response.drag_stopped() {
            // Retorno automatico al centro al soltar el raton (resorte virtual)
            *val_x = 0.0;
            *val_y = 0.0;
            interactuado = true;
        }

        // Fondo del stick
        painter.circle_filled(center, radio, Color32::from_rgb(20, 24, 36));
        painter.circle_stroke(center, radio, Stroke::new(1.5f32, Color32::from_rgb(51, 65, 85)));

        // Reticula en cruz (ejes X e Y neutrales)
        painter.line_segment(
            [Pos2::new(center.x - radio, center.y), Pos2::new(center.x + radio, center.y)],
            Stroke::new(1.0f32, Color32::from_rgb(40, 50, 70)),
        );
        painter.line_segment(
            [Pos2::new(center.x, center.y - radio), Pos2::new(center.x, center.y + radio)],
            Stroke::new(1.0f32, Color32::from_rgb(40, 50, 70)),
        );

        // Posicion del mando fisico o virtual (puck)
        let puck_x = center.x + (*val_x * radio * 0.85);
        let puck_y = center.y - (*val_y * radio * 0.85);
        let puck_center = Pos2::new(puck_x, puck_y);

        // Linea vector desde el centro al puck
        if val_x.abs() > 0.05 || val_y.abs() > 0.05 {
            painter.line_segment([center, puck_center], Stroke::new(1.5f32, color_puck));
        }

        // Indicador del puck
        painter.circle_filled(puck_center, 9.0f32, color_puck);
        painter.circle_stroke(puck_center, 9.0f32, Stroke::new(1.5f32, Color32::WHITE));

        // Titulo y valores numericos
        painter.text(
            Pos2::new(rect.center().x, rect.bottom() - 6.0),
            egui::Align2::CENTER_CENTER,
            format!("{}\nX:{:+.2} Y:{:+.2}", titulo, *val_x, *val_y),
            FontId::monospace(8.5),
            Color32::from_rgb(203, 213, 225),
        );

        interactuado
    }
}
