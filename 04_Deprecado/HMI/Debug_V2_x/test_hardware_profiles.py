"""
Pruebas unitarias para el modulo de perfiles de hardware y autodeteccion.
Verifica la identificacion pasiva (VID:PID), identificacion activa (handshake),
y resolucion de perfiles de microcontroladores soportados en el proyecto Rover Lunar V2.0.
"""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_MOD_DIR = Path(__file__).resolve().parent
if str(_MOD_DIR) not in sys.path:
    sys.path.insert(0, str(_MOD_DIR))

from hardware_profiles import (
    PerfilHardware,
    HardwareProfileRegistry,
    parsear_handshake,
    PERFIL_DEFAULT_ID,
)


class TestHardwareProfilesBasicos(unittest.TestCase):
    """Pruebas de inicializacion y estructura de perfiles registrados."""

    def setUp(self):
        self.registry = HardwareProfileRegistry()

    def test_listar_perfiles_contiene_tres_perfiles(self):
        perfiles = self.registry.listar_perfiles()
        self.assertEqual(len(perfiles), 3)
        ids = [p.id for p in perfiles]
        self.assertIn("ARDUINO_NANO_ESP32", ids)
        self.assertIn("ESP32_C3_SUPERMINI", ids)
        self.assertIn("ARDUINO_MKR_1310", ids)

    def test_perfil_default_es_arduino_nano_esp32(self):
        self.assertEqual(self.registry.perfil_default.id, PERFIL_DEFAULT_ID)
        self.assertEqual(self.registry.perfil_default.id, "ARDUINO_NANO_ESP32")
        self.assertEqual(self.registry.obtener_perfil_default().id, "ARDUINO_NANO_ESP32")

    def test_campos_obligatorios_perfil_nano_esp32(self):
        perfil = self.registry.obtener_perfil("ARDUINO_NANO_ESP32")
        self.assertEqual(perfil.id, "ARDUINO_NANO_ESP32")
        self.assertEqual(perfil.nombre, "Arduino Nano ESP32")
        self.assertEqual(perfil.mcu, "ESP32-S3")
        self.assertIn((0x2341, 0x0070), perfil.vid_pid_list)
        self.assertIn((0x2341, 0x0069), perfil.vid_pid_list)
        self.assertEqual(perfil.fqbn, "arduino:esp32:nano_nora")
        self.assertIsNotNone(perfil.sketch_tx)
        self.assertIn("Transmisor_ArduinoNano_ESP32.ino", perfil.sketch_tx)
        self.assertIsNotNone(perfil.sketch_rx)
        self.assertIn("Ejecutor_ArduinoNano_ESP32.ino", perfil.sketch_rx)
        self.assertTrue(perfil.soporta_tx)
        self.assertTrue(perfil.soporta_rx)

    def test_campos_obligatorios_perfil_esp32_c3(self):
        perfil = self.registry.obtener_perfil("ESP32_C3_SUPERMINI")
        self.assertEqual(perfil.id, "ESP32_C3_SUPERMINI")
        self.assertEqual(perfil.nombre, "ESP32-C3 SuperMini")
        self.assertEqual(perfil.mcu, "ESP32-C3")
        self.assertIn((0x303A, 0x1001), perfil.vid_pid_list)
        self.assertIn((0x1A86, 0x7523), perfil.vid_pid_list)
        self.assertIn((0x10C4, 0xEA60), perfil.vid_pid_list)
        self.assertEqual(perfil.fqbn, "esp32:esp32:esp32c3")
        self.assertIsNotNone(perfil.sketch_tx)
        self.assertIn("Control_ESP32_C3_Optimizado.ino", perfil.sketch_tx)
        self.assertIsNone(perfil.sketch_rx)
        self.assertTrue(perfil.soporta_tx)
        self.assertFalse(perfil.soporta_rx)

    def test_campos_obligatorios_perfil_mkr1310(self):
        perfil = self.registry.obtener_perfil("ARDUINO_MKR_1310")
        self.assertEqual(perfil.id, "ARDUINO_MKR_1310")
        self.assertEqual(perfil.nombre, "Arduino MKR WAN 1310")
        self.assertEqual(perfil.mcu, "SAMD21")
        self.assertIn((0x2341, 0x8054), perfil.vid_pid_list)
        self.assertIn((0x2341, 0x0054), perfil.vid_pid_list)
        self.assertEqual(perfil.fqbn, "arduino:samd:mkrwan1310")
        self.assertIsNone(perfil.sketch_tx)
        self.assertIsNotNone(perfil.sketch_rx)
        self.assertIn("Ejecutor_ArduinoMKR_Optimizado.ino", perfil.sketch_rx)
        self.assertFalse(perfil.soporta_tx)
        self.assertTrue(perfil.soporta_rx)


class TestDeteccionPasivaVidPid(unittest.TestCase):
    """Pruebas de identificacion pasiva a partir de metadatos de puerto USB."""

    def setUp(self):
        self.registry = HardwareProfileRegistry()

    def test_detectar_nano_esp32_por_objeto_port_info(self):
        port_info = SimpleNamespace(vid=0x2341, pid=0x0070, device="/dev/ttyACM0")
        perfil = self.registry.detectar_perfil(port_info)
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ARDUINO_NANO_ESP32")

    def test_detectar_nano_esp32_bootloader(self):
        port_info = SimpleNamespace(vid=0x2341, pid=0x0069, device="COM4")
        perfil = self.registry.detectar_perfil(port_info)
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ARDUINO_NANO_ESP32")

    def test_detectar_esp32_c3_cdc_nativo(self):
        port_info = SimpleNamespace(vid=0x303A, pid=0x1001, device="COM5")
        perfil = self.registry.detectar_perfil(port_info)
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ESP32_C3_SUPERMINI")

    def test_detectar_esp32_c3_ch340(self):
        port_info = SimpleNamespace(vid=0x1A86, pid=0x7523, device="/dev/ttyUSB0")
        perfil = self.registry.detectar_perfil(port_info)
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ESP32_C3_SUPERMINI")

    def test_detectar_esp32_c3_cp2102(self):
        port_info = SimpleNamespace(vid=0x10C4, pid=0xEA60, device="/dev/ttyUSB1")
        perfil = self.registry.detectar_perfil(port_info)
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ESP32_C3_SUPERMINI")

    def test_detectar_mkr1310_cdc(self):
        port_info = SimpleNamespace(vid=0x2341, pid=0x8054, device="COM3")
        perfil = self.registry.detectar_perfil(port_info)
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ARDUINO_MKR_1310")

    def test_detectar_mkr1310_bootloader(self):
        port_info = SimpleNamespace(vid=0x2341, pid=0x0054, device="COM3")
        perfil = self.registry.detectar_perfil(port_info)
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ARDUINO_MKR_1310")

    def test_detectar_por_diccionario(self):
        perfil = self.registry.detectar_perfil({"vid": 0x2341, "pid": 0x0070})
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ARDUINO_NANO_ESP32")

    def test_detectar_por_tupla(self):
        perfil = self.registry.detectar_perfil((0x303A, 0x1001))
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ESP32_C3_SUPERMINI")

    def test_detectar_por_cadena_hex(self):
        perfil = self.registry.detectar_perfil("USB VID:PID=2341:8054")
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ARDUINO_MKR_1310")

    def test_detectar_desconocido_retorna_none_por_defecto(self):
        port_info = SimpleNamespace(vid=0x9999, pid=0x8888, device="COM99")
        perfil = self.registry.detectar_perfil(port_info)
        self.assertIsNone(perfil)

    def test_detectar_desconocido_con_fallback_retorna_default(self):
        port_info = SimpleNamespace(vid=0x9999, pid=0x8888, device="COM99")
        perfil = self.registry.detectar_perfil(port_info, fallback_default=True)
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.id, "ARDUINO_NANO_ESP32")

    def test_detectar_port_info_nulo_o_sin_vid(self):
        self.assertIsNone(self.registry.detectar_perfil(None))
        self.assertIsNone(self.registry.detectar_perfil(SimpleNamespace(vid=None, pid=None)))


class TestObtenerPerfil(unittest.TestCase):
    """Pruebas de busqueda por ID, nombre y alias."""

    def setUp(self):
        self.registry = HardwareProfileRegistry()

    def test_obtener_por_id_exacto(self):
        p1 = self.registry.obtener_perfil("ARDUINO_NANO_ESP32")
        p2 = self.registry.obtener_perfil("ESP32_C3_SUPERMINI")
        p3 = self.registry.obtener_perfil("ARDUINO_MKR_1310")
        self.assertEqual(p1.id, "ARDUINO_NANO_ESP32")
        self.assertEqual(p2.id, "ESP32_C3_SUPERMINI")
        self.assertEqual(p3.id, "ARDUINO_MKR_1310")

    def test_obtener_por_nombre(self):
        p = self.registry.obtener_perfil("Arduino Nano ESP32")
        self.assertEqual(p.id, "ARDUINO_NANO_ESP32")

    def test_obtener_por_alias_handshake(self):
        self.assertEqual(self.registry.obtener_perfil("NANO_ESP32").id, "ARDUINO_NANO_ESP32")
        self.assertEqual(self.registry.obtener_perfil("ESP32C3").id, "ESP32_C3_SUPERMINI")
        self.assertEqual(self.registry.obtener_perfil("MKR1310").id, "ARDUINO_MKR_1310")

    def test_obtener_perfil_inexistente_lanza_keyerror(self):
        with self.assertRaises(KeyError):
            self.registry.obtener_perfil("PERFIL_INEXISTENTE")

    def test_obtener_perfil_inexistente_con_default(self):
        res = self.registry.obtener_perfil("INEXISTENTE", default=None)
        self.assertIsNone(res)


class TestHandshakeParser(unittest.TestCase):
    """Pruebas para el parseo de respuestas de handshake serie activo."""

    def setUp(self):
        self.registry = HardwareProfileRegistry()

    def test_parsear_handshake_nano_esp32_tx_v2_1(self):
        placa, rol, version = parsear_handshake("ID:NANO_ESP32:TX:v2.1")
        self.assertEqual(placa, "NANO_ESP32")
        self.assertEqual(rol, "TX")
        self.assertEqual(version, "v2.1")

    def test_parsear_handshake_nano_esp32_tx_v2_2(self):
        placa, rol, version = parsear_handshake("ID:NANO_ESP32:TX:v2.2")
        self.assertEqual(placa, "NANO_ESP32")
        self.assertEqual(rol, "TX")
        self.assertEqual(version, "v2.2")

    def test_parsear_handshake_nano_esp32_rx_v2_2(self):
        placa, rol, version = parsear_handshake("ID:NANO_ESP32:RX:v2.2\r\n")
        self.assertEqual(placa, "NANO_ESP32")
        self.assertEqual(rol, "RX")
        self.assertEqual(version, "v2.2")

    def test_parsear_handshake_mkr1310_rx(self):
        placa, rol, version = parsear_handshake("ID:MKR1310:RX:v2.0\n")
        self.assertEqual(placa, "MKR1310")
        self.assertEqual(rol, "RX")
        self.assertEqual(version, "v2.0")

    def test_parsear_handshake_esp32c3_tx(self):
        placa, rol, version = parsear_handshake("ID:ESP32C3:TX:v2.0")
        self.assertEqual(placa, "ESP32C3")
        self.assertEqual(rol, "TX")
        self.assertEqual(version, "v2.0")

    def test_parsear_handshake_desde_metodo_registry(self):
        placa, rol, version = self.registry.parsear_handshake("ID:NANO_ESP32:TX:v2.2")
        self.assertEqual(placa, "NANO_ESP32")
        self.assertEqual(rol, "TX")
        self.assertEqual(version, "v2.2")

    def test_parsear_handshake_invalido_lanza_valueerror(self):
        with self.assertRaises(ValueError):
            parsear_handshake("MENSAJE_NO_VALIDO")

        with self.assertRaises(ValueError):
            parsear_handshake("ID:SOLO_DOS_CAMPOS")

        with self.assertRaises(ValueError):
            parsear_handshake("")

    def test_parsear_handshake_no_estricto_retorna_none(self):
        self.assertIsNone(parsear_handshake("INVALIDO", strict=False))
        self.assertIsNone(parsear_handshake("", strict=False))

    def test_resolver_perfil_desde_handshake(self):
        perfil_tx, rol, ver = self.registry.resolver_handshake("ID:NANO_ESP32:TX:v2.2")
        self.assertEqual(perfil_tx.id, "ARDUINO_NANO_ESP32")
        self.assertEqual(rol, "TX")
        self.assertEqual(ver, "v2.2")

        perfil_rx, rol_rx, ver_rx = self.registry.resolver_handshake("ID:MKR1310:RX:v2.0")
        self.assertEqual(perfil_rx.id, "ARDUINO_MKR_1310")
        self.assertEqual(rol_rx, "RX")
        self.assertEqual(ver_rx, "v2.0")


class TestArchivosSketchesEnDisco(unittest.TestCase):
    """Verifica que los sketches asociados a los perfiles existan en el arbol del repositorio."""

    def setUp(self):
        self.registry = HardwareProfileRegistry()

    def test_existencia_archivos_sketches(self):
        repo_root = Path(__file__).resolve().parents[2]
        for perfil in self.registry.listar_perfiles():
            if perfil.sketch_tx:
                ruta_tx = repo_root / perfil.sketch_tx
                self.assertTrue(ruta_tx.is_file(), f"Falta archivo sketch TX: {ruta_tx}")
            if perfil.sketch_rx:
                ruta_rx = repo_root / perfil.sketch_rx
                self.assertTrue(ruta_rx.is_file(), f"Falta archivo sketch RX: {ruta_rx}")


if __name__ == "__main__":
    unittest.main()
