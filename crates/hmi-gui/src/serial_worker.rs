//! Trabajador Serial en Segundo Plano (Thread Dedicado no bloqueante).
//!
//! Garantiza cero congelamiento en la interfaz grafica de usuario:
//! - La conexion, transmision y recepcion ocurren en un hilo del sistema operativo.
//! - Comunicacion bidireccional mediante canales `std::sync::mpsc`.
//! - Admite envio tanto en formato ASCII CSV estandarizado como binario estricto (6 bytes).

use std::io::{Read, Write};
use std::sync::mpsc::{channel, Receiver, Sender, TryRecvError};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use protocol_rover::PaqueteRover;

/// Comandos emitidos desde la interfaz grafica hacia el trabajador serial.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SerialCommand {
    Connect { port: String, baud_rate: u32 },
    Disconnect,
    SendPacket(PaqueteRover),
    SendRaw(String),
    Stop,
    SetBinaryMode(bool),
    Shutdown,
}

/// Eventos notificados desde el trabajador serial hacia la interfaz grafica.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SerialEvent {
    Connected { port: String, baud_rate: u32 },
    Disconnected,
    LineReceived(String),
    PacketSent(PaqueteRover),
    BytesWritten(usize),
    Error(String),
    Info(String),
}

/// Manejador de comunicacion del trabajador serial en segundo plano.
pub struct SerialWorkerHandle {
    tx_cmd: Sender<SerialCommand>,
    rx_event: Receiver<SerialEvent>,
    _thread_handle: Option<JoinHandle<()>>,
}

impl Default for SerialWorkerHandle {
    fn default() -> Self {
        Self::start()
    }
}

impl SerialWorkerHandle {
    /// Inicia el trabajador serial en un hilo secundario independiente.
    pub fn start() -> Self {
        let (tx_cmd, rx_cmd) = channel::<SerialCommand>();
        let (tx_event, rx_event) = channel::<SerialEvent>();

        let thread_handle = thread::Builder::new()
            .name("rover-serial-worker".to_string())
            .spawn(move || {
                run_worker_loop(rx_cmd, tx_event);
            })
            .expect("No fue posible crear el hilo para el trabajador serial");

        Self {
            tx_cmd,
            rx_event,
            _thread_handle: Some(thread_handle),
        }
    }

    /// Solicita la conexion a un puerto serie con el baudrate especificado.
    pub fn connect(&self, port: impl Into<String>, baud_rate: u32) {
        let _ = self.tx_cmd.send(SerialCommand::Connect {
            port: port.into(),
            baud_rate,
        });
    }

    /// Solicita la desconexion inmediata y liberacion del puerto serie.
    pub fn disconnect(&self) {
        let _ = self.tx_cmd.send(SerialCommand::Disconnect);
    }

    /// Envia un paquete de control PaqueteRover (6 bytes o comando CSV).
    pub fn send_packet(&self, pkt: PaqueteRover) {
        let _ = self.tx_cmd.send(SerialCommand::SendPacket(pkt));
    }

    /// Envia una cadena de texto sin procesar terminada en salto de linea.
    pub fn send_raw(&self, text: impl Into<String>) {
        let mut msg = text.into();
        if !msg.ends_with('\n') {
            msg.push('\n');
        }
        let _ = self.tx_cmd.send(SerialCommand::SendRaw(msg));
    }

    /// Envia el comando de parada de emergencia inmediata.
    pub fn send_stop(&self) {
        let _ = self.tx_cmd.send(SerialCommand::Stop);
    }

    /// Activa o desactiva la transmision directa en binario puro (6 bytes).
    pub fn set_binary_mode(&self, enabled: bool) {
        let _ = self.tx_cmd.send(SerialCommand::SetBinaryMode(enabled));
    }

    /// Intenta extraer un evento pendiente sin bloquear el hilo actual.
    pub fn try_recv_event(&self) -> Option<SerialEvent> {
        match self.rx_event.try_recv() {
            Ok(event) => Some(event),
            Err(TryRecvError::Empty) => None,
            Err(TryRecvError::Disconnected) => Some(SerialEvent::Error(
                "El canal del hilo serial se ha desconectado".to_string(),
            )),
        }
    }

    /// Finaliza ordenadamente el hilo secundario del trabajador.
    pub fn shutdown(&self) {
        let _ = self.tx_cmd.send(SerialCommand::Shutdown);
    }
}

impl Drop for SerialWorkerHandle {
    fn drop(&mut self) {
        self.shutdown();
    }
}

/// Bucle de ejecucion principal del trabajador serial en segundo plano.
fn run_worker_loop(rx_cmd: Receiver<SerialCommand>, tx_event: Sender<SerialEvent>) {
    let mut port_conn: Option<Box<dyn serialport::SerialPort>> = None;
    let mut binary_mode = false;
    let mut rx_buf = [0u8; 256];
    let mut line_accumulator = String::with_capacity(256);

    'main_loop: loop {
        // 1. Procesar todos los comandos pendientes de la GUI
        while let Ok(cmd) = rx_cmd.try_recv() {
            match cmd {
                SerialCommand::Connect { port, baud_rate } => {
                    // Cerrar conexion anterior si existiera
                    let _ = port_conn.take();

                    match serialport::new(&port, baud_rate)
                        .timeout(Duration::from_millis(20))
                        .open()
                    {
                        Ok(mut p) => {
                            // Configuracion de senales DTR y RTS para ESP32 / Arduino
                            let _ = p.write_data_terminal_ready(true);
                            let _ = p.write_request_to_send(false);

                            let _ = tx_event.send(SerialEvent::Connected {
                                port: port.clone(),
                                baud_rate,
                            });
                            let _ = tx_event.send(SerialEvent::Info(format!(
                                "Puerto {} conectado exitosamente a {} baudios",
                                port, baud_rate
                            )));
                            port_conn = Some(p);
                        }
                        Err(e) => {
                            let _ = tx_event.send(SerialEvent::Error(format!(
                                "Error al abrir puerto {}: {}",
                                port, e
                            )));
                            port_conn = None;
                        }
                    }
                }
                SerialCommand::Disconnect => {
                    if port_conn.is_some() {
                        port_conn = None;
                        let _ = tx_event.send(SerialEvent::Disconnected);
                        let _ = tx_event.send(SerialEvent::Info(
                            "Puerto serial desconectado y liberado".to_string(),
                        ));
                    }
                }
                SerialCommand::SendPacket(pkt) => {
                    if let Some(ref mut port) = port_conn {
                        let result = if binary_mode {
                            let bytes = pkt.to_bytes();
                            port.write_all(&bytes).map(|_| bytes.len())
                        } else {
                            let msg = format!(
                                "CMD,{},{},{},{}\n",
                                pkt.traccion_izq(),
                                pkt.traccion_der(),
                                pkt.angulo_s1(),
                                pkt.angulo_s2()
                            );
                            port.write_all(msg.as_bytes()).map(|_| msg.len())
                        };

                        match result {
                            Ok(bytes_written) => {
                                let _ = port.flush();
                                let _ = tx_event.send(SerialEvent::PacketSent(pkt));
                                let _ = tx_event.send(SerialEvent::BytesWritten(bytes_written));
                            }
                            Err(e) => {
                                let _ = tx_event.send(SerialEvent::Error(format!(
                                    "Error al transmitir paquete: {}",
                                    e
                                )));
                            }
                        }
                    }
                }
                SerialCommand::SendRaw(raw_str) => {
                    if let Some(ref mut port) = port_conn {
                        match port.write_all(raw_str.as_bytes()) {
                            Ok(_) => {
                                let _ = port.flush();
                                let _ = tx_event.send(SerialEvent::BytesWritten(raw_str.len()));
                            }
                            Err(e) => {
                                let _ = tx_event.send(SerialEvent::Error(format!(
                                    "Error al enviar datos: {}",
                                    e
                                )));
                            }
                        }
                    }
                }
                SerialCommand::Stop => {
                    if let Some(ref mut port) = port_conn {
                        let _ = port.write_all(b"STOP\n");
                        let _ = port.flush();
                        let stop_pkt = PaqueteRover::default();
                        let _ = tx_event.send(SerialEvent::PacketSent(stop_pkt));
                        let _ = tx_event.send(SerialEvent::Info(
                            "Comando STOP transmitido inmediatamente".to_string(),
                        ));
                    }
                }
                SerialCommand::SetBinaryMode(mode) => {
                    binary_mode = mode;
                    let _ = tx_event.send(SerialEvent::Info(format!(
                        "Modo de transmision configurado a {}",
                        if mode { "BINARIO_ESTRICTO_6B" } else { "ASCII_CSV_CMD" }
                    )));
                }
                SerialCommand::Shutdown => {
                    break 'main_loop;
                }
            }
        }

        // 2. Si esta conectado, leer datos entrantes sin bloquear
        if let Some(ref mut port) = port_conn {
            match port.read(&mut rx_buf) {
                Ok(bytes_read) if bytes_read > 0 => {
                    for &b in &rx_buf[..bytes_read] {
                        if b == b'\n' || b == b'\r' {
                            let line = line_accumulator.trim().to_string();
                            if !line.is_empty() {
                                let _ = tx_event.send(SerialEvent::LineReceived(line));
                            }
                            line_accumulator.clear();
                        } else if line_accumulator.len() < 512 {
                            line_accumulator.push(b as char);
                        }
                    }
                }
                Ok(_) => {
                    // No hay bytes leidos en este ciclo
                    thread::sleep(Duration::from_millis(5));
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::TimedOut => {
                    // Timeout esperado para I/O no bloqueante
                    thread::sleep(Duration::from_millis(5));
                }
                Err(e) => {
                    // Error critico de I/O (puerto desconectado fisicamente)
                    let _ = tx_event.send(SerialEvent::Error(format!(
                        "Desconexion fisica o fallo I/O en puerto: {}",
                        e
                    )));
                    port_conn = None;
                    let _ = tx_event.send(SerialEvent::Disconnected);
                }
            }
        } else {
            // No conectado: esperar con bajo consumo de CPU
            match rx_cmd.recv_timeout(Duration::from_millis(50)) {
                Ok(cmd) => {
                    if cmd == SerialCommand::Shutdown {
                        break 'main_loop;
                    }
                    // Reinyectar para que el lazo procese el comando en la siguiente iteracion
                    // o manejar directamente el Connect
                    if let SerialCommand::Connect { port, baud_rate } = cmd {
                        match serialport::new(&port, baud_rate)
                            .timeout(Duration::from_millis(20))
                            .open()
                        {
                            Ok(mut p) => {
                                let _ = p.write_data_terminal_ready(true);
                                let _ = p.write_request_to_send(false);
                                let _ = tx_event.send(SerialEvent::Connected {
                                    port: port.clone(),
                                    baud_rate,
                                });
                                let _ = tx_event.send(SerialEvent::Info(format!(
                                    "Puerto {} conectado exitosamente a {} baudios",
                                    port, baud_rate
                                )));
                                port_conn = Some(p);
                            }
                            Err(e) => {
                                let _ = tx_event.send(SerialEvent::Error(format!(
                                    "Error al abrir puerto {}: {}",
                                    port, e
                                )));
                            }
                        }
                    }
                }
                Err(_) => {}
            }
        }
    }

    drop(port_conn);
}
