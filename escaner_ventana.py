"""Lo que se ve del escáner: vista de la cámara, controles y ficha de la persona."""

import tkinter as tk
from tkinter import ttk

import numpy as np

from facescan import config, interfaz, motor_facial
from facescan.motor_facial import ErrorMotorFacial

ANCHO_VIDEO, ALTO_VIDEO = 640, 480
LADO_FOTO_FICHA = 220
CAMPOS_FICHA = [("edad", "Edad"), ("carrera", "Carrera"), ("semestre", "Semestre"),
                ("codigo", "Código"), ("similitud", "Similitud")]
SIN_ROSTRO, DESCONOCIDO = "Sin rostro", "Desconocido"


class VentanaEscaner:
    """Arma los widgets del escáner; AppEscaner le pone la lógica."""

    def construir_interfaz(self):
        """Arma la vista de cámara con sus controles, la ficha y la barra de estado."""
        izquierda = ttk.Frame(self.ventana, padding=10)
        izquierda.pack(side="left", fill="y")
        # Marco de tamaño fijo: una foto de otra proporción no mueve el resto de la ventana.
        marco_video = tk.Frame(izquierda, bg="black", width=ANCHO_VIDEO, height=ALTO_VIDEO)
        marco_video.pack()
        marco_video.pack_propagate(False)
        self.vista = tk.Label(marco_video, bg="black")
        self.vista.pack(expand=True)
        self.construir_controles(izquierda)
        self.construir_ficha(ttk.Frame(self.ventana, padding=10))
        self.var_estado_camara = tk.StringVar()
        self.var_estado_bd = tk.StringVar(value="Conectando…")
        ttk.Label(izquierda, textvariable=self.var_estado_camara, foreground="gray").pack(anchor="w")
        ttk.Label(izquierda, textvariable=self.var_estado_bd, foreground="gray",
                  wraplength=ANCHO_VIDEO).pack(anchor="w")

    def construir_controles(self, padre):
        """Crea los botones y el control del umbral."""
        controles = ttk.Frame(padre)
        controles.pack(fill="x", pady=8)
        self.boton_pausa = ttk.Button(controles, text="Pausar", command=self.alternar_pausa)
        self.boton_camara = ttk.Button(controles, text="Cambiar cámara", command=self.cambiar_camara)
        for boton in (self.boton_pausa, self.boton_camara,
                      ttk.Button(controles, text="Analizar foto", command=self.analizar_foto)):
            boton.pack(side="left", padx=(0, 6))
        self.var_umbral = tk.DoubleVar(value=config.UMBRAL_COSENO)
        texto_umbral = tk.StringVar(value=f"Umbral: {config.UMBRAL_COSENO:.2f}")
        ttk.Label(controles, textvariable=texto_umbral, width=12).pack(side="right")
        ttk.Scale(controles, from_=config.UMBRAL_MINIMO, to=config.UMBRAL_MAXIMO, length=170,
                  variable=self.var_umbral,
                  command=lambda valor: texto_umbral.set(f"Umbral: {float(valor):.2f}")
                  ).pack(side="right", padx=6)

    def construir_ficha(self, marco):
        """Crea el panel con la foto y los datos de la persona reconocida."""
        marco.pack(side="left", fill="both", expand=True)
        ttk.Label(marco, text="Ficha", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.foto_ficha = tk.Label(marco, bg="#dddddd")
        self.foto_ficha.pack(pady=8)
        self.var_nombre = tk.StringVar()
        ttk.Label(marco, textvariable=self.var_nombre, font=("Segoe UI", 15, "bold"),
                  wraplength=300).pack(anchor="w", pady=(0, 8))
        datos = ttk.Frame(marco)
        datos.pack(fill="x")
        self.vars_ficha = {}
        for fila, (clave, titulo) in enumerate(CAMPOS_FICHA):
            self.vars_ficha[clave] = tk.StringVar(value="—")
            ttk.Label(datos, text=f"{titulo}:", font=("Segoe UI", 10, "bold")).grid(
                row=fila, column=0, sticky="nw", pady=2, padx=(0, 8))
            ttk.Label(datos, textvariable=self.vars_ficha[clave], wraplength=220).grid(
                row=fila, column=1, sticky="w")

    def mostrar_en_vista(self, imagen, resultados, personas):
        """Dibuja un recuadro por rostro (verde con nombre, rojo si es desconocido) y lo muestra."""
        marcas = []
        for r in resultados:
            porcentaje = f"{max(r['similitud'], 0):.0%}"
            persona = personas.get(r["id"])
            if persona:
                marcas.append((r["caja"], interfaz.VERDE, f"{persona['nombre_completo']} {porcentaje}"))
            else:
                marcas.append((r["caja"], interfaz.ROJO, f"{DESCONOCIDO} {porcentaje}"))
        self.vista.imagen = interfaz.imagen_a_tk(
            interfaz.dibujar_rostros(imagen, marcas), ANCHO_VIDEO, ALTO_VIDEO)
        self.vista.configure(image=self.vista.imagen)

    def mostrar_ficha(self, persona, texto):
        """Llena la ficha con la persona, o la vacía y muestra el texto ("Sin rostro"...)."""
        if persona is None:
            self.var_nombre.set(texto)
            for variable in self.vars_ficha.values():
                variable.set("—")
            self.poner_foto_ficha(None)
            return
        self.var_nombre.set(persona["nombre_completo"])
        for clave, _ in CAMPOS_FICHA[:-1]:
            self.vars_ficha[clave].set(persona[clave] or "—")
        self.poner_foto_ficha(persona["primera_foto"])

    def poner_foto_ficha(self, ruta):
        """Muestra la primera foto registrada, o un recuadro gris si no hay."""
        imagen = np.full((LADO_FOTO_FICHA, LADO_FOTO_FICHA, 3), 221, dtype=np.uint8)
        if ruta:
            try:
                imagen = motor_facial.leer_imagen(ruta)
            except ErrorMotorFacial:
                pass  # la foto se borró del disco: se deja el recuadro gris
        self.foto_ficha.imagen = interfaz.imagen_a_tk(imagen, LADO_FOTO_FICHA, LADO_FOTO_FICHA)
        self.foto_ficha.configure(image=self.foto_ficha.imagen)

    def mostrar_similitud(self, similitud):
        """Muestra el % de similitud de la persona de la ficha, o un guion."""
        self.vars_ficha["similitud"].set("—" if similitud is None else f"{similitud:.0%}")
