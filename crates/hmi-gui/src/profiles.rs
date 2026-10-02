//! Modulo de Definicion de Perfiles de Hardware y Autodeteccion.
//!
//! Soporta los perfiles oficiales del sistema:
//! - Arduino Nano ESP32 (Perfil oficial predeterminado, ESP32-S3 a 3.3V)
//! - ESP32-C3 SuperMini (Transmisor USB-RF previo basado en RISC-V)
//! - Arduino MKR WAN 1310 (Receptor historico a bordo basado en SAMD21)

use serialport::{SerialPortInfo, SerialPortType};

/// Identificador unico del perfil oficial por defecto del sistema.
pub const PERFIL_DEFAULT_ID: &str = "ARDUINO_NANO_ESP32";

/// Representa las caracteristicas tecnicas de una placa de desarrollo soportada.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PerfilHardware {
    pub id: &'static str,
    pub nombre: &'static str,
    pub mcu: &'static str,
    pub vid_pid_list: &'static [(u16, u16)],
    pub fqbn: &'static str,
    pub sketch_tx: Option<&'static str>,
    pub sketch_rx: Option<&'static str>,
    pub descripcion: &'static str,
}

impl PerfilHardware {
    /// Indica si el perfil dispone de firmware para transmision.
    pub const fn soporta_tx(&self) -> bool {
        self.sketch_tx.is_some()
    }

    /// Indica si el perfil dispone de firmware para recepcion.
    pub const fn soporta_rx(&self) -> bool {
        self.sketch_rx.is_some()
    }

    /// Verifica si un par VID:PID corresponde a este perfil.
    pub fn coincide_vid_pid(&self, vid: u16, pid: u16) -> bool {
        self.vid_pid_list.contains(&(vid, pid))
    }
}

/// Lista estatica de perfiles de hardware soportados oficialmente.
pub static PERFILES_OFICIALES: &[PerfilHardware] = &[
    PerfilHardware {
        id: "ARDUINO_NANO_ESP32",
        nombre: "Arduino Nano ESP32",
        mcu: "ESP32-S3",
        vid_pid_list: &[
            (0x2341, 0x0070), // Modo aplicacion normal (USB CDC)
            (0x2341, 0x0069), // Modo bootloader ROM / DFU
        ],
        fqbn: "arduino:esp32:nano_nora",
        sketch_tx: Some("02_Debug_y_Pruebas/Firmware_Debug/Transmisor_ArduinoNano_ESP32/Transmisor_ArduinoNano_ESP32.ino"),
        sketch_rx: Some("01_Oficial/Receptor_Rover_NanoESP32/Ejecutor_ArduinoNano_ESP32/Ejecutor_ArduinoNano_ESP32.ino"),
        descripcion: "Plataforma oficial estandarizada a 3.3V (ESP32-S3). Soporta transmision y recepcion.",
    },
    PerfilHardware {
        id: "ESP32_C3_SUPERMINI",
        nombre: "ESP32-C3 SuperMini",
        mcu: "ESP32-C3",
        vid_pid_list: &[
            (0x303A, 0x1001), // CDC nativo USB ESP32-C3
            (0x1A86, 0x7523), // Adaptador CH340
            (0x10C4, 0xEA60), // Adaptador CP2102
        ],
        fqbn: "esp32:esp32:esp32c3",
        sketch_tx: Some("01_Oficial/Transmisor_PC_ESP32C3/Control_ESP32_C3_Optimizado/Control_ESP32_C3_Optimizado.ino"),
        sketch_rx: None,
        descripcion: "Transmisor USB-RF de escritorio previo basado en ESP32-C3 (RISC-V).",
    },
    PerfilHardware {
        id: "ARDUINO_MKR_1310",
        nombre: "Arduino MKR WAN 1310",
        mcu: "SAMD21",
        vid_pid_list: &[
            (0x2341, 0x8054), // Modo USB CDC normal
            (0x2341, 0x0054), // Modo bootloader
        ],
        fqbn: "arduino:samd:mkrwan1310",
        sketch_tx: None,
        sketch_rx: Some("01_Oficial/Receptor_Rover_MKR1310/Ejecutor_ArduinoMKR_Optimizado/Ejecutor_ArduinoMKR_Optimizado.ino"),
        descripcion: "Receptor historico a bordo del chasis basado en SAMD21 (ARM Cortex-M0+).",
    },
];

/// Informacion extraida del comando de handshake serie IDENT.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HandshakeInfo {
    pub placa: String,
    pub rol: String,
    pub version: String,
}

/// Informacion de un puerto serie escaneado con deteccion de hardware.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiscoveredPort {
    pub port_name: String,
    pub vid_pid: Option<(u16, u16)>,
    pub manufacturer: Option<String>,
    pub product: Option<String>,
    pub detected_profile: Option<&'static PerfilHardware>,
}

/// Registro y motor de resolucion de perfiles de hardware.
#[derive(Debug, Clone, Default)]
pub struct HardwareProfileRegistry {
    profiles: &'static [PerfilHardware],
}

impl HardwareProfileRegistry {
    /// Inicializa el registro con los perfiles oficiales del sistema.
    pub fn new() -> Self {
        Self {
            profiles: PERFILES_OFICIALES,
        }
    }

    /// Retorna el perfil oficial predeterminado (Arduino Nano ESP32).
    pub fn default_profile(&self) -> &'static PerfilHardware {
        self.get_profile(PERFIL_DEFAULT_ID)
            .expect("El perfil predeterminado debe existir")
    }

    /// Lista todos los perfiles de hardware registrados.
    pub fn list_profiles(&self) -> &'static [PerfilHardware] {
        self.profiles
    }

    /// Busca un perfil por identificador exacto o alias normalizado.
    pub fn get_profile(&self, id_or_name: &str) -> Option<&'static PerfilHardware> {
        let clean = id_or_name.trim();
        if clean.is_empty() {
            return None;
        }

        // Busqueda exacta por ID
        if let Some(p) = self.profiles.iter().find(|p| p.id.eq_ignore_ascii_case(clean)) {
            return Some(p);
        }

        // Resolucion de alias comunes de handshake
        let alias_id = match clean.to_ascii_uppercase().as_str() {
            "NANO_ESP32" | "ARDUINO_NANO_ESP32" => Some("ARDUINO_NANO_ESP32"),
            "ESP32C3" | "ESP32_C3" | "ESP32_C3_SUPERMINI" => Some("ESP32_C3_SUPERMINI"),
            "MKR1310" | "MKR_1310" | "ARDUINO_MKR_1310" => Some("ARDUINO_MKR_1310"),
            _ => None,
        };

        if let Some(target) = alias_id {
            return self.profiles.iter().find(|p| p.id == target);
        }

        // Busqueda por nombre descriptivo
        self.profiles.iter().find(|p| p.nombre.eq_ignore_ascii_case(clean))
    }

    /// Identificacion pasiva por par USB VID:PID.
    pub fn detect_from_vid_pid(&self, vid: u16, pid: u16) -> Option<&'static PerfilHardware> {
        self.profiles.iter().find(|p| p.coincide_vid_pid(vid, pid))
    }

    /// Identificacion pasiva a partir de la informacion de un puerto serie.
    pub fn detect_from_port(&self, port: &SerialPortInfo) -> Option<&'static PerfilHardware> {
        if let SerialPortType::UsbPort(ref usb_info) = port.port_type {
            self.detect_from_vid_pid(usb_info.vid, usb_info.pid)
        } else {
            None
        }
    }

    /// Escanea los puertos seriales disponibles y asocia perfiles de hardware detectados.
    pub fn scan_ports(&self) -> Vec<DiscoveredPort> {
        let ports = serialport::available_ports().unwrap_or_default();
        ports
            .into_iter()
            .map(|p| {
                let mut vid_pid = None;
                let mut manufacturer = None;
                let mut product = None;

                if let SerialPortType::UsbPort(ref usb) = p.port_type {
                    vid_pid = Some((usb.vid, usb.pid));
                    manufacturer = usb.manufacturer.clone();
                    product = usb.product.clone();
                }

                let detected_profile = self.detect_from_port(&p);

                DiscoveredPort {
                    port_name: p.port_name,
                    vid_pid,
                    manufacturer,
                    product,
                    detected_profile,
                }
            })
            .collect()
    }

    /// Parsea la respuesta del comando IDENT (ID:<PLACA>:<ROL>:<VERSION>)
    /// y resuelve el perfil de hardware correspondiente.
    pub fn resolve_handshake(
        &self,
        raw_response: &str,
    ) -> Result<(&'static PerfilHardware, HandshakeInfo), String> {
        let info = parse_handshake(raw_response)?;
        let profile = self
            .get_profile(&info.placa)
            .ok_or_else(|| format!("Perfil desconocido para placa: {}", info.placa))?;
        Ok((profile, info))
    }
}

/// Parsea la respuesta de handshake textual IDENT.
///
/// Formato esperado: `ID:<PLACA>:<ROL>:<VERSION>`
/// Ejemplos:
/// - `ID:NANO_ESP32:TX:v2.1` -> placa="NANO_ESP32", rol="TX", version="v2.1"
/// - `ID:MKR1310:RX:v2.0` -> placa="MKR1310", rol="RX", version="v2.0"
pub fn parse_handshake(raw: &str) -> Result<HandshakeInfo, String> {
    let clean = raw.trim();
    if clean.is_empty() {
        return Err("Respuesta de handshake vacia".to_string());
    }

    let parts: Vec<&str> = clean.split(':').collect();
    if parts.len() != 4 || parts[0] != "ID" {
        return Err(format!(
            "Formato de handshake invalido: '{}'. Esperado: ID:<PLACA>:<ROL>:<VERSION>",
            clean
        ));
    }

    let placa = parts[1].trim().to_string();
    let rol = parts[2].trim().to_string();
    let version = parts[3].trim().to_string();

    if placa.is_empty() || rol.is_empty() || version.is_empty() {
        return Err(format!("Campos incompletos en respuesta de handshake: '{}'", clean));
    }

    Ok(HandshakeInfo {
        placa,
        rol,
        version,
    })
}
