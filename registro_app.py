"""Programa 1: registro de personas con sus fotos."""

import shutil
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np

from facescan import base_datos, config, interfaz, motor_facial
from facescan.base_datos import ErrorBaseDatos
from facescan.interfaz import ErrorCamara
from facescan.motor_facial import ErrorMotorFacial

CARRERAS = ["Ingeniería de Sistemas", "Ingeniería de Software", "Administración",
            "Contaduría", "Psicología", "Otra"]
TIPOS_IMAGEN = [("Imágenes", "*.jpg *.jpeg *.png"), ("Todos los archivos", "*.*")]
LADO_MINIATURA = 105
COLUMNAS = {"nombre_completo": ("Nombre", 165), "edad": ("Edad", 45),
            "carrera": ("Carrera", 150), "semestre": ("Sem.", 45), "num_fotos": ("Fotos", 45)}
ERRORES_CONOCIDOS = (ErrorBaseDatos, ErrorMotorFacial, ErrorCamara)


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


class AppRegistro:
    """Ventana principal del programa de registro."""

    def __init__(self, ventana):
        self.ventana = ventana
        self.fotos = []
        self.id_editando = None
        self.ocupado = False
        self.carpeta_temporal = Path(tempfile.mkdtemp(prefix="facescan_"))
        self.construir_interfaz()
        self.refrescar_lista(avisar=True)
        ventana.protocol("WM_DELETE_WINDOW", self.cerrar)

    # ---------- Construcción de la interfaz ----------

    def construir_interfaz(self):
        """Arma las dos columnas de la ventana y la barra de estado."""
        izquierda = ttk.Frame(self.ventana, padding=10, width=510)
        derecha = ttk.Frame(self.ventana, padding=10)
        izquierda.pack(side="left", fill="y")
        izquierda.pack_propagate(False)  # ancho fijo: la tabla no se mueve al agregar fotos
        derecha.pack(side="left", fill="both", expand=True)
        self.construir_formulario(izquierda)
        self.construir_fotos(izquierda)
        self.construir_lista(derecha)
        self.var_estado = tk.StringVar(value="Listo.")
        ttk.Label(izquierda, textvariable=self.var_estado, foreground="gray").pack(anchor="w")

    def construir_formulario(self, padre):
        """Crea los campos de la persona, la casilla y los botones."""
        self.var_titulo = tk.StringVar(value="Nueva persona")
        ttk.Label(padre, textvariable=self.var_titulo, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        marco = ttk.Frame(padre)
        marco.pack(fill="x", pady=6)
        self.var_nombre, self.var_codigo = tk.StringVar(), tk.StringVar()
        self.var_edad, self.var_semestre = tk.StringVar(value="18"), tk.StringVar(value="1")
        self.var_carrera = tk.StringVar(value=CARRERAS[0])
        self.var_consentimiento = tk.BooleanVar()
        campos = [
            ("Nombre completo", ttk.Entry(marco, textvariable=self.var_nombre, width=40)),
            ("Edad", ttk.Spinbox(marco, from_=10, to=100, textvariable=self.var_edad, width=6)),
            ("Carrera", ttk.Combobox(marco, values=CARRERAS, textvariable=self.var_carrera, width=37)),
            ("Semestre", ttk.Spinbox(marco, from_=1, to=10, textvariable=self.var_semestre, width=6)),
            ("Código estudiantil (opcional)", ttk.Entry(marco, textvariable=self.var_codigo, width=20)),
        ]
        for fila, (texto, campo) in enumerate(campos):
            ttk.Label(marco, text=texto).grid(row=fila, column=0, sticky="w", pady=3, padx=(0, 8))
            campo.grid(row=fila, column=1, sticky="w")
        ttk.Checkbutton(padre, variable=self.var_consentimiento,
                        text="La persona autoriza el uso de su rostro para este proyecto académico"
                        ).pack(anchor="w", pady=4)
        botones = ttk.Frame(padre)
        botones.pack(fill="x", pady=4)
        self.botones_foto = [
            ttk.Button(botones, text="Cargar foto(s)", command=self.cargar_fotos),
            ttk.Button(botones, text="Tomar foto con cámara", command=self.tomar_foto),
        ]
        self.boton_guardar = ttk.Button(botones, text="Guardar persona", command=self.guardar)
        self.botones_accion = [self.boton_guardar,
                               ttk.Button(botones, text="Limpiar", command=self.limpiar)]
        for boton in self.botones_foto + self.botones_accion:
            boton.pack(side="left", padx=(0, 6))

    def construir_fotos(self, padre):
        """Crea la zona donde se ven las miniaturas."""
        ttk.Label(padre, text=f"Fotos (1 a {config.MAX_FOTOS_POR_PERSONA}, verde = válida)").pack(anchor="w")
        self.marco_fotos = ttk.Frame(padre, height=2 * LADO_MINIATURA + 60)
        self.marco_fotos.pack(fill="x", pady=4)

    def construir_lista(self, padre):
        """Crea la tabla de personas registradas y sus botones."""
        ttk.Label(padre, text="Personas registradas", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.lista = ttk.Treeview(padre, columns=list(COLUMNAS), show="headings", selectmode="browse")
        for columna, (titulo, ancho) in COLUMNAS.items():
            self.lista.heading(columna, text=titulo)
            self.lista.column(columna, width=ancho, anchor="w" if ancho > 60 else "center")
        self.lista.pack(fill="both", expand=True, pady=6)
        botones = ttk.Frame(padre)
        botones.pack(fill="x")
        for texto, accion in [("Editar", self.editar), ("Agregar fotos", self.agregar_fotos),
                              ("Eliminar", self.eliminar), ("Actualizar lista", self.refrescar_lista)]:
            boton = ttk.Button(botones, text=texto, command=accion)
            boton.pack(side="left", padx=(0, 6))
            self.botones_accion.append(boton)

    def dibujar_miniaturas(self):
        """Vuelve a pintar las miniaturas: verde si es válida, rojo si no."""
        for hijo in self.marco_fotos.winfo_children():
            hijo.destroy()
        for indice, foto in enumerate(self.fotos):
            valida = foto["embedding"] is not None
            color = interfaz.VERDE if valida else interfaz.ROJO
            celda = tk.Frame(self.marco_fotos, bg="#%02x%02x%02x" % color[::-1], padx=3, pady=3)
            celda.grid(row=indice // 4, column=indice % 4, padx=4, pady=4)
            imagen = foto["imagen"]
            if imagen is None:
                imagen = np.full((LADO_MINIATURA, LADO_MINIATURA, 3), 200, dtype=np.uint8)
            marcas = [(r["caja"], color, None) for r in foto["rostros"]]
            grosor = max(2, max(imagen.shape[:2]) // 40)  # visible aun después de reducir
            miniatura = interfaz.imagen_a_tk(interfaz.dibujar_rostros(imagen, marcas, grosor),
                                             LADO_MINIATURA, LADO_MINIATURA)
            etiqueta = tk.Label(celda, image=miniatura)
            etiqueta.imagen = miniatura  # guardar la referencia evita que Tkinter la borre
            etiqueta.pack()
            tk.Label(celda, text=foto["estado"], bg=celda["bg"], fg="white").pack(fill="x")
            ttk.Button(celda, text="✕ Quitar", command=lambda i=indice: self.quitar_foto(i)).pack(fill="x")

    # ---------- Ayudas ----------

    def leer_formulario(self):
        """Devuelve los datos del formulario como dict."""
        return {"nombre_completo": self.var_nombre.get(), "edad": self.var_edad.get(),
                "carrera": self.var_carrera.get(), "semestre": self.var_semestre.get(),
                "codigo": self.var_codigo.get(), "consentimiento": self.var_consentimiento.get()}

    def id_seleccionado(self):
        """Devuelve el id de la persona elegida en la lista, o None."""
        seleccion = self.lista.selection()
        if not seleccion:
            messagebox.showinfo("FaceScan", "Primero selecciona una persona de la lista.")
            return None
        return int(seleccion[0])

    def actualizar_botones(self):
        """Activa o desactiva botones según si hay trabajo en curso o se edita."""
        normal = "disabled" if self.ocupado else "normal"
        for boton in self.botones_accion:
            boton.configure(state=normal)
        fotos = "disabled" if self.ocupado or self.id_editando is not None else "normal"
        for boton in self.botones_foto:
            boton.configure(state=fotos)

    def mostrar_error(self, error):
        """Muestra el error en un messagebox, con su mensaje tal como viene."""
        if isinstance(error, ERRORES_CONOCIDOS):
            messagebox.showerror("FaceScan", str(error))
        else:
            messagebox.showerror("FaceScan", f"Ocurrió un error inesperado:\n{error}")

    def ejecutar(self, tarea, texto, al_exito):
        """Corre tarea() en segundo plano y luego al_exito(resultado), o muestra el error."""
        self.ocupado = True
        self.var_estado.set(texto)
        self.ventana.configure(cursor="watch")
        self.actualizar_botones()

        def al_terminar(resultado, error):
            self.ocupado = False
            self.var_estado.set("Listo.")
            self.ventana.configure(cursor="")
            self.actualizar_botones()
            if error:
                self.mostrar_error(error)
            else:
                al_exito(resultado)
            self.refrescar_lista()

        interfaz.en_segundo_plano(self.ventana, tarea, al_terminar)

    # ---------- Acciones de los botones ----------

    def cargar_fotos(self):
        """Elige fotos del disco y las analiza."""
        rutas = filedialog.askopenfilenames(title="Elegir fotos", filetypes=TIPOS_IMAGEN)
        self.agregar_a_vista(rutas)

    def tomar_foto(self):
        """Abre la cámara para capturar una foto."""
        interfaz.ventana_captura(self.ventana, self.carpeta_temporal,
                                 al_capturar=lambda ruta: self.agregar_a_vista([ruta]))

    def agregar_a_vista(self, rutas):
        """Analiza las fotos en segundo plano respetando el máximo por persona."""
        espacio = config.MAX_FOTOS_POR_PERSONA - len(self.fotos)
        if rutas and len(rutas) > espacio:
            messagebox.showwarning("FaceScan", f"Máximo {config.MAX_FOTOS_POR_PERSONA} fotos por "
                                   f"persona: solo se agregarán {max(espacio, 0)}.")
            rutas = rutas[:max(espacio, 0)]
        if rutas:
            self.ejecutar(lambda: [analizar_foto(ruta) for ruta in rutas],
                          "Analizando fotos…", self.al_analizar)

    def al_analizar(self, fotos):
        """Agrega las fotos analizadas a la vista previa."""
        self.fotos.extend(fotos)
        self.dibujar_miniaturas()

    def quitar_foto(self, indice):
        """Quita una foto de la vista previa."""
        del self.fotos[indice]
        self.dibujar_miniaturas()

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
        for variable, valor in [(self.var_nombre, ""), (self.var_codigo, ""), (self.var_edad, "18"),
                                (self.var_semestre, "1"), (self.var_carrera, CARRERAS[0]),
                                (self.var_consentimiento, False), (self.var_titulo, "Nueva persona")]:
            variable.set(valor)
        self.id_editando = None
        self.boton_guardar.configure(text="Guardar persona")
        self.fotos = []
        self.dibujar_miniaturas()
        for archivo in self.carpeta_temporal.iterdir():  # fotos de cámara ya guardadas o descartadas
            archivo.unlink(missing_ok=True)
        self.actualizar_botones()

    def editar(self):
        """Carga en el formulario los datos de la persona elegida."""
        id_persona = self.id_seleccionado()
        if id_persona is None:
            return
        try:
            persona = base_datos.obtener_persona(id_persona)
        except ErrorBaseDatos as error:
            self.mostrar_error(error)
            return
        if persona is None:
            messagebox.showinfo("FaceScan", "Esa persona ya no existe.")
            self.refrescar_lista()
            return
        self.limpiar()
        for variable, campo in [(self.var_nombre, "nombre_completo"), (self.var_edad, "edad"),
                                (self.var_carrera, "carrera"), (self.var_semestre, "semestre"),
                                (self.var_consentimiento, "consentimiento")]:
            variable.set(persona[campo])
        self.var_codigo.set(persona["codigo"] or "")
        self.id_editando = id_persona
        self.var_titulo.set(f"Editando: {persona['nombre_completo']}")
        self.boton_guardar.configure(text="Guardar cambios")
        self.actualizar_botones()

    def agregar_fotos(self):
        """Agrega fotos a la persona elegida en la lista."""
        id_persona = self.id_seleccionado()
        if id_persona is None:
            return
        rutas = filedialog.askopenfilenames(title="Fotos para agregar", filetypes=TIPOS_IMAGEN)
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
        """Vuelve a leer las personas de la base y llena la tabla."""
        try:
            personas = base_datos.listar_personas()
        except ErrorBaseDatos as error:
            self.var_estado.set("Sin conexión con la base de datos.")
            if avisar:
                self.mostrar_error(error)
            return
        self.lista.delete(*self.lista.get_children())
        for persona in personas:
            self.lista.insert("", "end", iid=str(persona["id"]),
                              values=[persona[columna] for columna in COLUMNAS])

    def cerrar(self):
        """Borra las fotos temporales de la cámara y cierra la ventana."""
        if self.ocupado:
            messagebox.showinfo("FaceScan", "Espera a que termine la operación en curso.")
            return
        shutil.rmtree(self.carpeta_temporal, ignore_errors=True)
        self.ventana.destroy()


def main():
    """Abre la ventana de registro."""
    ventana = tk.Tk()
    ventana.title("FaceScan · Registro")
    ventana.geometry("1000x650")
    try:
        motor_facial.cargar_modelos()
    except ErrorMotorFacial as error:
        ventana.withdraw()
        messagebox.showerror("FaceScan", str(error))
        ventana.destroy()
        return
    AppRegistro(ventana)
    ventana.mainloop()


if __name__ == "__main__":
    main()
