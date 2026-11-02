#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HMI de diagnostico del Rover Lunar (v3.0).

Conecta a la vez el transmisor y el ejecutor a la PC, compara trama por trama lo que se
envia con lo que llega y lo grafica. Marca en las graficas cada reinicio del ejecutor.

Uso en banco. Con el ejecutor conectado por USB, verificar que la alimentacion de motores
y servos siga siendo independiente: el USB no puede alimentarlos.

Reutiliza protocolo, puerto serie y cinematica de HMI_Rover.py.
"""

import csv
import math
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None

from HMI_Rover import (ANGULO_CENTRO, ANGULO_MAX, ANGULO_MIN, CAUSA_BROWNOUT, CAUSAS_RESET, COLOR_ACENTO, COLOR_BOTON,
                       COLOR_FONDO, COLOR_TARJETA, COLOR_TENUE, COLOR_TEXTO, ESTADOS_EJECUTOR, FUENTE, FUENTE_DATOS,
                       PERIODO_ENVIO_S, PWM_MAX, VERSION_HMI, Consigna, EnlaceSerie, PanelSenales, boton, listar_puertos,
                       parsear_linea, serial, tarjeta)

VENTANA_S = 20.0            # Tiempo visible en las graficas
ESPERA_PERDIDA_S = 1.0      # Una trama sin respuesta tras este tiempo cuenta como perdida
LIMITE_MUESTRAS = 4000
HUECO_MAXIMO_S = 0.5        # Sin datos durante mas tiempo: la linea se corta

# Series. Paleta validada para fondo oscuro (ordenes y contraste controlados por script)
COLOR_GRAFICA = "#1a1a19"
COLOR_EJE = "#3a3a38"
COLOR_TEXTO_EJE = "#c3c2b7"
SERIE_ENVIADO = "#3987e5"
SERIE_RECIBIDO = "#d95926"
SERIE_APLICADO = "#199e70"
COLOR_REINICIO = "#e66767"


# =============================================================================
# Comparacion de lo enviado con lo recibido (sin interfaz: se prueba por separado)
# =============================================================================
@dataclass
class Metricas:
    enviadas: int = 0
    recibidas: int = 0
    perdidas: int = 0
    diferencias: int = 0
    latencia_ms: float = 0.0
    latencia_max_ms: float = 0.0

    @property
    def porcentaje_perdidas(self):
        total = self.recibidas + self.perdidas
        return 100.0 * self.perdidas / total if total else 0.0


class Comparador:
    """Empareja por numero de secuencia las lineas TX del transmisor y RX del ejecutor."""

    CLAVES = ("izq", "der", "s1", "s2", "s3", "s4")

    def __init__(self):
        self.metricas = Metricas()
        self._pendientes = {}          # seq -> (instante, datos TX)
        self._rx_adelantadas = {}      # seq -> (instante, datos RX)
        self._latencias = deque(maxlen=100)
        self.ultima_diferencia = None

    def reiniciar(self):
        self.__init__()

    def registrar_tx(self, datos, instante):
        if not datos["ok"]:
            return
        self.metricas.enviadas += 1
        adelantada = self._rx_adelantadas.pop(datos["seq"], None)
        if adelantada:  # Los dos puertos se leen en hilos separados: RX puede llegar antes
            self._emparejar(datos, instante, adelantada[1], adelantada[0])
        else:
            self._pendientes[datos["seq"]] = (instante, datos)

    def registrar_rx(self, datos, instante):
        self.metricas.recibidas += 1
        pendiente = self._pendientes.pop(datos["seq"], None)
        if pendiente:
            self._emparejar(pendiente[1], pendiente[0], datos, instante)
        else:
            self._rx_adelantadas[datos["seq"]] = (instante, datos)

    def _emparejar(self, tx, t_tx, rx, t_rx):
        latencia = max(0.0, (t_rx - t_tx) * 1000.0)
        self._latencias.append(latencia)
        m = self.metricas
        m.latencia_ms = sum(self._latencias) / len(self._latencias)
        m.latencia_max_ms = max(m.latencia_max_ms, latencia)
        if any(tx[c] != rx[c] for c in self.CLAVES):
            m.diferencias += 1
            self.ultima_diferencia = (tx, rx)

    def vencer(self, ahora):
        """Cuenta como perdidas las tramas sin respuesta y limpia las RX sin pareja."""
        limite = ahora - ESPERA_PERDIDA_S
        for seq in [s for s, (t, _) in self._pendientes.items() if t < limite]:
            del self._pendientes[seq]
            self.metricas.perdidas += 1
        for seq in [s for s, (t, _) in self._rx_adelantadas.items() if t < limite]:
            del self._rx_adelantadas[seq]


class Series:
    """Historial de muestras (instante, valor) para graficar."""

    NOMBRES = ("izq", "der", "s1", "s2", "s3", "s4")

    def __init__(self):
        self.enviado = {n: deque(maxlen=LIMITE_MUESTRAS) for n in self.NOMBRES}
        self.recibido = {n: deque(maxlen=LIMITE_MUESTRAS) for n in self.NOMBRES}
        self.aplicado = {n: deque(maxlen=LIMITE_MUESTRAS) for n in self.NOMBRES}
        self.latencia = deque(maxlen=LIMITE_MUESTRAS)
        self.rssi = deque(maxlen=LIMITE_MUESTRAS)
        self.reinicios = deque(maxlen=200)   # (instante, texto)

    def agregar_tx(self, d, t):
        for n in self.NOMBRES:
            self.enviado[n].append((t, d[n]))

    def agregar_rx(self, d, t):
        for n in self.NOMBRES:
            self.recibido[n].append((t, d[n]))
        self.agregar_aplicado(d, t)

    def agregar_aplicado(self, d, t):
        for n, c in zip(self.NOMBRES, ("apl_izq", "apl_der", "a1", "a2", "a3", "a4")):
            self.aplicado[n].append((t, d[c]))


def segmentar(datos, t_ini, hueco_max=HUECO_MAXIMO_S):
    """Separa las muestras visibles en tramos continuos. Unir un hueco ocultaria un reinicio."""
    tramos, actual, t_previo = [], [], None
    for t, v in datos:
        if t < t_ini:
            continue
        if t_previo is not None and t - t_previo > hueco_max:
            tramos.append(actual)
            actual = []
        actual.append((t, v))
        t_previo = t
    if actual:
        tramos.append(actual)
    return tramos


def perfil_prueba(nombre, t):
    """Consigna de prueba en el instante t (s). None en modo manual."""
    if nombre == "Escalon motores":
        v = 150 if int(t / 3.0) % 2 else 0
        return Consigna(v, v)
    if nombre == "Inversion motores":
        v = 150 if int(t / 3.0) % 2 else -150
        return Consigna(v, v)
    if nombre == "Seno motores":
        v = int(200 * math.sin(2 * math.pi * t / 8.0))
        return Consigna(v, v)
    if nombre == "Barrido servos":
        a = int(90 + 60 * math.sin(2 * math.pi * t / 6.0))
        return Consigna(0, 0, (a, a, a, a))
    if nombre == "Esfuerzo total":
        fase = int(t / 3.0) % 2
        v = 200 if fase else -200
        a = 140 if fase else 40
        return Consigna(v, v, (a, a, a, a))
    return None


PERFILES = ("Manual", "Escalon motores", "Inversion motores", "Seno motores", "Barrido servos", "Esfuerzo total")


# =============================================================================
# Grafica sobre Canvas de Tk
# =============================================================================
class Grafica:
    MARGEN_IZQ, MARGEN_DER, MARGEN_SUP, MARGEN_INF = 34, 8, 20, 16

    def __init__(self, padre, titulo, minimo, maximo, marcas):
        self.titulo = titulo
        self.minimo, self.maximo = minimo, maximo
        self.marcas = marcas
        self.canvas = tk.Canvas(padre, bg=COLOR_GRAFICA, highlightthickness=0, height=130)
        self.series = []
        self.reinicios = []
        self.t_fin = 0.0
        self._cursor_x = None
        self.canvas.bind("<Motion>", self._mover)
        self.canvas.bind("<Leave>", self._salir)

    def _mover(self, evento):
        self._cursor_x = evento.x
        self.dibujar()

    def _salir(self, _):
        self._cursor_x = None
        self.dibujar()

    def _x(self, t, ancho):
        util = ancho - self.MARGEN_IZQ - self.MARGEN_DER
        return self.MARGEN_IZQ + util * (1.0 - (self.t_fin - t) / VENTANA_S)

    def _y(self, v, alto):
        util = alto - self.MARGEN_SUP - self.MARGEN_INF
        return self.MARGEN_SUP + util * (1.0 - (v - self.minimo) / (self.maximo - self.minimo))

    def fijar(self, series, reinicios, t_fin):
        self.series = series          # lista de (nombre, color, grosor, datos)
        self.reinicios = reinicios
        self.t_fin = t_fin

    def dibujar(self):
        c = self.canvas
        ancho, alto = c.winfo_width(), c.winfo_height()
        if ancho < 40 or alto < 40:
            return
        c.delete("all")

        for marca in self.marcas:
            y = self._y(marca, alto)
            c.create_line(self.MARGEN_IZQ, y, ancho - self.MARGEN_DER, y, fill=COLOR_EJE)
            c.create_text(self.MARGEN_IZQ - 4, y, text=str(marca), anchor="e", fill=COLOR_TEXTO_EJE, font=(FUENTE_DATOS, 7))

        t_ini = self.t_fin - VENTANA_S
        for t_r, texto in self.reinicios:
            if t_r >= t_ini:
                x = self._x(t_r, ancho)
                c.create_line(x, self.MARGEN_SUP, x, alto - self.MARGEN_INF, fill=COLOR_REINICIO, width=2)
                c.create_text(x + 3, self.MARGEN_SUP, text=texto, anchor="nw", fill=COLOR_TEXTO, font=(FUENTE, 7, "bold"))

        ultimos = []
        for nombre, color, grosor, datos in self.series:
            for tramo in segmentar(datos, t_ini):
                puntos = []
                for t, v in tramo:
                    puntos += [self._x(t, ancho), self._y(max(self.minimo, min(self.maximo, v)), alto)]
                if len(puntos) >= 4:
                    c.create_line(puntos, fill=color, width=grosor)
            if datos:
                ultimos.append(f"{nombre} {datos[-1][1]}")

        c.create_text(self.MARGEN_IZQ, 3, text=self.titulo, anchor="nw", fill=COLOR_TEXTO, font=(FUENTE, 8, "bold"))
        c.create_text(ancho - self.MARGEN_DER, 3, text="  ".join(ultimos), anchor="ne", fill=COLOR_TEXTO_EJE,
                      font=(FUENTE_DATOS, 8))
        c.create_text(self.MARGEN_IZQ, alto - 2, text=f"-{VENTANA_S:.0f} s", anchor="sw", fill=COLOR_TEXTO_EJE, font=(FUENTE_DATOS, 7))
        c.create_text(ancho - self.MARGEN_DER, alto - 2, text="ahora", anchor="se", fill=COLOR_TEXTO_EJE, font=(FUENTE_DATOS, 7))

        if self._cursor_x is not None and self.MARGEN_IZQ <= self._cursor_x <= ancho - self.MARGEN_DER:
            self._dibujar_cursor(ancho, alto)

    def _dibujar_cursor(self, ancho, alto):
        c = self.canvas
        x = self._cursor_x
        util = ancho - self.MARGEN_IZQ - self.MARGEN_DER
        t = self.t_fin - VENTANA_S * (1.0 - (x - self.MARGEN_IZQ) / util)
        c.create_line(x, self.MARGEN_SUP, x, alto - self.MARGEN_INF, fill=COLOR_TEXTO_EJE)
        lineas = [f"-{self.t_fin - t:.1f} s"]
        for nombre, _, _, datos in self.series:
            cercano = min(datos, key=lambda m: abs(m[0] - t), default=None)
            if cercano is not None and abs(cercano[0] - t) < 0.5:
                lineas.append(f"{nombre}: {cercano[1]}")
        izquierda = x > ancho / 2
        ident = c.create_text(x - 6 if izquierda else x + 6, self.MARGEN_SUP + 2, text="\n".join(lineas),
                              anchor="ne" if izquierda else "nw", fill=COLOR_TEXTO, font=(FUENTE_DATOS, 8))
        caja = c.create_rectangle(*c.bbox(ident), fill="#000000", outline=COLOR_EJE)
        c.tag_lower(caja, ident)


# =============================================================================
# Aplicacion
# =============================================================================
class HMIRoverDebug:
    def __init__(self, root, fabrica_serie=None):
        self.root = root
        self.root.title(f"HMI Rover Lunar {VERSION_HMI} - DEBUG")
        self.root.geometry("1360x860")
        self.root.minsize(1180, 760)
        self.root.configure(bg=COLOR_FONDO)

        self.eventos = queue.Queue()
        self.enlace_tx = EnlaceSerie("TX", self.eventos, fabrica_serie)
        self.enlace_rx = EnlaceSerie("RX", self.eventos, fabrica_serie)
        self.fabrica_serie = fabrica_serie
        self.comparador = Comparador()
        self.series = Series()
        self.registro_csv = deque(maxlen=200000)
        self.ids = {"TX": None, "RX": None}
        self.usb = {"TX": False, "RX": False}
        self.t_ultimo = {"TX": None, "RX": None, "TLM": None}
        self.ultima_tlm = None
        self.clientes = 0
        self.uptime_previo = None
        self.reinicios_vistos = 0
        self._cerrojo = threading.Lock()
        self._activo = True
        self._parada_pendiente = threading.Event()
        self._t0_perfil = time.monotonic()
        self._ultima_consulta = 0.0
        self.pausado = False
        self.t_congelado = 0.0
        self.consigna = Consigna()

        self.izq = tk.IntVar(value=0)
        self.der = tk.IntVar(value=0)
        self.angulos = [tk.IntVar(value=ANGULO_CENTRO) for _ in range(4)]
        self.perfil = tk.StringVar(value="Manual")
        self.emitir = tk.BooleanVar(value=False)
        self.ver_flujo = tk.BooleanVar(value=False)

        self._crear_interfaz()
        self.refrescar_puertos()
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar)
        threading.Thread(target=self._bucle_envio, daemon=True).start()
        self._ciclo()

    # --- Construccion -------------------------------------------------------
    def _crear_interfaz(self):
        barra = tk.Frame(self.root, bg=COLOR_TARJETA, padx=10, pady=6)
        barra.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(barra, text="DEBUG ROVER", bg=COLOR_TARJETA, fg="#ffffff", font=(FUENTE, 12, "bold")).pack(side="left", padx=(0, 12))
        self.combo = {}
        self.btn = {}
        for rol, texto in (("TX", "Transmisor:"), ("RX", "Ejecutor:")):
            tk.Label(barra, text=texto, bg=COLOR_TARJETA, fg=COLOR_TEXTO, font=(FUENTE, 9)).pack(side="left")
            self.combo[rol] = ttk.Combobox(barra, width=10, state="readonly")
            self.combo[rol].pack(side="left", padx=3)
            self.btn[rol] = boton(barra, "Conectar", lambda r=rol: self.alternar(r), COLOR_ACENTO, "#0f172a")
            self.btn[rol].pack(side="left", padx=(0, 12))
        boton(barra, "Refrescar", self.refrescar_puertos).pack(side="left", padx=2)
        boton(barra, "Detectar placas", self.detectar).pack(side="left", padx=2)
        boton(barra, "Pausar graficas", self.alternar_pausa).pack(side="left", padx=2)
        boton(barra, "Reiniciar contadores", self.reiniciar_contadores).pack(side="left", padx=2)
        boton(barra, "Exportar CSV", self.exportar_csv).pack(side="left", padx=2)
        boton(barra, "PARADA", self.parada, "#e63946").pack(side="right")

        self.lbl_alerta = tk.Label(self.root, text="", bg=COLOR_FONDO, fg="#fbbf24", font=(FUENTE, 10, "bold"))
        self.lbl_alerta.pack(fill="x", padx=8)

        cuerpo = tk.Frame(self.root, bg=COLOR_FONDO)
        cuerpo.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        cuerpo.columnconfigure(1, weight=1)
        cuerpo.rowconfigure(0, weight=1)

        lateral = tk.Frame(cuerpo, bg=COLOR_FONDO, width=300)
        lateral.grid(row=0, column=0, sticky="ns", padx=(0, 8))

        t_est = tarjeta(lateral, "CONEXION")
        t_est.pack(fill="x", pady=(0, 6))
        self.panel = PanelSenales(t_est)

        t_cmp = tarjeta(lateral, "ENVIADO FRENTE A RECIBIDO")
        t_cmp.pack(fill="x", pady=(0, 6))
        self.lbl_cmp = tk.Label(t_cmp, justify="left", anchor="w", bg=COLOR_TARJETA, fg=COLOR_TEXTO, font=(FUENTE_DATOS, 9))
        self.lbl_cmp.pack(fill="x")

        t_ctl = tarjeta(lateral, "ESTIMULO")
        t_ctl.pack(fill="x")
        tk.Checkbutton(t_ctl, text="Emitir consignas", variable=self.emitir, bg=COLOR_TARJETA, fg=COLOR_TEXTO,
                       selectcolor=COLOR_FONDO, activebackground=COLOR_TARJETA, activeforeground=COLOR_TEXTO,
                       font=(FUENTE, 9, "bold"), takefocus=0).pack(anchor="w")
        fila = tk.Frame(t_ctl, bg=COLOR_TARJETA)
        fila.pack(fill="x", pady=2)
        tk.Label(fila, text="Perfil", width=7, anchor="w", bg=COLOR_TARJETA, fg=COLOR_TEXTO, font=(FUENTE, 9)).pack(side="left")
        cb = ttk.Combobox(fila, values=PERFILES, textvariable=self.perfil, state="readonly", width=20)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda _: self._perfil_cambiado())
        self._deslizador(t_ctl, "Izq", self.izq, -PWM_MAX, PWM_MAX)
        self._deslizador(t_ctl, "Der", self.der, -PWM_MAX, PWM_MAX)
        for i, var in enumerate(self.angulos):
            self._deslizador(t_ctl, f"S{i + 1}", var, ANGULO_MIN, ANGULO_MAX)

        centro = tk.Frame(cuerpo, bg=COLOR_FONDO)
        centro.grid(row=0, column=1, sticky="nsew")

        leyenda = tk.Frame(centro, bg=COLOR_TARJETA, padx=8, pady=4)
        leyenda.pack(fill="x", pady=(0, 4))
        for texto, color in (("Enviado (TX)", SERIE_ENVIADO), ("Recibido (RX)", SERIE_RECIBIDO), ("Aplicado (con rampa)", SERIE_APLICADO)):
            m = tk.Canvas(leyenda, width=20, height=10, bg=COLOR_TARJETA, highlightthickness=0)
            m.create_line(0, 5, 20, 5, fill=color, width=3)
            m.pack(side="left", padx=(0, 4))
            tk.Label(leyenda, text=texto, bg=COLOR_TARJETA, fg=COLOR_TEXTO, font=(FUENTE, 9)).pack(side="left", padx=(0, 14))
        m = tk.Canvas(leyenda, width=4, height=12, bg=COLOR_REINICIO, highlightthickness=0)
        m.pack(side="left", padx=(0, 4))
        tk.Label(leyenda, text="Reinicio del ejecutor", bg=COLOR_TARJETA, fg=COLOR_TEXTO, font=(FUENTE, 9)).pack(side="left")

        rejilla = tk.Frame(centro, bg=COLOR_FONDO)
        rejilla.pack(fill="both", expand=True)
        for c in range(2):
            rejilla.columnconfigure(c, weight=1, uniform="g")
        marcas_pwm = (-255, 0, 255)
        marcas_servo = (10, 90, 170)
        definicion = (("izq", "Motor izquierdo (PWM)", -255, 255, marcas_pwm),
                      ("der", "Motor derecho (PWM)", -255, 255, marcas_pwm),
                      ("s1", "S1 Del. Izq (grados)", 0, 180, marcas_servo),
                      ("s2", "S2 Del. Der (grados)", 0, 180, marcas_servo),
                      ("s3", "S3 Tras. Izq (grados)", 0, 180, marcas_servo),
                      ("s4", "S4 Tras. Der (grados)", 0, 180, marcas_servo))
        self.graficas = {}
        for i, (clave, titulo, mi, ma, marcas) in enumerate(definicion):
            g = Grafica(rejilla, titulo, mi, ma, marcas)
            g.canvas.grid(row=i // 2, column=i % 2, sticky="nsew", padx=2, pady=2)
            rejilla.rowconfigure(i // 2, weight=1)
            self.graficas[clave] = g
        self.g_latencia = Grafica(rejilla, "Latencia TX a RX (ms)", 0, 200, (0, 100, 200))
        self.g_latencia.canvas.grid(row=3, column=0, sticky="nsew", padx=2, pady=2)
        self.g_rssi = Grafica(rejilla, "RSSI del ejecutor (dBm)", -100, -20, (-100, -60, -20))
        self.g_rssi.canvas.grid(row=3, column=1, sticky="nsew", padx=2, pady=2)
        rejilla.rowconfigure(3, weight=1)

        t_log = tarjeta(centro, "REGISTRO DE LOS DOS PUERTOS")
        t_log.pack(fill="x", pady=(4, 0))
        tk.Checkbutton(t_log, text="Mostrar tambien el flujo TX/RX/TLM", variable=self.ver_flujo, bg=COLOR_TARJETA, fg=COLOR_TEXTO,
                       selectcolor=COLOR_FONDO, activebackground=COLOR_TARJETA, activeforeground=COLOR_TEXTO,
                       font=(FUENTE, 8), takefocus=0).pack(anchor="w")
        self.txt = tk.Text(t_log, height=6, bg="#07080d", fg=COLOR_TEXTO, font=(FUENTE_DATOS, 9), relief="flat", state="disabled", takefocus=0)
        self.txt.pack(fill="x")

    def _deslizador(self, padre, texto, var, minimo, maximo):
        fila = tk.Frame(padre, bg=COLOR_TARJETA)
        fila.pack(fill="x")
        tk.Label(fila, text=texto, width=4, anchor="w", bg=COLOR_TARJETA, fg=COLOR_TEXTO, font=(FUENTE, 9)).pack(side="left")
        tk.Scale(fila, from_=minimo, to=maximo, orient="horizontal", variable=var, bg=COLOR_TARJETA, fg=COLOR_TEXTO,
                 highlightthickness=0, takefocus=0, length=210, sliderlength=14, font=(FUENTE_DATOS, 8),
                 troughcolor="#0c0e17", command=lambda _: self._consigna_manual()).pack(side="left", fill="x", expand=True)

    # --- Conexion -----------------------------------------------------------
    def refrescar_puertos(self):
        puertos = listar_puertos()
        for rol in ("TX", "RX"):
            self.combo[rol]["values"] = puertos
            if self.combo[rol].get() not in puertos:
                self.combo[rol].set("")

    def _enlace(self, rol):
        return self.enlace_tx if rol == "TX" else self.enlace_rx

    def alternar(self, rol):
        enlace = self._enlace(rol)
        if enlace._puerto is not None:
            if rol == "TX":
                enlace.escribir("STOP\n")
            enlace.cerrar()
            self.btn[rol].config(text="Conectar", bg=COLOR_ACENTO, fg="#0f172a")
            return
        if serial is None and self.fabrica_serie is None:
            messagebox.showerror("Falta pyserial", "Instale pyserial: pip install pyserial")
            return
        puerto = self.combo[rol].get()
        otro = self.combo["RX" if rol == "TX" else "TX"].get()
        if not puerto:
            messagebox.showwarning("Puerto", "Seleccione un puerto o use Detectar placas.")
            return
        if puerto == otro and self._enlace("RX" if rol == "TX" else "TX")._puerto is not None:
            messagebox.showwarning("Puerto", "Ese puerto ya esta en uso por la otra placa.")
            return
        enlace.abrir(puerto)
        self.btn[rol].config(text="Desconectar", bg="#e63946", fg="#ffffff")

    def detectar(self):
        """Pregunta IDENT en cada puerto libre y asigna cada placa a su rol."""
        if serial is None and self.fabrica_serie is None:
            messagebox.showerror("Falta pyserial", "Instale pyserial: pip install pyserial")
            return
        ocupados = {e._puerto for e in (self.enlace_tx, self.enlace_rx) if e._puerto}
        libres = [p for p in listar_puertos() if p not in ocupados]

        def trabajo():
            hallados = {}
            for puerto in libres:
                rol = identificar_puerto(puerto)
                if rol:
                    hallados[rol] = puerto
            self.eventos.put(("SYS", "detectado", hallados, time.monotonic()))

        self.registrar("SYS", f"Buscando placas en: {', '.join(libres) or 'ninguno'}")
        threading.Thread(target=trabajo, daemon=True).start()

    def _aplicar_deteccion(self, hallados):
        if not hallados:
            self.registrar("SYS", "No se encontraron placas con firmware v3.0.")
        for rol, puerto in hallados.items():
            self.combo[rol].set(puerto)
            self.registrar("SYS", f"{rol} detectado en {puerto}.")
            if self._enlace(rol)._puerto is None:
                self.alternar(rol)

    # --- Estimulo -----------------------------------------------------------
    def _perfil_cambiado(self):
        self._t0_perfil = time.monotonic()
        if self.perfil.get() != "Manual":
            self.emitir.set(False)
            self.registrar("SYS", "Perfil listo. El rover va a moverse al activar Emitir consignas.")
        else:
            self._consigna_manual()

    def _consigna_manual(self):
        with self._cerrojo:
            self.consigna = Consigna(self.izq.get(), self.der.get(), tuple(v.get() for v in self.angulos))

    def parada(self):
        self._emitir_activo = False  # Antes del STOP: ningun CMD del perfil puede salir despues
        self._perfil_actual = "Manual"
        self.emitir.set(False)
        self.perfil.set("Manual")
        self.izq.set(0)
        self.der.set(0)
        for v in self.angulos:
            v.set(ANGULO_CENTRO)
        self._consigna_manual()
        self._parada_pendiente.set()
        self.registrar("SYS", "PARADA solicitada.")

    def _bucle_envio(self):
        while self._activo:
            inicio = time.monotonic()
            if self.enlace_tx.conectado:
                if self._parada_pendiente.is_set():
                    self._parada_pendiente.clear()
                    self.enlace_tx.escribir("STOP\n")
                if self._emitir_activo:
                    consigna = perfil_prueba(self._perfil_actual, inicio - self._t0_perfil)
                    if consigna is None:
                        with self._cerrojo:
                            consigna = self.consigna
                    self.enlace_tx.escribir(consigna.linea())
            time.sleep(max(0.0, PERIODO_ENVIO_S - (time.monotonic() - inicio)))

    # Copias leidas por el hilo de envio: las variables de Tk solo se usan en el hilo principal
    _emitir_activo = False
    _perfil_actual = "Manual"

    # --- Procesamiento --------------------------------------------------------
    def procesar_evento(self, rol, tipo, valor, instante):
        if tipo == "detectado":
            self._aplicar_deteccion(valor)
        elif tipo == "estado":
            self.usb[rol] = valor
            if not valor:
                self.ids[rol] = None
            self.registrar(rol, "Puerto abierto." if valor else "Puerto cerrado.")
        elif tipo == "error":
            self.registrar(rol, f"Error de puerto: {valor}")
        elif tipo == "linea":
            self.procesar_linea(rol, valor, instante)

    def procesar_linea(self, rol, linea, instante):
        m = parsear_linea(linea)
        self.registro_csv.append((f"{instante:.3f}", rol, linea))
        if m.tipo == "ID":
            self.ids[rol] = m.datos
            self.registrar(rol, linea)
            if m.datos["rol"] != rol:
                self.registrar("SYS", f"AVISO: el puerto {rol} tiene conectada la placa {m.datos['rol']}.")
        elif m.tipo == "TX":
            self.t_ultimo["TX"] = instante
            self.series.agregar_tx(m.datos, instante)
            self.comparador.registrar_tx(m.datos, instante)
        elif m.tipo == "RX":
            self.t_ultimo["RX"] = instante
            self.series.agregar_rx(m.datos, instante)
            self.comparador.registrar_rx(m.datos, instante)
            if self.comparador.metricas.latencia_ms:
                self.series.latencia.append((instante, round(self.comparador.metricas.latencia_ms, 1)))
        elif m.tipo == "TLM":
            # Con los dos puertos conectados el mismo dato llega dos veces: se usa solo el directo
            if rol == "RX" or not self.enlace_rx.conectado:
                self._procesar_tlm(m.datos, instante)
        elif m.tipo == "LINK":
            self.clientes = m.datos["clientes"]
        elif m.tipo == "BOOT":
            self._marcar_reinicio(m.datos["causa"], instante)
            self.registrar(rol, f"Arranque del ejecutor. Causa: {CAUSAS_RESET.get(m.datos['causa'], m.datos['causa'])}")
        else:
            self.registrar(rol, linea)
        if self.ver_flujo.get() and m.tipo in ("TX", "RX", "TLM", "LINK"):
            self.registrar(rol, linea)

    def _procesar_tlm(self, d, instante):
        self.t_ultimo["TLM"] = instante
        if self.uptime_previo is not None and d["uptime"] < self.uptime_previo:
            self._marcar_reinicio(d["causa"], instante)
        self.uptime_previo = d["uptime"]
        self.ultima_tlm = d
        self.series.rssi.append((instante, d["rssi"]))
        if not self.enlace_rx.conectado:  # Sin USB en el ejecutor, lo aplicado llega por telemetria
            self.series.agregar_aplicado(d, instante)

    def _marcar_reinicio(self, causa, instante):
        ultimo = self.series.reinicios[-1][0] if self.series.reinicios else -100.0
        if instante - ultimo < 2.0:  # BOOT y telemetria pueden informar el mismo reinicio
            return
        self.series.reinicios.append((instante, CAUSAS_RESET.get(causa, str(causa))))
        self.reinicios_vistos += 1

    def reiniciar_contadores(self):
        self.comparador.reiniciar()
        self.reinicios_vistos = 0
        self.series = Series()
        self.registrar("SYS", "Contadores y graficas reiniciados.")

    # --- Refresco -----------------------------------------------------------
    def senales(self, ahora):
        res = []
        for rol, nombre in (("TX", "Transmisor"), ("RX", "Ejecutor USB")):
            if not self.usb[rol]:
                res.append((nombre, "falla", "Sin conectar"))
            elif not self.ids[rol]:
                res.append((nombre, "aviso", "Esperando respuesta"))
            elif self.ids[rol]["rol"] != rol:
                res.append((nombre, "falla", f"Placa incorrecta ({self.ids[rol]['rol']})"))
            else:
                res.append((nombre, "ok", self.ids[rol]["version"]))
        res.append(("WiFi", "ok", "Ejecutor asociado") if self.clientes else ("WiFi", "falla", "Ejecutor no asociado"))
        t_rx = self.t_ultimo["RX"]
        if self.enlace_rx.conectado:
            if t_rx is not None and ahora - t_rx < 1.0:
                res.append(("Tramas", "ok", "Llegando al ejecutor"))
            else:
                res.append(("Tramas", "falla", "No llegan al ejecutor"))
        t_tlm = self.t_ultimo["TLM"]
        if t_tlm is not None and ahora - t_tlm < 1.0 and self.ultima_tlm:
            estado = self.ultima_tlm["estado"]
            nivel = {2: "ok", 3: "falla"}.get(estado, "aviso")
            res.append(("Estado", nivel, ESTADOS_EJECUTOR.get(estado, "?")))
            if not self.ultima_tlm["diag"] & 1:
                res.append(("PCA9685", "falla", "No responde"))
        else:
            res.append(("Estado", "falla", "Sin telemetria"))
        return res

    def _texto_comparacion(self):
        m = self.comparador.metricas
        tlm = self.ultima_tlm
        lineas = [f"Enviadas     {m.enviadas}",
                  f"Recibidas    {m.recibidas}",
                  f"Perdidas     {m.perdidas} ({m.porcentaje_perdidas:.1f} %)",
                  f"Diferentes   {m.diferencias}",
                  f"Latencia     {m.latencia_ms:.0f} ms (max {m.latencia_max_ms:.0f})",
                  f"Reinicios    {self.reinicios_vistos}"]
        if tlm:
            lineas += [f"Ult. causa   {CAUSAS_RESET.get(tlm['causa'], tlm['causa'])}",
                       f"Encendido    {tlm['uptime'] // 1000} s",
                       f"CRC malos    {tlm['crc_malos']}",
                       f"Failsafes    {tlm['failsafes']}"]
        if self.comparador.ultima_diferencia:
            tx, rx = self.comparador.ultima_diferencia
            lineas.append(f"Ult. dif #{tx['seq']}: {tx['izq']},{tx['der']} / {rx['izq']},{rx['der']}")
        return "\n".join(lineas)

    def _ciclo(self):
        if not self._activo:
            return
        self._emitir_activo = bool(self.emitir.get())
        self._perfil_actual = self.perfil.get()
        for _ in range(2000):
            try:
                rol, tipo, valor, instante = self.eventos.get_nowait()
            except queue.Empty:
                break
            self.procesar_evento(rol, tipo, valor, instante)

        ahora = time.monotonic()
        self.comparador.vencer(ahora)
        if ahora - self._ultima_consulta > 1.5:
            self._ultima_consulta = ahora
            for rol in ("TX", "RX"):
                enlace = self._enlace(rol)
                if enlace.conectado and not self.ids[rol]:
                    enlace.escribir("IDENT\n")

        self.panel.actualizar(self.senales(ahora))
        self.lbl_cmp.config(text=self._texto_comparacion())
        self._actualizar_alerta()
        self._dibujar_graficas(ahora)
        self._id_ciclo = self.root.after(150, self._ciclo)

    def _actualizar_alerta(self):
        tlm = self.ultima_tlm
        if tlm and tlm["causa"] == CAUSA_BROWNOUT:
            self.lbl_alerta.config(text=f"BROWNOUT en el ejecutor: la tension cayo por debajo del umbral. Reinicios vistos: {self.reinicios_vistos}.")
        elif self.reinicios_vistos:
            self.lbl_alerta.config(text=f"El ejecutor se reinicio {self.reinicios_vistos} vez/veces en esta sesion.")
        else:
            self.lbl_alerta.config(text="")

    def _dibujar_graficas(self, ahora):
        if self.pausado:
            t_fin = self.t_congelado
        else:
            t_fin = ahora
        reinicios = list(self.series.reinicios)
        for clave, g in self.graficas.items():
            g.fijar([("Env", SERIE_ENVIADO, 3, self.series.enviado[clave]),
                     ("Rec", SERIE_RECIBIDO, 1, self.series.recibido[clave]),
                     ("Apl", SERIE_APLICADO, 2, self.series.aplicado[clave])], reinicios, t_fin)
            g.dibujar()
        self.g_latencia.fijar([("ms", SERIE_ENVIADO, 2, self.series.latencia)], reinicios, t_fin)
        self.g_latencia.dibujar()
        self.g_rssi.fijar([("dBm", SERIE_ENVIADO, 2, self.series.rssi)], reinicios, t_fin)
        self.g_rssi.dibujar()

    def alternar_pausa(self):
        self.pausado = not self.pausado
        self.t_congelado = time.monotonic()

    def registrar(self, origen, texto):
        self.txt.config(state="normal")
        self.txt.insert("end", time.strftime("[%H:%M:%S] ") + f"{origen:>3} {texto}\n")
        if int(self.txt.index("end-1c").split(".")[0]) > 1000:
            self.txt.delete("1.0", "200.0")
        self.txt.see("end")
        self.txt.config(state="disabled")

    def exportar_csv(self):
        if not self.registro_csv:
            messagebox.showinfo("CSV", "Todavia no hay datos.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile=time.strftime("rover_debug_%Y%m%d_%H%M%S.csv"))
        if ruta:
            with open(ruta, "w", newline="", encoding="utf-8") as archivo:
                escritor = csv.writer(archivo)
                escritor.writerow(("instante_s", "puerto", "linea"))
                escritor.writerows(self.registro_csv)
            self.registrar("SYS", f"CSV guardado: {ruta}")

    def cerrar(self):
        self._activo = False
        self.root.after_cancel(self._id_ciclo)
        if self.enlace_tx.conectado:
            self.enlace_tx.escribir("STOP\n")
        self.enlace_tx.terminar()
        self.enlace_rx.terminar()
        self.root.destroy()


def identificar_puerto(puerto, espera_s=1.2):
    """Devuelve 'TX' o 'RX' si la placa responde al handshake."""
    try:
        ser = EnlaceSerie._abrir_puerto_real(puerto)
    except Exception:
        return None
    try:
        ser.write(b"IDENT\n")
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            m = parsear_linea(ser.readline().decode("utf-8", errors="replace"))
            if m.tipo == "ID":
                return m.datos["rol"]
    except Exception:
        return None
    finally:
        ser.close()
    return None


def main():
    if tk is None:
        raise SystemExit("Tkinter no esta disponible en este Python.")
    root = tk.Tk()
    HMIRoverDebug(root)
    root.mainloop()


if __name__ == "__main__":
    main()
