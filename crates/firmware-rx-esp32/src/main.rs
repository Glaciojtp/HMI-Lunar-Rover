// Punto de entrada para firmware-rx-esp32
// Proyecto: Rover Lunar V2.0
// Regla estricta: Prohibicion absoluta de emojis.

use firmware_rx_esp32::ReceptorEstado;
use protocol_rover::PaqueteRover;

fn main() {
    let mut estado = ReceptorEstado::new();

    // Verificacion de respuesta serie IDENT
    let r_ident = estado.procesar_linea_serie("IDENT\n");
    assert_eq!(r_ident.as_deref(), Some("ID:NANO_ESP32:RX:v2.1\n"));

    // Verificacion de recepcion de paquete RF
    let paquete = PaqueteRover::new(200, 200, 110, 70);
    estado.procesar_paquete_rf(&paquete, 100);
    assert_eq!(estado.traccion_izq, 200);
    assert_eq!(estado.traccion_der, 200);

    // Verificacion de timeout failsafe (mas de 1000 ms transcurridos)
    assert!(estado.verificar_failsafe(1200));
    assert_eq!(estado.traccion_izq, 0);
    assert_eq!(estado.traccion_der, 0);
}
