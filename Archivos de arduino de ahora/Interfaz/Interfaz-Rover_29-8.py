import tkinter as tk
import serial
import time

PUERTO_SERIAL = 'COM4'  # Cambia por tu puerto
BAUD_RATE = 115200

try:
    esp32 = serial.Serial(PUERTO_SERIAL, BAUD_RATE, timeout=1)
    time.sleep(2)
    print("Conexión serial establecida.")
except Exception as e:
    print(f"Error conectando al puerto serial: {e}")
    exit()

def presionar_tecla(event):
    tecla = event.keysym.lower()
    if tecla in ['w', 'a', 's', 'd']:
        # Leemos el valor actual de los sliders
        pot_izq = slider_izq.get()
        pot_der = slider_der.get()
        
        # Enviamos la tecla y las potencias separadas por comas (Ej: "W,150,165\n")
        comando = f"{tecla},{pot_izq},{pot_der}\n"
        esp32.write(comando.encode())
        etiqueta_estado.config(text=f"Comando: {tecla.upper()} | Izq: {pot_izq} | Der: {pot_der}")

def soltar_tecla(event):
    tecla = event.keysym.lower()
    if tecla in ['w', 'a', 's', 'd']:
        esp32.write(b' \n') 
        etiqueta_estado.config(text="Comando enviado: PARAR")

# --- Configuración de la Ventana ---
ventana = tk.Tk()
ventana.title("Control Rover Lunar")
ventana.geometry("800x700")

tk.Label(ventana, text="Panel de Control Avanzado", font=("Arial", 14, "bold")).pack(pady=10)
tk.Label(ventana, text="Mantén presionada W, A, S o D para moverte.", font=("Arial", 10)).pack(pady=5)

# --- Marco de Calibración ---
marco_calibracion = tk.LabelFrame(ventana, text="Calibración Independiente (0-255)", padx=10, pady=10)
marco_calibracion.pack(fill="x", padx=20, pady=10)

tk.Label(marco_calibracion, text="Motor Izquierdo (M1):").pack(anchor="w")
slider_izq = tk.Scale(marco_calibracion, from_=0, to=255, orient="horizontal")
slider_izq.set(150)
slider_izq.pack(fill="x")

tk.Label(marco_calibracion, text="Motor Derecho (M2):").pack(anchor="w")
slider_der = tk.Scale(marco_calibracion, from_=0, to=255, orient="horizontal")
slider_der.set(150)
slider_der.pack(fill="x")

etiqueta_estado = tk.Label(ventana, text="Esperando comando...", font=("Arial", 10), fg="blue")
etiqueta_estado.pack(pady=10)

ventana.bind('<KeyPress>', presionar_tecla)
ventana.bind('<KeyRelease>', soltar_tecla)

ventana.mainloop()