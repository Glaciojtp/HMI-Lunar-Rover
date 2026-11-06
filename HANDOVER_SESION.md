# Estado vivo del proyecto

Lectura obligatoria al iniciar una sesion, junto con `AGENTS.md` y `CHANGELOG.md`. Actualizar al terminar cada bloque de trabajo. Sin emojis.

Ultima actualizacion: 2026-11-06.

## Estado

| Item | Estado |
|---|---|
| Version activa | v3.1 (HMI). Firmwares y protocolo v3.0 |
| Pruebas en PC (`tests/`) | Pasan |
| Compilacion con el nucleo ESP32 real | Pasa en CI (`arduino:esp32:nano_nora`) |
| Prueba en hardware | v3.0 funciona en el rover con L9110S (informado por el equipo el 2026-11-06). El mando v3.1 esta pendiente de prueba |

## Tareas inmediatas

1. Probar en el rover el mando v3.1: direccion sola sin movimiento, `A`/`D` + `W`/`S`, y pivote con `Q`/`E` + `W`/`S`.
2. Si el pivote no gira con los motores en marcha (la HMI muestra PWM aplicado distinto de cero), revisar los angulos de pivote en `calcular_consigna`: con ruedas radiales en vez de tangenciales el rover se traba.
3. Publicar la release con la HMI como ejecutable.
4. Confirmar el modelo de servo. Determina la corriente del riel de servos: MG996R requiere un regulador de al menos 10 A.
5. Vigilar la temperatura de los L9110S en rampa: cada canal maneja un motor y admite unos 0,8 A continuos.
6. Si vuelven los reinicios, seguir la tabla de diagnostico del esquematico y anotarlo aca.

## Configuracion validada en el rover (2026-11-06)

- 3 modulos L9110S dobles en paralelo: `PUENTE_H_L298N 0`, pines A1A D2, A1B D5, B1A D3, B1B D4.
- `INVERTIR_IZQ = true` e `INVERTIR_DER = true`: con false avanzaba al reves.
- Sintoma con `PUENTE_H_L298N 1`: 3 salidas en 0 V y solo 3 motores andando.

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
