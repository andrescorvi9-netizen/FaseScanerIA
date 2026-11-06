"""Programa 2: escáner facial en vivo."""

import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np

from facescan import base_datos, config, interfaz, motor_facial
from facescan.base_datos import ErrorBaseDatos
from facescan.interfaz import ErrorCamara
from facescan.motor_facial import ErrorMotorFacial

MS_POR_CUADRO = 10  # read() espera el siguiente cuadro: el ritmo lo pone la cámara (~30 fps)
ANCHO_VIDEO, ALTO_VIDEO = 640, 480
LADO_FOTO_FICHA = 220
INDICES_CAMARA = range(4)
SIN_ROSTRO, DESCONOCIDO = "Sin rostro", "Desconocido"
CAMPOS_FICHA = [("edad", "Edad"), ("carrera", "Carrera"), ("semestre", "Semestre"),
                ("codigo", "Código"), ("similitud", "Similitud")]
TIPOS_IMAGEN = [("Imágenes", "*.jpg *.jpeg *.png"), ("Todos los archivos", "*.*")]


def elegir_candidato(resultados):
    """Devuelve el id más parecido del cuadro, o "Sin rostro" / "Desconocido"."""
    if not resultados:
        return SIN_ROSTRO
    conocidos = [r for r in resultados if r["id"] is not None]
    if not conocidos:
        return DESCONOCIDO
    return max(conocidos, key=lambda r: r["similitud"])["id"]


class AppEscaner:
    """Ventana principal del escáner."""

    def __init__(self, ventana):
        self.ventana = ventana
        self.camara, self.indice_camara = None, config.INDICE_CAMARA
        self.pausado = False
        self.contador = 0
        self.resultados = []
        self.historial = deque(maxlen=config.ANALISIS_PARA_CAMBIAR_FICHA)
        self.ficha_actual = None
        self.version, self.ids, self.personas = None, [], {}
        self.tarea_camara = self.tarea_bd = None
        self.matriz = np.empty((0, config.DIMENSION_EMBEDDING), dtype=np.float32)
        self.construir_interfaz()
        self.mostrar_ficha(SIN_ROSTRO)
        self.abrir_camara_inicial()
        self.consultar_base()
        self.ciclo_camara()
        ventana.protocol("WM_DELETE_WINDOW", self.cerrar)

    # ---------- Construcción de la interfaz ----------

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
        self.var_estado_camara, self.var_estado_bd = tk.StringVar(), tk.StringVar(value="Conectando…")
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

    # ---------- Cámara y reconocimiento ----------

    def abrir_camara_inicial(self):
        """Abre la cámara de config en segundo plano para que la ventana aparezca enseguida."""
        self.var_estado_camara.set("Abriendo cámara…")
        self.boton_camara.configure(state="disabled")
        indice = self.indice_camara
        interfaz.en_segundo_plano(self.ventana, lambda: interfaz.abrir_camara(indice),
                                  self.al_abrir_camara)

    def al_abrir_camara(self, camara, error):
        """Empieza a usar la cámara abierta o explica por qué no abrió."""
        self.boton_camara.configure(state="normal")
        if error:
            self.var_estado_camara.set("Sin cámara: prueba \"Cambiar cámara\" o \"Analizar foto\".")
            messagebox.showerror("FaceScan", str(error))
            return
        self.camara = camara
        self.var_estado_camara.set(self.texto_camara())

    def texto_camara(self):
        """Describe la cámara en uso para la barra de estado."""
        if self.camara is None:
            return "Sin cámara."
        return f"Cámara {self.indice_camara} activa ({self.camara.getBackendName()})."

    def ciclo_camara(self):
        """Lee un cuadro, lo procesa y se vuelve a programar con after()."""
        if self.camara is not None and not self.pausado:
            leido, cuadro = self.camara.read()
            if leido:
                self.procesar_cuadro(cv2.flip(cuadro, 1))  # efecto espejo, más natural
            else:
                self.var_estado_camara.set("La cámara no envía imagen. ¿Se desconectó?")
        self.tarea_camara = self.ventana.after(MS_POR_CUADRO, self.ciclo_camara)

    def procesar_cuadro(self, cuadro):
        """Analiza 1 de cada N cuadros y dibuja el último resultado en todos."""
        if self.contador % config.CUADROS_ENTRE_ANALISIS == 0:
            self.resultados = self.analizar(cuadro)
            self.decidir_ficha(self.resultados)
        self.contador += 1
        self.mostrar_en_vista(cuadro, self.resultados)

    def analizar(self, imagen):
        """Detecta los rostros de la imagen e identifica cada uno."""
        resultados = []
        for rostro in motor_facial.detectar_rostros(imagen):
            embedding = motor_facial.extraer_embedding(imagen, rostro)
            id_persona, similitud = motor_facial.identificar(
                embedding, self.ids, self.matriz, umbral=self.var_umbral.get())
            resultados.append({"caja": rostro["caja"], "id": id_persona, "similitud": similitud})
        return resultados

    def mostrar_en_vista(self, imagen, resultados):
        """Dibuja los recuadros (verde conocido, rojo desconocido) y muestra la imagen."""
        marcas = []
        for r in resultados:
            porcentaje = f"{max(r['similitud'], 0):.0%}"
            persona = self.personas.get(r["id"])
            if persona:
                marcas.append((r["caja"], interfaz.VERDE, f"{persona['nombre_completo']} {porcentaje}"))
            else:
                marcas.append((r["caja"], interfaz.ROJO, f"{DESCONOCIDO} {porcentaje}"))
        self.vista.imagen = interfaz.imagen_a_tk(
            interfaz.dibujar_rostros(imagen, marcas), ANCHO_VIDEO, ALTO_VIDEO)
        self.vista.configure(image=self.vista.imagen)

    def decidir_ficha(self, resultados):
        """Cambia la ficha solo si los últimos análisis coinciden (evita parpadeos)."""
        candidato = elegir_candidato(resultados)
        self.historial.append(candidato)
        estable = len(self.historial) == self.historial.maxlen and len(set(self.historial)) == 1
        if estable and candidato != self.ficha_actual:
            self.mostrar_ficha(candidato)
        self.mostrar_similitud(resultados)

    # ---------- Ficha ----------

    def mostrar_ficha(self, candidato):
        """Llena la ficha con la persona indicada, o con "Sin rostro" / "Desconocido"."""
        self.ficha_actual = candidato
        persona = self.personas.get(candidato)
        if persona is None:
            self.var_nombre.set(candidato if isinstance(candidato, str) else SIN_ROSTRO)
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

    def mostrar_similitud(self, resultados):
        """Actualiza el % de similitud de la persona que está en la ficha."""
        similitudes = [r["similitud"] for r in resultados if r["id"] == self.ficha_actual]
        self.vars_ficha["similitud"].set(f"{max(similitudes):.0%}" if similitudes else "—")

    # ---------- Base de datos (en segundo plano) ----------

    def consultar_base(self):
        """Revisa estado.version en un hilo y recarga los vectores si cambió."""
        version_conocida = self.version

        def tarea():
            version = base_datos.version_datos()
            if version == version_conocida:
                return version, None
            ids, matriz = base_datos.cargar_embeddings()
            personas = {p["id"]: p for p in base_datos.listar_personas()}
            return version, (ids, matriz, personas)

        interfaz.en_segundo_plano(self.ventana, tarea, self.al_consultar)

    def al_consultar(self, resultado, error):
        """Aplica los datos nuevos o avisa que no hay conexión; luego programa otra consulta."""
        if isinstance(error, ErrorBaseDatos):
            # Se muestra la causa (servicio apagado, contraseña, tablas...) y se reintenta.
            self.var_estado_bd.set(f"Sin conexión a la base de datos (reintentando…). {error}")
        elif error:
            self.var_estado_bd.set(f"Error al consultar la base de datos: {error}")
        else:
            version, datos = resultado
            if datos:
                self.version = version
                self.ids, self.matriz, self.personas = datos
                self.historial.clear()
                # Si la persona de la ficha se editó o se eliminó, la ficha se actualiza.
                sigue = isinstance(self.ficha_actual, str) or self.ficha_actual in self.personas
                self.mostrar_ficha(self.ficha_actual if sigue else SIN_ROSTRO)
            self.var_estado_bd.set(f"Base de datos: {len(self.personas)} personas, "
                                   f"{len(self.ids)} fotos.")
        self.tarea_bd = self.ventana.after(config.MS_ENTRE_CONSULTAS_BD, self.consultar_base)

    # ---------- Botones ----------

    def alternar_pausa(self):
        """Pausa o reanuda la cámara."""
        self.pausado = not self.pausado
        self.boton_pausa.configure(text="Reanudar" if self.pausado else "Pausar")
        if not self.pausado:
            self.contador, self.resultados = 0, []
            self.historial.clear()
            self.var_estado_camara.set(self.texto_camara())

    def cambiar_camara(self):
        """Busca en segundo plano la siguiente cámara que funcione (índices 0 a 3)."""
        total = len(INDICES_CAMARA)
        orden = [(self.indice_camara + paso) % total for paso in range(1, total + 1)]
        if self.camara is not None:
            orden.remove(self.indice_camara)  # la actual ya funciona: se prueban las otras

        def tarea():
            for indice in orden:
                try:
                    return indice, interfaz.abrir_camara(indice)
                except ErrorCamara:
                    continue
            raise ErrorCamara("No se encontró otra cámara (se probaron los índices 0 a 3).")

        self.boton_camara.configure(state="disabled")
        self.var_estado_camara.set("Buscando otra cámara…")
        interfaz.en_segundo_plano(self.ventana, tarea, self.al_cambiar_camara)

    def al_cambiar_camara(self, resultado, error):
        """Usa la cámara encontrada o muestra por qué no se pudo."""
        self.boton_camara.configure(state="normal")
        if error:
            self.var_estado_camara.set(self.texto_camara())
            messagebox.showerror("FaceScan", str(error))
            return
        if self.camara is not None:
            self.camara.release()
        self.indice_camara, self.camara = resultado
        self.var_estado_camara.set(self.texto_camara())

    def analizar_foto(self):
        """Analiza una imagen del disco igual que un cuadro de la cámara."""
        ruta = filedialog.askopenfilename(title="Analizar foto", filetypes=TIPOS_IMAGEN)
        if not ruta:
            return
        try:
            imagen = motor_facial.leer_imagen(ruta)
        except ErrorMotorFacial as error:
            messagebox.showerror("FaceScan", str(error))
            return
        if not self.pausado:
            self.alternar_pausa()
        resultados = self.analizar(imagen)
        self.mostrar_en_vista(imagen, resultados)
        self.mostrar_ficha(elegir_candidato(resultados))
        self.mostrar_similitud(resultados)
        self.var_estado_camara.set(f"Foto analizada: {Path(ruta).name}. "
                                   "Pulsa Reanudar para volver a la cámara.")

    def cerrar(self):
        """Detiene los ciclos, libera la cámara y cierra la ventana."""
        for tarea in (self.tarea_camara, self.tarea_bd):
            if tarea:
                self.ventana.after_cancel(tarea)
        if self.camara is not None:
            self.camara.release()
        self.ventana.destroy()


def main():
    """Abre la ventana del escáner."""
    ventana = tk.Tk()
    ventana.title("FaceScan · Escáner")
    ventana.geometry("1020x640")
    try:
        motor_facial.cargar_modelos()
    except ErrorMotorFacial as error:
        ventana.withdraw()
        messagebox.showerror("FaceScan", str(error))
        ventana.destroy()
        return
    AppEscaner(ventana)
    ventana.mainloop()


if __name__ == "__main__":
    main()
