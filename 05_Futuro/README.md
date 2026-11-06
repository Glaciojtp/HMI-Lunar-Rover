# Trabajo futuro

Nada de esta carpeta forma parte del sistema activo. A diferencia de `04_Deprecado/`, aca hay trabajo que se va a retomar.

| Carpeta | Contenido | Se retoma cuando | Antes de usarlo |
|---|---|---|---|
| `Rust_LiDAR/` | Lanzador de la HMI en Rust (repositorio aparte `HMI-Lunar-Rover-Rust`), estudio de viabilidad y plan de LiDAR | Se construya el mapeo con LiDAR | Adaptar `protocol-rover` y los firmwares Rust al protocolo v3.0 |
| `Joystick/` | Firmware del mando fisico y guia de hardware | Se construya el mando | Reescribirlo: usa nRF24 y el protocolo anterior. Debe enviar `CMD,...` a 20 Hz, o el `PaqueteControl` v3.0 |
