# Estado vivo del proyecto

Lectura obligatoria al iniciar una sesion, junto con `AGENTS.md` y `CHANGELOG.md`. Actualizar al terminar cada bloque de trabajo. Sin emojis.

Ultima actualizacion: 2026-11-02.

## Estado

| Item | Estado |
|---|---|
| Version activa | v3.0 |
| Pruebas en PC (`tests/`) | Pasan |
| Compilacion con el nucleo ESP32 real | **Pendiente** |
| Prueba en hardware | **Pendiente** |

## Tareas inmediatas

1. Compilar y cargar los dos firmwares.
2. Confirmar el puente H instalado. El firmware usa L298N por defecto, tomado del ultimo commit del equipo. Los documentos anteriores decian L9110S.
3. Recablear el ejecutor segun el esquematico: los pines del firmware anterior no eran validos para esta placa.
4. Confirmar el modelo de servo. Determina la corriente del riel de servos: MG996R requiere un regulador de al menos 10 A.
5. Revisar en banco el sentido de giro (`INVERTIR_IZQ`, `INVERTIR_DER`) y la calibracion de pulsos (`SERVO_TICKS_0`, `SERVO_TICKS_180`).
6. Seguir la tabla de diagnostico del esquematico y anotar aca si persisten los brownouts.

## Problema de reinicios del ejecutor

Causa fisica: brownout del ESP32-S3 por picos de corriente de motores y servos. Se esta revisando la alimentacion.

Problemas de software que los provocaban o agravaban, corregidos en v3.0:

| Problema | Efecto |
|---|---|
| La HMI enviaba solo al cambiar una tecla y el puente solo reenviaba eso | Con una tecla sostenida, a los 500 ms saltaba el failsafe y centraba los servos, y la trama siguiente los volvia a mover |
| El failsafe y el arranque movian los 4 servos a la vez, sin rampa | Pico conjunto. Puede encadenar reinicios: arranque, pico, brownout, arranque |
| Los motores pasaban de 0 a la consigna en una sola trama, y la reversa invertia sin pasar por cero | Corriente de arranque y de frenado a contramarcha |
| Los angulos se aceptaban hasta 360 en el ejecutor con PCA9685 | Pulsos fuera de rango, servo contra el tope con corriente de bloqueo |
| Ejecutor como AP, con WiFi a potencia maxima | Picos de radio sobre la bateria compartida |
| Varias lineas `Serial.printf` por trama, con salida bloqueante | Retrasos en el lazo de control |

Otros errores corregidos en la misma revision:

- El par PCA9685 V2 tenia las dos placas como estacion: ninguna creaba la red.
- Sus pines de motor eran de ESP32 clasico.
- La tecla S enviaba valores positivos que ese ejecutor interpretaba como avance.
- El transmisor seguia enviando la ultima consigna con la HMI cerrada.

## Limites conocidos

- No se puede afirmar que los brownouts desaparezcan hasta medir en el rover.
- La latencia de la HMI debug se mide con el reloj de la PC e incluye la demora del USB. Sirve para comparar, no como valor absoluto.
- El contador de reinicios usa memoria RTC: se conserva en resets, y una caida total de tension lo reinicia. La HMI debug tambien detecta reinicios porque el tiempo de encendido retrocede.
- Se retiro el boton de flasheo de la HMI: los firmwares se cargan con Arduino IDE o `arduino-cli`.
- Las guias de estudio en `03_Documentacion_y_Guias/Guias/` describen la arquitectura nRF24 anterior.
