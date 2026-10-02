"""
Motor de Flasheo en 1 Clic y Utilidad de Aprovisionamiento (FlasherEngine).
Parte de la suite HMI Debug del proyecto Rover Lunar V2.0.

Permite la deteccion de herramientas de carga (arduino-cli y esptool), la construccion
y sanitizacion de comandos de subproceso, la sincronizacion serie de calibraciones
de motores y servos con persistencia NVS/EEPROM, y la ejecucion en streaming
sin congelar la interfaz grafica.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from hardware_profiles import PerfilHardware


DEFAULT_ARDUINO_CLI = "arduino-cli"
DEFAULT_ESPTOOL = "esptool.py"
DEFAULT_BAUD_RATE = 921600
DEFAULT_ESPTOOL_OFFSET = "0x0"

# Valores predeterminados y limites de seguridad fisica
DEFAULT_TRIM_MOTOR = 100
DEFAULT_ANGULO_SERVO = 90
LIMITE_SERVO_MIN = 10
LIMITE_SERVO_MAX = 170
LIMITE_TRIM_MIN = 0
LIMITE_TRIM_MAX = 255


def sanitizar_puerto(puerto: str) -> str:
    """
    Valida y sanitiza el identificador de un puerto serie para prevenir inyecciones de comandos.

    Acepta formatos estandar de Linux (/dev/ttyUSB*, /dev/ttyACM*, /dev/pts/*)
    y Windows (COM*, \\\\.\\COM*).

    Lanza:
        ValueError si el puerto es nulo, esta vacio o contiene caracteres no permitidos.
    """
    if puerto is None:
        raise ValueError("El identificador de puerto no puede estar vacio o ser nulo")

    limpio = puerto.strip()
    if not limpio:
        raise ValueError("El identificador de puerto no puede estar vacio")

    # Patron seguro: caracteres alfanumericos, puntos, guiones, barras y barras invertidas
    patron_seguro = r"^[a-zA-Z0-9_\-\./\\]+$"
    if not re.match(patron_seguro, limpio):
        raise ValueError(f"Caracteres invalidos en el identificador de puerto: '{puerto}'")

    return limpio


def formatear_trama_calibracion(
    trims: dict[int, int] | list[int] | tuple[int, ...],
    servos: dict[int, int] | list[int] | tuple[int, ...],
) -> str:
    """
    Formatea la trama textual de sincronizacion de calibracion para el microcontrolador.

    Formato: CALIB,m1,m2,m3,m4,m5,m6,s1,s2,s3,s4\\n

    Parametros:
        trims: Diccionario (claves 1..6 o 0..5) o lista con los 6 ratios de motor (0 a 255).
        servos: Diccionario (claves 1..4 o 0..3) o lista con los 4 angulos de servos (10 a 170).

    Retorna:
        Cadena formateada lista para ser enviada por puerto serie con terminador \\n.

    Lanza:
        ValueError si algun valor esta fuera de los limites seguros de hardware.
    """
    # 1. Extraer trims de motores (6 valores)
    valores_trims: list[int] = []
    if isinstance(trims, dict):
        if 0 in trims and 6 not in trims:
            base_index = 0
        elif 1 in trims:
            base_index = 1
        else:
            base_index = 0 if 0 in trims else 1

        for i in range(6):
            clave = base_index + i
            valores_trims.append(int(trims.get(clave, DEFAULT_TRIM_MOTOR)))
    elif isinstance(trims, (list, tuple)):
        for i in range(6):
            if i < len(trims):
                valores_trims.append(int(trims[i]))
            else:
                valores_trims.append(DEFAULT_TRIM_MOTOR)
    else:
        raise TypeError("El parametro 'trims' debe ser un diccionario, lista o tupla")

    # Validar limites de trims de motor
    for idx, t in enumerate(valores_trims, start=1):
        if not (LIMITE_TRIM_MIN <= t <= LIMITE_TRIM_MAX):
            raise ValueError(
                f"Valor de trim para motor M{idx} fuera de rango [{LIMITE_TRIM_MIN}, {LIMITE_TRIM_MAX}]: {t}"
            )

    # 2. Extraer angulos de servomotores (4 valores)
    valores_servos: list[int] = []
    if isinstance(servos, dict):
        if 0 in servos and 4 not in servos:
            base_index = 0
        elif 1 in servos:
            base_index = 1
        else:
            base_index = 0 if 0 in servos else 1

        for i in range(4):
            clave = base_index + i
            valores_servos.append(int(servos.get(clave, DEFAULT_ANGULO_SERVO)))
    elif isinstance(servos, (list, tuple)):
        for i in range(4):
            if i < len(servos):
                valores_servos.append(int(servos[i]))
            else:
                valores_servos.append(DEFAULT_ANGULO_SERVO)
    else:
        raise TypeError("El parametro 'servos' debe ser un diccionario, lista o tupla")

    # Validar limites estrictos de seguridad de servomotores
    for idx, s in enumerate(valores_servos, start=1):
        if not (LIMITE_SERVO_MIN <= s <= LIMITE_SERVO_MAX):
            raise ValueError(
                f"Angulo de servomotor S{idx} fuera de rango seguro [{LIMITE_SERVO_MIN}, {LIMITE_SERVO_MAX}]: {s}"
            )

    cuerpo = ",".join(str(v) for v in (valores_trims + valores_servos))
    return f"CALIB,{cuerpo}\n"


def parsear_trama_calibracion(trama: str) -> tuple[list[int], list[int]]:
    """
    Parsea una trama textual de calibracion y extrae las listas de trims y servos.

    Retorna:
        Tupla (trims, servos) donde trims tiene 6 elementos y servos tiene 4 elementos.

    Lanza:
        ValueError si el formato o la cantidad de elementos es invalida.
    """
    limpia = trama.strip()
    partes = limpia.split(",")
    if not partes or partes[0] != "CALIB":
        raise ValueError(f"Formato de trama de calibracion invalido: '{trama.strip()}'")

    if len(partes) != 11:
        raise ValueError(
            f"Cantidad de parametros incorrecta en trama de calibracion: se esperaban 10 valores, se recibieron {len(partes) - 1}"
        )

    try:
        trims = [int(p) for p in partes[1:7]]
        servos = [int(p) for p in partes[7:11]]
    except ValueError as e:
        raise ValueError(f"Error al convertir valores numericos en trama de calibracion: {e}")

    return trims, servos


class FlasherEngine:
    """
    Motor de flasheo y aprovisionamiento pre-despliegue para la suite de depuracion.
    Coordina la ejecucion de herramientas de compilacion y subida (arduino-cli, esptool)
    y gestiona la sincronizacion de calibraciones en hardware real.
    """

    def __init__(
        self,
        arduino_cli_path: Optional[str] = None,
        esptool_path: Optional[str] = None,
        python_executable: Optional[str] = None,
        repo_root: Optional[Path] = None,
    ):
        self.arduino_cli_path = arduino_cli_path or DEFAULT_ARDUINO_CLI
        self.esptool_path = esptool_path or DEFAULT_ESPTOOL
        self.python_executable = python_executable or sys.executable

        if repo_root is not None:
            self.repo_root = Path(repo_root).resolve()
        else:
            # Por defecto asume que este archivo esta en 02_Debug_y_Pruebas/HMI_Debug/
            self.repo_root = Path(__file__).resolve().parents[2]

    def verificar_herramientas(self) -> dict[str, bool]:
        """
        Verifica la disponibilidad en el sistema de arduino-cli y esptool.

        Retorna:
            Diccionario {'arduino_cli': bool, 'esptool': bool}.
        """
        # 1. Comprobar arduino-cli
        cli_disponible = False
        if shutil.which(self.arduino_cli_path) is not None:
            cli_disponible = True
        else:
            p = Path(self.arduino_cli_path)
            if p.is_file() and os.access(p, os.X_OK):
                cli_disponible = True

        # 2. Comprobar esptool (ejecutable en PATH o modulo en entorno Python)
        esptool_disponible = False
        if shutil.which(self.esptool_path) is not None:
            esptool_disponible = True
        else:
            p = Path(self.esptool_path)
            if p.is_file() and os.access(p, os.X_OK):
                esptool_disponible = True
            elif importlib.util.find_spec("esptool") is not None:
                esptool_disponible = True

        return {
            "arduino_cli": cli_disponible,
            "esptool": esptool_disponible,
        }

    def construir_comando_arduino_cli(
        self,
        puerto: str,
        fqbn: str,
        sketch_path: str | Path,
        verbose: bool = False,
    ) -> list[str]:
        """
        Construye la lista de argumentos para compilar y subir mediante arduino-cli.

        Ejemplo: ['arduino-cli', 'compile', '--upload', '-b', 'arduino:esp32:nano_nora',
                  '-p', 'COM3', '/ruta/sketch.ino']
        """
        puerto_limpio = sanitizar_puerto(puerto)
        if not fqbn or not fqbn.strip():
            raise ValueError("El parametro FQBN no puede estar vacio")
        if not sketch_path or not str(sketch_path).strip():
            raise ValueError("La ruta del sketch no puede estar vacia")

        cmd = [
            self.arduino_cli_path,
            "compile",
            "--upload",
            "-b",
            fqbn.strip(),
            "-p",
            puerto_limpio,
            str(sketch_path),
        ]
        if verbose:
            cmd.append("-v")

        return cmd

    def construir_comando_esptool(
        self,
        puerto: str,
        chip: str,
        bin_path: str | Path,
        baud: int = DEFAULT_BAUD_RATE,
        offset: str = DEFAULT_ESPTOOL_OFFSET,
        use_python_module: bool = False,
    ) -> list[str]:
        """
        Construye la lista de argumentos para flashear directamente con esptool.

        Ejemplo: ['esptool.py', '--chip', 'esp32s3', '--port', 'COM3',
                  '--baud', '921600', 'write_flash', '-z', '0x0', 'firmware.bin']
        """
        puerto_limpio = sanitizar_puerto(puerto)
        if not chip or not chip.strip():
            raise ValueError("El identificador de chip no puede estar vacio")
        if not bin_path or not str(bin_path).strip():
            raise ValueError("La ruta del bin_path no puede estar vacia")

        if use_python_module:
            cmd_base = [self.python_executable, "-m", "esptool"]
        else:
            cmd_base = [self.esptool_path]

        cmd = cmd_base + [
            "--chip",
            chip.strip(),
            "--port",
            puerto_limpio,
            "--baud",
            str(baud),
            "write_flash",
            "-z",
            str(offset),
            str(bin_path),
        ]
        return cmd

    def _ejecutar_subproceso(
        self,
        cmd: list[str],
        callback_log: Optional[Callable[[str], None]] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        Ejecuta un subproceso con captura en streaming de stdout y stderr combinados.
        Invoca callback_log(linea) para cada linea recibida en tiempo real.

        Retorna:
            True si el proceso termino con codigo de retorno 0, False en caso contrario.
        """
        try:
            proceso = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            if proceso.stdout is not None:
                for linea in iter(proceso.stdout.readline, ""):
                    linea_limpia = linea.rstrip("\r\n")
                    if callback_log:
                        callback_log(linea_limpia)
                proceso.stdout.close()

            retcode = proceso.wait(timeout=timeout)
            return retcode == 0
        except (subprocess.SubprocessError, OSError) as e:
            if callback_log:
                callback_log(f"[ERROR] Excepcion al ejecutar subproceso: {e}")
            return False

    def sincronizar_calibracion(
        self,
        serial_conn: Any,
        trims: dict[int, int] | list[int] | tuple[int, ...],
        servos: dict[int, int] | list[int] | tuple[int, ...],
        persistir_nvs: bool = True,
        timeout: float = 2.0,
        callback_log: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        Envia la trama de calibracion a traves de una conexion serie abierta y opcionalmente
        envia la instruccion de persistencia en memoria no volatil (NVS/EEPROM).

        Parametros:
            serial_conn: Objeto de puerto serie abierto (con metodos write, flush y opcionalmente readline).
            trims: Configuracion de trim para los 6 motores.
            servos: Configuracion de angulos/centros para los 4 servos.
            persistir_nvs: Si es True, envia comando adicional para almacenar en NVS.
            timeout: Tiempo maximo en segundos para aguardar confirmacion del microcontrolador.
            callback_log: Funcion opcional para registrar trazas en consola.

        Retorna:
            True si la transmision y confirmaciones fueron exitosas, False ante fallos.
        """
        try:
            trama = formatear_trama_calibracion(trims, servos)
            if callback_log:
                callback_log(f"[SYS] Enviando calibracion: {trama.strip()}")

            serial_conn.write(trama.encode("utf-8"))
            if hasattr(serial_conn, "flush"):
                serial_conn.flush()

            # Verificacion de confirmacion si el objeto serie implementa lectura
            if hasattr(serial_conn, "readline"):
                resp = serial_conn.readline()
                if isinstance(resp, bytes):
                    resp_str = resp.decode("utf-8", errors="replace").strip()
                else:
                    resp_str = str(resp).strip()

                if resp_str and any(err in resp_str.upper() for err in ["ERROR", "NACK", "FAIL"]):
                    if callback_log:
                        callback_log(f"[ERROR] Microcontrolador rechazo la calibracion: '{resp_str}'")
                    return False

            # Persistencia en memoria NVS / EEPROM
            if persistir_nvs:
                cmd_persist = "PERSIST_NVS\n"
                if callback_log:
                    callback_log("[SYS] Solicitando persistencia de parametros en NVS...")
                serial_conn.write(cmd_persist.encode("utf-8"))
                if hasattr(serial_conn, "flush"):
                    serial_conn.flush()

                if hasattr(serial_conn, "readline"):
                    resp_persist = serial_conn.readline()
                    if isinstance(resp_persist, bytes):
                        resp_persist_str = resp_persist.decode("utf-8", errors="replace").strip()
                    else:
                        resp_persist_str = str(resp_persist).strip()

                    if resp_persist_str and any(err in resp_persist_str.upper() for err in ["ERROR", "FAIL"]):
                        if callback_log:
                            callback_log(f"[ERROR] Fallo de persistencia NVS: '{resp_persist_str}'")
                        return False

            if callback_log:
                callback_log("[INFO] Calibracion sincronizada y almacenada exitosamente.")
            return True

        except Exception as e:
            if callback_log:
                callback_log(f"[ERROR] Fallo en comunicacion serie durante sincronizacion: {e}")
            return False

    def liberar_puerto(self, serial_conn: Any, callback_log: Optional[Callable[[str], None]] = None) -> bool:
        """
        Cierra y libera de forma segura una conexion serie activa para permitir
        la operacion fisica autonoma del vehiculo en campo.
        """
        try:
            if serial_conn is not None:
                if hasattr(serial_conn, "flush"):
                    serial_conn.flush()
                if hasattr(serial_conn, "close"):
                    serial_conn.close()
            if callback_log:
                callback_log("[INFO] Puerto serie liberado satisfactoriamente. Vehiculo listo para campo.")
            return True
        except Exception as e:
            if callback_log:
                callback_log(f"[ERROR] Error al liberar puerto serie: {e}")
            return False

    def flashear(
        self,
        puerto: str,
        perfil: PerfilHardware,
        rol: str,
        callback_log: Optional[Callable[[str], None]] = None,
        tool: Optional[str] = None,
        bin_path_override: Optional[str | Path] = None,
    ) -> bool:
        """
        Ejecuta el aprovisionamiento de firmware en el microcontrolador objetivo.

        Parametros:
            puerto: Identificador del puerto COM o tty.
            perfil: Instancia de PerfilHardware con caracteristicas del microcontrolador.
            rol: 'TX' (transmision) o 'RX' (recepcion).
            callback_log: Callback para emitir logs en streaming hacia la consola de UI.
            tool: 'arduino_cli' o 'esptool' para forzar una herramienta especifica.
            bin_path_override: Ruta opcional a un archivo binario precompilado (.bin).

        Retorna:
            True si la operacion fue exitosa, False en caso contrario.
        """
        # 1. Sanitizar el puerto
        try:
            puerto_limpio = sanitizar_puerto(puerto)
        except ValueError as e:
            if callback_log:
                callback_log(f"[ERROR] {e}")
            return False

        # 2. Validar rol y obtener sketch correspondiente
        rol_norm = rol.strip().upper()
        if rol_norm == "TX" and not perfil.soporta_tx:
            if callback_log:
                callback_log(f"[ERROR] El perfil '{perfil.nombre}' no soporta el rol TX.")
            return False
        elif rol_norm == "RX" and not perfil.soporta_rx:
            if callback_log:
                callback_log(f"[ERROR] El perfil '{perfil.nombre}' no soporta el rol RX.")
            return False

        # 3. Determinar ruta de sketch / binario
        ruta_sketch: Optional[Path] = None
        if bin_path_override:
            ruta_sketch = Path(bin_path_override).resolve()
        else:
            ruta_sketch = perfil.obtener_ruta_sketch(rol_norm, repo_root=self.repo_root)

        if ruta_sketch is None or not ruta_sketch.exists():
            if callback_log:
                callback_log(f"[ERROR] No se encuentra el archivo fuente del firmware: {ruta_sketch}")
            return False

        # 4. Verificar herramientas disponibles
        herramientas = self.verificar_herramientas()
        usar_cli = (tool == "arduino_cli") or (tool is None and herramientas["arduino_cli"])
        usar_esptool = (tool == "esptool") or (tool is None and not herramientas["arduino_cli"] and herramientas["esptool"])

        # Intento de flasheo con arduino-cli
        if usar_cli and herramientas["arduino_cli"] and perfil.fqbn and ruta_sketch.suffix == ".ino":
            if callback_log:
                callback_log(f"[INFO] Compilando y cargando con arduino-cli en {puerto_limpio}...")
                callback_log(f"[INFO] FQBN: {perfil.fqbn} | Sketch: {ruta_sketch.name}")

            cmd = self.construir_comando_arduino_cli(puerto_limpio, perfil.fqbn, ruta_sketch)
            exito = self._ejecutar_subproceso(cmd, callback_log=callback_log)
            if exito:
                if callback_log:
                    callback_log("[INFO] Carga de firmware con arduino-cli completada exitosamente.")
                return True
            else:
                if callback_log:
                    callback_log("[ERROR] Error en el proceso de compilacion o subida con arduino-cli.")
                return False

        # Intento de flasheo con esptool
        if (usar_esptool or not herramientas["arduino_cli"]) and herramientas["esptool"]:
            bin_path: Optional[Path] = None
            if ruta_sketch.suffix == ".bin":
                bin_path = ruta_sketch
            else:
                candidato = ruta_sketch.with_suffix(".bin")
                if candidato.exists():
                    bin_path = candidato

            if bin_path and bin_path.exists():
                chip = "esp32s3" if "S3" in perfil.mcu.upper() or "NANO" in perfil.id.upper() else (
                    "esp32c3" if "C3" in perfil.mcu.upper() else "esp32"
                )
                use_mod = (shutil.which(self.esptool_path) is None)
                if callback_log:
                    callback_log(f"[INFO] Cargando binario precompilado con esptool en {puerto_limpio} (Chip: {chip})...")

                cmd = self.construir_comando_esptool(
                    puerto=puerto_limpio,
                    chip=chip,
                    bin_path=bin_path,
                    use_python_module=use_mod,
                )
                exito = self._ejecutar_subproceso(cmd, callback_log=callback_log)
                if exito:
                    if callback_log:
                        callback_log("[INFO] Flasheo con esptool completado exitosamente.")
                    return True
                else:
                    if callback_log:
                        callback_log("[ERROR] Error durante el flasheo con esptool.")
                    return False
            else:
                if callback_log:
                    callback_log(
                        f"[ERROR] arduino-cli no esta disponible y no se encontro archivo precompilado .bin para {ruta_sketch.name}."
                    )
                return False

        if callback_log:
            callback_log("[ERROR] No se encontraron herramientas de compilacion o flasheo disponibles (arduino-cli ni esptool).")
        return False
