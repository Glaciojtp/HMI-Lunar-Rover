# GUÍA Y CONTEXTO TÉCNICO DEL PROYECTO: ROVER LUNAR V2.0

> **DOCUMENTO PARA AGENTES DE INTELIGENCIA ARTIFICIAL Y DESARROLLADORES**  
> Este documento consolida todo el estado de conservación técnico, arquitectura de hardware, conexionado de pines, protocolo de comunicación y directrices de desarrollo para el proyecto **Rover Lunar V2.0**. Cualquier agente o desarrollador que intervenga en el repositorio debe seguir rigurosamente las especificaciones aquí descritas.

---

## 1. Propósito del Proyecto y Visión General

El objetivo primordial es el diseño, construcción y validación de una plataforma robótica de exploración móvil (**Rover Lunar V2.0**) equipada con un sistema de suspensión mecánica tipo **Rocker-Bogie**.

* **Misión Principal:** Sortear obstáculos pronunciados y pendientes críticas en entornos análogos simulados (ej. tubos de lava lunar y regolito simulado).
* **Aplicaciones Industriales Terrestres Paralelas:** Inspección en espacios confinados y detección ambiental / monitoreo de gases en túneles y explotaciones mineras subterráneas.

---

## 2. Organización del Equipo y Distribución de Tareas

* **Joaquín:** Logro, calibración y validación de la comunicación inalámbrica por RF estable entre ambos microcontroladores.
* **Lucas:** Diseño esquemático y ruteado de la placa PCB de montaje final para la electrónica de a bordo.
* **Lucio y Sebastián:** Diseño, corrección y ensamble de los mecanismos físicos de tracción (motores amarillos DC con caja reductora) y dirección.
* **Sebastián:** Adquisición de módulos de radiofrecuencia NRF24L01 y componentes de hardware.
* **Emir:** Desarrollo y mantenimiento de los códigos de control del emisor, receptor y subsistema de cámara ESP32-CAM.
* **Benjamín:** Mapeo y caracterización de zonas físicas de prueba (piso de pruebas CEPIT, rampa a 20°, terreno natural de Sierra) y misiones análogas de regolito lunar.
* **Keila y Ainsworth:** Investigación física de la rodadura de ruedas, tracción y redacción del informe de aplicaciones industriales terrestres.

---

## 3. Reglas Críticas de Hardware y Seguridad (Lecciones Aprendidas)

Cualquier intervención física o de software debe respetar las siguientes reglas obligatorias, originadas a partir de incidentes previos de laboratorio:

> [!CAUTION]
> **1. ALIMENTACIÓN DEL NRF24L01: NUNCA CONECTAR A 5V**  
> El módulo NRF24L01 tolera 5V en sus pines lógicos SPI, pero **su línea VCC debe ser estrictamente alimentada con 3.3V**. Conectar VCC a 5V destruye la radio de inmediato.

> [!IMPORTANT]
> **2. CAPACITOR OBLIGATORIO EN LA RADIO**  
> Es imprescindible soldar un capacitor electrolítico de entre **10 µF y 100 µF** directamente entre los pines **VCC** y **GND** del NRF24L01. Sin este capacitor, los picos transitorios de consumo durante la transmisión provocan caídas de tensión y pérdidas masivas de tramas.

> [!WARNING]
> **3. REGULACIÓN PARA SERVOMOTORES (PROHIBIDO LM7805)**  
> En las primeras pruebas se quemó un servomotor SG90 al recibir 8V directos de batería, y los reguladores lineales tipo 7805 disipan un calor inaceptable bajo carga.  
> Se debe utilizar **exclusivamente un regulador conmutado Step-Down (Buck)** ajustado a **5V - 6V** para alimentar los servos de dirección de manera aislada, compartiendo la tierra (GND común) con el microcontrolador.

> [!IMPORTANT]
> **4. LÍMITES DE ÁNGULO POR SOFTWARE (10° A 170°)**  
> Para evitar trabas mecánicas, sobrecalentamiento y rotura de engranajes por esfuerzos de corte en los servos, **ningún comando de software puede solicitar ángulos fuera del rango seguro [10°, 170°]**.

---

## 4. Arquitectura de Conexión de Hardware (Pinout Fijo)

### 4.1. Transmisor: ESP32-C3 SuperMini / LOLIN C3 Mini (Puente Serial-RF)
Conectado a la PC por USB, recibe comandos por puerto serie y los transmite por RF24:

| Pin NRF24L01 | Pin ESP32-C3 | Descripción / Detalle de Conexión |
|---|---|---|
| **VCC** | **3.3V** | Alimentación regulada (¡Nunca 5V!). Con capacitor electrolítico (10–100µF) a GND |
| **GND** | **GND** | Tierra común |
| **CE** | **GPIO 4** | Control de habilitación de radio |
| **CSN** | **GPIO 7** | Chip Select (SS) |
| **SCK** | **GPIO 6** | Reloj SPI de hardware |
| **MOSI** | **GPIO 3** | Transmisión de datos SPI |
| **MISO** | **GPIO 5** | Recepción de datos SPI |

---

### 4.2. Receptor: Arduino MKR 1310 (Electrónica a Bordo del Rover)
Montado en el chasis del rover, recibe las tramas RF y controla actuadores y motores:

| Componente Físico | Pin del Módulo | Pin del Arduino MKR 1310 | Función / Observación |
|---|---|---|---|
| **NRF24L01** | VCC | **3.3V** | Salida 3.3V regulada del MKR (con capacitor 10–100µF a GND) |
| **NRF24L01** | GND | **GND** | Tierra común del sistema |
| **NRF24L01** | CE | **Pin Digital 0** | Habilitación de radio (Reubicado desde pin 4 para liberar PWM) |
| **NRF24L01** | CSN | **Pin Digital 1** | Chip Select (Reubicado desde pin 5 para liberar PWM) |
| **NRF24L01** | MOSI | **Pin Digital 8** | Bus SPI Hardware |
| **NRF24L01** | SCK | **Pin Digital 9** | Bus SPI Hardware |
| **NRF24L01** | MISO | **Pin Digital 10** | Bus SPI Hardware |
| **Puente H L9110S** | A1A | **Pin Digital 2** | Motor Izquierdo - Señal de Avance (PWM) |
| **Puente H L9110S** | A1B | **Pin Digital 5** | Motor Izquierdo - Señal de Reversa (PWM) *(¡Atención cableado!)* |
| **Puente H L9110S** | B1A | **Pin Digital 3** | Motor Derecho - Señal de Avance (PWM) |
| **Puente H L9110S** | B1B | **Pin Digital 4** | Motor Derecho - Señal de Reversa (PWM) |
| **Servomotor S1** | PWM | **Pin Digital 6** | Señal de control de dirección 1 |
| **Servomotor S2** | PWM | **Pin Digital 7** | Señal de control de dirección 2 |
| **Regulador Step-Down**| Salida 5V | Alimentación Servos | Alimenta VCC de S1 y S2 de forma aislada de la lógica |

> [!NOTE]
> **Detalle crítico del Puente H L9110S:** Para lograr el sentido de rotación correcto, `A1B` debe conectarse físicamente al Pin 5 del MKR y `A1A` al Pin 2. En pruebas preliminares se descubrió que invertirlos bloqueaba la respuesta del motor. Además, reasignar la radio a los pines 0 y 1 fue obligatorio para liberar los pines 2, 3, 4 y 5 con capacidad PWM para el control bidireccional de ambos motores.

---

### 4.3. Receptor Migrado: Arduino Nano ESP32 (Arquitectura Rocker-Bogie 6x6 + 4WS)
Alternativa oficial al MKR 1310. Trabaja a **3.3V nativo** (ESP32-S3) con PWM por hardware en todos sus pines y deja libres pines analógicos y el bus I2C para telemetría:

| Componente Físico | Pin del Módulo | Pin Arduino Nano ESP32 | Función / Observación |
|---|---|---|---|
| **NRF24L01** | VCC | **3.3V** | Alimentación lógica regulada (¡Nunca 5V!). Con capacitor 10–100µF |
| **NRF24L01** | GND | **GND** | Tierra común |
| **NRF24L01** | CE | **Pin D9** | Chip Enable (GPIO 18) |
| **NRF24L01** | CSN | **Pin D10** | Chip Select SPI (GPIO 21) |
| **NRF24L01** | MOSI | **Pin D11** | Bus SPI Hardware (GPIO 38) |
| **NRF24L01** | MISO | **Pin D12** | Bus SPI Hardware (GPIO 47) |
| **NRF24L01** | SCK | **Pin D13** | Bus SPI Hardware (GPIO 48) |
| **Puente H L9110S** | A1A | **Pin D2** | Tracción Izquierda - Sentido de Avance (PWM) |
| **Puente H L9110S** | A1B | **Pin D5** | Tracción Izquierda - Sentido de Reversa (PWM) |
| **Puente H L9110S** | B1A | **Pin D3** | Tracción Derecha - Sentido de Avance (PWM) |
| **Puente H L9110S** | B1B | **Pin D4** | Tracción Derecha - Sentido de Reversa (PWM) |
| **Servomotor S1** | Señal | **Pin D6** | Dirección Rueda Delantera Izquierda |
| **Servomotor S2** | Señal | **Pin D7** | Dirección Rueda Delantera Derecha |
| **Servomotor S3** | Señal | **Pin D8** | Dirección Rueda Trasera Izquierda |
| **Servomotor S4** | Señal | **Pin A0** | Dirección Rueda Trasera Derecha |
| **Regulador Step-Down**| Salida 5V-6V | VCC Servos | Alimentación aislada para S1, S2, S3 y S4 (GND común) |

*Consulte [ESQUEMATICO_NANO_ESP32.md](file:///mnt/c/Users/joaqu/Downloads/hmi_rover_cepit/ESQUEMATICO_NANO_ESP32.md) para el pinout completo y los pines libres de expansión.*

---

## 5. Protocolo de Comunicación y Robustez de Software

### 5.1. Estructura Binaria de Datos Unificada (Trama de 6 Bytes)
Para evitar discrepancias de memoria y alineación de bytes entre arquitecturas heterogéneas (ESP32 con arquitectura RISC-V de 32 bits y Arduino MKR con microcontrolador SAMD21 ARM Cortex-M0+), el paquete se define con tipos enteros exactos y empaquetado estricto con `__attribute__((packed))`:

```cpp
struct __attribute__((packed)) Paquete {
  int16_t traccion_izq;  // -255 a 255 (negativo: reversa, positivo: avance)
  int16_t traccion_der;  // -255 a 255 (control independiente para calibración)
  uint8_t angulo_s1;     // 10 a 170 grados (servomotor de dirección 1)
  uint8_t angulo_s2;     // 10 a 170 grados (servomotor de dirección 2)
};
```
* **Tamaño total:** Exactamente **6 bytes**.
* Maximiza la tasa de transmisión por radio y minimiza el uso de CPU.

### 5.2. Configuración de Radiofrecuencia NRF24L01
* **Canal:** `108` (frecuencia: **2.508 GHz**). Se seleccionó deliberadamente por encima del espectro estándar de Wi-Fi de 2.4 GHz (canales 1 al 13) para evitar saturación e interferencias electromagnéticas.
* **Potencia:** `RF24_PA_MAX` (máxima potencia de emisión).
* **Tasa de datos (Data Rate):** `RF24_250KBPS` (baja velocidad para maximizar alcance, sensibilidad y penetración).

### 5.3. Medidas de Robustez de Software Implementadas
1. **Filtro Anti Key-Repeat en Python:** Las bibliotecas de interfaz gráfica en la PC generan ráfagas repetidas al mantener una tecla presionada. La GUI implementa un diccionario de estados (`teclas_presionadas`) para no inundar el puerto serie y enviar comandos solo cuando cambia el estado real de control.
2. **Drenaje de Búfer RF en Arduino MKR:** Para impedir que la cola interna de 3 niveles de carga del NRF24L01 se desborde y congele el procesador SAMD21, el lazo de recepción vacía la pila rápidamente utilizando:
   ```cpp
   while (radio.available()) {
       radio.read(&paquete, sizeof(Paquete));
   }
   ```
   De esta manera, el actuador siempre procesa únicamente la trama más reciente y descarta datos obsoletos acumulados.
3. **Máquina de Estados no bloqueante en ESP32:** Cero uso de `delay()`. Todas las secuencias y macros de pulso se calculan con base en `millis()`.
4. **Failsafe de Emergencia por Timeout (1000 ms):** En el receptor MKR, si transcurren más de `1000 ms` (`TIMEOUT_MS`) sin recibir una trama válida de radio, se dispara de inmediato la rutina `pararMotores()`, previniendo que el vehículo continúe en movimiento sin control ante pérdidas de enlace.
5. **Inversión Mecánica en Servomotores:** La macro de dirección en teclado envía 120° para la tecla `A` (giro a la izquierda) y 60° para la tecla `D` (giro a la derecha), compensando la orientación invertida con la que están montados los servos en el chasis físico.
6. **Compensación de Motores en Tiempo Real:** Debido a discrepancias de fabricación en los motores amarillos de CC (el motor izquierdo rota con mayor velocidad que el derecho), la interfaz de control cuenta con sliders de calibración independiente de potencia PWM para nivelar la trayectoria recta en marcha.

---

## 6. Estructura del Repositorio

```text
hmi_rover_cepit/
├── AGENTS.md                                # Este documento de referencia y contexto
├── ESQUEMATICO_MKR1310.md                   # Esquemático completo de conexiones y pinout del MKR
├── ESQUEMATICO_NANO_ESP32.md                # Esquemático completo de conexiones y pinout del Nano ESP32
├── Lanzar_HMI_Rover.bat                     # Lanzador Windows de la interfaz Python normal
├── Lanzar_HMI_Debug.bat                     # Lanzador Windows de la interfaz Python modo DEBUG
├── Subir_Cambios.bat                        # Sincronizador de 1 clic con GitHub
├── WindowsFormsApp4/                        # Interfaz gráfica de telemetría en C# (.NET)
├── WindowsFormsApp4.slnx                    # Archivo de solución de Visual Studio
├── Firmware_y_Control/                      # Firmware de microcontroladores y software HMI
│   ├── Contexto actual.docx                 # Documento técnico original del equipo
│   ├── Codigo_MKR_28-8/                     # Código de referencia preliminar para MKR
│   ├── Control/                             # Códigos para el módulo Transmisor (ESP32-C3 y Arduino Nano)
│   │   ├── Control_ESP32_C3_Debug/          # Versión DEBUG con telemetría RF y volcado HEX
│   │   ├── Control_ESP32_C3_Optimizado/     # Versión optimizada de transmisión
│   │   ├── Control_LOLIN-C3-MINI/           # Versión base LOLIN C3 Mini
│   │   ├── Control_LOLIN-C3-MINI-v0.2/
│   │   ├── Control_LOLIN_C3_MINI-v0.1/
│   │   └── Joystick_Arduino_Nano/           # Firmware Mando Joystick físico autónomo
│   ├── Ejecutor/                            # Códigos para el módulo Receptor del Rover
│   │   ├── Ejecutor_ArduinoNano_ESP32/      # Versión oficial Arduino Nano ESP32 (6x6 + 4WS)
│   │   ├── Ejecutor_ArduinoMKR_Debug/       # Versión DEBUG con reporte de FIFO, actuadores y watchdog
│   │   ├── Ejecutor_ArduinoMKR_Optimizado/  # Versión optimizada MKR 1310 con failsafe y vaciado de búfer
│   │   ├── Ejecutor_ArduinoMKR/             # Versión base
│   │   └── Ejecutor_ArduinoMKR-v0.1/
│   └── Interfaz/                            # Scripts de interfaz HMI en Python
│       ├── HMI_Rover_Debug.py               # Script HMI DEBUG con visor de tramas TX/RX en tiempo real
│       ├── HMI_Rover_V2.py                  # Script principal estándar con GUI y sliders
│       ├── Interfaz-Rover-29-8-v2.py
│       ├── Interfaz-Rover-29-8-v3.py
│       └── Interfaz-Rover_29-8.py
└── Informacion del grupo anterior/          # Documentación y antecedentes históricos
```

---

## 7. Próximos Hitos y Hoja de Ruta

1. **Validación en Rampa Diferencial (CEPIT):** Ensayos de descenso y ascenso por gravedad en rampa inclinada a 20° para verificar estabilidad estática y documentar error de tracción (tomando como base de modelado el rover indio *Pragyan* en la misión Chandrayaan-3).
2. **Pruebas de Campo en Sierra (Terreno Natural):** Evaluación en sustrato irregular y ajuste dinámico bajo carga del par motor mediante calibración PWM.
3. **Control en Lazo Cerrado:** Reemplazo de los motores amarillos básicos de corriente continua por motores con **encoders magnéticos de efecto Hall** de alta resolución para implementar algoritmos PID de velocidad y posición.
4. **Placa PCB de Producción:** Finalización del esquemático y ruteado de la PCB por parte de Lucas para eliminar cableado tipo protoboard.
5. **Telemetría de Visión Inalámbrica:** Montaje de módulo **ESP32-CAM** sobre un servo independiente de 180° para transmisión de video en tiempo real vía Wi-Fi, operando en red separada del canal de tracción por RF24.

---

## 8. Guía para Agentes de IA al Modificar Código

Cualquier agente que proponga cambios o refactorizaciones debe:
1. **Preservar el empaquetado binario:** Nunca modificar campos de la estructura `Paquete` sin sincronizar simultáneamente el script de Python, el código del ESP32-C3 y el código del Arduino MKR 1310.
2. **Respetar la restricción anti-bloqueo:** Nunca introducir llamadas a `delay()` en la lógica de transmisión ni recepción.
3. **Mantener los límites de seguridad de actuadores:** No programar valores angulares fuera de `[10, 170]` grados y conservar la rutina de parada en caso de pérdida de enlace (`TIMEOUT_MS = 1000`).
4. **Conservar las frecuencias asignadas:** Mantener el canal RF en 108 a 250 kbps a menos que se realice una reconfiguración coordinada de radio en ambos firmwares.
