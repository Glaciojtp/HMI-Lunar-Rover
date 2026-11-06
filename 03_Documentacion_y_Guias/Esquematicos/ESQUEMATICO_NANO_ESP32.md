# Esquematico vigente: dos Arduino Nano ESP32 (v3.0)

## Transmisor

Solo necesita el cable USB a la PC. No lleva modulos externos: usa el WiFi de la placa.

## Ejecutor

| Componente | Pin del modulo | Pin del Nano ESP32 |
|---|---|---|
| L9110S | A1A (izquierda avance) | D2 |
| L9110S | A1B (izquierda reversa) | D5 |
| L9110S | B1A (derecha avance) | D3 |
| L9110S | B1B (derecha reversa) | D4 |
| PCA9685 | SDA / SCL | A4 / A5 |
| PCA9685 | VCC (logica) | 3.3V |
| PCA9685 | GND | GND |
| Servos S1 a S4 | Senal | Canales 0 a 3 del PCA9685 |

El rover lleva L9110S, el valor por defecto del firmware (`PUENTE_H_L298N 0`).

Alternativa L298N (`PUENTE_H_L298N 1`): ENA D2, IN1 D3, IN2 D4, ENB D5, IN3 D6, IN4 D7. Quitar los jumpers de ENA y ENB: si quedan puestos, el PWM no controla la velocidad.

## Alimentacion: tres rieles con masa en estrella

```text
                +--> [1000 uF] -------------> Puente H (motores)
                |
BATERIA --------+--> Buck/UBEC 5-6 V --> [1000 uF] --> V+ del PCA9685 (servos)
                |
                +--> Schottky --> [470 uF] --> VIN del Nano ESP32 (6 a 21 V)

Todos los negativos se unen en un unico punto junto a la bateria.
```

- **Diodo Schottky (1N5819 o SS34) y capacitor en VIN:** cuando los motores hunden la bateria, el diodo impide que le quiten carga al capacitor del Arduino.
- **V+ del PCA9685:** nunca desde el Arduino ni desde el pin 5V de una placa.
- **Masa en estrella:** la corriente de los motores no debe circular por el cable de masa del Arduino ni por el I2C.

## Dimensionar los reguladores

Son valores de referencia. Confirmar con la hoja de datos de los componentes montados.

| Carga | Corriente de pico orientativa | Consecuencia |
|---|---|---|
| 4 servos MG996R | Hasta unos 2.5 A cada uno en bloqueo: 10 A en total | Un LM2596 (3 A) no alcanza. Usar buck o UBEC de al menos 10 A |
| 4 servos MG90S | Hasta unos 0.7 A cada uno en bloqueo: menos de 3 A | Un buck de 5 A da margen |
| 3 motores amarillos por canal | Cerca de 1 A o mas cada uno al arrancar o bloquearse | El L9110S admite unos 0,8 A continuos por canal (2 A de pico). Con 3 motores por canal queda justo: si calienta, se corta o el rover pierde fuerza en rampa, usar un puente H de mas corriente |

## Diagnostico de reinicios con la HMI debug

Conectar las dos placas por USB, con motores y servos alimentados por sus rieles. Probar en este orden, con el rover en un soporte y las ruedas en el aire:

| Paso | Prueba | Si aparece BROWNOUT |
|---|---|---|
| 1 | Sin consignas (**Emitir consignas** apagado) | Falla de la logica o de VIN, sin relacion con las cargas |
| 2 | Perfil `Barrido servos` | Riel de servos, o masa compartida con la logica |
| 3 | Perfil `Escalon motores` | Riel de motores, o falta el diodo y el capacitor en VIN |
| 4 | Perfil `Inversion motores` | Igual que el paso 3, con mayor exigencia |
| 5 | Perfil `Esfuerzo total` | La bateria o el cableado no sostienen el pico conjunto |
| 6 | Repetir el paso 5 sin el USB del ejecutor | El USB estaba sosteniendo la logica. Revisar VIN |

Con un osciloscopio o multimetro con registro de minimos, medir VIN durante el paso 5.

Si el reinicio ocurre con las ruedas apoyadas y no en el aire, el problema es la corriente de arranque con carga: ajustar `PASO_RAMPA_PWM` en el ejecutor o reforzar la bateria y el puente H.

## Conexion doble por USB

Con el ejecutor en USB y bateria a la vez, la PC queda unida a la masa del rover. Usar cables de masa cortos y gruesos entre bateria y placa, para que la corriente de los motores no busque retorno por el USB.
