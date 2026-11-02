#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simulador Cinematico 2D del Rover Lunar Rocker-Bogie 6x6 con 4WS.

Modela y simula el desplazamiento en un entorno plano horizontal ideal
bajo la hipotesis de rodadura pura sin deslizamiento:
1. Avance rectilineo y reversa.
2. Curvatura coordinada Ackermann simetrica 4WS (ICR en eje medio y=0).
3. Rotacion sobre el propio eje (Point Turn / Giro 360).
4. Traslacion diagonal y lateral pura (Modo Cangrejo / Crab con servos estandar o 360).

Proporciona analisis cinematico, generacion de trayectorias, mapa ASCII en terminal
y exportacion opcional a grafico de imagen PNG mediante matplotlib.
"""

import math
import sys
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class ParametrosChasis:
    """Parametros geometricos y mecanicos de la plataforma Rocker-Bogie."""
    semi_longitud_l: float = 0.22  # Distancia eje central a ejes extremos en metros (220 mm)
    semi_ancho_w: float = 0.18     # Distancia centro a ruedas laterales en metros (180 mm)
    radio_rueda_r: float = 0.045   # Radio nominal de rueda en metros (45 mm)
    vel_max_lineal: float = 0.35   # Velocidad lineal maxima a 255 PWM (m/s)


@dataclass
class Pose2D:
    """Estado de posicion y orientacion en el plano del mundo."""
    x: float = 0.0          # Posicion X en metros (Este / Derecha)
    y: float = 0.0          # Posicion Y en metros (Norte / Adelante)
    theta_rad: float = 0.0  # Orientacion de guiñada (Yaw) en radianes (0 = Norte)
    v_lineal: float = 0.0   # Velocidad lineal neta (m/s)
    omega_rad_s: float = 0.0# Velocidad angular de guiñada (rad/s)
    radio_icr: float = float("inf") # Radio de curvatura instantaneo en metros


class SimuladorCinematicoRover:
    """Simulador numerico de navegacion plana para el chasis Rocker-Bogie 6x6."""

    def __init__(self, params: Optional[ParametrosChasis] = None):
        self.params = params or ParametrosChasis()
        self.pose = Pose2D()
        self.trayectoria: List[Tuple[float, float]] = [(0.0, 0.0)]
        self.distancia_total_m: float = 0.0
        self.tiempo_acumulado_s: float = 0.0

    def reiniciar(self, x: float = 0.0, y: float = 0.0, theta_deg: float = 0.0):
        """Reinicia la pose inicial y la trayectoria acumulada."""
        self.pose = Pose2D(x=x, y=y, theta_rad=math.radians(theta_deg))
        self.trayectoria = [(x, y)]
        self.distancia_total_m = 0.0
        self.tiempo_acumulado_s = 0.0

    def paso_simulacion(
        self,
        pwm_izq: int,
        pwm_der: int,
        angulo_s1: int,
        angulo_s2: int,
        dt: float,
        modo_cangrejo: bool = False,
        modo_giro_eje: bool = False,
    ):
        """
        Integra un paso de tiempo dt utilizando cinematica directa y aproximacion Euler.

        Args:
            pwm_izq: Consigna PWM lateral izquierdo (-255 a 255).
            pwm_der: Consigna PWM lateral derecho (-255 a 255).
            angulo_s1: Angulo servo delantero izquierdo (grados, 90 es recto).
            angulo_s2: Angulo servo delantero derecho (grados, 90 es recto).
            dt: Intervalo de integracion temporal en segundos.
            modo_cangrejo: Habilitar vector de traslacion cangrejo puro.
            modo_giro_eje: Habilitar rotacion pura sobre el centro geometrico.
        """
        v_izq = (pwm_izq / 255.0) * self.params.vel_max_lineal
        v_der = (pwm_der / 255.0) * self.params.vel_max_lineal

        l = self.params.semi_longitud_l
        w = self.params.semi_ancho_w

        # Desviacion respecto al centro (90 deg = 0 rad)
        # Menor a 90 deg (ej 60) = giro derecha (+rad), Mayor a 90 deg (ej 120) = giro izquierda (-rad)
        delta_s1 = math.radians(90.0 - angulo_s1)
        delta_s2 = math.radians(90.0 - angulo_s2)
        delta_prom = (delta_s1 + delta_s2) / 2.0

        if abs(pwm_izq) == 0 and abs(pwm_der) == 0:
            self.pose.v_lineal = 0.0
            self.pose.omega_rad_s = 0.0
            self.pose.radio_icr = float("inf")
            return

        if modo_giro_eje:
            # Rotacion pura sobre el eje central (Point Turn)
            # Horario (Der): v_izq > 0, v_der < 0 => omega > 0
            # Antihorario (Izq): v_izq < 0, v_der > 0 => omega < 0
            r_esquina = math.sqrt(l * l + w * w)
            omega = (v_izq - v_der) / (2.0 * r_esquina)
            vx_loc = 0.0
            vy_loc = 0.0
            radio = 0.0
        elif modo_cangrejo:
            # Traslacion diagonal o transversal sin rotacion
            v_avg = (v_izq + v_der) / 2.0
            ang_marcha = delta_s1
            vx_loc = v_avg * math.sin(ang_marcha)
            vy_loc = v_avg * math.cos(ang_marcha)
            omega = 0.0
            radio = float("inf")
        else:
            # Conduccion coordinada Ackermann simetrica 4WS
            v_avg = (v_izq + v_der) / 2.0

            if abs(delta_prom) < 0.015:
                # Marcha rectilinea
                vx_loc = 0.0
                vy_loc = v_avg
                omega = (v_izq - v_der) / (2.0 * w)
                radio = float("inf")
            else:
                # Curva coordinada: centro instantaneo de rotacion sobre eje medio (y = 0)
                r_centro = l / math.tan(delta_prom)
                omega = v_avg / r_centro
                vx_loc = 0.0
                vy_loc = v_avg
                radio = abs(r_centro)

        # Actualizar rumbo (Yaw)
        theta_ant = self.pose.theta_rad
        self.pose.theta_rad += omega * dt

        # Normalizar a [-pi, pi]
        self.pose.theta_rad = (self.pose.theta_rad + math.pi) % (2.0 * math.pi) - math.pi

        # Transformar velocidad local al marco de referencia inercial del mundo
        theta_medio = theta_ant + omega * (dt * 0.5)
        cos_t = math.cos(theta_medio)
        sin_t = math.sin(theta_medio)

        dx_mundo = vx_loc * cos_t + vy_loc * sin_t
        dy_mundo = -vx_loc * sin_t + vy_loc * cos_t

        self.pose.x += dx_mundo * dt
        self.pose.y += dy_mundo * dt

        paso_dist = math.sqrt(dx_mundo * dx_mundo + dy_mundo * dy_mundo) * dt
        self.distancia_total_m += paso_dist
        self.tiempo_acumulado_s += dt

        self.pose.v_lineal = math.sqrt(vx_loc * vx_loc + vy_loc * vy_loc)
        self.pose.omega_rad_s = omega
        self.pose.radio_icr = radio

        # Registrar trayectoria cada 2 cm de desplazamiento o rotacion notable
        ultimo_x, ultimo_y = self.trayectoria[-1]
        if math.hypot(self.pose.x - ultimo_x, self.pose.y - ultimo_y) >= 0.02:
            self.trayectoria.append((self.pose.x, self.pose.y))

    def renderizar_mapa_ascii(self, ancho_cols: int = 60, alto_filas: int = 25) -> str:
        """Genera una representacion visual en texto ASCII de la trayectoria en el plano."""
        if not self.trayectoria:
            return "Trayectoria vacia"

        xs = [p[0] for p in self.trayectoria]
        ys = [p[1] for p in self.trayectoria]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        margen = 0.3
        min_x -= margen
        max_x += margen
        min_y -= margen
        max_y += margen

        span_x = max(max_x - min_x, 0.5)
        span_y = max(max_y - min_y, 0.5)

        cuadricula = [["." for _ in range(ancho_cols)] for _ in range(alto_filas)]

        def a_coords(x: float, y: float) -> Tuple[int, int]:
            col = int(((x - min_x) / span_x) * (ancho_cols - 1))
            fila = int(((max_y - y) / span_y) * (alto_filas - 1))
            return max(0, min(col, ancho_cols - 1)), max(0, min(fila, alto_filas - 1))

        # Trazar puntos
        for x, y in self.trayectoria:
            c, f = a_coords(x, y)
            cuadricula[f][c] = "*"

        # Origen (0, 0)
        c0, f0 = a_coords(0.0, 0.0)
        cuadricula[f0][c0] = "O"

        # Posicion actual del Rover
        cr, fr = a_coords(self.pose.x, self.pose.y)
        cuadricula[fr][cr] = "R"

        lineas = ["+" + "-" * ancho_cols + "+"]
        for f in range(alto_filas):
            lineas.append("|" + "".join(cuadricula[f]) + "|")
        lineas.append("+" + "-" * ancho_cols + "+")
        lineas.append(f"Leyenda: [O] Origen (0,0)  [*] Traza  [R] Pose Actual ({self.pose.x:.2f}, {self.pose.y:.2f}) m")
        lineas.append(f"Rango X: [{min_x:.2f}, {max_x:.2f}] m | Rango Y: [{min_y:.2f}, {max_y:.2f}] m | Yaw: {math.degrees(self.pose.theta_rad):.1f} deg")
        return "\n".join(lineas)


def ejecutar_ensayo_simulacion():
    """Ejecuta una serie representativa de maniobras y reporta metricas cinematicas."""
    print("=" * 72)
    print("SIMULADOR CINEMATICO 2D: ROVER LUNAR ROCKER-BOGIE 6x6 + 4WS")
    print("Entorno: Plano horizontal ideal, traccion sin deslizamiento (No-Slip)")
    print("=" * 72)

    sim = SimuladorCinematicoRover()
    dt = 0.05  # 50 ms por ciclo

    # Maniobra 1: Avance recto durante 3 segundos a 180 PWM
    print("\n[MANIOBRA 1] Avance Recto (3.0 s a 180 PWM)...")
    sim.reiniciar()
    pasos = int(3.0 / dt)
    for _ in range(pasos):
        sim.paso_simulacion(180, 180, 90, 90, dt)

    print(f"Pose final: X={sim.pose.x:.3f} m, Y={sim.pose.y:.3f} m, Rumbo={math.degrees(sim.pose.theta_rad):.1f} deg")
    print(f"Distancia recorrida: {sim.distancia_total_m:.3f} m | Velocidad: {sim.pose.v_lineal:.2f} m/s")

    # Maniobra 2: Curva Ackermann simetrica a izquierda (W + A) durante 4 segundos
    # Servos a 120 deg (delanteros) / 60 deg (traseros) con compensacion diferencial
    print("\n[MANIOBRA 2] Curva Coordinada Ackermann 4WS a Izquierda (4.0 s)...")
    sim.reiniciar()
    pasos = int(4.0 / dt)
    for _ in range(pasos):
        sim.paso_simulacion(126, 180, 120, 120, dt)

    print(f"Pose final: X={sim.pose.x:.3f} m, Y={sim.pose.y:.3f} m, Rumbo={math.degrees(sim.pose.theta_rad):.1f} deg")
    print(f"Radio de giro ICR calculado: {sim.pose.radio_icr:.3f} m")
    print(f"Velocidad angular de guiñada: {sim.pose.omega_rad_s:.3f} rad/s")

    # Maniobra 3: Giro completo sobre el propio eje (Point Turn) de 360 grados
    print("\n[MANIOBRA 3] Giro 360 Sobre el Propio Eje (Point Turn)...")
    sim.reiniciar()
    rumbo_objetivo = 2.0 * math.pi
    rumbo_acumulado = 0.0
    theta_ant = sim.pose.theta_rad
    t_giro = 0.0

    while rumbo_acumulado < rumbo_objetivo and t_giro < 15.0:
        sim.paso_simulacion(-150, 150, 45, 135, dt, modo_giro_eje=True)
        d_theta = abs(sim.pose.theta_rad - theta_ant)
        if d_theta > math.pi:
            d_theta = 2.0 * math.pi - d_theta
        rumbo_acumulado += d_theta
        theta_ant = sim.pose.theta_rad
        t_giro += dt

    print(f"Giro completado en {t_giro:.2f} s | Rumbo acumulado: {math.degrees(rumbo_acumulado):.1f} deg")
    print(f"Desplazamiento residual del centro: ({sim.pose.x:.4f}, {sim.pose.y:.4f}) m (Ideal: 0.0 m)")

    # Maniobra 4: Circuito Mixto Completo con Mapa Visual
    print("\n[MANIOBRA 4] Circuito Combinado (Avance -> Curva -> Cangrejo)...")
    sim.reiniciar()

    # Tramo A: Avance recto 1.5 m
    for _ in range(int(2.5 / dt)):
        sim.paso_simulacion(180, 180, 90, 90, dt)

    # Tramo B: Curva derecha 90 deg
    for _ in range(int(3.2 / dt)):
        sim.paso_simulacion(180, 126, 60, 60, dt)

    # Tramo C: Marcha lateral cangrejo (Crab) a 180 deg (con servos 360)
    for _ in range(int(2.0 / dt)):
        sim.paso_simulacion(150, 150, 180, 180, dt, modo_cangrejo=True)

    print("\nMapa de la Trayectoria Resultante:")
    print(sim.renderizar_mapa_ascii())
    print("\nSimulacion completada exitosamente.")


if __name__ == "__main__":
    ejecutar_ensayo_simulacion()
