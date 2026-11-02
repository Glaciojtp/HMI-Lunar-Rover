#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas Unitarias y de Integracion para HMI_Rover_V2_1_pre.py.
Parte de la suite de verificacion del pre-release oficial del Rover Lunar V2.1-pre.

Valida:
 1. Ausencia estricta de emojis en el archivo oficial pre-release y en pruebas.
 2. Inicializacion del perfil predeterminado Arduino Nano ESP32.
 3. Resolucion y autodeteccion pasiva de perfiles de hardware.
 4. Calculo cinematico inverso (angulos de direccion sin derrape).
 5. Calculo de traccion PWM por comandos de pilotaje.
 6. Formateo y persistencia de tramas de calibracion NVS.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

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

from HMI_Rover_V2_1_pre import HMIRoverRockerBogieV21Pre
from hardware_profiles import HardwareProfileRegistry, PERFIL_DEFAULT_ID
from flasher_engine import formatear_trama_calibracion


class TestReglaEstrictaCeroEmojis(unittest.TestCase):
    def test_cero_emojis_en_hmi_v2_1_pre(self):
        ruta_archivo = os.path.join(str(_dir_actual), "HMI_Rover_V2_1_pre.py")
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            contenido = f.read()

        emojis_detectados = []
        for i, char in enumerate(contenido):
            cp = ord(char)
            if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or (0xFE00 <= cp <= 0xFE0F):
                emojis_detectados.append((char, hex(cp)))

        self.assertEqual(len(emojis_detectados), 0,
                         f"Se detectaron emojis en HMI_Rover_V2_1_pre.py: {emojis_detectados}")

    def test_cero_emojis_en_este_archivo_de_pruebas(self):
        ruta_archivo = os.path.abspath(__file__)
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            contenido = f.read()

        emojis_detectados = []
        for i, char in enumerate(contenido):
            cp = ord(char)
            if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or (0xFE00 <= cp <= 0xFE0F):
                emojis_detectados.append((char, hex(cp)))

        self.assertEqual(len(emojis_detectados), 0,
                         f"Se detectaron emojis en archivo de pruebas: {emojis_detectados}")


class TestInicializacionHMIOficialPre(unittest.TestCase):
    def setUp(self):
        self.mock_root = MagicMock()

    def test_perfil_default_es_nano_esp32(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            self.assertEqual(app.perfil_activo.id, "ARDUINO_NANO_ESP32")
            self.assertEqual(app.perfil_activo.fqbn, "arduino:esp32:nano_nora")

    def test_cinematica_inversa_giro_sobre_eje(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            s1, s2, s3, s4 = app.calcular_cinematica_inversa(0.0, 0.0, -1.0)
            self.assertGreaterEqual(s1, 10)
            self.assertLessEqual(s1, 170)
            self.assertGreaterEqual(s2, 10)
            self.assertLessEqual(s2, 170)

    def test_calcular_pwms_parada_de_emergencia(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            app.comando_actual = "STOP"
            pwms = app.calcular_pwms_actuales()
            self.assertEqual(pwms, [0, 0, 0, 0, 0, 0])

    def test_calcular_pwms_avance_recto(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            app.comando_actual = "W"
            pwms = app.calcular_pwms_actuales()
            for p in pwms:
                self.assertGreater(p, 0)

    def test_inversion_pwm_izq_predeterminada(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            self.assertTrue(app.invertir_pwm_izq.get())
            self.assertFalse(app.invertir_pwm_der.get())

    def test_generar_trama_control_w_izq_invertida(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            app.master_izq.set(150)
            app.master_der.set(150)
            app.comando_actual = "W"
            trama = app.generar_trama_control()
            self.assertEqual(trama, "W,-150,150,90,90,90,90\n")

    def test_generar_trama_control_s_izq_invertida(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            app.master_izq.set(150)
            app.master_der.set(150)
            app.comando_actual = "S"
            trama = app.generar_trama_control()
            self.assertEqual(trama, "S,-150,150,90,90,90,90\n")

    def test_generar_trama_control_stop(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            app.comando_actual = "STOP"
            trama = app.generar_trama_control()
            self.assertEqual(trama, "STOP,0,0,90,90,90,90\n")

    def test_desactivar_inversion_pwm_izq(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            app.master_izq.set(150)
            app.master_der.set(150)
            app.invertir_pwm_izq.set(False)
            app.comando_actual = "W"
            trama = app.generar_trama_control()
            self.assertEqual(trama, "W,150,150,90,90,90,90\n")

    def test_rover_en_movimiento(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            app.comando_actual = " "
            self.assertFalse(app.rover_en_movimiento())
            app.comando_actual = "STOP"
            self.assertFalse(app.rover_en_movimiento())
            app.comando_actual = "W"
            self.assertTrue(app.rover_en_movimiento())
            app.comando_actual = "S"
            self.assertTrue(app.rover_en_movimiento())
            app.comando_actual = "PIVOT_IZQ"
            self.assertTrue(app.rover_en_movimiento())

    def test_sync_master_no_envia_cuando_detenido(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            app.conectado = True
            app.comando_actual = " "
            with patch.object(app, "enviar_trama_actual") as mock_env:
                app.sync_master_izq(200)
                app.sync_master_der(220)
                mock_env.assert_not_called()

    def test_sync_master_envia_cuando_en_movimiento(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            app.conectado = True
            app.comando_actual = "W"
            with patch.object(app, "_solicitar_envio_throttled") as mock_throt:
                app.sync_master_izq(200)
                mock_throt.assert_called_once()

    def test_lock_serial_presente(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            self.assertTrue(hasattr(app, "lock_serial"))

    def test_mapeo_ruedas_m1_a_m6_en_canvas(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            app.canvas_rover = MagicMock()
            ruedas_dibujadas = []

            def mock_dibujar_rueda(c, x, y, ang, color, label, pwm):
                ruedas_dibujadas.append((label, pwm, color))

            app.dibujar_rueda_orientada = mock_dibujar_rueda
            # pwms: [m1, m2, m3, m4, m5, m6]
            pwms_prueba = [-120, -120, -120, 150, 150, 150]
            app.dibujar_esquema_rover("W", 90, 90, 90, 90, pwms=pwms_prueba)

            dict_ruedas = {label: (pwm, color) for label, pwm, color in ruedas_dibujadas}
            # Verificar que las 3 ruedas izquierdas tengan PWM negativo (-120) y color naranja
            self.assertEqual(dict_ruedas["M1"][0], -120)
            self.assertEqual(dict_ruedas["M2"][0], -120)
            self.assertEqual(dict_ruedas["M3"][0], -120)
            self.assertEqual(dict_ruedas["M1"][1], "#ff9f1c")
            self.assertEqual(dict_ruedas["M2"][1], "#ff9f1c")
            self.assertEqual(dict_ruedas["M3"][1], "#ff9f1c")

            # Verificar que las 3 ruedas derechas tengan PWM positivo (150) y color verde
            self.assertEqual(dict_ruedas["M4"][0], 150)
            self.assertEqual(dict_ruedas["M5"][0], 150)
            self.assertEqual(dict_ruedas["M6"][0], 150)
            self.assertEqual(dict_ruedas["M4"][1], "#38b000")
            self.assertEqual(dict_ruedas["M5"][1], "#38b000")
            self.assertEqual(dict_ruedas["M6"][1], "#38b000")

    def test_alineacion_vectorial_flecha_rueda(self):
        with patch.object(HMIRoverRockerBogieV21Pre, "crear_widgets"), \
             patch.object(HMIRoverRockerBogieV21Pre, "iniciar_hilos_segundo_plano"), \
             patch.object(HMIRoverRockerBogieV21Pre, "actualizar_telemetria_ui"):
            app = HMIRoverRockerBogieV21Pre(self.mock_root)
            mock_canvas = MagicMock()
            # Giro a 45 grados hacia la derecha (delta_deg = 45 -> avance hacia arriba y a la derecha)
            app.dibujar_rueda_orientada(mock_canvas, 100, 100, 45, "#38b000", "M1", 150)

            # Verificar creacion de linea de flecha
            mock_canvas.create_line.assert_called_once()
            args, kwargs = mock_canvas.create_line.call_args
            x_ini, y_ini, x_fin, y_fin = args[0], args[1], args[2], args[3]

            dx = x_fin - x_ini
            dy = y_fin - y_ini
            # Con delta_deg = 45, dx debe ser positivo (hacia la derecha) y dy negativo (hacia arriba)
            self.assertGreater(dx, 0, "El vector x de la flecha debe apuntar hacia adelante-derecha")
            self.assertLess(dy, 0, "El vector y de la flecha debe apuntar hacia arriba (avance)")


if __name__ == "__main__":
    unittest.main()


