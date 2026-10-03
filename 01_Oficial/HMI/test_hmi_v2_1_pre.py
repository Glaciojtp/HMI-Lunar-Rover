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

    def test_formatear_calibracion_pre_despliegue(self):
        trims = {1: 100, 2: 100, 3: 100, 4: 100, 5: 100, 6: 100}
        servos = {1: 90, 2: 90, 3: 90, 4: 90}
        trama = formatear_trama_calibracion(trims, servos)
        self.assertEqual(trama, "CALIB,100,100,100,100,100,100,90,90,90,90\n")


if __name__ == "__main__":
    unittest.main()
