#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HMI de pilotaje del Rover Lunar (v3.1).

Se conecta por USB al Arduino Nano ESP32 transmisor y muestra:
  - Lo transmitido (consigna, secuencia y tasa de envio).
  - La cadena de senales que confirma la conexion: USB, transmisor, WiFi, telemetria y
    estado del ejecutor, incluida la causa del ultimo reinicio.

Dependencias: Tkinter (incluida en Python) y pyserial.
HMI_Rover_Debug.py reutiliza la logica de la primera mitad de este archivo.
"""

import math
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:
    tk = None

VERSION_HMI = "v3.1"
VERSION_FIRMWARE = "v3.0"  # Version del protocolo de las placas
BAUDIOS = 115200
PERIODO_ENVIO_S = 0.05  # 20 Hz. El transmisor frena si deja de recibir durante 500 ms
TELEMETRIA_VIGENTE_S = 1.0

PWM_MAX = 255
ANGULO_MIN = 10
ANGULO_MAX = 170
ANGULO_CENTRO = 90
FACTOR_GIRO = 0.7  # Rueda interior en giro Ackermann

MODOS = ("ACKERMANN", "CRAB", "MANUAL")

CAUSAS_RESET = {
    0: "DESCONOCIDA",
    1: "ENCENDIDO",
    2: "PIN EXTERNO",
    3: "SOFTWARE",
    4: "ERROR DE FIRMWARE",
    5: "WATCHDOG INT",
    6: "WATCHDOG TAREA",
    7: "WATCHDOG",
    8: "DEEP SLEEP",
    9: "BROWNOUT",
    10: "SDIO",
}
CAUSA_BROWNOUT = 9
ESTADOS_EJECUTOR = {0: "ARRANQUE", 1: "SIN ENLACE", 2: "OPERACION", 3: "FAILSAFE"}


# =============================================================================
# Protocolo
# =============================================================================
def limitar(valor, minimo, maximo):
    return max(minimo, min(maximo, int(valor)))


@dataclass(frozen=True)
class Consigna:
    izq: int = 0
    der: int = 0
    servos: tuple = (ANGULO_CENTRO, ANGULO_CENTRO, ANGULO_CENTRO, ANGULO_CENTRO)

    def linea(self):
        izq = limitar(self.izq, -PWM_MAX, PWM_MAX)
        der = limitar(self.der, -PWM_MAX, PWM_MAX)
        angulos = ",".join(str(limitar(a, ANGULO_MIN, ANGULO_MAX)) for a in self.servos)
        return f"CMD,{izq},{der},{angulos}\n"


@dataclass
class Mensaje:
    tipo: str
    datos: dict = field(default_factory=dict)
    texto: str = ""


CAMPOS_TLM = ("seq", "apl_izq", "apl_der", "a1", "a2", "a3", "a4", "rssi", "causa", "reinicios",
              "uptime", "rx_ok", "perdidos", "crc_malos", "failsafes", "estado", "diag")
CAMPOS_TX = ("seq", "izq", "der", "s1", "s2", "s3", "s4", "ok")
CAMPOS_RX = ("seq", "izq", "der", "s1", "s2", "s3", "s4", "dt", "apl_izq", "apl_der", "a1", "a2", "a3", "a4")
CAMPOS_LINK = ("clientes", "hmi", "edad_tlm")
CAMPOS_BOOT = ("causa", "reinicios")
FORMATOS = {"TLM": CAMPOS_TLM, "TX": CAMPOS_TX, "RX": CAMPOS_RX, "LINK": CAMPOS_LINK, "BOOT": CAMPOS_BOOT}


def parsear_linea(linea):
    """Convierte una linea del firmware en un Mensaje. Una linea danada queda como TEXTO."""
    linea = linea.strip()
    if linea.startswith("ID:"):
        partes = linea.split(":")
        if len(partes) == 4:
            return Mensaje("ID", {"placa": partes[1], "rol": partes[2], "version": partes[3]}, linea)
        return Mensaje("TEXTO", texto=linea)

    tipo = linea.split(",", 1)[0]
    campos = FORMATOS.get(tipo)
    if campos is None:
        return Mensaje("TEXTO", texto=linea)
    valores = linea.split(",")[1:]
    if len(valores) != len(campos):
        return Mensaje("TEXTO", texto=linea)
    try:
        return Mensaje(tipo, dict(zip(campos, map(int, valores))), linea)
    except ValueError:
        return Mensaje("TEXTO", texto=linea)


# =============================================================================
# Cinematica de direccion y traccion
# =============================================================================
def calcular_consigna(teclas, modo, pot_izq, pot_der, servos_manual, invertir_servos=False,
                      invertir_izq=False, invertir_der=False):
    """Traduce las teclas activas en una consigna. Devuelve (etiqueta, Consigna).

    Direccion y traccion van separadas:
      - A, D, Q y E solo orientan las ruedas. Por si solas no mueven los motores.
      - W y S son las unicas que mueven los motores: avance y reversa sobre la
        orientacion elegida. W y S juntas se anulan.
      - Q + W gira en el lugar hacia la izquierda y E + W hacia la derecha. Con S, al reves.
    Prioridad de direccion si hay varias apretadas: Q, E, A, D.
    """
    centro = (ANGULO_CENTRO,) * 4

    def orientar(angulos):
        if modo == "MANUAL":
            return tuple(servos_manual)
        return tuple(180 - a for a in angulos) if invertir_servos else angulos

    if teclas.get("space"):
        return "PARADA", Consigna(0, 0, tuple(servos_manual) if modo == "MANUAL" else centro)

    # Direccion: angulos de servo y factor de potencia por lado (izq, der)
    direccion, servos, factor = None, orientar(centro), (1.0, 1.0)
    if teclas.get("q"):
        direccion, servos, factor = "PIVOTE IZQ", orientar((45, 135, 135, 45)), (-1.0, 1.0)
    elif teclas.get("e"):
        direccion, servos, factor = "PIVOTE DER", orientar((45, 135, 135, 45)), (1.0, -1.0)
    elif teclas.get("a"):
        direccion = "IZQUIERDA"
        if modo == "CRAB":
            servos = orientar((135, 135, 135, 135))
        else:
            servos, factor = orientar((120, 120, 60, 60)), (FACTOR_GIRO, 1.0)
    elif teclas.get("d"):
        direccion = "DERECHA"
        if modo == "CRAB":
            servos = orientar((45, 45, 45, 45))
        else:
            servos, factor = orientar((60, 60, 120, 120)), (1.0, FACTOR_GIRO)

    # Traccion: solo W y S
    sentido = (1 if teclas.get("w") else 0) - (1 if teclas.get("s") else 0)
    traccion = {1: "AVANCE", -1: "REVERSA"}.get(sentido)
    izq = int(sentido * factor[0] * pot_izq)
    der = int(sentido * factor[1] * pot_der)

    if traccion and direccion:
        etiqueta = f"{traccion} + {direccion}"
    elif traccion:
        etiqueta = traccion
    elif direccion:
        etiqueta = f"{direccion} (detenido)"
    else:
        etiqueta = "REPOSO"

    if invertir_izq:
        izq = -izq
    if invertir_der:
        der = -der
    return etiqueta, Consigna(izq, der, servos)


# =============================================================================
# Estado del enlace: decide que senales mostrar a partir de los mensajes
# =============================================================================
class EstadoEnlace:
    def __init__(self, ahora=time.monotonic):
        self._ahora = ahora
        self.usb = False
        self.puerto = ""
        self.id_placa = None
        self.ultimo_tx = None
        self.ultima_tlm = None
        self.t_tlm = None
        self.clientes = 0
        self.hmi_activa = False
        self.reinicios_detectados = 0
        self.uptime_previo = None
        self.envios = deque()

    def registrar_usb(self, conectado, puerto=""):
        self.usb = conectado
        self.puerto = puerto
        if not conectado:
            self.id_placa = None
            self.clientes = 0

    def procesar(self, mensaje):
        ahora = self._ahora()
        if mensaje.tipo == "ID":
            self.id_placa = mensaje.datos
        elif mensaje.tipo == "TX":
            self.ultimo_tx = mensaje.datos
            if mensaje.datos["ok"]:
                self.envios.append(ahora)
        elif mensaje.tipo == "LINK":
            self.clientes = mensaje.datos["clientes"]
            self.hmi_activa = bool(mensaje.datos["hmi"])
        elif mensaje.tipo == "TLM":
            uptime = mensaje.datos["uptime"]
            if self.uptime_previo is not None and uptime < self.uptime_previo:
                self.reinicios_detectados += 1
            self.uptime_previo = uptime
            self.ultima_tlm = mensaje.datos
            self.t_tlm = ahora

    def tasa_envio_hz(self):
        limite = self._ahora() - 1.0
        while self.envios and self.envios[0] < limite:
            self.envios.popleft()
        return len(self.envios)

    def telemetria_vigente(self):
        return self.t_tlm is not None and self._ahora() - self.t_tlm < TELEMETRIA_VIGENTE_S

    def porcentaje_perdidas(self):
        if not self.ultima_tlm:
            return 0.0
        total = self.ultima_tlm["rx_ok"] + self.ultima_tlm["perdidos"]
        return 100.0 * self.ultima_tlm["perdidos"] / total if total else 0.0

    def senales(self):
        """Lista de (nombre, nivel, detalle). Nivel: ok, aviso o falla."""
        res = [("USB", "ok", self.puerto) if self.usb else ("USB", "falla", "Sin conectar")]

        if not self.usb:
            res.append(("Transmisor", "falla", "Sin conectar"))
        elif not self.id_placa:
            res.append(("Transmisor", "aviso", "Esperando respuesta"))
        elif self.id_placa["rol"] != "TX":
            res.append(("Transmisor", "falla", "Esta placa no es el transmisor"))
        elif self.id_placa["version"] != VERSION_FIRMWARE:
            res.append(("Transmisor", "aviso", f"Firmware {self.id_placa['version']}"))
        else:
            res.append(("Transmisor", "ok", self.id_placa["version"]))

        if self.usb and self.clientes > 0:
            res.append(("WiFi", "ok", "Ejecutor asociado"))
        else:
            res.append(("WiFi", "falla", "Ejecutor no asociado"))

        vigente = self.telemetria_vigente()
        if vigente:
            res.append(("Telemetria", "ok", f"RSSI {self.ultima_tlm['rssi']} dBm"))
        else:
            res.append(("Telemetria", "falla", "Sin datos del ejecutor"))

        if not vigente:
            res.append(("Ejecutor", "falla", "Sin datos"))
        else:
            estado = self.ultima_tlm["estado"]
            nombre = ESTADOS_EJECUTOR.get(estado, "?")
            if not self.ultima_tlm["diag"] & 1:
                res.append(("Ejecutor", "falla", "PCA9685 no responde"))
            elif estado == 2:
                res.append(("Ejecutor", "ok", nombre))
            elif estado == 3:
                res.append(("Ejecutor", "falla", nombre))
            else:
                res.append(("Ejecutor", "aviso", nombre))
        return res

    def alerta_reinicio(self):
        """Texto de alerta si el ejecutor se reinicio por algo distinto al encendido."""
        if not self.ultima_tlm:
            return ""
        causa = self.ultima_tlm["causa"]
        total = max(self.ultima_tlm["reinicios"], self.reinicios_detectados)
        if causa == CAUSA_BROWNOUT:
            return f"Ejecutor reiniciado por BROWNOUT (caida de tension). Reinicios: {total}. Revisar alimentacion."
        if total > 0:
            return f"Ejecutor reiniciado. Ultima causa: {CAUSAS_RESET.get(causa, causa)}. Reinicios: {total}."
        return ""


# =============================================================================
# Puerto serie en hilo propio, con reconexion automatica
# =============================================================================
class EnlaceSerie:
    """Lee lineas sin bloquear la interfaz. Eventos en cola: (nombre, tipo, valor, instante)."""

    def __init__(self, nombre, eventos, fabrica=None):
        self.nombre = nombre
        self.eventos = eventos
        self._fabrica = fabrica or self._abrir_puerto_real
        self._puerto = None
        self._ser = None
        self._cerrojo = threading.Lock()
        self._activo = True
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    @staticmethod
    def _abrir_puerto_real(puerto):
        ser = serial.Serial()
        ser.port = puerto
        ser.baudrate = BAUDIOS
        ser.timeout = 0.1
        ser.write_timeout = 0.2
        ser.rts = False  # Evita reiniciar la placa al abrir el puerto
        ser.dtr = False
        ser.open()
        time.sleep(0.15)
        ser.dtr = True
        return ser

    @property
    def conectado(self):
        return self._ser is not None

    def abrir(self, puerto):
        self._puerto = puerto

    def cerrar(self):
        self._puerto = None
        self._soltar_puerto()

    def terminar(self):
        self._activo = False
        self.cerrar()

    def escribir(self, texto):
        with self._cerrojo:
            ser = self._ser
        if ser is None:
            return False
        try:
            ser.write(texto.encode("ascii"))
            return True
        except Exception as error:  # pyserial falla con distintos tipos segun el sistema
            self._emitir("error", str(error))
            self._soltar_puerto()
            return False

    def _emitir(self, tipo, valor):
        self.eventos.put((self.nombre, tipo, valor, time.monotonic()))

    def _soltar_puerto(self):
        with self._cerrojo:
            ser, self._ser = self._ser, None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
            self._emitir("estado", False)

    def _bucle(self):
        while self._activo:
            puerto = self._puerto
            if self._ser is None:
                if puerto is None:
                    time.sleep(0.05)
                    continue
                try:
                    ser = self._fabrica(puerto)
                    with self._cerrojo:
                        self._ser = ser
                    self._emitir("estado", True)
                except Exception as error:
                    self._emitir("error", str(error))
                    time.sleep(1.0)
                continue
            try:
                crudo = self._ser.readline()
                if crudo:
                    self._emitir("linea", crudo.decode("utf-8", errors="replace").strip())
            except Exception as error:
                if self._ser is not None:
                    self._emitir("error", str(error))
                self._soltar_puerto()
                time.sleep(0.5)


def listar_puertos():
    if serial is None:
        return []
    return sorted(p.device for p in serial.tools.list_ports.comports())


# =============================================================================
# Interfaz grafica
# =============================================================================
COLOR_FONDO = "#161822"
COLOR_TARJETA = "#212433"
COLOR_TEXTO = "#e2e8f0"
COLOR_TENUE = "#94a3b8"
COLOR_ACENTO = "#00f5d4"
COLOR_BOTON = "#334155"
COLOR_NIVEL = {"ok": "#34d399", "aviso": "#fbbf24", "falla": "#f87171"}
MARCA_NIVEL = {"ok": "OK", "aviso": "!", "falla": "X"}
FUENTE = "Segoe UI"
FUENTE_DATOS = "Consolas"


def tarjeta(padre, titulo):
    marco = tk.Frame(padre, bg=COLOR_TARJETA, padx=10, pady=8)
    tk.Label(marco, text=titulo, bg=COLOR_TARJETA, fg=COLOR_ACENTO, font=(FUENTE, 10, "bold")).pack(anchor="w")
    return marco


def boton(padre, texto, comando, bg=COLOR_BOTON, fg="#ffffff"):
    return tk.Button(padre, text=texto, command=comando, bg=bg, fg=fg, relief="flat", padx=8, pady=3,
                     font=(FUENTE, 9, "bold"), takefocus=0, activebackground="#475569")


class PanelSenales:
    """Fila de indicadores. Cada uno lleva marca y texto: no depende solo del color."""

    def __init__(self, padre):
        self.filas = {}
        self.padre = padre

    def actualizar(self, senales):
        for nombre, nivel, detalle in senales:
            if nombre not in self.filas:
                fila = tk.Frame(self.padre, bg=COLOR_TARJETA)
                fila.pack(fill="x", pady=1)
                marca = tk.Label(fila, width=3, font=(FUENTE_DATOS, 9, "bold"), fg="#0f172a")
                marca.pack(side="left", padx=(0, 6))
                tk.Label(fila, text=nombre, width=12, anchor="w", bg=COLOR_TARJETA, fg=COLOR_TEXTO,
                         font=(FUENTE, 9, "bold")).pack(side="left")
                texto = tk.Label(fila, anchor="w", bg=COLOR_TARJETA, fg=COLOR_TENUE, font=(FUENTE, 9))
                texto.pack(side="left", fill="x", expand=True)
                self.filas[nombre] = (marca, texto)
            marca, texto = self.filas[nombre]
            marca.config(text=MARCA_NIVEL[nivel], bg=COLOR_NIVEL[nivel])
            texto.config(text=detalle)


class HMIRover:
    TECLAS = ("w", "a", "s", "d", "q", "e", "space")

    def __init__(self, root, fabrica_serie=None):
        self.root = root
        self.root.title(f"HMI Rover Lunar {VERSION_HMI}")
        self.root.geometry("1120x760")
        self.root.minsize(1020, 700)
        self.root.configure(bg=COLOR_FONDO)

        self.eventos = queue.Queue()
        self.estado = EstadoEnlace()
        self.enlace = EnlaceSerie("TX", self.eventos, fabrica_serie)
        self.teclas = {k: False for k in self.TECLAS}
        self.etiqueta = "REPOSO"
        self.consigna = Consigna()
        self._cerrojo_consigna = threading.Lock()
        self._parada_pendiente = threading.Event()
        self._ultima_consulta_id = 0.0
        self._activo = True

        self.modo = tk.StringVar(value="ACKERMANN")
        self.pot_izq = tk.IntVar(value=150)
        self.pot_der = tk.IntVar(value=150)
        self.angulos = [tk.IntVar(value=ANGULO_CENTRO) for _ in range(4)]
        self.inv_servos = tk.BooleanVar(value=False)
        self.inv_izq = tk.BooleanVar(value=False)
        self.inv_der = tk.BooleanVar(value=False)

        self._crear_interfaz()
        self.refrescar_puertos()
        self.recalcular()

        self.root.bind("<KeyPress>", self._tecla_abajo)
        self.root.bind("<KeyRelease>", self._tecla_arriba)
        self.root.bind("<FocusOut>", self._foco_perdido)
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar)

        threading.Thread(target=self._bucle_envio, daemon=True).start()
        self._ciclo_interfaz()

    # --- Construccion -------------------------------------------------------
    def _crear_interfaz(self):
        barra = tk.Frame(self.root, bg=COLOR_TARJETA, padx=10, pady=6)
        barra.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(barra, text="ROVER LUNAR", bg=COLOR_TARJETA, fg="#ffffff",
                 font=(FUENTE, 12, "bold")).pack(side="left", padx=(0, 14))
        tk.Label(barra, text="Puerto del transmisor:", bg=COLOR_TARJETA, fg=COLOR_TEXTO,
                 font=(FUENTE, 9)).pack(side="left")
        self.cb_puerto = ttk.Combobox(barra, width=12, state="readonly", takefocus=0)
        self.cb_puerto.pack(side="left", padx=4)
        boton(barra, "Refrescar", self.refrescar_puertos).pack(side="left", padx=2)
        self.btn_conectar = boton(barra, "CONECTAR", self.alternar_conexion, COLOR_ACENTO, "#0f172a")
        self.btn_conectar.pack(side="left", padx=6)
        tk.Label(barra, text="Modo:", bg=COLOR_TARJETA, fg=COLOR_TEXTO, font=(FUENTE, 9)).pack(side="left", padx=(14, 2))
        cb_modo = ttk.Combobox(barra, width=13, values=MODOS, state="readonly", textvariable=self.modo, takefocus=0)
        cb_modo.pack(side="left")
        cb_modo.bind("<<ComboboxSelected>>", lambda _: self._modo_cambiado())
        boton(barra, "PARADA", self.parada_emergencia, "#e63946").pack(side="right")

        self.lbl_alerta = tk.Label(self.root, text="", bg=COLOR_FONDO, fg="#fbbf24", font=(FUENTE, 10, "bold"))
        self.lbl_alerta.pack(fill="x", padx=10)

        consola = tarjeta(self.root, "REGISTRO")
        consola.pack(side="bottom", fill="x", padx=10, pady=(4, 8))
        self.txt = tk.Text(consola, height=6, bg="#07080d", fg=COLOR_TEXTO, font=(FUENTE_DATOS, 9),
                           relief="flat", takefocus=0, state="disabled")
        self.txt.pack(fill="x")

        cuerpo = tk.Frame(self.root, bg=COLOR_FONDO)
        cuerpo.pack(fill="both", expand=True, padx=10)
        for c in range(3):
            cuerpo.columnconfigure(c, weight=1, uniform="col")
        cuerpo.rowconfigure(0, weight=1)

        col_a = tk.Frame(cuerpo, bg=COLOR_FONDO)
        col_a.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        col_b = tk.Frame(cuerpo, bg=COLOR_FONDO)
        col_b.grid(row=0, column=1, sticky="nsew", padx=5)
        col_c = tk.Frame(cuerpo, bg=COLOR_FONDO)
        col_c.grid(row=0, column=2, sticky="nsew", padx=(5, 0))

        t_senales = tarjeta(col_a, "ESTADO DE LA CONEXION")
        t_senales.pack(fill="x", pady=(0, 8))
        self.panel_senales = PanelSenales(t_senales)

        t_tx = tarjeta(col_a, "LO TRANSMITIDO")
        t_tx.pack(fill="x", pady=(0, 8))
        self.lbl_tx = tk.Label(t_tx, justify="left", anchor="w", bg=COLOR_TARJETA, fg=COLOR_TEXTO, font=(FUENTE_DATOS, 10))
        self.lbl_tx.pack(fill="x")

        t_rx = tarjeta(col_a, "APLICADO EN EL EJECUTOR")
        t_rx.pack(fill="both", expand=True)
        self.lbl_rx = tk.Label(t_rx, justify="left", anchor="nw", bg=COLOR_TARJETA, fg=COLOR_TEXTO, font=(FUENTE_DATOS, 10))
        self.lbl_rx.pack(fill="both", expand=True)

        t_rover = tarjeta(col_b, "ROVER")
        t_rover.pack(fill="x", pady=(0, 8))
        self.lbl_cmd = tk.Label(t_rover, text="REPOSO", bg=COLOR_TARJETA, fg="#ffffff", font=(FUENTE, 11, "bold"))
        self.lbl_cmd.pack()
        self.canvas = tk.Canvas(t_rover, width=230, height=210, bg="#0c0e17", highlightthickness=0)
        self.canvas.pack(pady=4)

        t_mando = tarjeta(col_b, "MANDO (teclado o botones)")
        t_mando.pack(fill="both", expand=True)
        grilla = tk.Frame(t_mando, bg=COLOR_TARJETA)
        grilla.pack(pady=6)
        self.botones = {}
        disposicion = (("q", "Q piv", 0, 0), ("w", "W", 0, 1), ("e", "E piv", 0, 2),
                       ("a", "A", 1, 0), ("s", "S", 1, 1), ("d", "D", 1, 2))
        for tecla, texto, fila, col in disposicion:
            b = tk.Button(grilla, text=texto, width=7, height=2, bg=COLOR_BOTON, fg="#ffffff", relief="flat",
                          font=(FUENTE, 9, "bold"), takefocus=0)
            b.grid(row=fila, column=col, padx=2, pady=2)
            b.bind("<ButtonPress-1>", lambda _, k=tecla: self._fijar_tecla(k, True))
            b.bind("<ButtonRelease-1>", lambda _, k=tecla: self._fijar_tecla(k, False))
            self.botones[tecla] = b
        ayuda = ("A D Q E orientan las ruedas sin moverse.\n"
                 "W S mueven los motores. Combinar: A+W gira, Q+W pivota.\n"
                 "Espacio: parada")
        tk.Label(t_mando, text=ayuda, justify="center", bg=COLOR_TARJETA, fg=COLOR_TENUE, font=(FUENTE, 8)).pack()

        t_trac = tarjeta(col_c, "POTENCIA DE TRACCION (PWM)")
        t_trac.pack(fill="x", pady=(0, 8))
        for texto, var in (("Izquierda", self.pot_izq), ("Derecha", self.pot_der)):
            self._deslizador(t_trac, texto, var, 0, PWM_MAX)
        fila = tk.Frame(t_trac, bg=COLOR_TARJETA)
        fila.pack(fill="x")
        self._casilla(fila, "Invertir izq", self.inv_izq).pack(side="left")
        self._casilla(fila, "Invertir der", self.inv_der).pack(side="left", padx=8)

        t_serv = tarjeta(col_c, "DIRECCION (sliders en modo MANUAL)")
        t_serv.pack(fill="both", expand=True)
        nombres = ("S1 Del. Izq", "S2 Del. Der", "S3 Tras. Izq", "S4 Tras. Der")
        for texto, var in zip(nombres, self.angulos):
            self._deslizador(t_serv, texto, var, ANGULO_MIN, ANGULO_MAX)
        self._casilla(t_serv, "Invertir direccion", self.inv_servos).pack(anchor="w")
        boton(t_serv, "Centrar servos", self.centrar_servos).pack(anchor="w", pady=4)

    def _deslizador(self, padre, texto, var, minimo, maximo):
        fila = tk.Frame(padre, bg=COLOR_TARJETA)
        fila.pack(fill="x")
        tk.Label(fila, text=texto, width=11, anchor="w", bg=COLOR_TARJETA, fg=COLOR_TEXTO, font=(FUENTE, 9)).pack(side="left")
        tk.Scale(fila, from_=minimo, to=maximo, orient="horizontal", variable=var, bg=COLOR_TARJETA, fg=COLOR_TEXTO,
                 highlightthickness=0, takefocus=0, length=170, sliderlength=16, font=(FUENTE_DATOS, 8),
                 troughcolor="#0c0e17", command=lambda _: self.recalcular()).pack(side="left", fill="x", expand=True)

    def _casilla(self, padre, texto, var):
        return tk.Checkbutton(padre, text=texto, variable=var, command=self.recalcular, bg=COLOR_TARJETA, fg=COLOR_TEXTO,
                              selectcolor=COLOR_FONDO, activebackground=COLOR_TARJETA, activeforeground=COLOR_TEXTO,
                              font=(FUENTE, 8), takefocus=0)

    # --- Conexion -----------------------------------------------------------
    def refrescar_puertos(self):
        puertos = listar_puertos()
        self.cb_puerto["values"] = puertos
        if puertos and self.cb_puerto.get() not in puertos:
            self.cb_puerto.set(puertos[0])

    def alternar_conexion(self):
        if serial is None and self.enlace._fabrica == EnlaceSerie._abrir_puerto_real:
            messagebox.showerror("Falta pyserial", "Instale pyserial: pip install pyserial")
            return
        if self.enlace._puerto is not None:
            self.enlace.escribir("STOP\n")
            self.enlace.cerrar()
            self.btn_conectar.config(text="CONECTAR", bg=COLOR_ACENTO, fg="#0f172a")
            self.registrar("Desconectado por el usuario.")
            return
        puerto = self.cb_puerto.get()
        if not puerto:
            messagebox.showwarning("Puerto", "Seleccione el puerto del transmisor.")
            return
        self.enlace.abrir(puerto)
        self.btn_conectar.config(text="DESCONECTAR", bg="#e63946", fg="#ffffff")
        self.registrar(f"Abriendo {puerto}...")

    # --- Mando --------------------------------------------------------------
    def _tecla_abajo(self, evento):
        k = evento.keysym.lower()
        if k in self.teclas and not self.teclas[k]:  # Ignora la autorepeticion del sistema
            self._fijar_tecla(k, True)

    def _tecla_arriba(self, evento):
        k = evento.keysym.lower()
        if k in self.teclas:
            self._fijar_tecla(k, False)

    def _foco_perdido(self, evento):
        # Sin foco no llegaria el KeyRelease y el rover seguiria en marcha
        if evento.widget is self.root:
            for k in self.teclas:
                self.teclas[k] = False
            self.recalcular()

    def _fijar_tecla(self, tecla, valor):
        self.teclas[tecla] = valor
        if tecla == "space" and valor:
            self._parada_pendiente.set()
        self.recalcular()

    def _modo_cambiado(self):
        self.registrar(f"Modo: {self.modo.get()}")
        self.recalcular()

    def centrar_servos(self):
        for var in self.angulos:
            var.set(ANGULO_CENTRO)
        self.recalcular()

    def parada_emergencia(self):
        for k in self.teclas:
            self.teclas[k] = False
        self._parada_pendiente.set()
        self.registrar("PARADA solicitada.")
        self.recalcular()

    def recalcular(self):
        etiqueta, consigna = calcular_consigna(
            self.teclas, self.modo.get(), self.pot_izq.get(), self.pot_der.get(),
            [v.get() for v in self.angulos], self.inv_servos.get(), self.inv_izq.get(), self.inv_der.get())
        with self._cerrojo_consigna:
            self.consigna = consigna
        self.etiqueta = etiqueta
        self.lbl_cmd.config(text=etiqueta)
        for k, b in self.botones.items():
            activo = self.teclas[k]
            b.config(bg=COLOR_ACENTO if activo else COLOR_BOTON, fg="#0f172a" if activo else "#ffffff")
        self._dibujar_rover(consigna)

    def _bucle_envio(self):
        """Envio a 20 Hz en hilo propio: arrastrar la ventana no detiene el flujo."""
        while self._activo:
            inicio = time.monotonic()
            if self.enlace.conectado:
                if self._parada_pendiente.is_set():
                    self._parada_pendiente.clear()
                    self.enlace.escribir("STOP\n")
                with self._cerrojo_consigna:
                    linea = self.consigna.linea()
                self.enlace.escribir(linea)
            time.sleep(max(0.0, PERIODO_ENVIO_S - (time.monotonic() - inicio)))

    # --- Ciclo de interfaz --------------------------------------------------
    def _ciclo_interfaz(self):
        if not self._activo:
            return
        self._procesar_eventos()
        ahora = time.monotonic()
        if self.enlace.conectado and not self.estado.id_placa and ahora - self._ultima_consulta_id > 1.5:
            self._ultima_consulta_id = ahora
            self.enlace.escribir("IDENT\n")
        self._refrescar_datos()
        self._id_ciclo = self.root.after(100, self._ciclo_interfaz)

    def _procesar_eventos(self):
        while True:
            try:
                _, tipo, valor, _ = self.eventos.get_nowait()
            except queue.Empty:
                return
            if tipo == "estado":
                self.estado.registrar_usb(valor, self.cb_puerto.get() if valor else "")
                self.registrar("Puerto abierto." if valor else "Puerto cerrado.")
            elif tipo == "error":
                self.registrar(f"Error de puerto: {valor}")
            elif tipo == "linea":
                mensaje = parsear_linea(valor)
                self.estado.procesar(mensaje)
                if mensaje.tipo in ("ID", "TEXTO"):
                    self.registrar(valor)

    def _refrescar_datos(self):
        est = self.estado
        self.panel_senales.actualizar(est.senales())
        self.lbl_alerta.config(text=est.alerta_reinicio())

        if est.ultimo_tx:
            t = est.ultimo_tx
            self.lbl_tx.config(text=(
                f"Trama    #{t['seq']}   {est.tasa_envio_hz()} Hz\n"
                f"Motores  Izq {t['izq']:>5}  Der {t['der']:>5}\n"
                f"Servos   {t['s1']:>3} {t['s2']:>3} {t['s3']:>3} {t['s4']:>3}"))
        else:
            self.lbl_tx.config(text="Sin datos del transmisor")

        if est.ultima_tlm and est.telemetria_vigente():
            r = est.ultima_tlm
            self.lbl_rx.config(text=(
                f"Trama    #{r['seq']}\n"
                f"Motores  Izq {r['apl_izq']:>5}  Der {r['apl_der']:>5}\n"
                f"Servos   {r['a1']:>3} {r['a2']:>3} {r['a3']:>3} {r['a4']:>3}\n"
                f"Perdidas {est.porcentaje_perdidas():.1f} %\n"
                f"Failsafe {r['failsafes']}\n"
                f"Encendido hace {r['uptime'] // 1000} s\n"
                f"Ultimo reinicio: {CAUSAS_RESET.get(r['causa'], r['causa'])}"))
        else:
            self.lbl_rx.config(text="Sin datos del ejecutor")

    def registrar(self, texto):
        self.txt.config(state="normal")
        self.txt.insert("end", time.strftime("[%H:%M:%S] ") + texto + "\n")
        if int(self.txt.index("end-1c").split(".")[0]) > 500:
            self.txt.delete("1.0", "100.0")
        self.txt.see("end")
        self.txt.config(state="disabled")

    # --- Dibujo ---------------------------------------------------------------
    def _dibujar_rover(self, consigna):
        c = self.canvas
        c.delete("all")
        cx, cy = 115, 105
        c.create_rectangle(cx - 34, cy - 56, cx + 34, cy + 56, fill="#1e293b", outline=COLOR_ACENTO, width=2)
        c.create_text(cx, cy, text="ROCKER\nBOGIE", fill=COLOR_ACENTO, font=(FUENTE, 8, "bold"), justify="center")
        s1, s2, s3, s4 = consigna.servos
        ruedas = (
            (cx - 60, cy - 52, s1, consigna.izq), (cx + 60, cy - 52, s2, consigna.der),
            (cx - 60, cy, 90, consigna.izq), (cx + 60, cy, 90, consigna.der),
            (cx - 60, cy + 52, s3, consigna.izq), (cx + 60, cy + 52, s4, consigna.der),
        )
        for x, y, angulo, pwm in ruedas:
            self._dibujar_rueda(x, y, angulo, pwm)

    def _dibujar_rueda(self, x, y, angulo, pwm):
        color = "#34d399" if pwm > 0 else ("#f97316" if pwm < 0 else "#64748b")
        tita = math.radians(90.0 - angulo)
        cos_t, sin_t = math.cos(tita), math.sin(tita)
        puntos = []
        for lx, ly in ((-7, -13), (7, -13), (7, 13), (-7, 13)):
            puntos += [x + lx * cos_t - ly * sin_t, y + lx * sin_t + ly * cos_t]
        self.canvas.create_polygon(puntos, fill=color, outline="#ffffff")
        if pwm:
            signo = 1.0 if pwm > 0 else -1.0
            largo = 16 + 12 * min(PWM_MAX, abs(pwm)) / PWM_MAX
            self.canvas.create_line(x, y, x + signo * largo * sin_t, y - signo * largo * cos_t,
                                    fill="#ffffff", width=2, arrow=tk.LAST)

    # --- Cierre -------------------------------------------------------------
    def cerrar(self):
        self._activo = False
        self.root.after_cancel(self._id_ciclo)
        if self.enlace.conectado:
            self.enlace.escribir("STOP\n")
        self.enlace.terminar()
        self.root.destroy()


def main():
    if tk is None:
        raise SystemExit("Tkinter no esta disponible en este Python.")
    root = tk.Tk()
    HMIRover(root)
    root.mainloop()


if __name__ == "__main__":
    main()
