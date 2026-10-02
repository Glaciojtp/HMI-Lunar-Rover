//! Suite de Pruebas Unitarias para la Logica de la GUI Nativa (hmi-gui).
//!
//! Valida:
//! - Perfiles de hardware (Arduino Nano ESP32 default, VID:PID pasivo, handshake IDENT).
//! - Calculos de trims porcentuales y potencia promedio.
//! - Restriccion mecanica estricta de servos al rango [10, 170] grados.
//! - Cinematica de modos Ackermann, PointTurn (Giro 360), Crab y Manual.
//! - Generacion y empaquetado binario de paquetes PaqueteRover (6 bytes).
//! - Auditoria estricta de erradicacion total de emojis en todo el crate.

use std::fs;
use std::path::Path;

use hmi_gui::kinematics::{
    calcular_cinematica, generar_paquete_rover, AngulosServos, ModoConduccion, TeclasEstado,
    TrimsMotores,
};
use hmi_gui::profiles::{
    parse_handshake, HardwareProfileRegistry, PERFIL_DEFAULT_ID,
};
use protocol_rover::{ANGULO_CENTRO, ANGULO_MAX, ANGULO_MIN, TAMANO_PAQUETE};

// =========================================================================
// 1. PRUEBAS DE PERFILES DE HARDWARE Y AUTODETECCION
// =========================================================================

#[test]
fn test_perfil_default_es_nano_esp32() {
    let registry = HardwareProfileRegistry::new();
    let default_profile = registry.default_profile();

    assert_eq!(default_profile.id, PERFIL_DEFAULT_ID);
    assert_eq!(default_profile.id, "ARDUINO_NANO_ESP32");
    assert_eq!(default_profile.mcu, "ESP32-S3");
    assert!(default_profile.soporta_tx());
    assert!(default_profile.soporta_rx());
}

#[test]
fn test_perfiles_oficiales_registrados() {
    let registry = HardwareProfileRegistry::new();
    let profiles = registry.list_profiles();

    assert_eq!(profiles.len(), 3);
    assert!(registry.get_profile("ARDUINO_NANO_ESP32").is_some());
    assert!(registry.get_profile("ESP32_C3_SUPERMINI").is_some());
    assert!(registry.get_profile("ARDUINO_MKR_1310").is_some());
}

#[test]
fn test_resolucion_por_alias_de_handshake() {
    let registry = HardwareProfileRegistry::new();

    let p1 = registry.get_profile("NANO_ESP32").expect("Alias NANO_ESP32");
    assert_eq!(p1.id, "ARDUINO_NANO_ESP32");

    let p2 = registry.get_profile("ESP32C3").expect("Alias ESP32C3");
    assert_eq!(p2.id, "ESP32_C3_SUPERMINI");

    let p3 = registry.get_profile("MKR1310").expect("Alias MKR1310");
    assert_eq!(p3.id, "ARDUINO_MKR_1310");
}

#[test]
fn test_deteccion_pasiva_vid_pid() {
    let registry = HardwareProfileRegistry::new();

    // Arduino Nano ESP32 CDC
    let d1 = registry.detect_from_vid_pid(0x2341, 0x0070).expect("Nano ESP32 CDC");
    assert_eq!(d1.id, "ARDUINO_NANO_ESP32");

    // Arduino Nano ESP32 Bootloader DFU
    let d2 = registry.detect_from_vid_pid(0x2341, 0x0069).expect("Nano ESP32 DFU");
    assert_eq!(d2.id, "ARDUINO_NANO_ESP32");

    // ESP32-C3 CDC
    let d3 = registry.detect_from_vid_pid(0x303A, 0x1001).expect("ESP32-C3 CDC");
    assert_eq!(d3.id, "ESP32_C3_SUPERMINI");

    // Arduino MKR 1310 CDC
    let d4 = registry.detect_from_vid_pid(0x2341, 0x8054).expect("MKR 1310 CDC");
    assert_eq!(d4.id, "ARDUINO_MKR_1310");

    // Dispositivo desconocido
    assert!(registry.detect_from_vid_pid(0x1234, 0x5678).is_none());
}

#[test]
fn test_parsear_handshake_valido() {
    let res = parse_handshake("ID:NANO_ESP32:TX:v2.1\n").expect("Parseo exitoso");
    assert_eq!(res.placa, "NANO_ESP32");
    assert_eq!(res.rol, "TX");
    assert_eq!(res.version, "v2.1");

    let res2 = parse_handshake("ID:MKR1310:RX:v2.0").expect("Parseo exitoso");
    assert_eq!(res2.placa, "MKR1310");
    assert_eq!(res2.rol, "RX");
    assert_eq!(res2.version, "v2.0");
}

#[test]
fn test_parsear_handshake_invalido() {
    assert!(parse_handshake("").is_err());
    assert!(parse_handshake("STATUS:OK").is_err());
    assert!(parse_handshake("ID:NANO_ESP32").is_err());
    assert!(parse_handshake("ID:NANO_ESP32:TX").is_err());
    assert!(parse_handshake("INVALID:NANO:TX:v1").is_err());
}

#[test]
fn test_resolver_handshake_completo() {
    let registry = HardwareProfileRegistry::new();
    let (perfil, info) = registry
        .resolve_handshake("ID:NANO_ESP32:TX:v2.1")
        .expect("Handshake resuelto");

    assert_eq!(perfil.id, "ARDUINO_NANO_ESP32");
    assert_eq!(info.rol, "TX");
    assert_eq!(info.version, "v2.1");
}

// =========================================================================
// 2. PRUEBAS DE TRIMS Y POTENCIA DE MOTORES
// =========================================================================

#[test]
fn test_trims_default_y_reset() {
    let mut trims = TrimsMotores::default();
    assert_eq!(trims.m1, 100);
    assert_eq!(trims.master_izq, 150);

    trims.m1 = 80;
    trims.m4 = 120;
    trims.reset_trims();

    assert_eq!(trims.m1, 100);
    assert_eq!(trims.m4, 100);
}

#[test]
fn test_calculo_pwm_motor_con_trims() {
    let trims = TrimsMotores {
        m1: 100,
        m2: 50,
        m3: 150,
        m4: 80,
        m5: 100,
        m6: 120,
        master_izq: 200,
        master_der: 100,
    };

    assert_eq!(trims.calcular_pwm_motor(1), 200); // 200 * 100% = 200
    assert_eq!(trims.calcular_pwm_motor(2), 100); // 200 * 50% = 100
    assert_eq!(trims.calcular_pwm_motor(3), 255); // 200 * 150% = 300 -> clamp 255
    assert_eq!(trims.calcular_pwm_motor(4), 80);  // 100 * 80% = 80
    assert_eq!(trims.calcular_pwm_motor(5), 100); // 100 * 100% = 100
    assert_eq!(trims.calcular_pwm_motor(6), 120); // 100 * 120% = 120
}

#[test]
fn test_potencia_media_por_lado() {
    let trims = TrimsMotores {
        m1: 100,
        m2: 100,
        m3: 100,
        m4: 100,
        m5: 100,
        m6: 100,
        master_izq: 150,
        master_der: 180,
    };

    assert_eq!(trims.potencia_media_izq(), 150);
    assert_eq!(trims.potencia_media_der(), 180);
}

// =========================================================================
// 3. PRUEBAS DE SEGURIDAD MECANICA Y CLAMP DE SERVOS
// =========================================================================

#[test]
fn test_restriccion_estricta_angulos_servos() {
    let s = AngulosServos::clamped(0, 5, 180, 255);
    assert_eq!(s.s1, ANGULO_MIN); // 10
    assert_eq!(s.s2, ANGULO_MIN); // 10
    assert_eq!(s.s3, ANGULO_MAX); // 170
    assert_eq!(s.s4, ANGULO_MAX); // 170
}

#[test]
fn test_presets_servos() {
    let mut s = AngulosServos::default();
    assert_eq!(s.s1, ANGULO_CENTRO);

    s.preset_point_turn();
    assert_eq!(s.s1, 45);
    assert_eq!(s.s2, 135);
    assert_eq!(s.s3, 135);
    assert_eq!(s.s4, 45);

    s.preset_crab();
    assert_eq!(s.s1, 45);
    assert_eq!(s.s2, 45);
    assert_eq!(s.s3, 45);
    assert_eq!(s.s4, 45);

    s.centrar();
    assert_eq!(s.s1, 90);
    assert_eq!(s.s2, 90);
    assert_eq!(s.s3, 90);
    assert_eq!(s.s4, 90);
}

// =========================================================================
// 4. PRUEBAS DE CINEMATICA Y GENERACION DE PAQUETES
// =========================================================================

#[test]
fn test_cinematica_parada_de_emergencia() {
    let trims = TrimsMotores::default();
    let servos = AngulosServos::default();

    let mut teclas = TeclasEstado::default();
    teclas.w = true;
    teclas.space = true; // Espacio tiene prioridad absoluta

    let estado = calcular_cinematica(&teclas, ModoConduccion::Ackermann, &trims, &servos, false);
    assert_eq!(estado.traccion_izq, 0);
    assert_eq!(estado.traccion_der, 0);
    assert_eq!(estado.comando_nombre, "STOP");
    assert_eq!(estado.pwms_motores, [0; 6]);
}

#[test]
fn test_cinematica_ackermann_avance_recto() {
    let trims = TrimsMotores::default();
    let servos = AngulosServos::default();

    let mut teclas = TeclasEstado::default();
    teclas.w = true;

    let estado = calcular_cinematica(&teclas, ModoConduccion::Ackermann, &trims, &servos, false);
    assert_eq!(estado.traccion_izq, 150);
    assert_eq!(estado.traccion_der, 150);
    assert_eq!(estado.servos.s1, 90);
    assert_eq!(estado.servos.s2, 90);
    assert_eq!(estado.comando_nombre, "W");
}

#[test]
fn test_cinematica_ackermann_giro_izquierda() {
    let trims = TrimsMotores::default();
    let servos = AngulosServos::default();

    let mut teclas = TeclasEstado::default();
    teclas.w = true;
    teclas.a = true;

    let estado = calcular_cinematica(&teclas, ModoConduccion::Ackermann, &trims, &servos, false);
    assert_eq!(estado.servos.s1, 120);
    assert_eq!(estado.servos.s2, 120);
    assert_eq!(estado.servos.s3, 60);
    assert_eq!(estado.servos.s4, 60);
    assert_eq!(estado.traccion_izq, (150 * 7) / 10); // Reduccion diferencial
    assert_eq!(estado.traccion_der, 150);
    assert_eq!(estado.comando_nombre, "W_A");
}

#[test]
fn test_cinematica_point_turn_q() {
    let trims = TrimsMotores::default();
    let servos = AngulosServos::default();

    let mut teclas = TeclasEstado::default();
    teclas.q = true;

    let estado = calcular_cinematica(&teclas, ModoConduccion::Ackermann, &trims, &servos, false);
    assert_eq!(estado.servos.s1, 45);
    assert_eq!(estado.servos.s2, 135);
    assert_eq!(estado.servos.s3, 135);
    assert_eq!(estado.servos.s4, 45);
    assert_eq!(estado.traccion_izq, -150);
    assert_eq!(estado.traccion_der, 150);
    assert_eq!(estado.comando_nombre, "PIVOT_IZQ");
}

#[test]
fn test_generacion_paquete_rover_binario() {
    let trims = TrimsMotores::default();
    let servos = AngulosServos::default();
    let mut teclas = TeclasEstado::default();
    teclas.w = true;

    let estado = calcular_cinematica(&teclas, ModoConduccion::Ackermann, &trims, &servos, false);
    let pkt = generar_paquete_rover(&estado);

    assert_eq!(pkt.traccion_izq(), 150);
    assert_eq!(pkt.traccion_der(), 150);
    assert_eq!(pkt.angulo_s1(), 90);
    assert_eq!(pkt.angulo_s2(), 90);

    let bytes = pkt.to_bytes();
    assert_eq!(bytes.len(), TAMANO_PAQUETE);
    assert_eq!(bytes.len(), 6);

    // Verificacion Little-Endian
    let izq_bytes = 150i16.to_le_bytes();
    assert_eq!(bytes[0], izq_bytes[0]);
    assert_eq!(bytes[1], izq_bytes[1]);
}

// =========================================================================
// 5. AUDITORIA ESTRICTA DE ERRADICACION TOTAL DE EMOJIS
// =========================================================================

#[test]
fn test_auditoria_estricta_cero_emojis() {
    let crate_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
    let mut archivos_a_revisar = Vec::new();

    fn recolectar_rs(dir: &Path, acc: &mut Vec<std::path::PathBuf>) {
        if let Ok(entries) = fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    let nombre = path.file_name().unwrap_or_default().to_string_lossy();
                    if nombre != "target" && !nombre.starts_with('.') {
                        recolectar_rs(&path, acc);
                    }
                } else if path.extension().map(|e| e == "rs").unwrap_or(false) {
                    acc.push(path);
                }
            }
        }
    }

    recolectar_rs(&crate_dir.join("src"), &mut archivos_a_revisar);
    recolectar_rs(&crate_dir.join("tests"), &mut archivos_a_revisar);

    assert!(
        !archivos_a_revisar.is_empty(),
        "Debe haber archivos Rust para auditar"
    );

    for path in &archivos_a_revisar {
        let content = fs::read_to_string(path)
            .unwrap_or_else(|_| panic!("No se pudo leer {:?}", path));

        for (line_no, line) in content.lines().enumerate() {
            for ch in line.chars() {
                let code = ch as u32;
                // Rangos estandar Unicode de Emojis y pictogramas
                let es_emoji = (0x1F300..=0x1F5FF).contains(&code)
                    || (0x1F600..=0x1F64F).contains(&code)
                    || (0x1F680..=0x1F6FF).contains(&code)
                    || (0x2600..=0x26FF).contains(&code)
                    || (0x2700..=0x27BF).contains(&code)
                    || (0x1F900..=0x1F9FF).contains(&code)
                    || (0x1FA70..=0x1FAFF).contains(&code)
                    || (0x1F1E6..=0x1F1FF).contains(&code);

                assert!(
                    !es_emoji,
                    "VIOLACION REGLA CERO EMOJIS: caracter U+{:04X} '{}' detectado en {:?}:{}",
                    code, ch, path, line_no + 1
                );
            }
        }
    }
}
