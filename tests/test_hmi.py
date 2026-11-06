"""Pruebas de la logica de las dos HMI. Las de interfaz requieren Tkinter y se omiten sin el."""

import queue
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "01_Oficial" / "HMI"))

import HMI_Rover as hmi  # noqa: E402
import HMI_Rover_Debug as dbg  # noqa: E402

SIN_TECLAS = {k: False for k in ("w", "a", "s", "d", "q", "e", "space")}
TLM = "TLM,120,50,50,90,90,90,90,-55,1,0,6000,120,0,0,0,2,1"


def teclas(*activas):
    return {**SIN_TECLAS, **{k: True for k in activas}}


class Reloj:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class PuertoFalso:
    """Simula un puerto serie: entrega lineas programadas y guarda lo escrito."""

    def __init__(self):
        self.lineas = queue.Queue()
        self.escrito = []
        self.falla = False

    def readline(self):
        if self.falla:
            raise OSError("puerto desconectado")
        try:
            return self.lineas.get(timeout=0.01).encode() + b"\n"
        except queue.Empty:
            return b""

    def write(self, datos):
        self.escrito.append(datos.decode())

    def close(self):
        pass


class TestProtocolo(unittest.TestCase):
    def test_linea_de_consigna_con_limites(self):
        c = hmi.Consigna(999, -999, (0, 180, 90, 90))
        self.assertEqual(c.linea(), "CMD,255,-255,10,170,90,90\n")

    def test_parsea_todos_los_tipos(self):
        self.assertEqual(hmi.parsear_linea("ID:NANO_ESP32:TX:v3.0").datos["rol"], "TX")
        self.assertEqual(hmi.parsear_linea("TX,5,10,-10,90,91,92,93,1").datos["s4"], 93)
        self.assertEqual(hmi.parsear_linea("RX,5,10,-10,90,91,92,93,50,4,-4,90,90,90,90").datos["apl_der"], -4)
        self.assertEqual(hmi.parsear_linea(TLM).datos["rssi"], -55)
        self.assertEqual(hmi.parsear_linea("LINK,1,1,120").datos["clientes"], 1)
        self.assertEqual(hmi.parsear_linea("BOOT,9,2").datos["causa"], 9)

    def test_lineas_danadas_no_lanzan_excepcion(self):
        for linea in ("TX,1,2", "TX,a,b,c,d,e,f,g,h", "ID:roto", "", "WARN:FAILSAFE", "\xff\xfe"):
            self.assertEqual(hmi.parsear_linea(linea).tipo, "TEXTO", linea)

    def test_coincide_con_lo_que_imprime_el_firmware(self):
        raiz = Path(__file__).resolve().parent.parent / "01_Oficial"
        tx = (raiz / "Transmisor_NanoESP32/Transmisor_NanoESP32.ino").read_text(encoding="utf-8")
        rx = (raiz / "Ejecutor_NanoESP32/Ejecutor_NanoESP32.ino").read_text(encoding="utf-8")
        for texto, prefijo, campos in ((tx, '"TX,', hmi.CAMPOS_TX), (tx, '"TLM,', hmi.CAMPOS_TLM), (rx, '"TLM,', hmi.CAMPOS_TLM),
                                       (rx, '"RX,', hmi.CAMPOS_RX), (tx, '"LINK,', hmi.CAMPOS_LINK), (rx, '"BOOT,', hmi.CAMPOS_BOOT)):
            inicio = texto.index(prefijo)
            formato = texto[inicio:texto.index('"', inicio + 1)]
            self.assertEqual(formato.count("%"), len(campos), formato)


class TestCinematica(unittest.TestCase):
    def consigna(self, *activas, modo="ACKERMANN", **kw):
        return hmi.calcular_consigna(teclas(*activas), modo, 200, 100, [30, 40, 50, 60], **kw)

    def motores(self, *activas, **kw):
        c = self.consigna(*activas, **kw)[1]
        return c.izq, c.der

    def test_avance_y_reversa_llevan_signo_real(self):
        self.assertEqual(self.consigna("w")[1], hmi.Consigna(200, 100))
        self.assertEqual(self.consigna("s")[1], hmi.Consigna(-200, -100))

    def test_reposo_centra_servos_y_para_motores(self):
        self.assertEqual(self.consigna()[1], hmi.Consigna())

    def test_direccion_sola_orienta_ruedas_sin_mover_motores(self):
        for tecla, servos in (("a", (120, 120, 60, 60)), ("d", (60, 60, 120, 120)),
                              ("q", (45, 135, 135, 45)), ("e", (45, 135, 135, 45))):
            etiqueta, c = self.consigna(tecla)
            self.assertEqual((c.izq, c.der, c.servos), (0, 0, servos), tecla)
            self.assertIn("detenido", etiqueta)
        _, c = self.consigna("a", modo="CRAB")
        self.assertEqual((c.izq, c.der, c.servos), (0, 0, (135,) * 4))

    def test_giro_ackermann_con_traccion(self):
        _, c = self.consigna("a", "w")
        self.assertEqual((c.izq, c.der, c.servos), (140, 100, (120, 120, 60, 60)))
        _, c = self.consigna("d", "w")
        self.assertEqual((c.izq, c.der, c.servos), (200, 70, (60, 60, 120, 120)))
        _, c = self.consigna("a", "s")
        self.assertEqual((c.izq, c.der, c.servos), (-140, -100, (120, 120, 60, 60)))

    def test_cangrejo_con_traccion(self):
        _, c = self.consigna("a", "w", modo="CRAB")
        self.assertEqual((c.izq, c.der, c.servos), (200, 100, (135,) * 4))
        _, c = self.consigna("d", "s", modo="CRAB")
        self.assertEqual((c.izq, c.der, c.servos), (-200, -100, (45,) * 4))

    def test_pivote_con_traccion(self):
        etiqueta, c = self.consigna("q", "w")
        self.assertEqual((c.izq, c.der, c.servos), (-200, 100, (45, 135, 135, 45)))
        self.assertEqual(etiqueta, "AVANCE + PIVOTE IZQ")
        self.assertEqual(self.motores("e", "w"), (200, -100))
        self.assertEqual(self.motores("q", "s"), (200, -100))
        self.assertEqual(self.motores("e", "s"), (-200, 100))

    def test_w_y_s_juntas_se_anulan(self):
        _, c = self.consigna("w", "s", "a")
        self.assertEqual((c.izq, c.der), (0, 0))

    def test_prioridad_de_direccion(self):
        self.assertEqual(self.motores("a", "q", "w"), (-200, 100))
        self.assertEqual(self.consigna("a", "d")[1].servos, (120, 120, 60, 60))

    def test_espacio_prevalece(self):
        self.assertEqual(self.consigna("w", "space")[1], hmi.Consigna())

    def test_modo_manual_usa_sliders(self):
        self.assertEqual(self.consigna("a", modo="MANUAL")[1].servos, (30, 40, 50, 60))

    def test_inversiones(self):
        _, c = self.consigna("w", invertir_izq=True)
        self.assertEqual((c.izq, c.der), (-200, 100))
        self.assertEqual(self.consigna("a", invertir_servos=True)[1].servos, (60, 60, 120, 120))
        _, c = self.consigna("q", "w", invertir_der=True)
        self.assertEqual((c.izq, c.der), (-200, -100))


class TestEstadoEnlace(unittest.TestCase):
    def setUp(self):
        self.reloj = Reloj()
        self.est = hmi.EstadoEnlace(self.reloj)

    def niveles(self):
        return {n: nivel for n, nivel, _ in self.est.senales()}

    def recibir(self, linea):
        self.est.procesar(hmi.parsear_linea(linea))

    def test_sin_conectar_todo_en_falla(self):
        self.assertEqual(set(self.niveles().values()), {"falla"})

    def test_cadena_completa_correcta(self):
        self.est.registrar_usb(True, "COM4")
        self.recibir("ID:NANO_ESP32:TX:v3.0")
        self.recibir("LINK,1,1,100")
        self.recibir(TLM)
        self.assertEqual(set(self.niveles().values()), {"ok"})

    def test_placa_equivocada_y_version_vieja(self):
        self.est.registrar_usb(True, "COM4")
        self.recibir("ID:NANO_ESP32:RX:v3.0")
        self.assertEqual(self.niveles()["Transmisor"], "falla")
        self.recibir("ID:NANO_ESP32:TX:v2.3")
        self.assertEqual(self.niveles()["Transmisor"], "aviso")

    def test_telemetria_vencida_se_marca_como_falla(self):
        self.recibir(TLM)
        self.assertEqual(self.niveles()["Telemetria"], "ok")
        self.reloj.t += 1.5
        self.assertEqual(self.niveles()["Telemetria"], "falla")
        self.assertEqual(self.niveles()["Ejecutor"], "falla")

    def test_failsafe_y_pca_ausente(self):
        self.recibir("TLM,1,0,0,90,90,90,90,-50,1,0,6000,1,0,0,1,3,1")
        self.assertEqual(self.niveles()["Ejecutor"], "falla")
        self.recibir("TLM,1,0,0,90,90,90,90,-50,1,0,6100,1,0,0,1,2,0")
        self.assertIn("PCA9685", dict((n, d) for n, _, d in self.est.senales())["Ejecutor"])

    def test_alerta_brownout_y_reinicio_detectado_por_uptime(self):
        self.recibir(TLM)
        self.assertEqual(self.est.alerta_reinicio(), "")
        self.recibir("TLM,2,0,0,90,90,90,90,-50,9,1,500,1,0,0,0,1,1")
        self.assertEqual(self.est.reinicios_detectados, 1)
        self.assertIn("BROWNOUT", self.est.alerta_reinicio())

    def test_tasa_de_envio(self):
        for i in range(20):
            self.recibir(f"TX,{i},0,0,90,90,90,90,1")
            self.reloj.t += 0.05
        self.assertEqual(self.est.tasa_envio_hz(), 20)
        self.reloj.t += 2
        self.assertEqual(self.est.tasa_envio_hz(), 0)


class TestEnlaceSerie(unittest.TestCase):
    def esperar(self, condicion, limite=2.0):
        fin = time.monotonic() + limite
        while time.monotonic() < fin:
            if condicion():
                return True
            time.sleep(0.01)
        return False

    def test_lee_lineas_y_escribe(self):
        eventos = queue.Queue()
        puerto = PuertoFalso()
        enlace = hmi.EnlaceSerie("TX", eventos, lambda _: puerto)
        enlace.abrir("COM1")
        self.assertTrue(self.esperar(lambda: enlace.conectado))
        puerto.lineas.put("PONG:TX")
        self.assertTrue(enlace.escribir("PING\n"))
        vistos = []
        self.assertTrue(self.esperar(lambda: (vistos.append(eventos.get(timeout=1)) or vistos[-1][1] == "linea")))
        self.assertEqual(vistos[-1][2], "PONG:TX")
        self.assertEqual(puerto.escrito, ["PING\n"])
        enlace.terminar()

    def test_reconecta_si_se_pierde_el_puerto(self):
        eventos = queue.Queue()
        puertos = [PuertoFalso(), PuertoFalso()]
        abiertos = []

        def fabrica(_):
            abiertos.append(puertos[len(abiertos)])
            return abiertos[-1]

        enlace = hmi.EnlaceSerie("TX", eventos, fabrica)
        enlace.abrir("COM1")
        self.assertTrue(self.esperar(lambda: enlace.conectado))
        puertos[0].falla = True
        self.assertTrue(self.esperar(lambda: len(abiertos) == 2 and enlace.conectado, 3.0))
        enlace.terminar()

    def test_cierre_manual_no_reconecta(self):
        abiertos = []
        enlace = hmi.EnlaceSerie("TX", queue.Queue(), lambda _: abiertos.append(1) or PuertoFalso())
        enlace.abrir("COM1")
        self.assertTrue(self.esperar(lambda: enlace.conectado))
        enlace.cerrar()
        time.sleep(0.3)
        self.assertEqual(len(abiertos), 1)
        self.assertFalse(enlace.escribir("x"))
        enlace.terminar()


def tx(seq, izq=10, ok=1):
    return {"seq": seq, "izq": izq, "der": 0, "s1": 90, "s2": 90, "s3": 90, "s4": 90, "ok": ok}


class TestComparador(unittest.TestCase):
    def test_empareja_y_mide_latencia(self):
        c = dbg.Comparador()
        c.registrar_tx(tx(1), 10.0)
        c.registrar_rx(tx(1), 10.02)
        m = c.metricas
        self.assertEqual((m.enviadas, m.recibidas, m.perdidas, m.diferencias), (1, 1, 0, 0))
        self.assertAlmostEqual(m.latencia_ms, 20.0, places=3)

    def test_rx_antes_que_tx_tambien_empareja(self):
        c = dbg.Comparador()
        c.registrar_rx(tx(1), 10.001)
        c.registrar_tx(tx(1), 10.0)
        c.vencer(20.0)
        self.assertEqual(c.metricas.perdidas, 0)
        self.assertAlmostEqual(c.metricas.latencia_ms, 1.0, places=3)

    def test_trama_sin_respuesta_cuenta_como_perdida(self):
        c = dbg.Comparador()
        c.registrar_tx(tx(1), 10.0)
        c.registrar_tx(tx(2), 10.05)
        c.registrar_rx(tx(2), 10.06)
        c.vencer(10.5)
        self.assertEqual(c.metricas.perdidas, 0)
        c.vencer(11.2)
        self.assertEqual(c.metricas.perdidas, 1)
        self.assertAlmostEqual(c.metricas.porcentaje_perdidas, 50.0)

    def test_diferencia_de_contenido(self):
        c = dbg.Comparador()
        c.registrar_tx(tx(1, izq=10), 10.0)
        c.registrar_rx(tx(1, izq=99), 10.01)
        self.assertEqual(c.metricas.diferencias, 1)
        self.assertEqual(c.ultima_diferencia[1]["izq"], 99)

    def test_no_cuenta_tramas_no_emitidas(self):
        c = dbg.Comparador()
        c.registrar_tx(tx(0, ok=0), 10.0)
        c.vencer(20.0)
        self.assertEqual((c.metricas.enviadas, c.metricas.perdidas), (0, 0))


class TestSegmentar(unittest.TestCase):
    def test_corta_la_linea_en_los_huecos(self):
        datos = [(10.0, 1), (10.05, 2), (12.0, 3), (12.05, 4)]
        self.assertEqual(dbg.segmentar(datos, 0.0), [[(10.0, 1), (10.05, 2)], [(12.0, 3), (12.05, 4)]])

    def test_descarta_lo_que_quedo_fuera_de_la_ventana(self):
        self.assertEqual(dbg.segmentar([(1.0, 1), (10.0, 2)], 5.0), [[(10.0, 2)]])
        self.assertEqual(dbg.segmentar([], 0.0), [])


class TestPerfiles(unittest.TestCase):
    def test_todos_respetan_limites(self):
        for nombre in dbg.PERFILES[1:]:
            for i in range(200):
                c = dbg.perfil_prueba(nombre, i * 0.1)
                self.assertTrue(abs(c.izq) <= 255 and abs(c.der) <= 255, nombre)
                self.assertTrue(all(10 <= a <= 170 for a in c.servos), nombre)

    def test_manual_no_genera_consigna(self):
        self.assertIsNone(dbg.perfil_prueba("Manual", 1.0))


@unittest.skipIf(hmi.tk is None, "Requiere Tkinter")
class TestInterfaces(unittest.TestCase):
    def setUp(self):
        try:
            self.root = hmi.tk.Tk()
        except hmi.tk.TclError as error:
            self.skipTest(f"Sin pantalla: {error}")
        self.puerto = PuertoFalso()

    def tearDown(self):
        pass

    def bombear(self, segundos):
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self.root.update()
            time.sleep(0.01)

    def test_hmi_normal_emite_a_20_hz_con_la_tecla_sostenida(self):
        app = hmi.HMIRover(self.root, lambda _: self.puerto)
        app.cb_puerto["values"] = ("COM1",)
        app.cb_puerto.set("COM1")
        app.alternar_conexion()
        self.bombear(0.2)
        app.pot_izq.set(180)
        app.pot_der.set(170)
        app._fijar_tecla("w", True)
        self.puerto.escrito.clear()
        self.bombear(1.0)
        comandos = [x for x in self.puerto.escrito if x.startswith("CMD")]
        self.assertGreaterEqual(len(comandos), 15)  # Antes solo se enviaba al cambiar la tecla
        self.assertTrue(all(x == "CMD,180,170,90,90,90,90\n" for x in comandos))

        self.puerto.lineas.put("ID:NANO_ESP32:TX:v3.0")
        self.puerto.lineas.put("LINK,1,1,50")
        self.puerto.lineas.put("TX,7,180,170,90,90,90,90,1")
        self.puerto.lineas.put(TLM)
        self.bombear(0.4)
        self.assertEqual({n for _, n, _ in app.estado.senales()}, {"ok"})
        self.assertIn("#7", app.lbl_tx.cget("text"))
        self.assertIn("OPERACION", app.panel_senales.filas["Ejecutor"][1].cget("text"))

        app._fijar_tecla("w", False)
        app.parada_emergencia()
        self.bombear(0.2)
        self.assertIn("STOP\n", self.puerto.escrito)
        app.cerrar()

    def test_hmi_normal_para_si_pierde_el_foco(self):
        app = hmi.HMIRover(self.root, lambda _: self.puerto)
        app._fijar_tecla("w", True)
        self.assertEqual(app.etiqueta, "AVANCE")

        class Evento:
            widget = app.root

        app._foco_perdido(Evento)
        self.assertEqual(app.etiqueta, "REPOSO")
        app.cerrar()

    def test_hmi_debug_compara_grafica_y_marca_reinicios(self):
        puertos = {"COM1": PuertoFalso(), "COM2": PuertoFalso()}
        app = dbg.HMIRoverDebug(self.root, lambda p: puertos[p])
        for rol, puerto in (("TX", "COM1"), ("RX", "COM2")):
            app.combo[rol]["values"] = tuple(puertos)
            app.combo[rol].set(puerto)
            app.alternar(rol)
        self.bombear(0.3)
        puertos["COM1"].lineas.put("ID:NANO_ESP32:TX:v3.0")
        puertos["COM2"].lineas.put("ID:NANO_ESP32:RX:v3.0")
        for seq in range(1, 11):
            puertos["COM1"].lineas.put(f"TX,{seq},100,100,90,90,90,90,1")
            puertos["COM2"].lineas.put(f"RX,{seq},100,100,90,90,90,90,50,80,80,90,90,90,90")
        puertos["COM2"].lineas.put(TLM)
        puertos["COM2"].lineas.put("BOOT,9,3")
        self.bombear(0.6)

        m = app.comparador.metricas
        self.assertEqual((m.enviadas, m.recibidas, m.diferencias), (10, 10, 0))
        self.assertEqual(app.reinicios_vistos, 1)
        self.assertEqual(app.series.reinicios[-1][1], "BROWNOUT")
        self.assertEqual(len(app.series.enviado["izq"]), 10)
        self.assertEqual(app.series.aplicado["izq"][-1][1], 80)
        self.assertEqual(app.ids["RX"]["rol"], "RX")

        # Cada grafica dibujo sus series y el marcador
        lineas = app.graficas["izq"].canvas.find_all()
        self.assertGreater(len(lineas), 8)

        app.emitir.set(True)
        app.perfil.set("Escalon motores")
        puertos["COM1"].escrito.clear()
        self.bombear(0.6)
        self.assertTrue([x for x in puertos["COM1"].escrito if x.startswith("CMD")])

        app.parada()
        self.bombear(0.3)
        self.assertIn("STOP\n", puertos["COM1"].escrito)
        self.assertFalse(app.emitir.get())
        puertos["COM1"].escrito.clear()
        self.bombear(0.3)
        self.assertFalse([x for x in puertos["COM1"].escrito if x.startswith("CMD")])
        app.cerrar()

    def test_debug_no_emite_sin_activarlo_explicitamente(self):
        puerto = PuertoFalso()
        app = dbg.HMIRoverDebug(self.root, lambda _: puerto)
        app.combo["TX"]["values"] = ("COM1",)
        app.combo["TX"].set("COM1")
        app.alternar("TX")
        self.bombear(0.5)
        self.assertFalse([x for x in puerto.escrito if x.startswith("CMD")])
        app.cerrar()


if __name__ == "__main__":
    unittest.main()
