#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================================
 HMI ROVER LUNAR V2.0 — ROCKER-BOGIE 6x6 (4 SERVOS DE DIRECCIÓN INDEPENDIENTES)
=====================================================================================
 Configuración Cinemática Rocker-Bogie:
  - 6 Motores de tracción:
      Lado Izq: M1 (Delantero), M2 (Medio - Fijo), M3 (Trasero)
      Lado Der: M4 (Delantero), M5 (Medio - Fijo), M6 (Trasero)
  - 4 Servos de dirección independientes:
      S1: Delantero Izquierdo (Front-Left)
      S2: Delantero Derecho   (Front-Right)
      S3: Trasero Izquierdo   (Rear-Left)
      S4: Trasero Derecho     (Rear-Right)

 Modos de Conducción Soportados:
  1. Modo Estándar / Ackermann (WASD): Delanteros y traseros giran coordinados.
  2. Giro sobre su propio eje (Point Turn / 360°): Las 4 esquinas se orientan tangenciales
     al círculo y los motores giran en sentido inverso para rotar en el lugar.
  3. Modo Cangrejo (Crab Drive): Las 4 ruedas giran en paralelo para avanzar en diagonal.
  4. Modo Calibración Manual: 4 sliders individuales para regular S1, S2, S3 y S4 en tiempo real.
=====================================================================================
"""

import sys
import time
import math
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# Soporte para pyserial
try:
    import serial
    import serial.tools.list_ports
    SERIAL_DISPONIBLE = True
except ImportError:
    SERIAL_DISPONIBLE = False


class HMIRoverRockerBogie:
    def __init__(self, root):
        self.root = root
        self.root.title("HMI Rover Lunar V2.0 — Rocker-Bogie 6x6 (4 Servos Independientes)")
        self.root.geometry("1160x820")
        self.root.minsize(1050, 750)
        self.root.configure(bg="#161822")

        # Variables de comunicación Serial
        self.serial_conn = None
        self.conectado = False
        self.hilo_serial = None
        self.ejecutando = True

        # Estado dinámico de control
        self.comando_actual = " "
        self.modo_conduccion = tk.StringVar(value="ACKERMANN") # ACKERMANN, POINT_TURN, CRAB, MANUAL
        self.teclas_presionadas = {'w': False, 'a': False, 's': False, 'd': False, 'q': False, 'e': False, 'space': False}
        self.paquetes_tx_contador = 0
        self.tasa_tx_hz = 0
        self.ultimo_tiempo_tasa = time.time()

        # Variables de Trim porcentual (Ratio 0% a 150%, 100% = 1.0x directo de Master)
        self.trim_m1 = tk.IntVar(value=100) # Delantero Izq
        self.trim_m2 = tk.IntVar(value=100) # Medio Izq (Fijo)
        self.trim_m3 = tk.IntVar(value=100) # Trasero Izq
        self.trim_m4 = tk.IntVar(value=100) # Delantero Der
        self.trim_m5 = tk.IntVar(value=100) # Medio Der (Fijo)
        self.trim_m6 = tk.IntVar(value=100) # Trasero Der
        self.lbl_trims = {}

        # Masters de Tracción por Lado (0 a 255)
        self.master_izq = tk.IntVar(value=150)
        self.master_der = tk.IntVar(value=150)

        # Variables de Ángulo para los 4 Servomotores Independientes (10° a 170°, 90° = Centro)
        self.ang_s1 = tk.IntVar(value=90) # Delantero Izq
        self.ang_s2 = tk.IntVar(value=90) # Delantero Der
        self.ang_s3 = tk.IntVar(value=90) # Trasero Izq
        self.ang_s4 = tk.IntVar(value=90) # Trasero Der

        # Inversión de sentido de servos (para adaptarse a montajes mecánicos invertidos)
        self.invertir_servos = tk.BooleanVar(value=False)

        # Configurar Estilos Visuales
        self.configurar_estilos()

        # Construir Interfaz Gráfica
        self.crear_widgets()
        self.actualizar_labels_trim()
        self.redibujar_rover_actual()

        # Enlazar eventos de Teclado
        self.root.bind("<KeyPress>", self.evento_key_press)
        self.root.bind("<KeyRelease>", self.evento_key_release)

        # Iniciar hilos y actualización periódica
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
        estilo.configure("Placeholder.TLabel", background="#212433", foreground="#94a3b8", font=("Consolas", 9))

    def crear_widgets(self):
        # =========================================================================
        # 1. BARRA SUPERIOR: CONEXIÓN COM & ESTADO GENERAL
        # =========================================================================
        top_frame = ttk.Frame(self.root, style="Card.TFrame", padding=(15, 8))
        top_frame.pack(fill="x", padx=15, pady=(12, 8))

        lbl_titulo = tk.Label(top_frame, text="🛰️ ROVER LUNAR CEPIT — ROCKER-BOGIE 4-SERVO HMI",
                              font=("Segoe UI", 13, "bold"), bg="#212433", fg="#ffffff")
        lbl_titulo.pack(side="left", padx=(0, 15))

        # Selector de Puerto COM
        lbl_puerto = tk.Label(top_frame, text="Puerto:", bg="#212433", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
        lbl_puerto.pack(side="left", padx=(10, 4))

        self.cb_puertos = ttk.Combobox(top_frame, width=11, state="readonly")
        self.cb_puertos.pack(side="left", padx=4)
        self.actualizar_lista_puertos()

        btn_refrescar = tk.Button(top_frame, text="🔄", bg="#334155", fg="#ffffff", font=("Segoe UI", 8, "bold"),
                                  command=self.actualizar_lista_puertos, relief="flat", padx=6, pady=2)
        btn_refrescar.pack(side="left", padx=4)

        # Baudrate
        lbl_baud = tk.Label(top_frame, text="Baud:", bg="#212433", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
        lbl_baud.pack(side="left", padx=(10, 4))

        self.cb_baud = ttk.Combobox(top_frame, width=8, values=["115200", "57600", "9600"], state="readonly")
        self.cb_baud.set("115200")
        self.cb_baud.pack(side="left", padx=4)

        # Botón Conectar
        self.btn_conectar = tk.Button(top_frame, text="🔌 CONECTAR", bg="#00f5d4", fg="#0f172a",
                                      font=("Segoe UI", 9, "bold"), command=self.toggle_conexion,
                                      relief="flat", padx=12, pady=3, cursor="hand2")
        self.btn_conectar.pack(side="left", padx=12)

        # Selector de Modo de Conducción
        lbl_modo = tk.Label(top_frame, text="Modo:", bg="#212433", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
        lbl_modo.pack(side="left", padx=(10, 4))

        self.cb_modo = ttk.Combobox(top_frame, width=14, textvariable=self.modo_conduccion,
                                    values=["ACKERMANN", "POINT_TURN", "CRAB", "MANUAL"], state="readonly")
        self.cb_modo.pack(side="left", padx=4)
        self.cb_modo.bind("<<ComboboxSelected>>", self.cambiar_modo_conduccion)

        # Indicador de Estado
        self.lbl_estado_badge = tk.Label(top_frame, text="🔴 DESCONECTADO", bg="#374151", fg="#f87171",
                                         font=("Segoe UI", 9, "bold"), padx=8, pady=2)
        self.lbl_estado_badge.pack(side="right", padx=5)

        # =========================================================================
        # 2. CUERPO PRINCIPAL (2 COLUMNAS: IZQUIERDA MOTORES Y SERVOS, DERECHA ESQUEMA)
        # =========================================================================
        main_content = ttk.Frame(self.root, style="Dark.TFrame")
        main_content.pack(fill="both", expand=True, padx=15, pady=4)

        col_izq = ttk.Frame(main_content, style="Dark.TFrame")
        col_izq.pack(side="left", fill="both", expand=True, padx=(0, 6))

        col_der = ttk.Frame(main_content, style="Dark.TFrame")
        col_der.pack(side="right", fill="both", expand=True, padx=(6, 0))

        # -------------------------------------------------------------------------
        # TARJETA 1: TRIMS DE TRACCIÓN (RATIO % MULTIPLICADO POR MASTER)
        # -------------------------------------------------------------------------
        card_motores = ttk.Frame(col_izq, style="Card.TFrame", padding=10)
        card_motores.pack(fill="x", pady=(0, 8))

        frm_tit_mot = ttk.Frame(card_motores, style="Card.TFrame")
        frm_tit_mot.pack(fill="x", pady=(0, 4))
        ttk.Label(frm_tit_mot, text="⚙️ CALIBRACIÓN & TRIMS (RATIO % MULTIPLICADO POR MASTER)", style="Header.TLabel").pack(side="left")
        tk.Button(frm_tit_mot, text="⟲ Reset Trims (100%)", bg="#334155", fg="#00f5d4",
                  font=("Segoe UI", 8, "bold"), relief="flat", padx=6, pady=1, command=self.reset_trims).pack(side="right")

        grid_motores = ttk.Frame(card_motores, style="Card.TFrame")
        grid_motores.pack(fill="x")

        # Columna Izquierda
        col_m_izq = ttk.Frame(grid_motores, style="Card.TFrame")
        col_m_izq.pack(side="left", fill="both", expand=True, padx=(0, 5))
        ttk.Label(col_m_izq, text="LADO IZQUIERDO", style="SubHeader.TLabel").pack(anchor="w")
        self.crear_slider_trim(col_m_izq, 1, "M1 (Delantero Izq)", self.trim_m1)
        self.crear_slider_trim(col_m_izq, 2, "M2 (Medio Izq - Fijo)", self.trim_m2)
        self.crear_slider_trim(col_m_izq, 3, "M3 (Trasero Izq)", self.trim_m3)

        # Master Izquierdo
        frm_mi = ttk.Frame(col_m_izq, style="Card.TFrame")
        frm_mi.pack(fill="x", pady=(4, 0))
        ttk.Label(frm_mi, text="Master Izq:", style="SubHeader.TLabel").pack(side="left")
        tk.Scale(frm_mi, from_=0, to=255, orient="horizontal", variable=self.master_izq,
                 bg="#212433", fg="#00f5d4", highlightthickness=0, command=self.sync_master_izq).pack(side="right", fill="x", expand=True)

        # Columna Derecha
        col_m_der = ttk.Frame(grid_motores, style="Card.TFrame")
        col_m_der.pack(side="right", fill="both", expand=True, padx=(5, 0))
        ttk.Label(col_m_der, text="LADO DERECHO", style="SubHeader.TLabel").pack(anchor="w")
        self.crear_slider_trim(col_m_der, 4, "M4 (Delantero Der)", self.trim_m4)
        self.crear_slider_trim(col_m_der, 5, "M5 (Medio Der - Fijo)", self.trim_m5)
        self.crear_slider_trim(col_m_der, 6, "M6 (Trasero Der)", self.trim_m6)

        # Master Derecho
        frm_md = ttk.Frame(col_m_der, style="Card.TFrame")
        frm_md.pack(fill="x", pady=(4, 0))
        ttk.Label(frm_md, text="Master Der:", style="SubHeader.TLabel").pack(side="left")
        tk.Scale(frm_md, from_=0, to=255, orient="horizontal", variable=self.master_der,
                 bg="#212433", fg="#00f5d4", highlightthickness=0, command=self.sync_master_der).pack(side="right", fill="x", expand=True)

        # -------------------------------------------------------------------------
        # TARJETA 2: 4 SERVOS DE DIRECCIÓN INDEPENDIENTES (S1, S2, S3, S4)
        # -------------------------------------------------------------------------
        card_servos = ttk.Frame(col_izq, style="Card.TFrame", padding=10)
        card_servos.pack(fill="x", pady=(0, 8))

        lbl_tit_srv = ttk.Label(card_servos, text="🎯 DIRECCIÓN INDEPENDIENTE (4 SERVOMOTORES)", style="Header.TLabel")
        lbl_tit_srv.pack(anchor="w", pady=(0, 4))

        grid_servos = ttk.Frame(card_servos, style="Card.TFrame")
        grid_servos.pack(fill="x")

        # Servos Delanteros
        col_s_del = ttk.Frame(grid_servos, style="Card.TFrame")
        col_s_del.pack(side="left", fill="both", expand=True, padx=(0, 5))
        ttk.Label(col_s_del, text="TREN DELANTERO", style="SubHeader.TLabel").pack(anchor="w")
        self.crear_slider(col_s_del, "S1: Delantero Izq (10°-170°)", self.ang_s1, 10, 170, callback=self.al_mover_servo)
        self.crear_slider(col_s_del, "S2: Delantero Der (10°-170°)", self.ang_s2, 10, 170, callback=self.al_mover_servo)

        # Servos Traseros
        col_s_tras = ttk.Frame(grid_servos, style="Card.TFrame")
        col_s_tras.pack(side="right", fill="both", expand=True, padx=(5, 0))
        ttk.Label(col_s_tras, text="TREN TRASERO", style="SubHeader.TLabel").pack(anchor="w")
        self.crear_slider(col_s_tras, "S3: Trasero Izq (10°-170°)", self.ang_s3, 10, 170, callback=self.al_mover_servo)
        self.crear_slider(col_s_tras, "S4: Trasero Der (10°-170°)", self.ang_s4, 10, 170, callback=self.al_mover_servo)

        # Botones de Ajuste Rápido de Servos
        frm_btns_srv = ttk.Frame(card_servos, style="Card.TFrame")
        frm_btns_srv.pack(fill="x", pady=(6, 0))

        tk.Button(frm_btns_srv, text="⌖ Centrar Servos (90°)", bg="#334155", fg="#ffffff", font=("Segoe UI", 8, "bold"),
                  command=self.centrar_todos_los_servos, relief="flat", padx=6).pack(side="left", padx=(0, 5))

        tk.Button(frm_btns_srv, text="🔄 Config. Giro Sobre Eje", bg="#334155", fg="#00f5d4", font=("Segoe UI", 8, "bold"),
                  command=self.preset_point_turn, relief="flat", padx=6).pack(side="left", padx=(0, 5))

        tk.Button(frm_btns_srv, text="🦀 Cangrejo (45°)", bg="#334155", fg="#ff9f1c", font=("Segoe UI", 8, "bold"),
                  command=self.preset_cangrejo, relief="flat", padx=6).pack(side="left", padx=(0, 5))

        tk.Checkbutton(frm_btns_srv, text="Invertir Sentido Servos", variable=self.invertir_servos,
                       bg="#212433", fg="#e2e8f0", selectcolor="#161822", activebackground="#212433",
                       font=("Segoe UI", 8), command=self.al_cambiar_inversion_servos).pack(side="right")

        # -------------------------------------------------------------------------
        # TARJETA 3 (DERECHA ARRIBA): ESQUEMA 2D INTERACTIVO CON ROTACIÓN DE RUEDAS
        # -------------------------------------------------------------------------
        card_esquema = ttk.Frame(col_der, style="Card.TFrame", padding=10)
        card_esquema.pack(fill="x", pady=(0, 8))

        ttk.Label(card_esquema, text="🕹️ ESQUEMA 2D EN TIEMPO REAL & MANDOS", style="Header.TLabel").pack(anchor="w", pady=(0, 4))

        frm_esq_ctrl = ttk.Frame(card_esquema, style="Card.TFrame")
        frm_esq_ctrl.pack(fill="x")

        # Canvas 2D
        self.canvas_rover = tk.Canvas(frm_esq_ctrl, width=210, height=210, bg="#161822", highlightthickness=1,
                                      highlightbackground="#334155")
        self.canvas_rover.pack(side="left", padx=(0, 12))

        # Panel Mandos WASD y Rotación
        frm_mandos = ttk.Frame(frm_esq_ctrl, style="Card.TFrame")
        frm_mandos.pack(side="left", fill="both", expand=True)

        ttk.Label(frm_mandos, text="Teclado: [W, A, S, D] | [Q, E] Giros Eje | [Espacio] Stop",
                  style="Placeholder.TLabel").pack(anchor="w", pady=(0, 4))

        grid_botones = ttk.Frame(frm_mandos, style="Card.TFrame")
        grid_botones.pack(anchor="center", pady=2)

        # Fila 0: Q (Giro Eje Izq), W (Adelante), E (Giro Eje Der)
        self.btn_q = tk.Button(grid_botones, text="↺ Q\n(Eje Izq)", width=8, height=2, bg="#334155", fg="#00f5d4",
                               font=("Segoe UI", 7, "bold"), relief="flat", command=lambda: self.activar_macro("PIVOT_IZQ"))
        self.btn_q.grid(row=0, column=0, padx=2, pady=2)

        self.btn_w = tk.Button(grid_botones, text="▲\nW (Adelante)", width=10, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat")
        self.btn_w.grid(row=0, column=1, padx=2, pady=2)

        self.btn_e = tk.Button(grid_botones, text="↻ E\n(Eje Der)", width=8, height=2, bg="#334155", fg="#00f5d4",
                               font=("Segoe UI", 7, "bold"), relief="flat", command=lambda: self.activar_macro("PIVOT_DER"))
        self.btn_e.grid(row=0, column=2, padx=2, pady=2)

        # Fila 1: A (Izq), STOP (Espacio), D (Der)
        self.btn_a = tk.Button(grid_botones, text="◄ A\n(Giro Izq)", width=8, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 7, "bold"), relief="flat")
        self.btn_a.grid(row=1, column=0, padx=2, pady=2)

        self.btn_stop = tk.Button(grid_botones, text="■ STOP\n(Espacio)", width=10, height=2, bg="#e63946", fg="#ffffff",
                                  font=("Segoe UI", 8, "bold"), relief="flat", command=self.parar_emergencia)
        self.btn_stop.grid(row=1, column=1, padx=2, pady=2)

        self.btn_d = tk.Button(grid_botones, text="D ►\n(Giro Der)", width=8, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 7, "bold"), relief="flat")
        self.btn_d.grid(row=1, column=2, padx=2, pady=2)

        # Fila 2: S (Atrás)
        self.btn_s = tk.Button(grid_botones, text="▼\nS (Atrás)", width=10, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat")
        self.btn_s.grid(row=2, column=1, padx=2, pady=2)

        # -------------------------------------------------------------------------
        # TARJETA 4: MONITOR DE TELEMETRÍA EN VIVO (SERVOS Y PWM)
        # -------------------------------------------------------------------------
        card_telemetria = ttk.Frame(col_der, style="Card.TFrame", padding=10)
        card_telemetria.pack(fill="x", pady=(0, 8))

        ttk.Label(card_telemetria, text="📊 TELEMETRÍA DINÁMICA DEL SISTEMA", style="Header.TLabel").pack(anchor="w", pady=(0, 4))

        grid_tele = ttk.Frame(card_telemetria, style="Card.TFrame")
        grid_tele.pack(fill="x")

        # Fila 1
        ttk.Label(grid_tele, text="Estado Actual:", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w", pady=1)
        self.lbl_val_estado = ttk.Label(grid_tele, text="DETENIDO", style="Value.TLabel")
        self.lbl_val_estado.grid(row=0, column=1, sticky="w", padx=(4, 15), pady=1)

        ttk.Label(grid_tele, text="Tasa TX (RF):", style="SubHeader.TLabel").grid(row=0, column=2, sticky="w", pady=1)
        self.lbl_val_tasa = ttk.Label(grid_tele, text="0 Hz", style="Value.TLabel")
        self.lbl_val_tasa.grid(row=0, column=3, sticky="w", padx=4, pady=1)

        # Fila 2 (PWM)
        ttk.Label(grid_tele, text="PWM Izq Prom:", style="SubHeader.TLabel").grid(row=1, column=0, sticky="w", pady=1)
        self.lbl_val_pwm_izq = ttk.Label(grid_tele, text="0 / 255", style="Value.TLabel")
        self.lbl_val_pwm_izq.grid(row=1, column=1, sticky="w", padx=(4, 15), pady=1)

        ttk.Label(grid_tele, text="PWM Der Prom:", style="SubHeader.TLabel").grid(row=1, column=2, sticky="w", pady=1)
        self.lbl_val_pwm_der = ttk.Label(grid_tele, text="0 / 255", style="Value.TLabel")
        self.lbl_val_pwm_der.grid(row=1, column=3, sticky="w", padx=4, pady=1)

        # Fila 3 (Servos S1, S2, S3, S4)
        ttk.Label(grid_tele, text="Servos Delanteros:", style="SubHeader.TLabel").grid(row=2, column=0, sticky="w", pady=1)
        self.lbl_val_s_del = ttk.Label(grid_tele, text="S1: 90° | S2: 90°", style="Value.TLabel")
        self.lbl_val_s_del.grid(row=2, column=1, sticky="w", padx=(4, 15), pady=1)

        ttk.Label(grid_tele, text="Servos Traseros:", style="SubHeader.TLabel").grid(row=2, column=2, sticky="w", pady=1)
        self.lbl_val_s_tras = ttk.Label(grid_tele, text="S3: 90° | S4: 90°", style="Value.TLabel")
        self.lbl_val_s_tras.grid(row=2, column=3, sticky="w", padx=4, pady=1)

        # -------------------------------------------------------------------------
        # TARJETA 5: PLACEHOLDERS PARA FUTUROS SENSORES
        # -------------------------------------------------------------------------
        card_sensores = ttk.Frame(col_izq, style="Card.TFrame", padding=10)
        card_sensores.pack(fill="x")

        ttk.Label(card_sensores, text="🔬 SENSORES Y DIAGNÓSTICO (EXPANSIÓN FUTURA)", style="Header.TLabel").pack(anchor="w", pady=(0, 4))

        grid_sens = ttk.Frame(card_sensores, style="Card.TFrame")
        grid_sens.pack(fill="x")

        ttk.Label(grid_sens, text="🔋 Batería:", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w", pady=1)
        ttk.Label(grid_sens, text="--.- V (-- %)", style="Placeholder.TLabel").grid(row=0, column=1, sticky="w", padx=(4, 15))

        ttk.Label(grid_sens, text="🧭 IMU (Pitch/Roll):", style="SubHeader.TLabel").grid(row=0, column=2, sticky="w", pady=1)
        ttk.Label(grid_sens, text="P: --° | R: --°", style="Placeholder.TLabel").grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(grid_sens, text="📏 Obstáculo Frontal:", style="SubHeader.TLabel").grid(row=1, column=0, sticky="w", pady=1)
        ttk.Label(grid_sens, text="-- cm", style="Placeholder.TLabel").grid(row=1, column=1, sticky="w", padx=(4, 15))

        ttk.Label(grid_sens, text="📡 Radio RF24:", style="SubHeader.TLabel").grid(row=1, column=2, sticky="w", pady=1)
        ttk.Label(grid_sens, text="CH: 108 | 250kbps", style="Placeholder.TLabel").grid(row=1, column=3, sticky="w", padx=4)

        # =========================================================================
        # 3. TERMINAL / CONSOLA INFERIOR DE PROTOCOLO SERIAL
        # =========================================================================
        card_consola = ttk.Frame(self.root, style="Card.TFrame", padding=(15, 6))
        card_consola.pack(fill="x", padx=15, pady=(4, 12))

        frm_tit_cons = ttk.Frame(card_consola, style="Card.TFrame")
        frm_tit_cons.pack(fill="x", pady=(0, 2))

        ttk.Label(frm_tit_cons, text="💻 TERMINAL Y REGISTRO DE COMANDOS", style="Header.TLabel").pack(side="left")

        tk.Button(frm_tit_cons, text="Limpiar", bg="#334155", fg="#ffffff", font=("Segoe UI", 7, "bold"),
                  command=self.limpiar_consola, relief="flat", padx=6).pack(side="right")

        self.txt_consola = tk.Text(card_consola, height=3, bg="#0f111a", fg="#38b000",
                                   font=("Consolas", 9), insertbackground="#ffffff", relief="flat")
        self.txt_consola.pack(fill="x")
        self.log_consola("HMI Rocker-Bogie V2.0 cargado. 6 Motores + 4 Servos independientes listos.")

    def crear_slider(self, parent, nombre, variable, desde, hasta, callback=None):
        frm = ttk.Frame(parent, style="Card.TFrame")
        frm.pack(fill="x", pady=1)

        ttk.Label(frm, text=nombre, style="SubHeader.TLabel").pack(anchor="w")

        cmd_call = callback if callback else self.al_mover_slider_motor
        s = tk.Scale(frm, from_=desde, to=hasta, orient="horizontal", variable=variable,
                     bg="#212433", fg="#00f5d4", highlightthickness=0, command=cmd_call)
        s.pack(fill="x")

    def crear_slider_trim(self, parent, motor_idx, nombre, variable):
        frm = ttk.Frame(parent, style="Card.TFrame")
        frm.pack(fill="x", pady=2)

        lbl = ttk.Label(frm, text=f"{nombre} [100% ➔ PWM: 150]", style="SubHeader.TLabel")
        lbl.pack(anchor="w")
        self.lbl_trims[motor_idx] = (lbl, nombre)

        def al_mover(val):
            self.actualizar_labels_trim()
            if self.conectado and self.comando_actual != " ":
                self.enviar_trama_actual()
            self.redibujar_rover_actual()

        s = tk.Scale(frm, from_=0, to=150, orient="horizontal", variable=variable,
                     bg="#212433", fg="#00f5d4", highlightthickness=0, command=al_mover)
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
                lbl.config(text=f"{nombre} [{trim}% ➔ PWM: {pwm}]")

    def reset_trims(self):
        for i in range(1, 7):
            getattr(self, f"trim_m{i}").set(100)
        self.actualizar_labels_trim()
        if self.conectado and self.comando_actual != " ":
            self.enviar_trama_actual()
        self.redibujar_rover_actual()
        self.log_consola("Trims de los 6 motores restablecidos al 100% (Ratio 1.0x).")

    # =========================================================================
    # PRESETS Y CALIBRACIONES
    # =========================================================================
    def cambiar_modo_conduccion(self, event=None):
        modo = self.modo_conduccion.get()
        self.log_consola(f"Modo de conducción cambiado a: {modo}")
        if modo == "POINT_TURN":
            self.preset_point_turn()
        elif modo == "CRAB":
            self.preset_cangrejo()
        elif modo == "ACKERMANN":
            self.centrar_todos_los_servos()

    def centrar_todos_los_servos(self):
        self.ang_s1.set(90)
        self.ang_s2.set(90)
        self.ang_s3.set(90)
        self.ang_s4.set(90)
        self.enviar_trama_actual()
        self.dibujar_esquema_rover(self.comando_actual, 90, 90, 90, 90)
        self.log_consola("Servos centrados a 90° (Conducción recta).")

    def calcular_cinematica_inversa(self, vx, vy, omega, L=1.0, W=1.0):
        """
        Calcula la cinemática inversa 2D para la plataforma Rocker-Bogie 6x6.
        Determina los ángulos tangenciales exactos de los 4 servos (S1, S2, S3, S4)
        para giro y traslación sin derrape ni arrastre lateral.
        
        Marco de referencia (Cuerpo del Rover):
          +X: Hacia la derecha del vehículo
          +Y: Hacia adelante (longitudinal)
          +omega: Giro antihorario (CCW)
          -omega: Giro horario (CW)
          
        Posición de las esquinas respecto al centro de rotación (0, 0):
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
                
            # Determinar si la rueda opera con tracción longitudinal positiva o reversa
            # En giro sobre su eje horario (omega < 0), lado derecho retrocede (v_iy < 0)
            # En giro sobre su eje antihorario (omega > 0), lado izquierdo retrocede (v_iy < 0)
            trac_reversa = (v_iy < -1e-4) or (abs(v_iy) <= 1e-4 and ((omega < 0 and xi > 0) or (omega > 0 and xi < 0)))
            
            if trac_reversa:
                heading_rad = math.atan2(-v_ix, -v_iy)
            else:
                heading_rad = math.atan2(v_ix, v_iy)
                
            heading_deg = math.degrees(heading_rad)
            # Conversión a ángulo de servo: 90° es recto, <90° gira derecha, >90° gira izquierda
            servo_deg = int(round(90 - heading_deg))
            servo_deg = max(10, min(170, servo_deg))
            angulos[rueda] = servo_deg
            
        if self.invertir_servos.get():
            for k in angulos:
                angulos[k] = 180 - angulos[k]
                
        return angulos['S1'], angulos['S2'], angulos['S3'], angulos['S4']

    def al_cambiar_inversion_servos(self):
        modo = self.modo_conduccion.get()
        if modo == "POINT_TURN" or self.comando_actual in ["PIVOT_IZQ", "PIVOT_DER"]:
            self.preset_point_turn()
        elif modo == "CRAB":
            self.preset_cangrejo()
        elif modo == "ACKERMANN":
            self.evaluar_estado_movimiento()
        else:
            self.redibujar_rover_actual()

    def preset_point_turn(self):
        # Cinemática inversa tangencial al círculo concéntrico centrado en el rover:
        # S1 (Del. Izq) = 45°, S2 (Del. Der) = 135°, S3 (Tras. Izq) = 135°, S4 (Tras. Der) = 45°
        s1, s2, s3, s4 = self.calcular_cinematica_inversa(0.0, 0.0, -1.0)
        self.ang_s1.set(s1)
        self.ang_s2.set(s2)
        self.ang_s3.set(s3)
        self.ang_s4.set(s4)
        self.enviar_trama_actual()
        self.dibujar_esquema_rover("PIVOT", s1, s2, s3, s4)
        self.log_consola(f"Geometría tangencial configurada para Giro 360°: S1={s1}°, S2={s2}°, S3={s3}°, S4={s4}°.")

    def preset_cangrejo(self):
        # Desplazamiento diagonal a 45°
        s1, s2, s3, s4 = self.calcular_cinematica_inversa(1.0, 1.0, 0.0)
        self.ang_s1.set(s1)
        self.ang_s2.set(s2)
        self.ang_s3.set(s3)
        self.ang_s4.set(s4)
        self.enviar_trama_actual()
        self.dibujar_esquema_rover("CRAB", s1, s2, s3, s4)
        self.log_consola(f"Geometría configurada para Modo Cangrejo: S1={s1}°, S2={s2}°, S3={s3}°, S4={s4}°.")

    def sync_master_izq(self, val):
        self.actualizar_labels_trim()
        if self.conectado and self.comando_actual != " ":
            self.enviar_trama_actual()
        self.redibujar_rover_actual()

    def sync_master_der(self, val):
        self.actualizar_labels_trim()
        if self.conectado and self.comando_actual != " ":
            self.enviar_trama_actual()
        self.redibujar_rover_actual()

    def al_mover_slider_motor(self, val):
        if self.conectado and self.comando_actual != " ":
            self.enviar_trama_actual()
        self.redibujar_rover_actual()

    def al_mover_servo(self, val):
        self.redibujar_rover_actual()
        if self.conectado:
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
            return [int(m1 * 0.7), int(m2 * 0.7), int(m3 * 0.7), m4, m5, m6]
        elif cmd == "D":
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

    # =========================================================================
    # COMUNICACIÓN SERIAL & PROTOCOLO EXTENDIDO
    # =========================================================================
    def actualizar_lista_puertos(self):
        if not SERIAL_DISPONIBLE:
            self.cb_puertos['values'] = ["Sin pyserial"]
            self.cb_puertos.set("Sin pyserial")
            return

        puertos = [p.device for p in serial.tools.list_ports.comports()]
        if puertos:
            self.cb_puertos['values'] = puertos
            if self.cb_puertos.get() not in puertos:
                self.cb_puertos.set(puertos[0])
        else:
            self.cb_puertos['values'] = ["Sin puertos"]
            self.cb_puertos.set("Sin puertos")

    def toggle_conexion(self):
        if not SERIAL_DISPONIBLE:
            messagebox.showerror("Error", "Librería pyserial no instalada (pip install pyserial).")
            return

        if self.conectado:
            self.conectado = False
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.close()
                except:
                    pass
            self.btn_conectar.config(text="🔌 CONECTAR", bg="#00f5d4", fg="#0f172a")
            self.lbl_estado_badge.config(text="🔴 DESCONECTADO", bg="#374151", fg="#f87171")
            self.log_consola("Puerto serial desconectado.")
        else:
            puerto = self.cb_puertos.get()
            if not puerto or puerto == "Sin puertos":
                messagebox.showwarning("Atención", "Seleccione un puerto COM válido.")
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
                self.btn_conectar.config(text="❌ DESCONECTAR", bg="#e63946", fg="#ffffff")
                self.lbl_estado_badge.config(text=f"🟢 CONECTADO ({puerto})", bg="#064e3b", fg="#34d399")
                self.log_consola(f"Conexión exitosa en {puerto} a {baud} baudios (DTR=ON, RTS=OFF).")
            except Exception as e:
                self.conectado = False
                messagebox.showerror("Error de Conexión", f"No se pudo abrir {puerto}:\n{e}")
                self.log_consola(f"ERROR: {e}")

    def enviar_trama_actual(self):
        if not self.conectado or not self.serial_conn or not self.serial_conn.is_open:
            return

        # Calcular potencias efectivas aplicando trims
        pot_izq = int((self.get_pwm_motor(1) + self.get_pwm_motor(2) + self.get_pwm_motor(3)) / 3)
        pot_der = int((self.get_pwm_motor(4) + self.get_pwm_motor(5) + self.get_pwm_motor(6)) / 3)

        s1 = self.ang_s1.get()
        s2 = self.ang_s2.get()
        s3 = self.ang_s3.get()
        s4 = self.ang_s4.get()

        cmd = self.comando_actual.strip().upper()
        if not cmd:
            cmd = "STOP"

        # Trama extendida para 4 servos: "CMD,PotIzq,PotDer,S1,S2,S3,S4\n"
        if cmd == "STOP":
            trama = f"STOP,0,0,{s1},{s2},{s3},{s4}\n"
        else:
            trama = f"{cmd},{pot_izq},{pot_der},{s1},{s2},{s3},{s4}\n"

        try:
            self.serial_conn.write(trama.encode('ascii'))
            self.paquetes_tx_contador += 1
        except Exception as e:
            self.log_consola(f"Error TX: {e}")

    def iniciar_hilos_segundo_plano(self):
        self.hilo_serial = threading.Thread(target=self.bucle_recepcion_serial, daemon=True)
        self.hilo_serial.start()

    def bucle_recepcion_serial(self):
        while self.ejecutando:
            if self.conectado and self.serial_conn and self.serial_conn.is_open:
                try:
                    linea = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    if linea:
                        self.root.after(0, self.log_consola, f"RX: {linea}")
                except:
                    pass
            time.sleep(0.02)

    def log_consola(self, texto):
        t_str = time.strftime("[%H:%M:%S] ")
        self.txt_consola.insert("end", t_str + texto + "\n")
        self.txt_consola.see("end")

    def limpiar_consola(self):
        self.txt_consola.delete("1.0", "end")

    # =========================================================================
    # EVENTOS DE TECLADO Y EVALUACIÓN DE MOVIMIENTO
    # =========================================================================
    def evento_key_press(self, event):
        k = event.keysym.lower()
        if k in self.teclas_presionadas:
            if not self.teclas_presionadas[k]:
                self.teclas_presionadas[k] = True
                self.evaluar_estado_movimiento()

    def evento_key_release(self, event):
        k = event.keysym.lower()
        if k in self.teclas_presionadas:
            self.teclas_presionadas[k] = False
            self.evaluar_estado_movimiento()

    def parar_emergencia(self):
        for k in self.teclas_presionadas:
            self.teclas_presionadas[k] = False
        self.comando_actual = " "
        self.enviar_trama_actual()
        self.actualizar_botones_ui("STOP")
        self.dibujar_esquema_rover("STOP", self.ang_s1.get(), self.ang_s2.get(), self.ang_s3.get(), self.ang_s4.get())

    def activar_macro(self, tipo):
        if tipo == "PIVOT_IZQ":
            self.preset_point_turn()
            self.comando_actual = "PIVOT_IZQ"
        elif tipo == "PIVOT_DER":
            self.preset_point_turn()
            self.comando_actual = "PIVOT_DER"
        self.enviar_trama_actual()
        self.actualizar_botones_ui(self.comando_actual)

    def evaluar_estado_movimiento(self):
        modo = self.modo_conduccion.get()
        nuevo_cmd = " "

        if self.teclas_presionadas['space']:
            nuevo_cmd = " "
        elif self.teclas_presionadas['q']:
            self.preset_point_turn()
            nuevo_cmd = "PIVOT_IZQ"
        elif self.teclas_presionadas['e']:
            self.preset_point_turn()
            nuevo_cmd = "PIVOT_DER"
        elif self.teclas_presionadas['w']:
            nuevo_cmd = "W"
            if modo == "ACKERMANN":
                self.ang_s1.set(90); self.ang_s2.set(90); self.ang_s3.set(90); self.ang_s4.set(90)
        elif self.teclas_presionadas['s']:
            nuevo_cmd = "S"
            if modo == "ACKERMANN":
                self.ang_s1.set(90); self.ang_s2.set(90); self.ang_s3.set(90); self.ang_s4.set(90)
        elif self.teclas_presionadas['a']:
            nuevo_cmd = "A"
            if modo == "ACKERMANN":
                if not self.invertir_servos.get():
                    self.ang_s1.set(120); self.ang_s2.set(120); self.ang_s3.set(60); self.ang_s4.set(60)
                else:
                    self.ang_s1.set(60); self.ang_s2.set(60); self.ang_s3.set(120); self.ang_s4.set(120)
            elif modo == "CRAB":
                self.ang_s1.set(135); self.ang_s2.set(135); self.ang_s3.set(135); self.ang_s4.set(135)
        elif self.teclas_presionadas['d']:
            nuevo_cmd = "D"
            if modo == "ACKERMANN":
                if not self.invertir_servos.get():
                    self.ang_s1.set(60); self.ang_s2.set(60); self.ang_s3.set(120); self.ang_s4.set(120)
                else:
                    self.ang_s1.set(120); self.ang_s2.set(120); self.ang_s3.set(60); self.ang_s4.set(60)
            elif modo == "CRAB":
                self.ang_s1.set(45); self.ang_s2.set(45); self.ang_s3.set(45); self.ang_s4.set(45)

        if nuevo_cmd != self.comando_actual:
            self.comando_actual = nuevo_cmd
            self.enviar_trama_actual()
            self.actualizar_botones_ui(nuevo_cmd)
            self.dibujar_esquema_rover(nuevo_cmd, self.ang_s1.get(), self.ang_s2.get(),
                                       self.ang_s3.get(), self.ang_s4.get())

    def actualizar_botones_ui(self, cmd):
        c_off, c_on = "#334155", "#00f5d4"
        fg_off, fg_on = "#ffffff", "#0f172a"

        self.btn_w.config(bg=c_on if cmd == "W" else c_off, fg=fg_on if cmd == "W" else fg_off)
        self.btn_s.config(bg=c_on if cmd == "S" else c_off, fg=fg_on if cmd == "S" else fg_off)
        self.btn_a.config(bg=c_on if cmd == "A" else c_off, fg=fg_on if cmd == "A" else fg_off)
        self.btn_d.config(bg=c_on if cmd == "D" else c_off, fg=fg_on if cmd == "D" else fg_off)
        self.btn_q.config(bg=c_on if cmd == "PIVOT_IZQ" else c_off, fg=fg_on if cmd == "PIVOT_IZQ" else "#00f5d4")
        self.btn_e.config(bg=c_on if cmd == "PIVOT_DER" else c_off, fg=fg_on if cmd == "PIVOT_DER" else "#00f5d4")

    # =========================================================================
    # DIBUJO CINEMÁTICO 2D: ROCKER-BOGIE 6 RUEDAS + 4 SERVOS ROTATORIOS
    # =========================================================================
    def dibujar_rueda_rotada(self, cx, cy, angulo_grados, color, texto, pwm=0):
        # Convierte el ángulo a radianes: 90° es recto, <90° (ej 60°) inclina a la derecha, >90° (ej 120°) inclina a la izquierda
        rad = math.radians(90 - angulo_grados)
        w_half, h_half = 7, 14 # Ancho y alto de la rueda

        # 4 vértices del rectángulo rotado
        vertices = [(-w_half, -h_half), (w_half, -h_half), (w_half, h_half), (-w_half, h_half)]
        puntos_rotados = []
        for vx, vy in vertices:
            rx = cx + (vx * math.cos(rad) - vy * math.sin(rad))
            ry = cy + (vx * math.sin(rad) + vy * math.cos(rad))
            puntos_rotados.extend([rx, ry])

        self.canvas_rover.create_polygon(puntos_rotados, fill=color, outline="#ffffff", width=1)
        self.canvas_rover.create_text(cx, cy, text=texto, fill="#ffffff", font=("Segoe UI", 6, "bold"))

        # Flecha indicadora de dirección y sentido de tracción por rueda
        if pwm != 0:
            arrow_color = "#34d399" if pwm > 0 else "#f97316" # Verde avance, Naranja reversa
            longitud = 10 + int((min(255, abs(pwm)) / 255.0) * 12)
            signo = 1 if pwm > 0 else -1

            ux = math.sin(rad)
            uy = -math.cos(rad)

            x_ini = cx + signo * (h_half * 0.4) * ux
            y_ini = cy + signo * (h_half * 0.4) * uy
            x_fin = cx + signo * (h_half + longitud) * ux
            y_fin = cy + signo * (h_half + longitud) * uy

            self.canvas_rover.create_line(x_ini, y_ini, x_fin, y_fin,
                                          fill=arrow_color, width=2,
                                          arrow=tk.LAST, arrowshape=(8, 10, 4))

    def dibujar_esquema_rover(self, cmd, s1, s2, s3, s4, pwms=None):
        if pwms is None:
            pwms = self.calcular_pwms_actuales()

        c = self.canvas_rover
        c.delete("all")

        cx, cy = 105, 105

        # Chasis Central y Articulaciones Rocker-Bogie
        c.create_rectangle(cx - 32, cy - 58, cx + 32, cy + 58, fill="#2b2d42", outline="#00f5d4", width=2)
        c.create_text(cx, cy, text="ROCKER\nBOGIE\n6x6", fill="#94a3b8", font=("Segoe UI", 7, "bold"), justify="center")

        # Color de ruedas activas
        color_activa = "#38b000" if cmd != " " and cmd != "STOP" else "#64748b"

        # Posiciones fijas de los ejes de las 6 ruedas
        # Esquinas Delanteras (con servos S1 y S2)
        pos_m1 = (cx - 52, cy - 50) # Delantero Izq
        pos_m4 = (cx + 52, cy - 50) # Delantero Der

        # Ruedas Medias (Fijas - Sin servo)
        pos_m2 = (cx - 52, cy)      # Medio Izq
        pos_m5 = (cx + 52, cy)      # Medio Der

        # Esquinas Traseras (con servos S3 y S4)
        pos_m3 = (cx - 52, cy + 50) # Trasero Izq
        pos_m6 = (cx + 52, cy + 50) # Trasero Der

        # 1. Dibujar Ruedas Delanteras Rotadas (S1 y S2) con flechas
        self.dibujar_rueda_rotada(pos_m1[0], pos_m1[1], s1, color_activa, "M1", pwms[0])
        self.dibujar_rueda_rotada(pos_m4[0], pos_m4[1], s2, color_activa, "M4", pwms[3])

        # 2. Dibujar Ruedas Medias Fijas (90° siempre recto) con flechas
        self.dibujar_rueda_rotada(pos_m2[0], pos_m2[1], 90, color_activa, "M2", pwms[1])
        self.dibujar_rueda_rotada(pos_m5[0], pos_m5[1], 90, color_activa, "M5", pwms[4])

        # 3. Dibujar Ruedas Traseras Rotadas (S3 y S4) con flechas
        self.dibujar_rueda_rotada(pos_m3[0], pos_m3[1], s3, color_activa, "M3", pwms[2])
        self.dibujar_rueda_rotada(pos_m6[0], pos_m6[1], s4, color_activa, "M6", pwms[5])

        # 4. Indicador de Vector de Movimiento General Central
        if cmd == "W":
            c.create_line(cx, cy - 15, cx, cy - 50, fill="#00f5d4", width=3, arrow=tk.LAST, arrowshape=(10, 12, 5))
        elif cmd == "S":
            c.create_line(cx, cy + 15, cx, cy + 50, fill="#ff9f1c", width=3, arrow=tk.LAST, arrowshape=(10, 12, 5))
        elif cmd in ["A", "PIVOT_IZQ"]:
            c.create_arc(cx - 30, cy - 30, cx + 30, cy + 30, start=45, extent=180, style=tk.ARC,
                         outline="#00f5d4", width=3)
        elif cmd in ["D", "PIVOT_DER", "PIVOT"]:
            c.create_arc(cx - 30, cy - 30, cx + 30, cy + 30, start=225, extent=180, style=tk.ARC,
                         outline="#00f5d4", width=3)

    def actualizar_telemetria_ui(self):
        t_ahora = time.time()
        dt = t_ahora - self.ultimo_tiempo_tasa
        if dt >= 1.0:
            self.tasa_tx_hz = int(self.paquetes_tx_contador / dt)
            self.paquetes_tx_contador = 0
            self.ultimo_tiempo_tasa = t_ahora
            self.lbl_val_tasa.config(text=f"{self.tasa_tx_hz} Hz")

        estados_map = {
            " ": "DETENIDO (Listo)",
            "W": "AVANZANDO (Recto)",
            "S": "RETROCEDIENDO",
            "A": "CURVA IZQUIERDA",
            "D": "CURVA DERECHA",
            "PIVOT_IZQ": "ROTACIÓN EJE ↺ (360° Izq)",
            "PIVOT_DER": "ROTACIÓN EJE ↻ (360° Der)",
            "CRAB": "MODO CANGREJO"
        }
        self.lbl_val_estado.config(text=estados_map.get(self.comando_actual, self.comando_actual))

        p_izq = int((self.pwm_m1.get() + self.pwm_m2.get() + self.pwm_m3.get()) / 3) if self.comando_actual != " " else 0
        p_der = int((self.pwm_m4.get() + self.pwm_m5.get() + self.pwm_m6.get()) / 3) if self.comando_actual != " " else 0

        self.lbl_val_pwm_izq.config(text=f"{p_izq} / 255")
        self.lbl_val_pwm_der.config(text=f"{p_der} / 255")

        self.lbl_val_s_del.config(text=f"S1: {self.ang_s1.get()}° | S2: {self.ang_s2.get()}°")
        self.lbl_val_s_tras.config(text=f"S3: {self.ang_s3.get()}° | S4: {self.ang_s4.get()}°")

        self.root.after(100, self.actualizar_telemetria_ui)


if __name__ == "__main__":
    ventana_principal = tk.Tk()
    app = HMIRoverRockerBogie(ventana_principal)
    ventana_principal.mainloop()
