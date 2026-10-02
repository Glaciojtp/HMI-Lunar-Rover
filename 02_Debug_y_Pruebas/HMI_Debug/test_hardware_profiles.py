"""
Pruebas unitarias para el modulo de perfiles de hardware y autodeteccion.
Verifica la identificacion pasiva (VID:PID), identificacion activa (handshake),
y resolucion de perfiles de microcontroladores soportados en el proyecto Rover Lunar V2.0.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

_MOD_DIR = Path(__file__).resolve().parent
if str(_MOD_DIR) not in sys.path:
    sys.path.insert(0, str(_MOD_DIR))

from hardware_profiles import (
    PerfilHardware,
    HardwareProfileRegistry,
    parsear_handshake,
    PERFIL_DEFAULT_ID,
)


@pytest.fixture
def registry():
    """Instancia limpia de HardwareProfileRegistry para cada prueba."""
    return HardwareProfileRegistry()


class TestHardwareProfilesBasicos:
    """Pruebas de inicializacion y estructura de perfiles registrados."""

    def test_listar_perfiles_contiene_tres_perfiles(self, registry):
        perfiles = registry.listar_perfiles()
        assert len(perfiles) == 3
        ids = [p.id for p in perfiles]
        assert "ARDUINO_NANO_ESP32" in ids
        assert "ESP32_C3_SUPERMINI" in ids
        assert "ARDUINO_MKR_1310" in ids

    def test_perfil_default_es_arduino_nano_esp32(self, registry):
        assert registry.perfil_default.id == PERFIL_DEFAULT_ID
        assert registry.perfil_default.id == "ARDUINO_NANO_ESP32"
        assert registry.obtener_perfil_default().id == "ARDUINO_NANO_ESP32"

    def test_campos_obligatorios_perfil_nano_esp32(self, registry):
        perfil = registry.obtener_perfil("ARDUINO_NANO_ESP32")
        assert perfil.id == "ARDUINO_NANO_ESP32"
        assert perfil.nombre == "Arduino Nano ESP32"
        assert perfil.mcu == "ESP32-S3"
        assert (0x2341, 0x0070) in perfil.vid_pid_list
        assert (0x2341, 0x0069) in perfil.vid_pid_list
        assert perfil.fqbn == "arduino:esp32:nano_nora"
        assert perfil.sketch_tx is not None
        assert "Transmisor_ArduinoNano_ESP32.ino" in perfil.sketch_tx
        assert perfil.sketch_rx is not None
        assert "Ejecutor_ArduinoNano_ESP32.ino" in perfil.sketch_rx
        assert perfil.soporta_tx is True
        assert perfil.soporta_rx is True

    def test_campos_obligatorios_perfil_esp32_c3(self, registry):
        perfil = registry.obtener_perfil("ESP32_C3_SUPERMINI")
        assert perfil.id == "ESP32_C3_SUPERMINI"
        assert perfil.nombre == "ESP32-C3 SuperMini"
        assert perfil.mcu == "ESP32-C3"
        assert (0x303A, 0x1001) in perfil.vid_pid_list
        assert (0x1A86, 0x7523) in perfil.vid_pid_list
        assert (0x10C4, 0xEA60) in perfil.vid_pid_list
        assert perfil.fqbn == "esp32:esp32:esp32c3"
        assert perfil.sketch_tx is not None
        assert "Control_ESP32_C3_Optimizado.ino" in perfil.sketch_tx
        assert perfil.sketch_rx is None
        assert perfil.soporta_tx is True
        assert perfil.soporta_rx is False

    def test_campos_obligatorios_perfil_mkr1310(self, registry):
        perfil = registry.obtener_perfil("ARDUINO_MKR_1310")
        assert perfil.id == "ARDUINO_MKR_1310"
        assert perfil.nombre == "Arduino MKR WAN 1310"
        assert perfil.mcu == "SAMD21"
        assert (0x2341, 0x8054) in perfil.vid_pid_list
        assert (0x2341, 0x0054) in perfil.vid_pid_list
        assert perfil.fqbn == "arduino:samd:mkrwan1310"
        assert perfil.sketch_tx is None
        assert perfil.sketch_rx is not None
        assert "Ejecutor_ArduinoMKR_Optimizado.ino" in perfil.sketch_rx
        assert perfil.soporta_tx is False
        assert perfil.soporta_rx is True


class TestDeteccionPasivaVidPid:
    """Pruebas de identificacion pasiva a partir de metadatos de puerto USB."""

    def test_detectar_nano_esp32_por_objeto_port_info(self, registry):
        port_info = SimpleNamespace(vid=0x2341, pid=0x0070, device="/dev/ttyACM0")
        perfil = registry.detectar_perfil(port_info)
        assert perfil is not None
        assert perfil.id == "ARDUINO_NANO_ESP32"

    def test_detectar_nano_esp32_bootloader(self, registry):
        port_info = SimpleNamespace(vid=0x2341, pid=0x0069, device="COM4")
        perfil = registry.detectar_perfil(port_info)
        assert perfil is not None
        assert perfil.id == "ARDUINO_NANO_ESP32"

    def test_detectar_esp32_c3_cdc_nativo(self, registry):
        port_info = SimpleNamespace(vid=0x303A, pid=0x1001, device="COM5")
        perfil = registry.detectar_perfil(port_info)
        assert perfil is not None
        assert perfil.id == "ESP32_C3_SUPERMINI"

    def test_detectar_esp32_c3_ch340(self, registry):
        port_info = SimpleNamespace(vid=0x1A86, pid=0x7523, device="/dev/ttyUSB0")
        perfil = registry.detectar_perfil(port_info)
        assert perfil is not None
        assert perfil.id == "ESP32_C3_SUPERMINI"

    def test_detectar_esp32_c3_cp2102(self, registry):
        port_info = SimpleNamespace(vid=0x10C4, pid=0xEA60, device="/dev/ttyUSB1")
        perfil = registry.detectar_perfil(port_info)
        assert perfil is not None
        assert perfil.id == "ESP32_C3_SUPERMINI"

    def test_detectar_mkr1310_cdc(self, registry):
        port_info = SimpleNamespace(vid=0x2341, pid=0x8054, device="COM3")
        perfil = registry.detectar_perfil(port_info)
        assert perfil is not None
        assert perfil.id == "ARDUINO_MKR_1310"

    def test_detectar_mkr1310_bootloader(self, registry):
        port_info = SimpleNamespace(vid=0x2341, pid=0x0054, device="COM3")
        perfil = registry.detectar_perfil(port_info)
        assert perfil is not None
        assert perfil.id == "ARDUINO_MKR_1310"

    def test_detectar_por_diccionario(self, registry):
        perfil = registry.detectar_perfil({"vid": 0x2341, "pid": 0x0070})
        assert perfil is not None
        assert perfil.id == "ARDUINO_NANO_ESP32"

    def test_detectar_por_tupla(self, registry):
        perfil = registry.detectar_perfil((0x303A, 0x1001))
        assert perfil is not None
        assert perfil.id == "ESP32_C3_SUPERMINI"

    def test_detectar_por_cadena_hex(self, registry):
        perfil = registry.detectar_perfil("USB VID:PID=2341:8054")
        assert perfil is not None
        assert perfil.id == "ARDUINO_MKR_1310"

    def test_detectar_desconocido_retorna_none_por_defecto(self, registry):
        port_info = SimpleNamespace(vid=0x9999, pid=0x8888, device="COM99")
        perfil = registry.detectar_perfil(port_info)
        assert perfil is None

    def test_detectar_desconocido_con_fallback_retorna_default(self, registry):
        port_info = SimpleNamespace(vid=0x9999, pid=0x8888, device="COM99")
        perfil = registry.detectar_perfil(port_info, fallback_default=True)
        assert perfil is not None
        assert perfil.id == "ARDUINO_NANO_ESP32"

    def test_detectar_port_info_nulo_o_sin_vid(self, registry):
        assert registry.detectar_perfil(None) is None
        assert registry.detectar_perfil(SimpleNamespace(vid=None, pid=None)) is None


class TestObtenerPerfil:
    """Pruebas de busqueda por ID, nombre y alias."""

    def test_obtener_por_id_exacto(self, registry):
        p1 = registry.obtener_perfil("ARDUINO_NANO_ESP32")
        p2 = registry.obtener_perfil("ESP32_C3_SUPERMINI")
        p3 = registry.obtener_perfil("ARDUINO_MKR_1310")
        assert p1.id == "ARDUINO_NANO_ESP32"
        assert p2.id == "ESP32_C3_SUPERMINI"
        assert p3.id == "ARDUINO_MKR_1310"

    def test_obtener_por_nombre(self, registry):
        p = registry.obtener_perfil("Arduino Nano ESP32")
        assert p.id == "ARDUINO_NANO_ESP32"

    def test_obtener_por_alias_handshake(self, registry):
        assert registry.obtener_perfil("NANO_ESP32").id == "ARDUINO_NANO_ESP32"
        assert registry.obtener_perfil("ESP32C3").id == "ESP32_C3_SUPERMINI"
        assert registry.obtener_perfil("MKR1310").id == "ARDUINO_MKR_1310"

    def test_obtener_perfil_inexistente_lanza_keyerror(self, registry):
        with pytest.raises(KeyError):
            registry.obtener_perfil("PERFIL_INEXISTENTE")

    def test_obtener_perfil_inexistente_con_default(self, registry):
        res = registry.obtener_perfil("INEXISTENTE", default=None)
        assert res is None


class TestHandshakeParser:
    """Pruebas para el parseo de respuestas de handshake serie activo."""

    def test_parsear_handshake_nano_esp32_tx(self):
        placa, rol, version = parsear_handshake("ID:NANO_ESP32:TX:v2.1")
        assert placa == "NANO_ESP32"
        assert rol == "TX"
        assert version == "v2.1"

    def test_parsear_handshake_nano_esp32_rx(self):
        placa, rol, version = parsear_handshake("ID:NANO_ESP32:RX:v2.1\r\n")
        assert placa == "NANO_ESP32"
        assert rol == "RX"
        assert version == "v2.1"

    def test_parsear_handshake_mkr1310_rx(self):
        placa, rol, version = parsear_handshake("ID:MKR1310:RX:v2.0\n")
        assert placa == "MKR1310"
        assert rol == "RX"
        assert version == "v2.0"

    def test_parsear_handshake_esp32c3_tx(self):
        placa, rol, version = parsear_handshake("ID:ESP32C3:TX:v2.0")
        assert placa == "ESP32C3"
        assert rol == "TX"
        assert version == "v2.0"

    def test_parsear_handshake_desde_metodo_registry(self, registry):
        placa, rol, version = registry.parsear_handshake("ID:NANO_ESP32:TX:v2.1")
        assert placa == "NANO_ESP32"
        assert rol == "TX"
        assert version == "v2.1"

    def test_parsear_handshake_invalido_lanza_valueerror(self):
        with pytest.raises(ValueError):
            parsear_handshake("MENSAJE_NO_VALIDO")

        with pytest.raises(ValueError):
            parsear_handshake("ID:SOLO_DOS_CAMPOS")

        with pytest.raises(ValueError):
            parsear_handshake("")

    def test_parsear_handshake_no_estricto_retorna_none(self):
        assert parsear_handshake("INVALIDO", strict=False) is None
        assert parsear_handshake("", strict=False) is None

    def test_resolver_perfil_desde_handshake(self, registry):
        perfil_tx, rol, ver = registry.resolver_handshake("ID:NANO_ESP32:TX:v2.1")
        assert perfil_tx.id == "ARDUINO_NANO_ESP32"
        assert rol == "TX"
        assert ver == "v2.1"

        perfil_rx, rol_rx, ver_rx = registry.resolver_handshake("ID:MKR1310:RX:v2.0")
        assert perfil_rx.id == "ARDUINO_MKR_1310"
        assert rol_rx == "RX"
        assert ver_rx == "v2.0"


class TestArchivosSketchesEnDisco:
    """Verifica que los sketches asociados a los perfiles existan en el arbol del repositorio."""

    def test_existencia_archivos_sketches(self, registry):
        repo_root = Path(__file__).resolve().parents[2]
        for perfil in registry.listar_perfiles():
            if perfil.sketch_tx:
                ruta_tx = repo_root / perfil.sketch_tx
                assert ruta_tx.is_file(), f"Falta archivo sketch TX: {ruta_tx}"
            if perfil.sketch_rx:
                ruta_rx = repo_root / perfil.sketch_rx
                assert ruta_rx.is_file(), f"Falta archivo sketch RX: {ruta_rx}"
