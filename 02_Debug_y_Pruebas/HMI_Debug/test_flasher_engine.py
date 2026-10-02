"""
Pruebas Unitarias para el Motor de Flasheo y Aprovisionamiento (FlasherEngine).
Parte de la suite HMI Debug del proyecto Rover Lunar V2.0.

Valida la sanitizacion de puertos serie, la construccion de comandos para
arduino-cli y esptool, el formateo de tramas de calibracion, la sincronizacion
serie con persistencia NVS/EEPROM y el flujo de ejecucion con captura de streaming.
"""

from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

_MOD_DIR = Path(__file__).resolve().parent
if str(_MOD_DIR) not in sys.path:
    sys.path.insert(0, str(_MOD_DIR))

from hardware_profiles import PerfilHardware, HardwareProfileRegistry
from flasher_engine import (
    FlasherEngine,
    sanitizar_puerto,
    formatear_trama_calibracion,
    parsear_trama_calibracion,
)


# ==============================================================================
# 1. PRUEBAS DE SANITIZACION DE PUERTOS SERIE
# ==============================================================================

class TestSanitizacionPuertos:
    """Valida la sanitizacion de nombres de puertos para prevenir inyecciones de comandos."""

    def test_puertos_validos_linux(self):
        """Puertos comunes de Linux deben ser aceptados sin modificaciones indebidas."""
        assert sanitizar_puerto("/dev/ttyUSB0") == "/dev/ttyUSB0"
        assert sanitizar_puerto("/dev/ttyACM0") == "/dev/ttyACM0"
        assert sanitizar_puerto("/dev/pts/3") == "/dev/pts/3"
        assert sanitizar_puerto("/dev/serial/by-id/usb-Arduino_LLC-if00") == "/dev/serial/by-id/usb-Arduino_LLC-if00"

    def test_puertos_validos_windows(self):
        """Puertos comunes de Windows deben ser aceptados correctamente."""
        assert sanitizar_puerto("COM1") == "COM1"
        assert sanitizar_puerto("COM10") == "COM10"
        assert sanitizar_puerto(r"\\.\COM12") == r"\\.\COM12"

    def test_limpieza_de_espacios_blancos(self):
        """Espacios al inicio y final deben eliminarse."""
        assert sanitizar_puerto("  COM3  ") == "COM3"
        assert sanitizar_puerto("\t/dev/ttyUSB1\n") == "/dev/ttyUSB1"

    def test_puerto_vacio_o_nulo(self):
        """Un puerto vacio o None debe generar ValueError."""
        with pytest.raises(ValueError, match="El identificador de puerto no puede estar vacio"):
            sanitizar_puerto("")
        with pytest.raises(ValueError, match="El identificador de puerto no puede estar vacio"):
            sanitizar_puerto("   ")
        with pytest.raises(ValueError):
            sanitizar_puerto(None)  # type: ignore

    def test_rechazo_inyeccion_comandos(self):
        """Caracteres peligrosos de shell deben generar ValueError."""
        inyecciones = [
            "COM1; rm -rf /",
            "/dev/ttyUSB0 && cat /etc/passwd",
            "COM3 | echo pwned",
            "COM1`reboot`",
            "COM1$(whoami)",
            "COM1\nCOM2",
            "COM1\rCOM2",
            'COM1" --flag',
            "COM1' --flag",
            "COM 1",  # Espacio en medio
            "/dev/tty;reboot",
            "/dev/ttyUSB0 > /tmp/out",
        ]
        for intento in inyecciones:
            with pytest.raises(ValueError, match="Caracteres invalidos en el identificador de puerto"):
                sanitizar_puerto(intento)


# ==============================================================================
# 2. PRUEBAS DE CONSTRUCCION DE COMANDOS ARDUINO-CLI
# ==============================================================================

class TestComandoArduinoCli:
    """Valida la construccion de comandos de compilacion y subida con arduino-cli."""

    def test_construccion_comando_basico(self):
        engine = FlasherEngine(arduino_cli_path="arduino-cli")
        cmd = engine.construir_comando_arduino_cli(
            puerto="COM3",
            fqbn="arduino:esp32:nano_nora",
            sketch_path="sketches/mi_sketch/mi_sketch.ino",
        )
        assert cmd[0] == "arduino-cli"
        assert "compile" in cmd
        assert "--upload" in cmd
        assert "-p" in cmd
        assert "COM3" in cmd
        assert "-b" in cmd or "--fqbn" in cmd
        assert "arduino:esp32:nano_nora" in cmd
        assert "sketches/mi_sketch/mi_sketch.ino" in cmd

    def test_soporte_pathlib(self):
        engine = FlasherEngine()
        sketch_p = Path("/tmp/rover/transmisor.ino")
        cmd = engine.construir_comando_arduino_cli(
            puerto="/dev/ttyUSB0",
            fqbn="esp32:esp32:esp32c3",
            sketch_path=sketch_p,
        )
        assert "/dev/ttyUSB0" in cmd
        assert str(sketch_p) in cmd

    def test_opcion_verbose(self):
        engine = FlasherEngine()
        cmd = engine.construir_comando_arduino_cli(
            puerto="COM4",
            fqbn="arduino:samd:mkrwan1310",
            sketch_path="sketch.ino",
            verbose=True,
        )
        assert "-v" in cmd or "--verbose" in cmd

    def test_validacion_parametros_invalidos(self):
        engine = FlasherEngine()
        with pytest.raises(ValueError, match="FQBN"):
            engine.construir_comando_arduino_cli(puerto="COM1", fqbn="", sketch_path="sketch.ino")
        with pytest.raises(ValueError, match="sketch"):
            engine.construir_comando_arduino_cli(puerto="COM1", fqbn="test:fqbn", sketch_path="")
        with pytest.raises(ValueError, match="Caracteres invalidos"):
            engine.construir_comando_arduino_cli(puerto="COM1;bad", fqbn="test:fqbn", sketch_path="s.ino")


# ==============================================================================
# 3. PRUEBAS DE CONSTRUCCION DE COMANDOS ESPTOOL
# ==============================================================================

class TestComandoEsptool:
    """Valida la construccion de comandos de flasheo directo con esptool."""

    def test_comando_esptool_binario_directo(self):
        engine = FlasherEngine(esptool_path="esptool.py")
        cmd = engine.construir_comando_esptool(
            puerto="COM5",
            chip="esp32s3",
            bin_path="firmware.bin",
            baud=921600,
            offset="0x0",
            use_python_module=False,
        )
        assert cmd[0] == "esptool.py"
        assert "--chip" in cmd and cmd[cmd.index("--chip") + 1] == "esp32s3"
        assert "--port" in cmd and cmd[cmd.index("--port") + 1] == "COM5"
        assert "--baud" in cmd and cmd[cmd.index("--baud") + 1] == "921600"
        assert "write_flash" in cmd
        assert "0x0" in cmd
        assert "firmware.bin" in cmd

    def test_comando_esptool_modulo_python(self):
        engine = FlasherEngine(python_executable="/usr/bin/python3")
        cmd = engine.construir_comando_esptool(
            puerto="/dev/ttyACM0",
            chip="esp32c3",
            bin_path=Path("/build/output.bin"),
            offset="0x10000",
            use_python_module=True,
        )
        assert cmd[0] == "/usr/bin/python3"
        assert cmd[1] == "-m"
        assert cmd[2] == "esptool"
        assert "--chip" in cmd and cmd[cmd.index("--chip") + 1] == "esp32c3"
        assert "/dev/ttyACM0" in cmd
        assert "0x10000" in cmd
        assert "/build/output.bin" in cmd

    def test_validacion_chip_invalido(self):
        engine = FlasherEngine()
        with pytest.raises(ValueError, match="chip"):
            engine.construir_comando_esptool(puerto="COM1", chip="", bin_path="f.bin")
        with pytest.raises(ValueError, match="bin_path"):
            engine.construir_comando_esptool(puerto="COM1", chip="esp32", bin_path="")


# ==============================================================================
# 4. PRUEBAS DE TRAMA DE CALIBRACION
# ==============================================================================

class TestTramaCalibracion:
    """Valida el formateo y parseo de tramas de calibracion para motores y servos."""

    def test_formateo_con_diccionarios_1_indexados(self):
        trims = {1: 100, 2: 105, 3: 95, 4: 100, 5: 98, 6: 102}
        servos = {1: 90, 2: 88, 3: 92, 4: 90}
        trama = formatear_trama_calibracion(trims, servos)
        assert trama == "CALIB,100,105,95,100,98,102,90,88,92,90\n"

    def test_formateo_con_diccionarios_0_indexados(self):
        trims = {0: 90, 1: 91, 2: 92, 3: 93, 4: 94, 5: 95}
        servos = {0: 85, 1: 86, 2: 87, 3: 88}
        trama = formatear_trama_calibracion(trims, servos)
        assert trama == "CALIB,90,91,92,93,94,95,85,86,87,88\n"

    def test_formateo_con_listas(self):
        trims = [100, 100, 100, 100, 100, 100]
        servos = [90, 90, 90, 90]
        trama = formatear_trama_calibracion(trims, servos)
        assert trama == "CALIB,100,100,100,100,100,100,90,90,90,90\n"

    def test_valores_predeterminados_por_defecto(self):
        """Si se pasan diccionarios vacios o parciales, debe aplicar valores seguros por defecto (100 para trims, 90 para servos)."""
        trama = formatear_trama_calibracion({}, {})
        assert trama == "CALIB,100,100,100,100,100,100,90,90,90,90\n"

    def test_acotacion_y_validacion_limites_servos(self):
        """Los angulos de servos deben estar dentro del rango seguro [10, 170] segun regla de hardware."""
        with pytest.raises(ValueError, match="rango seguro"):
            formatear_trama_calibracion([100] * 6, [5, 90, 90, 90])  # S1 = 5 < 10

        with pytest.raises(ValueError, match="rango seguro"):
            formatear_trama_calibracion([100] * 6, [90, 90, 90, 175])  # S4 = 175 > 170

    def test_validacion_trims_motores(self):
        """Los trims de motores deben estar en rango razonable de ratio (ej. 0 a 255)."""
        with pytest.raises(ValueError, match="trim"):
            formatear_trama_calibracion([-10, 100, 100, 100, 100, 100], [90, 90, 90, 90])
        with pytest.raises(ValueError, match="trim"):
            formatear_trama_calibracion([300, 100, 100, 100, 100, 100], [90, 90, 90, 90])

    def test_parsear_trama_calibracion_valida(self):
        trama = "CALIB,100,102,98,100,101,99,90,92,88,90\n"
        trims, servos = parsear_trama_calibracion(trama)
        assert trims == [100, 102, 98, 100, 101, 99]
        assert servos == [90, 92, 88, 90]

    def test_parsear_trama_invalida(self):
        with pytest.raises(ValueError, match="Formato de trama de calibracion invalido"):
            parsear_trama_calibracion("CMD,100,100,90,90\n")
        with pytest.raises(ValueError, match="Cantidad de parametros"):
            parsear_trama_calibracion("CALIB,100,100,90,90\n")  # Solo 4 parametros


# ==============================================================================
# 5. PRUEBAS DE VERIFICACION DE HERRAMIENTAS
# ==============================================================================

class TestVerificacionHerramientas:
    """Valida la deteccion en el sistema de arduino-cli y esptool."""

    @patch("shutil.which")
    @patch("importlib.util.find_spec")
    def test_ambas_herramientas_disponibles(self, mock_find_spec, mock_which):
        mock_which.side_effect = lambda cmd: "/usr/bin/" + cmd if cmd in ["arduino-cli", "esptool.py"] else None
        mock_find_spec.return_value = MagicMock()

        engine = FlasherEngine()
        tools = engine.verificar_herramientas()
        assert tools["arduino_cli"] is True
        assert tools["esptool"] is True

    @patch("shutil.which")
    @patch("importlib.util.find_spec")
    def test_solo_arduino_cli(self, mock_find_spec, mock_which):
        mock_which.side_effect = lambda cmd: "/usr/bin/arduino-cli" if cmd == "arduino-cli" else None
        mock_find_spec.return_value = None

        engine = FlasherEngine()
        tools = engine.verificar_herramientas()
        assert tools["arduino_cli"] is True
        assert tools["esptool"] is False

    @patch("shutil.which")
    @patch("importlib.util.find_spec")
    def test_esptool_disponible_como_modulo_python(self, mock_find_spec, mock_which):
        mock_which.return_value = None
        mock_find_spec.return_value = MagicMock()  # esptool importable

        engine = FlasherEngine()
        tools = engine.verificar_herramientas()
        assert tools["arduino_cli"] is False
        assert tools["esptool"] is True

    @patch("shutil.which")
    @patch("importlib.util.find_spec")
    def test_ninguna_herramienta_disponible(self, mock_find_spec, mock_which):
        mock_which.return_value = None
        mock_find_spec.return_value = None

        engine = FlasherEngine()
        tools = engine.verificar_herramientas()
        assert tools["arduino_cli"] is False
        assert tools["esptool"] is False


# ==============================================================================
# 6. PRUEBAS DE SINCRONIZACION SERIE Y PERSISTENCIA NVS
# ==============================================================================

class TestSincronizacionCalibracion:
    """Valida el protocolo serie para transferir y persistir calibraciones al receptor."""

    def test_sincronizacion_exitosa_con_ack(self):
        engine = FlasherEngine()
        serial_mock = MagicMock()
        serial_mock.readline.side_effect = [b"CALIB:OK\n", b"PERSIST:OK\n"]

        trims = {1: 100, 2: 100, 3: 100, 4: 100, 5: 100, 6: 100}
        servos = {1: 90, 2: 90, 3: 90, 4: 90}

        exito = engine.sincronizar_calibracion(serial_mock, trims, servos, persistir_nvs=True)
        assert exito is True
        assert serial_mock.write.call_count >= 1
        llamadas_escritura = [call_args[0][0] for call_args in serial_mock.write.call_args_list]
        assert b"CALIB,100,100,100,100,100,100,90,90,90,90\n" in llamadas_escritura

    def test_sincronizacion_sin_persistencia_nvs(self):
        engine = FlasherEngine()
        serial_mock = MagicMock()
        serial_mock.readline.return_value = b"CALIB:OK\n"

        trims = [100] * 6
        servos = [90] * 4

        exito = engine.sincronizar_calibracion(serial_mock, trims, servos, persistir_nvs=False)
        assert exito is True
        # Debe haber enviado solo la trama de calibracion
        assert serial_mock.write.call_count == 1
        assert serial_mock.write.call_args[0][0] == b"CALIB,100,100,100,100,100,100,90,90,90,90\n"

    def test_sincronizacion_fallo_por_nack(self):
        engine = FlasherEngine()
        serial_mock = MagicMock()
        serial_mock.readline.return_value = b"ERROR:CALIB_CHECKSUM\n"

        exito = engine.sincronizar_calibracion(serial_mock, [100] * 6, [90] * 4)
        assert exito is False

    def test_sincronizacion_fallo_excepcion_puerto(self):
        engine = FlasherEngine()
        serial_mock = MagicMock()
        serial_mock.write.side_effect = OSError("Dispositivo desconectado")

        exito = engine.sincronizar_calibracion(serial_mock, [100] * 6, [90] * 4)
        assert exito is False


# ==============================================================================
# 7. PRUEBAS DE EJECUCION DE SUBPROCESOS EN STREAMING
# ==============================================================================

class TestEjecucionSubprocesos:
    """Valida la captura en streaming de stdout y stderr."""

    @patch("subprocess.Popen")
    def test_captura_streaming_exitosa(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "Compiling sketch...\n",
            "Linking everything together...\n",
            "Flash written at 115200 bps\n",
            "",
        ]
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        lineas_log = []
        callback = lambda linea: lineas_log.append(linea)

        engine = FlasherEngine()
        exito = engine._ejecutar_subproceso(["echo", "test"], callback_log=callback)

        assert exito is True
        assert len(lineas_log) == 3
        assert lineas_log[0] == "Compiling sketch..."
        assert lineas_log[2] == "Flash written at 115200 bps"

    @patch("subprocess.Popen")
    def test_captura_streaming_con_error_codigo_salida(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "Error: could not open port\n",
            "",
        ]
        mock_proc.wait.return_value = 1
        mock_popen.return_value = mock_proc

        lineas_log = []
        engine = FlasherEngine()
        exito = engine._ejecutar_subproceso(["false"], callback_log=lineas_log.append)

        assert exito is False
        assert "Error: could not open port" in lineas_log


# ==============================================================================
# 8. PRUEBAS DEL METODO PRINCIPAL FLASHEAR
# ==============================================================================

class TestMetodoFlashear:
    """Valida el metodo flashear() integrando perfiles, roles y herramientas."""

    def test_flasheo_puerto_invalido(self):
        engine = FlasherEngine()
        perfil = HardwareProfileRegistry().obtener_perfil("ARDUINO_NANO_ESP32")
        logs = []
        exito = engine.flashear(
            puerto="COM1; bad_cmd",
            perfil=perfil,
            rol="TX",
            callback_log=logs.append,
        )
        assert exito is False
        assert any("invalido" in log.lower() for log in logs)

    def test_flasheo_rol_no_soportado(self):
        engine = FlasherEngine()
        perfil = HardwareProfileRegistry().obtener_perfil("ARDUINO_MKR_1310")
        logs = []
        # MKR 1310 no soporta rol TX
        exito = engine.flashear(
            puerto="COM2",
            perfil=perfil,
            rol="TX",
            callback_log=logs.append,
        )
        assert exito is False
        assert any("no soporta el rol" in log.lower() for log in logs)

    def test_flasheo_archivo_no_existente(self):
        engine = FlasherEngine()
        perfil_ficticio = PerfilHardware(
            id="FICTICIO",
            nombre="Ficticio",
            mcu="ESP32",
            fqbn="test:fqbn",
            sketch_tx="no_existe/archivo_inexistente.ino",
        )
        logs = []
        exito = engine.flashear(
            puerto="COM1",
            perfil=perfil_ficticio,
            rol="TX",
            callback_log=logs.append,
        )
        assert exito is False
        assert any("no se encuentra" in log.lower() for log in logs)

    @patch.object(FlasherEngine, "verificar_herramientas")
    @patch.object(FlasherEngine, "_ejecutar_subproceso")
    def test_flasheo_con_arduino_cli_exitoso(self, mock_ejecutar, mock_herramientas):
        mock_herramientas.return_value = {"arduino_cli": True, "esptool": True}
        mock_ejecutar.return_value = True

        registry = HardwareProfileRegistry()
        perfil = registry.obtener_perfil("ARDUINO_NANO_ESP32")

        logs = []
        engine = FlasherEngine()
        exito = engine.flashear(
            puerto="/dev/ttyACM0",
            perfil=perfil,
            rol="TX",
            callback_log=logs.append,
        )

        assert exito is True
        assert mock_ejecutar.called
        cmd_ejecutado = mock_ejecutar.call_args[0][0]
        assert "arduino-cli" in cmd_ejecutado[0]
        assert "/dev/ttyACM0" in cmd_ejecutado
        assert "arduino:esp32:nano_nora" in cmd_ejecutado

    @patch.object(FlasherEngine, "verificar_herramientas")
    @patch.object(FlasherEngine, "_ejecutar_subproceso")
    def test_flasheo_fallback_esptool_con_bin(self, mock_ejecutar, mock_herramientas, tmp_path):
        # arduino-cli no disponible, esptool disponible
        mock_herramientas.return_value = {"arduino_cli": False, "esptool": True}
        mock_ejecutar.return_value = True

        bin_falso = tmp_path / "firmware.bin"
        bin_falso.write_bytes(b"\x00" * 100)

        perfil = PerfilHardware(
            id="NANO_TEST",
            nombre="Nano Test",
            mcu="ESP32-S3",
            fqbn="arduino:esp32:nano_nora",
            sketch_tx=str(bin_falso),
        )

        logs = []
        engine = FlasherEngine()
        exito = engine.flashear(
            puerto="COM3",
            perfil=perfil,
            rol="TX",
            callback_log=logs.append,
        )

        assert exito is True
        assert mock_ejecutar.called
        cmd_ejecutado = mock_ejecutar.call_args[0][0]
        assert any("esptool" in part for part in cmd_ejecutado)
        assert "esp32s3" in cmd_ejecutado
        assert "COM3" in cmd_ejecutado

    @patch.object(FlasherEngine, "verificar_herramientas")
    def test_flasheo_sin_herramientas_disponibles(self, mock_herramientas):
        mock_herramientas.return_value = {"arduino_cli": False, "esptool": False}

        registry = HardwareProfileRegistry()
        perfil = registry.obtener_perfil("ARDUINO_NANO_ESP32")

        logs = []
        engine = FlasherEngine()
        exito = engine.flashear(
            puerto="COM1",
            perfil=perfil,
            rol="TX",
            callback_log=logs.append,
        )

        assert exito is False
        assert any("no se encontraron herramientas" in log.lower() for log in logs)


# ==============================================================================
# 9. REGLA ESTRICTA DE PROYECTO: CERO EMOJIS
# ==============================================================================

def test_cero_emojis_en_archivos_de_tarea():
    """Verifica que no existan emojis en los archivos fuente creados para la Tarea 3."""
    directorio = Path(__file__).resolve().parent
    archivos = [
        directorio / "flasher_engine.py",
        directorio / "test_flasher_engine.py",
    ]

    patron_emoji = re.compile(
        "[\U00010000-\U0010ffff"
        "\u2600-\u26FF"
        "\u2700-\u27BF"
        "\u2300-\u23FF"
        "\u2B50-\u2B55"
        "\u203C\u2049\u2122\u2139\u2194-\u2199\u21A9-\u21AA"
        "]",
        flags=re.UNICODE,
    )

    for archivo in archivos:
        if archivo.exists():
            contenido = archivo.read_text(encoding="utf-8")
            coincidencias = patron_emoji.findall(contenido)
            assert not coincidencias, (
                f"Se detectaron emojis prohibidos en {archivo.name}: {coincidencias}"
            )
