"""Programa 1: registro de personas con sus fotos (las acciones de cada botón)."""

import shutil
import tempfile
from pathlib import Path
from tkinter import filedialog, messagebox

from facescan import base_datos, config, interfaz, motor_facial
from facescan.conexion import ErrorBaseDatos
from facescan.motor_facial import ErrorMotorFacial
from registro_ventana import VentanaRegistro


def analizar_foto(ruta):
    """Lee una foto, detecta sus rostros y calcula el embedding si hay exactamente uno."""
    foto = {"ruta": Path(ruta), "imagen": None, "rostros": [], "embedding": None}
    try:
        foto["imagen"] = motor_facial.leer_imagen(ruta)
    except ErrorMotorFacial:
        foto["estado"] = "No se pudo abrir"
        return foto
    foto["rostros"] = motor_facial.detectar_rostros(foto["imagen"])
    cantidad = len(foto["rostros"])
    if cantidad == 1:
        foto["embedding"] = motor_facial.extraer_embedding(foto["imagen"], foto["rostros"][0])
        foto["estado"] = "Rostro OK"
    else:
        foto["estado"] = "Sin rostro" if cantidad == 0 else f"{cantidad} rostros"
    return foto


def agregar_fotos_a_persona(id_persona, rutas):
    """Calcula el embedding de cada foto y la agrega; devuelve (agregadas, problemas)."""
    agregadas, problemas = 0, []
    for ruta in rutas:
        try:
            base_datos.agregar_foto(id_persona, ruta, motor_facial.embedding_de_foto(ruta))
            agregadas += 1
        except ErrorMotorFacial as error:
            problemas.append(str(error))
        except ErrorBaseDatos as error:
            problemas.append(str(error))
            break
    return agregadas, problemas


class AppRegistro(VentanaRegistro):
    """Ventana de registro con el estado del formulario y lo que hace cada botón."""

    def __init__(self, ventana):
        self.ventana = ventana
        self.fotos = []
        self.id_editando = None
        self.ocupado = False
        self.carpeta_temporal = Path(tempfile.mkdtemp(prefix="facescan_"))
        self.construir_interfaz()
        self.refrescar_lista(avisar=True)
        ventana.protocol("WM_DELETE_WINDOW", self.cerrar)

    # ---------- Trabajo en segundo plano ----------

    def ejecutar(self, tarea, texto, al_exito):
        """Corre tarea() en segundo plano y luego al_exito(resultado), o muestra el error."""
        self.marcar_ocupado(True, texto)

        def al_terminar(resultado, error):
            self.marcar_ocupado(False, "Listo.")
            if error:
                self.mostrar_error(error)
            else:
                al_exito(resultado)
            self.refrescar_lista()

        interfaz.en_segundo_plano(self.ventana, tarea, al_terminar)

    def marcar_ocupado(self, ocupado, texto):
        """Muestra el estado y bloquea los botones mientras hay trabajo en curso."""
        self.ocupado = ocupado
        self.var_estado.set(texto)
        self.ventana.configure(cursor="watch" if ocupado else "")
        self.actualizar_botones(ocupado, self.id_editando is not None)

    # ---------- Fotos del formulario ----------

    def cargar_fotos(self):
        """Elige fotos del disco y las analiza."""
        rutas = filedialog.askopenfilenames(title="Elegir fotos", filetypes=interfaz.TIPOS_IMAGEN)
        self.agregar_a_vista(rutas)

    def tomar_foto(self):
        """Abre la cámara para capturar una foto."""
        interfaz.ventana_captura(self.ventana, self.carpeta_temporal,
                                 al_capturar=lambda ruta: self.agregar_a_vista([ruta]))

    def agregar_a_vista(self, rutas):
        """Analiza las fotos en segundo plano respetando el máximo por persona."""
        espacio = max(config.MAX_FOTOS_POR_PERSONA - len(self.fotos), 0)
        if rutas and len(rutas) > espacio:
            messagebox.showwarning("FaceScan", f"Máximo {config.MAX_FOTOS_POR_PERSONA} fotos por "
                                   f"persona: solo se agregarán {espacio}.")
            rutas = rutas[:espacio]
        if rutas:
            self.ejecutar(lambda: [analizar_foto(ruta) for ruta in rutas],
                          "Analizando fotos…", self.al_analizar)

    def al_analizar(self, fotos):
        """Agrega las fotos analizadas a la vista previa."""
        self.fotos.extend(fotos)
        self.dibujar_miniaturas(self.fotos)

    def quitar_foto(self, indice):
        """Quita una foto de la vista previa."""
        del self.fotos[indice]
        self.dibujar_miniaturas(self.fotos)

    # ---------- Guardar, limpiar y editar ----------

    def guardar(self):
        """Registra a la persona nueva o guarda los cambios de la que se edita."""
        datos = self.leer_formulario()
        if not datos["consentimiento"]:
            messagebox.showwarning("FaceScan", "Falta marcar la casilla de autorización de la persona.")
            return
        if self.id_editando is not None:
            id_persona = self.id_editando
            self.ejecutar(lambda: base_datos.actualizar_persona(id_persona, datos),
                          "Guardando cambios…", lambda _: self.al_guardar("Datos actualizados."))
            return
        if not self.fotos:
            messagebox.showwarning("FaceScan", "Agrega al menos una foto del rostro.")
            return
        if any(foto["embedding"] is None for foto in self.fotos):
            messagebox.showwarning("FaceScan", "Hay fotos marcadas en rojo (sin rostro, con varios "
                                   "rostros o dañadas). Quítalas con \"✕ Quitar\" antes de guardar.")
            return
        fotos = [(foto["ruta"], foto["embedding"]) for foto in self.fotos]
        self.ejecutar(lambda: base_datos.registrar_persona(datos, fotos),
                      "Guardando persona…", lambda _: self.al_guardar("Persona registrada."))

    def al_guardar(self, mensaje):
        """Avisa que se guardó y deja el formulario limpio."""
        messagebox.showinfo("FaceScan", mensaje)
        self.limpiar()

    def limpiar(self):
        """Deja el formulario vacío y en modo de persona nueva."""
        self.id_editando = None
        self.llenar_formulario()
        self.fotos = []
        self.dibujar_miniaturas(self.fotos)
        for archivo in self.carpeta_temporal.iterdir():  # fotos de cámara ya guardadas o descartadas
            archivo.unlink(missing_ok=True)
        self.actualizar_botones(self.ocupado, editando=False)

    def editar(self):
        """Lee de la base (en segundo plano) los datos de la persona elegida."""
        id_persona = self.id_seleccionado()
        if id_persona is not None:
            self.ejecutar(lambda: base_datos.obtener_persona(id_persona),
                          "Cargando datos…", self.al_editar)

    def al_editar(self, persona):
        """Carga en el formulario los datos leídos para editarlos."""
        if persona is None:
            messagebox.showinfo("FaceScan", "Esa persona ya no existe.")
            return
        self.limpiar()
        self.id_editando = persona["id"]
        self.llenar_formulario(persona)
        self.actualizar_botones(self.ocupado, editando=True)

    # ---------- Acciones sobre la lista ----------

    def agregar_fotos(self):
        """Agrega fotos a la persona elegida en la lista."""
        id_persona = self.id_seleccionado()
        if id_persona is None:
            return
        rutas = filedialog.askopenfilenames(title="Fotos para agregar",
                                            filetypes=interfaz.TIPOS_IMAGEN)
        if rutas:
            self.ejecutar(lambda: agregar_fotos_a_persona(id_persona, rutas),
                          "Agregando fotos…", self.al_agregar_fotos)

    def al_agregar_fotos(self, resultado):
        """Muestra cuántas fotos se agregaron y cuáles no."""
        agregadas, problemas = resultado
        mensaje = f"Se agregaron {agregadas} foto(s)."
        if problemas:
            mensaje += "\n\nNo se agregaron:\n• " + "\n• ".join(problemas)
        messagebox.showinfo("FaceScan", mensaje)

    def eliminar(self):
        """Elimina a la persona elegida, previa confirmación."""
        id_persona = self.id_seleccionado()
        if id_persona is None:
            return
        nombre = self.lista.set(str(id_persona), "nombre_completo")
        if not messagebox.askyesno("Confirmar", f"¿Eliminar a {nombre} con todas sus fotos y "
                                   "vectores?\nEsta acción no se puede deshacer."):
            return
        self.ejecutar(lambda: base_datos.eliminar_persona(id_persona), "Eliminando…",
                      lambda _: self.al_eliminar(id_persona, nombre))

    def al_eliminar(self, id_persona, nombre):
        """Avisa que se eliminó y limpia el formulario si se estaba editando."""
        if self.id_editando == id_persona:
            self.limpiar()
        messagebox.showinfo("FaceScan", f"Se eliminó a {nombre}.")

    def refrescar_lista(self, avisar=False):
        """Vuelve a leer las personas de la base en segundo plano y llena la tabla."""
        interfaz.en_segundo_plano(self.ventana, base_datos.listar_personas,
                                  lambda personas, error: self.al_listar(personas, error, avisar))

    def al_listar(self, personas, error, avisar):
        """Llena la tabla con las personas leídas, o avisa que no hay conexión."""
        if error:
            self.var_estado.set("Sin conexión con la base de datos.")
            if avisar:
                self.mostrar_error(error)
            return
        if not self.ocupado:
            self.var_estado.set("Listo.")
        self.llenar_lista(personas)

    def cerrar(self):
        """Borra las fotos temporales de la cámara y cierra la ventana."""
        if self.ocupado:
            messagebox.showinfo("FaceScan", "Espera a que termine la operación en curso.")
            return
        shutil.rmtree(self.carpeta_temporal, ignore_errors=True)
        self.ventana.destroy()


def main():
    """Abre la ventana de registro."""
    interfaz.iniciar_app(AppRegistro, "FaceScan · Registro", "1000x650")


if __name__ == "__main__":
    main()
