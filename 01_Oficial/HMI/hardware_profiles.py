"""
Modulo de Definicion de Perfiles de Hardware y Autodeteccion.
Parte de la suite HMI Debug del proyecto Rover Lunar V2.0.

Define los perfiles de hardware soportados (Arduino Nano ESP32, ESP32-C3 SuperMini,
Arduino MKR WAN 1310), el mecanismo de identificacion pasiva por USB VID:PID
y el protocolo de identificacion activa mediante handshake serie.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class PerfilHardware:
    """Representa las caracteristicas de un microcontrolador soportado en el sistema."""

    id: str
    nombre: str
    mcu: str
    vid_pid_list: list[tuple[int, int]] = field(default_factory=list)
    fqbn: str = ""
    sketch_tx: Optional[str] = None
    sketch_rx: Optional[str] = None
    descripcion: str = ""

    @property
    def soporta_tx(self) -> bool:
        """Indica si el perfil tiene firmware de transmision asignado."""
        return self.sketch_tx is not None

    @property
    def soporta_rx(self) -> bool:
        """Indica si el perfil tiene firmware de recepcion asignado."""
        return self.sketch_rx is not None

    def coincide_vid_pid(self, vid: int, pid: int) -> bool:
        """Verifica si el par (vid, pid) corresponde a este perfil."""
        return (vid, pid) in self.vid_pid_list

    def obtener_ruta_sketch(self, rol: str, repo_root: Optional[Path] = None) -> Optional[Path]:
        """
        Retorna la ruta absoluta o relativa al sketch segun el rol solicitado ('TX' o 'RX').
        Si se especifica repo_root, retorna la ruta absoluta resuelta.
        """
        rol_norm = rol.strip().upper()
        ruta_rel: Optional[str] = None
        if rol_norm == "TX":
            ruta_rel = self.sketch_tx
        elif rol_norm == "RX":
            ruta_rel = self.sketch_rx

        if ruta_rel is None:
            return None

        if repo_root is not None:
            return (repo_root / ruta_rel).resolve()
        return Path(ruta_rel)


# Identificador del perfil predeterminado oficial del sistema
PERFIL_DEFAULT_ID = "ARDUINO_NANO_ESP32"

# Matriz estandar de perfiles de hardware oficiales
PERFILES_OFICIALES: list[PerfilHardware] = [
    PerfilHardware(
        id="ARDUINO_NANO_ESP32",
        nombre="Arduino Nano ESP32",
        mcu="ESP32-S3",
        vid_pid_list=[
            (0x2341, 0x0070),  # Modo aplicacion normal (USB CDC)
            (0x2341, 0x0069),  # Modo bootloader ROM / DFU
        ],
        fqbn="arduino:esp32:nano_nora",
        sketch_tx="02_Debug_y_Pruebas/Firmware_Debug/Transmisor_ArduinoNano_ESP32/Transmisor_ArduinoNano_ESP32.ino",
        sketch_rx="01_Oficial/Receptor_Rover_NanoESP32/Ejecutor_ArduinoNano_ESP32/Ejecutor_ArduinoNano_ESP32.ino",
        descripcion="Plataforma oficial estandarizada a 3.3V (ESP32-S3). Soporta transmision y recepcion.",
    ),
    PerfilHardware(
        id="ESP32_C3_SUPERMINI",
        nombre="ESP32-C3 SuperMini",
        mcu="ESP32-C3",
        vid_pid_list=[
            (0x303A, 0x1001),  # CDC nativo USB ESP32-C3
            (0x1A86, 0x7523),  # Adaptador CH340
            (0x10C4, 0xEA60),  # Adaptador CP2102
        ],
        fqbn="esp32:esp32:esp32c3",
        sketch_tx="01_Oficial/Transmisor_PC_ESP32C3/Control_ESP32_C3_Optimizado/Control_ESP32_C3_Optimizado.ino",
        sketch_rx=None,
        descripcion="Transmisor USB-RF de escritorio previo basado en ESP32-C3 (RISC-V).",
    ),
    PerfilHardware(
        id="ARDUINO_MKR_1310",
        nombre="Arduino MKR WAN 1310",
        mcu="SAMD21",
        vid_pid_list=[
            (0x2341, 0x8054),  # Modo USB CDC normal
            (0x2341, 0x0054),  # Modo bootloader
        ],
        fqbn="arduino:samd:mkrwan1310",
        sketch_tx=None,
        sketch_rx="01_Oficial/Receptor_Rover_MKR1310/Ejecutor_ArduinoMKR_Optimizado/Ejecutor_ArduinoMKR_Optimizado.ino",
        descripcion="Receptor historico a bordo del chasis basado en SAMD21 (ARM Cortex-M0+).",
    ),
]


def parsear_handshake(respuesta_ident: str, strict: bool = True) -> tuple[str, str, str] | None:
    """
    Parsea la respuesta textual del comando IDENT recibido desde un microcontrolador.

    Formato esperado: ID:<PLACA>:<ROL>:<VERSION>
    Ejemplos:
        ID:NANO_ESP32:TX:v2.1 -> ('NANO_ESP32', 'TX', 'v2.1')
        ID:MKR1310:RX:v2.0    -> ('MKR1310', 'RX', 'v2.0')

    Parametros:
        respuesta_ident: Cadena de texto recibida por el puerto serie.
        strict: Si es True, lanza ValueError si el formato no coincide; si es False, retorna None.

    Retorna:
        Tupla de tres elementos (placa, rol, version) o None si strict es False y falla.
    """
    if not respuesta_ident:
        if strict:
            raise ValueError("Cadena de handshake vacia o nula")
        return None

    limpia = respuesta_ident.strip()
    patron = r"^ID:([A-Za-z0-9_]+):([A-Za-z0-9_]+):([A-Za-z0-9_.]+)$"
    coincidencia = re.match(patron, limpia)

    if not coincidencia:
        if strict:
            raise ValueError(f"Formato de handshake invalido: '{respuesta_ident.strip()}'")
        return None

    placa, rol, version = coincidencia.groups()
    return placa, rol, version


def _extraer_vid_pid(port_info: Any) -> Optional[tuple[int, int]]:
    """Extrae el par (vid, pid) desde distintos tipos de objetos o estructuras."""
    if port_info is None:
        return None

    # Caso 1: Objeto pyserial ListPortInfo o similar con atributos vid y pid
    if hasattr(port_info, "vid") and hasattr(port_info, "pid"):
        vid = getattr(port_info, "vid", None)
        pid = getattr(port_info, "pid", None)
        if vid is not None and pid is not None:
            try:
                return int(vid), int(pid)
            except (ValueError, TypeError):
                pass

    # Caso 2: Diccionario con claves 'vid' y 'pid'
    if isinstance(port_info, dict):
        vid_val = port_info.get("vid")
        pid_val = port_info.get("pid")
        if vid_val is not None and pid_val is not None:
            try:
                vid_int = int(vid_val, 16) if isinstance(vid_val, str) else int(vid_val)
                pid_int = int(pid_val, 16) if isinstance(pid_val, str) else int(pid_val)
                return vid_int, pid_int
            except (ValueError, TypeError):
                pass

    # Caso 3: Tupla o lista de longitud 2
    if isinstance(port_info, (tuple, list)) and len(port_info) == 2:
        try:
            return int(port_info[0]), int(port_info[1])
        except (ValueError, TypeError):
            pass

    # Caso 4: Cadena de texto con formato VID:PID (ej. 'USB VID:PID=2341:0070')
    if isinstance(port_info, str):
        patron_hex = r"([0-9a-fA-F]{4}):([0-9a-fA-F]{4})"
        m = re.search(patron_hex, port_info)
        if m:
            try:
                return int(m.group(1), 16), int(m.group(2), 16)
            except ValueError:
                pass

    return None


class HardwareProfileRegistry:
    """
    Registro y administrador de perfiles de hardware para la suite de control.
    Proporciona metodos para identificacion pasiva (VID:PID) y activa (handshake).
    """

    # Mapeo de identificadores de placa reportados en handshake a ID de perfil
    _ALIAS_HANDSHAKE: dict[str, str] = {
        "NANO_ESP32": "ARDUINO_NANO_ESP32",
        "ARDUINO_NANO_ESP32": "ARDUINO_NANO_ESP32",
        "ESP32C3": "ESP32_C3_SUPERMINI",
        "ESP32_C3": "ESP32_C3_SUPERMINI",
        "ESP32_C3_SUPERMINI": "ESP32_C3_SUPERMINI",
        "MKR1310": "ARDUINO_MKR_1310",
        "MKR_1310": "ARDUINO_MKR_1310",
        "ARDUINO_MKR_1310": "ARDUINO_MKR_1310",
    }

    def __init__(self, perfiles: Optional[list[PerfilHardware]] = None):
        """Inicializa el registro con la lista de perfiles o los predeterminados oficiales."""
        self._perfiles: dict[str, PerfilHardware] = {}
        perfiles_iniciales = perfiles if perfiles is not None else PERFILES_OFICIALES
        for perfil in perfiles_iniciales:
            self._perfiles[perfil.id] = perfil

    @property
    def perfil_default(self) -> PerfilHardware:
        """Retorna el perfil oficial predeterminado del sistema (Arduino Nano ESP32)."""
        return self._perfiles[PERFIL_DEFAULT_ID]

    def obtener_perfil_default(self) -> PerfilHardware:
        """Metodo de acceso al perfil predeterminado."""
        return self.perfil_default

    def listar_perfiles(self) -> list[PerfilHardware]:
        """Retorna la lista ordenada de perfiles registrados."""
        return list(self._perfiles.values())

    def obtener_perfil(self, id_o_nombre: str, default: Any = ...) -> PerfilHardware:
        """
        Busca y retorna un perfil por su identificador principal, nombre descriptivo o alias.

        Si no se encuentra y se especifico 'default', retorna dicho valor.
        Si no se especifico 'default', lanza KeyError.
        """
        if not id_o_nombre:
            if default is not ...:
                return default
            raise KeyError("Identificador de perfil vacio o nulo")

        # 1. Busqueda directa por ID exacto
        if id_o_nombre in self._perfiles:
            return self._perfiles[id_o_nombre]

        # 2. Busqueda por alias de handshake o normalizado
        clave_upper = id_o_nombre.strip().upper()
        if clave_upper in self._ALIAS_HANDSHAKE:
            target_id = self._ALIAS_HANDSHAKE[clave_upper]
            if target_id in self._perfiles:
                return self._perfiles[target_id]

        # 3. Busqueda por coincidencia insensible a mayusculas en ID o nombre
        clave_lower = id_o_nombre.strip().lower()
        for p in self._perfiles.values():
            if p.id.lower() == clave_lower or p.nombre.lower() == clave_lower:
                return p

        # No encontrado
        if default is not ...:
            return default
        raise KeyError(f"Perfil de hardware no encontrado: '{id_o_nombre}'")

    def detectar_perfil(
        self, port_info: Any, fallback_default: bool = False
    ) -> Optional[PerfilHardware]:
        """
        Identificacion pasiva de perfil evaluando el VID y PID del dispositivo USB.

        Parametros:
            port_info: Objeto de puerto serial (ej. ListPortInfo de pyserial),
                       diccionario, tupla (vid, pid) o cadena con VID:PID.
            fallback_default: Si es True y no hay coincidencia, retorna el perfil default.
                              Si es False y no hay coincidencia, retorna None.

        Retorna:
            Instancia de PerfilHardware coincidente, perfil default si fallback_default es True,
            o None si no se identifico.
        """
        par_vid_pid = _extraer_vid_pid(port_info)
        if par_vid_pid is not None:
            vid, pid = par_vid_pid
            for perfil in self._perfiles.values():
                if perfil.coincide_vid_pid(vid, pid):
                    return perfil

        if fallback_default:
            return self.perfil_default
        return None

    def parsear_handshake(
        self, respuesta_ident: str, strict: bool = True
    ) -> tuple[str, str, str] | None:
        """Metodo de conveniencia para parsear tramas de handshake."""
        return parsear_handshake(respuesta_ident, strict=strict)

    def resolver_handshake(
        self, respuesta_ident: str
    ) -> tuple[PerfilHardware, str, str]:
        """
        Parsea la trama de identificacion activa y resuelve el objeto PerfilHardware correspondiente.

        Parametros:
            respuesta_ident: Cadena devuelta ante comando IDENT (ej. 'ID:NANO_ESP32:TX:v2.1').

        Retorna:
            Tupla de tres elementos (PerfilHardware, rol, version).

        Lanza:
            ValueError si la trama es invalida.
            KeyError si la placa identificada no coincide con ningun perfil registrado.
        """
        placa, rol, version = parsear_handshake(respuesta_ident, strict=True)
        perfil = self.obtener_perfil(placa)
        return perfil, rol, version
