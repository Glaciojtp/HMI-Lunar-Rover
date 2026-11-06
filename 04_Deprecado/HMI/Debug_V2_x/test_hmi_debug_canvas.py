#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas Unitarias para la actualizacion grafica y telemetria de HMI_Rover_Debug.py.
Parte de la suite de verificacion tecnica del Rover Lunar V2.0.

Valida:
 1. Ausencia estricta de emojis en HMI_Rover_Debug.py y en esta suite.
 2. Mapeo y coloreado individual por rueda segun PWM en actualizar_grafico_tx.
 3. Mapeo y coloreado individual por rueda segun PWM en actualizar_grafico_rx.
 4. Orientacion paralela del vector de direccion en dibujar_rueda_en_canvas.
 5. Inversion de polaridad de motores en enviar_trama_actual.
 6. Procesamiento flexible de tramas TLM: y TLM_RX: (6 a 8 campos).
"""

from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

_dir_actual = Path(__file__).resolve().parent
if str(_dir_actual) not in sys.path:
    sys.path.insert(0, str(_dir_actual))

# Mocks para tkinter en entornos headless / sin display
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    mock_tk = MagicMock()
    mock_ttk = MagicMock()
    mock_mb = MagicMock()

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

from HMI_Rover_Debug import HMIRoverDebug


class TestReglaCeroEmojisDebug(unittest.TestCase):
    def test_cero_emojis_en_hmi_rover_debug(self):
        ruta_archivo = os.path.join(str(_dir_actual), "HMI_Rover_Debug.py")
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            contenido = f.read()

        emojis = []
        for char in contenido:
            cp = ord(char)
            if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or (0xFE00 <= cp <= 0xFE0F):
                emojis.append((char, hex(cp)))

        self.assertEqual(len(emojis), 0, f"Emojis detectados en HMI_Rover_Debug.py: {emojis}")

    def test_cero_emojis_en_test_debug_canvas(self):
        ruta_archivo = os.path.abspath(__file__)
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            contenido = f.read()

        emojis = []
        for char in contenido:
            cp = ord(char)
            if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or (0xFE00 <= cp <= 0xFE0F):
                emojis.append((char, hex(cp)))

        self.assertEqual(len(emojis), 0, f"Emojis detectados en archivo de prueba: {emojis}")


class TestGraficosYTelemetriaDebug(unittest.TestCase):
    def setUp(self):
        self.mock_root = MagicMock()

    def _crear_instancia_aislada(self):
        with patch.object(HMIRoverDebug, "crear_widgets"), \
             patch.object(HMIRoverDebug, "iniciar_hilos"), \
             patch.object(HMIRoverDebug, "bucle_periodico_ui"), \
             patch.object(HMIRoverDebug, "configurar_estilos"):
            app = HMIRoverDebug(self.mock_root)
            app.canvas_tx = MagicMock()
            app.canvas_rx = MagicMock()
            app.lbl_tx_valores = MagicMock()
            app.lbl_rx_valores = MagicMock()
            return app

    def test_actualizar_grafico_tx_coloreado_individual(self):
        app = self._crear_instancia_aislada()
        ruedas_registradas = []

        def mock_dibujar_rueda(c, x, y, ang, color, texto, pwm=0):
            ruedas_registradas.append((texto, pwm, color))

        app.dibujar_rueda_en_canvas = mock_dibujar_rueda
        app.comando_actual = "PIVOT_IZQ"

        # Mockear calcular_pwms_tx para simular giro sobre el eje:
        # izquierda reversa (-150), derecha avance (+150)
        with patch.object(app, "calcular_pwms_tx", return_value=[-150, -150, -150, 150, 150, 150]):
            app.actualizar_grafico_tx()

        dict_ruedas = {label: (pwm, color) for label, pwm, color in ruedas_registradas}

        # Las 3 ruedas izquierdas deben ser negativas y de color naranja
        self.assertEqual(dict_ruedas["M1"][0], -150)
        self.assertEqual(dict_ruedas["M2"][0], -150)
        self.assertEqual(dict_ruedas["M3"][0], -150)
        self.assertEqual(dict_ruedas["M1"][1], "#ff9f1c")
        self.assertEqual(dict_ruedas["M2"][1], "#ff9f1c")
        self.assertEqual(dict_ruedas["M3"][1], "#ff9f1c")

        # Las 3 ruedas derechas deben ser positivas y de color verde
        self.assertEqual(dict_ruedas["M4"][0], 150)
        self.assertEqual(dict_ruedas["M5"][0], 150)
        self.assertEqual(dict_ruedas["M6"][0], 150)
        self.assertEqual(dict_ruedas["M4"][1], "#38b000")
        self.assertEqual(dict_ruedas["M5"][1], "#38b000")
        self.assertEqual(dict_ruedas["M6"][1], "#38b000")

    def test_actualizar_grafico_rx_coloreado_individual(self):
        app = self._crear_instancia_aislada()
        ruedas_rx_registradas = []

        def mock_dibujar_rueda(c, x, y, ang, color, texto, pwm=0):
            ruedas_rx_registradas.append((texto, pwm, color))

        app.dibujar_rueda_en_canvas = mock_dibujar_rueda
        app.snapshot_rx['izq'] = 140
        app.snapshot_rx['der'] = -140

        app.actualizar_grafico_rx()

        dict_ruedas = {label: (pwm, color) for label, pwm, color in ruedas_rx_registradas}
        # Izquierda positiva (verde), derecha negativa (naranja)
        self.assertEqual(dict_ruedas["M1"][1], "#38b000")
        self.assertEqual(dict_ruedas["M2"][1], "#38b000")
        self.assertEqual(dict_ruedas["M3"][1], "#38b000")
        self.assertEqual(dict_ruedas["M4"][1], "#ff9f1c")
        self.assertEqual(dict_ruedas["M5"][1], "#ff9f1c")
        self.assertEqual(dict_ruedas["M6"][1], "#ff9f1c")

    def test_dibujar_rueda_en_canvas_flecha_alineada(self):
        app = self._crear_instancia_aislada()
        mock_canvas = MagicMock()

        # Angulo 45 deg, pwm 150 -> avance orientado hacia arriba-derecha
        app.dibujar_rueda_en_canvas(mock_canvas, 87, 87, 45, "#38b000", "M1", 150)

        mock_canvas.create_line.assert_called_once()
        args, kwargs = mock_canvas.create_line.call_args
        x_ini, y_ini, x_fin, y_fin = args[0], args[1], args[2], args[3]

        dx = x_fin - x_ini
        dy = y_fin - y_ini
        # dx debe ser positivo (derecha) y dy negativo (arriba)
        self.assertGreater(dx, 0, "El vector x de la flecha debe apuntar hacia la derecha")
        self.assertLess(dy, 0, "El vector y de la flecha debe apuntar hacia arriba")

    def test_inversion_polaridad_en_enviar_trama_actual(self):
        app = self._crear_instancia_aislada()
        app.master_izq.set(150)
        app.master_der.set(150)
        app.ang_s1.set(90)
        app.ang_s2.set(90)
        app.ang_s3.set(90)
        app.ang_s4.set(90)
        app.invertir_dir_izq.set(True)
        app.invertir_dir_der.set(False)
        app.comando_actual = "W"

        with patch.object(app, "actualizar_grafico_tx") as mock_graf:
            app.enviar_trama_actual()
            mock_graf.assert_called_once()

        self.assertEqual(app.snapshot_tx['izq'], -150)
        self.assertEqual(app.snapshot_tx['der'], 150)

    def test_procesar_linea_mkr_soporta_tlm_y_tlm_rx(self):
        app = self._crear_instancia_aislada()
        app.validar_datos_cruzados = MagicMock()

        # Telemetria estandar TLM (8 campos)
        app.procesar_linea_mkr("TLM:120,130,85,95,90,90,45,2")
        self.assertEqual(app.snapshot_rx['izq'], 120)
        self.assertEqual(app.snapshot_rx['der'], 130)
        self.assertEqual(app.snapshot_rx['s1'], 85)
        self.assertEqual(app.snapshot_rx['s2'], 95)
        self.assertEqual(app.snapshot_rx['dt'], 45)

        # Telemetria alternativa TLM_RX (6 campos)
        app.procesar_linea_mkr("TLM_RX:-100,100,70,110,60,120")
        self.assertEqual(app.snapshot_rx['izq'], -100)
        self.assertEqual(app.snapshot_rx['der'], 100)
        self.assertEqual(app.snapshot_rx['s1'], 70)
        self.assertEqual(app.snapshot_rx['s2'], 110)


if __name__ == "__main__":
    unittest.main()
