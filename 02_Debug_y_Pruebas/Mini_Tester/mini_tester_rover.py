#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINI TESTER INDEPENDIENTE — ROVER LUNAR V2.0
Herramienta de diagnostico y prueba unitaria para actuadores del Rover:
  - Traccion izquierda (Pines D2/D5) y derecha (Pines D3/D4)
  - Servomotores independientes S1 (D6), S2 (D7), S3 (D8), S4 (A0) con angulo directo [10, 170]
  - Enlace dual: Puerto Serie USB (COM) o Wi-Fi UDP (192.168.4.1:4210)

Regla estricta: Cero emojis en toda la aplicacion.
"""

import sys
import os
import time
import socket
import struct
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Intentar importar pyserial si esta disponible
try:
    import serial
    import serial.tools.list_ports
    SERIAL_DISPONIBLE = True
except ImportError:
    SERIAL_DISPONIBLE = False


class RoverCommunicator:
    """Gestiona la comunicacion hacia el Rover via Serial USB o Wi-Fi UDP."""

    def __init__(self, callback_log=None, callback_status=None):
        self.callback_log = callback_log
        self.callback_status = callback_status
        self.modo = "SERIAL"  # "SERIAL" o "WIFI"
        self.ser = None
        self.udp_sock = None
        self.udp_ip = "192.168.4.1"
        self.udp_port = 4210
        self.conectado = False
        self.hilo_rx = None
        self.activo = False
        self.lock = threading.Lock()

    def log(self, mensaje):
        if self.callback_log:
            self.callback_log(mensaje)
        else:
            print(mensaje)

    def set_status(self, conectado, detalle=""):
        self.conectado = conectado
        if self.callback_status:
            self.callback_status(conectado, detalle)

    def conectar_serial(self, puerto, baudrate=115200):
        if not SERIAL_DISPONIBLE:
            self.log("[ERROR] pyserial no esta instalado en este interprete de Python.")
            return False
        self.desconectar()
        try:
            self.ser = serial.Serial(puerto, baudrate, timeout=0.1)
            self.modo = "SERIAL"
            self.activo = True
            self.hilo_rx = threading.Thread(target=self._bucle_rx_serial, daemon=True)
            self.hilo_rx.start()
            self.set_status(True, f"Serial en {puerto} ({baudrate} bps)")
            self.log(f"[INFO] Conectado exitosamente por Serial a {puerto}")
            self.enviar_texto("IDENT\n")
            return True
        except Exception as e:
            self.set_status(False, f"Error: {e}")
            self.log(f"[ERROR] No se pudo abrir {puerto}: {e}")
            return False

    def conectar_wifi(self, ip="192.168.4.1", port=4210):
        self.desconectar()
        try:
            self.udp_ip = ip
            self.udp_port = int(port)
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.settimeout(0.2)
            self.modo = "WIFI"
            self.activo = True
            self.hilo_rx = threading.Thread(target=self._bucle_rx_wifi, daemon=True)
            self.hilo_rx.start()
            self.set_status(True, f"Wi-Fi UDP hacia {ip}:{port}")
            self.log(f"[INFO] Socket UDP listo para transmitir hacia {ip}:{port}")
            self.enviar_texto("IDENT\n")
            return True
        except Exception as e:
            self.set_status(False, f"Error: {e}")
            self.log(f"[ERROR] No se pudo inicializar socket UDP: {e}")
            return False

    def desconectar(self):
        self.activo = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

        if self.udp_sock:
            try:
                self.udp_sock.close()
            except Exception:
                pass
            self.udp_sock = None

        self.set_status(False, "Desconectado")
        self.log("[INFO] Comunicacion desconectada.")

    def enviar_texto(self, texto):
        if not self.conectado:
            self.log(f"[WARN] No hay conexion activa. Comando descartado: {texto.strip()}")
            return False

        if not texto.endswith("\n"):
            texto += "\n"

        with self.lock:
            try:
                if self.modo == "SERIAL" and self.ser and self.ser.is_open:
                    self.ser.write(texto.encode("utf-8"))
                    self.log(f"[TX-SER] {texto.strip()}")
                    return True
                elif self.modo == "WIFI" and self.udp_sock:
                    self.udp_sock.sendto(texto.encode("utf-8"), (self.udp_ip, self.udp_port))
                    self.log(f"[TX-UDP] {texto.strip()}")
                    return True
            except Exception as e:
                self.log(f"[ERROR TX] Fallo al enviar comando: {e}")
                return False
        return False

    def enviar_paquete_binario(self, traccion_izq, traccion_der, s1, s2, s3, s4):
        """Empaqueta trama binaria estricta de 8 bytes (int16, int16, uint8, uint8, uint8, uint8)."""
        if not self.conectado:
            self.log("[WARN] No hay conexion activa para paquete binario.")
            return False

        t_izq = max(-255, min(255, int(traccion_izq)))
        t_der = max(-255, min(255, int(traccion_der)))
        a1 = max(10, min(170, int(s1)))
        a2 = max(10, min(170, int(s2)))
        a3 = max(10, min(170, int(s3)))
        a4 = max(10, min(170, int(s4)))

        # Formato little-endian packed: 2x int16, 4x uint8 (8 bytes exactos)
        payload = struct.pack("<hhBBBB", t_izq, t_der, a1, a2, a3, a4)

        with self.lock:
            try:
                if self.modo == "SERIAL" and self.ser and self.ser.is_open:
                    cmd_csv = f"CMD,{t_izq},{t_der},{a1},{a2},{a3},{a4}\n"
                    self.ser.write(cmd_csv.encode("utf-8"))
                    self.log(f"[TX-BIN-CSV] CMD,{t_izq},{t_der},{a1},{a2},{a3},{a4}")
                    return True
                elif self.modo == "WIFI" and self.udp_sock:
                    self.udp_sock.sendto(payload, (self.udp_ip, self.udp_port))
                    self.log(f"[TX-BIN-UDP] 8 bytes: Trac=({t_izq},{t_der}) Servos=({a1},{a2},{a3},{a4})")
                    return True
            except Exception as e:
                self.log(f"[ERROR TX-BIN] Fallo: {e}")
                return False
        return False

    def _bucle_rx_serial(self):
        while self.activo and self.ser and self.ser.is_open:
            try:
                linea = self.ser.readline().decode("utf-8", errors="replace").strip()
                if linea:
                    self.log(f"[RX-SER] {linea}")
            except Exception:
                break
            time.sleep(0.01)

    def _bucle_rx_wifi(self):
        while self.activo and self.udp_sock:
            try:
                datos, addr = self.udp_sock.recvfrom(256)
                if datos:
                    texto = datos.decode("utf-8", errors="replace").strip()
                    self.log(f"[RX-UDP] {texto}")
            except socket.timeout:
                pass
            except Exception:
                break
            time.sleep(0.01)


class MiniTesterRoverGUI:
    """Interfaz Grafica de Diagnostico y Prueba de Componentes Individuales."""

    def __init__(self, root):
        self.root = root
        self.root.title("Mini Tester de Actuadores — Rover Lunar V2.0")
        self.root.geometry("1180x800")
        self.root.minsize(1050, 720)
        self.root.configure(bg="#161823")

        self.comm = RoverCommunicator(callback_log=self.agregar_log, callback_status=self.actualizar_estado_conexion)

        # Variables de control de motores
        self.pwm_izq = tk.IntVar(value=0)
        self.pwm_der = tk.IntVar(value=0)

        # Variables de control de servos (angulos directos 10 a 170 grados)
        self.ang_s1 = tk.IntVar(value=90)
        self.ang_s2 = tk.IntVar(value=90)
        self.ang_s3 = tk.IntVar(value=90)
        self.ang_s4 = tk.IntVar(value=90)

        # Variables de comunicacion
        self.tipo_conexion = tk.StringVar(value="SERIAL")
        self.puerto_com = tk.StringVar(value="")
        self.ip_udp = tk.StringVar(value="192.168.4.1")
        self.port_udp = tk.StringVar(value="4210")

        self._crear_estilos()
        self._construir_interfaz()
        self._escanear_puertos_com()

    def _crear_estilos(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self.style.configure(".", background="#161823", foreground="#e0e6ed", font=("Segoe UI", 9))
        self.style.configure("TFrame", background="#161823")
        self.style.configure("Card.TFrame", background="#212433", relief="solid", borderwidth=1)
        self.style.configure("CardHeader.TLabel", background="#212433", foreground="#00f5d4", font=("Segoe UI", 10, "bold"))
        self.style.configure("SubHeader.TLabel", background="#212433", foreground="#ff9f1c", font=("Segoe UI", 9, "bold"))
        self.style.configure("Muted.TLabel", background="#212433", foreground="#8a99ad", font=("Segoe UI", 8))

        # Botones estandar
        self.style.configure("Accent.TButton", background="#00b4d8", foreground="#ffffff", font=("Segoe UI", 9, "bold"))
        self.style.map("Accent.TButton", background=[("active", "#0096c7"), ("disabled", "#334155")])

        self.style.configure("Danger.TButton", background="#e63946", foreground="#ffffff", font=("Segoe UI", 9, "bold"))
        self.style.map("Danger.TButton", background=[("active", "#d90429"), ("disabled", "#334155")])

        self.style.configure("Warn.TButton", background="#ff9f1c", foreground="#161823", font=("Segoe UI", 9, "bold"))
        self.style.map("Warn.TButton", background=[("active", "#f77f00"), ("disabled", "#334155")])

        self.style.configure("Success.TButton", background="#2ec4b6", foreground="#161823", font=("Segoe UI", 9, "bold"))
        self.style.map("Success.TButton", background=[("active", "#20a39e"), ("disabled", "#334155")])

        self.style.configure("Dark.TButton", background="#2b3044", foreground="#e0e6ed", font=("Segoe UI", 8))
        self.style.map("Dark.TButton", background=[("active", "#3a415a"), ("disabled", "#222533")])

    def _construir_interfaz(self):
        # 1. Barra Superior de Conexion
        frame_top = ttk.Frame(self.root, style="Card.TFrame")
        frame_top.pack(fill="x", padx=10, pady=8)

        lbl_tit = ttk.Label(frame_top, text="PANEL DE COMUNICACION", style="CardHeader.TLabel")
        lbl_tit.grid(row=0, column=0, columnspan=8, sticky="w", padx=10, pady=(6, 4))

        # Radio selector
        rb_ser = ttk.Radiobutton(frame_top, text="Serial USB (COM)", variable=self.tipo_conexion, value="SERIAL", command=self._actualizar_campos_conexion)
        rb_ser.grid(row=1, column=0, padx=10, pady=4)
        rb_udp = ttk.Radiobutton(frame_top, text="Wi-Fi UDP (Directo)", variable=self.tipo_conexion, value="WIFI", command=self._actualizar_campos_conexion)
        rb_udp.grid(row=1, column=1, padx=10, pady=4)

        # Campos Serial
        self.lbl_com = ttk.Label(frame_top, text="Puerto:", background="#212433")
        self.lbl_com.grid(row=1, column=2, padx=(10, 2), pady=4)
        self.combo_puertos = ttk.Combobox(frame_top, textvariable=self.puerto_com, width=12, state="readonly")
        self.combo_puertos.grid(row=1, column=3, padx=2, pady=4)
        self.btn_scan = ttk.Button(frame_top, text="Escanear", style="Dark.TButton", command=self._escanear_puertos_com)
        self.btn_scan.grid(row=1, column=4, padx=4, pady=4)

        # Campos UDP
        self.lbl_ip = ttk.Label(frame_top, text="IP:", background="#212433")
        self.lbl_ip.grid(row=1, column=2, padx=(10, 2), pady=4)
        self.ent_ip = ttk.Entry(frame_top, textvariable=self.ip_udp, width=13)
        self.ent_ip.grid(row=1, column=3, padx=2, pady=4)
        self.lbl_port = ttk.Label(frame_top, text="Puerto:", background="#212433")
        self.lbl_port.grid(row=1, column=4, padx=(8, 2), pady=4)
        self.ent_port = ttk.Entry(frame_top, textvariable=self.port_udp, width=6)
        self.ent_port.grid(row=1, column=5, padx=2, pady=4)

        # Boton Conectar y Estado
        self.btn_conectar = ttk.Button(frame_top, text="Conectar", style="Accent.TButton", command=self._toggle_conexion)
        self.btn_conectar.grid(row=1, column=6, padx=10, pady=4)

        self.lbl_estado_conn = ttk.Label(frame_top, text="DESCONECTADO", background="#212433", foreground="#e63946", font=("Segoe UI", 9, "bold"))
        self.lbl_estado_conn.grid(row=1, column=7, padx=10, pady=4)

        btn_ident = ttk.Button(frame_top, text="IDENT / PING", style="Dark.TButton", command=self._enviar_ident)
        btn_ident.grid(row=1, column=8, padx=6, pady=4)

        self._actualizar_campos_conexion()

        # 2. Contenedor Principal (3 Columnas)
        frame_main = ttk.Frame(self.root)
        frame_main.pack(fill="both", expand=True, padx=10, pady=2)
        frame_main.columnconfigure(0, weight=3)
        frame_main.columnconfigure(1, weight=4)
        frame_main.columnconfigure(2, weight=4)
        frame_main.rowconfigure(0, weight=1)

        # Columna 1: Traccion y Motores DC
        self._construir_panel_motores(frame_main)

        # Columna 2: Servomotores de Direccion (Angulo Directo)
        self._construir_panel_servos(frame_main)

        # Columna 3: Diagnostico y Consola de Telemetria
        self._construir_panel_diagnostico_y_consola(frame_main)

        # 3. Barra Inferior de Emergencia
        frame_bottom = ttk.Frame(self.root, style="Card.TFrame")
        frame_bottom.pack(fill="x", padx=10, pady=(4, 8))

        btn_estop = ttk.Button(frame_bottom, text="PARADA GENERAL DE EMERGENCIA (E-STOP)", style="Danger.TButton", command=self._parada_emergencia)
        btn_estop.pack(fill="x", ipady=5, padx=10, pady=6)

    def _actualizar_campos_conexion(self):
        modo = self.tipo_conexion.get()
        if modo == "SERIAL":
            self.lbl_com.grid()
            self.combo_puertos.grid()
            self.btn_scan.grid()
            self.lbl_ip.grid_remove()
            self.ent_ip.grid_remove()
            self.lbl_port.grid_remove()
            self.ent_port.grid_remove()
        else:
            self.lbl_com.grid_remove()
            self.combo_puertos.grid_remove()
            self.btn_scan.grid_remove()
            self.lbl_ip.grid()
            self.ent_ip.grid()
            self.lbl_port.grid()
            self.ent_port.grid()

    def _escanear_puertos_com(self):
        if not SERIAL_DISPONIBLE:
            self.combo_puertos["values"] = ["No hay pyserial"]
            return
        puertos = [p.device for p in serial.tools.list_ports.comports()]
        if puertos:
            self.combo_puertos["values"] = puertos
            if not self.puerto_com.get() or self.puerto_com.get() not in puertos:
                self.puerto_com.set(puertos[0])
            self.agregar_log(f"[INFO] Puertos detectados: {', '.join(puertos)}")
        else:
            self.combo_puertos["values"] = []
            self.puerto_com.set("")
            self.agregar_log("[WARN] No se detectaron puertos COM en el sistema.")

    def _toggle_conexion(self):
        if self.comm.conectado:
            self.comm.desconectar()
        else:
            modo = self.tipo_conexion.get()
            if modo == "SERIAL":
                pto = self.puerto_com.get().strip()
                if not pto:
                    messagebox.showwarning("Atencion", "Selecciona un puerto COM valido.")
                    return
                self.comm.conectar_serial(pto)
            else:
                ip = self.ip_udp.get().strip()
                puerto = self.port_udp.get().strip()
                if not ip or not puerto.isdigit():
                    messagebox.showwarning("Atencion", "Ingresa una IP y puerto validos.")
                    return
                self.comm.conectar_wifi(ip, int(puerto))

    def actualizar_estado_conexion(self, conectado, detalle):
        def _actualizar():
            if conectado:
                self.btn_conectar.config(text="Desconectar", style="Danger.TButton")
                self.lbl_estado_conn.config(text=f"CONECTADO ({detalle})", foreground="#00f5d4")
            else:
                self.btn_conectar.config(text="Conectar", style="Accent.TButton")
                self.lbl_estado_conn.config(text="DESCONECTADO", foreground="#e63946")
        self.root.after(0, _actualizar)

    def _enviar_ident(self):
        self.comm.enviar_texto("IDENT\n")
        self.comm.enviar_texto("PING\n")

    # ==========================================
    # PANEL DE MOTORES DC (TRACCION INDEPENDIENTE)
    # ==========================================
    def _construir_panel_motores(self, parent):
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        ttk.Label(frame, text="TRACCION Y MOTORES DC (L9110S)", style="CardHeader.TLabel").pack(anchor="w", padx=10, pady=(8, 4))
        ttk.Label(frame, text="Control independiente de bancada izquierda y derecha", style="Muted.TLabel").pack(anchor="w", padx=10, pady=(0, 6))

        # --- Motor Izquierdo (M1, M2, M3: D2 / D5) ---
        frm_izq = ttk.Frame(frame, style="Card.TFrame")
        frm_izq.pack(fill="x", padx=8, pady=4)
        ttk.Label(frm_izq, text="MOTOR IZQUIERDO (Pines D2 / D5)", style="SubHeader.TLabel").pack(anchor="w", padx=8, pady=(4, 2))

        self.lbl_pwm_izq = ttk.Label(frm_izq, text="PWM: 0 (STOP)", background="#212433", foreground="#00f5d4")
        self.lbl_pwm_izq.pack(anchor="w", padx=8)

        sc_izq = tk.Scale(frm_izq, from_=-255, to=255, orient="horizontal", variable=self.pwm_izq,
                          bg="#161823", fg="#00f5d4", highlightthickness=0, command=self._al_mover_motor_izq)
        sc_izq.pack(fill="x", padx=8, pady=2)

        frm_btn_izq = ttk.Frame(frm_izq)
        frm_btn_izq.pack(fill="x", padx=8, pady=4)
        ttk.Button(frm_btn_izq, text="Avance +150", style="Dark.TButton", command=lambda: self._set_motor_izq(150)).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(frm_btn_izq, text="STOP (0)", style="Warn.TButton", command=lambda: self._set_motor_izq(0)).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(frm_btn_izq, text="Reversa -150", style="Dark.TButton", command=lambda: self._set_motor_izq(-150)).pack(side="left", expand=True, fill="x", padx=1)

        # Pulso directo a pin
        frm_pins_izq = ttk.Frame(frm_izq)
        frm_pins_izq.pack(fill="x", padx=8, pady=(2, 6))
        ttk.Button(frm_pins_izq, text="Test Pin D2 (A1A)", style="Dark.TButton", command=lambda: self.comm.enviar_texto("TEST:PIN_RAW,D2,150\n")).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(frm_pins_izq, text="Test Pin D5 (A1B)", style="Dark.TButton", command=lambda: self.comm.enviar_texto("TEST:PIN_RAW,D5,150\n")).pack(side="left", expand=True, fill="x", padx=1)

        # --- Motor Derecho (M4, M5, M6: D3 / D4) ---
        frm_der = ttk.Frame(frame, style="Card.TFrame")
        frm_der.pack(fill="x", padx=8, pady=4)
        ttk.Label(frm_der, text="MOTOR DERECHO (Pines D3 / D4)", style="SubHeader.TLabel").pack(anchor="w", padx=8, pady=(4, 2))

        self.lbl_pwm_der = ttk.Label(frm_der, text="PWM: 0 (STOP)", background="#212433", foreground="#00f5d4")
        self.lbl_pwm_der.pack(anchor="w", padx=8)

        sc_der = tk.Scale(frm_der, from_=-255, to=255, orient="horizontal", variable=self.pwm_der,
                          bg="#161823", fg="#00f5d4", highlightthickness=0, command=self._al_mover_motor_der)
        sc_der.pack(fill="x", padx=8, pady=2)

        frm_btn_der = ttk.Frame(frm_der)
        frm_btn_der.pack(fill="x", padx=8, pady=4)
        ttk.Button(frm_btn_der, text="Avance +150", style="Dark.TButton", command=lambda: self._set_motor_der(150)).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(frm_btn_der, text="STOP (0)", style="Warn.TButton", command=lambda: self._set_motor_der(0)).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(frm_btn_der, text="Reversa -150", style="Dark.TButton", command=lambda: self._set_motor_der(-150)).pack(side="left", expand=True, fill="x", padx=1)

        frm_pins_der = ttk.Frame(frm_der)
        frm_pins_der.pack(fill="x", padx=8, pady=(2, 6))
        ttk.Button(frm_pins_der, text="Test Pin D3 (B1A)", style="Dark.TButton", command=lambda: self.comm.enviar_texto("TEST:PIN_RAW,D3,150\n")).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(frm_pins_der, text="Test Pin D4 (B1B)", style="Dark.TButton", command=lambda: self.comm.enviar_texto("TEST:PIN_RAW,D4,150\n")).pack(side="left", expand=True, fill="x", padx=1)

        # --- Comandos Globales de Traccion ---
        frm_glob_mot = ttk.Frame(frame, style="Card.TFrame")
        frm_glob_mot.pack(fill="x", padx=8, pady=6)
        ttk.Label(frm_glob_mot, text="MANIOBRAS GLOBALES DE TRACCION", style="SubHeader.TLabel").pack(anchor="w", padx=8, pady=(4, 2))

        f_gm1 = ttk.Frame(frm_glob_mot)
        f_gm1.pack(fill="x", padx=8, pady=2)
        ttk.Button(f_gm1, text="Ambos Frente (+160)", style="Dark.TButton", command=lambda: self._ambos_motores(160, 160)).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(f_gm1, text="Ambos Reversa (-160)", style="Dark.TButton", command=lambda: self._ambos_motores(-160, -160)).pack(side="left", expand=True, fill="x", padx=1)

        f_gm2 = ttk.Frame(frm_glob_mot)
        f_gm2.pack(fill="x", padx=8, pady=2)
        ttk.Button(f_gm2, text="Pivot Izquierda", style="Dark.TButton", command=lambda: self._ambos_motores(-160, 160)).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(f_gm2, text="Pivot Derecha", style="Dark.TButton", command=lambda: self._ambos_motores(160, -160)).pack(side="left", expand=True, fill="x", padx=1)

        f_gm3 = ttk.Frame(frm_glob_mot)
        f_gm3.pack(fill="x", padx=8, pady=(4, 6))
        ttk.Button(f_gm3, text="FRENAR MOTORES", style="Warn.TButton", command=self._frenar_motores).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(f_gm3, text="Invertir Logica PWM", style="Dark.TButton", command=lambda: self.comm.enviar_texto("INV:LOGICA,1\n")).pack(side="left", expand=True, fill="x", padx=2)

    def _al_mover_motor_izq(self, val):
        v = int(float(val))
        estado = "STOP" if v == 0 else ("AVANCE" if v > 0 else "REVERSA")
        self.lbl_pwm_izq.config(text=f"PWM: {v} ({estado})")
        self.comm.enviar_texto(f"MOT:IZQ,{v}\n")

    def _al_mover_motor_der(self, val):
        v = int(float(val))
        estado = "STOP" if v == 0 else ("AVANCE" if v > 0 else "REVERSA")
        self.lbl_pwm_der.config(text=f"PWM: {v} ({estado})")
        self.comm.enviar_texto(f"MOT:DER,{v}\n")

    def _set_motor_izq(self, val):
        self.pwm_izq.set(val)
        self._al_mover_motor_izq(val)

    def _set_motor_der(self, val):
        self.pwm_der.set(val)
        self._al_mover_motor_der(val)

    def _ambos_motores(self, izq, der):
        self.pwm_izq.set(izq)
        self.pwm_der.set(der)
        self.lbl_pwm_izq.config(text=f"PWM: {izq}")
        self.lbl_pwm_der.config(text=f"PWM: {der}")
        self.comm.enviar_texto(f"MOT:AMBOS,{izq},{der}\n")

    def _frenar_motores(self):
        self.pwm_izq.set(0)
        self.pwm_der.set(0)
        self.lbl_pwm_izq.config(text="PWM: 0 (STOP)")
        self.lbl_pwm_der.config(text="PWM: 0 (STOP)")
        self.comm.enviar_texto("MOT:PARAR\n")

    # ==========================================
    # PANEL DE SERVOMOTORES (CONTROL ANGULAR DIRECTO)
    # ==========================================
    def _construir_panel_servos(self, parent):
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)

        ttk.Label(frame, text="SERVOMOTORES DE DIRECCION (S1..S4)", style="CardHeader.TLabel").pack(anchor="w", padx=10, pady=(8, 2))
        ttk.Label(frame, text="Posicion angular directa [10, 170] grados. Centro = 90 grados.", style="Muted.TLabel").pack(anchor="w", padx=10, pady=(0, 6))

        # Contenedor para los 4 Servos
        scrollable_frame = ttk.Frame(frame, style="Card.TFrame")
        scrollable_frame.pack(fill="both", expand=True, padx=4, pady=2)

        self.labels_ang_servos = {}

        servos_info = [
            (1, "S1: Delantero Izquierdo (Pin D6)", self.ang_s1),
            (2, "S2: Delantero Derecho   (Pin D7)", self.ang_s2),
            (3, "S3: Trasero Izquierdo   (Pin D8)", self.ang_s3),
            (4, "S4: Trasero Derecho     (Pin A0)", self.ang_s4)
        ]

        for s_num, s_nom, var_ang in servos_info:
            self._crear_tarjeta_servo(scrollable_frame, s_num, s_nom, var_ang)

        # Botonera de Pruebas Globales de Servos
        frm_glob_srv = ttk.Frame(frame, style="Card.TFrame")
        frm_glob_srv.pack(fill="x", padx=8, pady=6)

        f_gs1 = ttk.Frame(frm_glob_srv)
        f_gs1.pack(fill="x", padx=6, pady=2)
        ttk.Button(f_gs1, text="Centrar Todos a 90°", style="Accent.TButton", command=self._centrar_todos_servos).pack(side="left", expand=True, fill="x", padx=1)

        f_gs2 = ttk.Frame(frm_glob_srv)
        f_gs2.pack(fill="x", padx=6, pady=2)
        ttk.Button(f_gs2, text="Viraje Izquierda (60° / 120°)", style="Dark.TButton", command=self._viraje_izquierda).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(f_gs2, text="Viraje Derecha (120° / 60°)", style="Dark.TButton", command=self._viraje_derecha).pack(side="left", expand=True, fill="x", padx=1)

    def _crear_tarjeta_servo(self, parent, num, nombre, var_ang):
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="x", padx=6, pady=4)

        ttk.Label(card, text=nombre, style="SubHeader.TLabel").pack(anchor="w", padx=6, pady=(4, 2))

        f_ang = ttk.Frame(card)
        f_ang.pack(fill="x", padx=6, pady=(2, 6))

        lbl_a = ttk.Label(f_ang, text="Angulo: 90°", width=12, background="#212433", foreground="#00f5d4")
        lbl_a.pack(side="left")
        self.labels_ang_servos[num] = lbl_a

        sc_ang = tk.Scale(f_ang, from_=10, to=170, orient="horizontal", variable=var_ang,
                          bg="#161823", fg="#00f5d4", highlightthickness=0,
                          command=lambda v, n=num: self._al_mover_angulo_servo(n, v))
        sc_ang.pack(side="left", fill="x", expand=True, padx=4)

        ttk.Button(f_ang, text="60° (Izq)", width=8, style="Dark.TButton", command=lambda n=num: self._fijar_angulo(n, 60)).pack(side="left", padx=1)
        ttk.Button(f_ang, text="90° (Centro)", width=10, style="Warn.TButton", command=lambda n=num: self._fijar_angulo(n, 90)).pack(side="left", padx=1)
        ttk.Button(f_ang, text="120° (Der)", width=8, style="Dark.TButton", command=lambda n=num: self._fijar_angulo(n, 120)).pack(side="left", padx=1)

    def _al_mover_angulo_servo(self, num, val):
        ang = int(float(val))
        self.labels_ang_servos[num].config(text=f"Angulo: {ang}°")
        self.comm.enviar_texto(f"TEST:S{num},{ang}\n")

    def _fijar_angulo(self, num, ang):
        var = getattr(self, f"ang_s{num}")
        var.set(ang)
        self._al_mover_angulo_servo(num, ang)

    def _centrar_todos_servos(self):
        for i in range(1, 5):
            getattr(self, f"ang_s{i}").set(90)
            self.labels_ang_servos[i].config(text="Angulo: 90°")
        self.comm.enviar_texto("TEST:SERVOS_CENTRO\n")

    def _viraje_izquierda(self):
        self._fijar_angulo(1, 60)
        self._fijar_angulo(2, 60)
        self._fijar_angulo(3, 120)
        self._fijar_angulo(4, 120)

    def _viraje_derecha(self):
        self._fijar_angulo(1, 120)
        self._fijar_angulo(2, 120)
        self._fijar_angulo(3, 60)
        self._fijar_angulo(4, 60)

    # ==========================================
    # PANEL DE DIAGNOSTICO Y CONSOLA
    # ==========================================
    def _construir_panel_diagnostico_y_consola(self, parent):
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(row=0, column=2, sticky="nsew", padx=4, pady=4)

        ttk.Label(frame, text="DIAGNOSTICO Y CONSOLA DE COMANDOS", style="CardHeader.TLabel").pack(anchor="w", padx=10, pady=(8, 2))

        # Cuadro explicativo
        frm_diag = ttk.Frame(frame, style="Card.TFrame")
        frm_diag.pack(fill="x", padx=8, pady=4)

        ttk.Label(frm_diag, text="ARQUITECTURA DE DIRECCION 4WS", style="SubHeader.TLabel").pack(anchor="w", padx=6, pady=(4, 2))

        explicacion = (
            "- Cada servomotor recibe un angulo exacto en grados [10, 170].\n"
            "- Angulo 90° representa el centro colineal (marcha recta).\n"
            "- Rango seguro [10°, 170°] para proteccion mecanica de topes.\n"
            "- Ruedas delanteras (S1, S2) viran solidarias.\n"
            "- Ruedas traseras (S3, S4) viran en sentido contrario (viraje 4WS).\n"
            "- Comandos aceptados: TEST:S1,ang / TEST:SERVOS_CENTRO / MOT:IZQ,pwm\n"
            "- Watchdog Failsafe de seguridad: parada automatica tras 1000 ms."
        )
        lbl_info = tk.Label(frm_diag, text=explicacion, bg="#212433", fg="#c5d1de", font=("Consolas", 8), justify="left")
        lbl_info.pack(fill="x", padx=6, pady=(2, 6))

        # Consola de Mensajes y Telemetria
        ttk.Label(frame, text="REGISTRO EN TIEMPO REAL (LOG)", style="SubHeader.TLabel").pack(anchor="w", padx=10, pady=(4, 1))

        self.txt_log = scrolledtext.ScrolledText(frame, bg="#0f111a", fg="#00f5d4", insertbackground="#00f5d4",
                                                font=("Consolas", 8), height=14)
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=2)

        # Entrada de comando manual
        frm_cmd = ttk.Frame(frame)
        frm_cmd.pack(fill="x", padx=8, pady=4)

        self.ent_cmd = ttk.Entry(frm_cmd)
        self.ent_cmd.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.ent_cmd.bind("<Return>", lambda e: self._enviar_comando_manual())

        ttk.Button(frm_cmd, text="Enviar", style="Accent.TButton", command=self._enviar_comando_manual).pack(side="left", padx=2)
        ttk.Button(frm_cmd, text="Limpiar", style="Dark.TButton", command=self._limpiar_log).pack(side="left", padx=2)

    def _enviar_comando_manual(self):
        cmd = self.ent_cmd.get().strip()
        if cmd:
            self.comm.enviar_texto(cmd + "\n")
            self.ent_cmd.delete(0, tk.END)

    def _limpiar_log(self):
        self.txt_log.delete("1.0", tk.END)

    def agregar_log(self, mensaje):
        def _append():
            timestamp = time.strftime("%H:%M:%S")
            self.txt_log.insert(tk.END, f"[{timestamp}] {mensaje}\n")
            self.txt_log.see(tk.END)
        self.root.after(0, _append)

    # ==========================================
    # PARADA DE EMERGENCIA GENERAL
    # ==========================================
    def _parada_emergencia(self):
        self.pwm_izq.set(0)
        self.pwm_der.set(0)
        self.lbl_pwm_izq.config(text="PWM: 0 (STOP)")
        self.lbl_pwm_der.config(text="PWM: 0 (STOP)")
        self.comm.enviar_texto("STOP\n")
        self.comm.enviar_texto("MOT:PARAR\n")
        self.comm.enviar_texto("TEST:SERVOS_CENTRO\n")
        self.agregar_log("[E-STOP] Parada general de emergencia enviada (Motores STOP + Servos a 90).")


def main():
    root = tk.Tk()
    app = MiniTesterRoverGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.comm.desconectar(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
