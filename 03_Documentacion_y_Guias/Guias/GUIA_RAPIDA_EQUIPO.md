# 🚀 GUÍA RÁPIDA DE USO: HMI ROVER LUNAR V2.0

> **Manual de 1 minuto para los integrantes del equipo (100% orientado a Windows)**  
> Esta guía explica cómo abrir la interfaz gráfica de control, conectar el Rover por USB y comenzar a operarlo sin configurar entornos ni escribir líneas de comando.

---

## 1. ¿Cómo abrir la aplicación?

Elegí la opción que te resulte más cómoda:

### Opción A (Recomendada: Cero instalaciones ni configuración)
1. Si en la carpeta principal tenés el archivo **`HMI_Rover_Lunar_V2.exe`**, simplemente hacé **doble clic sobre él**.
   * *Si todavía no está generado:* Hacé doble clic en [`Compilar_HMI_a_EXE.bat`](file:///mnt/c/Users/joaqu/Downloads/hmi_rover_cepit/Compilar_HMI_a_EXE.bat). Esperás 30 segundos y te crea el `.exe` para siempre.
2. ¡Listo! Se abre la ventana gráfica nativa de Windows. No necesitás instalar Python, ni librerías, ni Docker.

### Opción B (Desde el lanzador automático con Python)
1. Hacé doble clic en [`Lanzar_HMI_Rover.bat`](file:///mnt/c/Users/joaqu/Downloads/hmi_rover_cepit/Lanzar_HMI_Rover.bat).
2. El script detecta si te falta alguna librería (como `pyserial`) y **la instala automáticamente en 2 segundos** sin que tengas que abrir consolas ni tocar nada.

---

## 2. Conectar el Rover por USB

1. Enchufá el cable USB del módulo transmisor (ESP32-C3 o Arduino) a cualquier puerto USB de tu computadora.
2. Abrí la HMI. El programa cuenta con **detección inteligente de hardware**:
   * Escanea automáticamente los puertos y **preselecciona el puerto COM correcto** (reconociendo chips CH340, CP210x, FTDI, Arduino o ESP32).
3. Hacé clic en el botón verde **"🔌 CONECTAR"**.
4. La insignia superior cambiará a **`🟢 CONECTADO (COMx)`**. ¡Ya estás enlazado por radio con el Rover!

---

## 3. Controles de Conducción desde la PC

Podés manejar el Rover con las teclas de tu teclado o haciendo clic en los botones de pantalla:

| Tecla | Acción en el Rover | Explicación Cinemática Rocker-Bogie |
|---|---|---|
| **`W`** | **Avanzar** | Los 6 motores giran hacia adelante con los servos centrados (90°). |
| **`S`** | **Retroceder** | Los 6 motores giran en reversa. |
| **`A`** | **Curva a la Izquierda** | Servos delanteros a 120° y traseros a 60° (geometría Ackermann). |
| **`D`** | **Curva a la Derecha** | Servos delanteros a 60° y traseros a 120°. |
| **`Q`** | **Rotación en el lugar (Antihoraria ↺)** | Las 4 ruedas se orientan a 45° tangenciales y giran sobre su eje. |
| **`E`** | **Rotación en el lugar (Horaria ↻)** | Rotación sobre su eje en sentido horario. |
| **`Espacio`** | **STOP de Emergencia** | Freno instantáneo de los 6 motores de tracción a 0 PWM. |

---

## 4. Modos Especiales de Conducción

En la barra superior podés cambiar el **Modo**:
* **ACKERMANN:** Conducción tradicional (delanteras y traseras doblan coordinadas).
* **CRAB (Modo Cangrejo):** Las 4 ruedas giran al mismo ángulo en paralelo para avanzar en diagonal sin rotar el chasis.
* **MANUAL:** Habilita los 4 deslizadores independientes para calibrar o mover cada servo por separado (S1, S2, S3, S4).

---

## 5. Sliders de Calibración de Motores (Trims)
Si notas que el vehículo tiende a desviarse ligeramente hacia un lado en línea recta debido a diferencias de fabricación entre los motorreductores amarillos:
* Ajustá los **Trims porcentuales (M1 a M6)** en el panel izquierdo.
* Modificá el **Master Izquierdo** o **Master Derecho** para nivelar la velocidad general de ambos lados.
