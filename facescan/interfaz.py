"""Ayudas de Tkinter para los dos programas: cámara, imágenes y tareas en segundo plano."""

import functools
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

from facescan import config, motor_facial

VERDE = (60, 180, 75)    # colores en BGR, como los usa OpenCV
ROJO = (40, 40, 220)
BACKENDS = {"MSMF": cv2.CAP_MSMF, "DSHOW": cv2.CAP_DSHOW}  # Media Foundation y DirectShow
TIPOS_IMAGEN = [("Imágenes", "*.jpg *.jpeg *.png"), ("Todos los archivos", "*.*")]


class ErrorCamara(Exception):
    """Error con un mensaje en español listo para mostrar al usuario."""


def _backends_en_orden():
    """Devuelve los backends a probar: primero el de config y luego el otro."""
    if sys.platform != "win32":
        return [cv2.CAP_ANY]
    preferido = BACKENDS.get(config.BACKEND_CAMARA.upper(), cv2.CAP_MSMF)
    return [preferido] + [api for api in BACKENDS.values() if api != preferido]


def _esperar_imagen(camara):
    """Descarta los cuadros negros del arranque; dice si la cámara entregó alguna imagen."""
    limite = time.monotonic() + config.SEGUNDOS_ARRANQUE_CAMARA
    hubo_cuadro = False
    while time.monotonic() < limite:
        leido, cuadro = camara.read()
        if leido:
            hubo_cuadro = True
            if cuadro.mean() > config.BRILLO_MINIMO_CAMARA:
                return True
    return hubo_cuadro  # imagen muy oscura de verdad (tapa puesta): igual se usa


def abrir_camara(indice):
    """Abre la cámara con el backend de config (o el otro si falla) o lanza ErrorCamara."""
    for api in _backends_en_orden():
        camara = cv2.VideoCapture(indice, api)
        if camara.isOpened() and _esperar_imagen(camara):
            return camara
        camara.release()
    raise ErrorCamara(
        f"No se pudo abrir la cámara {indice}.\n\n"
        "• ¿Otra aplicación la está usando (Teams, Zoom, la app Cámara)? Ciérrala.\n"
        "• Revisa Configuración de Windows > Privacidad y seguridad > Cámara > "
        "\"Permitir que las aplicaciones de escritorio accedan a la cámara\"."
    )


def guardar_imagen(imagen_bgr, ruta):
    """Guarda una imagen como JPG (acepta rutas con tildes)."""
    _, datos = cv2.imencode(".jpg", imagen_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    datos.tofile(str(ruta))


@functools.cache
def _fuente(tamano):
    """Devuelve una fuente con tildes y ñ (Arial en Windows)."""
    try:
        return ImageFont.truetype("arial.ttf", tamano)
    except OSError:
        return ImageFont.load_default(tamano)


def dibujar_rostros(imagen_bgr, marcas, grosor=None):
    """Devuelve una copia con un recuadro por marca (caja, color, texto o None)."""
    imagen = imagen_bgr.copy()
    grosor = grosor or max(2, imagen.shape[1] // 300)
    for (x, y, w, h), color, _ in marcas:
        cv2.rectangle(imagen, (x, y), (x + w, y + h), color, grosor)
    if not any(texto for _, _, texto in marcas):
        return imagen
    # cv2.putText no dibuja tildes ni ñ: los textos se escriben con Pillow.
    lienzo = Image.fromarray(cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB))
    pincel = ImageDraw.Draw(lienzo)
    fuente = _fuente(max(14, imagen.shape[1] // 40))
    for (x, y, _, _), color, texto in marcas:
        if texto:
            izq, _, der, abajo = pincel.textbbox((0, 0), texto, font=fuente)
            alto = abajo + 6
            base = max(y, alto)  # si el rostro toca el borde de arriba, la etiqueta no se sale
            pincel.rectangle((x, base - alto, x + der - izq + 8, base), fill=color[::-1])
            pincel.text((x + 4, base - alto + 3), texto, font=fuente, fill="white")
    return cv2.cvtColor(np.asarray(lienzo), cv2.COLOR_RGB2BGR)


def imagen_a_tk(imagen_bgr, ancho, alto):
    """Convierte una imagen de OpenCV en una imagen de Tkinter que cabe en ancho x alto."""
    imagen = Image.fromarray(cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2RGB))
    imagen.thumbnail((ancho, alto))
    return ImageTk.PhotoImage(imagen)


def en_segundo_plano(ventana, tarea, al_terminar):
    """Ejecuta tarea() en un hilo y luego llama al_terminar(resultado, error) sin congelar."""
    buzon = queue.Queue(maxsize=1)

    def trabajar():
        try:
            buzon.put((tarea(), None))
        except Exception as error:
            buzon.put((None, error))

    def revisar():
        # Tkinter solo se puede tocar desde el hilo principal: aquí se recoge el resultado.
        try:
            resultado, error = buzon.get_nowait()
        except queue.Empty:
            ventana.after(50, revisar)
            return
        al_terminar(resultado, error)

    threading.Thread(target=trabajar, daemon=True).start()
    ventana.after(50, revisar)


def ventana_captura(padre, carpeta, al_capturar):
    """Muestra la cámara en una ventanita; al capturar guarda la foto y llama al_capturar(ruta)."""
    padre.configure(cursor="watch")  # abrir la cámara puede tardar unos segundos
    padre.update_idletasks()
    try:
        camara = abrir_camara(config.INDICE_CAMARA)
    except ErrorCamara as error:
        messagebox.showerror("FaceScan", str(error), parent=padre)
        return
    finally:
        padre.configure(cursor="")
    ventana = tk.Toplevel(padre)
    ventana.title("Tomar foto")
    ventana.transient(padre)
    ventana.grab_set()
    vista = ttk.Label(ventana)
    vista.pack(padx=8, pady=8)
    ttk.Label(ventana, text="Recuadro verde = un rostro listo para capturar").pack()
    estado = {"cuadro": None, "tarea": None}

    def cerrar():
        if estado["tarea"]:
            ventana.after_cancel(estado["tarea"])
        camara.release()
        ventana.destroy()

    def actualizar():
        leido, cuadro = camara.read()
        if not leido:
            cerrar()
            messagebox.showerror("FaceScan", "Se perdió la señal de la cámara.", parent=padre)
            return
        estado["cuadro"] = cuadro
        rostros = motor_facial.detectar_rostros(cuadro)
        color = VERDE if len(rostros) == 1 else ROJO
        imagen = dibujar_rostros(cuadro, [(r["caja"], color, None) for r in rostros])
        vista.imagen = imagen_a_tk(imagen, 640, 480)  # guardar la referencia evita que se borre
        vista.configure(image=vista.imagen)
        estado["tarea"] = ventana.after(40, actualizar)

    def capturar():
        if estado["cuadro"] is None:
            return
        ruta = carpeta / datetime.now().strftime("camara_%H%M%S_%f.jpg")
        guardar_imagen(estado["cuadro"], ruta)
        cerrar()
        al_capturar(ruta)

    ttk.Button(ventana, text="Capturar", command=capturar).pack(pady=8)
    ventana.protocol("WM_DELETE_WINDOW", cerrar)
    actualizar()


def iniciar_app(clase_app, titulo, tamano):
    """Crea la ventana, comprueba los modelos y arranca la app (o explica qué falta)."""
    ventana = tk.Tk()
    ventana.title(titulo)
    ventana.geometry(tamano)
    try:
        motor_facial.cargar_modelos()
    except motor_facial.ErrorMotorFacial as error:
        ventana.withdraw()
        messagebox.showerror("FaceScan", str(error))
        ventana.destroy()
        return
    clase_app(ventana)
    ventana.mainloop()
