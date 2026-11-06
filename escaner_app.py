"""Programa 2: escáner facial en vivo (cámara, reconocimiento y recarga desde la base)."""

from collections import deque
from pathlib import Path
from tkinter import filedialog, messagebox

import cv2
import numpy as np

from escaner_ventana import VentanaEscaner
from facescan import base_datos, config, interfaz, motor_facial
from facescan.conexion import ErrorBaseDatos
from facescan.interfaz import ErrorCamara
from facescan.motor_facial import ErrorMotorFacial

MS_POR_CUADRO = 10  # read() espera el siguiente cuadro: el ritmo lo pone la cámara (~30 fps)
INDICES_CAMARA = range(4)
SIN_ROSTRO, DESCONOCIDO = "Sin rostro", "Desconocido"


def elegir_candidato(resultados):
    """Devuelve el id más parecido del cuadro, o "Sin rostro" / "Desconocido"."""
    if not resultados:
        return SIN_ROSTRO
    conocidos = [r for r in resultados if r["id"] is not None]
    if not conocidos:
        return DESCONOCIDO
    return max(conocidos, key=lambda r: r["similitud"])["id"]


class AppEscaner(VentanaEscaner):
    """Escáner: lee la cámara, reconoce rostros y mantiene los vectores al día."""

    def __init__(self, ventana):
        self.ventana = ventana
        self.camara, self.indice_camara = None, config.INDICE_CAMARA
        self.pausado = False
        self.contador = 0
        self.resultados = []
        self.historial = deque(maxlen=config.ANALISIS_PARA_CAMBIAR_FICHA)
        self.ficha_actual = None
        self.version, self.ids, self.personas = None, [], {}
        self.matriz = np.empty((0, config.DIMENSION_EMBEDDING), dtype=np.float32)
        self.tarea_camara = self.tarea_bd = None
        self.construir_interfaz()
        self.cambiar_ficha(SIN_ROSTRO)
        self.abrir_camara_inicial()
        self.consultar_base()
        self.ciclo_camara()
        ventana.protocol("WM_DELETE_WINDOW", self.cerrar)

    # ---------- Cámara ----------

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

    # ---------- Reconocimiento ----------

    def procesar_cuadro(self, cuadro):
        """Analiza 1 de cada N cuadros y dibuja el último resultado en todos."""
        if self.contador % config.CUADROS_ENTRE_ANALISIS == 0:
            self.resultados = self.analizar(cuadro)
            self.decidir_ficha(self.resultados)
        self.contador += 1
        self.mostrar_en_vista(cuadro, self.marcas(self.resultados))

    def analizar(self, imagen):
        """Detecta los rostros de la imagen e identifica cada uno."""
        resultados = []
        for rostro in motor_facial.detectar_rostros(imagen):
            embedding = motor_facial.extraer_embedding(imagen, rostro)
            id_persona, similitud = motor_facial.identificar(
                embedding, self.ids, self.matriz, umbral=self.var_umbral.get())
            resultados.append({"caja": rostro["caja"], "id": id_persona, "similitud": similitud})
        return resultados

    def marcas(self, resultados):
        """Convierte los resultados en recuadros: verde con nombre, o rojo "Desconocido"."""
        marcas = []
        for r in resultados:
            porcentaje = f"{max(r['similitud'], 0):.0%}"
            persona = self.personas.get(r["id"])
            if persona:
                marcas.append((r["caja"], interfaz.VERDE, f"{persona['nombre_completo']} {porcentaje}"))
            else:
                marcas.append((r["caja"], interfaz.ROJO, f"{DESCONOCIDO} {porcentaje}"))
        return marcas

    def decidir_ficha(self, resultados):
        """Cambia la ficha solo si los últimos análisis coinciden (evita parpadeos)."""
        candidato = elegir_candidato(resultados)
        self.historial.append(candidato)
        estable = len(self.historial) == self.historial.maxlen and len(set(self.historial)) == 1
        if estable and candidato != self.ficha_actual:
            self.cambiar_ficha(candidato)
        self.actualizar_similitud(resultados)

    def cambiar_ficha(self, candidato):
        """Muestra en la ficha al id indicado, o "Sin rostro" / "Desconocido"."""
        self.ficha_actual = candidato
        texto = candidato if isinstance(candidato, str) else SIN_ROSTRO
        self.mostrar_ficha(self.personas.get(candidato), texto)

    def actualizar_similitud(self, resultados):
        """Muestra la mayor similitud de la persona que está en la ficha."""
        similitudes = [r["similitud"] for r in resultados if r["id"] == self.ficha_actual]
        self.mostrar_similitud(max(similitudes) if similitudes else None)

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
                self.cambiar_ficha(self.ficha_actual if sigue else SIN_ROSTRO)
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
        ruta = filedialog.askopenfilename(title="Analizar foto", filetypes=interfaz.TIPOS_IMAGEN)
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
        self.mostrar_en_vista(imagen, self.marcas(resultados))
        self.cambiar_ficha(elegir_candidato(resultados))
        self.actualizar_similitud(resultados)
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
    interfaz.iniciar_app(AppEscaner, "FaceScan · Escáner", "1020x640")


if __name__ == "__main__":
    main()
