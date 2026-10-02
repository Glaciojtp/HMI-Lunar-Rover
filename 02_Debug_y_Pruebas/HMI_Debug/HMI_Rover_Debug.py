#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================================
 HMI ROVER LUNAR V2.0 - DEBUG Y TELEMETRIA AVANZADA CON DOBLE MONITOR TX / RX
=====================================================================================
 Caracteristicas Principales:
  1. Soporte para Doble Puerto COM simultaneo:
     - Puerto TX: Transmisor conectado a la PC (Arduino Nano ESP32 / ESP32-C3)
     - Puerto RX: Receptor conectado a la PC para banco de pruebas (Nano ESP32 / MKR 1310)
  2. Motor de Validacion Cruzada en Tiempo Real:
     - Compara campo por campo lo que se envia al TX vs lo que confirma el RX.
     - Calculo de latencia de enlace de radio (ms) y deteccion de discrepancias.
  3. Doble Grafico 2D del Rocker-Bogie (Lado a Lado):
     - Grafico 1: "[TX] TRANSMITIDO (Comando GUI)"
     - Grafico 2: "[RX] RECIBIDO (Telemetria Real RX)"
  4. Consola de Depuracion con 5 canales de color (TX, MCU, RX, Validacion, Alertas).
  5. Aprovisionamiento y Flasheo en 1 Clic (FlasherEngine) y Sincronizacion Pre-Despliegue.
=====================================================================================
"""

import sys
import os
import time
import math
import threading
from pathlib import Path

# Asegurar importacion de modulos locales de HMI_Debug
_dir_actual = os.path.dirname(os.path.abspath(__file__))
if _dir_actual not in sys.path:
    sys.path.insert(0, _dir_actual)

from hardware_profiles import (
    HardwareProfileRegistry,
    PerfilHardware,
    PERFILES_OFICIALES,
    PERFIL_DEFAULT_ID,
    parsear_handshake,
)
from flasher_engine import (
    FlasherEngine,
    sanitizar_puerto,
    formatear_trama_calibracion,
)

try:
    import serial
    import serial.tools.list_ports
    SERIAL_DISPONIBLE = True
except ImportError:
    SERIAL_DISPONIBLE = False

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    TKINTER_DISPONIBLE = True
except ImportError:
    tk = None
    ttk = None
    messagebox = None
    filedialog = None
    TKINTER_DISPONIBLE = False


class HMIRoverDebug:
    def __init__(self, root):
        self.root = root
        if hasattr(self.root, "title"):
            self.root.title("HMI ROVER LUNAR V2.0 - DEPURACION INTEGRAL Y DOBLE TELEMETRIA (TX / RX)")
        if hasattr(self.root, "geometry"):
            self.root.geometry("1360x900")
        if hasattr(self.root, "minsize"):
            self.root.minsize(1150, 800)
        if hasattr(self.root, "configure"):
            self.root.configure(bg="#0c0e17")

        # Registro de perfiles de hardware y motor de flasheo
        self.registry = HardwareProfileRegistry()
        self.flasher_engine = FlasherEngine(repo_root=Path(_dir_actual).resolve().parents[1])
        self.flasheando = False

        # Perfiles seleccionados por defecto (Nano ESP32 tanto para TX como para RX)
        self.perfil_tx = tk.StringVar(value=PERFIL_DEFAULT_ID) if tk else None
        self.perfil_rx = tk.StringVar(value=PERFIL_DEFAULT_ID) if tk else None

        # Conexion Serial Puerto 1 (Transmisor TX)
        self.serial_tx = None
        self.conectado_tx = False
        self.hilo_tx = None

        # Conexion Serial Puerto 2 (Receptor RX)
        self.serial_rx = None
        self.conectado_rx = False
        self.hilo_rx = None

        self.ejecutando = True
        self.txt_consola = None
        self._log_buffer = []

        # Metricas de transmision y recepcion
        self.contador_tx = 0
        self.contador_rx_mkr = 0
        self.contador_matches = 0
        self.contador_mismatches = 0
        self.tasa_tx_hz = 0
        self.ultimo_tiempo_tasa = time.time()
        self.ultima_latencia_ms = 0.0

        # Opciones visuales y de consola
        self.mostrar_hex = tk.BooleanVar(value=True) if tk else None
        self.mostrar_raw_esp = tk.BooleanVar(value=True) if tk else None
        self.mostrar_raw_mkr = tk.BooleanVar(value=True) if tk else None
        self.auto_scroll = tk.BooleanVar(value=True) if tk else None
        self.tx_continuo = tk.BooleanVar(value=True) if tk else None

        # Estado dinamico de control (TX)
        self.comando_actual = "STOP"
        self.modo_conduccion = tk.StringVar(value="ACKERMANN") if tk else None
        self.teclas_presionadas = {'w': False, 'a': False, 's': False, 'd': False, 'q': False, 'e': False, 'space': False}

        # Variables de Trim porcentual (Ratio 0% a 150%, 100% = 1.0x directo de Master)
        self.trim_m1 = tk.IntVar(value=100) if tk else None
        self.trim_m2 = tk.IntVar(value=100) if tk else None
        self.trim_m3 = tk.IntVar(value=100) if tk else None
        self.trim_m4 = tk.IntVar(value=100) if tk else None
        self.trim_m5 = tk.IntVar(value=100) if tk else None
        self.trim_m6 = tk.IntVar(value=100) if tk else None
        self.lbl_trims = {}
        self.master_izq = tk.IntVar(value=150) if tk else None
        self.master_der = tk.IntVar(value=150) if tk else None

        # Sliders de Servos TX (10 deg - 170 deg / 0 deg - 360 deg)
        self.ang_s1 = tk.IntVar(value=90) if tk else None
        self.ang_s2 = tk.IntVar(value=90) if tk else None
        self.ang_s3 = tk.IntVar(value=90) if tk else None
        self.ang_s4 = tk.IntVar(value=90) if tk else None
        self.invertir_servos = tk.BooleanVar(value=False) if tk else None
        self.servos_360 = tk.BooleanVar(value=False) if tk else None
        self.sliders_servos = {}

        # Conexion Serial Joystick Fisico (Arduino Nano)
        self.serial_joy = None
        self.conectado_joy = False
        self.hilo_joy = None
        self.joy_data = {
            's1_x': 0, 's1_y': 0,
            's2_x': 0, 's2_y': 0,
            'pot': 150,
            'sw1': 0, 'sw2': 0, 'estop': 0, 's360': 0, 'q': 0, 'e': 0
        }
        self.ultimo_joy_sw1 = 0
        self.ultimo_joy_estop = 0
        self.ultimo_joy_360 = 0

        # Estado Snapshot TX (ultimo enviado)
        self.snapshot_tx = {
            'cmd': 'STOP', 'izq': 0, 'der': 0,
            's1': 90, 's2': 90, 's3': 90, 's4': 90,
            't': time.time()
        }

        # Estado Snapshot RX (ultimo confirmado por el receptor)
        self.snapshot_rx = {
            'izq': 0, 'der': 0,
            's1': 90, 's2': 90, 's3': 90, 's4': 90,
            'dt': 0, 'cola': 0,
            't': time.time(),
            'activo': False
        }

        # Construir Interfaz Grafica
        if tk:
            self.configurar_estilos()
            self.crear_widgets()
            self.actualizar_labels_trim()
            self.actualizar_grafico_tx()
            self.actualizar_grafico_rx()

            # Enlazar eventos de teclado
            self.root.bind("<KeyPress>", self.evento_key_press)
            self.root.bind("<KeyRelease>", self.evento_key_release)

            # Iniciar hilos y reloj de telemetria
            self.iniciar_hilos()
            self.bucle_periodico_ui()

    def configurar_estilos(self):
        estilo = ttk.Style()
        estilo.theme_use('clam')
        estilo.configure("Card.TFrame", background="#151824", relief="flat")
        estilo.configure("CardDark.TFrame", background="#11131c", relief="flat")
        estilo.configure("Dark.TFrame", background="#0c0e17")
        estilo.configure("Header.TLabel", background="#151824", foreground="#00f5d4", font=("Segoe UI", 10, "bold"))
        estilo.configure("SubHeader.TLabel", background="#151824", foreground="#cbd5e1", font=("Segoe UI", 9, "bold"))
        estilo.configure("Value.TLabel", background="#151824", foreground="#38b000", font=("Consolas", 10, "bold"))
        estilo.configure("ValueWarn.TLabel", background="#151824", foreground="#ffb703", font=("Consolas", 10, "bold"))
        estilo.configure("ValueErr.TLabel", background="#151824", foreground="#f87171", font=("Consolas", 10, "bold"))

    def crear_widgets(self):
        # =========================================================================
        # 1. BARRA SUPERIOR: DOBLE CONEXION SERIAL (TX & RX) Y APROVISIONAMIENTO
        # =========================================================================
        top_bar = ttk.Frame(self.root, style="Card.TFrame", padding=(12, 6))
        top_bar.pack(fill="x", padx=12, pady=(8, 4))

        # --- FILA 1: PUERTOS, PERFILES Y CONEXIONES ---
        row_conn = ttk.Frame(top_bar, style="Card.TFrame")
        row_conn.pack(fill="x", pady=(0, 4))

        # --- SECCION TX ---
        frm_tx_conn = ttk.Frame(row_conn, style="Card.TFrame")
        frm_tx_conn.pack(side="left", padx=(0, 8))

        tk.Label(frm_tx_conn, text="TX:", bg="#151824", fg="#00f5d4", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 3))
        self.cb_puerto_tx = ttk.Combobox(frm_tx_conn, width=8, state="readonly")
        self.cb_puerto_tx.pack(side="left", padx=2)
        self.cb_puerto_tx.bind("<<ComboboxSelected>>", self.al_seleccionar_puerto_tx)

        perfiles_ids = [p.id for p in self.registry.listar_perfiles()]
        self.cb_perfil_tx = ttk.Combobox(frm_tx_conn, width=15, textvariable=self.perfil_tx,
                                         values=perfiles_ids, state="readonly")
        self.cb_perfil_tx.pack(side="left", padx=2)

        self.btn_conectar_tx = tk.Button(frm_tx_conn, text="Conectar TX", bg="#00f5d4", fg="#0c0e17",
                                         font=("Segoe UI", 8, "bold"), command=self.toggle_conexion_tx, relief="flat", padx=4)
        self.btn_conectar_tx.pack(side="left", padx=2)

        self.btn_ping_tx = tk.Button(frm_tx_conn, text="IDENT / Ping", bg="#0f766e", fg="#ffffff",
                                     font=("Segoe UI", 8, "bold"), command=self.ident_o_ping_tx, relief="flat", padx=4)
        self.btn_ping_tx.pack(side="left", padx=2)

        self.btn_reset_tx = tk.Button(frm_tx_conn, text="Reset HW", bg="#334155", fg="#fca5a5",
                                      font=("Segoe UI", 8, "bold"), command=self.reset_hw_tx, relief="flat", padx=4)
        self.btn_reset_tx.pack(side="left", padx=2)

        self.badge_tx = tk.Label(frm_tx_conn, text="[TX OFF]", bg="#2a2e3f", fg="#f87171", font=("Segoe UI", 8, "bold"), padx=5)
        self.badge_tx.pack(side="left", padx=2)

        # Separador vertical
        ttk.Separator(row_conn, orient="vertical").pack(side="left", fill="y", padx=6)

        # --- SECCION RX ---
        frm_rx_conn = ttk.Frame(row_conn, style="Card.TFrame")
        frm_rx_conn.pack(side="left", padx=(0, 8))

        tk.Label(frm_rx_conn, text="RX:", bg="#151824", fg="#fbbf24", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 3))
        self.cb_puerto_rx = ttk.Combobox(frm_rx_conn, width=8, state="readonly")
        self.cb_puerto_rx.pack(side="left", padx=2)
        self.cb_puerto_rx.bind("<<ComboboxSelected>>", self.al_seleccionar_puerto_rx)

        self.cb_perfil_rx = ttk.Combobox(frm_rx_conn, width=15, textvariable=self.perfil_rx,
                                         values=perfiles_ids, state="readonly")
        self.cb_perfil_rx.pack(side="left", padx=2)

        self.btn_conectar_rx = tk.Button(frm_rx_conn, text="Conectar RX", bg="#fbbf24", fg="#0c0e17",
                                         font=("Segoe UI", 8, "bold"), command=self.toggle_conexion_rx, relief="flat", padx=4)
        self.btn_conectar_rx.pack(side="left", padx=2)

        self.btn_ping_rx = tk.Button(frm_rx_conn, text="IDENT / Ping", bg="#854d0e", fg="#ffffff",
                                     font=("Segoe UI", 8, "bold"), command=self.ident_o_ping_rx, relief="flat", padx=4)
        self.btn_ping_rx.pack(side="left", padx=2)

        self.badge_rx = tk.Label(frm_rx_conn, text="[RX OFF]", bg="#2a2e3f", fg="#f87171", font=("Segoe UI", 8, "bold"), padx=5)
        self.badge_rx.pack(side="left", padx=2)

        btn_refrescar = tk.Button(row_conn, text="Refrescar Puertos", bg="#334155", fg="#ffffff", font=("Segoe UI", 8, "bold"),
                                  command=self.actualizar_lista_puertos, relief="flat", padx=5)
        btn_refrescar.pack(side="left", padx=3)

        # Insignia de Validacion Cruzada TX <-> RX a la derecha
        self.badge_validacion = tk.Label(row_conn, text="[VALIDACION: EN ESPERA]", bg="#2a2e3f", fg="#94a3b8",
                                         font=("Segoe UI", 9, "bold"), padx=8, pady=2)
        self.badge_validacion.pack(side="right", padx=3)

        # Modo de Conduccion
        self.cb_modo = ttk.Combobox(row_conn, width=11, textvariable=self.modo_conduccion,
                                    values=["ACKERMANN", "CRAB", "MANUAL"], state="readonly")
        self.cb_modo.pack(side="right", padx=2)
        self.cb_modo.bind("<<ComboboxSelected>>", self.cambiar_modo_conduccion)
        tk.Label(row_conn, text="Modo:", bg="#151824", fg="#cbd5e1", font=("Segoe UI", 9, "bold")).pack(side="right", padx=(6, 2))

        # --- FILA 2: APROVISIONAMIENTO Y DESPLIEGUE EN CAMPO ---
        row_flash = ttk.Frame(top_bar, style="Card.TFrame")
        row_flash.pack(fill="x", pady=(2, 0))

        tk.Label(row_flash, text="BANCO DE PRUEBAS & DESPLIEGUE:", bg="#151824", fg="#cbd5e1",
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))

        self.btn_subir_tx = tk.Button(row_flash, text="Subir TX", bg="#0f766e", fg="#ffffff",
                                      font=("Segoe UI", 8, "bold"), command=self.iniciar_flasheo_tx, relief="flat", padx=6)
        self.btn_subir_tx.pack(side="left", padx=3)

        self.btn_subir_rx = tk.Button(row_flash, text="Subir RX", bg="#854d0e", fg="#ffffff",
                                      font=("Segoe UI", 8, "bold"), command=self.iniciar_flasheo_rx, relief="flat", padx=6)
        self.btn_subir_rx.pack(side="left", padx=3)

        ttk.Separator(row_flash, orient="vertical").pack(side="left", fill="y", padx=6)

        self.btn_sync_calib = tk.Button(row_flash, text="Sincronizar Calibracion RX", bg="#1e3a8a", fg="#93c5fd",
                                        font=("Segoe UI", 8, "bold"), command=self.sincronizar_calibracion_rx, relief="flat", padx=6)
        self.btn_sync_calib.pack(side="left", padx=3)

        self.btn_liberar_rx = tk.Button(row_flash, text="Liberar RX (Campo)", bg="#334155", fg="#38bdf8",
                                        font=("Segoe UI", 8, "bold"), command=self.liberar_rx_campo, relief="flat", padx=6)
        self.btn_liberar_rx.pack(side="left", padx=3)

        # =========================================================================
        # 2. CUERPO PRINCIPAL: IZQUIERDA (CONTROLES), DERECHA (DOBLE ESQUEMA 2D)
        # =========================================================================
        main_content = ttk.Frame(self.root, style="Dark.TFrame")
        main_content.pack(fill="both", expand=True, padx=12, pady=4)

        col_izq = ttk.Frame(main_content, style="Dark.TFrame")
        col_izq.pack(side="left", fill="both", expand=True, padx=(0, 6))

        col_der = ttk.Frame(main_content, style="Dark.TFrame")
        col_der.pack(side="right", fill="both", expand=True, padx=(6, 0))

        # --- PANEL TRIMS DE MOTORES ---
        card_motores = ttk.Frame(col_izq, style="Card.TFrame", padding=8)
        card_motores.pack(fill="x", pady=(0, 6))

        frm_tit_m = ttk.Frame(card_motores, style="Card.TFrame")
        frm_tit_m.pack(fill="x", pady=(0, 2))
        ttk.Label(frm_tit_m, text="CALIBRACION & TRIMS (RATIO % DE MASTER)", style="Header.TLabel").pack(side="left")
        tk.Button(frm_tit_m, text="Reset (100%)", bg="#334155", fg="#00f5d4",
                  font=("Segoe UI", 7, "bold"), relief="flat", padx=5, pady=1, command=self.reset_trims).pack(side="right")

        grid_m = ttk.Frame(card_motores, style="Card.TFrame")
        grid_m.pack(fill="x")

        col_m_izq = ttk.Frame(grid_m, style="Card.TFrame")
        col_m_izq.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.crear_slider_trim(col_m_izq, 1, "M1 (Del. Izq)", self.trim_m1)
        self.crear_slider_trim(col_m_izq, 2, "M2 (Med. Izq)", self.trim_m2)
        self.crear_slider_trim(col_m_izq, 3, "M3 (Tras. Izq)", self.trim_m3)

        frm_mi = ttk.Frame(col_m_izq, style="Card.TFrame")
        frm_mi.pack(fill="x", pady=2)
        ttk.Label(frm_mi, text="Master Izq:", style="SubHeader.TLabel").pack(side="left")
        tk.Scale(frm_mi, from_=0, to=255, orient="horizontal", variable=self.master_izq,
                 bg="#151824", fg="#00f5d4", highlightthickness=0, command=self.sync_master_izq).pack(side="right", fill="x", expand=True)

        col_m_der = ttk.Frame(grid_m, style="Card.TFrame")
        col_m_der.pack(side="right", fill="both", expand=True, padx=(4, 0))
        self.crear_slider_trim(col_m_der, 4, "M4 (Del. Der)", self.trim_m4)
        self.crear_slider_trim(col_m_der, 5, "M5 (Med. Der)", self.trim_m5)
        self.crear_slider_trim(col_m_der, 6, "M6 (Tras. Der)", self.trim_m6)

        frm_md = ttk.Frame(col_m_der, style="Card.TFrame")
        frm_md.pack(fill="x", pady=2)
        ttk.Label(frm_md, text="Master Der:", style="SubHeader.TLabel").pack(side="left")
        tk.Scale(frm_md, from_=0, to=255, orient="horizontal", variable=self.master_der,
                 bg="#151824", fg="#00f5d4", highlightthickness=0, command=self.sync_master_der).pack(side="right", fill="x", expand=True)

        # --- PANEL SERVOS ---
        card_servos = ttk.Frame(col_izq, style="Card.TFrame", padding=8)
        card_servos.pack(fill="x", pady=(0, 6))

        self.lbl_header_servos = ttk.Label(card_servos, text="SERVOS DE DIRECCION (10 deg - 170 deg)", style="Header.TLabel")
        self.lbl_header_servos.pack(anchor="w", pady=(0, 2))
        grid_s = ttk.Frame(card_servos, style="Card.TFrame")
        grid_s.pack(fill="x")

        col_s_del = ttk.Frame(grid_s, style="Card.TFrame")
        col_s_del.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.crear_slider_servo(col_s_del, 1, "S1: Del. Izq", self.ang_s1)
        self.crear_slider_servo(col_s_del, 2, "S2: Del. Der", self.ang_s2)

        col_s_tras = ttk.Frame(grid_s, style="Card.TFrame")
        col_s_tras.pack(side="right", fill="both", expand=True, padx=(4, 0))
        self.crear_slider_servo(col_s_tras, 3, "S3: Tras. Izq", self.ang_s3)
        self.crear_slider_servo(col_s_tras, 4, "S4: Tras. Der", self.ang_s4)

        frm_s_btns = ttk.Frame(card_servos, style="Card.TFrame")
        frm_s_btns.pack(fill="x", pady=(4, 0))
        tk.Button(frm_s_btns, text="90 deg", bg="#334155", fg="#ffffff", font=("Segoe UI", 8, "bold"),
                  command=self.centrar_todos_los_servos, relief="flat", padx=6).pack(side="left", padx=2)
        tk.Button(frm_s_btns, text="Giro 360 deg", bg="#334155", fg="#00f5d4", font=("Segoe UI", 8, "bold"),
                  command=self.preset_point_turn, relief="flat", padx=6).pack(side="left", padx=2)
        tk.Button(frm_s_btns, text="Cangrejo", bg="#334155", fg="#ff9f1c", font=("Segoe UI", 8, "bold"),
                  command=self.preset_cangrejo, relief="flat", padx=6).pack(side="left", padx=2)

        tk.Checkbutton(frm_s_btns, text="Invertir Servos", variable=self.invertir_servos,
                       bg="#151824", fg="#e2e8f0", selectcolor="#0c0e17", font=("Segoe UI", 8),
                       command=self.al_cambiar_inversion_servos).pack(side="right", padx=(4, 0))
        tk.Checkbutton(frm_s_btns, text="Servos 360 deg", variable=self.servos_360,
                       bg="#151824", fg="#00f5d4", selectcolor="#0c0e17", font=("Segoe UI", 8, "bold"),
                       command=self.actualizar_rango_servos).pack(side="right", padx=(4, 0))

        # --- PANEL JOYSTICK FISICO (NANO) ---
        card_joy = ttk.Frame(col_izq, style="Card.TFrame", padding=8)
        card_joy.pack(fill="x", pady=(0, 6))

        frm_joy_top = ttk.Frame(card_joy, style="Card.TFrame")
        frm_joy_top.pack(fill="x", pady=(0, 4))

        ttk.Label(frm_joy_top, text="JOYSTICK (NANO):", style="Header.TLabel").pack(side="left", padx=(0, 4))
        self.cb_puertos_joy = ttk.Combobox(frm_joy_top, width=8, state="readonly")
        self.cb_puertos_joy.pack(side="left", padx=2)

        self.btn_conectar_joy = tk.Button(frm_joy_top, text="Conectar Joy", bg="#00f5d4", fg="#0c0e17",
                                          font=("Segoe UI", 8, "bold"), command=self.toggle_conexion_joy, relief="flat", padx=5)
        self.btn_conectar_joy.pack(side="left", padx=3)

        self.lbl_badge_joy = tk.Label(frm_joy_top, text="[OFF]", bg="#2a2e3f", fg="#f87171",
                                      font=("Segoe UI", 8, "bold"), padx=6, pady=1)
        self.lbl_badge_joy.pack(side="left", padx=3)

        # Body: sticks 2D canvases + pot and buttons
        frm_joy_body = ttk.Frame(card_joy, style="Card.TFrame")
        frm_joy_body.pack(fill="x", pady=2)

        # Stick 1 (L)
        frm_s1 = ttk.Frame(frm_joy_body, style="Card.TFrame")
        frm_s1.pack(side="left", padx=(0, 8))
        ttk.Label(frm_s1, text="STICK 1 (L)", font=("Segoe UI", 8, "bold"), style="SubHeader.TLabel").pack(anchor="center")
        self.canvas_joy_s1 = tk.Canvas(frm_s1, width=64, height=64, bg="#08090f", highlightthickness=1, highlightbackground="#334155")
        self.canvas_joy_s1.pack(anchor="center", pady=1)
        self.lbl_joy_s1 = ttk.Label(frm_s1, text="X: 0% | Y: 0%", font=("Consolas", 7), style="SubHeader.TLabel")
        self.lbl_joy_s1.pack(anchor="center")

        # Stick 2 (R)
        frm_s2 = ttk.Frame(frm_joy_body, style="Card.TFrame")
        frm_s2.pack(side="left", padx=(0, 8))
        ttk.Label(frm_s2, text="STICK 2 (R)", font=("Segoe UI", 8, "bold"), style="SubHeader.TLabel").pack(anchor="center")
        self.canvas_joy_s2 = tk.Canvas(frm_s2, width=64, height=64, bg="#08090f", highlightthickness=1, highlightbackground="#334155")
        self.canvas_joy_s2.pack(anchor="center", pady=1)
        self.lbl_joy_s2 = ttk.Label(frm_s2, text="X: 0% | Y: 0%", font=("Consolas", 7), style="SubHeader.TLabel")
        self.lbl_joy_s2.pack(anchor="center")

        # Controls & Badges
        frm_joy_ctrls = ttk.Frame(frm_joy_body, style="Card.TFrame")
        frm_joy_ctrls.pack(side="left", fill="both", expand=True)

        ttk.Label(frm_joy_ctrls, text="POTENCIOMETRO:", font=("Segoe UI", 8, "bold"), style="SubHeader.TLabel").pack(anchor="w")
        self.lbl_joy_pot = ttk.Label(frm_joy_ctrls, text="Pot: 150 / 255 (59%)", style="Value.TLabel")
        self.lbl_joy_pot.pack(anchor="w", pady=(0, 2))

        frm_badges = ttk.Frame(frm_joy_ctrls, style="Card.TFrame")
        frm_badges.pack(anchor="w", fill="x")

        self.badge_btn_modo = tk.Label(frm_badges, text="MODO", bg="#334155", fg="#94a3b8", font=("Segoe UI", 7, "bold"), padx=3, pady=1)
        self.badge_btn_modo.pack(side="left", padx=1)

        self.badge_btn_centrar = tk.Label(frm_badges, text="90 deg", bg="#334155", fg="#94a3b8", font=("Segoe UI", 7, "bold"), padx=3, pady=1)
        self.badge_btn_centrar.pack(side="left", padx=1)

        self.badge_btn_360 = tk.Label(frm_badges, text="360 deg", bg="#334155", fg="#94a3b8", font=("Segoe UI", 7, "bold"), padx=3, pady=1)
        self.badge_btn_360.pack(side="left", padx=1)

        self.badge_btn_q = tk.Label(frm_badges, text="Q", bg="#334155", fg="#94a3b8", font=("Segoe UI", 7, "bold"), padx=3, pady=1)
        self.badge_btn_q.pack(side="left", padx=1)

        self.badge_btn_e = tk.Label(frm_badges, text="E", bg="#334155", fg="#94a3b8", font=("Segoe UI", 7, "bold"), padx=3, pady=1)
        self.badge_btn_e.pack(side="left", padx=1)

        self.badge_btn_estop = tk.Label(frm_badges, text="ESTOP", bg="#334155", fg="#f87171", font=("Segoe UI", 7, "bold"), padx=3, pady=1)
        self.badge_btn_estop.pack(side="left", padx=1)

        self.dibujar_stick_neutro(self.canvas_joy_s1)
        self.dibujar_stick_neutro(self.canvas_joy_s2)

        # --- PANEL DERECHO: DOBLE ESQUEMA 2D (TX vs RX) ---
        card_dual_esquema = ttk.Frame(col_der, style="Card.TFrame", padding=8)
        card_dual_esquema.pack(fill="x", pady=(0, 6))

        ttk.Label(card_dual_esquema, text="DOBLE COMPARADOR VISUAL ROCKER-BOGIE (TX vs RX)", style="Header.TLabel").pack(anchor="w", pady=(0, 4))

        frm_canvases = ttk.Frame(card_dual_esquema, style="Card.TFrame")
        frm_canvases.pack(fill="x")

        # Canvas TX
        frm_c_tx = ttk.Frame(frm_canvases, style="CardDark.TFrame", padding=4)
        frm_c_tx.pack(side="left", fill="both", expand=True, padx=(0, 4))
        tk.Label(frm_c_tx, text="1. COMANDO TRANSMITIDO (TX)", bg="#11131c", fg="#00f5d4", font=("Segoe UI", 8, "bold")).pack(anchor="center")
        self.canvas_tx = tk.Canvas(frm_c_tx, width=175, height=175, bg="#08090f", highlightthickness=1, highlightbackground="#00f5d4")
        self.canvas_tx.pack(anchor="center", pady=2)
        self.lbl_tx_valores = tk.Label(frm_c_tx, text="Izq: 0 | Der: 0 | S:[90,90,90,90]", bg="#11131c", fg="#94a3b8", font=("Consolas", 8))
        self.lbl_tx_valores.pack(anchor="center")

        # Canvas RX
        frm_c_rx = ttk.Frame(frm_canvases, style="CardDark.TFrame", padding=4)
        frm_c_rx.pack(side="right", fill="both", expand=True, padx=(4, 0))
        tk.Label(frm_c_rx, text="2. TELEMETRIA RECIBIDA (RX)", bg="#11131c", fg="#fbbf24", font=("Segoe UI", 8, "bold")).pack(anchor="center")
        self.canvas_rx = tk.Canvas(frm_c_rx, width=175, height=175, bg="#08090f", highlightthickness=1, highlightbackground="#fbbf24")
        self.canvas_rx.pack(anchor="center", pady=2)
        self.lbl_rx_valores = tk.Label(frm_c_rx, text="Izq: -- | Der: -- | S:[--,--,--,--]", bg="#11131c", fg="#94a3b8", font=("Consolas", 8))
        self.lbl_rx_valores.pack(anchor="center")

        # Botonera Mandos WASD
        frm_mandos = ttk.Frame(card_dual_esquema, style="Card.TFrame", padding=4)
        frm_mandos.pack(fill="x", pady=(4, 0))

        grid_botones = ttk.Frame(frm_mandos, style="Card.TFrame")
        grid_botones.pack(anchor="center")

        self.btn_q = tk.Button(grid_botones, text="Q", width=6, height=2, bg="#334155", fg="#00f5d4",
                               font=("Segoe UI", 8, "bold"), relief="flat", command=lambda: self.activar_macro("PIVOT_IZQ"))
        self.btn_q.grid(row=0, column=0, padx=2, pady=2)

        self.btn_w = tk.Button(grid_botones, text="W", width=8, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat")
        self.btn_w.grid(row=0, column=1, padx=2, pady=2)

        self.btn_e = tk.Button(grid_botones, text="E", width=6, height=2, bg="#334155", fg="#00f5d4",
                               font=("Segoe UI", 8, "bold"), relief="flat", command=lambda: self.activar_macro("PIVOT_DER"))
        self.btn_e.grid(row=0, column=2, padx=2, pady=2)

        self.btn_a = tk.Button(grid_botones, text="A", width=6, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat")
        self.btn_a.grid(row=1, column=0, padx=2, pady=2)

        self.btn_stop = tk.Button(grid_botones, text="STOP", width=8, height=2, bg="#e63946", fg="#ffffff",
                                  font=("Segoe UI", 8, "bold"), relief="flat", command=self.parar_emergencia)
        self.btn_stop.grid(row=1, column=1, padx=2, pady=2)

        self.btn_d = tk.Button(grid_botones, text="D", width=6, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat")
        self.btn_d.grid(row=1, column=2, padx=2, pady=2)

        self.btn_s = tk.Button(grid_botones, text="S", width=8, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat")
        self.btn_s.grid(row=2, column=1, padx=2, pady=2)

        # Metricas Resumen
        card_metricas = ttk.Frame(col_der, style="Card.TFrame", padding=6)
        card_metricas.pack(fill="x", pady=(0, 4))
        grid_met = ttk.Frame(card_metricas, style="Card.TFrame")
        grid_met.pack(fill="x")

        ttk.Label(grid_met, text="Tasa TX:", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_met_tasa = ttk.Label(grid_met, text="0 Hz", style="Value.TLabel")
        self.lbl_met_tasa.grid(row=0, column=1, sticky="w", padx=(4, 15))

        ttk.Label(grid_met, text="Paquetes TX:", style="SubHeader.TLabel").grid(row=0, column=2, sticky="w")
        self.lbl_met_tot_tx = ttk.Label(grid_met, text="0", style="Value.TLabel")
        self.lbl_met_tot_tx.grid(row=0, column=3, sticky="w", padx=(4, 15))

        ttk.Label(grid_met, text="Paquetes RX:", style="SubHeader.TLabel").grid(row=0, column=4, sticky="w")
        self.lbl_met_tot_rx = ttk.Label(grid_met, text="0", style="ValueWarn.TLabel")
        self.lbl_met_tot_rx.grid(row=0, column=5, sticky="w", padx=4)

        ttk.Label(grid_met, text="Latencia RF:", style="SubHeader.TLabel").grid(row=1, column=0, sticky="w")
        self.lbl_met_latencia = ttk.Label(grid_met, text="-- ms", style="Value.TLabel")
        self.lbl_met_latencia.grid(row=1, column=1, sticky="w", padx=(4, 15))

        ttk.Label(grid_met, text="Matches 1:1:", style="SubHeader.TLabel").grid(row=1, column=2, sticky="w")
        self.lbl_met_matches = ttk.Label(grid_met, text="0 OK", style="Value.TLabel")
        self.lbl_met_matches.grid(row=1, column=3, sticky="w", padx=(4, 15))

        ttk.Label(grid_met, text="Discrepancias:", style="SubHeader.TLabel").grid(row=1, column=4, sticky="w")
        self.lbl_met_mismatches = ttk.Label(grid_met, text="0", style="ValueWarn.TLabel")
        self.lbl_met_mismatches.grid(row=1, column=5, sticky="w", padx=4)

        # =========================================================================
        # 3. TERMINAL INFERIOR MULTI-CANAL DE DEPURACION Y VALIDACION
        # =========================================================================
        card_consola = ttk.Frame(self.root, style="Card.TFrame", padding=(12, 6))
        card_consola.pack(fill="both", expand=True, padx=12, pady=(4, 8))

        frm_tit_cons = ttk.Frame(card_consola, style="Card.TFrame")
        frm_tit_cons.pack(fill="x", pady=(0, 2))

        ttk.Label(frm_tit_cons, text="MONITOR MULTI-CANAL DE DEPURACION (TX / RX / VALIDACION)", style="Header.TLabel").pack(side="left")

        tk.Checkbutton(frm_tit_cons, text="Ver Hex TX", variable=self.mostrar_hex,
                       bg="#151824", fg="#94a3b8", selectcolor="#0c0e17", font=("Segoe UI", 8)).pack(side="left", padx=(15, 3))
        tk.Checkbutton(frm_tit_cons, text="Ver TX RAW", variable=self.mostrar_raw_esp,
                       bg="#151824", fg="#94a3b8", selectcolor="#0c0e17", font=("Segoe UI", 8)).pack(side="left", padx=3)
        tk.Checkbutton(frm_tit_cons, text="Ver RX RAW", variable=self.mostrar_raw_mkr,
                       bg="#151824", fg="#94a3b8", selectcolor="#0c0e17", font=("Segoe UI", 8)).pack(side="left", padx=3)
        tk.Checkbutton(frm_tit_cons, text="TX Continuo", variable=self.tx_continuo,
                       bg="#151824", fg="#00f5d4", selectcolor="#0c0e17", font=("Segoe UI", 8)).pack(side="left", padx=3)
        tk.Checkbutton(frm_tit_cons, text="AutoScroll", variable=self.auto_scroll,
                       bg="#151824", fg="#94a3b8", selectcolor="#0c0e17", font=("Segoe UI", 8)).pack(side="left", padx=3)

        tk.Button(frm_tit_cons, text="Guardar Log", bg="#334155", fg="#ffffff", font=("Segoe UI", 7, "bold"),
                  command=self.guardar_log_archivo, relief="flat", padx=6).pack(side="right", padx=2)
        tk.Button(frm_tit_cons, text="Limpiar", bg="#334155", fg="#ffffff", font=("Segoe UI", 7, "bold"),
                  command=self.limpiar_consola, relief="flat", padx=6).pack(side="right", padx=2)

        frm_txt = ttk.Frame(card_consola, style="Card.TFrame")
        frm_txt.pack(fill="both", expand=True)

        scroll_y = tk.Scrollbar(frm_txt)
        scroll_y.pack(side="right", fill="y")

        self.txt_consola = tk.Text(frm_txt, height=8, bg="#07080d", fg="#e2e8f0",
                                   font=("Consolas", 9), insertbackground="#ffffff", relief="flat",
                                   yscrollcommand=scroll_y.set)
        self.txt_consola.pack(side="left", fill="both", expand=True)
        scroll_y.config(command=self.txt_consola.yview)

        # Tags de color para claridad visual
        self.txt_consola.tag_config("TAG_TX", foreground="#00f5d4")        # Cyan: Salida PC -> TX
        self.txt_consola.tag_config("TAG_ESP", foreground="#38b000")       # Verde: Logs TX Firmware
        self.txt_consola.tag_config("TAG_MKR", foreground="#fbbf24")       # Amarillo: Logs RX Firmware
        self.txt_consola.tag_config("TAG_MATCH", foreground="#34d399")     # Verde brillante: Match 1:1
        self.txt_consola.tag_config("TAG_MISMATCH", foreground="#f87171")  # Rojo: Discrepancia
        self.txt_consola.tag_config("TAG_WARN", foreground="#fb923c")      # Naranja: Alertas
        self.txt_consola.tag_config("TAG_SYS", foreground="#94a3b8")       # Gris: Sistema

        # Volcar logs previos
        if hasattr(self, '_log_buffer') and self._log_buffer:
            for tag, msg in self._log_buffer:
                self.log_consola(tag, msg)
            self._log_buffer.clear()

        self.log_consola("SYS", "HMI Rover Debug cargado. Conecte los puertos COM de Transmisor (TX) y/o Receptor (RX).")
        self.actualizar_lista_puertos()

    def crear_slider(self, parent, nombre, variable, desde, hasta, callback=None):
        frm = ttk.Frame(parent, style="Card.TFrame")
        frm.pack(fill="x", pady=1)
        ttk.Label(frm, text=nombre, style="SubHeader.TLabel").pack(anchor="w")
        cmd_call = callback if callback else self.al_mover_slider_motor
        s = tk.Scale(frm, from_=desde, to=hasta, orient="horizontal", variable=variable,
                     bg="#151824", fg="#00f5d4", highlightthickness=0, command=cmd_call)
        s.pack(fill="x")

    def crear_slider_servo(self, parent, servo_idx, nombre, variable):
        frm = ttk.Frame(parent, style="Card.TFrame")
        frm.pack(fill="x", pady=1)

        rango_str = "0-360 deg" if self.servos_360.get() else "10-170 deg"
        lbl = ttk.Label(frm, text=f"{nombre} ({rango_str})", style="SubHeader.TLabel")
        lbl.pack(anchor="w")

        desde = 0 if self.servos_360.get() else 10
        hasta = 360 if self.servos_360.get() else 170
        s = tk.Scale(frm, from_=desde, to=hasta, orient="horizontal", variable=variable,
                     bg="#151824", fg="#00f5d4", highlightthickness=0, command=self.al_mover_servo)
        s.pack(fill="x")
        self.sliders_servos[servo_idx] = (lbl, s, nombre)

    def actualizar_rango_servos(self):
        es_360 = self.servos_360.get()
        desde = 0 if es_360 else 10
        hasta = 360 if es_360 else 170
        rango_str = "0-360 deg" if es_360 else "10-170 deg"

        if hasattr(self, 'lbl_header_servos') and self.lbl_header_servos is not None:
            self.lbl_header_servos.config(text=f"SERVOS DE DIRECCION ({rango_str})")

        for idx, (lbl, s, nombre) in self.sliders_servos.items():
            s.config(from_=desde, to=hasta)
            lbl.config(text=f"{nombre} ({rango_str})")
            val = getattr(self, f"ang_s{idx}").get()
            if not es_360:
                val = max(10, min(170, val))
                getattr(self, f"ang_s{idx}").set(val)

        modo = self.modo_conduccion.get()
        if modo == "CRAB":
            self.preset_cangrejo()
        elif self.comando_actual in ["PIVOT_IZQ", "PIVOT_DER"]:
            self.preset_point_turn()
        else:
            self.actualizar_grafico_tx()

        estado_txt = "360 deg (Continuo/Extendido)" if es_360 else "Estandar (10-170 deg Seguro)"
        self.log_consola("SYS", f"Rango de Servos cambiado a: {estado_txt}")

    def crear_slider_trim(self, parent, motor_idx, nombre, variable):
        frm = ttk.Frame(parent, style="Card.TFrame")
        frm.pack(fill="x", pady=2)

        lbl = ttk.Label(frm, text=f"{nombre} [100% -> PWM: 150]", style="SubHeader.TLabel")
        lbl.pack(anchor="w")
        self.lbl_trims[motor_idx] = (lbl, nombre)

        def al_mover(val):
            self.actualizar_labels_trim()
            if self.conectado_tx and self.comando_actual != "STOP":
                self.enviar_trama_actual()
            self.actualizar_grafico_tx()

        s = tk.Scale(frm, from_=0, to=150, orient="horizontal", variable=variable,
                     bg="#151824", fg="#00f5d4", highlightthickness=0, command=al_mover)
        s.pack(fill="x")

    def get_pwm_motor(self, motor_idx):
        """Calcula el PWM (0-255) escalando el Master del lado por el ratio de Trim (0-150%)."""
        if motor_idx in [1, 2, 3]:
            master = self.master_izq.get()
        else:
            master = self.master_der.get()
        trim = getattr(self, f"trim_m{motor_idx}").get()
        return max(0, min(255, int(round(master * (trim / 100.0)))))

    def actualizar_labels_trim(self):
        for idx in range(1, 7):
            if idx in self.lbl_trims:
                lbl, nombre = self.lbl_trims[idx]
                trim = getattr(self, f"trim_m{idx}").get()
                pwm = self.get_pwm_motor(idx)
                lbl.config(text=f"{nombre} [{trim}% -> PWM: {pwm}]")

    def reset_trims(self):
        for i in range(1, 7):
            getattr(self, f"trim_m{i}").set(100)
        self.actualizar_labels_trim()
        if self.conectado_tx and self.comando_actual != "STOP":
            self.enviar_trama_actual()
        self.actualizar_grafico_tx()
        self.log_consola("SYS", "Trims de los 6 motores restablecidos al 100% (Ratio 1.0x).")

    def calcular_pwms_tx(self):
        cmd = self.comando_actual.strip().upper()
        if not cmd or cmd == "STOP" or cmd == " ":
            return [0, 0, 0, 0, 0, 0]

        m1 = self.get_pwm_motor(1)
        m2 = self.get_pwm_motor(2)
        m3 = self.get_pwm_motor(3)
        m4 = self.get_pwm_motor(4)
        m5 = self.get_pwm_motor(5)
        m6 = self.get_pwm_motor(6)

        if cmd == "W":
            return [m1, m2, m3, m4, m5, m6]
        elif cmd == "S":
            return [-m1, -m2, -m3, -m4, -m5, -m6]
        elif cmd == "PIVOT_IZQ":
            return [-m1, -m2, -m3, m4, m5, m6]
        elif cmd == "PIVOT_DER":
            return [m1, m2, m3, -m4, -m5, -m6]
        elif cmd == "A":
            if self.modo_conduccion.get() == "CRAB":
                return [m1, m2, m3, m4, m5, m6]
            return [int(m1 * 0.7), int(m2 * 0.7), int(m3 * 0.7), m4, m5, m6]
        elif cmd == "D":
            if self.modo_conduccion.get() == "CRAB":
                return [m1, m2, m3, m4, m5, m6]
            return [m1, m2, m3, int(m4 * 0.7), int(m5 * 0.7), int(m6 * 0.7)]
        elif cmd == "CRAB":
            return [m1, m2, m3, m4, m5, m6]
        else:
            return [0, 0, 0, 0, 0, 0]

    # =========================================================================
    # COMUNICACION PUERTO 1 (TX) Y PUERTO 2 (RX)
    # =========================================================================
    def actualizar_lista_puertos(self):
        if not SERIAL_DISPONIBLE:
            if hasattr(self, 'cb_puerto_tx'):
                self.cb_puerto_tx['values'] = ["Sin pyserial"]
            if hasattr(self, 'cb_puerto_rx'):
                self.cb_puerto_rx['values'] = ["Sin pyserial"]
            if hasattr(self, 'cb_puertos_joy'):
                self.cb_puertos_joy['values'] = ["Sin pyserial"]
            return

        com_list = list(serial.tools.list_ports.comports())
        puertos = [p.device for p in com_list]
        if puertos:
            if hasattr(self, 'cb_puerto_tx'):
                self.cb_puerto_tx['values'] = puertos
            if hasattr(self, 'cb_puerto_rx'):
                self.cb_puerto_rx['values'] = puertos
            if hasattr(self, 'cb_puertos_joy'):
                self.cb_puertos_joy['values'] = puertos

            # Deteccion pasiva de perfiles de hardware soportados
            for p in com_list:
                perf = self.registry.detectar_perfil(p)
                if perf:
                    self.log_consola("SYS", f"[AUTODETECCION] Puerto {p.device} coincide con perfil: {perf.nombre} ({perf.id})")

            chips_conocidos = ['ch340', 'cp210', 'ftdi', 'usb-serial', 'arduino', 'esp32', 'silicon labs', 'usb serial']
            puertos_detectados = []
            for p in com_list:
                info_txt = f"{p.description} {p.manufacturer or ''} {p.hwid}".lower()
                if any(chip in info_txt for chip in chips_conocidos):
                    puertos_detectados.append(p.device)

            orden_puertos = puertos_detectados + [pt for pt in puertos if pt not in puertos_detectados]

            # Puerto TX (Transmisor)
            if hasattr(self, 'cb_puerto_tx'):
                if not self.cb_puerto_tx.get() or self.cb_puerto_tx.get() not in puertos:
                    self.cb_puerto_tx.set(orden_puertos[0])

            # Puerto RX (Receptor)
            if hasattr(self, 'cb_puerto_rx'):
                if len(orden_puertos) > 1 and (not self.cb_puerto_rx.get() or self.cb_puerto_rx.get() not in puertos):
                    self.cb_puerto_rx.set(orden_puertos[1])
                elif not self.cb_puerto_rx.get() or self.cb_puerto_rx.get() not in puertos:
                    self.cb_puerto_rx.set(orden_puertos[0])

            # Puerto Mando Joystick (si existe)
            if hasattr(self, 'cb_puertos_joy'):
                if len(orden_puertos) > 2 and (not self.cb_puertos_joy.get() or self.cb_puertos_joy.get() not in puertos):
                    self.cb_puertos_joy.set(orden_puertos[2])
                elif len(orden_puertos) > 1 and (not self.cb_puertos_joy.get() or self.cb_puertos_joy.get() not in puertos):
                    self.cb_puertos_joy.set(orden_puertos[1])
                elif not self.cb_puertos_joy.get() or self.cb_puertos_joy.get() not in puertos:
                    self.cb_puertos_joy.set(orden_puertos[0])

            # Autodeteccion pasiva para los puertos preseleccionados
            if hasattr(self, 'cb_puerto_tx') and self.cb_puerto_tx.get():
                self.autodetectar_perfil_puerto(self.cb_puerto_tx.get(), "TX")
            if hasattr(self, 'cb_puerto_rx') and self.cb_puerto_rx.get():
                self.autodetectar_perfil_puerto(self.cb_puerto_rx.get(), "RX")

            self.log_consola("SYS", f"Puertos COM escaneados: {', '.join(puertos)} | Preseleccionado TX: {self.cb_puerto_tx.get() if hasattr(self, 'cb_puerto_tx') else ''}")
        else:
            if hasattr(self, 'cb_puerto_tx'):
                self.cb_puerto_tx['values'] = ["Sin puertos"]
            if hasattr(self, 'cb_puerto_rx'):
                self.cb_puerto_rx['values'] = ["Sin puertos"]
            if hasattr(self, 'cb_puertos_joy'):
                self.cb_puertos_joy['values'] = ["Sin puertos"]

    def al_seleccionar_puerto_tx(self, event=None):
        puerto = self.cb_puerto_tx.get()
        self.autodetectar_perfil_puerto(puerto, "TX")

    def al_seleccionar_puerto_rx(self, event=None):
        puerto = self.cb_puerto_rx.get()
        self.autodetectar_perfil_puerto(puerto, "RX")

    def autodetectar_perfil_puerto(self, nombre_puerto, rol):
        """Asigna automaticamente el perfil si coincide el VID:PID por USB."""
        if not SERIAL_DISPONIBLE or not nombre_puerto:
            return
        try:
            com_list = list(serial.tools.list_ports.comports())
            for p in com_list:
                if p.device == nombre_puerto:
                    perfil = self.registry.detectar_perfil(p)
                    if perfil:
                        if rol == "TX":
                            self.perfil_tx.set(perfil.id)
                        else:
                            self.perfil_rx.set(perfil.id)
                        self.log_consola("SYS", f"[AUTODETECCION {rol}] Perfil asignado automaticamente: {perfil.nombre} ({perfil.id})")
                    break
        except Exception:
            pass

    def toggle_conexion_tx(self):
        if not SERIAL_DISPONIBLE:
            if messagebox:
                messagebox.showerror("Error", "pyserial no instalado.")
            return

        if self.conectado_tx:
            self.conectado_tx = False
            if self.serial_tx and self.serial_tx.is_open:
                try:
                    self.serial_tx.close()
                except Exception:
                    pass
            self.btn_conectar_tx.config(text="Conectar TX", bg="#00f5d4", fg="#0c0e17")
            self.badge_tx.config(text="[TX OFF]", bg="#2a2e3f", fg="#f87171")
            self.log_consola("SYS", "Puerto TX desconectado.")
        else:
            p = self.cb_puerto_tx.get()
            if not p or p in ["Sin puertos", "Sin pyserial"]:
                if messagebox:
                    messagebox.showwarning("Atencion", "Seleccione un puerto valido para TX.")
                return
            try:
                self.serial_tx = serial.Serial()
                self.serial_tx.port = p
                self.serial_tx.baudrate = 115200
                self.serial_tx.timeout = 0.05
                self.serial_tx.write_timeout = 0.2
                self.serial_tx.rts = False
                self.serial_tx.dtr = False
                self.serial_tx.open()
                time.sleep(0.15)
                self.serial_tx.dtr = True
                self.conectado_tx = True
                self.btn_conectar_tx.config(text="Desconectar TX", bg="#e63946", fg="#ffffff")
                self.badge_tx.config(text=f"[TX ON] {p}", bg="#064e3b", fg="#34d399")
                self.log_consola("SYS", f"Transmisor TX conectado en {p} @ 115200 bps (DTR=ON, RTS=OFF).")
                # Auto-identificacion activa tras 300 ms
                self.root.after(300, self.ident_o_ping_tx)
            except Exception as e:
                self.conectado_tx = False
                if messagebox:
                    messagebox.showerror("Error TX", f"No se pudo conectar a {p}:\n{e}")

    def ident_o_ping_tx(self):
        """Envia comando IDENT y PING al transmisor para handshake activo y confirmacion."""
        if self.conectado_tx and self.serial_tx and self.serial_tx.is_open:
            try:
                self.serial_tx.write(b"IDENT\n")
                self.serial_tx.flush()
                self.log_consola("TX", "[DIAGNOSTICO] Enviado comando 'IDENT' a TX...")
            except Exception as e:
                self.log_consola("WARN", f"Error enviando IDENT a TX: {e}")
        else:
            if messagebox:
                messagebox.showinfo("IDENT TX", "Conecte primero el puerto TX.")

    def ping_tx(self):
        self.ident_o_ping_tx()

    def reset_hw_tx(self):
        if self.conectado_tx and self.serial_tx and self.serial_tx.is_open:
            try:
                self.log_consola("SYS", "[RESET] Enviando pulso de reinicio por hardware a TX...")
                self.serial_tx.dtr = False
                self.serial_tx.rts = True
                time.sleep(0.1)
                self.serial_tx.rts = False
                time.sleep(0.15)
                self.serial_tx.dtr = True
                self.log_consola("SYS", "[RESET] TX liberado. Esperando arranque...")
                self.root.after(1000, self.ident_o_ping_tx)
            except Exception as e:
                self.log_consola("WARN", f"Error reiniciando TX: {e}")
        else:
            if messagebox:
                messagebox.showinfo("Reset TX", "Conecte primero el puerto TX.")

    def toggle_conexion_rx(self):
        if not SERIAL_DISPONIBLE:
            if messagebox:
                messagebox.showerror("Error", "pyserial no instalado.")
            return

        if self.conectado_rx:
            self.conectado_rx = False
            if self.serial_rx and self.serial_rx.is_open:
                try:
                    self.serial_rx.close()
                except Exception:
                    pass
            self.btn_conectar_rx.config(text="Conectar RX", bg="#fbbf24", fg="#0c0e17")
            self.badge_rx.config(text="[RX OFF]", bg="#2a2e3f", fg="#f87171")
            self.log_consola("SYS", "Puerto RX desconectado.")
        else:
            p = self.cb_puerto_rx.get()
            if not p or p in ["Sin puertos", "Sin pyserial"]:
                if messagebox:
                    messagebox.showwarning("Atencion", "Seleccione un puerto valido para RX.")
                return
            try:
                self.serial_rx = serial.Serial()
                self.serial_rx.port = p
                self.serial_rx.baudrate = 115200
                self.serial_rx.timeout = 0.05
                self.serial_rx.write_timeout = 0.2
                self.serial_rx.rts = False
                self.serial_rx.dtr = True
                self.serial_rx.open()
                time.sleep(0.15)
                self.conectado_rx = True
                self.btn_conectar_rx.config(text="Desconectar RX", bg="#e63946", fg="#ffffff")
                self.badge_rx.config(text=f"[RX ON] {p}", bg="#451a03", fg="#fbbf24")
                self.log_consola("SYS", f"Receptor RX conectado en {p} @ 115200 bps.")
                self.root.after(300, self.ident_o_ping_rx)
            except Exception as e:
                self.conectado_rx = False
                if messagebox:
                    messagebox.showerror("Error RX", f"No se pudo conectar a {p}:\n{e}")

    def ident_o_ping_rx(self):
        """Envia comando IDENT y PING al receptor para handshake activo y confirmacion."""
        if self.conectado_rx and self.serial_rx and self.serial_rx.is_open:
            try:
                self.serial_rx.write(b"IDENT\n")
                self.serial_rx.flush()
                self.log_consola("MKR", "[DIAGNOSTICO] Enviado comando 'IDENT' a RX...")
            except Exception as e:
                self.log_consola("WARN", f"Error enviando IDENT a RX: {e}")
        else:
            if messagebox:
                messagebox.showinfo("IDENT RX", "Conecte primero el puerto RX.")

    def ping_rx(self):
        self.ident_o_ping_rx()

    # =========================================================================
    # APROVISIONAMIENTO Y FLASHEO EN 1 CLIC (NO BLOQUEANTE)
    # =========================================================================
    def iniciar_flasheo_tx(self):
        if self.flasheando:
            if messagebox:
                messagebox.showwarning("Flasheo en curso", "Ya hay una operacion de subida en ejecucion.")
            return
        puerto = self.cb_puerto_tx.get()
        if not puerto or puerto in ["Sin puertos", "Sin pyserial"]:
            if messagebox:
                messagebox.showwarning("Atencion", "Seleccione un puerto COM valido para TX.")
            return
        perfil_id = self.perfil_tx.get()
        try:
            perfil = self.registry.obtener_perfil(perfil_id)
        except KeyError:
            perfil = self.registry.perfil_default

        hilo = threading.Thread(target=self._ejecutar_flasheo, args=(puerto, perfil, "TX"), daemon=True)
        hilo.start()

    def iniciar_flasheo_rx(self):
        if self.flasheando:
            if messagebox:
                messagebox.showwarning("Flasheo en curso", "Ya hay una operacion de subida en ejecucion.")
            return
        puerto = self.cb_puerto_rx.get()
        if not puerto or puerto in ["Sin puertos", "Sin pyserial"]:
            if messagebox:
                messagebox.showwarning("Atencion", "Seleccione un puerto COM valido para RX.")
            return
        perfil_id = self.perfil_rx.get()
        try:
            perfil = self.registry.obtener_perfil(perfil_id)
        except KeyError:
            perfil = self.registry.perfil_default

        hilo = threading.Thread(target=self._ejecutar_flasheo, args=(puerto, perfil, "RX"), daemon=True)
        hilo.start()

    def _ejecutar_flasheo(self, puerto, perfil, rol):
        self.flasheando = True
        rol_tx = (rol == "TX")
        estaba_conectado = self.conectado_tx if rol_tx else self.conectado_rx

        if estaba_conectado:
            self.root.after(0, self.log_consola, "SYS", f"[SYS] Cerrando puerto {puerto} temporalmente para flasheo de {rol}...")
            if rol_tx:
                self.conectado_tx = False
                if self.serial_tx and self.serial_tx.is_open:
                    try:
                        self.serial_tx.close()
                    except Exception:
                        pass
                self.root.after(0, lambda: self.badge_tx.config(text="[TX FLASHEANDO]", bg="#78350f", fg="#fde047"))
                self.root.after(0, lambda: self.btn_conectar_tx.config(text="Conectar TX", bg="#00f5d4", fg="#0c0e17"))
            else:
                self.conectado_rx = False
                if self.serial_rx and self.serial_rx.is_open:
                    try:
                        self.serial_rx.close()
                    except Exception:
                        pass
                self.root.after(0, lambda: self.badge_rx.config(text="[RX FLASHEANDO]", bg="#78350f", fg="#fde047"))
                self.root.after(0, lambda: self.btn_conectar_rx.config(text="Conectar RX", bg="#fbbf24", fg="#0c0e17"))

        time.sleep(0.3)
        self.root.after(0, self.log_consola, "SYS", f"[SYS] Iniciando subida de firmware para {rol} ({perfil.nombre}) en {puerto}...")

        def cb_log(msg):
            self.root.after(0, self.log_consola, "SYS", msg)

        try:
            exito = self.flasher_engine.flashear(
                puerto=puerto,
                perfil=perfil,
                rol=rol,
                callback_log=cb_log,
            )
            if exito:
                self.root.after(0, self.log_consola, "SYS", f"[OK] Subida de firmware {rol} completada exitosamente.")
                if rol_tx:
                    self.root.after(0, lambda: self.badge_tx.config(text="[TX FLASHEADO OK]", bg="#064e3b", fg="#34d399"))
                else:
                    self.root.after(0, lambda: self.badge_rx.config(text="[RX FLASHEADO OK]", bg="#064e3b", fg="#34d399"))
            else:
                self.root.after(0, self.log_consola, "WARN", f"[ERROR] Fallo en la subida de firmware {rol}.")
                if rol_tx:
                    self.root.after(0, lambda: self.badge_tx.config(text="[TX ERROR FLASH]", bg="#450a0a", fg="#f87171"))
                else:
                    self.root.after(0, lambda: self.badge_rx.config(text="[RX ERROR FLASH]", bg="#450a0a", fg="#f87171"))
        except Exception as e:
            self.root.after(0, self.log_consola, "WARN", f"[ERROR] Excepcion durante el flasheo de {rol}: {e}")
        finally:
            self.flasheando = False
            if estaba_conectado:
                self.root.after(0, self.log_consola, "SYS", f"[SYS] Restaurando conexion en {puerto}...")
                time.sleep(1.2)
                if rol_tx:
                    self.root.after(0, self.toggle_conexion_tx)
                else:
                    self.root.after(0, self.toggle_conexion_rx)

    # =========================================================================
    # SINCRONIZACION PRE-DESPLIEGUE Y LIBERACION DE PUERTO (CAMPO)
    # =========================================================================
    def sincronizar_calibracion_rx(self):
        """Transmite trama de calibracion y orden de persistencia NVS al receptor."""
        if not self.conectado_rx or not self.serial_rx or not self.serial_rx.is_open:
            if messagebox:
                messagebox.showwarning("Atencion", "Conecte primero el puerto RX para sincronizar la calibracion.")
            return

        trims = [
            self.trim_m1.get(),
            self.trim_m2.get(),
            self.trim_m3.get(),
            self.trim_m4.get(),
            self.trim_m5.get(),
            self.trim_m6.get(),
        ]
        servos = [
            self.ang_s1.get(),
            self.ang_s2.get(),
            self.ang_s3.get(),
            self.ang_s4.get(),
        ]

        def tarea_sincronizacion():
            def cb_log(msg):
                self.root.after(0, self.log_consola, "SYS", msg)

            cb_log("[SYS] Sincronizando parametros de calibracion con el receptor...")
            exito = self.flasher_engine.sincronizar_calibracion(
                serial_conn=self.serial_rx,
                trims=trims,
                servos=servos,
                persistir_nvs=True,
                callback_log=cb_log,
            )
            if exito:
                self.root.after(0, lambda: self.badge_rx.config(text="[CALIB SINCRONIZADA]", bg="#064e3b", fg="#34d399"))
            else:
                self.root.after(0, lambda: self.badge_rx.config(text="[ERROR CALIB]", bg="#450a0a", fg="#f87171"))

        threading.Thread(target=tarea_sincronizacion, daemon=True).start()

    def liberar_rx_campo(self):
        """Cierra de forma segura el puerto serie del receptor para operacion autonoma."""
        def cb_log(msg):
            self.root.after(0, self.log_consola, "SYS", msg)

        if self.conectado_rx and self.serial_rx:
            self.conectado_rx = False
            self.flasher_engine.liberar_puerto(self.serial_rx, callback_log=cb_log)
            self.serial_rx = None
            if hasattr(self, 'btn_conectar_rx'):
                self.btn_conectar_rx.config(text="Conectar RX", bg="#fbbf24", fg="#0c0e17")
        else:
            cb_log("[INFO] Receptor RX ya se encuentra desconectado y libre para campo.")

        if hasattr(self, 'badge_rx'):
            self.badge_rx.config(text="[RX LIBERADO - CAMPO]", bg="#1e293b", fg="#38bdf8")

    # =========================================================================
    # PROCESAMIENTO DE HANDSHAKE ACTIVO (TX Y RX)
    # =========================================================================
    def procesar_handshake_tx(self, placa, rol, version, linea):
        self.log_consola("SYS", f"[HANDSHAKE TX] {linea} -> Placa:{placa} Rol:{rol} Ver:{version}")
        if hasattr(self, 'badge_tx'):
            self.badge_tx.config(text=f"[TX: {placa} {version}]", bg="#064e3b", fg="#34d399")
        try:
            perfil = self.registry.obtener_perfil(placa, default=None)
            if perfil and hasattr(self, 'perfil_tx'):
                self.perfil_tx.set(perfil.id)
        except Exception:
            pass

    def procesar_handshake_rx(self, placa, rol, version, linea):
        self.log_consola("SYS", f"[HANDSHAKE RX] {linea} -> Placa:{placa} Rol:{rol} Ver:{version}")
        if hasattr(self, 'badge_rx'):
            self.badge_rx.config(text=f"[RX: {placa} {version}]", bg="#451a03", fg="#fbbf24")
        try:
            perfil = self.registry.obtener_perfil(placa, default=None)
            if perfil and hasattr(self, 'perfil_rx'):
                self.perfil_rx.set(perfil.id)
        except Exception:
            pass

    def iniciar_hilos(self):
        self.hilo_tx = threading.Thread(target=self.bucle_lectura_tx, daemon=True)
        self.hilo_tx.start()

        self.hilo_rx = threading.Thread(target=self.bucle_lectura_rx, daemon=True)
        self.hilo_rx.start()

        self.hilo_joy = threading.Thread(target=self.bucle_lectura_joy, daemon=True)
        self.hilo_joy.start()

    def dibujar_stick_neutro(self, canvas):
        canvas.delete("all")
        cx, cy = 32, 32
        canvas.create_line(cx, 4, cx, 60, fill="#2a2e3f", dash=(2, 2))
        canvas.create_line(4, cy, 60, cy, fill="#2a2e3f", dash=(2, 2))
        canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#00f5d4", outline="#ffffff", width=1)

    def actualizar_stick_canvas(self, canvas, nx, ny, color="#00f5d4"):
        canvas.delete("all")
        cx, cy = 32, 32
        canvas.create_line(cx, 4, cx, 60, fill="#2a2e3f", dash=(2, 2))
        canvas.create_line(4, cy, 60, cy, fill="#2a2e3f", dash=(2, 2))
        px = cx + int((nx / 100.0) * 24)
        py = cy - int((ny / 100.0) * 24)
        canvas.create_oval(px - 4, py - 4, px + 4, py + 4, fill=color, outline="#ffffff", width=1)

    def toggle_conexion_joy(self):
        if not SERIAL_DISPONIBLE:
            if messagebox:
                messagebox.showerror("Error", "Libreria pyserial no instalada.")
            return

        if self.conectado_joy:
            self.conectado_joy = False
            if self.serial_joy and self.serial_joy.is_open:
                try:
                    self.serial_joy.close()
                except Exception:
                    pass
            self.btn_conectar_joy.config(text="Conectar Joy", bg="#00f5d4", fg="#0c0e17")
            self.lbl_badge_joy.config(text="[OFF]", bg="#2a2e3f", fg="#f87171")
            self.dibujar_stick_neutro(self.canvas_joy_s1)
            self.dibujar_stick_neutro(self.canvas_joy_s2)
            self.log_consola("SYS", "Joystick Nano desconectado.")
        else:
            p = self.cb_puertos_joy.get()
            if not p or p in ["Sin puertos", "Sin pyserial"]:
                if messagebox:
                    messagebox.showwarning("Atencion", "Seleccione un puerto COM valido para el Joystick.")
                return
            try:
                self.serial_joy = serial.Serial()
                self.serial_joy.port = p
                self.serial_joy.baudrate = 115200
                self.serial_joy.timeout = 0.05
                self.serial_joy.dtr = True
                self.serial_joy.rts = False
                self.serial_joy.open()
                self.conectado_joy = True
                self.btn_conectar_joy.config(text="Desconectar Joy", bg="#e63946", fg="#ffffff")
                self.lbl_badge_joy.config(text=f"[ON] {p}", bg="#064e3b", fg="#34d399")
                self.log_consola("SYS", f"Joystick fisico conectado en {p} @ 115200 bps.")
            except Exception as e:
                self.conectado_joy = False
                if messagebox:
                    messagebox.showerror("Error Joystick", f"No se pudo conectar a {p}:\n{e}")

    def bucle_lectura_joy(self):
        while self.ejecutando:
            if self.conectado_joy and self.serial_joy and self.serial_joy.is_open:
                try:
                    linea = self.serial_joy.readline().decode('utf-8', errors='ignore').strip()
                    if linea.startswith("JOY:"):
                        self.procesar_trama_joystick(linea[4:])
                except Exception:
                    pass
            time.sleep(0.015)

    def procesar_trama_joystick(self, datos_str):
        try:
            partes = datos_str.split(',')
            if len(partes) >= 11:
                s1_x = int(partes[0])
                s1_y = int(partes[1])
                s2_x = int(partes[2])
                s2_y = int(partes[3])
                master_pwm = int(partes[4])
                sw1 = int(partes[5])
                sw2 = int(partes[6])
                estop = int(partes[7])
                s360 = int(partes[8])
                piv_izq = int(partes[9])
                piv_der = int(partes[10])

                self.root.after(0, self.actualizar_ui_joystick, s1_x, s1_y, s2_x, s2_y, master_pwm,
                                sw1, sw2, estop, s360, piv_izq, piv_der)
        except Exception:
            pass

    def actualizar_ui_joystick(self, s1_x, s1_y, s2_x, s2_y, pot, sw1, sw2, estop, s360, piv_izq, piv_der):
        self.actualizar_stick_canvas(self.canvas_joy_s1, s1_x, s1_y, "#00f5d4")
        self.lbl_joy_s1.config(text=f"X: {s1_x:+d}% | Y: {s1_y:+d}%")

        self.actualizar_stick_canvas(self.canvas_joy_s2, s2_x, s2_y, "#fbbf24")
        self.lbl_joy_s2.config(text=f"X: {s2_x:+d}% | Y: {s2_y:+d}%")

        pct = int((pot / 255.0) * 100)
        self.lbl_joy_pot.config(text=f"Pot: {pot} / 255 ({pct}%)")

        if abs(self.master_izq.get() - pot) > 2:
            self.master_izq.set(pot)
            self.master_der.set(pot)
            self.actualizar_labels_trim()
            if self.conectado_tx and self.comando_actual != "STOP":
                self.enviar_trama_actual()
            self.actualizar_grafico_tx()

        c_off, c_on = "#334155", "#00f5d4"
        fg_off, fg_on = "#94a3b8", "#0f172a"

        self.badge_btn_modo.config(bg=c_on if sw1 else c_off, fg=fg_on if sw1 else fg_off,
                                   text="CANGREJO" if sw1 else "ACKERM")
        self.badge_btn_centrar.config(bg=c_on if sw2 else c_off, fg=fg_on if sw2 else fg_off)
        self.badge_btn_360.config(bg="#ff9f1c" if s360 else c_off, fg=fg_on if s360 else fg_off)
        self.badge_btn_q.config(bg=c_on if piv_izq else c_off, fg=fg_on if piv_izq else fg_off)
        self.badge_btn_e.config(bg=c_on if piv_der else c_off, fg=fg_on if piv_der else fg_off)
        self.badge_btn_estop.config(bg="#ef4444" if estop else c_off, fg="#ffffff" if estop else "#f87171")

        if sw1 != self.ultimo_joy_sw1:
            self.ultimo_joy_sw1 = sw1
            nuevo_modo = "CRAB" if sw1 else "ACKERMANN"
            self.modo_conduccion.set(nuevo_modo)
            self.cambiar_modo_conduccion()

        if s360 != self.ultimo_joy_360:
            self.ultimo_joy_360 = s360
            self.servos_360.set(bool(s360))
            self.actualizar_rango_servos()

        if estop and not self.ultimo_joy_estop:
            self.ultimo_joy_estop = estop
            self.parar_emergencia()
            return
        self.ultimo_joy_estop = estop

        if sw2:
            self.centrar_todos_los_servos()

        if not any(self.teclas_presionadas.values()):
            modo = self.modo_conduccion.get()
            nuevo = " "

            if piv_izq or s2_x < -35:
                self.preset_point_turn()
                nuevo = "PIVOT_IZQ"
            elif piv_der or s2_x > 35:
                self.preset_point_turn()
                nuevo = "PIVOT_DER"
            elif s1_y > 35:
                nuevo = "W"
                if modo in ["ACKERMANN", "CRAB"]:
                    self.ang_s1.set(90); self.ang_s2.set(90); self.ang_s3.set(90); self.ang_s4.set(90)
            elif s1_y < -35:
                nuevo = "S"
                if modo in ["ACKERMANN", "CRAB"]:
                    self.ang_s1.set(90); self.ang_s2.set(90); self.ang_s3.set(90); self.ang_s4.set(90)
            elif s1_x < -35:
                nuevo = "A"
                if modo == "ACKERMANN":
                    if not self.invertir_servos.get():
                        self.ang_s1.set(120); self.ang_s2.set(120); self.ang_s3.set(60); self.ang_s4.set(60)
                    else:
                        self.ang_s1.set(60); self.ang_s2.set(60); self.ang_s3.set(120); self.ang_s4.set(120)
                elif modo == "CRAB":
                    if self.servos_360.get():
                        ang = 180 if not self.invertir_servos.get() else 0
                        self.ang_s1.set(ang); self.ang_s2.set(ang); self.ang_s3.set(ang); self.ang_s4.set(ang)
                    else:
                        ang = 135 if not self.invertir_servos.get() else 45
                        self.ang_s1.set(ang); self.ang_s2.set(ang); self.ang_s3.set(ang); self.ang_s4.set(ang)
            elif s1_x > 35:
                nuevo = "D"
                if modo == "ACKERMANN":
                    if not self.invertir_servos.get():
                        self.ang_s1.set(60); self.ang_s2.set(60); self.ang_s3.set(120); self.ang_s4.set(120)
                    else:
                        self.ang_s1.set(120); self.ang_s2.set(120); self.ang_s3.set(60); self.ang_s4.set(60)
                elif modo == "CRAB":
                    if self.servos_360.get():
                        ang = 0 if not self.invertir_servos.get() else 180
                        self.ang_s1.set(ang); self.ang_s2.set(ang); self.ang_s3.set(ang); self.ang_s4.set(ang)
                    else:
                        ang = 45 if not self.invertir_servos.get() else 135
                        self.ang_s1.set(ang); self.ang_s2.set(ang); self.ang_s3.set(ang); self.ang_s4.set(ang)

            if nuevo != self.comando_actual:
                self.comando_actual = nuevo
                self.enviar_trama_actual()
                self.actualizar_botones_ui(nuevo)

    def bucle_lectura_tx(self):
        while self.ejecutando:
            if self.conectado_tx and self.serial_tx and self.serial_tx.is_open:
                try:
                    linea = self.serial_tx.readline().decode('utf-8', errors='ignore').strip()
                    if linea:
                        if linea.startswith("ID:"):
                            parsed = self.registry.parsear_handshake(linea, strict=False)
                            if parsed:
                                placa, rol, version = parsed
                                self.root.after(0, self.procesar_handshake_tx, placa, rol, version, linea)
                        elif linea.startswith("PONG:"):
                            self.root.after(0, self.log_consola, "SYS", f"[OK] {linea}")
                            self.root.after(0, lambda: self.badge_tx.config(text="[TX OK]", bg="#064e3b", fg="#34d399"))
                        elif self.mostrar_raw_esp.get():
                            self.root.after(0, self.log_consola, "ESP", f"[TX RAW]: {linea}")
                except Exception:
                    pass
            time.sleep(0.01)

    def bucle_lectura_rx(self):
        while self.ejecutando:
            if self.conectado_rx and self.serial_rx and self.serial_rx.is_open:
                try:
                    linea = self.serial_rx.readline().decode('utf-8', errors='ignore').strip()
                    if linea:
                        self.contador_rx_mkr += 1
                        self.procesar_linea_mkr(linea)
                except Exception:
                    pass
            time.sleep(0.01)

    def procesar_linea_mkr(self, linea):
        if linea.startswith("ID:"):
            parsed = self.registry.parsear_handshake(linea, strict=False)
            if parsed:
                placa, rol, version = parsed
                self.root.after(0, self.procesar_handshake_rx, placa, rol, version, linea)
            return

        if linea.startswith("PONG:"):
            self.root.after(0, self.log_consola, "SYS", f"[OK] {linea}")
            self.root.after(0, lambda: self.badge_rx.config(text="[RX OK]", bg="#451a03", fg="#fbbf24"))
            return

        # Trama de telemetria estructurada TLM:izq,der,s1,s2,s3,s4,dt,cola
        if linea.startswith("TLM:"):
            datos = linea[4:].split(',')
            if len(datos) >= 8:
                try:
                    izq = int(datos[0]) if datos[0] != "FAILSAFE" else 0
                    der = int(datos[1])
                    s1 = int(datos[2])
                    s2 = int(datos[3])
                    s3 = int(datos[4])
                    s4 = int(datos[5])
                    dt_mkr = int(datos[6])
                    cola = int(datos[7])

                    self.snapshot_rx['izq'] = izq
                    self.snapshot_rx['der'] = der
                    self.snapshot_rx['s1'] = s1
                    self.snapshot_rx['s2'] = s2
                    self.snapshot_rx['s3'] = s3
                    self.snapshot_rx['s4'] = s4
                    self.snapshot_rx['dt'] = dt_mkr
                    self.snapshot_rx['cola'] = cola
                    self.snapshot_rx['t'] = time.time()
                    self.snapshot_rx['activo'] = True

                    # Actualizar grafico RX y realizar validacion cruzada
                    self.root.after(0, self.actualizar_grafico_rx)
                    self.root.after(0, self.validar_datos_cruzados)
                except Exception:
                    pass
        else:
            if self.mostrar_raw_mkr.get():
                self.root.after(0, self.log_consola, "MKR", f"[RX RAW]: {linea}")

    def validar_datos_cruzados(self):
        tx = self.snapshot_tx
        rx = self.snapshot_rx

        latencia = (rx['t'] - tx['t']) * 1000.0
        if latencia >= 0:
            self.ultima_latencia_ms = round(latencia, 1)

        match_izq = (tx['izq'] == rx['izq'])
        match_der = (tx['der'] == rx['der'])
        match_s1 = (tx['s1'] == rx['s1'])
        match_s2 = (tx['s2'] == rx['s2'])
        match_s3 = (tx['s3'] == rx['s3'])
        match_s4 = (tx['s4'] == rx['s4'])

        total_match = match_izq and match_der and match_s1 and match_s2 and match_s3 and match_s4

        if total_match:
            self.contador_matches += 1
            self.badge_validacion.config(text=f"[MATCH 100%] (Lat: {self.ultima_latencia_ms} ms)", bg="#064e3b", fg="#34d399")
            self.lbl_met_latencia.config(text=f"{self.ultima_latencia_ms} ms", style="Value.TLabel")
        else:
            self.contador_mismatches += 1
            self.badge_validacion.config(text="[TRANSICION / DISCREPANCIA]", bg="#78350f", fg="#fde047")

        self.lbl_met_matches.config(text=f"{self.contador_matches} OK")
        self.lbl_met_mismatches.config(text=f"{self.contador_mismatches}")

    # =========================================================================
    # TRANSMISION DE COMANDOS (GUI -> TX)
    # =========================================================================
    def enviar_trama_actual(self):
        cmd = self.comando_actual.upper()
        if cmd == " ":
            cmd = "STOP"

        avg_izq = int((self.get_pwm_motor(1) + self.get_pwm_motor(2) + self.get_pwm_motor(3)) / 3)
        avg_der = int((self.get_pwm_motor(4) + self.get_pwm_motor(5) + self.get_pwm_motor(6)) / 3)

        if cmd == "STOP":
            pot_izq_efectivo = 0
            pot_der_efectivo = 0
            s1 = 90; s2 = 90; s3 = 90; s4 = 90
        elif cmd == "W":
            pot_izq_efectivo = avg_izq
            pot_der_efectivo = avg_der
            s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()
        elif cmd == "S":
            pot_izq_efectivo = -avg_izq
            pot_der_efectivo = -avg_der
            s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()
        elif cmd == "PIVOT_IZQ":
            pot_izq_efectivo = -avg_izq
            pot_der_efectivo = avg_der
            s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()
        elif cmd == "PIVOT_DER":
            pot_izq_efectivo = avg_izq
            pot_der_efectivo = -avg_der
            s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()
        else: # A, D, CRAB
            pot_izq_efectivo = avg_izq
            pot_der_efectivo = avg_der
            s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()

        self.snapshot_tx['cmd'] = cmd
        self.snapshot_tx['izq'] = pot_izq_efectivo
        self.snapshot_tx['der'] = pot_der_efectivo
        self.snapshot_tx['s1'] = s1
        self.snapshot_tx['s2'] = s2
        self.snapshot_tx['s3'] = s3
        self.snapshot_tx['s4'] = s4
        self.snapshot_tx['t'] = time.time()

        self.actualizar_grafico_tx()

        if not self.conectado_tx or not self.serial_tx or not self.serial_tx.is_open:
            return

        trama = f"{cmd},{abs(pot_izq_efectivo)},{abs(pot_der_efectivo)},{s1},{s2},{s3},{s4}\n"
        raw_bytes = trama.encode('ascii')

        try:
            self.serial_tx.write(raw_bytes)
            self.contador_tx += 1

            hex_str = " ".join(f"{b:02X}" for b in raw_bytes)
            msg = f"[TX PC -> MCU #{self.contador_tx}]: \"{trama.strip()}\""
            self.log_consola("TX", msg)
            if self.mostrar_hex.get():
                self.log_consola("TX", f"   BYTES: [{hex_str}] ({len(raw_bytes)} B)")
        except Exception as e:
            self.log_consola("WARN", f"Error enviando comando a TX: {e}")

    # =========================================================================
    # DIBUJO CINEMATICO 2D: TRANSMITIDO (TX) vs RECIBIDO (RX)
    # =========================================================================
    def dibujar_rueda_en_canvas(self, canvas, cx, cy, angulo_grados, color, texto, pwm=0):
        rad = math.radians(90 - angulo_grados)
        w_half, h_half = 6, 12
        vertices = [(-w_half, -h_half), (w_half, -h_half), (w_half, h_half), (-w_half, h_half)]
        puntos_rotados = []
        for vx, vy in vertices:
            rx = cx + (vx * math.cos(rad) - vy * math.sin(rad))
            ry = cy + (vx * math.sin(rad) + vy * math.cos(rad))
            puntos_rotados.extend([rx, ry])
        canvas.create_polygon(puntos_rotados, fill=color, outline="#ffffff", width=1)
        canvas.create_text(cx, cy, text=texto, fill="#ffffff", font=("Segoe UI", 5, "bold"))

        if pwm != 0:
            arrow_color = "#34d399" if pwm > 0 else "#f97316"
            longitud = 8 + int((min(255, abs(pwm)) / 255.0) * 10)
            signo = 1 if pwm > 0 else -1

            ux = math.sin(rad)
            uy = -math.cos(rad)

            x_ini = cx + signo * (h_half * 0.4) * ux
            y_ini = cy + signo * (h_half * 0.4) * uy
            x_fin = cx + signo * (h_half + longitud) * ux
            y_fin = cy + signo * (h_half + longitud) * uy

            canvas.create_line(x_ini, y_ini, x_fin, y_fin,
                               fill=arrow_color, width=2,
                               arrow=tk.LAST, arrowshape=(6, 8, 3))

    def actualizar_grafico_tx(self):
        c = self.canvas_tx
        c.delete("all")
        cx, cy = 87, 87
        c.create_rectangle(cx - 26, cy - 42, cx + 26, cy + 42, fill="#151928", outline="#00f5d4", width=2)
        c.create_text(cx, cy, text="TX\nGUI", fill="#00f5d4", font=("Segoe UI", 7, "bold"), justify="center")

        tx = self.snapshot_tx
        cmd = tx['cmd']
        pwms = self.calcular_pwms_tx()
        color = "#38b000" if (tx['izq'] != 0 or tx['der'] != 0) else "#64748b"
        if tx['izq'] < 0 and tx['der'] < 0:
            color = "#ff9f1c"

        self.dibujar_rueda_en_canvas(c, cx - 42, cy - 36, tx['s1'], color, "M1", pwms[0])
        self.dibujar_rueda_en_canvas(c, cx + 42, cy - 36, tx['s2'], color, "M4", pwms[3])
        self.dibujar_rueda_en_canvas(c, cx - 42, cy,      90,        color, "M2", pwms[1])
        self.dibujar_rueda_en_canvas(c, cx + 42, cy,      90,        color, "M5", pwms[4])
        self.dibujar_rueda_en_canvas(c, cx - 42, cy + 36, tx['s3'], color, "M3", pwms[2])
        self.dibujar_rueda_en_canvas(c, cx + 42, cy + 36, tx['s4'], color, "M6", pwms[5])

        modo_act = self.modo_conduccion.get()
        if cmd == "W":
            c.create_line(cx, cy - 8, cx, cy - 28, fill="#00f5d4", width=2, arrow=tk.LAST)
        elif cmd == "S":
            c.create_line(cx, cy + 8, cx, cy + 28, fill="#ff9f1c", width=2, arrow=tk.LAST)
        elif cmd == "A":
            if modo_act == "CRAB":
                c.create_line(cx + 15, cy, cx - 25, cy, fill="#ff9f1c", width=2, arrow=tk.LAST)
            else:
                c.create_arc(cx - 20, cy - 20, cx + 20, cy + 20, start=45, extent=180, style=tk.ARC, outline="#00f5d4", width=2)
        elif cmd == "D":
            if modo_act == "CRAB":
                c.create_line(cx - 15, cy, cx + 25, cy, fill="#ff9f1c", width=2, arrow=tk.LAST)
            else:
                c.create_arc(cx - 20, cy - 20, cx + 20, cy + 20, start=225, extent=180, style=tk.ARC, outline="#00f5d4", width=2)
        elif cmd == "PIVOT_IZQ":
            c.create_arc(cx - 20, cy - 20, cx + 20, cy + 20, start=45, extent=180, style=tk.ARC, outline="#00f5d4", width=2)
        elif cmd in ["PIVOT_DER", "PIVOT"]:
            c.create_arc(cx - 20, cy - 20, cx + 20, cy + 20, start=225, extent=180, style=tk.ARC, outline="#00f5d4", width=2)
        elif cmd == "CRAB":
            if self.servos_360.get():
                c.create_line(cx + 15, cy, cx - 25, cy, fill="#ff9f1c", width=2, arrow=tk.LAST)
            else:
                c.create_line(cx - 15, cy + 15, cx + 20, cy - 20, fill="#ff9f1c", width=2, arrow=tk.LAST)

        self.lbl_tx_valores.config(text=f"Izq:{tx['izq']} | Der:{tx['der']} | S:[{tx['s1']},{tx['s2']},{tx['s3']},{tx['s4']}]")

    def actualizar_grafico_rx(self):
        c = self.canvas_rx
        c.delete("all")
        cx, cy = 87, 87
        c.create_rectangle(cx - 26, cy - 42, cx + 26, cy + 42, fill="#151928", outline="#fbbf24", width=2)
        c.create_text(cx, cy, text="RX\nROVER", fill="#fbbf24", font=("Segoe UI", 7, "bold"), justify="center")

        rx = self.snapshot_rx
        pwms = [rx['izq'], rx['izq'], rx['izq'], rx['der'], rx['der'], rx['der']]
        color = "#38b000" if (rx['izq'] != 0 or rx['der'] != 0) else "#64748b"
        if rx['izq'] < 0 and rx['der'] < 0:
            color = "#ff9f1c"

        self.dibujar_rueda_en_canvas(c, cx - 42, cy - 36, rx['s1'], color, "M1", pwms[0])
        self.dibujar_rueda_en_canvas(c, cx + 42, cy - 36, rx['s2'], color, "M4", pwms[3])
        self.dibujar_rueda_en_canvas(c, cx - 42, cy,      90,        color, "M2", pwms[1])
        self.dibujar_rueda_en_canvas(c, cx + 42, cy,      90,        color, "M5", pwms[4])
        self.dibujar_rueda_en_canvas(c, cx - 42, cy + 36, rx['s3'], color, "M3", pwms[2])
        self.dibujar_rueda_en_canvas(c, cx + 42, cy + 36, rx['s4'], color, "M6", pwms[5])

        if rx['izq'] > 0 and rx['der'] > 0:
            c.create_line(cx, cy - 8, cx, cy - 28, fill="#38b000", width=2, arrow=tk.LAST)
        elif rx['izq'] < 0 and rx['der'] < 0:
            c.create_line(cx, cy + 8, cx, cy + 28, fill="#ff9f1c", width=2, arrow=tk.LAST)

        self.lbl_rx_valores.config(text=f"Izq:{rx['izq']} | Der:{rx['der']} | S:[{rx['s1']},{rx['s2']},{rx['s3']},{rx['s4']}]")

    # =========================================================================
    # LOGGING Y CONSOLA
    # =========================================================================
    def log_consola(self, tag, texto):
        t_str = time.strftime("[%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}] "
        tag_map = {
            "TX": "TAG_TX",
            "ESP": "TAG_ESP",
            "MKR": "TAG_MKR",
            "MATCH": "TAG_MATCH",
            "MISMATCH": "TAG_MISMATCH",
            "WARN": "TAG_WARN",
            "SYS": "TAG_SYS"
        }
        style = tag_map.get(tag, "TAG_SYS")
        if hasattr(self, 'txt_consola') and self.txt_consola is not None:
            try:
                self.txt_consola.insert("end", t_str, "TAG_SYS")
                self.txt_consola.insert("end", str(texto) + "\n", style)
                if hasattr(self, 'auto_scroll') and self.auto_scroll.get():
                    self.txt_consola.see("end")
                return
            except Exception:
                pass
        try:
            if sys.stdout is not None and hasattr(sys.stdout, 'write'):
                sys.stdout.write(f"{t_str} [{tag}] {texto}\n")
                sys.stdout.flush()
        except Exception:
            pass
        if hasattr(self, '_log_buffer'):
            self._log_buffer.append((tag, texto))

    def limpiar_consola(self):
        if self.txt_consola:
            self.txt_consola.delete("1.0", "end")

    def guardar_log_archivo(self):
        if not self.txt_consola:
            return
        contenido = self.txt_consola.get("1.0", "end")
        if not contenido.strip():
            if messagebox:
                messagebox.showinfo("Info", "Consola vacia.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".log",
                                            filetypes=[("Log", "*.log"), ("Texto", "*.txt")],
                                            initialfile=f"log_rover_dual_{time.strftime('%Y%m%d_%H%M%S')}.log")
        if ruta:
            try:
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(contenido)
                if messagebox:
                    messagebox.showinfo("Exito", f"Log guardado en:\n{ruta}")
            except Exception as e:
                if messagebox:
                    messagebox.showerror("Error", f"Error guardando:\n{e}")

    # =========================================================================
    # PRESETS Y CALIBRACIONES
    # =========================================================================
    def cambiar_modo_conduccion(self, event=None):
        m = self.modo_conduccion.get()
        if m == "POINT_TURN":
            self.preset_point_turn()
        elif m == "CRAB":
            self.preset_cangrejo()
        elif m == "ACKERMANN":
            self.centrar_todos_los_servos()

    def centrar_todos_los_servos(self):
        self.ang_s1.set(90); self.ang_s2.set(90); self.ang_s3.set(90); self.ang_s4.set(90)
        self.enviar_trama_actual()

    def calcular_cinematica_inversa(self, vx, vy, omega, L=1.0, W=1.0):
        """
        Calcula la cinematica inversa 2D para la plataforma Rocker-Bogie 6x6.
        Determina los angulos tangenciales exactos de los 4 servos (S1, S2, S3, S4)
        para giro y traslacion sin derrape ni arrastre lateral.

        Marco de referencia (Cuerpo del Rover):
          +X: Hacia la derecha del vehiculo
          +Y: Hacia adelante (longitudinal)
          +omega: Giro antihorario (CCW)
          -omega: Giro horario (CW)

        Posicion de las esquinas respecto al centro de rotacion (0, 0):
          S1 (Delantero Izq): (-W, +L)
          S2 (Delantero Der): (+W, +L)
          S3 (Trasero Izq):   (-W, -L)
          S4 (Trasero Der):   (+W, -L)
        """
        esquinas = {
            'S1': (-W,  L),
            'S2': ( W,  L),
            'S3': (-W, -L),
            'S4': ( W, -L),
        }
        angulos = {}
        for rueda, (xi, yi) in esquinas.items():
            v_ix = vx - omega * yi
            v_iy = vy + omega * xi

            if abs(v_ix) < 1e-4 and abs(v_iy) < 1e-4:
                angulos[rueda] = 90
                continue

            trac_reversa = (v_iy < -1e-4) or (abs(v_iy) <= 1e-4 and ((omega < 0 and xi > 0) or (omega > 0 and xi < 0)))

            if trac_reversa:
                heading_rad = math.atan2(-v_ix, -v_iy)
            else:
                heading_rad = math.atan2(v_ix, v_iy)

            heading_deg = math.degrees(heading_rad)
            servo_deg = int(round(90 - heading_deg))
            if self.servos_360.get():
                servo_deg = servo_deg % 360
            else:
                servo_deg = max(10, min(170, servo_deg))
            angulos[rueda] = servo_deg

        if self.invertir_servos.get():
            for k in angulos:
                if self.servos_360.get():
                    angulos[k] = (360 - angulos[k]) % 360
                else:
                    angulos[k] = 180 - angulos[k]

        return angulos['S1'], angulos['S2'], angulos['S3'], angulos['S4']

    def al_cambiar_inversion_servos(self):
        modo = self.modo_conduccion.get()
        if modo == "CRAB":
            self.preset_cangrejo()
        elif modo == "ACKERMANN":
            self.evaluar_movimiento()
        elif self.comando_actual in ["PIVOT_IZQ", "PIVOT_DER"]:
            self.preset_point_turn()
        else:
            self.actualizar_grafico_tx()

    def preset_point_turn(self):
        s1, s2, s3, s4 = self.calcular_cinematica_inversa(0.0, 0.0, -1.0)
        self.ang_s1.set(s1); self.ang_s2.set(s2); self.ang_s3.set(s3); self.ang_s4.set(s4)
        self.enviar_trama_actual()
        self.log_consola("SYS", f"Geometria tangencial configurada para Giro 360 deg: S1={s1} deg, S2={s2} deg, S3={s3} deg, S4={s4} deg.")

    def preset_cangrejo(self):
        if self.servos_360.get():
            s1, s2, s3, s4 = (180, 180, 180, 180) if not self.invertir_servos.get() else (0, 0, 0, 0)
        else:
            s1, s2, s3, s4 = self.calcular_cinematica_inversa(1.0, 1.0, 0.0)
        self.ang_s1.set(s1); self.ang_s2.set(s2); self.ang_s3.set(s3); self.ang_s4.set(s4)
        self.enviar_trama_actual()
        self.actualizar_grafico_tx()
        tipo = "Lateral Puro 90 deg" if self.servos_360.get() else "Diagonal 45 deg"
        self.log_consola("SYS", f"Geometria configurada para Modo Cangrejo ({tipo}): S1={s1} deg, S2={s2} deg, S3={s3} deg, S4={s4} deg.")

    def sync_master_izq(self, val):
        self.actualizar_labels_trim()
        if self.conectado_tx and self.comando_actual != "STOP":
            self.enviar_trama_actual()
        self.actualizar_grafico_tx()

    def sync_master_der(self, val):
        self.actualizar_labels_trim()
        if self.conectado_tx and self.comando_actual != "STOP":
            self.enviar_trama_actual()
        self.actualizar_grafico_tx()

    def al_mover_slider_motor(self, val):
        self.actualizar_labels_trim()
        if self.conectado_tx and self.comando_actual != "STOP":
            self.enviar_trama_actual()
        self.actualizar_grafico_tx()

    def al_mover_servo(self, val):
        if self.conectado_tx and self.comando_actual != "STOP":
            self.enviar_trama_actual()
        self.actualizar_grafico_tx()

    # =========================================================================
    # TECLADO
    # =========================================================================
    def evento_key_press(self, event):
        k = event.keysym.lower()
        if k in self.teclas_presionadas:
            if not self.teclas_presionadas[k]:
                self.teclas_presionadas[k] = True
                self.evaluar_movimiento()

    def evento_key_release(self, event):
        k = event.keysym.lower()
        if k in self.teclas_presionadas:
            self.teclas_presionadas[k] = False
            self.evaluar_movimiento()

    def parar_emergencia(self):
        for k in self.teclas_presionadas:
            self.teclas_presionadas[k] = False
        self.comando_actual = "STOP"
        self.enviar_trama_actual()
        self.actualizar_botones_ui("STOP")
        self.actualizar_grafico_tx()

    def activar_macro(self, tipo):
        if tipo == "PIVOT_IZQ":
            self.preset_point_turn()
            self.comando_actual = "PIVOT_IZQ"
        elif tipo == "PIVOT_DER":
            self.preset_point_turn()
            self.comando_actual = "PIVOT_DER"
        self.enviar_trama_actual()
        self.actualizar_botones_ui(self.comando_actual)

    def evaluar_movimiento(self):
        modo = self.modo_conduccion.get()
        nuevo = " "

        if self.teclas_presionadas['space']:
            nuevo = " "
        elif self.teclas_presionadas['q']:
            self.preset_point_turn()
            nuevo = "PIVOT_IZQ"
        elif self.teclas_presionadas['e']:
            self.preset_point_turn()
            nuevo = "PIVOT_DER"
        elif self.teclas_presionadas['w']:
            nuevo = "W"
            if modo in ["ACKERMANN", "CRAB"]:
                self.ang_s1.set(90); self.ang_s2.set(90); self.ang_s3.set(90); self.ang_s4.set(90)
        elif self.teclas_presionadas['s']:
            nuevo = "S"
            if modo in ["ACKERMANN", "CRAB"]:
                self.ang_s1.set(90); self.ang_s2.set(90); self.ang_s3.set(90); self.ang_s4.set(90)
        elif self.teclas_presionadas['a']:
            nuevo = "A"
            if modo == "ACKERMANN":
                if not self.invertir_servos.get():
                    self.ang_s1.set(120); self.ang_s2.set(120); self.ang_s3.set(60); self.ang_s4.set(60)
                else:
                    self.ang_s1.set(60); self.ang_s2.set(60); self.ang_s3.set(120); self.ang_s4.set(120)
            elif modo == "CRAB":
                if self.servos_360.get():
                    ang = 180 if not self.invertir_servos.get() else 0
                    self.ang_s1.set(ang); self.ang_s2.set(ang); self.ang_s3.set(ang); self.ang_s4.set(ang)
                else:
                    ang = 135 if not self.invertir_servos.get() else 45
                    self.ang_s1.set(ang); self.ang_s2.set(ang); self.ang_s3.set(ang); self.ang_s4.set(ang)
        elif self.teclas_presionadas['d']:
            nuevo = "D"
            if modo == "ACKERMANN":
                if not self.invertir_servos.get():
                    self.ang_s1.set(60); self.ang_s2.set(60); self.ang_s3.set(120); self.ang_s4.set(120)
                else:
                    self.ang_s1.set(120); self.ang_s2.set(120); self.ang_s3.set(60); self.ang_s4.set(60)
            elif modo == "CRAB":
                if self.servos_360.get():
                    ang = 0 if not self.invertir_servos.get() else 180
                    self.ang_s1.set(ang); self.ang_s2.set(ang); self.ang_s3.set(ang); self.ang_s4.set(ang)
                else:
                    ang = 45 if not self.invertir_servos.get() else 135
                    self.ang_s1.set(ang); self.ang_s2.set(ang); self.ang_s3.set(ang); self.ang_s4.set(ang)

        if nuevo != self.comando_actual:
            self.comando_actual = nuevo
            self.enviar_trama_actual()
            self.actualizar_botones_ui(nuevo)

    def actualizar_botones_ui(self, cmd):
        c_off, c_on = "#334155", "#00f5d4"
        fg_off, fg_on = "#ffffff", "#0c0e17"
        self.btn_w.config(bg=c_on if cmd == "W" else c_off, fg=fg_on if cmd == "W" else fg_off)
        self.btn_s.config(bg=c_on if cmd == "S" else c_off, fg=fg_on if cmd == "S" else fg_off)
        self.btn_a.config(bg=c_on if cmd == "A" else c_off, fg=fg_on if cmd == "A" else fg_off)
        self.btn_d.config(bg=c_on if cmd == "D" else c_off, fg=fg_on if cmd == "D" else fg_off)
        self.btn_q.config(bg=c_on if cmd == "PIVOT_IZQ" else c_off, fg=fg_on if cmd == "PIVOT_IZQ" else "#00f5d4")
        self.btn_e.config(bg=c_on if cmd == "PIVOT_DER" else c_off, fg=fg_on if cmd == "PIVOT_DER" else "#00f5d4")

    # =========================================================================
    # BUCLE PERIODICO DE LA UI (20 HZ KEEP-ALIVE Y METRICAS)
    # =========================================================================
    def bucle_periodico_ui(self):
        t_ahora = time.time()
        dt = t_ahora - self.ultimo_tiempo_tasa

        # Si esta activado TX Continuo y conectado TX, enviar periodicamente
        if self.tx_continuo.get() and self.conectado_tx:
            self.enviar_trama_actual()

        # Calculo de tasa Hz
        if dt >= 1.0:
            self.tasa_tx_hz = int(self.contador_tx / dt)
            self.contador_tx = 0
            self.ultimo_tiempo_tasa = t_ahora
            self.lbl_met_tasa.config(text=f"{self.tasa_tx_hz} Hz")

        self.lbl_met_tot_tx.config(text=f"{self.contador_tx}")
        self.lbl_met_tot_rx.config(text=f"{self.contador_rx_mkr}")

        # Comprobar si el receptor dejo de emitir telemetria (>1.5 seg)
        if self.conectado_rx and (t_ahora - self.snapshot_rx['t'] > 1.5):
            self.badge_validacion.config(text="[SIN SENAL DE RECEPTOR]", bg="#450a0a", fg="#f87171")

        self.root.after(50, self.bucle_periodico_ui)


def configurar_captura_errores():
    import traceback
    import os

    def manejador_excepciones(tipo, valor, tb):
        err_msg = "".join(traceback.format_exception(tipo, valor, tb))
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        log_path = os.path.join(base_dir, "hmi_debug_crash_log.txt")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\nREPORTE DE ERROR DEBUG (CRASH) - {time.strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}\n{err_msg}\n")
        except Exception:
            pass
        try:
            if messagebox:
                messagebox.showerror(
                    "Error Inesperado - HMI Rover Debug",
                    f"Se produjo un fallo al ejecutar la aplicacion de depuracion:\n\n{valor}\n\n"
                    f"Detalles tecnicos guardados en:\n{log_path}"
                )
        except Exception:
            pass

    sys.excepthook = manejador_excepciones


if __name__ == "__main__":
    configurar_captura_errores()
    if not TKINTER_DISPONIBLE:
        sys.stderr.write("[ERROR] El modulo tkinter no esta instalado en este entorno Python.\n")
        sys.exit(1)
    try:
        ventana_principal = tk.Tk()
        app = HMIRoverDebug(ventana_principal)
        ventana_principal.mainloop()
    except Exception as e:
        sys.excepthook(*sys.exc_info())
