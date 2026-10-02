//! Crate de la Interfaz Grafica de Usuario (HMI) Nativa en Rust para el Rover Lunar V2.0.
//!
//! Desarrollado con eframe / egui para renderizado acelerado por hardware y comunicacion
//! serial no bloqueante con la electronica de abordo y la estacion terrena de radiofrecuencia.

pub mod app;
pub mod kinematics;
pub mod profiles;
pub mod serial_worker;
pub mod simulation;
