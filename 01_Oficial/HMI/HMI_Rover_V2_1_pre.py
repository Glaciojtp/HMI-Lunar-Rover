#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================================
 HMI ROVER LUNAR V2.1-PRE - ROCKER-BOGIE 6x6 (4 SERVOS DE DIRECCION INDEPENDIENTES)
=====================================================================================
 Version Pre-Release Oficial:
  - Soporte predeterminado para Arduino Nano ESP32 (ESP32-S3), con compatibilidad
    para ESP32-C3 SuperMini y Arduino MKR WAN 1310.
  - Registro y autodeteccion pasiva de perfiles de hardware mediante VID:PID USB.
  - Handshake activo con firmware (IDENT / PING) y decodificacion de rol y version.
  - Aprovisionamiento y flasheo en 1 clic (FlasherEngine) y sincronizacion de trims/calibracion.
  - Rango de servos configurable (estandar 10-170 deg o continuo 0-360 deg).
  - Geometria de interfaz fija y estatica (sin desplazamientos ni saltos visuales por teclado).
  - Cinematica corregida: giro a derecha (+X, omega > 0), giro a izquierda (-X, omega < 0).
  - Esquema 2D interactivo con cajas de ruedas y vectores colineales a los angulos reales.
  - Cumplimiento estricto de cero emojis en toda la interfaz y registros de consola.
=====================================================================================
"""

import sys
import os
import time
import math
import threading
from pathlib import Path

# Asegurar importacion de modulos locales de HMI
_dir_actual = os.path.dirname(os.path.abspath(__file__))
if _dir_actual not in sys.path:
    sys.path.insert(0, _dir_actual)

# Modulos de perfiles y motor de flasheo
try:
    from hardware_profiles import (
        HardwareProfileRegistry,
        PerfilHardware,
        PERFILES_OFICIALES,
        PERFIL_DEFAULT_ID,
        parsear_handshake,
    )
except ImportError:
    # Fallback si se ejecuta desde otra ubicacion
    _dir_debug = os.path.abspath(os.path.join(_dir_actual, "..", "..", "02_Debug_y_Pruebas", "HMI_Debug"))
    if _dir_debug not in sys.path:
        sys.path.insert(0, _dir_debug)
    from hardware_profiles import (
        HardwareProfileRegistry,
        PerfilHardware,
        PERFILES_OFICIALES,
        PERFIL_DEFAULT_ID,
        parsear_handshake,
    )

try:
    from flasher_engine import (
        FlasherEngine,
        sanitizar_puerto,
        formatear_trama_calibracion,
    )
except ImportError:
    _dir_debug = os.path.abspath(os.path.join(_dir_actual, "..", "..", "02_Debug_y_Pruebas", "HMI_Debug"))
    if _dir_debug not in sys.path:
        sys.path.insert(0, _dir_debug)
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


class HMIRoverRockerBogieV21Pre:
    def __init__(self, root):
        self.root = root
        self.root.title("HMI Rover Lunar V2.1-pre - Rocker-Bogie 6x6 (4 Servos Independientes)")
        self.root.geometry("1180x840")
        self.root.minsize(1080, 760)
        self.root.configure(bg="#161822")

        # Modulo de perfiles de hardware y flasher
        self.registry = HardwareProfileRegistry()
        self.perfil_activo = self.registry.obtener_perfil(PERFIL_DEFAULT_ID)
        self.flasher = FlasherEngine()
        self.flasheando = False

        # Variables de comunicacion Serial
        self.serial_conn = None
        self.conectado = False
        self.hilo_serial = None
        self.ejecutando = True
        self.txt_consola = None
        self._log_buffer = []
        self._actualizando_desde_teclas = False

        # Estado dinamico de control
        self.comando_actual = " "
        self.modo_conduccion = tk.StringVar(value="ACKERMANN")  # ACKERMANN, POINT_TURN, CRAB, MANUAL
        self.teclas_presionadas = {'w': False, 'a': False, 's': False, 'd': False, 'q': False, 'e': False, 'space': False}
        self.paquetes_tx_contador = 0
        self.tasa_tx_hz = 0
        self.ultimo_tiempo_tasa = time.time()

        # Variables de Trim porcentual (Ratio 0% a 150%, 100% = 1.0x directo de Master)
        self.trim_m1 = tk.IntVar(value=100)  # Delantero Izq
        self.trim_m2 = tk.IntVar(value=100)  # Medio Izq (Fijo)
        self.trim_m3 = tk.IntVar(value=100)  # Trasero Izq
        self.trim_m4 = tk.IntVar(value=100)  # Delantero Der
        self.trim_m5 = tk.IntVar(value=100)  # Medio Der (Fijo)
        self.trim_m6 = tk.IntVar(value=100)  # Trasero Der
        self.lbl_trims = {}

        # Masters de Traccion por Lado (0 a 255)
        self.master_izq = tk.IntVar(value=150)
        self.master_der = tk.IntVar(value=150)

        # Variables de Angulo para los 4 Servomotores Independientes (10 a 170 deg, 90 deg = Centro)
        self.ang_s1 = tk.IntVar(value=90)  # Delantero Izq
        self.ang_s2 = tk.IntVar(value=90)  # Delantero Der
        self.ang_s3 = tk.IntVar(value=90)  # Trasero Izq
        self.ang_s4 = tk.IntVar(value=90)  # Trasero Der

        # Inversion y rango de servos (estandar 10-170 deg o extendido continuo 360 deg)
        self.invertir_servos = tk.BooleanVar(value=False)
        self.servos_360 = tk.BooleanVar(value=False)
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

        # Snapshot para telemetria y graficos
        self.snapshot = {
            'cmd': 'STOP', 'izq': 0, 'der': 0,
            's1': 90, 's2': 90, 's3': 90, 's4': 90
        }

        # Configurar Estilos Visuales
        self.configurar_estilos()

        # Construir Interfaz Grafica
        self.crear_widgets()
        self.actualizar_labels_trim()
        self.redibujar_rover_actual()

        # Enlazar eventos de Teclado
        self.root.bind("<KeyPress>", self.evento_key_press)
        self.root.bind("<KeyRelease>", self.evento_key_release)

        # Iniciar hilos y actualizacion periodica
        self.iniciar_hilos_segundo_plano()
        self.actualizar_telemetria_ui()

    def configurar_estilos(self):
        estilo = ttk.Style()
        estilo.theme_use('clam')

        estilo.configure("Card.TFrame", background="#212433", relief="flat")
        estilo.configure("Dark.TFrame", background="#161822")

        estilo.configure("Header.TLabel", background="#212433", foreground="#00f5d4", font=("Segoe UI", 10, "bold"))
        estilo.configure("SubHeader.TLabel", background="#212433", foreground="#e2e8f0", font=("Segoe UI", 9, "bold"))
        estilo.configure("Value.TLabel", background="#212433", foreground="#38b000", font=("Consolas", 10, "bold"))
        estilo.configure("ValueWarn.TLabel", background="#212433", foreground="#f87171", font=("Consolas", 10, "bold"))
        estilo.configure("Placeholder.TLabel", background="#212433", foreground="#94a3b8", font=("Consolas", 9))

    def crear_widgets(self):
        # =========================================================================
        # 1. BARRA SUPERIOR: CONEXION COM, PERFIL DE HARDWARE & ESTADO GENERAL
        # =========================================================================
        top_frame = ttk.Frame(self.root, style="Card.TFrame", padding=(12, 6))
        top_frame.pack(side="top", fill="x", padx=12, pady=(8, 4))

        lbl_titulo = tk.Label(top_frame, text="ROVER LUNAR CEPIT - V2.1-PRE (4-SERVO HMI)",
                              font=("Segoe UI", 12, "bold"), bg="#212433", fg="#ffffff")
        lbl_titulo.pack(side="left", padx=(0, 10))

        # Selector de Perfil de Hardware
        lbl_perfil = tk.Label(top_frame, text="Perfil:", bg="#212433", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
        lbl_perfil.pack(side="left", padx=(4, 2))

        nombres_perfiles = [p.nombre for p in self.registry.listar_perfiles()]
        self.cb_perfil = ttk.Combobox(top_frame, width=17, values=nombres_perfiles, state="readonly")
        self.cb_perfil.set(self.perfil_activo.nombre)
        self.cb_perfil.pack(side="left", padx=2)
        self.cb_perfil.bind("<<ComboboxSelected>>", self.al_seleccionar_perfil)

        self.lbl_badge_hw = tk.Label(top_frame, text="[NANO ESP32]", bg="#0f766e", fg="#5eead4",
                                     font=("Segoe UI", 8, "bold"), padx=5, pady=1)
        self.lbl_badge_hw.pack(side="left", padx=(2, 8))

        # Selector de Puerto COM
        lbl_puerto = tk.Label(top_frame, text="Puerto:", bg="#212433", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
        lbl_puerto.pack(side="left", padx=(4, 2))

        self.cb_puertos = ttk.Combobox(top_frame, width=9, state="readonly")
        self.cb_puertos.pack(side="left", padx=2)
        self.cb_puertos.bind("<<ComboboxSelected>>", self.al_seleccionar_puerto)

        btn_refrescar = tk.Button(top_frame, text="Refrescar", bg="#334155", fg="#ffffff", font=("Segoe UI", 8, "bold"),
                                  command=self.actualizar_lista_puertos, relief="flat", padx=5, pady=2, takefocus=0)
        btn_refrescar.pack(side="left", padx=2)

        # Baudrate
        lbl_baud = tk.Label(top_frame, text="Baud:", bg="#212433", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
        lbl_baud.pack(side="left", padx=(6, 2))

        self.cb_baud = ttk.Combobox(top_frame, width=7, values=["115200", "57600", "9600"], state="readonly")
        self.cb_baud.set("115200")
        self.cb_baud.pack(side="left", padx=2)

        # Boton Conectar
        self.btn_conectar = tk.Button(top_frame, text="CONECTAR", bg="#00f5d4", fg="#0f172a",
                                      font=("Segoe UI", 9, "bold"), command=self.toggle_conexion,
                                      relief="flat", padx=10, pady=2, cursor="hand2", takefocus=0)
        self.btn_conectar.pack(side="left", padx=6)

        # Boton Identificar Handshake
        self.btn_ident = tk.Button(top_frame, text="IDENT", bg="#334155", fg="#00f5d4",
                                   font=("Segoe UI", 8, "bold"), command=self.ident_o_ping,
                                   relief="flat", padx=6, pady=2, takefocus=0)
        self.btn_ident.pack(side="left", padx=2)

        # Boton Flasheo 1-Clic
        self.btn_flash = tk.Button(top_frame, text="FLASHEAR", bg="#4338ca", fg="#ffffff",
                                   font=("Segoe UI", 8, "bold"), command=self.iniciar_flasheo,
                                   relief="flat", padx=6, pady=2, takefocus=0)
        self.btn_flash.pack(side="left", padx=2)

        # Selector de Modo de Conduccion
        lbl_modo = tk.Label(top_frame, text="Modo:", bg="#212433", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
        lbl_modo.pack(side="left", padx=(6, 2))

        self.cb_modo = ttk.Combobox(top_frame, width=12, textvariable=self.modo_conduccion,
                                    values=["ACKERMANN", "CRAB", "MANUAL"], state="readonly")
        self.cb_modo.pack(side="left", padx=2)
        self.cb_modo.bind("<<ComboboxSelected>>", self.cambiar_modo_conduccion)

        # Indicador de Estado
        self.lbl_estado_badge = tk.Label(top_frame, text="[DESCONECTADO]", bg="#374151", fg="#f87171",
                                         font=("Segoe UI", 9, "bold"), padx=6, pady=2, width=14)
        self.lbl_estado_badge.pack(side="right", padx=2)

        # =========================================================================
        # 3. TERMINAL INFERIOR MULTI-CANAL (CARD_CONSOLA - ALTURA FIJA ANCLADA ABAJO)
        # =========================================================================
        card_consola = ttk.Frame(self.root, style="Card.TFrame", padding=(12, 4))
        card_consola.pack(side="bottom", fill="x", expand=False, padx=12, pady=(2, 6))

        frm_tit_cons = ttk.Frame(card_consola, style="Card.TFrame")
        frm_tit_cons.pack(fill="x", pady=(0, 2))

        ttk.Label(frm_tit_cons, text="TERMINAL Y REGISTRO DE TELEMETRIA", style="Header.TLabel").pack(side="left")

        tk.Button(frm_tit_cons, text="Exportar Log", bg="#334155", fg="#00f5d4", font=("Segoe UI", 8, "bold"),
                  command=self.guardar_log_archivo, relief="flat", padx=6, pady=1, takefocus=0).pack(side="right", padx=(4, 0))

        tk.Button(frm_tit_cons, text="Limpiar", bg="#334155", fg="#ffffff", font=("Segoe UI", 8, "bold"),
                  command=self.limpiar_consola, relief="flat", padx=6, pady=1, takefocus=0).pack(side="right")

        frm_txt = ttk.Frame(card_consola, style="Card.TFrame")
        frm_txt.pack(fill="x")

        scroll_y = ttk.Scrollbar(frm_txt, orient="vertical")
        scroll_y.pack(side="right", fill="y")

        self.txt_consola = tk.Text(frm_txt, height=6, bg="#07080d", fg="#e2e8f0",
                                   font=("Consolas", 9), insertbackground="#ffffff", relief="flat",
                                   takefocus=0, yscrollcommand=scroll_y.set)
        self.txt_consola.pack(side="left", fill="both", expand=True)
        scroll_y.config(command=self.txt_consola.yview)

        # Configurar tags de color para consola
        self.txt_consola.tag_configure("TAG_TX", foreground="#00f5d4")
        self.txt_consola.tag_configure("TAG_MCU", foreground="#38b000")
        self.txt_consola.tag_configure("TAG_WARN", foreground="#fbbf24")
        self.txt_consola.tag_configure("TAG_ERR", foreground="#f87171")
        self.txt_consola.tag_configure("TAG_SYS", foreground="#94a3b8")

        # =========================================================================
        # 2. CUERPO PRINCIPAL (2 COLUMNAS RIGIDAS CON DIVISION UNIFORME 50%-50%)
        # =========================================================================
        main_content = ttk.Frame(self.root, style="Dark.TFrame")
        main_content.pack(side="top", fill="both", expand=True, padx=12, pady=2)

        main_content.columnconfigure(0, weight=1, uniform="cols_principales")
        main_content.columnconfigure(1, weight=1, uniform="cols_principales")
        main_content.rowconfigure(0, weight=1)

        col_izq = ttk.Frame(main_content, style="Dark.TFrame")
        col_izq.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)

        col_der = ttk.Frame(main_content, style="Dark.TFrame")
        col_der.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=0)

        # -------------------------------------------------------------------------
        # TARJETA 1 (IZQ): TRIMS DE TRACCION (RATIO % MULTIPLICADO POR MASTER)
        # -------------------------------------------------------------------------
        card_motores = ttk.Frame(col_izq, style="Card.TFrame", padding=8)
        card_motores.pack(fill="x", pady=(0, 6))

        frm_tit_mot = ttk.Frame(card_motores, style="Card.TFrame")
        frm_tit_mot.pack(fill="x", pady=(0, 2))
        ttk.Label(frm_tit_mot, text="CALIBRACION & TRIMS (RATIO %)", style="Header.TLabel").pack(side="left")

        tk.Button(frm_tit_mot, text="Sincronizar Calib", bg="#1e3a8a", fg="#93c5fd",
                  font=("Segoe UI", 8, "bold"), relief="flat", padx=6, pady=1,
                  command=self.sincronizar_calibracion, takefocus=0).pack(side="right", padx=(4, 0))

        tk.Button(frm_tit_mot, text="Reset Trims (100%)", bg="#334155", fg="#00f5d4",
                  font=("Segoe UI", 8, "bold"), relief="flat", padx=6, pady=1,
                  command=self.reset_trims, takefocus=0).pack(side="right")

        grid_motores = ttk.Frame(card_motores, style="Card.TFrame")
        grid_motores.pack(fill="x")
        grid_motores.columnconfigure(0, weight=1, uniform="cols_m")
        grid_motores.columnconfigure(1, weight=1, uniform="cols_m")

        # Columna Izquierda Motores
        col_m_izq = ttk.Frame(grid_motores, style="Card.TFrame")
        col_m_izq.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        ttk.Label(col_m_izq, text="LADO IZQUIERDO", style="SubHeader.TLabel").pack(anchor="w")
        self.crear_slider_trim(col_m_izq, 1, "M1 (Del. Izq)", self.trim_m1)
        self.crear_slider_trim(col_m_izq, 2, "M2 (Med. Izq)", self.trim_m2)
        self.crear_slider_trim(col_m_izq, 3, "M3 (Tras. Izq)", self.trim_m3)

        frm_mi = ttk.Frame(col_m_izq, style="Card.TFrame")
        frm_mi.pack(fill="x", pady=(2, 0))
        ttk.Label(frm_mi, text="Master Izq:", style="SubHeader.TLabel").pack(side="left")
        tk.Scale(frm_mi, from_=0, to=255, orient="horizontal", variable=self.master_izq,
                 bg="#212433", fg="#00f5d4", highlightthickness=0, command=self.sync_master_izq, takefocus=0).pack(side="right", fill="x", expand=True)

        # Columna Derecha Motores
        col_m_der = ttk.Frame(grid_motores, style="Card.TFrame")
        col_m_der.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        ttk.Label(col_m_der, text="LADO DERECHO", style="SubHeader.TLabel").pack(anchor="w")
        self.crear_slider_trim(col_m_der, 4, "M4 (Del. Der)", self.trim_m4)
        self.crear_slider_trim(col_m_der, 5, "M5 (Med. Der)", self.trim_m5)
        self.crear_slider_trim(col_m_der, 6, "M6 (Tras. Der)", self.trim_m6)

        frm_md = ttk.Frame(col_m_der, style="Card.TFrame")
        frm_md.pack(fill="x", pady=(2, 0))
        ttk.Label(frm_md, text="Master Der:", style="SubHeader.TLabel").pack(side="left")
        tk.Scale(frm_md, from_=0, to=255, orient="horizontal", variable=self.master_der,
                 bg="#212433", fg="#00f5d4", highlightthickness=0, command=self.sync_master_der, takefocus=0).pack(side="right", fill="x", expand=True)

        # -------------------------------------------------------------------------
        # TARJETA 2 (IZQ): 4 SERVOS DE DIRECCION INDEPENDIENTES (S1, S2, S3, S4)
        # -------------------------------------------------------------------------
        card_servos = ttk.Frame(col_izq, style="Card.TFrame", padding=8)
        card_servos.pack(fill="x", pady=(0, 6))

        lbl_tit_srv = ttk.Label(card_servos, text="DIRECCION INDEPENDIENTE (4 SERVOMOTORES)", style="Header.TLabel")
        lbl_tit_srv.pack(anchor="w", pady=(0, 2))

        grid_servos = ttk.Frame(card_servos, style="Card.TFrame")
        grid_servos.pack(fill="x")
        grid_servos.columnconfigure(0, weight=1, uniform="cols_s")
        grid_servos.columnconfigure(1, weight=1, uniform="cols_s")

        col_s_del = ttk.Frame(grid_servos, style="Card.TFrame")
        col_s_del.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        ttk.Label(col_s_del, text="TREN DELANTERO", style="SubHeader.TLabel").pack(anchor="w")
        self.crear_slider_servo(col_s_del, 1, "S1: Delantero Izq", self.ang_s1)
        self.crear_slider_servo(col_s_del, 2, "S2: Delantero Der", self.ang_s2)

        col_s_tras = ttk.Frame(grid_servos, style="Card.TFrame")
        col_s_tras.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        ttk.Label(col_s_tras, text="TREN TRASERO", style="SubHeader.TLabel").pack(anchor="w")
        self.crear_slider_servo(col_s_tras, 3, "S3: Trasero Izq", self.ang_s3)
        self.crear_slider_servo(col_s_tras, 4, "S4: Trasero Der", self.ang_s4)

        # Botones de Ajuste Rapido de Servos
        frm_btns_srv = ttk.Frame(card_servos, style="Card.TFrame")
        frm_btns_srv.pack(fill="x", pady=(4, 0))

        tk.Button(frm_btns_srv, text="Centrar (90 deg)", bg="#334155", fg="#ffffff", font=("Segoe UI", 8, "bold"),
                  command=self.centrar_todos_los_servos, relief="flat", padx=6, takefocus=0).pack(side="left", padx=(0, 4))

        tk.Button(frm_btns_srv, text="Point Turn", bg="#334155", fg="#00f5d4", font=("Segoe UI", 8, "bold"),
                  command=self.preset_point_turn, relief="flat", padx=6, takefocus=0).pack(side="left", padx=(0, 4))

        tk.Button(frm_btns_srv, text="Cangrejo", bg="#334155", fg="#ff9f1c", font=("Segoe UI", 8, "bold"),
                  command=self.preset_cangrejo, relief="flat", padx=6, takefocus=0).pack(side="left", padx=(0, 4))

        tk.Checkbutton(frm_btns_srv, text="Invertir Servos", variable=self.invertir_servos,
                       bg="#212433", fg="#e2e8f0", selectcolor="#161822", activebackground="#212433",
                       font=("Segoe UI", 8), command=self.al_cambiar_inversion_servos, takefocus=0).pack(side="right", padx=(4, 0))

        tk.Checkbutton(frm_btns_srv, text="Servos 360 deg", variable=self.servos_360,
                       bg="#212433", fg="#00f5d4", selectcolor="#161822", activebackground="#212433",
                       font=("Segoe UI", 8, "bold"), command=self.actualizar_rango_servos, takefocus=0).pack(side="right", padx=(4, 0))

        # -------------------------------------------------------------------------
        # TARJETA 3 (DER ARRIBA): ESQUEMA 2D INTERACTIVO CON ROTACION DE RUEDAS
        # -------------------------------------------------------------------------
        card_esquema = ttk.Frame(col_der, style="Card.TFrame", padding=8)
        card_esquema.pack(fill="x", pady=(0, 6))

        ttk.Label(card_esquema, text="ESQUEMA 2D EN TIEMPO REAL & PILOTAJE", style="Header.TLabel").pack(anchor="w", pady=(0, 2))

        frm_esq_ctrl = ttk.Frame(card_esquema, style="Card.TFrame")
        frm_esq_ctrl.pack(fill="x")

        # Canvas 2D
        self.canvas_rover = tk.Canvas(frm_esq_ctrl, width=200, height=200, bg="#161822", highlightthickness=1,
                                      highlightbackground="#334155")
        self.canvas_rover.pack(side="left", padx=(0, 10))

        # Panel Mandos WASD y Rotacion
        frm_mandos = ttk.Frame(frm_esq_ctrl, style="Card.TFrame")
        frm_mandos.pack(side="left", fill="both", expand=True)

        ttk.Label(frm_mandos, text="Teclado: [W, A, S, D] | [Q, E] Eje | [Espacio] Stop",
                  style="Placeholder.TLabel").pack(anchor="w", pady=(0, 2))

        grid_botones = ttk.Frame(frm_mandos, style="Card.TFrame")
        grid_botones.pack(anchor="center", pady=2)

        self.btn_q = tk.Button(grid_botones, text="Q\n(Eje Izq)", width=7, height=2, bg="#334155", fg="#00f5d4",
                               font=("Segoe UI", 7, "bold"), relief="flat", command=lambda: self.activar_macro("PIVOT_IZQ"), takefocus=0)
        self.btn_q.grid(row=0, column=0, padx=2, pady=2)

        self.btn_w = tk.Button(grid_botones, text="W\n(Adelante)", width=9, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat", takefocus=0)
        self.btn_w.grid(row=0, column=1, padx=2, pady=2)

        self.btn_e = tk.Button(grid_botones, text="E\n(Eje Der)", width=7, height=2, bg="#334155", fg="#00f5d4",
                               font=("Segoe UI", 7, "bold"), relief="flat", command=lambda: self.activar_macro("PIVOT_DER"), takefocus=0)
        self.btn_e.grid(row=0, column=2, padx=2, pady=2)

        self.btn_a = tk.Button(grid_botones, text="A\n(Giro Izq)", width=7, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 7, "bold"), relief="flat", takefocus=0)
        self.btn_a.grid(row=1, column=0, padx=2, pady=2)

        self.btn_stop = tk.Button(grid_botones, text="STOP\n(Espacio)", width=9, height=2, bg="#e63946", fg="#ffffff",
                                  font=("Segoe UI", 8, "bold"), relief="flat", command=self.parar_emergencia, takefocus=0)
        self.btn_stop.grid(row=1, column=1, padx=2, pady=2)

        self.btn_d = tk.Button(grid_botones, text="D\n(Giro Der)", width=7, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 7, "bold"), relief="flat", takefocus=0)
        self.btn_d.grid(row=1, column=2, padx=2, pady=2)

        self.btn_s = tk.Button(grid_botones, text="S\n(Atras)", width=9, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat", takefocus=0)
        self.btn_s.grid(row=2, column=1, padx=2, pady=2)

        # -------------------------------------------------------------------------
        # TARJETA 4 (DER): MONITOR DE TELEMETRIA EN VIVO (SERVOS Y PWM)
        # -------------------------------------------------------------------------
        card_telemetria = ttk.Frame(col_der, style="Card.TFrame", padding=8)
        card_telemetria.pack(fill="x", pady=(0, 6))

        ttk.Label(card_telemetria, text="TELEMETRIA DINAMICA DEL SISTEMA", style="Header.TLabel").pack(anchor="w", pady=(0, 2))

        grid_tele = ttk.Frame(card_telemetria, style="Card.TFrame")
        grid_tele.pack(fill="x")

        ttk.Label(grid_tele, text="Estado Actual:", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w", pady=1)
        self.lbl_val_estado = ttk.Label(grid_tele, text="DETENIDO", style="Value.TLabel", width=12)
        self.lbl_val_estado.grid(row=0, column=1, sticky="w", padx=(4, 10), pady=1)

        ttk.Label(grid_tele, text="Tasa TX (RF):", style="SubHeader.TLabel").grid(row=0, column=2, sticky="w", pady=1)
        self.lbl_val_tasa = ttk.Label(grid_tele, text="0 Hz", style="Value.TLabel", width=8)
        self.lbl_val_tasa.grid(row=0, column=3, sticky="w", padx=4, pady=1)

        ttk.Label(grid_tele, text="PWM Izq Prom:", style="SubHeader.TLabel").grid(row=1, column=0, sticky="w", pady=1)
        self.lbl_val_pwm_izq = ttk.Label(grid_tele, text="0 / 255", style="Value.TLabel", width=12)
        self.lbl_val_pwm_izq.grid(row=1, column=1, sticky="w", padx=(4, 10), pady=1)

        ttk.Label(grid_tele, text="PWM Der Prom:", style="SubHeader.TLabel").grid(row=1, column=2, sticky="w", pady=1)
        self.lbl_val_pwm_der = ttk.Label(grid_tele, text="0 / 255", style="Value.TLabel", width=8)
        self.lbl_val_pwm_der.grid(row=1, column=3, sticky="w", padx=4, pady=1)

        ttk.Label(grid_tele, text="Servos Delanteros:", style="SubHeader.TLabel").grid(row=2, column=0, sticky="w", pady=1)
        self.lbl_val_s_del = ttk.Label(grid_tele, text="S1: 90 deg | S2: 90 deg", style="Value.TLabel", width=22)
        self.lbl_val_s_del.grid(row=2, column=1, sticky="w", padx=(4, 10), pady=1)

        ttk.Label(grid_tele, text="Servos Traseros:", style="SubHeader.TLabel").grid(row=2, column=2, sticky="w", pady=1)
        self.lbl_val_s_tras = ttk.Label(grid_tele, text="S3: 90 deg | S4: 90 deg", style="Value.TLabel", width=22)
        self.lbl_val_s_tras.grid(row=2, column=3, sticky="w", padx=4, pady=1)

        # -------------------------------------------------------------------------
        # TARJETA 5 (IZQ ABAJO): TELEMETRIA JOYSTICK FISICO (OPCIONAL ARDUINO NANO)
        # -------------------------------------------------------------------------
        card_joy = ttk.Frame(col_izq, style="Card.TFrame", padding=6)
        card_joy.pack(fill="x")

        frm_joy_top = ttk.Frame(card_joy, style="Card.TFrame")
        frm_joy_top.pack(fill="x", pady=(0, 2))

        ttk.Label(frm_joy_top, text="JOYSTICK FISICO:", style="Header.TLabel").pack(side="left", padx=(0, 4))

        self.cb_puertos_joy = ttk.Combobox(frm_joy_top, width=8, state="readonly")
        self.cb_puertos_joy.pack(side="left", padx=2)

        self.btn_conectar_joy = tk.Button(frm_joy_top, text="Conectar Joy", bg="#00f5d4", fg="#0f172a",
                                          font=("Segoe UI", 8, "bold"), command=self.toggle_conexion_joy, relief="flat", padx=5, takefocus=0)
        self.btn_conectar_joy.pack(side="left", padx=2)

        self.lbl_badge_joy = tk.Label(frm_joy_top, text="[OFF]", bg="#374151", fg="#f87171",
                                      font=("Segoe UI", 8, "bold"), padx=5, pady=1, width=8)
        self.lbl_badge_joy.pack(side="left", padx=2)

        frm_joy_body = ttk.Frame(card_joy, style="Card.TFrame")
        frm_joy_body.pack(fill="x", pady=1)

        frm_s1 = ttk.Frame(frm_joy_body, style="Card.TFrame")
        frm_s1.pack(side="left", padx=(0, 6))
        ttk.Label(frm_s1, text="STICK 1 (L)", font=("Segoe UI", 7, "bold"), style="SubHeader.TLabel").pack(anchor="center")
        self.canvas_joy_s1 = tk.Canvas(frm_s1, width=54, height=54, bg="#161822", highlightthickness=1, highlightbackground="#334155")
        self.canvas_joy_s1.pack(anchor="center", pady=1)
        self.lbl_joy_s1 = ttk.Label(frm_s1, text="X:0% | Y:0%", font=("Consolas", 7), style="SubHeader.TLabel")
        self.lbl_joy_s1.pack(anchor="center")

        frm_s2 = ttk.Frame(frm_joy_body, style="Card.TFrame")
        frm_s2.pack(side="left", padx=(0, 6))
        ttk.Label(frm_s2, text="STICK 2 (R)", font=("Segoe UI", 7, "bold"), style="SubHeader.TLabel").pack(anchor="center")
        self.canvas_joy_s2 = tk.Canvas(frm_s2, width=54, height=54, bg="#161822", highlightthickness=1, highlightbackground="#334155")
        self.canvas_joy_s2.pack(anchor="center", pady=1)
        self.lbl_joy_s2 = ttk.Label(frm_s2, text="X:0% | Y:0%", font=("Consolas", 7), style="SubHeader.TLabel")
        self.lbl_joy_s2.pack(anchor="center")

        frm_joy_ctrls = ttk.Frame(frm_joy_body, style="Card.TFrame")
        frm_joy_ctrls.pack(side="left", fill="both", expand=True)

        ttk.Label(frm_joy_ctrls, text="POTENCIOMETRO:", font=("Segoe UI", 7, "bold"), style="SubHeader.TLabel").pack(anchor="w")
        self.lbl_joy_pot = ttk.Label(frm_joy_ctrls, text="Pot: 150 / 255 (59%)", style="Value.TLabel")
        self.lbl_joy_pot.pack(anchor="w", pady=(0, 1))

        frm_badges = ttk.Frame(frm_joy_ctrls, style="Card.TFrame")
        frm_badges.pack(anchor="w", fill="x")

        self.badge_btn_modo = tk.Label(frm_badges, text="MODO", bg="#334155", fg="#94a3b8", font=("Segoe UI", 7, "bold"), padx=2, pady=1)
        self.badge_btn_modo.pack(side="left", padx=1)

        self.badge_btn_centrar = tk.Label(frm_badges, text="90 deg", bg="#334155", fg="#94a3b8", font=("Segoe UI", 7, "bold"), padx=2, pady=1)
        self.badge_btn_centrar.pack(side="left", padx=1)

        self.badge_btn_360 = tk.Label(frm_badges, text="360 deg", bg="#334155", fg="#94a3b8", font=("Segoe UI", 7, "bold"), padx=2, pady=1)
        self.badge_btn_360.pack(side="left", padx=1)

        self.badge_btn_q = tk.Label(frm_badges, text="Q", bg="#334155", fg="#94a3b8", font=("Segoe UI", 7, "bold"), padx=2, pady=1)
        self.badge_btn_q.pack(side="left", padx=1)

        self.badge_btn_e = tk.Label(frm_badges, text="E", bg="#334155", fg="#94a3b8", font=("Segoe UI", 7, "bold"), padx=2, pady=1)
        self.badge_btn_e.pack(side="left", padx=1)

        self.badge_btn_estop = tk.Label(frm_badges, text="ESTOP", bg="#334155", fg="#f87171", font=("Segoe UI", 7, "bold"), padx=2, pady=1)
        self.badge_btn_estop.pack(side="left", padx=1)

        self.dibujar_stick_neutro(self.canvas_joy_s1)
        self.dibujar_stick_neutro(self.canvas_joy_s2)

        self.log_consola("SYS", "HMI Rocker-Bogie V2.1-pre iniciada. Perfil: Arduino Nano ESP32.")
        self.actualizar_lista_puertos()

    def al_seleccionar_perfil(self, event=None):
        nombre = self.cb_perfil.get()
        p = self.registry.obtener_perfil(nombre)
        if p:
            self.perfil_activo = p
            self.lbl_badge_hw.config(text=f"[{p.nombre.upper()}]")
            self.log_consola("SYS", f"Perfil activo cambiado a: {p.nombre} (FQBN: {p.fqbn})")

    def al_seleccionar_puerto(self, event=None):
        puerto = self.cb_puertos.get()
        if not SERIAL_DISPONIBLE or not puerto:
            return
        com_list = list(serial.tools.list_ports.comports())
        for p in com_list:
            if p.device == puerto:
                perfil_detectado = self.registry.detectar_perfil(p)
                if perfil_detectado:
                    self.perfil_activo = perfil_detectado
                    self.cb_perfil.set(perfil_detectado.nombre)
                    self.lbl_badge_hw.config(text=f"[{perfil_detectado.nombre.upper()}]")
                    self.log_consola("SYS", f"Autodeteccion pasiva en {puerto}: {perfil_detectado.nombre} (VID:PID {p.vid:04X}:{p.pid:04X})")
                break

    def crear_slider_trim(self, parent, motor_idx, nombre, variable):
        frm = ttk.Frame(parent, style="Card.TFrame")
        frm.pack(fill="x", pady=1)

        lbl = ttk.Label(frm, text=f"{nombre} [100% -> PWM: 150]", style="SubHeader.TLabel")
        lbl.pack(anchor="w")
        self.lbl_trims[motor_idx] = (lbl, nombre)

        def al_mover(val):
            self.actualizar_labels_trim()
            if self.conectado and self.comando_actual != "STOP":
                self.enviar_trama_actual()
            self.redibujar_rover_actual()

        s = tk.Scale(frm, from_=0, to=150, orient="horizontal", variable=variable,
                     bg="#212433", fg="#00f5d4", highlightthickness=0, command=al_mover, takefocus=0)
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
                     bg="#212433", fg="#00f5d4", highlightthickness=0, command=self.al_mover_servo, takefocus=0)
        s.pack(fill="x")
        self.sliders_servos[servo_idx] = (lbl, s, nombre)

    def actualizar_rango_servos(self):
        es_360 = self.servos_360.get()
        desde = 0 if es_360 else 10
        hasta = 360 if es_360 else 170
        rango_str = "0-360 deg" if es_360 else "10-170 deg"

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
            self.redibujar_rover_actual()

        estado_txt = "360 deg (Continuo/Extendido)" if es_360 else "Estandar (10-170 deg Seguro)"
        self.log_consola("SYS", f"Rango de Servos cambiado a: {estado_txt}")

    def get_pwm_motor(self, motor_idx):
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
        if self.conectado and self.comando_actual != "STOP":
            self.enviar_trama_actual()
        self.redibujar_rover_actual()
        self.log_consola("SYS", "Trims de los 6 motores restablecidos al 100% (Ratio 1.0x).")

    def cambiar_modo_conduccion(self, event=None):
        modo = self.modo_conduccion.get()
        self.log_consola("SYS", f"Modo de conduccion cambiado a: {modo}")
        if modo == "POINT_TURN":
            self.preset_point_turn()
        elif modo == "CRAB":
            self.preset_cangrejo()
        elif modo == "ACKERMANN":
            self.centrar_todos_los_servos()

    def centrar_todos_los_servos(self):
        self.ang_s1.set(90); self.ang_s2.set(90); self.ang_s3.set(90); self.ang_s4.set(90)
        self.enviar_trama_actual()
        self.redibujar_rover_actual()
        self.log_consola("SYS", "Servos centrados a 90 deg (Conduccion recta).")

    def calcular_cinematica_inversa(self, vx, vy, omega, L=1.0, W=1.0):
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
            self.redibujar_rover_actual()

    def preset_point_turn(self):
        s1, s2, s3, s4 = self.calcular_cinematica_inversa(0.0, 0.0, -1.0)
        self.ang_s1.set(s1); self.ang_s2.set(s2); self.ang_s3.set(s3); self.ang_s4.set(s4)
        self.enviar_trama_actual()
        self.redibujar_rover_actual()
        self.log_consola("SYS", f"Geometria tangencial configurada para Giro 360 deg: S1={s1} deg, S2={s2} deg, S3={s3} deg, S4={s4} deg.")

    def preset_cangrejo(self):
        if self.servos_360.get():
            s1, s2, s3, s4 = (180, 180, 180, 180) if not self.invertir_servos.get() else (0, 0, 0, 0)
        else:
            s1, s2, s3, s4 = self.calcular_cinematica_inversa(1.0, 1.0, 0.0)

        self.ang_s1.set(s1); self.ang_s2.set(s2); self.ang_s3.set(s3); self.ang_s4.set(s4)
        self.enviar_trama_actual()
        self.redibujar_rover_actual()
        tipo = "Lateral Puro 90 deg" if self.servos_360.get() else "Diagonal 45 deg"
        self.log_consola("SYS", f"Geometria configurada para Modo Cangrejo ({tipo}): S1={s1} deg, S2={s2} deg, S3={s3} deg, S4={s4} deg.")

    def sync_master_izq(self, val):
        self.actualizar_labels_trim()
        if self.conectado and self.comando_actual != "STOP":
            self.enviar_trama_actual()
        self.redibujar_rover_actual()

    def sync_master_der(self, val):
        self.actualizar_labels_trim()
        if self.conectado and self.comando_actual != "STOP":
            self.enviar_trama_actual()
        self.redibujar_rover_actual()

    def al_mover_slider_motor(self, val):
        if self.conectado and self.comando_actual != "STOP":
            self.enviar_trama_actual()
        self.redibujar_rover_actual()

    def al_mover_servo(self, val):
        if getattr(self, '_actualizando_desde_teclas', False):
            return
        self.redibujar_rover_actual()
        if self.conectado and self.comando_actual != "STOP":
            self.enviar_trama_actual()

    def calcular_pwms_actuales(self):
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

    def redibujar_rover_actual(self):
        pwms = self.calcular_pwms_actuales()
        self.dibujar_esquema_rover(self.comando_actual,
                                   self.ang_s1.get(), self.ang_s2.get(),
                                   self.ang_s3.get(), self.ang_s4.get(),
                                   pwms)

    def dibujar_esquema_rover(self, cmd, s1, s2, s3, s4, pwms=None):
        if not hasattr(self, 'canvas_rover') or self.canvas_rover is None:
            return

        c = self.canvas_rover
        c.delete("all")
        w, h = 200, 200
        cx, cy = w // 2, h // 2

        # Chasis central Rocker-Bogie
        c.create_rectangle(cx - 30, cy - 45, cx + 30, cy + 45, fill="#1e293b", outline="#00f5d4", width=2)
        c.create_text(cx, cy, text="ROCKER\nBOGIE", fill="#00f5d4", font=("Segoe UI", 7, "bold"), justify="center")

        pos_ruedas = [
            (cx - 48, cy - 42, s1, "M1"),
            (cx + 48, cy - 42, s2, "M4"),
            (cx - 48, cy,      90, "M2"),
            (cx + 48, cy,      90, "M5"),
            (cx - 48, cy + 42, s3, "M3"),
            (cx + 48, cy + 42, s4, "M6"),
        ]

        if pwms is None:
            pwms = [0] * 6

        for i, (rx, ry, ang, label) in enumerate(pos_ruedas):
            pwm = pwms[i] if i < len(pwms) else 0
            color = "#38b000" if pwm > 0 else ("#ff9f1c" if pwm < 0 else "#64748b")
            self.dibujar_rueda_orientada(c, rx, ry, ang, color, label, pwm)

    def dibujar_rueda_orientada(self, c, x, y, angulo_deg, color, etiqueta, pwm):
        ancho, alto = 12, 22
        # Angulo de deflexion respecto al avance recto (90 deg)
        delta_deg = 90.0 - angulo_deg
        theta = math.radians(delta_deg)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        hw = ancho / 2.0
        hh = alto / 2.0

        puntos_locales = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        puntos_canvas = []
        for lx, ly in puntos_locales:
            rx = x + lx * cos_t - ly * sin_t
            ry = y + lx * sin_t + ly * cos_t
            puntos_canvas.extend([rx, ry])

        c.create_polygon(puntos_canvas, fill=color, outline="#ffffff", width=1)
        c.create_text(x, y, text=etiqueta, fill="#ffffff", font=("Segoe UI", 6, "bold"))

        if pwm != 0:
            longitud_vector = 14
            signo = 1.0 if pwm > 0 else -1.0
            vx = -signo * sin_t * longitud_vector
            vy = -signo * cos_t * longitud_vector
            c.create_line(x, y, x + vx, y + vy, fill="#ffff00", width=2, arrow=tk.LAST)

    def actualizar_lista_puertos(self):
        if not SERIAL_DISPONIBLE:
            self.cb_puertos['values'] = ["Sin pyserial"]
            self.cb_puertos.set("Sin pyserial")
            if hasattr(self, 'cb_puertos_joy'):
                self.cb_puertos_joy['values'] = ["Sin pyserial"]
                self.cb_puertos_joy.set("Sin pyserial")
            return

        com_list = list(serial.tools.list_ports.comports())
        puertos = [p.device for p in com_list]
        if puertos:
            self.cb_puertos['values'] = puertos
            if hasattr(self, 'cb_puertos_joy'):
                self.cb_puertos_joy['values'] = puertos

            puerto_preferido = None
            for p in com_list:
                perfil_detectado = self.registry.detectar_perfil(p)
                if perfil_detectado:
                    puerto_preferido = p.device
                    self.perfil_activo = perfil_detectado
                    self.cb_perfil.set(perfil_detectado.nombre)
                    self.lbl_badge_hw.config(text=f"[{perfil_detectado.nombre.upper()}]")
                    break

            if not self.cb_puertos.get() or self.cb_puertos.get() not in puertos:
                self.cb_puertos.set(puerto_preferido if puerto_preferido else puertos[0])

            if hasattr(self, 'cb_puertos_joy'):
                if not self.cb_puertos_joy.get() or self.cb_puertos_joy.get() not in puertos:
                    otros = [pt for pt in puertos if pt != self.cb_puertos.get()]
                    self.cb_puertos_joy.set(otros[0] if otros else puertos[0])

            self.log_consola("SYS", f"Puertos escaneados: {', '.join(puertos)} | Seleccionado: {self.cb_puertos.get()}")
        else:
            self.cb_puertos['values'] = ["Sin puertos"]
            self.cb_puertos.set("Sin puertos")
            if hasattr(self, 'cb_puertos_joy'):
                self.cb_puertos_joy['values'] = ["Sin puertos"]
                self.cb_puertos_joy.set("Sin puertos")

    def toggle_conexion(self):
        if not SERIAL_DISPONIBLE:
            if messagebox:
                messagebox.showerror("Error", "Libreria pyserial no instalada.")
            return

        if self.conectado:
            self.desconectar()
        else:
            puerto = self.cb_puertos.get()
            if not puerto or puerto == "Sin puertos":
                if messagebox:
                    messagebox.showwarning("Atencion", "Seleccione un puerto COM valido.")
                return

            baud = int(self.cb_baud.get())
            try:
                self.serial_conn = serial.Serial()
                self.serial_conn.port = puerto
                self.serial_conn.baudrate = baud
                self.serial_conn.timeout = 0.1
                self.serial_conn.rts = False
                self.serial_conn.dtr = False
                self.serial_conn.open()
                time.sleep(0.15)
                self.serial_conn.dtr = True
                self.conectado = True
                self.btn_conectar.config(text="DESCONECTAR", bg="#e63946", fg="#ffffff")
                self.lbl_estado_badge.config(text="[CONECTADO]", bg="#064e3b", fg="#34d399")
                self.log_consola("SYS", f"Conexion exitosa en {puerto} a {baud} baud.")
                self.ident_o_ping()
            except Exception as e:
                self.conectado = False
                if messagebox:
                    messagebox.showerror("Error de Conexion", f"No se pudo abrir {puerto}:\n{e}")
                self.log_consola("ERR", f"Error al abrir {puerto}: {e}")

    def desconectar(self):
        self.conectado = False
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.btn_conectar.config(text="CONECTAR", bg="#00f5d4", fg="#0f172a")
        self.lbl_estado_badge.config(text="[DESCONECTADO]", bg="#374151", fg="#f87171")
        self.log_consola("SYS", "Puerto serial desconectado.")

    def ident_o_ping(self):
        if not self.conectado or not self.serial_conn or not self.serial_conn.is_open:
            self.log_consola("WARN", "No conectado para enviar IDENT/PING.")
            return
        try:
            self.serial_conn.write(b"IDENT\n")
            self.log_consola("TX", "[TX IDENT -> MCU]: Solicitando identificacion de firmware...")
        except Exception as e:
            self.log_consola("ERR", f"Error enviando IDENT: {e}")

    def enviar_trama_actual(self):
        cmd = self.comando_actual.upper()
        if cmd == " ":
            cmd = "STOP"

        avg_izq = int((self.get_pwm_motor(1) + self.get_pwm_motor(2) + self.get_pwm_motor(3)) / 3)
        avg_der = int((self.get_pwm_motor(4) + self.get_pwm_motor(5) + self.get_pwm_motor(6)) / 3)

        if cmd == "STOP":
            pot_izq = 0
            pot_der = 0
            s1 = 90; s2 = 90; s3 = 90; s4 = 90
        elif cmd == "W":
            pot_izq = avg_izq; pot_der = avg_der
            s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()
        elif cmd == "S":
            pot_izq = -avg_izq; pot_der = -avg_der
            s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()
        elif cmd == "PIVOT_IZQ":
            pot_izq = -avg_izq; pot_der = avg_der
            s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()
        elif cmd == "PIVOT_DER":
            pot_izq = avg_izq; pot_der = -avg_der
            s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()
        else:
            pot_izq = avg_izq; pot_der = avg_der
            s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()

        self.snapshot['cmd'] = cmd
        self.snapshot['izq'] = pot_izq
        self.snapshot['der'] = pot_der
        self.snapshot['s1'] = s1
        self.snapshot['s2'] = s2
        self.snapshot['s3'] = s3
        self.snapshot['s4'] = s4

        if not self.conectado or not self.serial_conn or not self.serial_conn.is_open:
            return

        trama = f"{cmd},{abs(pot_izq)},{abs(pot_der)},{s1},{s2},{s3},{s4}\n"
        raw_bytes = trama.encode('ascii')

        try:
            self.serial_conn.write(raw_bytes)
            self.paquetes_tx_contador += 1
        except Exception as e:
            self.log_consola("ERR", f"Error TX: {e}")

    def sincronizar_calibracion(self):
        if not self.conectado or not self.serial_conn or not self.serial_conn.is_open:
            if messagebox:
                messagebox.showwarning("Atencion", "Conecte el puerto serie antes de sincronizar calibracion.")
            return

        trims = {i: getattr(self, f"trim_m{i}").get() for i in range(1, 7)}
        servos = {i: getattr(self, f"ang_s{i}").get() for i in range(1, 5)}
        trama_calib = formatear_trama_calibracion(trims, servos)

        try:
            self.serial_conn.write(trama_calib.encode('ascii'))
            self.serial_conn.write(b"PERSIST_NVS\n")
            self.log_consola("TX", f"[CALIB]: {trama_calib.strip()} -> Guardado en NVS.")
            if messagebox:
                messagebox.showinfo("Exito", "Calibracion sincronizada y persistida en memoria no volatil (NVS).")
        except Exception as e:
            self.log_consola("ERR", f"Error enviando calibracion: {e}")

    def iniciar_flasheo(self):
        if self.flasheando:
            if messagebox:
                messagebox.showwarning("Atencion", "Flasheo en curso. Espere a que finalice.")
            return

        puerto = self.cb_puertos.get()
        if not puerto or puerto == "Sin puertos":
            if messagebox:
                messagebox.showwarning("Atencion", "Seleccione un puerto COM para flashear.")
            return

        perfil = self.perfil_activo
        self.flasheando = True
        self.btn_flash.config(text="FLASHEANDO...", bg="#d97706")
        self.log_consola("SYS", f"Iniciando flasheo para {perfil.nombre} en {puerto}...")

        def _worker():
            estaba_conectado = self.conectado
            if estaba_conectado:
                self.desconectar()
                time.sleep(0.3)

            ok = self.flasher.flashear(
                puerto=puerto,
                perfil=perfil,
                rol="TX",
                callback_log=lambda msg: self.log_consola("SYS", f"[FLASHER]: {msg}")
            )

            self.flasheando = False
            self.btn_flash.config(text="FLASHEAR", bg="#4338ca")
            if ok:
                self.log_consola("SYS", f"Flasheo completado con exito en {puerto}.")
                if messagebox:
                    messagebox.showinfo("Flasheo", f"Firmware cargado exitosamente en {perfil.nombre}.")
            else:
                self.log_consola("ERR", f"Fallo al flashear en {puerto}.")
                if messagebox:
                    messagebox.showerror("Error Flasheo", f"No se pudo flashear el microcontrolador en {puerto}.")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    # =========================================================================
    # BUCLES DE SEGUNDO PLANO Y TELEMETRIA
    # =========================================================================
    def iniciar_hilos_segundo_plano(self):
        self.hilo_serial = threading.Thread(target=self.bucle_recepcion_serial, daemon=True)
        self.hilo_serial.start()
        self.hilo_joy = threading.Thread(target=self.bucle_recepcion_joy, daemon=True)
        self.hilo_joy.start()

    def bucle_recepcion_serial(self):
        while self.ejecutando:
            if self.conectado and self.serial_conn and self.serial_conn.is_open:
                try:
                    if self.serial_conn.in_waiting:
                        linea = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                        if linea:
                            self.procesar_linea_serial(linea)
                except Exception:
                    pass
            time.sleep(0.01)

    def procesar_linea_serial(self, linea):
        if linea.startswith("ID:") or linea.startswith("PONG:"):
            parsed = parsear_handshake(linea)
            if parsed:
                modelo, rol, ver = parsed
                self.log_consola("MCU", f"[HANDSHAKE CONFIRMADO]: Modelo={modelo} | Rol={rol} | Ver={ver}")
                p = self.registry.obtener_perfil(modelo)
                if p:
                    self.perfil_activo = p
                    self.cb_perfil.set(p.nombre)
                    self.lbl_badge_hw.config(text=f"[{p.nombre.upper()}]")
            else:
                self.log_consola("MCU", f"[RESPUESTA]: {linea}")
        else:
            self.log_consola("MCU", linea)

    def bucle_recepcion_joy(self):
        while self.ejecutando:
            if self.conectado_joy and self.serial_joy and self.serial_joy.is_open:
                try:
                    if self.serial_joy.in_waiting:
                        linea = self.serial_joy.readline().decode('utf-8', errors='ignore').strip()
                        if linea.startswith("JOY,"):
                            self.procesar_telemetria_joy(linea)
                except Exception:
                    pass
            time.sleep(0.01)

    def procesar_telemetria_joy(self, linea):
        partes = linea.split(",")
        if len(partes) >= 11:
            try:
                self.joy_data['s1_x'] = int(partes[1])
                self.joy_data['s1_y'] = int(partes[2])
                self.joy_data['s2_x'] = int(partes[3])
                self.joy_data['s2_y'] = int(partes[4])
                self.joy_data['pot']  = int(partes[5])
                self.joy_data['sw1']  = int(partes[6])
                self.joy_data['sw2']  = int(partes[7])
                self.joy_data['estop']= int(partes[8])
                self.joy_data['s360'] = int(partes[9])
                self.joy_data['q']    = int(partes[10])
                self.joy_data['e']    = int(partes[11]) if len(partes) > 11 else 0

                self.master_izq.set(self.joy_data['pot'])
                self.master_der.set(self.joy_data['pot'])

                if self.joy_data['estop'] == 1 and self.ultimo_joy_estop == 0:
                    self.parar_emergencia()
                self.ultimo_joy_estop = self.joy_data['estop']

                if self.joy_data['s360'] == 1 and self.ultimo_joy_360 == 0:
                    self.servos_360.set(not self.servos_360.get())
                    self.actualizar_rango_servos()
                self.ultimo_joy_360 = self.joy_data['s360']
            except ValueError:
                pass

    def toggle_conexion_joy(self):
        if not SERIAL_DISPONIBLE:
            return
        if self.conectado_joy:
            self.conectado_joy = False
            if self.serial_joy and self.serial_joy.is_open:
                try:
                    self.serial_joy.close()
                except Exception:
                    pass
            self.btn_conectar_joy.config(text="Conectar Joy", bg="#00f5d4", fg="#0f172a")
            self.lbl_badge_joy.config(text="[OFF]", bg="#374151", fg="#f87171")
            self.log_consola("SYS", "Mando Joystick desconectado.")
        else:
            puerto = self.cb_puertos_joy.get()
            if not puerto or puerto == "Sin puertos":
                return
            try:
                self.serial_joy = serial.Serial(puerto, 115200, timeout=0.1)
                self.conectado_joy = True
                self.btn_conectar_joy.config(text="Desconectar", bg="#e63946", fg="#ffffff")
                self.lbl_badge_joy.config(text="[ON]", bg="#064e3b", fg="#34d399")
                self.log_consola("SYS", f"Mando Joystick conectado en {puerto}.")
            except Exception as e:
                self.conectado_joy = False
                self.log_consola("ERR", f"Error al abrir Joystick en {puerto}: {e}")

    def dibujar_stick_neutro(self, canvas):
        canvas.delete("all")
        w, h = 54, 54
        cx, cy = w // 2, h // 2
        canvas.create_oval(cx - 22, cy - 22, cx + 22, cy + 22, outline="#334155", width=1)
        canvas.create_line(cx - 22, cy, cx + 22, cy, fill="#1e293b")
        canvas.create_line(cx, cy - 22, cx, cy + 22, fill="#1e293b")
        canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill="#00f5d4", outline="#ffffff")

    def actualizar_telemetria_ui(self):
        ahora = time.time()
        dt = ahora - self.ultimo_tiempo_tasa
        if dt >= 1.0:
            self.tasa_tx_hz = int(round(self.paquetes_tx_contador / dt))
            self.paquetes_tx_contador = 0
            self.ultimo_tiempo_tasa = ahora
            self.lbl_val_tasa.config(text=f"{self.tasa_tx_hz} Hz")

        cmd = self.snapshot['cmd']
        self.lbl_val_estado.config(text=cmd)

        pwms = self.calcular_pwms_actuales()
        p_izq = int(abs(pwms[0] + pwms[1] + pwms[2]) / 3)
        p_der = int(abs(pwms[3] + pwms[4] + pwms[5]) / 3)
        self.lbl_val_pwm_izq.config(text=f"{p_izq} / 255")
        self.lbl_val_pwm_der.config(text=f"{p_der} / 255")

        s1 = self.ang_s1.get(); s2 = self.ang_s2.get()
        s3 = self.ang_s3.get(); s4 = self.ang_s4.get()
        self.lbl_val_s_del.config(text=f"S1: {s1} deg | S2: {s2} deg")
        self.lbl_val_s_tras.config(text=f"S3: {s3} deg | S4: {s4} deg")

        self.root.after(100, self.actualizar_telemetria_ui)

    # =========================================================================
    # EVENTOS DE TECLADO Y NAVEGACION
    # =========================================================================
    def evento_key_press(self, event):
        k = event.keysym.lower()
        if k in self.teclas_presionadas:
            if not self.teclas_presionadas[k]:
                self.teclas_presionadas[k] = True
                self.evaluar_movimiento()
            return "break"

    def evento_key_release(self, event):
        k = event.keysym.lower()
        if k in self.teclas_presionadas:
            self.teclas_presionadas[k] = False
            self.evaluar_movimiento()
            return "break"

    def parar_emergencia(self):
        for k in self.teclas_presionadas:
            self.teclas_presionadas[k] = False
        self.comando_actual = "STOP"
        self.enviar_trama_actual()
        self.actualizar_botones_ui("STOP")
        self.redibujar_rover_actual()

    def activar_macro(self, tipo):
        if tipo == "PIVOT_IZQ":
            self.preset_point_turn()
            self.comando_actual = "PIVOT_IZQ"
        elif tipo == "PIVOT_DER":
            self.preset_point_turn()
            self.comando_actual = "PIVOT_DER"
        self.enviar_trama_actual()
        self.actualizar_botones_ui(self.comando_actual)
        self.redibujar_rover_actual()

    def evaluar_movimiento(self):
        self._actualizando_desde_teclas = True
        try:
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
                self.redibujar_rover_actual()
        finally:
            self._actualizando_desde_teclas = False

    def actualizar_botones_ui(self, cmd):
        c_off, c_on = "#334155", "#00f5d4"
        fg_off, fg_on = "#ffffff", "#0c0e17"
        self.btn_w.config(bg=c_on if cmd == "W" else c_off, fg=fg_on if cmd == "W" else fg_off)
        self.btn_s.config(bg=c_on if cmd == "S" else c_off, fg=fg_on if cmd == "S" else fg_off)
        self.btn_a.config(bg=c_on if cmd == "A" else c_off, fg=fg_on if cmd == "A" else fg_off)
        self.btn_d.config(bg=c_on if cmd == "D" else c_off, fg=fg_on if cmd == "D" else fg_off)
        self.btn_q.config(bg=c_on if cmd == "PIVOT_IZQ" else c_off, fg=fg_on if cmd == "PIVOT_IZQ" else "#00f5d4")
        self.btn_e.config(bg=c_on if cmd == "PIVOT_DER" else c_off, fg=fg_on if cmd == "PIVOT_DER" else "#00f5d4")

    def log_consola(self, tag, texto):
        t_str = time.strftime("[%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}] "
        tag_map = {
            "TX": "TAG_TX",
            "MCU": "TAG_MCU",
            "WARN": "TAG_WARN",
            "ERR": "TAG_ERR",
            "SYS": "TAG_SYS"
        }
        style = tag_map.get(tag, "TAG_SYS")
        if hasattr(self, 'txt_consola') and self.txt_consola is not None:
            try:
                self.txt_consola.insert("end", t_str, "TAG_SYS")
                self.txt_consola.insert("end", str(texto) + "\n", style)
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
        if filedialog:
            ruta = filedialog.asksaveasfilename(defaultextension=".log",
                                                filetypes=[("Log", "*.log"), ("Texto", "*.txt")],
                                                initialfile=f"log_rover_v2_1_{time.strftime('%Y%m%d_%H%M%S')}.log")
            if ruta:
                try:
                    with open(ruta, "w", encoding="utf-8") as f:
                        f.write(contenido)
                    if messagebox:
                        messagebox.showinfo("Exito", f"Log guardado en:\n{ruta}")
                except Exception as e:
                    if messagebox:
                        messagebox.showerror("Error", f"Error guardando:\n{e}")


def main():
    if not TKINTER_DISPONIBLE:
        print("Error: Tkinter no esta disponible en este entorno.")
        sys.exit(1)
    root = tk.Tk()
    app = HMIRoverRockerBogieV21Pre(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (setattr(app, 'ejecutando', False), app.desconectar(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
