import tkinter as tk
import serial
import time

PUERTO_SERIAL = 'COM4'  # ¡Asegúrate de que este sea el puerto correcto!
BAUD_RATE = 115200

try:
    esp32 = serial.Serial(PUERTO_SERIAL, BAUD_RATE, timeout=1)
    time.sleep(2)
    print("Conexión serial establecida.")
except Exception as e:
    print(f"Error conectando al puerto serial: {e}")
    exit()

# Estado actual
comando_actual = ' '
pot_izq_actual = 150
pot_der_actual = 150

def enviar_estado():
    # Formato: Comando,PotIzq,PotDer\n (Ej: W,150,150\n)
    trama = f"{comando_actual.upper()},{pot_izq_actual},{pot_der_actual}\n"
    try:
        esp32.write(trama.encode())
        etiqueta_estado.config(text=f"TX: {trama.strip()}")
    except Exception as e:
        etiqueta_estado.config(text=f"Error TX: {e}")

def actualizar_slider(val):
    global pot_izq_actual, pot_der_actual
    pot_izq_actual = slider_izq.get()
    pot_der_actual = slider_der.get()
    enviar_estado()

def presionar_tecla(event):
    global comando_actual
    tecla = event.keysym.lower()
    if tecla in ['w', 'a', 's', 'd'] and comando_actual != tecla:
        comando_actual = tecla
        enviar_estado()

def soltar_tecla(event):
    global comando_actual
    tecla = event.keysym.lower()
    if tecla == comando_actual:
        comando_actual = ' '
        enviar_estado()

# --- Configuración de la Ventana ---
ventana = tk.Tk()
ventana.title("Control Rover")
ventana.geometry("400x350")

tk.Label(ventana, text="Panel de Control WASD", font=("Arial", 14, "bold")).pack(pady=10)
tk.Label(ventana, text="Mantén W, A, S o D para moverte.", font=("Arial", 10)).pack(pady=5)

# --- Marco de Calibración ---
marco_calibracion = tk.LabelFrame(ventana, text="Calibración Independiente (0-255)", padx=10, pady=10)
marco_calibracion.pack(fill="x", padx=20, pady=10)

tk.Label(marco_calibracion, text="Motor Izquierdo (M1):").pack(anchor="w")
slider_izq = tk.Scale(marco_calibracion, from_=0, to=255, orient="horizontal", command=actualizar_slider)
slider_izq.set(150)
slider_izq.pack(fill="x")

tk.Label(marco_calibracion, text="Motor Derecho (M2):").pack(anchor="w")
slider_der = tk.Scale(marco_calibracion, from_=0, to=255, orient="horizontal", command=actualizar_slider)
slider_der.set(150)
slider_der.pack(fill="x")

etiqueta_estado = tk.Label(ventana, text="Esperando comando...", font=("Arial", 10), fg="blue")
etiqueta_estado.pack(pady=20)

# Enlazamos los eventos
ventana.bind('<KeyPress>', presionar_tecla)
ventana.bind('<KeyRelease>', soltar_tecla)

ventana.mainloop()