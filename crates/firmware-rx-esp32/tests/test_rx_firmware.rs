// Pruebas unitarias para firmware-rx-esp32
// Proyecto: Rover Lunar V2.0
// Regla estricta: Prohibicion absoluta de emojis.

use firmware_rx_esp32::{
    ReceptorEstado, ANGULO_MAX_SERVO, ANGULO_MIN_SERVO, PIN_MOTOR_A1A, PIN_MOTOR_A1B,
    PIN_MOTOR_B1A, PIN_MOTOR_B1B, PIN_NRF_CE, PIN_NRF_CSN, PIN_SERVO_S1, PIN_SERVO_S2,
    PIN_SERVO_S3, PIN_SERVO_S4, PIN_SPI_MISO, PIN_SPI_MOSI, PIN_SPI_SCK, RESPUESTA_IDENT_RX,
    RESPUESTA_PONG_RX, TIMEOUT_FAILSAFE_MS,
};
use protocol_rover::PaqueteRover;

#[test]
fn test_asignacion_pines_hardware_receptor() {
    // SPI NRF24L01+
    assert_eq!(PIN_NRF_CE, 18);
    assert_eq!(PIN_NRF_CSN, 21);
    assert_eq!(PIN_SPI_MOSI, 38);
    assert_eq!(PIN_SPI_MISO, 47);
    assert_eq!(PIN_SPI_SCK, 48);

    // Motores traccion L9110S
    assert_eq!(PIN_MOTOR_A1A, 5); // D2
    assert_eq!(PIN_MOTOR_A1B, 8); // D5
    assert_eq!(PIN_MOTOR_B1A, 6); // D3
    assert_eq!(PIN_MOTOR_B1B, 7); // D4

    // Servos direccion 4WS
    assert_eq!(PIN_SERVO_S1, 9);  // D6
    assert_eq!(PIN_SERVO_S2, 10); // D7
    assert_eq!(PIN_SERVO_S3, 17); // D8
    assert_eq!(PIN_SERVO_S4, 1);  // A0
}

#[test]
fn test_failsafe_timeout_1000ms() {
    assert_eq!(TIMEOUT_FAILSAFE_MS, 1000);

    let mut estado = ReceptorEstado::new();
    let paquete = PaqueteRover::new(220, 220, 90, 90);

    estado.procesar_paquete_rf(&paquete, 5000);
    assert_eq!(estado.traccion_izq, 220);
    assert_eq!(estado.traccion_der, 220);
    assert!(!estado.failsafe_activo);

    // Dentro del margen seguro (500 ms tras el paquete)
    assert!(!estado.verificar_failsafe(5500));
    assert_eq!(estado.traccion_izq, 220);

    // Timeout excedido (1001 ms tras el paquete)
    assert!(estado.verificar_failsafe(6001));
    assert!(estado.failsafe_activo);
    assert_eq!(estado.traccion_izq, 0);
    assert_eq!(estado.traccion_der, 0);
}

#[test]
fn test_restriccion_segura_angulos_servos_y_ackermann_4ws() {
    let mut estado = ReceptorEstado::new();

    // Consigna con angulo extremo (5 grados y 180 grados)
    let paquete = PaqueteRover::new(100, 100, 5, 180);
    estado.procesar_paquete_rf(&paquete, 1000);

    // Deben ser recortados al rango [10, 170]
    assert_eq!(estado.angulo_s1, ANGULO_MIN_SERVO); // 10
    assert_eq!(estado.angulo_s2, ANGULO_MAX_SERVO); // 170

    // En 4WS, las ruedas traseras giran en direccion inversa
    // delta_s1 = 10 - 90 = -80 -> s3 = 90 - (-80) = 170
    assert_eq!(estado.angulo_s3, 170);
    // delta_s2 = 170 - 90 = +80 -> s4 = 90 - 80 = 10
    assert_eq!(estado.angulo_s4, 10);
}

#[test]
fn test_comandos_serie_ident_y_ping_rx() {
    let mut estado = ReceptorEstado::new();

    let r_ident = estado.procesar_linea_serie("IDENT");
    assert_eq!(r_ident.as_deref(), Some(RESPUESTA_IDENT_RX));

    let r_ping = estado.procesar_linea_serie("PING\n");
    assert_eq!(r_ping.as_deref(), Some(RESPUESTA_PONG_RX));
}

#[test]
fn test_calibracion_parseo_y_persistencia() {
    let mut estado = ReceptorEstado::new();

    let r_calib = estado.procesar_linea_serie("CALIB,110,105,100,95,90,85,88,92,89,91\n");
    assert_eq!(r_calib.as_deref(), Some("ACK:CALIB\n"));

    assert_eq!(estado.calibracion.trims_motores, [110, 105, 100, 95, 90, 85]);
    assert_eq!(estado.calibracion.centros_servos, [88, 92, 89, 91]);

    let r_persist = estado.procesar_linea_serie("PERSIST_NVS\n");
    assert_eq!(r_persist.as_deref(), Some("ACK:PERSIST_NVS\n"));
}

#[test]
fn test_formateo_telemetria() {
    let mut estado = ReceptorEstado::new();
    let paquete = PaqueteRover::new(150, -150, 110, 70);
    estado.procesar_paquete_rf(&paquete, 100);

    let tlm = estado.formatear_telemetria(15, 0);
    assert_eq!(tlm, "TLM:150,-150,110,70,70,110,15,0\n");
}

#[test]
fn test_cero_emojis_en_firmware_rx() {
    let codigo = include_str!("../src/lib.rs");
    let patron_emoji = ['\u{1F600}'..='\u{1F64F}', '\u{1F300}'..='\u{1F5FF}'];

    for ch in codigo.chars() {
        for rango in &patron_emoji {
            assert!(!rango.contains(&ch), "Se detecto un emoji prohibido");
        }
    }
}
