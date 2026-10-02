use protocol_rover::{
    PaqueteRover, ProtocolError, ANGULO_CENTRO, ANGULO_MAX, ANGULO_MIN, TAMANO_PAQUETE,
    TRACCION_MAX, TRACCION_MIN,
};

#[test]
fn test_paquete_size_and_alignment() {
    assert_eq!(core::mem::size_of::<PaqueteRover>(), 6);
    assert_eq!(core::mem::align_of::<PaqueteRover>(), 1);
}

#[test]
fn test_paquete_constants() {
    assert_eq!(TAMANO_PAQUETE, 6);
    assert_eq!(ANGULO_MIN, 10);
    assert_eq!(ANGULO_MAX, 170);
    assert_eq!(ANGULO_CENTRO, 90);
    assert_eq!(TRACCION_MIN, -255);
    assert_eq!(TRACCION_MAX, 255);
}

#[test]
fn test_paquete_new() {
    let p = PaqueteRover::new(150, -150, 45, 135);
    assert_eq!(p.traccion_izq(), 150);
    assert_eq!(p.traccion_der(), -150);
    assert_eq!(p.angulo_s1(), 45);
    assert_eq!(p.angulo_s2(), 135);

    // Acceso por copia de campos directos
    let izq = { p.traccion_izq };
    let der = { p.traccion_der };
    assert_eq!(izq, 150);
    assert_eq!(der, -150);
}

#[test]
fn test_paquete_default() {
    let p = PaqueteRover::default();
    assert_eq!(p.traccion_izq(), 0);
    assert_eq!(p.traccion_der(), 0);
    assert_eq!(p.angulo_s1(), 90);
    assert_eq!(p.angulo_s2(), 90);
}

#[test]
fn test_paquete_clamped_in_bounds() {
    let p = PaqueteRover::clamped(200, -200, 50, 120);
    assert_eq!(p.traccion_izq(), 200);
    assert_eq!(p.traccion_der(), -200);
    assert_eq!(p.angulo_s1(), 50);
    assert_eq!(p.angulo_s2(), 120);
    assert!(p.is_valid_range());
}

#[test]
fn test_paquete_clamped_out_of_bounds() {
    let p = PaqueteRover::clamped(500, -400, 0, 200);
    assert_eq!(p.traccion_izq(), 255);
    assert_eq!(p.traccion_der(), -255);
    assert_eq!(p.angulo_s1(), 10);
    assert_eq!(p.angulo_s2(), 170);
    assert!(p.is_valid_range());
}

#[test]
fn test_is_valid_range() {
    let valid = PaqueteRover::new(0, 0, 90, 90);
    assert!(valid.is_valid_range());

    let invalid_trac_izq = PaqueteRover::new(256, 0, 90, 90);
    assert!(!invalid_trac_izq.is_valid_range());

    let invalid_trac_der = PaqueteRover::new(0, -256, 90, 90);
    assert!(!invalid_trac_der.is_valid_range());

    let invalid_s1_low = PaqueteRover::new(0, 0, 9, 90);
    assert!(!invalid_s1_low.is_valid_range());

    let invalid_s2_high = PaqueteRover::new(0, 0, 90, 171);
    assert!(!invalid_s2_high.is_valid_range());
}

#[test]
fn test_to_bytes_and_from_bytes_roundtrip() {
    let original = PaqueteRover::new(250, -250, 90, 90);
    let bytes = original.to_bytes();

    // Verificacion de orden Little-Endian y alineacion binaria estricta
    // 250 (0x00FA) -> [0xFA, 0x00]
    // -250 (0xFF06 en complemento a dos de 16 bits) -> [0x06, 0xFF]
    // 90 -> 0x5A
    // 90 -> 0x5A
    assert_eq!(bytes, [0xFA, 0x00, 0x06, 0xFF, 0x5A, 0x5A]);

    let decoded = PaqueteRover::from_bytes(&bytes);
    assert_eq!(decoded, original);
    assert_eq!(decoded.traccion_izq(), 250);
    assert_eq!(decoded.traccion_der(), -250);
    assert_eq!(decoded.angulo_s1(), 90);
    assert_eq!(decoded.angulo_s2(), 90);
}

#[test]
fn test_try_from_slice_success() {
    let slice = [0xFA, 0x00, 0x06, 0xFF, 0x5A, 0x5A];
    let res = PaqueteRover::try_from_slice(&slice);
    assert!(res.is_ok());
    let p = res.unwrap();
    assert_eq!(p.traccion_izq(), 250);
    assert_eq!(p.traccion_der(), -250);
    assert_eq!(p.angulo_s1(), 90);
    assert_eq!(p.angulo_s2(), 90);
}

#[test]
fn test_try_from_slice_invalid_lengths() {
    assert_eq!(
        PaqueteRover::try_from_slice(&[]),
        Err(ProtocolError::InvalidLength {
            expected: 6,
            actual: 0
        })
    );

    assert_eq!(
        PaqueteRover::try_from_slice(&[0x01, 0x02, 0x03, 0x04, 0x05]),
        Err(ProtocolError::InvalidLength {
            expected: 6,
            actual: 5
        })
    );

    assert_eq!(
        PaqueteRover::try_from_slice(&[0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]),
        Err(ProtocolError::InvalidLength {
            expected: 6,
            actual: 7
        })
    );
}

#[test]
fn test_protocol_error_traits() {
    let err = ProtocolError::InvalidLength {
        expected: 6,
        actual: 4,
    };
    let cloned = err;
    assert_eq!(err, cloned);

    let err2 = ProtocolError::BufferTooSmall;
    assert_eq!(err2, ProtocolError::BufferTooSmall);

    // Formateo Display
    use core::fmt::Write;
    struct SimpleWriter([u8; 128], usize);
    impl Write for SimpleWriter {
        fn write_str(&mut self, s: &str) -> core::fmt::Result {
            for b in s.as_bytes() {
                if self.1 < self.0.len() {
                    self.0[self.1] = *b;
                    self.1 += 1;
                }
            }
            Ok(())
        }
    }
    let mut writer = SimpleWriter([0u8; 128], 0);
    let _ = write!(writer, "{}", err);
    assert!(writer.1 > 0);

    let mut writer2 = SimpleWriter([0u8; 128], 0);
    let _ = write!(writer2, "{}", err2);
    assert!(writer2.1 > 0);
}
