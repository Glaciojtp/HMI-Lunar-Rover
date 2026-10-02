//! Modulo de la Aplicacion de Escritorio Nativa (eframe / egui).
//!
//! Implementa la interfaz grafica completa:
//! - Barra superior de conexion y handshake.
//! - Panel de trims para los 6 motores Rocker-Bogie (M1..M6).
//! - Panel de control de los 4 servos independientes (S1..S4) con restriccion a [10, 170] grados.
//! - Captura de eventos de teclado (WASD, QE, Parada de emergencia con Barra Espaciadora).
//! - Canvas 2D en tiempo real con orientacion de ruedas y vectores de traccion.
//! - Consola de telemetria y eventos con scroll automatico.
//! - Prohibicion estricta de emojis (nomenclatura sobria con corchetes).

use std::time::{Duration, Instant};

use eframe::egui::{
    self, Color32, FontId, Key, Pos2, Rect, Rounding, Stroke, Vec2,
};
use protocol_rover::PaqueteRover;

use crate::kinematics::{
    calcular_cinematica, generar_paquete_rover, AngulosServos, EstadoChasis, ModoConduccion,
    TeclasEstado, TrimsMotores,
};
use crate::profiles::{DiscoveredPort, HandshakeInfo, HardwareProfileRegistry, PERFIL_DEFAULT_ID};
use crate::serial_worker::{SerialEvent, SerialWorkerHandle};

/// Entrada de registro en la consola de telemetria.
#[derive(Debug, Clone)]
pub struct RegistroLog {
    pub hora: String,
    pub etiqueta: &'static str,
    pub texto: String,
    pub color: Color32,
}

/// Estado y estadisticas de operacion de la aplicacion.
#[derive(Debug, Clone, Default)]
pub struct EstadisticasApp {
    pub paquetes_tx: u64,
    pub lineas_rx: u64,
    pub bytes_tx: u64,
    pub tasa_tx_hz: f32,
}

/// Estructura principal de la aplicacion eframe / egui.
pub struct RoverApp {
    // Comunicacion serial y hardware
    registro_perfiles: HardwareProfileRegistry,
    serial_worker: SerialWorkerHandle,
    puertos_disponibles: Vec<DiscoveredPort>,
    puerto_seleccionado: String,
    baudrate_seleccionado: u32,
    perfil_seleccionado_id: String,
    conectado: bool,
    puerto_conectado: Option<String>,
    handshake: Option<HandshakeInfo>,

    // Control y cinematica
    modo: ModoConduccion,
    teclas: TeclasEstado,
    trims: TrimsMotores,
    servos_manuales: AngulosServos,
    invertir_servos: bool,
    modo_binario: bool,
    transmision_continua: bool,

    // Estado calculado actual
    estado_chasis: EstadoChasis,
    ultimo_paquete_tx: Option<PaqueteRover>,

    // Telemetria y visualizacion
    logs: Vec<RegistroLog>,
    texto_comando_personalizado: String,
    estadisticas: EstadisticasApp,
    ultimo_envio_tiempo: Instant,
    ultimo_calculo_tasa: Instant,
    paquetes_en_segundo: u32,
}

impl Default for RoverApp {
    fn default() -> Self {
        let registry = HardwareProfileRegistry::new();
        let default_profile_id = PERFIL_DEFAULT_ID.to_string();
        let serial_worker = SerialWorkerHandle::start();

        let mut app = Self {
            registro_perfiles: registry,
            serial_worker,
            puertos_disponibles: Vec::new(),
            puerto_seleccionado: String::new(),
            baudrate_seleccionado: 115200,
            perfil_seleccionado_id: default_profile_id,
            conectado: false,
            puerto_conectado: None,
            handshake: None,

            modo: ModoConduccion::Ackermann,
            teclas: TeclasEstado::default(),
            trims: TrimsMotores::default(),
            servos_manuales: AngulosServos::default(),
            invertir_servos: false,
            modo_binario: false,
            transmision_continua: true,

            estado_chasis: EstadoChasis {
                traccion_izq: 0,
                traccion_der: 0,
                servos: AngulosServos::default(),
                pwms_motores: [0; 6],
                comando_nombre: "NEUTRO",
            },
            ultimo_paquete_tx: None,

            logs: Vec::new(),
            texto_comando_personalizado: String::new(),
            estadisticas: EstadisticasApp::default(),
            ultimo_envio_tiempo: Instant::now(),
            ultimo_calculo_tasa: Instant::now(),
            paquetes_en_segundo: 0,
        };

        app.agregar_log(
            "[SYS]",
            "HMI Rover Lunar V2.0 inicializado. Perfil: ARDUINO_NANO_ESP32",
            Color32::from_rgb(0, 245, 212),
        );
        app.refrescar_puertos();
        app
    }
}

impl RoverApp {
    /// Agrega una entrada a la consola de logs interna.
    pub fn agregar_log(&mut self, etiqueta: &'static str, texto: impl Into<String>, color: Color32) {
        let now = Instant::now();
        let dur = now.elapsed();
        let hora = format!("{:02}.{:03}", dur.as_secs() % 100, dur.subsec_millis());

        if self.logs.len() >= 500 {
            self.logs.remove(0);
        }

        self.logs.push(RegistroLog {
            hora,
            etiqueta,
            texto: texto.into(),
            color,
        });
    }

    /// Escanea los puertos seriales e identifica perfiles de hardware pasivos por USB VID:PID.
    pub fn refrescar_puertos(&mut self) {
        self.puertos_disponibles = self.registro_perfiles.scan_ports();

        if let Some(primer_puerto) = self.puertos_disponibles.first() {
            if self.puerto_seleccionado.is_empty()
                || !self
                    .puertos_disponibles
                    .iter()
                    .any(|p| p.port_name == self.puerto_seleccionado)
            {
                self.puerto_seleccionado = primer_puerto.port_name.clone();

                if let Some(perfil) = primer_puerto.detected_profile {
                    self.perfil_seleccionado_id = perfil.id.to_string();
                    self.agregar_log(
                        "[SYS]",
                        format!(
                            "Autodeteccion pasiva en {}: perfil {}",
                            primer_puerto.port_name, perfil.nombre
                        ),
                        Color32::from_rgb(56, 176, 0),
                    );
                }
            }
        }

        self.agregar_log(
            "[SYS]",
            format!("Puertos detectados: {}", self.puertos_disponibles.len()),
            Color32::from_rgb(148, 163, 184),
        );
    }

    /// Conmuta la conexion serial con el puerto y baudrate actualmente seleccionados.
    pub fn toggle_conexion(&mut self) {
        if self.conectado {
            self.serial_worker.disconnect();
            self.conectado = false;
            self.puerto_conectado = None;
            self.handshake = None;
        } else {
            if self.puerto_seleccionado.is_empty() {
                self.agregar_log(
                    "[ERR]",
                    "No hay ningun puerto COM seleccionado",
                    Color32::from_rgb(248, 113, 113),
                );
                return;
            }
            self.agregar_log(
                "[SYS]",
                format!(
                    "Conectando a {} a {} baudios...",
                    self.puerto_seleccionado, self.baudrate_seleccionado
                ),
                Color32::from_rgb(255, 159, 28),
            );
            self.serial_worker
                .connect(&self.puerto_seleccionado, self.baudrate_seleccionado);
        }
    }

    /// Envia el comando de parada de emergencia inmediata.
    pub fn parada_emergencia(&mut self) {
        self.teclas = TeclasEstado::default();
        self.teclas.space = true;
        self.serial_worker.send_stop();
        self.servos_manuales.centrar();
        self.estado_chasis = calcular_cinematica(
            &self.teclas,
            self.modo,
            &self.trims,
            &self.servos_manuales,
            self.invertir_servos,
        );
        self.agregar_log(
            "[STOP]",
            "PARADA DE EMERGENCIA ACTIVADA: Consigna 0 PWM y detencion total",
            Color32::from_rgb(248, 113, 113),
        );
    }

    /// Procesa eventos asincronos recibidos desde el hilo del trabajador serial.
    fn procesar_eventos_serial(&mut self) {
        while let Some(evento) = self.serial_worker.try_recv_event() {
            match evento {
                SerialEvent::Connected { port, baud_rate } => {
                    self.conectado = true;
                    self.puerto_conectado = Some(port.clone());
                    self.agregar_log(
                        "[CONECTADO]",
                        format!("Enlace activo en {} a {} baudios", port, baud_rate),
                        Color32::from_rgb(56, 176, 0),
                    );
                    // Disparar handshake activo al conectar
                    self.serial_worker.send_raw("IDENT\n");
                }
                SerialEvent::Disconnected => {
                    self.conectado = false;
                    self.puerto_conectado = None;
                    self.handshake = None;
                    self.agregar_log(
                        "[DESCONECTADO]",
                        "Puerto serial liberado",
                        Color32::from_rgb(248, 113, 113),
                    );
                }
                SerialEvent::LineReceived(linea) => {
                    self.estadisticas.lineas_rx += 1;
                    // Evaluar si es respuesta de handshake IDENT
                    if linea.starts_with("ID:") {
                        match self.registro_perfiles.resolve_handshake(&linea) {
                            Ok((perfil, info)) => {
                                self.agregar_log(
                                    "[IDENT]",
                                    format!(
                                        "Placa: {} | Rol: {} | Version: {} (Perfil: {})",
                                        info.placa, info.rol, info.version, perfil.nombre
                                    ),
                                    Color32::from_rgb(0, 245, 212),
                                );
                                self.perfil_seleccionado_id = perfil.id.to_string();
                                self.handshake = Some(info);
                            }
                            Err(e) => {
                                self.agregar_log(
                                    "[RX]",
                                    format!("{} (Error handshake: {})", linea, e),
                                    Color32::from_rgb(248, 113, 113),
                                );
                            }
                        }
                    } else if linea.starts_with("PONG:") {
                        self.agregar_log(
                            "[PONG]",
                            linea,
                            Color32::from_rgb(56, 176, 0),
                        );
                    } else {
                        self.agregar_log(
                            "[RX]",
                            linea,
                            Color32::from_rgb(203, 213, 225),
                        );
                    }
                }
                SerialEvent::PacketSent(pkt) => {
                    self.estadisticas.paquetes_tx += 1;
                    self.paquetes_en_segundo += 1;
                    self.ultimo_paquete_tx = Some(pkt);
                }
                SerialEvent::BytesWritten(n) => {
                    self.estadisticas.bytes_tx += n as u64;
                }
                SerialEvent::Error(err) => {
                    self.agregar_log(
                        "[ERR]",
                        err,
                        Color32::from_rgb(248, 113, 113),
                    );
                }
                SerialEvent::Info(info) => {
                    self.agregar_log(
                        "[SYS]",
                        info,
                        Color32::from_rgb(148, 163, 184),
                    );
                }
            }
        }
    }

    /// Captura y mapea las pulsaciones de teclado para pilotaje.
    fn procesar_teclado(&mut self, ctx: &egui::Context) {
        if ctx.wants_keyboard_input() {
            return;
        }

        ctx.input(|i| {
            // Parada de emergencia con Barra Espaciadora
            if i.key_pressed(Key::Space) {
                self.parada_emergencia();
                return;
            }

            // WASD y QE
            self.teclas.w = i.key_down(Key::W);
            self.teclas.a = i.key_down(Key::A);
            self.teclas.s = i.key_down(Key::S);
            self.teclas.d = i.key_down(Key::D);
            self.teclas.q = i.key_down(Key::Q);
            self.teclas.e = i.key_down(Key::E);
            self.teclas.space = false;
        });

        // Recalcular estado cinematico
        self.estado_chasis = calcular_cinematica(
            &self.teclas,
            self.modo,
            &self.trims,
            &self.servos_manuales,
            self.invertir_servos,
        );

        // Si hay una orden de direccion por teclado en un modo coordinado (Ackermann/PointTurn/Crab),
        // sincronizar los deslizadores manuales con los angulos activos del chasis
        if self.teclas.hay_movimiento() && self.modo != ModoConduccion::Manual {
            self.servos_manuales = self.estado_chasis.servos;
        }
    }

    /// Transmite la consigna de control al hardware a una frecuencia regular (20 Hz).
    fn procesar_transmision_periodica(&mut self) {
        let ahora = Instant::now();

        // Calculo de tasa Hz en tiempo real
        if ahora.duration_since(self.ultimo_calculo_tasa) >= Duration::from_secs(1) {
            self.estadisticas.tasa_tx_hz = self.paquetes_en_segundo as f32;
            self.paquetes_en_segundo = 0;
            self.ultimo_calculo_tasa = ahora;
        }

        // Intervalo de transmision 50 ms = 20 Hz continuo
        if self.conectado
            && ahora.duration_since(self.ultimo_envio_tiempo) >= Duration::from_millis(50)
        {
            if self.transmision_continua || self.teclas.hay_movimiento() {
                let pkt = generar_paquete_rover(&self.estado_chasis);
                self.serial_worker.send_packet(pkt);
                self.ultimo_envio_tiempo = ahora;
            }
        }
    }
}

impl eframe::App for RoverApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.procesar_eventos_serial();
        self.procesar_teclado(ctx);
        self.procesar_transmision_periodica();

        // Solicitar repintado continuo mientras este conectado para tasa 20 Hz
        if self.conectado {
            ctx.request_repaint_after(Duration::from_millis(40));
        }

        // =====================================================================
        // 1. BARRA SUPERIOR: CONEXION, IDENT Y ESTADO GENERAL
        // =====================================================================
        egui::TopBottomPanel::top("top_panel").show(ctx, |ui| {
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                ui.label(
                    egui::RichText::new("ROVER LUNAR CEPIT - ROCKER-BOGIE 6x6 HMI (RUST)")
                        .strong()
                        .color(Color32::from_rgb(0, 245, 212)),
                );

                ui.separator();

                // Insignia de perfil de hardware
                let perfil_nombre = self
                    .registro_perfiles
                    .get_profile(&self.perfil_seleccionado_id)
                    .map(|p| p.nombre)
                    .unwrap_or("Desconocido");
                ui.label(
                    egui::RichText::new(format!("[PERFIL: {}]", perfil_nombre))
                        .color(Color32::from_rgb(148, 163, 184)),
                );

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if self.conectado {
                        let puerto_str = self
                            .puerto_conectado
                            .as_deref()
                            .unwrap_or("COM");
                        ui.label(
                            egui::RichText::new(format!("[CONECTADO ({})]", puerto_str))
                                .strong()
                                .color(Color32::from_rgb(56, 176, 0)),
                        );
                    } else {
                        ui.label(
                            egui::RichText::new("[DESCONECTADO]")
                                .strong()
                                .color(Color32::from_rgb(248, 113, 113)),
                        );
                    }

                    if let Some(ref h) = self.handshake {
                        ui.label(
                            egui::RichText::new(format!("[ID: {}:{}:{}]", h.placa, h.rol, h.version))
                                .color(Color32::from_rgb(0, 245, 212)),
                        );
                    }
                });
            });

            ui.add_space(4.0);

            // Controles de seleccion de puerto, conexion y handshake
            ui.horizontal(|ui| {
                ui.label("Puerto:");

                egui::ComboBox::from_id_source("cb_puerto")
                    .selected_text(if self.puerto_seleccionado.is_empty() {
                        "Sin puertos"
                    } else {
                        &self.puerto_seleccionado
                    })
                    .show_ui(ui, |ui| {
                        for p in &self.puertos_disponibles {
                            let desc = if let Some(perfil) = p.detected_profile {
                                format!("{} ({})", p.port_name, perfil.nombre)
                            } else {
                                p.port_name.clone()
                            };
                            ui.selectable_value(&mut self.puerto_seleccionado, p.port_name.clone(), desc);
                        }
                    });

                if ui.button("[Refrescar]").clicked() {
                    self.refrescar_puertos();
                }

                ui.separator();

                ui.label("Baud:");
                egui::ComboBox::from_id_source("cb_baud")
                    .selected_text(format!("{}", self.baudrate_seleccionado))
                    .show_ui(ui, |ui| {
                        ui.selectable_value(&mut self.baudrate_seleccionado, 115200, "115200");
                        ui.selectable_value(&mut self.baudrate_seleccionado, 57600, "57600");
                        ui.selectable_value(&mut self.baudrate_seleccionado, 9600, "9600");
                    });

                let btn_conectar_texto = if self.conectado {
                    "[DESCONECTAR]"
                } else {
                    "[CONECTAR]"
                };
                if ui.button(btn_conectar_texto).clicked() {
                    self.toggle_conexion();
                }

                if ui.button("[IDENT]").clicked() {
                    self.serial_worker.send_raw("IDENT\n");
                    self.agregar_log(
                        "[TX]",
                        "Consulta de identidad: IDENT",
                        Color32::from_rgb(0, 245, 212),
                    );
                }

                if ui.button("[PING]").clicked() {
                    self.serial_worker.send_raw("PING\n");
                    self.agregar_log(
                        "[TX]",
                        "Test de conectividad: PING",
                        Color32::from_rgb(0, 245, 212),
                    );
                }

                ui.separator();

                ui.label("Modo:");
                let modo_previo = self.modo;
                egui::ComboBox::from_id_source("cb_modo")
                    .selected_text(self.modo.as_str())
                    .show_ui(ui, |ui| {
                        ui.selectable_value(&mut self.modo, ModoConduccion::Ackermann, "ACKERMANN");
                        ui.selectable_value(&mut self.modo, ModoConduccion::PointTurn, "POINT_TURN");
                        ui.selectable_value(&mut self.modo, ModoConduccion::Crab, "CRAB");
                        ui.selectable_value(&mut self.modo, ModoConduccion::Manual, "MANUAL");
                    });
                if self.modo != modo_previo {
                    match self.modo {
                        ModoConduccion::PointTurn => self.servos_manuales.preset_point_turn(),
                        ModoConduccion::Crab => self.servos_manuales.preset_crab(),
                        ModoConduccion::Ackermann => self.servos_manuales.centrar(),
                        ModoConduccion::Manual => {}
                    }
                    self.estado_chasis = calcular_cinematica(
                        &self.teclas,
                        self.modo,
                        &self.trims,
                        &self.servos_manuales,
                        self.invertir_servos,
                    );
                }

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let btn_stop = egui::Button::new(
                        egui::RichText::new("[PARADA DE EMERGENCIA (ESPACIO)]")
                            .strong()
                            .color(Color32::WHITE),
                    )
                    .fill(Color32::from_rgb(220, 38, 38));
                    if ui.add(btn_stop).clicked() {
                        self.parada_emergencia();
                    }
                });
            });
            ui.add_space(4.0);
        });

        // =====================================================================
        // 2. PANEL CENTRAL: COLUMNAS DE CONTROL, 2D CANVAS Y TELEMETRIA
        // =====================================================================
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.columns(2, |columns| {
                // -------------------------------------------------------------
                // COLUMNA IZQUIERDA: TRIMS Y SERVOS
                // -------------------------------------------------------------
                columns[0].vertical(|ui| {
                    // TARJETA 1: TRIMS DE TRACCION (6 MOTORES ROCKER-BOGIE)
                    egui::Frame::group(ui.style()).show(ui, |ui| {
                        ui.horizontal(|ui| {
                            ui.label(
                                egui::RichText::new("CALIBRACION Y TRIMS (6 MOTORES M1..M6)")
                                    .strong()
                                    .color(Color32::from_rgb(0, 245, 212)),
                            );
                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                if ui.button("[Reset Trims (100%)]").clicked() {
                                    self.trims.reset_trims();
                                }
                            });
                        });

                        ui.separator();

                        ui.columns(2, |subcols| {
                            // Subcolumna Lado Izquierdo
                            subcols[0].vertical(|ui| {
                                ui.label(
                                    egui::RichText::new("LADO IZQUIERDO (M1, M2, M3)")
                                        .strong()
                                        .color(Color32::from_rgb(226, 232, 240)),
                                );
                                ui.add(
                                    egui::Slider::new(&mut self.trims.m1, 0..=150)
                                        .text("M1 (Del. Izq) %"),
                                );
                                ui.add(
                                    egui::Slider::new(&mut self.trims.m2, 0..=150)
                                        .text("M2 (Medio Izq) %"),
                                );
                                ui.add(
                                    egui::Slider::new(&mut self.trims.m3, 0..=150)
                                        .text("M3 (Tras. Izq) %"),
                                );
                                ui.separator();
                                ui.add(
                                    egui::Slider::new(&mut self.trims.master_izq, 0..=255)
                                        .text("Master Izq (PWM)"),
                                );
                            });

                            // Subcolumna Lado Derecho
                            subcols[1].vertical(|ui| {
                                ui.label(
                                    egui::RichText::new("LADO DERECHO (M4, M5, M6)")
                                        .strong()
                                        .color(Color32::from_rgb(226, 232, 240)),
                                );
                                ui.add(
                                    egui::Slider::new(&mut self.trims.m4, 0..=150)
                                        .text("M4 (Del. Der) %"),
                                );
                                ui.add(
                                    egui::Slider::new(&mut self.trims.m5, 0..=150)
                                        .text("M5 (Medio Der) %"),
                                );
                                ui.add(
                                    egui::Slider::new(&mut self.trims.m6, 0..=150)
                                        .text("M6 (Tras. Der) %"),
                                );
                                ui.separator();
                                ui.add(
                                    egui::Slider::new(&mut self.trims.master_der, 0..=255)
                                        .text("Master Der (PWM)"),
                                );
                            });
                        });
                    });

                    ui.add_space(8.0);

                    // TARJETA 2: DIRECCION INDEPENDIENTE (4 SERVOMOTORES)
                    egui::Frame::group(ui.style()).show(ui, |ui| {
                        ui.label(
                            egui::RichText::new("DIRECCION INDEPENDIENTE (SERVOS S1..S4)")
                                .strong()
                                .color(Color32::from_rgb(0, 245, 212)),
                        );

                        ui.separator();

                        ui.columns(2, |subcols| {
                            subcols[0].vertical(|ui| {
                                ui.label("TREN DELANTERO");
                                ui.add(
                                    egui::Slider::new(&mut self.servos_manuales.s1, 10..=170)
                                        .text("S1: Del. Izq (deg)"),
                                );
                                ui.add(
                                    egui::Slider::new(&mut self.servos_manuales.s2, 10..=170)
                                        .text("S2: Del. Der (deg)"),
                                );
                            });

                            subcols[1].vertical(|ui| {
                                ui.label("TREN TRASERO");
                                ui.add(
                                    egui::Slider::new(&mut self.servos_manuales.s3, 10..=170)
                                        .text("S3: Tras. Izq (deg)"),
                                );
                                ui.add(
                                    egui::Slider::new(&mut self.servos_manuales.s4, 10..=170)
                                        .text("S4: Tras. Der (deg)"),
                                );
                            });
                        });

                        ui.add_space(4.0);

                        ui.horizontal_wrapped(|ui| {
                            if ui.button("[Centrar Servos (90 deg)]").clicked() {
                                self.servos_manuales.centrar();
                            }
                            if ui.button("[Preset Giro Sobre Eje]").clicked() {
                                self.servos_manuales.preset_point_turn();
                            }
                            if ui.button("[Preset Cangrejo (45 deg)]").clicked() {
                                self.servos_manuales.preset_crab();
                            }
                            if ui.checkbox(&mut self.invertir_servos, "Invertir Servos").changed() {
                                self.servos_manuales.invertir();
                            }
                            if ui
                                .checkbox(&mut self.modo_binario, "Modo Binario Estricto (6B)")
                                .changed()
                            {
                                self.serial_worker.set_binary_mode(self.modo_binario);
                            }
                        });
                    });

                    ui.add_space(8.0);

                    // TARJETA DE ESTADO CINEMATICO INSTANTANEO
                    egui::Frame::group(ui.style()).show(ui, |ui| {
                        ui.label(
                            egui::RichText::new("CONSIGNA DE CONTROL Y TELEMETRIA")
                                .strong()
                                .color(Color32::from_rgb(0, 245, 212)),
                        );
                        ui.separator();
                        ui.horizontal(|ui| {
                            ui.label(format!("Comando: [{}]", self.estado_chasis.comando_nombre));
                            ui.label(format!("Traccion Izq: {}", self.estado_chasis.traccion_izq));
                            ui.label(format!("Traccion Der: {}", self.estado_chasis.traccion_der));
                        });
                        ui.horizontal(|ui| {
                            let s = self.estado_chasis.servos;
                            ui.label(format!("Angulos: S1={} S2={} S3={} S4={}", s.s1, s.s2, s.s3, s.s4));
                        });
                        ui.horizontal(|ui| {
                            ui.label(format!(
                                "TX: {} paq ({:.1} Hz) | RX: {} lin | Bytes: {}",
                                self.estadisticas.paquetes_tx,
                                self.estadisticas.tasa_tx_hz,
                                self.estadisticas.lineas_rx,
                                self.estadisticas.bytes_tx
                            ));
                        });
                    });
                });

                // -------------------------------------------------------------
                // COLUMNA DERECHA: ESQUEMA 2D Y CONSOLA DE TELEMETRIA
                // -------------------------------------------------------------
                columns[1].vertical(|ui| {
                    // TARJETA 3: ESQUEMA 2D DEL CHASSIS ROCKER-BOGIE
                    egui::Frame::group(ui.style()).show(ui, |ui| {
                        ui.label(
                            egui::RichText::new("ESQUEMA 2D EN TIEMPO REAL (CANVAS ROCKER-BOGIE)")
                                .strong()
                                .color(Color32::from_rgb(0, 245, 212)),
                        );
                        ui.separator();

                        // Canvas 2D
                        let canvas_size = Vec2::new(320.0, 240.0);
                        let (response, painter) = ui.allocate_painter(canvas_size, egui::Sense::hover());
                        let rect = response.rect;

                        // Fondo del canvas
                        painter.rect_filled(rect, Rounding::same(6.0f32), Color32::from_rgb(22, 24, 34));
                        painter.rect_stroke(
                            rect,
                            Rounding::same(6.0f32),
                            Stroke::new(1.0f32, Color32::from_rgb(51, 65, 85)),
                        );

                        let center = rect.center();

                        // Dibujar cuerpo central del Rover
                        let body_rect = Rect::from_center_size(center, Vec2::new(56.0f32, 110.0f32));
                        painter.rect_filled(
                            body_rect,
                            Rounding::same(4.0f32),
                            Color32::from_rgb(33, 36, 51),
                        );
                        painter.rect_stroke(
                            body_rect,
                            Rounding::same(4.0f32),
                            Stroke::new(1.5f32, Color32::from_rgb(0, 245, 212)),
                        );

                        // Linea longitudinal de simetria y diferencial mecanico
                        painter.line_segment(
                            [
                                Pos2::new(center.x, body_rect.top() + 6.0f32),
                                Pos2::new(center.x, body_rect.bottom() - 6.0f32),
                            ],
                            Stroke::new(1.0f32, Color32::from_rgb(71, 85, 105)),
                        );

                        // Coordenadas relativas de las 6 ruedas
                        let dx = 58.0f32;
                        let dy_front = 54.0f32;
                        let dy_mid = 0.0f32;
                        let dy_rear = 54.0f32;

                        let pos_m1 = Pos2::new(center.x - dx, center.y - dy_front); // FL
                        let pos_m2 = Pos2::new(center.x - dx, center.y - dy_mid);   // ML
                        let pos_m3 = Pos2::new(center.x - dx, center.y + dy_rear);  // RL
                        let pos_m4 = Pos2::new(center.x + dx, center.y - dy_front); // FR
                        let pos_m5 = Pos2::new(center.x + dx, center.y - dy_mid);   // MR
                        let pos_m6 = Pos2::new(center.x + dx, center.y + dy_rear);  // RR

                        // Brazos de suspension Rocker-Bogie (enlaces mecanicos)
                        let stroke_arm = Stroke::new(2.0f32, Color32::from_rgb(100, 116, 139));
                        painter.line_segment([pos_m1, pos_m2], stroke_arm);
                        painter.line_segment([pos_m2, pos_m3], stroke_arm);
                        painter.line_segment([pos_m4, pos_m5], stroke_arm);
                        painter.line_segment([pos_m5, pos_m6], stroke_arm);
                        painter.line_segment([Pos2::new(center.x - 28.0f32, center.y), pos_m2], stroke_arm);
                        painter.line_segment([Pos2::new(center.x + 28.0f32, center.y), pos_m5], stroke_arm);

                        // Dibujar las 6 ruedas con orientacion y vectores
                        let s = self.estado_chasis.servos;
                        let pwms = self.estado_chasis.pwms_motores;

                        Self::dibujar_rueda(&painter, pos_m1, s.s1, pwms[0], "M1");
                        Self::dibujar_rueda(&painter, pos_m2, 90, pwms[1], "M2");
                        Self::dibujar_rueda(&painter, pos_m3, s.s3, pwms[2], "M3");
                        Self::dibujar_rueda(&painter, pos_m4, s.s2, pwms[3], "M4");
                        Self::dibujar_rueda(&painter, pos_m5, 90, pwms[4], "M5");
                        Self::dibujar_rueda(&painter, pos_m6, s.s4, pwms[5], "M6");
                    });

                    ui.add_space(8.0);

                    // TARJETA 4: CONSOLA DE TELEMETRIA Y LOGS
                    egui::Frame::group(ui.style()).show(ui, |ui| {
                        ui.horizontal(|ui| {
                            ui.label(
                                egui::RichText::new("CONSOLA DE EVENTOS Y TELEMETRIA")
                                    .strong()
                                    .color(Color32::from_rgb(0, 245, 212)),
                            );
                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                if ui.button("[Limpiar]").clicked() {
                                    self.logs.clear();
                                }
                            });
                        });

                        ui.separator();

                        // Area con scroll de registros
                        egui::ScrollArea::vertical()
                            .max_height(140.0)
                            .auto_shrink([false, false])
                            .stick_to_bottom(true)
                            .show(ui, |ui| {
                                for r in &self.logs {
                                    ui.horizontal(|ui| {
                                        ui.label(
                                            egui::RichText::new(&r.hora)
                                                .font(FontId::monospace(10.0))
                                                .color(Color32::from_rgb(100, 116, 139)),
                                        );
                                        ui.label(
                                            egui::RichText::new(r.etiqueta)
                                                .font(FontId::monospace(10.0))
                                                .color(r.color),
                                        );
                                        ui.label(
                                            egui::RichText::new(&r.texto)
                                                .font(FontId::monospace(10.0))
                                                .color(Color32::from_rgb(226, 232, 240)),
                                        );
                                    });
                                }
                            });

                        ui.separator();

                        // Envio de comando libre por consola
                        ui.horizontal(|ui| {
                            ui.label("Comando:");
                            let response = ui.add_sized(
                                [ui.available_width() - 80.0, 20.0],
                                egui::TextEdit::singleline(&mut self.texto_comando_personalizado)
                                    .hint_text("Ej: IDENT, PING, STOP, CMD,150,150,90,90"),
                            );

                            let enter_presionado = response.lost_focus() && ctx.input(|i| i.key_pressed(Key::Enter));
                            if (ui.button("[Enviar]").clicked() || enter_presionado)
                                && !self.texto_comando_personalizado.trim().is_empty()
                            {
                                let cmd = self.texto_comando_personalizado.trim().to_string();
                                self.serial_worker.send_raw(&cmd);
                                self.agregar_log(
                                    "[TX]",
                                    &cmd,
                                    Color32::from_rgb(0, 245, 212),
                                );
                                self.texto_comando_personalizado.clear();
                            }
                        });
                    });
                });
            });
        });
    }
}

impl RoverApp {
    /// Renderiza una rueda rotada segun el angulo de su servomotor y dibuja su vector de velocidad con flecha.
    fn dibujar_rueda(
        painter: &egui::Painter,
        pos: Pos2,
        angulo_deg: u8,
        pwm: i16,
        label: &str,
    ) {
        // En nuestro marco y en Python HMI:
        // 90 deg es recto (rad = 0).
        // Menor a 90 deg (ej 60 deg) inclina hacia la derecha (+X).
        // Mayor a 90 deg (ej 120 deg) inclina hacia la izquierda (-X).
        let rad = (90.0 - angulo_deg as f32).to_radians();

        let w_half = 7.0f32;
        let h_half = 14.0f32;

        let corners = [
            Vec2::new(-w_half, -h_half),
            Vec2::new(w_half, -h_half),
            Vec2::new(w_half, h_half),
            Vec2::new(-w_half, h_half),
        ];

        let rotated_points: Vec<Pos2> = corners
            .iter()
            .map(|&c| {
                let rx = c.x * rad.cos() - c.y * rad.sin();
                let ry = c.x * rad.sin() + c.y * rad.cos();
                Pos2::new(pos.x + rx, pos.y + ry)
            })
            .collect();

        // Color de la rueda segun potencia y sentido (congruente con Python HMI)
        let wheel_color = if pwm > 0 {
            Color32::from_rgb(56, 176, 0) // Avance: Verde (#38b000)
        } else if pwm < 0 {
            Color32::from_rgb(255, 159, 28) // Reversa: Naranja (#ff9f1c)
        } else {
            Color32::from_rgb(100, 116, 139) // Detenido: Slate neutro (#64748b)
        };

        painter.add(egui::Shape::convex_polygon(
            rotated_points,
            wheel_color,
            Stroke::new(1.0f32, Color32::from_rgb(203, 213, 225)),
        ));

        // Etiqueta centrada del motor dentro de la rueda (M1..M6)
        painter.text(
            pos,
            egui::Align2::CENTER_CENTER,
            label,
            FontId::monospace(8.0),
            Color32::WHITE,
        );

        // Vector de traccion (flecha en la direccion y sentido longitudinal de la rueda)
        if pwm != 0 {
            let arrow_color = if pwm > 0 {
                Color32::from_rgb(52, 211, 153) // Verde avance (#34d399)
            } else {
                Color32::from_rgb(249, 115, 22)  // Naranja reversa (#f97316)
            };

            let longitud = 10.0f32 + (pwm.abs().min(255) as f32 / 255.0f32) * 12.0f32;
            let signo = if pwm > 0 { 1.0f32 } else { -1.0f32 };

            let ux = rad.sin();
            let uy = -rad.cos();

            let x_ini = pos.x + signo * (h_half * 0.4f32) * ux;
            let y_ini = pos.y + signo * (h_half * 0.4f32) * uy;
            let x_fin = pos.x + signo * (h_half + longitud) * ux;
            let y_fin = pos.y + signo * (h_half + longitud) * uy;

            let p_ini = Pos2::new(x_ini, y_ini);
            let p_fin = Pos2::new(x_fin, y_fin);

            // Segmento de linea principal
            painter.line_segment([p_ini, p_fin], Stroke::new(2.0f32, arrow_color));

            // Cabeza de flecha triangular en p_fin apuntando en sentido del movimiento
            let dir = Vec2::new(signo * ux, signo * uy);
            let perp = Vec2::new(-dir.y, dir.x);
            let head_len = 6.0f32;
            let head_width = 3.5f32;
            let base = p_fin - dir * head_len;
            let v1 = base + perp * head_width;
            let v2 = base - perp * head_width;

            painter.add(egui::Shape::convex_polygon(
                vec![p_fin, v1, v2],
                arrow_color,
                Stroke::NONE,
            ));
        }
    }
}
