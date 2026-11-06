# Archivos deprecados

**Nada de esta carpeta se usa ni se actualiza.** Se conserva solo como referencia. El sistema activo esta en `01_Oficial/`.

No son compatibles con los firmwares v3.0: el protocolo cambio.

Al deprecar un archivo, agregar una fila con la regla de `AGENTS.md`.

| Ubicacion | Que era | Por que se deprecia | Reemplazo |
|---|---|---|---|
| `Firmware/Receptor_Rover_NanoESP32/Ejecutor_ArduinoNano_ESP32/` | Ejecutor v2.1 con servos directos por LEDC, SoftAP y nRF24 opcional | Picos de corriente, AP a bordo, servos sin PCA9685 | `Ejecutor_NanoESP32` |
| `Firmware/Receptor_Rover_NanoESP32/Ejecutor_ArduinoNano_PCA9685/` | Receptor PCA9685 por UART (`S<id>:<angulo>`) | Sin enlace WiFi ni motores | `Ejecutor_NanoESP32` |
| `Firmware/Receptor_Rover_NanoESP32/Ejecutor_ArduinoNano_Funcional-servos/` | Sketch de banco de 4 servos con PCA9685 | Prueba puntual. De aca salio la calibracion de pulsos 150 a 550 | `Ejecutor_NanoESP32` |
| `Firmware/Ejecutor_PCA9685/` (V1 y V2) | Ejecutor WiFi con L298N y PCA9685 | Pines de ESP32 clasico, sin AP en ninguna placa, angulos hasta 360, failsafe que centraba los 4 servos de golpe | `Ejecutor_NanoESP32` |
| `Firmware/Transmisor_PCA9685/` y `Firmware/Transmisor_PC_NanoESP32/Transmisor_PCA9685/` | Puentes USB a WiFi o UART | Solo reenviaban al cambiar el comando, lo que disparaba el failsafe | `Transmisor_NanoESP32` |
| `Firmware/Transmisor_PC_NanoESP32/Transmisor_ArduinoNano_ESP32/` | Transmisor v2.2 con estacion WiFi | Seguia enviando la ultima consigna con la HMI cerrada | `Transmisor_NanoESP32` |
| `Firmware/Transmisor_PC_ESP32C3/` | Transmisor con ESP32-C3 | La placa fue reemplazada por el Nano ESP32 | `Transmisor_NanoESP32` |
| `Firmware/Receptor_Rover_MKR1310/` | Receptor con MKR 1310 y nRF24 | Placa y radio reemplazadas | `Ejecutor_NanoESP32` |
| `Firmware/Firmware_v2_2_pre/` | Pre-release con servos de rotacion continua | Experimento abandonado | `Ejecutor_NanoESP32`, `Transmisor_NanoESP32` |
| `Firmware/Firmware_v2_3_pre/` | Pre-release con servos por angulo | Consolidada en v3.0 | `Ejecutor_NanoESP32`, `Transmisor_NanoESP32` |
| `Firmware/Firmware_Debug/` | Variantes de depuracion de C3, MKR y Nano | La depuracion ahora esta en los firmwares activos | HMI debug |
| `HMI/Oficial_V2_x/` | HMI V2, V2.1, V2.1-pre, V2.2, V2.2-pre, flasher y perfiles de hardware | Cinco copias casi iguales, sin envio continuo. El boton de flasheo se retiro | `HMI_Rover.py` |
| `HMI/Debug_V2_x/` y `HMI/Debug_PCA9685/` | HMI de diagnostico y simulador cinematico | Solo manejaban una placa y no comparaban envio y recepcion | `HMI_Rover_Debug.py` |
| `HMI/HMI_Rover_Lunar_V2_obsoleto.exe` | Ejecutable del 28/09 (fuera de git) | Corresponde a una HMI vieja, y el lanzador lo priorizaba sobre el codigo | `Compilar_HMI_a_EXE.bat` |
| `Bancos_de_Prueba/` | Pruebas de RF y WiFi, mini tester, prueba de actuadores, simulacion Docker/Wine, sketch MG996R | Sobre pines y protocolos anteriores | `tests/` y HMI debug |
| `Documentacion/` | Esquematicos, guias y planes anteriores | Describen la arquitectura nRF24 o versiones previas | `README.md`, `AGENTS.md`, esquematico vigente |
| `Historico_Grupo_Anterior/` | Interfaz C#, firmwares e interfaces de las primeras versiones (antes `04_Legacy_y_Versiones_Previas`) | Historico | |
