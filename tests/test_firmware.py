"""Pruebas de los dos firmwares oficiales, ejecutados en la PC con hardware simulado.

Compilan los .ino reales con g++ y los stubs de tests/banco_firmware/stubs. Validan la
logica; no reemplazan la compilacion con el nucleo ESP32 ni la prueba en banco.
"""

import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INO_TX = RAIZ / "01_Oficial/Transmisor_NanoESP32/Transmisor_NanoESP32.ino"
INO_RX = RAIZ / "01_Oficial/Ejecutor_NanoESP32/Ejecutor_NanoESP32.ino"
BANCO = RAIZ / "tests/banco_firmware"

# D2..D7 valen 2..7 en los stubs
ENA, IN1, IN2, ENB = 2, 3, 4, 5              # L298N (PUENTE_H_L298N=1)
A1A, A1B, B1A, B1B = 2, 5, 3, 4              # L9110S (por defecto)
L298N = ("PUENTE_H_L298N=1",)
ARRANQUE_MS = 1700


def crc8(datos):
    crc = 0
    for b in datos:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def trama(seq, izq=0, der=0, servos=(90, 90, 90, 90), flags=0, crc_ok=True):
    cuerpo = struct.pack("<BBHhh4B", 0xA5, flags, seq, izq, der, *servos)
    crc = crc8(cuerpo)
    return (cuerpo + bytes([crc if crc_ok else crc ^ 0xFF])).hex()


def angulo_a_ticks(angulo):
    return (angulo * 400) // 180 + 150


class Binario:
    directorio = None
    cache = {}

    @classmethod
    def obtener(cls, ino, defines=()):
        clave = (ino, defines)
        if clave not in cls.cache:
            if cls.directorio is None:
                cls.directorio = tempfile.mkdtemp(prefix="banco_rover_")
            salida = Path(cls.directorio) / (ino.stem + "".join("_" + d.replace("=", "") for d in defines))
            subprocess.run(
                ["g++", "-std=c++17", "-Wall", *(f"-D{d}" for d in defines), f"-I{BANCO / 'stubs'}",
                 "-x", "c++", str(ino), "-x", "c++", str(BANCO / "banco.cpp"), "-o", str(salida)],
                check=True, capture_output=True, text=True)
            cls.cache[clave] = str(salida)
        return cls.cache[clave]


def ejecutar(ino, guion, defines=()):
    r = subprocess.run([Binario.obtener(ino, defines)], input="\n".join(guion) + "\n",
                       capture_output=True, text=True, check=True, timeout=60)
    eventos = []
    for linea in r.stdout.splitlines():
        t, resto = linea.split(" ", 1)
        eventos.append((int(t), resto))
    return eventos


def ejecutor_operando(*guion):
    return ["P 1", "C 1", "I", f"A {ARRANQUE_MS}", "W 1", *guion]


def stream(desde, cantidad, **kw):
    guion = []
    for i in range(cantidad):
        guion += [f"U {trama(desde + i, **kw)}", "A 50"]
    return guion


def pwm(eventos, pin):
    return [(t, int(e.split()[2])) for t, e in eventos if e.startswith(f"PWM {pin} ")]


def pca(eventos):
    return [(t, *map(int, e.split()[1:])) for t, e in eventos if e.startswith("PCA ")]


def seriales(eventos, prefijo):
    return [e[4:] for _, e in eventos if e.startswith("SER " + prefijo)]


@unittest.skipUnless(shutil.which("g++"), "Requiere g++")
class TestEjecutor(unittest.TestCase):
    def test_arranque_centra_servos_de_a_uno_y_despues_inicia_wifi(self):
        ev = ejecutar(INO_RX, ["P 1", "C 1", "I", f"A {ARRANQUE_MS}"], L298N)
        servos = pca(ev)
        self.assertEqual([s[1] for s in servos], [0, 1, 2, 3])
        for a, b in zip(servos, servos[1:]):
            self.assertGreaterEqual(b[0] - a[0], 300)
        t_wifi = next(t for t, e in ev if e.startswith("WIFI begin"))
        self.assertGreater(t_wifi, servos[-1][0])

    def test_motores_quedan_apagados_en_el_arranque(self):
        ev = ejecutar(INO_RX, ["P 1", "C 1", "I", "A 20"], L298N)
        self.assertTrue(pwm(ev, ENA))
        self.assertTrue(all(v == 0 for _, v in pwm(ev, ENA) + pwm(ev, ENB)))

    def test_rampa_limita_el_salto_de_pwm(self):
        ev = ejecutar(INO_RX, ejecutor_operando(*stream(1, 30, izq=255, der=255)), L298N)
        for pin in (ENA, ENB):
            valores = [v for _, v in pwm(ev, pin)]
            self.assertEqual(valores[-1], 255)
            for a, b in zip(valores, valores[1:]):
                self.assertLessEqual(abs(b - a), 4)

    def test_los_dos_lados_no_arrancan_en_el_mismo_instante(self):
        ev = ejecutar(INO_RX, ejecutor_operando(*stream(1, 10, izq=200, der=200)), L298N)
        t_izq = next(t for t, v in pwm(ev, ENA) if v > 0)
        t_der = next(t for t, v in pwm(ev, ENB) if v > 0)
        self.assertGreaterEqual(abs(t_der - t_izq), 60)

    def test_inversion_pasa_por_cero_con_pausa(self):
        guion = ejecutor_operando(*stream(1, 20, izq=120), *stream(21, 30, izq=-120))
        ev = ejecutar(INO_RX, guion, L298N)
        eventos_pwm = pwm(ev, ENA)
        ultimo_cero = max(t for t, v in eventos_pwm if v == 0)
        t_rev = next(t for t, e in ev if e == f"DW {IN2} 1")
        cero_previo = max(t for t, v in eventos_pwm if v == 0 and t < t_rev)
        self.assertGreaterEqual(t_rev - cero_previo, 80)
        self.assertLessEqual(ultimo_cero, t_rev)
        self.assertEqual(eventos_pwm[-1][1], 120)

    def test_servos_una_escritura_por_tick_y_velocidad_limitada(self):
        ev = ejecutar(INO_RX, ejecutor_operando(*stream(1, 40, servos=(150, 30, 150, 30))), L298N)
        arranque = [s for s in pca(ev) if s[0] > ARRANQUE_MS]
        tiempos = [s[0] for s in arranque]
        self.assertEqual(len(tiempos), len(set(tiempos)))
        for a, b in zip(tiempos, tiempos[1:]):
            self.assertGreaterEqual(b - a, 10)
        por_canal = {}
        for t, canal, on, off in arranque:
            por_canal.setdefault(canal, []).append(off - on)
        self.assertEqual(sorted(por_canal), [0, 1, 2, 3])
        paso_max = angulo_a_ticks(93) - angulo_a_ticks(90) + 1
        for ticks in por_canal.values():
            for a, b in zip(ticks, ticks[1:]):
                self.assertLessEqual(abs(b - a), paso_max)
        self.assertEqual(por_canal[0][-1], angulo_a_ticks(150))
        self.assertEqual(por_canal[1][-1], angulo_a_ticks(30))

    def test_pulsos_del_pca_tienen_fases_distintas_y_validas(self):
        ev = ejecutar(INO_RX, ["P 1", "C 1", "I", f"A {ARRANQUE_MS}"], L298N)
        fases = [s[2] for s in pca(ev)]
        self.assertEqual(fases, [0, 1024, 2048, 3072])
        self.assertTrue(all(s[3] < 4096 for s in pca(ev)))

    def test_angulos_fuera_de_rango_se_limitan(self):
        ev = ejecutar(INO_RX, ejecutor_operando(*stream(1, 80, servos=(255, 0, 180, 5))), L298N)
        ticks = {}
        for t, canal, on, off in pca(ev):
            ticks[canal] = off - on
        self.assertEqual(ticks[0], angulo_a_ticks(170))
        self.assertEqual(ticks[1], angulo_a_ticks(10))
        self.assertEqual(ticks[2], angulo_a_ticks(170))
        self.assertEqual(ticks[3], angulo_a_ticks(10))

    def test_crc_incorrecto_no_mueve_nada_y_se_cuenta(self):
        ev = ejecutar(INO_RX, ejecutor_operando(f"U {trama(1, izq=200, crc_ok=False)}", "A 300"), L298N)
        self.assertTrue(all(v == 0 for _, v in pwm(ev, ENA)))
        tlm = seriales(ev, "TLM")[-1].split(",")
        self.assertEqual(tlm[14], "1")  # crc malos
        self.assertEqual(tlm[12], "0")  # tramas validas

    def test_failsafe_a_los_1000_ms_para_motores_y_centra_lento(self):
        guion = ejecutor_operando(*stream(1, 30, izq=255, der=255, servos=(150, 150, 150, 150)), "A 2500")
        ev = ejecutar(INO_RX, guion, L298N)
        t_fs = next(t for t, e in ev if e == "SER WARN:FAILSAFE")
        t_ultima = ARRANQUE_MS + 30 * 50 - 50
        self.assertGreaterEqual(t_fs - t_ultima, 1000)
        self.assertLessEqual(t_fs - t_ultima, 1010)
        self.assertEqual(pwm([x for x in ev if x[0] == t_fs], ENA)[-1][1], 0)
        posteriores = [s for s in pca(ev) if s[0] > t_fs]
        self.assertTrue(posteriores)
        self.assertEqual(len({s[0] for s in posteriores}), len(posteriores))
        self.assertEqual(seriales(ev, "TLM")[-1].split(",")[16], "3")

    def test_recupera_operacion_tras_failsafe(self):
        guion = ejecutor_operando(*stream(1, 5, izq=100), "A 1500", *stream(6, 10, izq=100))
        ev = ejecutar(INO_RX, guion, L298N)
        self.assertEqual(seriales(ev, "TLM")[-1].split(",")[16], "2")

    def test_flag_de_emergencia_corta_motores_sin_rampa(self):
        guion = ejecutor_operando(*stream(1, 30, izq=200), f"U {trama(31, flags=1)}", "A 2")
        ev = ejecutar(INO_RX, guion, L298N)
        valores = pwm(ev, ENA)
        self.assertEqual(valores[-1][1], 0)
        self.assertGreater(valores[-2][1], 100)

    def test_duplicadas_se_descartan_y_perdidas_se_cuentan(self):
        guion = ejecutor_operando(f"U {trama(10)}", "A 50", f"U {trama(10)}", "A 50",
                                  f"U {trama(14)}", "A 300")
        ev = ejecutar(INO_RX, guion, L298N)
        tlm = seriales(ev, "TLM")[-1].split(",")
        self.assertEqual(tlm[12], "2")  # validas
        self.assertEqual(tlm[13], "3")  # perdidas 11, 12, 13

    def test_informa_causa_de_reset_por_brownout(self):
        ev = ejecutar(INO_RX, ["P 1", "C 9", "I", f"A {ARRANQUE_MS}", "W 1", "A 300"], L298N)
        self.assertTrue(seriales(ev, "BOOT,9,"))
        self.assertEqual(seriales(ev, "TLM")[-1].split(",")[9], "9")

    def test_sin_pca_sigue_funcionando_y_lo_informa(self):
        ev = ejecutar(INO_RX, ["P 0", "C 1", "I", f"A {ARRANQUE_MS}", "W 1", *stream(1, 30, izq=100)], L298N)
        self.assertTrue(seriales(ev, "ERR:PCA9685"))
        self.assertEqual(pca(ev), [])
        self.assertEqual(pwm(ev, ENA)[-1][1], 100)
        self.assertEqual(seriales(ev, "TLM")[-1].split(",")[17], "0")

    def test_wifi_con_canal_e_ip_fijos_y_potencia_reducida(self):
        ev = ejecutar(INO_RX, ["P 1", "C 1", "I", f"A {ARRANQUE_MS}"], L298N)
        textos = [e for _, e in ev]
        self.assertIn("WIFI config 192.168.4.2", textos)
        self.assertIn("WIFI begin ROVER_NET 6", textos)
        self.assertIn("WIFI power 34", textos)


@unittest.skipUnless(shutil.which("g++"), "Requiere g++")
class TestTransmisor(unittest.TestCase):
    def test_crea_el_ap_y_responde_al_handshake(self):
        ev = ejecutar(INO_TX, ["I", "S IDENT", "S PING", "A 5"])
        textos = [e for _, e in ev]
        self.assertIn("WIFI softAP ROVER_NET 6 0 1", textos)
        self.assertIn("SER ID:NANO_ESP32:TX:v3.0", textos)
        self.assertIn("SER PONG:TX", textos)

    def test_retransmite_a_20_hz_fijos(self):
        guion = ["I", "W 1"]
        for _ in range(40):
            guion += ["S CMD,10,20,90,90,90,90", "A 25"]
        ev = ejecutar(INO_TX, guion)
        udp = [t for t, e in ev if e.startswith("UDP ")]
        self.assertAlmostEqual(len(udp), 20, delta=1)

    def test_watchdog_de_hmi_ordena_parada_con_flag(self):
        ev = ejecutar(INO_TX, ["I", "W 1", "S CMD,200,200,120,120,60,60", "A 100", "A 700"])
        self.assertIn("SER WARN:HMI_TIMEOUT", [e for _, e in ev])
        t_wd = next(t for t, e in ev if e == "SER WARN:HMI_TIMEOUT")
        self.assertLessEqual(t_wd, 510)
        posteriores = [e for t, e in ev if t >= t_wd and e.startswith("UDP ")]
        cuerpo = bytes.fromhex(posteriores[0].split()[2])
        self.assertEqual(cuerpo[1], 1)
        self.assertEqual(struct.unpack("<hh", cuerpo[4:8]), (0, 0))
        self.assertEqual(tuple(cuerpo[8:12]), (90, 90, 90, 90))

    def test_consigna_se_limita_y_se_empaqueta_con_crc(self):
        ev = ejecutar(INO_TX, ["I", "W 1", "S CMD,999,-999,200,0,90,90", "A 60"])
        hexa = next(e for _, e in ev if e.startswith("UDP ")).split()[2]
        p = bytes.fromhex(hexa)
        self.assertEqual(len(p), 13)
        self.assertEqual(p[0], 0xA5)
        self.assertEqual(struct.unpack("<hh", p[4:8]), (255, -255))
        self.assertEqual(tuple(p[8:12]), (170, 10, 90, 90))
        self.assertEqual(crc8(p[:-1]), p[-1])

    def test_trama_invalida_no_alimenta_el_watchdog(self):
        ev = ejecutar(INO_TX, ["I", "W 1", "S CMD,1,2,3", "S BASURA", "A 700"])
        self.assertEqual(len(seriales(ev, "ERR:TRAMA")), 2)
        self.assertNotIn("SER WARN:HMI_TIMEOUT", [e for _, e in ev])
        p = bytes.fromhex(next(e for _, e in ev if e.startswith("UDP ")).split()[2])
        self.assertEqual(struct.unpack("<hh", p[4:8]), (0, 0))

    def test_stop_se_transmite_de_inmediato(self):
        ev = ejecutar(INO_TX, ["I", "W 1", "A 10", "S STOP", "A 1"])
        p = bytes.fromhex(next(e for _, e in ev if e.startswith("UDP ")).split()[2])
        self.assertEqual(p[1], 1)
        self.assertLessEqual(next(t for t, e in ev if e.startswith("UDP ")), 11)

    def test_sin_ejecutor_informa_ok_cero_y_no_consume_secuencia(self):
        ev = ejecutar(INO_TX, ["I", "A 120"])
        lineas = seriales(ev, "TX,")
        self.assertTrue(lineas)
        self.assertTrue(all(x.split(",")[1] == "0" and x.endswith(",0") for x in lineas))
        self.assertFalse([e for _, e in ev if e.startswith("UDP ")])


@unittest.skipUnless(shutil.which("g++"), "Requiere g++")
class TestEjecutorL9110S(unittest.TestCase):
    """Compilacion por defecto: el rover lleva L9110S."""

    def ultimo(self, ev, pin):
        return pwm(ev, pin)[-1][1]

    def test_motores_quedan_apagados_en_el_arranque(self):
        ev = ejecutar(INO_RX, ["P 1", "C 1", "I", "A 20"])
        for pin in (A1A, A1B, B1A, B1B):
            self.assertTrue(pwm(ev, pin), pin)
            self.assertTrue(all(v == 0 for _, v in pwm(ev, pin)), pin)

    def test_cada_sentido_sale_por_su_pin(self):
        ev = ejecutar(INO_RX, ejecutor_operando(*stream(1, 60, izq=150, der=-100)))
        self.assertEqual([self.ultimo(ev, p) for p in (A1A, A1B, B1A, B1B)], [150, 0, 0, 100])

    def test_pivote_mueve_los_dos_lados_en_sentidos_opuestos(self):
        ev = ejecutar(INO_RX, ejecutor_operando(*stream(1, 60, izq=-200, der=200, servos=(45, 135, 135, 45))))
        self.assertEqual([self.ultimo(ev, p) for p in (A1A, A1B, B1A, B1B)], [0, 200, 200, 0])
        for pin in (A1B, B1A):
            valores = [v for _, v in pwm(ev, pin)]
            for a, b in zip(valores, valores[1:]):
                self.assertLessEqual(abs(b - a), 4)

    def test_inversion_pasa_por_cero_y_nunca_activa_los_dos_pines(self):
        ev = ejecutar(INO_RX, ejecutor_operando(*stream(1, 20, izq=120), *stream(21, 30, izq=-120)))
        avance = reversa = 0
        hubo_avance = False
        t_cero = t_rev = None
        for t, e in ev:
            if e.startswith(f"PWM {A1A} "):
                avance = int(e.split()[2])
                hubo_avance = hubo_avance or avance > 0
                if avance == 0 and hubo_avance and t_cero is None:
                    t_cero = t
            elif e.startswith(f"PWM {A1B} "):
                reversa = int(e.split()[2])
                if reversa > 0 and t_rev is None:
                    t_rev = t
            self.assertFalse(avance > 0 and reversa > 0)
        self.assertIsNotNone(t_cero)
        self.assertGreaterEqual(t_rev - t_cero, 80)
        self.assertEqual(self.ultimo(ev, A1B), 120)


@unittest.skipUnless(shutil.which("g++"), "Requiere g++")
class TestExtremoAExtremo(unittest.TestCase):
    def test_comando_de_hmi_llega_al_ejecutor_y_telemetria_vuelve(self):
        guion_tx = ["I", "W 1"]
        for _ in range(30):
            guion_tx += ["S CMD,180,-90,120,120,60,60", "A 50"]
        tramas = [e.split()[2] for _, e in ejecutar(INO_TX, guion_tx) if e.startswith("UDP ")]
        self.assertGreater(len(tramas), 25)

        guion_rx = ejecutor_operando()
        for h in tramas:
            guion_rx += [f"U {h}", "A 50"]
        ev_rx = ejecutar(INO_RX, guion_rx, L298N)
        self.assertEqual(pwm(ev_rx, ENA)[-1][1], 180)
        self.assertEqual(pwm(ev_rx, ENB)[-1][1], 90)
        self.assertIn(f"DW {IN1} 1", [e for _, e in ev_rx])
        ultima_rx = seriales(ev_rx, "RX,")[-1].split(",")
        self.assertEqual(ultima_rx[2:8], ["180", "-90", "120", "120", "60", "60"])

        tlm_hex = [e.split()[2] for _, e in ev_rx if e.startswith("UDP 192.168.4.1:4210")]
        self.assertTrue(tlm_hex)
        ev_tx = ejecutar(INO_TX, ["I", f"U {tlm_hex[-1]}", "A 3"])
        linea = seriales(ev_tx, "TLM,")[0].split(",")
        self.assertEqual(linea[2], "180")
        self.assertEqual(linea[3], "-90")
        self.assertEqual(linea[16], "2")

    def test_telemetria_corrupta_no_se_reenvia(self):
        ev_rx = ejecutar(INO_RX, ejecutor_operando("A 250"), L298N)
        h = next(e.split()[2] for _, e in ev_rx if e.startswith("UDP 192.168.4.1"))
        malo = bytes.fromhex(h)
        malo = (malo[:-1] + bytes([malo[-1] ^ 0xFF])).hex()
        ev_tx = ejecutar(INO_TX, ["I", f"U {malo}", "A 3"])
        self.assertEqual(seriales(ev_tx, "TLM,"), [])


class TestCoherencia(unittest.TestCase):
    @staticmethod
    def bloque(texto, nombre):
        return re.search(r"struct __attribute__\(\(packed\)\) " + nombre + r" \{.*?\};", texto, re.S).group(0)

    def setUp(self):
        self.tx = INO_TX.read_text(encoding="utf-8")
        self.rx = INO_RX.read_text(encoding="utf-8")

    def test_estructuras_identicas_en_ambos_firmwares(self):
        for nombre in ("PaqueteControl", "PaqueteTelemetria"):
            self.assertEqual(self.bloque(self.tx, nombre), self.bloque(self.rx, nombre))

    def test_constantes_de_red_identicas(self):
        for patron in (r"WIFI_SSID = (\S+);", r"WIFI_PASS = (\S+);", r"WIFI_CANAL = (\d+);",
                       r"PUERTO_UDP = (\d+);", r"MAGIC_CONTROL = (\S+);", r"MAGIC_TELEMETRIA = (\S+);",
                       r'VERSION_FW "(.+?)"'):
            self.assertEqual(re.search(patron, self.tx).group(1), re.search(patron, self.rx).group(1), patron)

    def test_sin_delay_en_ninguno(self):
        for texto in (self.tx, self.rx):
            sin_comentarios = re.sub(r"/\*.*?\*/|//[^\n]*", "", texto, flags=re.S)
            self.assertIsNone(re.search(r"\bdelay\s*\(", sin_comentarios))

    def test_limites_de_seguridad(self):
        for texto in (self.tx, self.rx):
            self.assertIn("ANGULO_MIN = 10", texto)
            self.assertIn("ANGULO_MAX = 170", texto)
        self.assertIn("TIMEOUT_MS = 1000", self.rx)


if __name__ == "__main__":
    unittest.main()
