// Punto de entrada para firmware-tx-esp32
// Proyecto: Rover Lunar V2.0
// Regla estricta: Prohibicion absoluta de emojis.

use firmware_tx_esp32::{AccionTx, TransmisorEstado};

fn main() {
    let mut estado = TransmisorEstado::new();

    // Verificacion de arranque en entorno de simulacion/pruebas
    let accion_ident = estado.procesar_texto("IDENT\n");
    match accion_ident {
        AccionTx::ResponderSerie(msg) => {
            assert!(msg.contains("ID:NANO_ESP32:TX:v2.1"));
        }
        _ => panic!("Fallo en respuesta inicial de IDENT"),
    }

    let accion_ping = estado.procesar_texto("PING\n");
    match accion_ping {
        AccionTx::ResponderSerie(msg) => {
            assert!(msg.contains("PONG:TX:NANO_ESP32"));
        }
        _ => panic!("Fallo en respuesta inicial de PING"),
    }
}
