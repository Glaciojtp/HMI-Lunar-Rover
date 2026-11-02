# PLAN DE MEJORAS TECNICAS, ARQUITECTURA LIDAR Y HOJA DE RUTA
## Proyecto: Rover Lunar V2.5 / V3.0 — Exploracion de Entornos Confinados y Tubos de Lava

> **DOCUMENTO TECNICO DE PLANIFICACION Y DISENO DE SISTEMAS**  
> Este documento consolida el analisis cinematico del chasis Rocker-Bogie, el catalogo de mejoras tecnicas mecanicas, electronicas y de control, la arquitectura completa de integracion del sensor LiDAR 3D para mapeo en cuevas y la distribucion operativa de tareas para el equipo de trabajo.

---

## 1. Resumen Ejecutivo y Objetivos de Evolucion

El Rover Lunar ha superado la fase de prototipado preliminar (**V2.0**), contando actualmente con traccion 6x6 funcional, direccion en las 4 esquinas (4WS), comunicacion por radiofrecuencia a 2.508 GHz y estacion terrena dual en Python y Rust.

Para avanzar hacia las fases **V2.5** (banco de pruebas y mapeo activo) y **V3.0** (navegacion autonoma en entornos confinados), el vehiculo debe superar tres limitaciones clave identificadas en pruebas de laboratorio:
1. **Traccion en lazo abierto:** Discrepancias de velocidad entre motores que inducen desvio de trayectoria y arrastre parásito.
2. **Arrastre lateral de ruedas intermedias (Scrubbing):** En giros cerrados (Point Turn) y traslaciones diagonales (Crab), las ruedas fijas del eje medio frenan el vehiculo y sobrecargan la mecanica.
3. **Carencia de percepcion tridimensional:** Para ingresar a tubos de lava lunares o galerias mineras subterráneas sin luz, el rover requiere un sistema activo de reconstruccion de mapas tridimensionales independiente de iluminacion ambiental.

---

## 2. Analisis Cinematico: Modos de Conduccion vs. Chasis Rocker-Bogie

La suspension **Rocker-Bogie** es un mecanismo pasivo articulado de 6 ruedas disenado para absorcion de desniveles sin resortes:
* Dos balancines principales (**Rockers**) en los laterales, unidos en el techo mediante una **barra diferencial** que acopla sus movimientos de cabeceo ($\theta_{\text{izq}} = -\theta_{\text{der}}$).
* Dos sub-balancines (**Bogies**) en la parte posterior, que articulan la rueda intermedia y la rueda trasera de cada lateral.
* Las 4 ruedas de las esquinas poseen servomotores de direccion independiente ($S_1, S_2, S_3, S_4$).
* Las 2 ruedas intermedias ($M_2, M_5$) estan rígidamente fijadas a $90^\circ$ sobre el eje longitudinal de los bogies.

```
                             [ Barra Diferencial ]
                                   /       \
                        Rocker Izq.         Rocker Der.
                         /       \           /       \
                   S1 (FL)     Pivote      S2 (FR)    Pivote
                                  |                      |
                                Bogie                  Bogie
                                /   \                  /   \
                             M2 (ML) S3 (RL)        M5 (MR) S4 (RR)
```

### 2.1. Modo Avance y Retroceso Rectilineo
* **Comportamiento:** Las 4 ruedas directrices se alinean a $90^\circ$ ($\delta = 0\text{ rad}$). Todas las ruedas traccionan en el mismo sentido.
* **Respuesta de la suspension:** El mecanismo ecualiza las fuerzas normales contra el suelo. Al superar un obstaculo con la rueda delantera, el balancin oscila y el diferencial transfiere par descendente al lado opuesto, impidiendo que el chasis vuelque.
* **Punto de atencion:** Pequeñas diferencias en las RPM de los motores generan pares de guiñada parásitos. Se requiere trimado individual o lazo cerrado con encoders.

### 2.2. Modo Curva Coordinada Ackermann 4WS Simetrica
* **Geometria obligatoria:** Dado que las ruedas intermedias $M_2$ y $M_5$ son fijas a $90^\circ$, el Centro Instantaneo de Rotacion (ICR) debe ubicarse estrictamente sobre la prolongacion del eje transversal medio ($y = 0$).
* **Direccion simetrica:** Para un radio de giro $R_{\text{ICR}}$, los servos delanteros giran $\delta_f$ y los traseros giran $-\delta_f$:
  $$\delta_{\text{delantero}} = \arctan\left(\frac{l}{R_{\text{ICR}}}\right), \quad \delta_{\text{trasero}} = -\delta_{\text{delantero}}$$
* **Respuesta de la suspension:** Optima. Los sub-balancines bogie no sufren momentos torsores laterales, desplazandose de forma puramente tangencial. Las ruedas interiores recorren arcos de menor longitud, requiriendo reduccion diferencial de potencia PWM (slider master diferencial o trims) para eliminar deslizamiento.

### 2.3. Modo Giro Sobre el Propio Eje (Point Turn / Rotacion 360°)
* **Geometria:** Los servos se orientan tangentes al circulo ($S_1=45^\circ, S_2=135^\circ, S_3=135^\circ, S_4=45^\circ$), el ICR se situa en el centroide $(0, 0)$, y los laterales giran en sentido contrario ($+v$ y $-v$).
* **Conflicto mecanico (Scrubbing):** Las ruedas intermedias $M_2$ y $M_5$ estan perpendiculares a la tangente de giro. Por tanto, sufren un arrastre lateral forzado del 100%.
* **Efectos observados:**
  * En suelo blando (arena, regolito): Tienden a excavar pozos laterales, atrapando el vehiculo.
  * En suelo de alta friccion: Generan picos de corriente que recalientan los puentes H y pueden desgastar las cajas reductoras plasticas.
* **Estrategia correctiva:** Modular por firmware la potencia de $M_2$ y $M_5$ al 25%-30% del valor de las esquinas o activar micropulsos de avance/retroceso para asistir el giro sin bloquear lateralmente.

### 2.4. Modo Cangrejo (Crab Steer)
* **Geometria:** Las 4 ruedas esquineras se orientan paralelas al mismo angulo (ej. $45^\circ$ en servos estandar, o $180^\circ$ en servos de 360° para traslacion lateral pura a $90^\circ$).
* **Conflicto mecanico:** Si las ruedas intermedias continuan traccionando hacia adelante mientras el vehiculo se desplaza en diagonal o de lado, actuan como un freno mecanico severo.
* **Estrategia correctiva:** En modo Cangrejo, el firmware debe apagar por completo los motores intermedios ($M_2 = 0, M_5 = 0$), dejando que actuen como ruedas locas sin oponer resistencia motriz frontal.

---

## 3. Catalogo de Mejoras Tecnicas Propuestas

```
[ ARBOL DE MEJORAS DEL ROVER LUNAR ]
│
├── 1. Traccion y Control
│   ├── M1.1: Desacople por firmware de M2 y M5 en Point Turn y Cangrejo (Inmediata)
│   ├── M1.2: Encoders magneticos de efecto Hall en los 6 motores DC (Corto Plazo)
│   ├── M1.3: Reemplazo de drivers L9110S por MOSFETs TB6612FNG o DRV8833 (Corto Plazo)
│   └── M1.4: Algoritmo PID de sincronizacion de velocidad en Nano ESP32 (Mediano Plazo)
│
├── 2. Sensado Estructural y Odometria
│   ├── M2.1: Sensor angular absoluto AS5600 en pivote diferencial (Mediano Plazo)
│   ├── M2.2: IMU de 9 ejes BNO085 para estimacion de actitud y cabeceo (Mediano Plazo)
│   └── M2.3: Odometria fusionada (Filtro de Kalman Extendido EKF) en Rust (Largo Plazo)
│
├── 3. Chasis y Absorcion Mecanica
│   ├── M3.1: Ruedas conformables elasticas impresas en filamento TPU 95A (Corto Plazo)
│   └── M3.2: Ejes de acero rectificado en pivotes de bogies con bujes de bronce (Mediano Plazo)
│
└── 4. Percepcion y Mapeo
    ├── M4.1: Mastil elevado para sensor LiDAR 2D DToF (LDROBOT LD06) (Corto Plazo)
    ├── M4.2: Mecanismo de cabeceo (Pitch-Tilt) con servomotor de precision (Corto Plazo)
    └── M4.3: Renderizado 3D de nubes de puntos acelerado por GPU en hmi-gui (Corto Plazo)
```

### 3.1. Traccion y Control

#### Mejora M1.1: Desacople Dinamico de Motores Intermedios (Inmediata por Firmware)
* **Objetivo:** Eliminar el bloqueo cinematico en giros sobre el eje y marchas cangrejo.
* **Implementacion:** Actualizar las rutinas de consigna en el receptor Arduino Nano ESP32 y en la funcion `calcular_cinematica`:
  * Si `ModoConduccion == PointTurn`: fijar $PWM_{M2} = PWM_{izq} \times 0.3$, $PWM_{M5} = PWM_{der} \times 0.3$.
  * Si `ModoConduccion == Crab`: forzar $PWM_{M2} = 0$ y $PWM_{M5} = 0$.

#### Mejora M1.2: Encoders Magneticos de Efecto Hall (Corto Plazo)
* **Objetivo:** Pasar de control en lazo abierto (tension PWM estimativa) a lazo cerrado de velocidad.
* **Componente:** Micromotores DC con caja reductora metalica 1:50 o 1:100 y disco magnetico trasero con sensor Hall de doble canal (cuadratura, 12 pulsos por vuelta de motor, ~600 pulsos por vuelta de rueda).
* **Beneficio:** Garantiza velocidad de avance identica en las 6 ruedas, eliminando el desvio de trayectoria sin necesidad de calibracion manual constante de trims.

#### Mejora M1.3: Drivers de Potencia MOSFET (Corto Plazo)
* **Objetivo:** Eliminar caidas de tension y sobrecalentamiento de los L9110S.
* **Componente:** Modulos basados en TB6612FNG o DRV8833 con transistores MOSFET integrados (resistencia interna $R_{DS(on)} < 0.2\,\Omega$ frente a la caida de $\approx 1.2\,\text{V}$ del puente bipolar actual). Proporciona mayor torque a igualdad de bateria y menor disipacion termica.

---

### 3.2. Sensado Estructural y Odometria

#### Mejora M2.1: Sensor de Inclinacion en el Balancin Diferencial
* **Objetivo:** Monitorizar en tiempo real el cruce de obstaculos y detectar riesgo de vuelco.
* **Componente:** Encoder magnetico sin contacto AS5600 (resolucion 12 bits, interfaz I2C) montado coaxialmente con el perno central del diferencial superior.
* **Funcion:** Mide el angulo relativo $\alpha_{\text{diff}}$ entre el rocker izquierdo y el derecho. Permite activar alarmas de desnivel critico ($>25^\circ$) en la pantalla del operador.

#### Mejora M2.2: Unidad de Medicion Inercial (IMU) de 9 Ejes
* **Objetivo:** Proveer rumbo magnetico, balanceo (*roll*) y cabeceo (*pitch*) del chasis central.
* **Componente:** Sensor BNO085 o MPU9250 conectado por bus I2C al microcontrolador a bordo.
* **Funcion:** Corrige la orientacion espacial de los puntos medidos por el LiDAR cuando el vehiculo transita sobre piedras o pendientes.

---

### 3.3. Chasis y Absorcion Mecanica

#### Mejora M3.1: Ruedas Conformables Impresas en TPU 95A
* **Objetivo:** Reducir vibraciones destructivas sobre sensores laser y camaras.
* **Diseno:** Llantas sin aire (*airless*) con radios curvos deformables inspiradas en las ruedas de los rovers Curiosity y Perseverance. Al impactar una roca, la banda de rodadura se amolda al obstaculo aumentando la superficie de traccion y absorbiendo la aceleracion vertical sin recurrir a resortes.

---

## 4. Arquitectura del Subsistema LiDAR para Mapeo en Cuevas

Para reconstruir nubes de puntos 3D en tubos de lava y minas subterraneas sin iluminacion, se adopta un **sistema hibrido de escaneo tridimensional**: un sensor LiDAR 2D planar montado sobre un soporte oscilante comandado por servomotor (Pitch-Tilt).

```
                         [ Mastil LiDAR 3D ]
                        (Elevacion +110 mm)
                                 |
                          [ Servo Tilt ]
                                 |
                               [===] <--- Sensor LD06 (Azimut 360°)
                              /  |  \
                             /   |   \  Cono de haz libre (+60° / -30°)
                            v    |    v
                    +------------+------------+
                    |    Cuerpo Central      |  <-- Chasis Principal
                    |  (Baterias / Electron) |
                    +-------------------------+
                      o                     o
                   Rueda FL              Rueda FR
```

### 4.1. Seleccion de Hardware
* **Sensor Principal:** **LDROBOT LD06** (o Slamtec RPLiDAR A1).
  * **Tecnologia:** DToF (Direct Time-of-Flight) a 905 nm.
  * **Alcance:** $0.12\text{ m}$ a $12.0\text{ m}$.
  * **Frecuencia de muestreo:** $4500\text{ mediciones/segundo}$.
  * **Frecuencia de giro azimutal:** $10\text{ Hz}$ ($360^\circ$ en 100 ms).
  * **Peso y consumo:** $42\text{ g}$, $5\text{ V}$ a $180\text{ mA}$.
  * **Comunicacion:** UART serie a $230400\text{ bps}$.
* **Actuador de Inclinacion (Pitch):** Servomotor digital con piñoneria metalica (MG996R o RDS3116) controlado con micropasos de alta resolucion.

### 4.2. Posicionamiento Fisico en el Chasis
* **Ubicacion:** Mástil frontal superior en el eje longitudinal ($X = 0$, $Y = +120\text{ mm}$ respecto al centroide geometrico del chasis).
* **Cota de altura:** **$+110\text{ mm}$ sobre la placa superior del chasis**.
* **Justificacion geometrica:** Con una elevacion de 110 mm, cuando el servomotor inclina el sensor hacia abajo en su cota minima de $-30^\circ$, el plano inferior del haz laser pasa a $25\text{ mm}$ por encima de los guardabarros de las ruedas delanteras $S_1$ y $S_2$, eliminando zonas ciegas a corta distancia sin ocluir el piso inmediatamente frontal.

### 4.3. Modelo Matematico de Transformacion de Coordenadas
Para cada punto medido por el LiDAR con distancia $r$ y angulo azimutal $\theta \in [0^\circ, 360^\circ)$, conociendo el angulo instantaneo de cabeceo del servo $\phi \in [-30^\circ, +60^\circ]$:

```
                                      Z (Altura)
                                      ^
                                      |      * Punto medido P(X, Y, Z)
                                      |     /|
                                      | r  / |
                                      |   /  |
                                      |  /   |
                                      | /phi |
                         (0,0,0) LiDAR+------+-------> Y (Frente)
                                     /
                                    / theta
                                   v
                                  X (Derecha)
```

1. **Coordenadas locales relativas al sensor LiDAR:**
   $$X_{\text{local}} = r \cdot \cos(\phi) \cdot \sin(\theta)$$
   $$Y_{\text{local}} = r \cdot \cos(\phi) \cdot \cos(\theta)$$
   $$Z_{\text{local}} = r \cdot \sin(\phi)$$

2. **Transformacion al marco inercial del mapa (Mundo):**
   Considerando la pose instantanea del rover $(X_r, Y_r, Z_r)$, el rumbo $\theta_{\text{yaw}}$ y la altura del mastil $h_{\text{mastil}}$:
   $$\begin{bmatrix} X_{\text{mundo}} \\ Y_{\text{mundo}} \\ Z_{\text{mundo}} \end{bmatrix} = \begin{bmatrix} \cos(\theta_{\text{yaw}}) & \sin(\theta_{\text{yaw}}) & 0 \\ -\sin(\theta_{\text{yaw}}) & \cos(\theta_{\text{yaw}}) & 0 \\ 0 & 0 & 1 \end{bmatrix} \begin{bmatrix} X_{\text{local}} \\ Y_{\text{local}} \\ Z_{\text{local}} \end{bmatrix} + \begin{bmatrix} X_r \\ Y_r \\ Z_r + h_{\text{mastil}} \end{bmatrix}$$

### 4.4. Pipeline de Procesamiento y Visualizacion en Rust (`hmi-gui`)
* **Hilo Serial Asincrono:** Recepcion del flujo UART del LiDAR en un hilo de sistema operativo desacoplado de la GUI mediante canales `mpsc`.
* **Filtro Voxel Grid:** Discretizacion del espacio en celdas cubicas de $5\text{ cm} \times 5\text{ cm} \times 5\text{ cm}$. Los puntos que caen dentro de la misma celda se promedian, reduciendo el uso de memoria en un 70% sin perder resolucion de paredes ni obstaculos.
* **Renderizado por GPU:** Dibujado de los vertices tridimensionales en un viewport OpenGL (`egui_glow` o `wgpu`) con mapa de color segun altura $Z$ (suelo: azul, obstaculos: amarillo/verde, techo: rojo).
* **Exportacion:** Boton en interfaz para descargar la nube completa en formato `.PCD` o `.PLY` compatible con herramientas profesionales de inspeccion geologica.

---

## 5. Presupuesto Estimado y Desglose de Componentes

| Item | Componente | Cantidad | Costo Unitario Estimado (USD) | Total (USD) | Estado / Proveedor |
|---|---|---|---|---|---|
| 1 | Sensor LiDAR 2D DToF LDROBOT LD06 | 1 | $75.00 | $75.00 | Por adquirir (AliExpress / RobotShop) |
| 2 | Servomotor Digital Metalico MG996R / RDS3116 | 1 | $12.00 | $12.00 | Stock de laboratorio |
| 3 | Mástil y articulacion impresos en PETG/ABS | 1 | $5.00 | $5.00 | Fabricacion propia 3D |
| 4 | Microcontrolador Arduino Nano ESP32 (Oficial) | 2 | $22.00 | $44.00 | En uso operativo (TX + RX) |
| 5 | Modulos de radio NRF24L01 + Antena SMA | 2 | $4.50 | $9.00 | En uso operativo |
| 6 | Drivers MOSFET TB6612FNG (Reemplazo L9110S) | 3 | $3.50 | $10.50 | Recomendado adquirir |
| 7 | Filamento TPU 95A para ruedas conformables (1 kg) | 1 | $24.00 | $24.00 | Recomendado adquirir |
| 8 | Regulador Step-Down Buck 5A (alimentacion servos) | 1 | $6.00 | $6.00 | En uso operativo |
| **TOTAL** | **Inversion Estimada Fase V2.5** | — | — | **$185.50** | — |

---

## 6. Distribucion Operativa de Tareas para el Equipo

Para ejecutar ordenadamente esta hoja de ruta, se establecen las siguientes responsabilidades tecnicas:

* **Joaquin:**
  * Calibracion del enlace UART a 230400 bps entre el LiDAR y la estacion receptora.
  * Validacion de latencia del puente RF24 y pruebas de sincronizacion temporal con el servomotor de cabeceo.
* **Lucas:**
  * Integracion en el diseno esquematico y PCB de produccion de las pistas de alimentacion dedicada para los drivers MOSFET y el puerto serie del LiDAR.
  * Eliminacion de cableado tipo protoboard para minimizar caidas de tension en los motores.
* **Lucio y Sebastian:**
  * Diseno CAD y fabricacion del mastil elevado (+110 mm) con soporte oscilante para el sensor LD06.
  * Modelado e impresion 3D de las ruedas conformables de radios curvos en filamento TPU 95A.
* **Emir:**
  * Actualizacion del firmware en Arduino Nano ESP32 para incluir el generador de pulso PWM del servo de pitch y desacople de $M_2/M_5$ en modo Cangrejo.
  * Mantenimiento de la trama binaria de telemetria y recepcion de datos de IMU.
* **Benjamin:**
  * Ensayos de superacion de obstaculos y medicion del angulo del balancin diferencial en la rampa a 20° y suelo irregular en piso de pruebas CEPIT.
  * Determinacion experimental de las zonas ciegas del LiDAR segun diferentes angulos de cabeceo.
* **Keila y Ainsworth:**
  * Ensayos comparativos de rodadura y traccion entre ruedas rigidas y ruedas conformables de TPU.
  * Redaccion del informe tecnico de inspeccion ambiental y mapeo de conductos subterraneos aplicado a explotaciones mineras e investigacion espacial análoga.
