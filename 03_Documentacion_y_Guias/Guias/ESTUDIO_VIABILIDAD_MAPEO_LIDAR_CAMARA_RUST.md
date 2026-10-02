# ESTUDIO DE VIABILIDAD TECNICA Y COSTOS: MAPEO 3D, LIDAR, CAMARAS Y RUST
## Proyecto: Rover Lunar V2.0 — Exploracion de Tubos de Lava y Entornos Confinados

---

## 1. Contexto Operativo del Problema

El Rover Lunar V2.0 tiene como mision la exploracion de terrenos irregulares y ambientes confinados análogos (tubos de lava lunares y galerias subterraneas). Estos entornos presentan desafios fisicos criticos:
1. **Ausencia total de luz solar natural:** Las cuevas carecen de iluminacion ambiental, inhabilitando camaras opticas pasivas convencionales a menos que se incorpore un sistema activo de iluminacion artificial.
2. **Ambiente sin GPS:** La navegacion y localizacion deben ser estimadas puramente mediante odometria (inercial + encoders de ruedas) y tecnicas SLAM (Simultaneous Localization and Mapping).
3. **Restriccion severa de ancho de banda y masa:** El enlace de radiofrecuencia (2.508 GHz / NRF24L01 a 250 kbps) no soporta transmision masiva de video continuo ni nubes de puntos de alta densidad. El video y los datos masivos de escaneo requieren enlace Wi-Fi local o procesamiento previo a bordo.

---

## 2. Analisis de Sensores de Mapeo y Estimacion de Costos

### Opcion A: Camaras Opticas (Arducam / ESP32-CAM / USB)
* **ESP32-CAM (OV2640):**
  - **Costo:** USD 8 a USD 15.
  - **Ventajas:** Extremadamente economica, comunicacion Wi-Fi nativa integrada, bajo consumo (~180 mA a 5V).
  - **Limitaciones:** Resolucion practica fluida baja (SVGA 800x600 a 15-20 FPS), lente sin sensibilidad infrarroja (requiere iluminacion LED obligatoria), no genera informacion de profundidad tridimensional de forma directa.
* **Arducam para Microcontroladores (OV5642 / Global Shutter / ToF):**
  - **Costo:** USD 25 a USD 65 segun modelo.
  - **Ventajas:** Búfer de memoria FIFO integrado, conexion SPI/I2C, mejor optica y opciones sin filtro IR (NoIR).
  - **Limitaciones:** Enlace SPI con microcontrolador limita el framerate a 5-10 FPS en resoluciones medias.
* **Camaras de Profundidad Estereoscopicas (Intel RealSense D435i / Luxonis OAK-D Lite):**
  - **Costo:** USD 149 (OAK-D Lite) a USD 350-450 (RealSense D435i).
  - **Ventajas:** Generan mapas de profundidad RGB-D directos en 3D y nubes de puntos densas con acelerador VPU integrado.
  - **Limitaciones:** Requieren una computadora a bordo tipo Raspberry Pi 4/5 o Jetson Nano conectada por USB 3.0 (no pueden ser procesadas directamente por un microcontrolador ESP32).

---

### Opcion B: Modulos LiDAR 2D (Triangulacion / DToF 360°)
* **LDROBOT LD06 / D300 (LiDAR DToF 360°):**
  - **Costo:** USD 60 a USD 85.
  - **Rango:** 0.12 m a 12 m. Frecuencia de muestreo: 4500 Hz.
  - **Ventajas:** Muy compacto, bajo peso (42 g), alta resistencia a interferencias por tecnologia Direct Time-of-Flight (DToF), salida serie UART sencilla a 230400 bps.
* **Slamtec RPLiDAR A1M8:**
  - **Costo:** USD 85 a USD 115.
  - **Rango:** 0.15 m a 12 m. Frecuencia: 2000 a 8000 Hz.
  - **Ventajas:** Estandar de la industria academica para SLAM 2D, soporte masivo de bibliotecas y ROS.
  - **Limitaciones de LiDAR 2D:** Escanea solo un plano horizontal estatico. En una cueva irregular, un obstaculo por encima o por debajo del haz laser (estalactitas, pozos) pasa desapercibido.

---

### Opcion C: Sistema Hibrido 3D de Bajo Costo (LiDAR 2D sobre Servomotor de Cabeceo / Tilt)
* **Arquitectura:** Un sensor LiDAR 2D (ej. LD06) montado sobre un eje oscilante comandado por un servomotor de alta precision (barrido de -45° a +45° en pitch).
* **Costo estimado total:** USD 90 a USD 130 (LiDAR USD 75 + Servomotor metalico MG996R USD 10 + soporte estructural 3D).
* **Viabilidad:** Excelente y probada historicamente en misiones de exploracion planetaria. Al rotar el plano 2D respecto del eje horizontal, el sistema acumula sucesivos cortes angulares reconstruyendo una nube de puntos tridimensional (3D Point Cloud) completa del entorno de la cueva.

---

### Opcion D: LiDAR 3D Industrial de Estado Solido (ej. Livox Mid-360)
* **Costo:** USD 600 a USD 900.
* **Ventajas:** Nube de puntos tridimensional nativa de altisima densidad (200.000 pts/seg) y 360° x 59° de apertura.
* **Limitaciones:** Excede el presupuesto academico actual y requiere conexion Ethernet y procesamiento en computadora de abordo de alta gama.

---

## 3. ¿Hacerlo en Rust Mejoraria Algo?

### 3.1. Rendimiento y Concurrencia en Mapeo 3D
1. **Ausencia de GIL (Global Interpreter Lock):** En Python, procesar 5.000 a 50.000 puntos laser por segundo en tiempo real satura el hilo principal de la GUI, provocando congelamientos perceptibles salvo que se recurra a bibliotecas C/C++ externas complejas. En Rust, la biblioteca estandar y crates de concurrencia como `rayon` permiten paralelizar el filtrado de nubes (downsampling por voxel grid, eliminacion de ruido estadistico) en multiples hilos sin sobrecarga de sincronizacion.
2. **Gestion de Memoria y Latencia Determinista:** En sistemas de navegacion en tiempo real dentro de cuevas, las pausas inducidas por el recolector de basura (Garbage Collector) de Python o Java pueden provocar perdida de muestras criticas. Rust ofrece tiempo de ejecucion determinista y consumo de memoria estricto (cero copia con slices y buffers circulares).
3. **Graficado 3D Nativo Acelerado por GPU:**
   - En Python, herramientas como Matplotlib 3D colapsan con mas de 2.000 puntos; Open3D o PyVista requieren dependencias pesadas y wrappers C++.
   - En Rust, el ecosistema grafico moderno (`wgpu`, `three-d`, `rerun`, o `egui_glow` / OpenGL nativo) permite renderizar millones de puntos 3D a 60 FPS estables consumiendo directamente la VRAM de la placa grafica sin mediacion de capas intermedias.

---

## 4. Comparativa de Costos y Viabilidad por Estrategia

| Estrategia | Componentes Requeridos | Costo Estimado (USD) | Viabilidad en Microcontrolador | Nube de Puntos 3D |
|---|---|---|---|---|
| **Estrategia 1 (Economica)** | ESP32-CAM + Foco LED auxiliar blanco | USD 15 - USD 25 | Inmediata (a bordo) | No (Solo streaming 2D) |
| **Estrategia 2 (Recomendada V2.5)** | LiDAR LD06 + Servo Tilt + Iluminacion | USD 90 - USD 130 | Alta (UART a ESP32 o PC) | Si (Nube 3D densa por barrido) |
| **Estrategia 3 (Stereo Vision)** | Luxonis OAK-D Lite + SBC (Raspberry Pi) | USD 250 - USD 320 | Media (Requiere SBC a bordo) | Si (RGB-D nativo) |
| **Estrategia 4 (Industrial)** | Livox Mid-360 + Jetson Orin Nano | USD 1200 - USD 1600 | Baja por costo actual | Si (Precision milimetrica) |

---

## 5. Hoja de Ruta Sugerida para el Proyecto Rover Lunar

1. **Fase Inmediata (Actual V2.0):** Consolidar la traccion Rocker-Bogie 6x6, el control de 4 servos de direccion (4WS) y la telemetria robusta por radiofrecuencia (Arduino Nano ESP32 con paquetes packed de 6 bytes).
2. **Fase Proxima (V2.5 - Mapeo Confina):**
   - Incorporar sensor LiDAR DToF (LD06 o RPLiDAR A1) montado sobre servomotor de inclinacion de 90°.
   - Conectar la salida UART del LiDAR a la PC o puente serial.
   - En la aplicacion Rust (`hmi-gui`), procesar las coordenadas esfericas (distancia `r`, angulo azimutal `theta`, angulo de cabeceo del servo `phi`) y proyectarlas a coordenadas cartesianas `(X, Y, Z)` para graficar la nube de puntos 3D de la cueva en tiempo real.
3. **Fase Avanzada (V3.0):** Integrar sensor IMU de 9 ejes (BNO085) para fusion sensorial (filtro de Kalman extendido) y compensar las inclinaciones del chasis en terrenos abruptos sobre el mapa 3D resultante.
