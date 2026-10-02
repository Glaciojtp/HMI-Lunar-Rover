# GUIA RAPIDA DE USO: HMI ROVER LUNAR V2.0

> **Manual de referencia para los integrantes del equipo**  
> Esta guia explica como abrir la interfaz grafica de control, conectar el Rover por USB, calibrar motores y servos, flashear firmwares en un clic y operar el vehiculo tanto en la version oficial de produccion como en la suite de depuracion y la version paralela nativa en Rust.

---

## 1. ¿Como abrir la aplicacion?

### Opcion A: Suite Oficial de Produccion (Python / Tkinter)
1. Ejecutar el acceso directo `Lanzar_HMI_Rover.bat` en la raiz del repositorio.
2. Si se prefiere ejecutable autonomo sin dependencias, ejecutar `Compilar_HMI_a_EXE.bat` para generar `HMI_Rover_Lunar_V2.exe`.

### Opcion B: Suite de Depuracion y Banco de Pruebas (HMI Debug)
1. Ejecutar `02_Debug_y_Pruebas/Lanzar_HMI_Debug.bat`.
2. Permite conectar simultaneamente el Transmisor (TX) y el Receptor (RX), monitorear telemetria cruzada en tiempo real, sincronizar calibraciones en memoria NVS y subir firmware con un clic.

### Opcion C: Aplicacion Nativa Paralela en Rust (hmi-gui)
1. Ubicada en la carpeta hermana `C:\Users\joaqu\Desktop\HMI-Lunar-Rover-Rust`.
2. Compilada con `cargo run -p hmi-gui` para un rendimiento maximo y renderizado acelerado por hardware con egui.

---

## 2. Perfiles de Hardware Soportados

El sistema cuenta con autodeteccion pasiva por USB VID:PID y confirmacion activa por trama de handshake (`IDENT` -> `ID:<PLACA>:<ROL>:<VERSION>`):

1. **Arduino Nano ESP32 (Perfil Oficial Predeterminado):**
   - Microcontrolador ESP32-S3 a 3.3V nativo.
   - Compatible tanto para Dongle Transmisor como para Receptor a bordo y futuro Mando Joystick.
   - Pines SPI: D9 (CE), D10 (CSN), D11 (MOSI), D12 (MISO), D13 (SCK).
2. **ESP32-C3 SuperMini:**
   - Perfil para transmisores USB compactos previos.
3. **Arduino MKR 1310:**
   - Microcontrolador SAMD21 ARM Cortex-M0+ (receptor previo).

---

## 3. Subida de Firmware en 1 Clic

Desde la barra superior de `HMI_Rover_Debug.py`:
1. Seleccionar el puerto COM y el perfil correspondiente (o permitir que el sistema lo autodetecte).
2. Presionar el boton **[Subir TX]** o **[Subir RX]**.
3. La interfaz desconectara de forma segura el puerto, invocara el motor de compilacion y flasheo (`arduino-cli` o fallback a `esptool`) en segundo plano sin congelar la ventana, mostrara el progreso en la consola y reconectara el puerto automaticamente al finalizar.

---

## 4. Flujo de Calibracion Pre-Despliegue (Banco de Pruebas -> Campo)

Antes de operar en terreno (rampa o suelo natural):
1. **Conectar ambos dispositivos por USB a la PC:**
   - Transmisor conectado a su puerto COM.
   - Receptor montado en el Rover conectado a su puerto COM (alimentado por USB o con bateria compartiendo masa).
2. **Nivelar la trayectoria recta:**
   - Ajustar los deslizadores de Trims individuales (M1 a M6) y los centros de los servomotores (S1 a S4).
3. **Guardar en Memoria No Volatil (NVS):**
   - Presionar **[Sincronizar Calibracion RX]**. La GUI enviara la trama `CALIB,m1..m6,s1..s4` seguida de `PERSIST_NVS`. El microcontrolador almacenara los valores para que no se pierdan al apagar.
4. **Liberar para operacion autonoma:**
   - Presionar **[Liberar RX (Campo)]**. El puerto serie se cerrara de forma limpia, dejando el vehiculo listo para desconectar el cable USB y operar exclusivamente por radiofrecuencia (bateria).

---

## 5. Controles de Conduccion desde Teclado

| Tecla | Accion en el Rover | Descripcion Cinematica Rocker-Bogie |
|---|---|---|
| **W** | Avanzar | 6 motores hacia adelante, servos centrados (90°). |
| **S** | Retroceder | 6 motores en reversa, servos centrados (90°). |
| **A** | Curva a la Izquierda | Geometria Ackermann (delanteras a 120°, traseras a 60°). |
| **D** | Curva a la Derecha | Geometria Ackermann (delanteras a 60°, traseras a 120°). |
| **Q** | Rotacion en el lugar (Antihoraria) | Ruedas orientadas a 45° tangenciales, traccion en sentidos opuestos. |
| **E** | Rotacion en el lugar (Horaria) | Ruedas tangenciales, traccion en sentidos opuestos. |
| **Espacio** | Parada de Emergencia | Freno instantaneo de los 6 motores a 0 PWM. |

---

## 6. Modos Especiales de Conduccion

* **ACKERMANN:** Conduccion diferencial coordinada entre tren delantero y trasero.
* **CRAB (Modo Cangrejo):** Las 4 ruedas se orientan paralelas a 45° para desplazamiento diagonal sin rotacion del chasis.
* **MANUAL:** Permite controlar individualmente el angulo de cada rueda mediante deslizadores dedicados dentro del rango de seguridad [10, 170] grados.
