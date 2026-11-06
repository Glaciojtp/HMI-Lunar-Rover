"""Hace cumplir la regla de AGENTS.md: un solo archivo activo por pieza del sistema."""

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OFICIAL = RAIZ / "01_Oficial"
RANGOS_EMOJI = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0xFE0F, 0xFE0F))
PATRON_EMOJI = re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in RANGOS_EMOJI) + "]")


def activos(*sufijos):
    return sorted(p.relative_to(OFICIAL).as_posix() for p in OFICIAL.rglob("*")
                  if p.suffix in sufijos and "__pycache__" not in p.parts)


class TestEstructura(unittest.TestCase):
    def test_un_firmware_por_microcontrolador(self):
        self.assertEqual(activos(".ino"), ["Ejecutor_NanoESP32/Ejecutor_NanoESP32.ino",
                                           "Transmisor_NanoESP32/Transmisor_NanoESP32.ino"])

    def test_sin_cabeceras_auxiliares_de_firmware(self):
        self.assertEqual(activos(".h", ".cpp", ".hpp", ".txt"), [])

    def test_una_hmi_normal_y_una_debug(self):
        self.assertEqual(activos(".py"), ["HMI/HMI_Rover.py", "HMI/HMI_Rover_Debug.py"])

    def test_las_carpetas_previas_no_vuelven(self):
        for nombre in ("02_Debug_y_Pruebas", "04_Legacy_y_Versiones_Previas", "Herramientas_Docker_Wine", "docs"):
            self.assertFalse((RAIZ / nombre).exists(), nombre)

    def test_deprecado_y_futuro_tienen_indice(self):
        self.assertTrue((RAIZ / "04_Deprecado/README.md").is_file())
        self.assertTrue((RAIZ / "05_Futuro/README.md").is_file())

    def test_lanzadores_apuntan_a_archivos_existentes(self):
        for bat, py in (("Lanzar_HMI_Rover.bat", "HMI_Rover.py"), ("Lanzar_HMI_Debug.bat", "HMI_Rover_Debug.py"),
                        ("Compilar_HMI_a_EXE.bat", "HMI_Rover.py")):
            self.assertIn(py, (RAIZ / bat).read_text(encoding="utf-8"))

    def test_sin_emojis_en_archivos_activos(self):
        rutas = [*OFICIAL.rglob("*.ino"), *OFICIAL.rglob("*.py"), *(RAIZ / "tests").glob("*.py"), *RAIZ.glob("*.md"), *RAIZ.glob("*.bat")]
        for ruta in rutas:
            self.assertIsNone(PATRON_EMOJI.search(ruta.read_text(encoding="utf-8")), str(ruta))


if __name__ == "__main__":
    unittest.main()
