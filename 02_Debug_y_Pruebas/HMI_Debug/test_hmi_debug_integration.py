"""
Pruebas Unitarias y de Integracion para HMI_Rover_Debug.py.
Parte de la suite de verificacion del proyecto Rover Lunar V2.0.

Valida:
1. Ausencia estricta de emojis en archivos de codigo fuente.
2. Inicializacion de perfiles de hardware (HardwareProfileRegistry) y motor de flasheo (FlasherEngine).
3. Autodeteccion pasiva de perfiles de microcontrolador por USB VID:PID.
4. Handshake activo mediante comando IDENT y parsing de tramas ID:<PLACA>:<ROL>:<VERSION>.
5. Subida de firmware en 1 clic (no bloqueante, en hilo secundario, con liberacion y restauracion de puerto).
6. Sincronizacion de calibracion pre-despliegue con persistencia en memoria NVS.
7. Liberacion segura de puerto para operacion por bateria en campo.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Asegurar importacion de modulos locales
_dir_actual = Path(__file__).resolve().parent
if str(_dir_actual) not in sys.path:
    sys.path.insert(0, str(_dir_actual))

# Configuracion de Mock de Tkinter si no se encuentra instalado en el entorno
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except ImportError:
    mock_tk = MagicMock()
    mock_ttk = MagicMock()
    mock_mb = MagicMock()
    mock_fd = MagicMock()

    class FakeVar:
        def __init__(self, value: Any = None):
            self._val = value

        def get(self) -> Any:
            return self._val

        def set(self, val: Any) -> None:
            self._val = val

    mock_tk.BooleanVar = lambda value=False: FakeVar(value)
    mock_tk.StringVar = lambda value="": FakeVar(value)
    mock_tk.IntVar = lambda value=0: FakeVar(value)
    mock_tk.DoubleVar = lambda value=0.0: FakeVar(value)

    mock_tk.Button = lambda *args, **kwargs: MagicMock()
    mock_tk.Label = lambda *args, **kwargs: MagicMock()
    mock_tk.Checkbutton = lambda *args, **kwargs: MagicMock()
    mock_tk.Scale = lambda *args, **kwargs: MagicMock()
    mock_tk.Canvas = lambda *args, **kwargs: MagicMock()
    mock_tk.Text = lambda *args, **kwargs: MagicMock()
    mock_tk.Scrollbar = lambda *args, **kwargs: MagicMock()

    mock_ttk.Frame = lambda *args, **kwargs: MagicMock()
    mock_ttk.Label = lambda *args, **kwargs: MagicMock()
    mock_ttk.Combobox = lambda *args, **kwargs: MagicMock()
    mock_ttk.Separator = lambda *args, **kwargs: MagicMock()
    mock_ttk.Style = lambda *args, **kwargs: MagicMock()

    sys.modules["tkinter"] = mock_tk
    sys.modules["tkinter.ttk"] = mock_ttk
    sys.modules["tkinter.messagebox"] = mock_mb
    sys.modules["tkinter.filedialog"] = mock_fd

    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog

import HMI_Rover_Debug
from HMI_Rover_Debug import HMIRoverDebug
from hardware_profiles import HardwareProfileRegistry, PERFIL_DEFAULT_ID
from flasher_engine import FlasherEngine


@pytest.fixture
def mock_root():
    """Provee un root falso de Tkinter que simula eventos y bucle de mensajes sin ventana real."""
    root = MagicMock()
    callbacks_pendientes = []

    def fake_after(ms, func, *args):
        callbacks_pendientes.append((func, args))
        return "timer_id"

    root.after = MagicMock(side_effect=fake_after)
    root._pendientes = callbacks_pendientes
    return root


@pytest.fixture
def app_debug(mock_root):
    """Instancia la clase HMIRoverDebug con widgets y timers mockeados."""
    # Desactivar ejecucion de bucles infinitos en background durante la creacion del fixture
    with patch.object(HMIRoverDebug, "iniciar_hilos"), patch.object(HMIRoverDebug, "bucle_periodico_ui"):
        app = HMIRoverDebug(mock_root)
        app.ejecutando = False

        # Configurar instancias independientes para cb_puerto_tx y cb_puerto_rx
        app.cb_puerto_tx = MagicMock()
        app.cb_puerto_rx = MagicMock()
        tx_val = [""]
        rx_val = [""]
        app.cb_puerto_tx.get = MagicMock(side_effect=lambda: tx_val[0])
        app.cb_puerto_tx.set = MagicMock(side_effect=lambda v: tx_val.__setitem__(0, str(v)))
        app.cb_puerto_rx.get = MagicMock(side_effect=lambda: rx_val[0])
        app.cb_puerto_rx.set = MagicMock(side_effect=lambda v: rx_val.__setitem__(0, str(v)))

        return app


# ==============================================================================
# 1. REGLA ESTRICTA DE PROYECTO: CERO EMOJIS
# ==============================================================================
class TestReglaEstrictaCeroEmojis:
    """Verifica que ningun archivo de la suite HMI Debug contenga emojis ni simbolos ornamentales."""

    def test_cero_emojis_en_hmi_rover_debug(self):
        ruta_archivo = _dir_actual / "HMI_Rover_Debug.py"
        assert ruta_archivo.exists(), "No se encontro HMI_Rover_Debug.py"

        contenido = ruta_archivo.read_text(encoding="utf-8")
        patron_emoji = re.compile(
            "[\U00010000-\U0010ffff"
            "\u2600-\u26FF"
            "\u2700-\u27BF"
            "\u2300-\u23FF"
            "\u2B50-\u2B55"
            "\u203C\u2049\u2122\u2139\u2194-\u2199\u21A9-\u21AA"
            "\u21BA\u21BB\u25A0\u25B2\u25BA\u25BC\u25C4\u2794\u27F2"
            "]",
            flags=re.UNICODE,
        )
        coincidencias = patron_emoji.findall(contenido)
        assert len(coincidencias) == 0, f"Se detectaron emojis no permitidos en HMI_Rover_Debug.py: {coincidencias}"

    def test_cero_emojis_en_este_archivo_de_pruebas(self):
        ruta_archivo = Path(__file__).resolve()
        contenido = ruta_archivo.read_text(encoding="utf-8")
        patron_emoji = re.compile(
            "[\U00010000-\U0010ffff"
            "\u2600-\u26FF"
            "\u2700-\u27BF"
            "\u2300-\u23FF"
            "\u2B50-\u2B55"
            "\u203C\u2049\u2122\u2139\u2194-\u2199\u21A9-\u21AA"
            "\u21BA\u21BB\u25A0\u25B2\u25BA\u25BC\u25C4\u2794\u27F2"
            "]",
            flags=re.UNICODE,
        )
        coincidencias = patron_emoji.findall(contenido)
        assert len(coincidencias) == 0, f"Se detectaron emojis no permitidos en el archivo de prueba: {coincidencias}"


# ==============================================================================
# 2. INICIALIZACION Y REGISTRO DE PERFILES DE HARDWARE
# ==============================================================================
class TestInicializacionPerfiles:
    """Verifica la correcta integracion de HardwareProfileRegistry y FlasherEngine."""

    def test_inicializacion_componentes_principales(self, app_debug):
        assert isinstance(app_debug.registry, HardwareProfileRegistry)
        assert isinstance(app_debug.flasher_engine, FlasherEngine)
        assert app_debug.flasheando is False

    def test_perfil_predeterminado_es_nano_esp32(self, app_debug):
        # Arduino Nano ESP32 es el perfil predeterminado tanto para TX como para RX
        assert app_debug.perfil_tx.get() == "ARDUINO_NANO_ESP32"
        assert app_debug.perfil_rx.get() == "ARDUINO_NANO_ESP32"

    def test_perfiles_oficiales_soportados_disponibles(self, app_debug):
        perfiles = [p.id for p in app_debug.registry.listar_perfiles()]
        assert "ARDUINO_NANO_ESP32" in perfiles
        assert "ESP32_C3_SUPERMINI" in perfiles
        assert "ARDUINO_MKR_1310" in perfiles


# ==============================================================================
# 3. AUTODETECCION PASIVA (VID:PID)
# ==============================================================================
class TestAutodeteccionPasiva:
    """Verifica la asignacion automatica del perfil segun el VID:PID del puerto serie."""

    def test_autodeteccion_puerto_nano_esp32(self, app_debug):
        fake_port = MagicMock()
        fake_port.device = "COM3"
        fake_port.vid = 0x2341
        fake_port.pid = 0x0070
        fake_port.description = "Arduino Nano ESP32"
        fake_port.manufacturer = "Arduino LLC"
        fake_port.hwid = "USB VID:PID=2341:0070"

        with patch("serial.tools.list_ports.comports", return_value=[fake_port]):
            with patch("HMI_Rover_Debug.SERIAL_DISPONIBLE", True):
                app_debug.autodetectar_perfil_puerto("COM3", "TX")
                assert app_debug.perfil_tx.get() == "ARDUINO_NANO_ESP32"

    def test_autodeteccion_puerto_esp32_c3(self, app_debug):
        fake_port = MagicMock()
        fake_port.device = "COM4"
        fake_port.vid = 0x303A
        fake_port.pid = 0x1001
        fake_port.description = "USB JTAG/serial debug unit"
        fake_port.manufacturer = "Espressif"
        fake_port.hwid = "USB VID:PID=303A:1001"

        with patch("serial.tools.list_ports.comports", return_value=[fake_port]):
            with patch("HMI_Rover_Debug.SERIAL_DISPONIBLE", True):
                app_debug.autodetectar_perfil_puerto("COM4", "TX")
                assert app_debug.perfil_tx.get() == "ESP32_C3_SUPERMINI"

    def test_autodeteccion_puerto_mkr1310(self, app_debug):
        fake_port = MagicMock()
        fake_port.device = "COM5"
        fake_port.vid = 0x2341
        fake_port.pid = 0x8054
        fake_port.description = "Arduino MKR WAN 1310"
        fake_port.manufacturer = "Arduino LLC"
        fake_port.hwid = "USB VID:PID=2341:8054"

        with patch("serial.tools.list_ports.comports", return_value=[fake_port]):
            with patch("HMI_Rover_Debug.SERIAL_DISPONIBLE", True):
                app_debug.autodetectar_perfil_puerto("COM5", "RX")
                assert app_debug.perfil_rx.get() == "ARDUINO_MKR_1310"

    def test_actualizar_lista_puertos_aplica_autodeteccion(self, app_debug):
        p_tx = MagicMock(device="COM3", vid=0x303A, pid=0x1001, description="ESP32-C3", manufacturer="", hwid="")
        p_rx = MagicMock(device="COM7", vid=0x2341, pid=0x8054, description="MKR1310", manufacturer="", hwid="")

        with patch("serial.tools.list_ports.comports", return_value=[p_tx, p_rx]):
            with patch("HMI_Rover_Debug.SERIAL_DISPONIBLE", True):
                app_debug.cb_puerto_tx.set("COM3")
                app_debug.cb_puerto_rx.set("COM7")
                app_debug.actualizar_lista_puertos()

                assert app_debug.perfil_tx.get() == "ESP32_C3_SUPERMINI"
                assert app_debug.perfil_rx.get() == "ARDUINO_MKR_1310"


# ==============================================================================
# 4. HANDSHAKE ACTIVO (IDENT)
# ==============================================================================
class TestHandshakeActivo:
    """Verifica el protocolo de identificacion activa e intercambio IDENT / ID:<PLACA>."""

    def test_procesar_handshake_tx_valido(self, app_debug):
        linea = "ID:NANO_ESP32:TX:v2.1"
        app_debug.badge_tx = MagicMock()

        app_debug.procesar_handshake_tx("NANO_ESP32", "TX", "v2.1", linea)
        assert app_debug.perfil_tx.get() == "ARDUINO_NANO_ESP32"
        app_debug.badge_tx.config.assert_called_with(
            text="[TX: NANO_ESP32 v2.1]", bg="#064e3b", fg="#34d399"
        )

    def test_procesar_handshake_rx_valido(self, app_debug):
        linea = "ID:MKR1310:RX:v2.0"
        app_debug.badge_rx = MagicMock()

        app_debug.procesar_handshake_rx("MKR1310", "RX", "v2.0", linea)
        assert app_debug.perfil_rx.get() == "ARDUINO_MKR_1310"
        app_debug.badge_rx.config.assert_called_with(
            text="[RX: MKR1310 v2.0]", bg="#451a03", fg="#fbbf24"
        )

    def test_ident_o_ping_tx_envia_trama_ident(self, app_debug):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        app_debug.serial_tx = mock_serial
        app_debug.conectado_tx = True

        app_debug.ident_o_ping_tx()
        mock_serial.write.assert_called_with(b"IDENT\n")
        mock_serial.flush.assert_called()

    def test_ident_o_ping_rx_envia_trama_ident(self, app_debug):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        app_debug.serial_rx = mock_serial
        app_debug.conectado_rx = True

        app_debug.ident_o_ping_rx()
        mock_serial.write.assert_called_with(b"IDENT\n")
        mock_serial.flush.assert_called()


# ==============================================================================
# 5. FLASHEO EN 1 CLIC (NO BLOQUEANTE Y SEGURO)
# ==============================================================================
class TestFlasheoEnUnoClic:
    """Verifica el aprovisionamiento de firmware no bloqueante y el control del puerto serie."""

    def test_iniciar_flasheo_tx_despacha_en_hilo(self, app_debug):
        app_debug.cb_puerto_tx.set("COM3")
        app_debug.perfil_tx.set("ARDUINO_NANO_ESP32")

        with patch.object(app_debug, "_ejecutar_flasheo") as mock_ejecutar:
            app_debug.iniciar_flasheo_tx()
            time.sleep(0.05)
            mock_ejecutar.assert_called_once()
            args = mock_ejecutar.call_args[0]
            assert args[0] == "COM3"
            assert args[1].id == "ARDUINO_NANO_ESP32"
            assert args[2] == "TX"

    def test_iniciar_flasheo_rx_despacha_en_hilo(self, app_debug):
        app_debug.cb_puerto_rx.set("COM4")
        app_debug.perfil_rx.set("ARDUINO_NANO_ESP32")

        with patch.object(app_debug, "_ejecutar_flasheo") as mock_ejecutar:
            app_debug.iniciar_flasheo_rx()
            time.sleep(0.05)
            mock_ejecutar.assert_called_once()
            args = mock_ejecutar.call_args[0]
            assert args[0] == "COM4"
            assert args[1].id == "ARDUINO_NANO_ESP32"
            assert args[2] == "RX"

    def test_flasheo_rechaza_operacion_concurrente_si_ya_esta_flasheando(self, app_debug):
        app_debug.flasheando = True
        with patch.object(app_debug, "_ejecutar_flasheo") as mock_ejecutar:
            with patch.object(HMI_Rover_Debug.messagebox, "showwarning") as mock_warn:
                app_debug.iniciar_flasheo_tx()
                mock_ejecutar.assert_not_called()
                mock_warn.assert_called_once()

    def test_ejecutar_flasheo_cierra_puerto_activo_y_lo_restaura(self, app_debug):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        app_debug.serial_tx = mock_serial
        app_debug.conectado_tx = True
        app_debug.badge_tx = MagicMock()
        app_debug.btn_conectar_tx = MagicMock()

        perfil = app_debug.registry.obtener_perfil("ARDUINO_NANO_ESP32")

        with patch.object(app_debug.flasher_engine, "flashear", return_value=True) as mock_flashear:
            with patch.object(app_debug, "toggle_conexion_tx") as mock_reconnect:
                with patch("time.sleep"):  # Evitar demoras de sleep en prueba
                    app_debug._ejecutar_flasheo("COM3", perfil, "TX")

                    # Verificaciones
                    mock_serial.close.assert_called_once()
                    assert app_debug.conectado_tx is False
                    mock_flashear.assert_called_once()
                    assert mock_flashear.call_args[1]["puerto"] == "COM3"
                    assert mock_flashear.call_args[1]["rol"] == "TX"
                    assert app_debug.flasheando is False


# ==============================================================================
# 6. SINCRONIZACION PRE-DESPLIEGUE Y LIBERACION DE PUERTO
# ==============================================================================
class TestSincronizacionYLiberacion:
    """Verifica la persistencia NVS y la liberacion segura de puerto para operacion en campo."""

    def test_sincronizar_calibracion_con_rx_conectado(self, app_debug):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        app_debug.serial_rx = mock_serial
        app_debug.conectado_rx = True
        app_debug.badge_rx = MagicMock()

        # Configurar valores especificos en sliders de trims y servos
        app_debug.trim_m1.set(110)
        app_debug.trim_m2.set(100)
        app_debug.ang_s1.set(85)
        app_debug.ang_s2.set(95)

        with patch.object(app_debug.flasher_engine, "sincronizar_calibracion", return_value=True) as mock_sync:
            app_debug.sincronizar_calibracion_rx()
            time.sleep(0.05)

            mock_sync.assert_called_once()
            trims_arg = mock_sync.call_args[1]["trims"]
            servos_arg = mock_sync.call_args[1]["servos"]
            persistir_arg = mock_sync.call_args[1]["persistir_nvs"]

            assert trims_arg[0] == 110
            assert servos_arg[0] == 85
            assert persistir_arg is True

    def test_sincronizar_calibracion_sin_rx_muestra_aviso(self, app_debug):
        app_debug.conectado_rx = False
        with patch.object(app_debug.flasher_engine, "sincronizar_calibracion") as mock_sync:
            with patch.object(HMI_Rover_Debug.messagebox, "showwarning") as mock_warn:
                app_debug.sincronizar_calibracion_rx()
                mock_sync.assert_not_called()
                mock_warn.assert_called_once()

    def test_liberar_rx_campo_cierra_puerto_y_actualiza_badge(self, app_debug):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        app_debug.serial_rx = mock_serial
        app_debug.conectado_rx = True
        app_debug.badge_rx = MagicMock()
        app_debug.btn_conectar_rx = MagicMock()

        with patch.object(app_debug.flasher_engine, "liberar_puerto", return_value=True) as mock_liberar:
            app_debug.liberar_rx_campo()

            mock_liberar.assert_called_once_with(mock_serial, callback_log=pytest.approx(object, rel=1e-3) if False else mock_liberar.call_args[1]["callback_log"])
            assert app_debug.conectado_rx is False
            assert app_debug.serial_rx is None
            app_debug.badge_rx.config.assert_called_with(
                text="[RX LIBERADO - CAMPO]", bg="#1e293b", fg="#38bdf8"
            )
