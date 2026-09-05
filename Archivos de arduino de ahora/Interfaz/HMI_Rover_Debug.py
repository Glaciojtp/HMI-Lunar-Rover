#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================================
 HMI ROVER LUNAR V2.0 — MODO DEBUG Y TELEMETRIA AVANZADA (ROCKER-BOGIE 6x6)
=====================================================================================
 Funciones de depuración exhaustiva:
  - Registro exacto de lo que se envia al puerto COM (Comando ASCII y Bytes Hex).
  - Captura y visualización en tiempo real de lo que responde el microcontrolador.
  - Tasa de transmisión (Hz), latencia y conteo de paquetes.
  - Monitor detallado de eventos de teclado (Anti Key-Repeat).
  - Exportación de logs de sesión a archivo de texto.
=====================================================================================
"""

import sys
import os
import time
import math
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import serial
    import serial.tools.list_ports
    SERIAL_DISPONIBLE = True
except ImportError:
    SERIAL_DISPONIBLE = False


class HMIRoverDebug:
    def __init__(self, root):
        self.root = root
        self.root.title("🛰️ HMI ROVER LUNAR V2.0 — MODO DEBUG & TELEMETRIA AVANZADA")
        self.root.geometry("1220x840")
        self.root.minsize(1050, 750)
        self.root.configure(bg="#0f111a")

        # Variables Serial
        self.serial_conn = None
        self.conectado = False
        self.hilo_serial = None
        self.ejecutando = True

        # Métricas de depuración
        self.paquetes_tx_contador = 0
        self.paquetes_rx_contador = 0
        self.tasa_tx_hz = 0
        self.ultimo_tiempo_tasa = time.time()
        self.ultimo_cmd_enviado = ""
        self.ultimo_hex_enviado = ""

        # Opciones visuales
        self.mostrar_hex = tk.BooleanVar(value=True)
        self.mostrar_rx = tk.BooleanVar(value=True)
        self.auto_scroll = tk.BooleanVar(value=True)

        # Estado dinámico
        self.comando_actual = " "
        self.modo_conduccion = tk.StringVar(value="ACKERMANN")
        self.teclas_presionadas = {'w': False, 'a': False, 's': False, 'd': False, 'q': False, 'e': False, 'space': False}

        # Motores PWM
        self.pwm_m1 = tk.IntVar(value=150)
        self.pwm_m2 = tk.IntVar(value=150)
        self.pwm_m3 = tk.IntVar(value=150)
        self.pwm_m4 = tk.IntVar(value=150)
        self.pwm_m5 = tk.IntVar(value=150)
        self.pwm_m6 = tk.IntVar(value=150)
        self.master_izq = tk.IntVar(value=150)
        self.master_der = tk.IntVar(value=150)

        # Servos
        self.ang_s1 = tk.IntVar(value=90)
        self.ang_s2 = tk.IntVar(value=90)
        self.ang_s3 = tk.IntVar(value=90)
        self.ang_s4 = tk.IntVar(value=90)
        self.invertir_servos = tk.BooleanVar(value=False)

        self.configurar_estilos()
        self.crear_widgets()

        self.root.bind("<KeyPress>", self.evento_key_press)
        self.root.bind("<KeyRelease>", self.evento_key_release)

        self.iniciar_hilos_segundo_plano()
        self.actualizar_telemetria_ui()

    def configurar_estilos(self):
        estilo = ttk.Style()
        estilo.theme_use('clam')
        estilo.configure("Card.TFrame", background="#1a1d2d", relief="flat")
        estilo.configure("Dark.TFrame", background="#0f111a")
        estilo.configure("Header.TLabel", background="#1a1d2d", foreground="#00f5d4", font=("Segoe UI", 10, "bold"))
        estilo.configure("SubHeader.TLabel", background="#1a1d2d", foreground="#e2e8f0", font=("Segoe UI", 9, "bold"))
        estilo.configure("Value.TLabel", background="#1a1d2d", foreground="#38b000", font=("Consolas", 10, "bold"))
        estilo.configure("ValueWarn.TLabel", background="#1a1d2d", foreground="#ffb703", font=("Consolas", 10, "bold"))

    def crear_widgets(self):
        # 1. BARRA SUPERIOR: CONEXION COM
        top_frame = ttk.Frame(self.root, style="Card.TFrame", padding=(15, 8))
        top_frame.pack(fill="x", padx=15, pady=(10, 6))

        lbl_titulo = tk.Label(top_frame, text="🛰️ ROVER CEPIT — MODO DEBUG Y TELEMETRIA",
                              font=("Segoe UI", 12, "bold"), bg="#1a1d2d", fg="#00f5d4")
        lbl_titulo.pack(side="left", padx=(0, 15))

        lbl_puerto = tk.Label(top_frame, text="Puerto:", bg="#1a1d2d", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
        lbl_puerto.pack(side="left", padx=(5, 3))

        self.cb_puertos = ttk.Combobox(top_frame, width=12, state="readonly")
        self.cb_puertos.pack(side="left", padx=3)
        self.actualizar_lista_puertos()

        btn_refrescar = tk.Button(top_frame, text="🔄", bg="#334155", fg="#ffffff", font=("Segoe UI", 8, "bold"),
                                  command=self.actualizar_lista_puertos, relief="flat", padx=6, pady=2)
        btn_refrescar.pack(side="left", padx=3)

        lbl_baud = tk.Label(top_frame, text="Baud:", bg="#1a1d2d", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
        lbl_baud.pack(side="left", padx=(8, 3))

        self.cb_baud = ttk.Combobox(top_frame, width=8, values=["115200", "57600", "9600"], state="readonly")
        self.cb_baud.set("115200")
        self.cb_baud.pack(side="left", padx=3)

        self.btn_conectar = tk.Button(top_frame, text="🔌 CONECTAR", bg="#00f5d4", fg="#0f172a",
                                      font=("Segoe UI", 9, "bold"), command=self.toggle_conexion,
                                      relief="flat", padx=10, pady=2, cursor="hand2")
        self.btn_conectar.pack(side="left", padx=10)

        lbl_modo = tk.Label(top_frame, text="Modo:", bg="#1a1d2d", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
        lbl_modo.pack(side="left", padx=(8, 3))

        self.cb_modo = ttk.Combobox(top_frame, width=13, textvariable=self.modo_conduccion,
                                    values=["ACKERMANN", "POINT_TURN", "CRAB", "MANUAL"], state="readonly")
        self.cb_modo.pack(side="left", padx=3)
        self.cb_modo.bind("<<ComboboxSelected>>", self.cambiar_modo_conduccion)

        self.lbl_estado_badge = tk.Label(top_frame, text="🔴 DESCONECTADO", bg="#374151", fg="#f87171",
                                         font=("Segoe UI", 9, "bold"), padx=8, pady=2)
        self.lbl_estado_badge.pack(side="right", padx=5)

        # 2. CUERPO PRINCIPAL
        main_content = ttk.Frame(self.root, style="Dark.TFrame")
        main_content.pack(fill="both", expand=True, padx=15, pady=4)

        col_izq = ttk.Frame(main_content, style="Dark.TFrame")
        col_izq.pack(side="left", fill="both", expand=True, padx=(0, 6))

        col_der = ttk.Frame(main_content, style="Dark.TFrame")
        col_der.pack(side="right", fill="both", expand=True, padx=(6, 0))

        # MOTORES
        card_motores = ttk.Frame(col_izq, style="Card.TFrame", padding=8)
        card_motores.pack(fill="x", pady=(0, 6))
        ttk.Label(card_motores, text="⚙️ MOTORES DE TRACCION (PWM 0-255)", style="Header.TLabel").pack(anchor="w", pady=(0, 2))
        grid_m = ttk.Frame(card_motores, style="Card.TFrame")
        grid_m.pack(fill="x")

        col_m_izq = ttk.Frame(grid_m, style="Card.TFrame")
        col_m_izq.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.crear_slider(col_m_izq, "M1 (Del. Izq)", self.pwm_m1, 0, 255)
        self.crear_slider(col_m_izq, "M2 (Med. Izq)", self.pwm_m2, 0, 255)
        self.crear_slider(col_m_izq, "M3 (Tras. Izq)", self.pwm_m3, 0, 255)

        frm_mi = ttk.Frame(col_m_izq, style="Card.TFrame")
        frm_mi.pack(fill="x", pady=2)
        ttk.Label(frm_mi, text="Master Izq:", style="SubHeader.TLabel").pack(side="left")
        tk.Scale(frm_mi, from_=0, to=255, orient="horizontal", variable=self.master_izq,
                 bg="#1a1d2d", fg="#00f5d4", highlightthickness=0, command=self.sync_master_izq).pack(side="right", fill="x", expand=True)

        col_m_der = ttk.Frame(grid_m, style="Card.TFrame")
        col_m_der.pack(side="right", fill="both", expand=True, padx=(4, 0))
        self.crear_slider(col_m_der, "M4 (Del. Der)", self.pwm_m4, 0, 255)
        self.crear_slider(col_m_der, "M5 (Med. Der)", self.pwm_m5, 0, 255)
        self.crear_slider(col_m_der, "M6 (Tras. Der)", self.pwm_m6, 0, 255)

        frm_md = ttk.Frame(col_m_der, style="Card.TFrame")
        frm_md.pack(fill="x", pady=2)
        ttk.Label(frm_md, text="Master Der:", style="SubHeader.TLabel").pack(side="left")
        tk.Scale(frm_md, from_=0, to=255, orient="horizontal", variable=self.master_der,
                 bg="#1a1d2d", fg="#00f5d4", highlightthickness=0, command=self.sync_master_der).pack(side="right", fill="x", expand=True)

        # SERVOS
        card_servos = ttk.Frame(col_izq, style="Card.TFrame", padding=8)
        card_servos.pack(fill="x", pady=(0, 6))
        ttk.Label(card_servos, text="🎯 SERVOS DE DIRECCION (10°-170°)", style="Header.TLabel").pack(anchor="w", pady=(0, 2))
        grid_s = ttk.Frame(card_servos, style="Card.TFrame")
        grid_s.pack(fill="x")

        col_s_del = ttk.Frame(grid_s, style="Card.TFrame")
        col_s_del.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.crear_slider(col_s_del, "S1: Del. Izq", self.ang_s1, 10, 170, callback=self.al_mover_servo)
        self.crear_slider(col_s_del, "S2: Del. Der", self.ang_s2, 10, 170, callback=self.al_mover_servo)

        col_s_tras = ttk.Frame(grid_s, style="Card.TFrame")
        col_s_tras.pack(side="right", fill="both", expand=True, padx=(4, 0))
        self.crear_slider(col_s_tras, "S3: Tras. Izq", self.ang_s3, 10, 170, callback=self.al_mover_servo)
        self.crear_slider(col_s_tras, "S4: Tras. Der", self.ang_s4, 10, 170, callback=self.al_mover_servo)

        frm_s_btns = ttk.Frame(card_servos, style="Card.TFrame")
        frm_s_btns.pack(fill="x", pady=(4, 0))
        tk.Button(frm_s_btns, text="⌖ 90°", bg="#334155", fg="#ffffff", font=("Segoe UI", 8, "bold"),
                  command=self.centrar_todos_los_servos, relief="flat", padx=6).pack(side="left", padx=2)
        tk.Button(frm_s_btns, text="🔄 Eje", bg="#334155", fg="#00f5d4", font=("Segoe UI", 8, "bold"),
                  command=self.preset_point_turn, relief="flat", padx=6).pack(side="left", padx=2)
        tk.Button(frm_s_btns, text="🦀 Cangrejo", bg="#334155", fg="#ff9f1c", font=("Segoe UI", 8, "bold"),
                  command=self.preset_cangrejo, relief="flat", padx=6).pack(side="left", padx=2)
        tk.Checkbutton(frm_s_btns, text="Invertir Servos", variable=self.invertir_servos,
                       bg="#1a1d2d", fg="#e2e8f0", selectcolor="#0f111a", font=("Segoe UI", 8)).pack(side="right")

        # ESQUEMA 2D Y BOTONES
        card_esquema = ttk.Frame(col_der, style="Card.TFrame", padding=8)
        card_esquema.pack(fill="x", pady=(0, 6))
        ttk.Label(card_esquema, text="🕹️ ESTADO DE MOVIMIENTO & ESQUEMA 2D", style="Header.TLabel").pack(anchor="w", pady=(0, 4))
        frm_esq_ctrl = ttk.Frame(card_esquema, style="Card.TFrame")
        frm_esq_ctrl.pack(fill="x")

        self.canvas_rover = tk.Canvas(frm_esq_ctrl, width=170, height=170, bg="#0f111a", highlightthickness=1,
                                      highlightbackground="#334155")
        self.canvas_rover.pack(side="left", padx=(0, 10))

        frm_mandos = ttk.Frame(frm_esq_ctrl, style="Card.TFrame")
        frm_mandos.pack(side="left", fill="both", expand=True)

        grid_botones = ttk.Frame(frm_mandos, style="Card.TFrame")
        grid_botones.pack(anchor="center", pady=2)

        self.btn_q = tk.Button(grid_botones, text="↺ Q", width=5, height=2, bg="#334155", fg="#00f5d4",
                               font=("Segoe UI", 8, "bold"), relief="flat", command=lambda: self.activar_macro("PIVOT_IZQ"))
        self.btn_q.grid(row=0, column=0, padx=2, pady=2)

        self.btn_w = tk.Button(grid_botones, text="▲ W", width=7, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat")
        self.btn_w.grid(row=0, column=1, padx=2, pady=2)

        self.btn_e = tk.Button(grid_botones, text="↻ E", width=5, height=2, bg="#334155", fg="#00f5d4",
                               font=("Segoe UI", 8, "bold"), relief="flat", command=lambda: self.activar_macro("PIVOT_DER"))
        self.btn_e.grid(row=0, column=2, padx=2, pady=2)

        self.btn_a = tk.Button(grid_botones, text="◄ A", width=5, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat")
        self.btn_a.grid(row=1, column=0, padx=2, pady=2)

        self.btn_stop = tk.Button(grid_botones, text="■ STOP", width=7, height=2, bg="#e63946", fg="#ffffff",
                                  font=("Segoe UI", 8, "bold"), relief="flat", command=self.parar_emergencia)
        self.btn_stop.grid(row=1, column=1, padx=2, pady=2)

        self.btn_d = tk.Button(grid_botones, text="D ►", width=5, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat")
        self.btn_d.grid(row=1, column=2, padx=2, pady=2)

        self.btn_s = tk.Button(grid_botones, text="▼ S", width=7, height=2, bg="#334155", fg="#ffffff",
                               font=("Segoe UI", 8, "bold"), relief="flat")
        self.btn_s.grid(row=2, column=1, padx=2, pady=2)

        # TELEMETRIA BADGES
        card_telemetria = ttk.Frame(col_der, style="Card.TFrame", padding=8)
        card_telemetria.pack(fill="x", pady=(0, 6))

        ttk.Label(card_telemetria, text="📊 TELEMETRIA EN VIVO DEL PROTOCOLO", style="Header.TLabel").pack(anchor="w", pady=(0, 4))
        grid_diag = ttk.Frame(card_telemetria, style="Card.TFrame")
        grid_diag.pack(fill="x")

        ttk.Label(grid_diag, text="Tasa TX:", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_diag_tasa = ttk.Label(grid_diag, text="0 Hz", style="Value.TLabel")
        self.lbl_diag_tasa.grid(row=0, column=1, sticky="w", padx=(4, 15))

        ttk.Label(grid_diag, text="Total TX:", style="SubHeader.TLabel").grid(row=0, column=2, sticky="w")
        self.lbl_diag_tot_tx = ttk.Label(grid_diag, text="0 paq", style="Value.TLabel")
        self.lbl_diag_tot_tx.grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(grid_diag, text="Total RX:", style="SubHeader.TLabel").grid(row=1, column=0, sticky="w")
        self.lbl_diag_tot_rx = ttk.Label(grid_diag, text="0 lin", style="Value.TLabel")
        self.lbl_diag_tot_rx.grid(row=1, column=1, sticky="w", padx=(4, 15))

        ttk.Label(grid_diag, text="Ultima Trama:", style="SubHeader.TLabel").grid(row=1, column=2, sticky="w")
        self.lbl_diag_ult_trama = ttk.Label(grid_diag, text="--", style="ValueWarn.TLabel")
        self.lbl_diag_ult_trama.grid(row=1, column=3, sticky="w", padx=4)

        # TERMINAL DE DEPURACION CON TAGS
        card_consola = ttk.Frame(self.root, style="Card.TFrame", padding=(15, 6))
        card_consola.pack(fill="both", expand=True, padx=15, pady=(4, 10))

        frm_tit_cons = ttk.Frame(card_consola, style="Card.TFrame")
        frm_tit_cons.pack(fill="x", pady=(0, 3))
        ttk.Label(frm_tit_cons, text="🔍 MONITOR SERIAL DEPURACION (TX / RX)", style="Header.TLabel").pack(side="left")

        tk.Checkbutton(frm_tit_cons, text="Ver Hex", variable=self.mostrar_hex,
                       bg="#1a1d2d", fg="#94a3b8", selectcolor="#0f111a", font=("Segoe UI", 8)).pack(side="left", padx=(15, 4))
        tk.Checkbutton(frm_tit_cons, text="Ver RX", variable=self.mostrar_rx,
                       bg="#1a1d2d", fg="#94a3b8", selectcolor="#0f111a", font=("Segoe UI", 8)).pack(side="left", padx=4)
        tk.Checkbutton(frm_tit_cons, text="AutoScroll", variable=self.auto_scroll,
                       bg="#1a1d2d", fg="#94a3b8", selectcolor="#0f111a", font=("Segoe UI", 8)).pack(side="left", padx=4)

        tk.Button(frm_tit_cons, text="💾 Guardar Log", bg="#334155", fg="#ffffff", font=("Segoe UI", 7, "bold"),
                  command=self.guardar_log_archivo, relief="flat", padx=6).pack(side="right", padx=3)
        tk.Button(frm_tit_cons, text="Limpiar", bg="#334155", fg="#ffffff", font=("Segoe UI", 7, "bold"),
                  command=self.limpiar_consola, relief="flat", padx=6).pack(side="right", padx=3)

        frm_txt = ttk.Frame(card_consola, style="Card.TFrame")
        frm_txt.pack(fill="both", expand=True)

        scroll_y = tk.Scrollbar(frm_txt)
        scroll_y.pack(side="right", fill="y")

        self.txt_consola = tk.Text(frm_txt, height=8, bg="#0a0c13", fg="#e2e8f0",
                                   font=("Consolas", 9), insertbackground="#ffffff", relief="flat",
                                   yscrollcommand=scroll_y.set)
        self.txt_consola.pack(side="left", fill="both", expand=True)
        scroll_y.config(command=self.txt_consola.yview)

        self.txt_consola.tag_config("TAG_TX", foreground="#00f5d4")
        self.txt_consola.tag_config("TAG_RX", foreground="#38b000")
        self.txt_consola.tag_config("TAG_HEX", foreground="#a78bfa")
        self.txt_consola.tag_config("TAG_KEY", foreground="#fbbf24")
        self.txt_consola.tag_config("TAG_WARN", foreground="#f87171")
        self.txt_consola.tag_config("TAG_SYS", foreground="#94a3b8")

        self.log_consola("SYS", "HMI Rover Debug cargado. Inspeccion de protocolo y telemetria lista.")

    def crear_slider(self, parent, nombre, variable, desde, hasta, callback=None):
        frm = ttk.Frame(parent, style="Card.TFrame")
        frm.pack(fill="x", pady=1)
        ttk.Label(frm, text=nombre, style="SubHeader.TLabel").pack(anchor="w")
        cmd_call = callback if callback else self.al_mover_slider_motor
        s = tk.Scale(frm, from_=desde, to=hasta, orient="horizontal", variable=variable,
                     bg="#1a1d2d", fg="#00f5d4", highlightthickness=0, command=cmd_call)
        s.pack(fill="x")

    def cambiar_modo_conduccion(self, event=None):
        modo = self.modo_conduccion.get()
        self.log_consola("SYS", f"Modo cambiado a: {modo}")
        if modo == "POINT_TURN":
            self.preset_point_turn()
        elif modo == "CRAB":
            self.preset_cangrejo()
        elif modo == "ACKERMANN":
            self.centrar_todos_los_servos()

    def centrar_todos_los_servos(self):
        self.ang_s1.set(90); self.ang_s2.set(90); self.ang_s3.set(90); self.ang_s4.set(90)
        self.enviar_trama_actual()
        self.dibujar_esquema_rover(self.comando_actual, 90, 90, 90, 90)
        self.log_consola("SYS", "Servos centrados a 90°.")

    def preset_point_turn(self):
        self.ang_s1.set(135); self.ang_s2.set(45); self.ang_s3.set(45); self.ang_s4.set(135)
        self.enviar_trama_actual()
        self.dibujar_esquema_rover("PIVOT", 135, 45, 45, 135)
        self.log_consola("SYS", "Preset Point Turn: S1=135°, S2=45°, S3=45°, S4=135°")

    def preset_cangrejo(self):
        self.ang_s1.set(135); self.ang_s2.set(135); self.ang_s3.set(135); self.ang_s4.set(135)
        self.enviar_trama_actual()
        self.dibujar_esquema_rover("CRAB", 135, 135, 135, 135)
        self.log_consola("SYS", "Preset Cangrejo: Todos a 135°")

    def sync_master_izq(self, val):
        v = int(val)
        self.pwm_m1.set(v); self.pwm_m2.set(v); self.pwm_m3.set(v)
        if self.conectado and self.comando_actual != " ":
            self.enviar_trama_actual()

    def sync_master_der(self, val):
        v = int(val)
        self.pwm_m4.set(v); self.pwm_m5.set(v); self.pwm_m6.set(v)
        if self.conectado and self.comando_actual != " ":
            self.enviar_trama_actual()

    def al_mover_slider_motor(self, val):
        if self.conectado and self.comando_actual != " ":
            self.enviar_trama_actual()

    def al_mover_servo(self, val):
        self.dibujar_esquema_rover(self.comando_actual, self.ang_s1.get(), self.ang_s2.get(),
                                   self.ang_s3.get(), self.ang_s4.get())
        if self.conectado:
            self.enviar_trama_actual()

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
            messagebox.showerror("Error", "Instale pyserial: pip install pyserial")
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
            self.log_consola("SYS", "Puerto cerrado.")
        else:
            puerto = self.cb_puertos.get()
            if not puerto or puerto == "Sin puertos":
                messagebox.showwarning("Atencion", "Seleccione un puerto COM.")
                return

            baud = int(self.cb_baud.get())
            try:
                self.serial_conn = serial.Serial(puerto, baud, timeout=0.1)
                time.sleep(0.5)
                self.conectado = True
                self.btn_conectar.config(text="❌ DESCONECTAR", bg="#e63946", fg="#ffffff")
                self.lbl_estado_badge.config(text=f"🟢 {puerto}", bg="#064e3b", fg="#34d399")
                self.log_consola("SYS", f"Conectado en {puerto} @ {baud} bps.")
            except Exception as e:
                self.conectado = False
                messagebox.showerror("Error", f"No se pudo abrir {puerto}:\\n{e}")
                self.log_consola("WARN", f"Error conexion {puerto}: {e}")

    def enviar_trama_actual(self):
        if not self.conectado or not self.serial_conn or not self.serial_conn.is_open:
            return

        pot_izq = int((self.pwm_m1.get() + self.pwm_m2.get() + self.pwm_m3.get()) / 3)
        pot_der = int((self.pwm_m4.get() + self.pwm_m5.get() + self.pwm_m6.get()) / 3)
        s1 = self.ang_s1.get(); s2 = self.ang_s2.get(); s3 = self.ang_s3.get(); s4 = self.ang_s4.get()

        cmd = self.comando_actual.upper()
        trama = f"{cmd},{pot_izq},{pot_der},{s1},{s2},{s3},{s4}\n"
        raw_bytes = trama.encode('ascii')
        hex_dump = " ".join(f"{b:02X}" for b in raw_bytes)

        try:
            self.serial_conn.write(raw_bytes)
            self.paquetes_tx_contador += 1
            self.ultimo_cmd_enviado = trama.strip()
            self.ultimo_hex_enviado = hex_dump

            self.log_consola("TX", f"[TX #{self.paquetes_tx_contador}] \"{trama.strip()}\"")
            if self.mostrar_hex.get():
                self.log_consola("HEX", f"    BYTES: [{hex_dump}] ({len(raw_bytes)} B)")
        except Exception as e:
            self.log_consola("WARN", f"Error TX: {e}")

    def iniciar_hilos_segundo_plano(self):
        self.hilo_serial = threading.Thread(target=self.bucle_recepcion_serial, daemon=True)
        self.hilo_serial.start()

    def bucle_recepcion_serial(self):
        while self.ejecutando:
            if self.conectado and self.serial_conn and self.serial_conn.is_open:
                try:
                    linea = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    if linea:
                        self.paquetes_rx_contador += 1
                        if self.mostrar_rx.get():
                            self.root.after(0, self.log_consola, "RX", f"[RX #{self.paquetes_rx_contador}] {linea}")
                except:
                    pass
            time.sleep(0.01)

    def log_consola(self, tag, texto):
        t_str = time.strftime("[%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}] "
        tag_style = f"TAG_{tag}" if f"TAG_{tag}" in ["TAG_TX", "TAG_RX", "TAG_HEX", "TAG_KEY", "TAG_WARN", "TAG_SYS"] else "TAG_SYS"
        self.txt_consola.insert("end", t_str, "TAG_SYS")
        self.txt_consola.insert("end", texto + "\n", tag_style)
        if self.auto_scroll.get():
            self.txt_consola.see("end")

    def limpiar_consola(self):
        self.txt_consola.delete("1.0", "end")

    def guardar_log_archivo(self):
        contenido = self.txt_consola.get("1.0", "end")
        if not contenido.strip():
            messagebox.showinfo("Info", "Consola vacia.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".log",
                                            filetypes=[("Log", "*.log"), ("Texto", "*.txt")],
                                            initialfile=f"log_rover_{time.strftime('%Y%m%d_%H%M%S')}.log")
        if ruta:
            try:
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(contenido)
                messagebox.showinfo("Exito", f"Guardado en:\n{ruta}")
            except Exception as e:
                messagebox.showerror("Error", f"Error al guardar:\n{e}")

    def evento_key_press(self, event):
        k = event.keysym.lower()
        if k in self.teclas_presionadas:
            if not self.teclas_presionadas[k]:
                self.teclas_presionadas[k] = True
                self.log_consola("KEY", f"KeyDown: '{k}'")
                self.evaluar_estado_movimiento()

    def evento_key_release(self, event):
        k = event.keysym.lower()
        if k in self.teclas_presionadas:
            self.teclas_presionadas[k] = False
            self.log_consola("KEY", f"KeyUp: '{k}'")
            self.evaluar_estado_movimiento()

    def parar_emergencia(self):
        for k in self.teclas_presionadas:
            self.teclas_presionadas[k] = False
        self.comando_actual = " "
        self.enviar_trama_actual()
        self.actualizar_botones_ui("STOP")
        self.dibujar_esquema_rover("STOP", self.ang_s1.get(), self.ang_s2.get(), self.ang_s3.get(), self.ang_s4.get())
        self.log_consola("WARN", "🚨 STOP DE EMERGENCIA -> Motores=0")

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

    def dibujar_rueda_rotada(self, cx, cy, angulo_grados, color, texto):
        rad = math.radians(90 - angulo_grados)
        w_half, h_half = 6, 12
        vertices = [(-w_half, -h_half), (w_half, -h_half), (w_half, h_half), (-w_half, h_half)]
        puntos_rotados = []
        for vx, vy in vertices:
            rx = cx + (vx * math.cos(rad) - vy * math.sin(rad))
            ry = cy + (vx * math.sin(rad) + vy * math.cos(rad))
            puntos_rotados.extend([rx, ry])
        self.canvas_rover.create_polygon(puntos_rotados, fill=color, outline="#ffffff", width=1)
        self.canvas_rover.create_text(cx, cy, text=texto, fill="#ffffff", font=("Segoe UI", 5, "bold"))

    def dibujar_esquema_rover(self, cmd, s1, s2, s3, s4):
        c = self.canvas_rover
        c.delete("all")
        cx, cy = 85, 85
        c.create_rectangle(cx - 28, cy - 45, cx + 28, cy + 45, fill="#1e2235", outline="#00f5d4", width=2)
        c.create_text(cx, cy, text="6x6", fill="#94a3b8", font=("Segoe UI", 7, "bold"))

        color_activa = "#38b000" if cmd != " " and cmd != "STOP" else "#64748b"
        self.dibujar_rueda_rotada(cx - 45, cy - 38, s1, color_activa, "M1")
        self.dibujar_rueda_rotada(cx + 45, cy - 38, s2, color_activa, "M4")
        self.dibujar_rueda_rotada(cx - 45, cy, 90, color_activa, "M2")
        self.dibujar_rueda_rotada(cx + 45, cy, 90, color_activa, "M5")
        self.dibujar_rueda_rotada(cx - 45, cy + 38, s3, color_activa, "M3")
        self.dibujar_rueda_rotada(cx + 45, cy + 38, s4, color_activa, "M6")

        if cmd == "W":
            c.create_line(cx, cy - 8, cx, cy - 30, fill="#00f5d4", width=2, arrow=tk.LAST)
        elif cmd == "S":
            c.create_line(cx, cy + 8, cx, cy + 30, fill="#ff9f1c", width=2, arrow=tk.LAST)

    def actualizar_telemetria_ui(self):
        t_ahora = time.time()
        dt = t_ahora - self.ultimo_tiempo_tasa
        if dt >= 1.0:
            self.tasa_tx_hz = int(self.paquetes_tx_contador / dt)
            self.ultimo_tiempo_tasa = t_ahora
            self.lbl_diag_tasa.config(text=f"{self.tasa_tx_hz} Hz")

        self.lbl_diag_tot_tx.config(text=f"{self.paquetes_tx_contador} paq")
        self.lbl_diag_tot_rx.config(text=f"{self.paquetes_rx_contador} lin")
        self.lbl_diag_ult_trama.config(text=self.ultimo_cmd_enviado if self.ultimo_cmd_enviado else "--")
        self.root.after(100, self.actualizar_telemetria_ui)

if __name__ == '__main__':
    ventana_principal = tk.Tk()
    app = HMIRoverDebug(ventana_principal)
    ventana_principal.mainloop()
