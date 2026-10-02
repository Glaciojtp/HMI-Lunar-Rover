//! Punto de entrada de la aplicacion de escritorio nativa HMI Rover Lunar V2.0.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use eframe::egui;
use hmi_gui::app::RoverApp;

fn main() -> eframe::Result<()> {
    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1120.0, 720.0])
            .with_min_inner_size([960.0, 640.0])
            .with_title("HMI Rover Lunar V2.0 - Rocker-Bogie 6x6 (Rust Nativo)"),
        ..Default::default()
    };

    eframe::run_native(
        "HMI Rover Lunar V2.0",
        native_options,
        Box::new(|_cc| Ok(Box::new(RoverApp::default()))),
    )
}
