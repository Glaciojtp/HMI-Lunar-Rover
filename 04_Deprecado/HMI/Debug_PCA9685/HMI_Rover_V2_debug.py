#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HMI ROVER LUNAR - VERSION DEBUG
================================
Version de depuracion de la HMI oficial.
Extiende HMIRoverRockerBogieV21Pre (de HMI_Rover_V2_2_pre.py) y agrega:
  - Impresion en consola (stdout) de TODA trama enviada al Arduino.
  - Titulo de ventana diferenciado para indicar modo debug.
  - Registro [DEBUG][SERIAL] de cada byte transmitido por serial.

Uso:
    python HMI_Rover_V2_debug.py

La HMI original debe estar en:
    ../HMI/HMI_Rover_V2_2_pre.py  (mismo repositorio)
"""

import sys
import os
import time
import threading

# ---------------------------------------------------------------------------
# Ajuste de sys.path para importar modulos del proyecto
# ---------------------------------------------------------------------------
_dir_debug = os.path.dirname(os.path.abspath(__file__))
_dir_hmi   = os.path.abspath(os.path.join(_dir_debug, "..", "..", "HMI"))

for _d in [_dir_debug, _dir_hmi]:
    if _d not in sys.path:
        sys.path.insert(0, _d)

# ---------------------------------------------------------------------------
# Importar dependencias del proyecto (hardware_profiles, flasher_engine, etc.)
# Estas viven en 01_Oficial/HMI/
# ---------------------------------------------------------------------------
try:
    from hardware_profiles import (
        HardwareProfileRegistry,
        PerfilHardware,
        PERFILES_OFICIALES,
        PERFIL_DEFAULT_ID,
        parsear_handshake,
    )
except ImportError as e:
    print(f"[ERROR] No se pudo importar hardware_profiles: {e}")
    print(f"        Asegurese de que el archivo exista en: {_dir_hmi}")
    input("Presione ENTER para cerrar...")
    sys.exit(1)

try:
    from flasher_engine import (
        FlasherEngine,
        sanitizar_puerto,
        formatear_trama_calibracion,
    )
except ImportError as e:
    print(f"[ERROR] No se pudo importar flasher_engine: {e}")
    input("Presione ENTER para cerrar...")
    sys.exit(1)

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
    print("[ERROR] Tkinter no disponible. Instale una version de Python con soporte Tk.")
    TKINTER_DISPONIBLE = False

# ---------------------------------------------------------------------------
# Importar clase base de la HMI oficial
# ---------------------------------------------------------------------------
try:
    from HMI_Rover_V2_2_pre import HMIRoverRockerBogieV21Pre
except ImportError as e:
    print(f"[ERROR] No se pudo importar HMI_Rover_V2_2_pre: {e}")
    print(f"        Asegurese de que el archivo exista en: {_dir_hmi}")
    input("Presione ENTER para cerrar...")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helper de escritura serial con debug a stdout
# ---------------------------------------------------------------------------

def _debug_serial_write(serial_conn, raw_bytes: bytes, descripcion: str = ""):
    """Escribe bytes al puerto serial y los imprime en consola."""
    if not serial_conn or not serial_conn.is_open:
        print(f"[DEBUG][SERIAL] Sin conexion - descartado: {raw_bytes!r}")
        return
    try:
        serial_conn.write(raw_bytes)
        texto = raw_bytes.decode('ascii', errors='replace').strip()
        print(f"[DEBUG][SERIAL] TX -> {texto!r}  ({len(raw_bytes)} bytes){' | ' + descripcion if descripcion else ''}")
    except Exception as e:
        print(f"[DEBUG][SERIAL] ERROR al escribir {raw_bytes!r}: {e}")


# ---------------------------------------------------------------------------
# Clase DEBUG: hereda toda la UI y logica de la HMI oficial
# Solo sobreescribe enviar_trama_actual, ident_o_ping y sincronizar_calibracion
# para interceptar y loguear cada transmision.
# ---------------------------------------------------------------------------

class HMIRoverRockerBogieV21PreDebug(HMIRoverRockerBogieV21Pre):
    """
    Version debug de la HMI oficial.
    Hereda completamente la interfaz grafica y la logica de control.
    Agrega impresion detallada en consola de cada trama enviada al Arduino.
    """

    def __init__(self, root):
        print("[DEBUG] Iniciando HMI en modo DEBUG...")
        super().__init__(root)
        # Cambiar titulo de ventana para indicar modo debug
        self.root.title("HMI Rover Lunar V2.1-pre  [MODO DEBUG]")
        print("[DEBUG] HMI inicializada correctamente.")
        print("[DEBUG] Todas las tramas enviadas al Arduino se mostraran en esta consola.")
        print("-" * 70)

    # -----------------------------------------------------------------------
    # Override: enviar_trama_actual
    # Genera la trama identica a la original y la imprime antes de enviarla.
    # -----------------------------------------------------------------------
    def enviar_trama_actual(self):
        trama = self.generar_trama_control()

        # Siempre loguear la trama (incluso si no hay conexion)
        trama_limpia = trama.strip()
        print(f"[DEBUG][TRAMA] Generada: {trama_limpia!r}")

        if not self.conectado or not self.serial_conn:
            print("[DEBUG][SERIAL] Sin conexion - trama no enviada.")
            return

        raw_bytes = trama.encode('ascii')
        try:
            with self.lock_serial:
                if self.serial_conn and self.serial_conn.is_open:
                    self.serial_conn.write(raw_bytes)
            self.paquetes_tx_contador += 1
            print(f"[DEBUG][SERIAL] TX -> {trama_limpia!r}  ({len(raw_bytes)} bytes)")
        except Exception as e:
            self.log_consola("ERR", f"Error TX: {e}")
            print(f"[DEBUG][SERIAL] ERROR TX: {e}")

    # -----------------------------------------------------------------------
    # Override: ident_o_ping - agrega log a stdout
    # -----------------------------------------------------------------------
    def ident_o_ping(self):
        if not self.conectado or not self.serial_conn:
            self.log_consola("WARN", "No conectado para enviar IDENT/PING.")
            return
        try:
            with self.lock_serial:
                if self.serial_conn and self.serial_conn.is_open:
                    self.serial_conn.write(b"IDENT\n")
            self.log_consola("TX", "[TX IDENT -> MCU]: Solicitando identificacion de firmware...")
            print("[DEBUG][SERIAL] TX -> 'IDENT'  (6 bytes) | Handshake")
        except Exception as e:
            self.log_consola("ERR", f"Error enviando IDENT: {e}")

    # -----------------------------------------------------------------------
    # Override: sincronizar_calibracion - agrega log a stdout
    # -----------------------------------------------------------------------
    def sincronizar_calibracion(self):
        if not self.conectado or not self.serial_conn:
            if messagebox:
                messagebox.showwarning("Atencion", "Conecte el puerto serie antes de sincronizar calibracion.")
            return

        trims = {i: getattr(self, f"trim_m{i}").get() for i in range(1, 7)}
        servos = {i: getattr(self, f"ang_s{i}").get() for i in range(1, 5)}
        trama_calib = formatear_trama_calibracion(trims, servos)

        try:
            with self.lock_serial:
                if self.serial_conn and self.serial_conn.is_open:
                    self.serial_conn.write(trama_calib.encode('ascii'))
                    self.serial_conn.write(b"PERSIST_NVS\n")
            self.log_consola("TX", f"[CALIB]: {trama_calib.strip()} -> Guardado en NVS.")
            print(f"[DEBUG][SERIAL] TX -> {trama_calib.strip()!r}  | Calibracion")
            print(f"[DEBUG][SERIAL] TX -> 'PERSIST_NVS'  | NVS persist")
            if messagebox:
                messagebox.showinfo("Exito", "Calibracion sincronizada y persistida en memoria no volatil (NVS).")
        except Exception as e:
            self.log_consola("ERR", f"Error enviando calibracion: {e}")

    # -----------------------------------------------------------------------
    # Override: procesar_linea_serial - loguear tambien a stdout lo recibido
    # -----------------------------------------------------------------------
    def procesar_linea_serial(self, linea):
        print(f"[DEBUG][SERIAL] RX <- {linea!r}")
        super().procesar_linea_serial(linea)

    # -----------------------------------------------------------------------
    # Override: toggle_conexion - loguear estado de conexion a stdout
    # -----------------------------------------------------------------------
    def toggle_conexion(self):
        if not self.conectado:
            print(f"[DEBUG] Intentando conectar a {self.cb_puertos.get()} @ {self.cb_baud.get()} baud...")
        else:
            print("[DEBUG] Desconectando...")
        super().toggle_conexion()
        if self.conectado:
            print(f"[DEBUG] Conectado exitosamente a {self.cb_puertos.get()}")
        else:
            print("[DEBUG] Desconectado.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    if not TKINTER_DISPONIBLE:
        print("[ERROR] Tkinter no esta disponible. No se puede iniciar la UI.")
        input("Presione ENTER para cerrar...")
        sys.exit(1)

    root = tk.Tk()
    app = HMIRoverRockerBogieV21PreDebug(root)
    root.protocol(
        "WM_DELETE_WINDOW",
        lambda: (setattr(app, 'ejecutando', False), app.desconectar(), root.destroy())
    )
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        print(f"\n[EXCEPTION] {exc}")
        traceback.print_exc()
        input("\nPresione ENTER para cerrar...")
