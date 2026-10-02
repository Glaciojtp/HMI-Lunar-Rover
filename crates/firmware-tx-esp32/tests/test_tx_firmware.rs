// Pruebas unitarias para firmware-tx-esp32
// Proyecto: Rover Lunar V2.0
// Regla estricta: Prohibicion absoluta de emojis.

use firmware_tx_esp32::{
    AccionTx, TransmisorEstado, PIN_LED_BLUE, PIN_LED_GREEN, PIN_LED_RED, PIN_NRF_CE,
    PIN_NRF_CSN, PIN_SPI_MISO, PIN_SPI_MOSI, PIN_SPI_SCK, RESPUESTA_IDENT, RESPUESTA_PONG,
    RF_CHANNEL, RF_DATARATE_KBPS,
};
use protocol_rover::PaqueteRover;

#[test]
fn test_asignacion_pines_hardware_nano_esp32() {
    assert_eq!(PIN_NRF_CE, 18);
    assert_eq!(PIN_NRF_CSN, 21);
    assert_eq!(PIN_SPI_MOSI, 38);
    assert_eq!(PIN_SPI_MISO, 47);
    assert_eq!(PIN_SPI_SCK, 48);

    assert_eq!(PIN_LED_RED, 46);
    assert_eq!(PIN_LED_GREEN, 0);
    assert_eq!(PIN_LED_BLUE, 45);
}

#[test]
fn test_parametros_radiofrecuencia() {
    assert_eq!(RF_CHANNEL, 108);
    assert_eq!(RF_DATARATE_KBPS, 250);
}

#[test]
fn test_comando_ident_y_ping() {
    let mut estado = TransmisorEstado::new();

    let r_ident = estado.procesar_texto("IDENT");
    assert_eq!(r_ident, AccionTx::ResponderSerie(RESPUESTA_IDENT.into()));
    assert_eq!(estado.idents_respondidos, 1);

    let r_ping = estado.procesar_texto("ping\n");
    assert_eq!(r_ping, AccionTx::ResponderSerie(RESPUESTA_PONG.into()));
    assert_eq!(estado.pings_respondidos, 1);
}

#[test]
fn test_comando_cmd_texto_con_clamping() {
    let mut estado = TransmisorEstado::new();

    // Valores fuera de rango para servos: 5 grados y 180 grados
    let r_cmd = estado.procesar_texto("CMD,150,-150,5,180\n");
    let paquete_esperado = PaqueteRover::new(150, -150, 10, 170);

    assert_eq!(r_cmd, AccionTx::TransmitirRf(paquete_esperado));
    assert_eq!(estado.paquetes_transmitidos, 1);
    assert_eq!(estado.ultimo_paquete.angulo_s1(), 10);
    assert_eq!(estado.ultimo_paquete.angulo_s2(), 170);
}

#[test]
fn test_comando_stop() {
    let mut estado = TransmisorEstado::new();
    estado.ultimo_paquete = PaqueteRover::new(200, 200, 120, 60);

    let r_stop = estado.procesar_texto("STOP\n");
    let paquete_esperado = PaqueteRover::new(0, 0, 120, 60);

    assert_eq!(r_stop, AccionTx::TransmitirRf(paquete_esperado));
    assert_eq!(estado.ultimo_paquete.traccion_izq(), 0);
    assert_eq!(estado.ultimo_paquete.traccion_der(), 0);
}

#[test]
fn test_parseo_trama_binaria_6_bytes() {
    let mut estado = TransmisorEstado::new();
    let paquete_original = PaqueteRover::new(180, -180, 100, 80);
    let bytes = paquete_original.to_bytes();

    assert_eq!(bytes.len(), 6);
    let r_bin = estado.procesar_binario(&bytes);
    assert_eq!(r_bin, AccionTx::TransmitirRf(paquete_original));

    // Bloque con longitud incorrecta debe retornar error
    let r_invalido = estado.procesar_binario(&[1, 2, 3]);
    match r_invalido {
        AccionTx::ResponderSerie(msg) => assert!(msg.contains("ERR")),
        _ => panic!("Esperaba mensaje de error"),
    }
}

#[test]
fn test_comando_desconocido() {
    let mut estado = TransmisorEstado::new();
    let r_desc = estado.procesar_texto("COMANDO_INVALIDO_XYZ\n");
    match r_desc {
        AccionTx::ResponderSerie(msg) => assert!(msg.contains("ERR")),
        _ => panic!("Esperaba mensaje de error"),
    }
    assert_eq!(estado.errores_trama, 1);
}

#[test]
fn test_cero_emojis_en_firmware_tx() {
    let codigo = include_str!("../src/lib.rs");
    let patron_emoji = ['\u{1F600}'..='\u{1F64F}', '\u{1F300}'..='\u{1F5FF}'];

    for ch in codigo.chars() {
        for rango in &patron_emoji {
            assert!(!rango.contains(&ch), "Se detecto un emoji prohibido");
        }
    }
}
