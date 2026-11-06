"""Lo que se ve del programa de registro: formulario, miniaturas y tabla de personas."""

import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np

from facescan import config, interfaz
from facescan.conexion import ErrorBaseDatos
from facescan.interfaz import ErrorCamara
from facescan.motor_facial import ErrorMotorFacial

CARRERAS = ["Ingeniería en Sistemas y Computación", "Ingeniería de Software",
            "Administración", "Contaduría", "Psicología", "Otra"]
LADO_MINIATURA = 105
COLUMNAS = {"nombre_completo": ("Nombre", 165), "edad": ("Edad", 45),
            "carrera": ("Carrera", 150), "semestre": ("Sem.", 45), "num_fotos": ("Fotos", 45)}
CAMPOS_FORMULARIO = ["nombre_completo", "edad", "carrera", "semestre", "codigo", "consentimiento"]
VALORES_INICIALES = {"nombre_completo": "", "edad": "18", "carrera": CARRERAS[0],
                     "semestre": "1", "codigo": "", "consentimiento": False}
ERRORES_CONOCIDOS = (ErrorBaseDatos, ErrorMotorFacial, ErrorCamara)


class VentanaRegistro:
    """Arma los widgets del registro; AppRegistro le pone las acciones a los botones."""

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
        self.campos = {clave: tk.StringVar(value=VALORES_INICIALES[clave])
                       for clave in CAMPOS_FORMULARIO[:-1]}
        self.campos["consentimiento"] = tk.BooleanVar(value=False)
        filas = [
            ("Nombre completo", ttk.Entry(marco, textvariable=self.campos["nombre_completo"], width=40)),
            ("Edad", ttk.Spinbox(marco, from_=10, to=100, textvariable=self.campos["edad"], width=6)),
            ("Carrera", ttk.Combobox(marco, values=CARRERAS, textvariable=self.campos["carrera"],
                                     width=37)),
            ("Semestre", ttk.Spinbox(marco, from_=1, to=10, textvariable=self.campos["semestre"],
                                     width=6)),
            ("Código estudiantil (opcional)", ttk.Entry(marco, textvariable=self.campos["codigo"],
                                                        width=20)),
        ]
        for fila, (texto, campo) in enumerate(filas):
            ttk.Label(marco, text=texto).grid(row=fila, column=0, sticky="w", pady=3, padx=(0, 8))
            campo.grid(row=fila, column=1, sticky="w")
        ttk.Checkbutton(padre, variable=self.campos["consentimiento"],
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
        ttk.Label(padre, text=f"Fotos (1 a {config.MAX_FOTOS_POR_PERSONA}, verde = válida)"
                  ).pack(anchor="w")
        self.marco_fotos = ttk.Frame(padre, height=2 * LADO_MINIATURA + 60)
        self.marco_fotos.pack(fill="x", pady=4)

    def construir_lista(self, padre):
        """Crea la tabla de personas registradas y sus botones."""
        ttk.Label(padre, text="Personas registradas", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.lista = ttk.Treeview(padre, columns=list(COLUMNAS), show="headings",
                                  selectmode="browse")
        for columna, (titulo, ancho) in COLUMNAS.items():
            self.lista.heading(columna, text=titulo)
            self.lista.column(columna, width=ancho, anchor="w" if ancho > 60 else "center")
        self.lista.pack(fill="both", expand=True, pady=6)
        botones = ttk.Frame(padre)
        botones.pack(fill="x")
        for texto, accion in [("Editar", self.editar), ("Agregar fotos", self.agregar_fotos),
                              ("Eliminar", self.eliminar),
                              ("Actualizar lista", lambda: self.refrescar_lista(avisar=True))]:
            boton = ttk.Button(botones, text=texto, command=accion)
            boton.pack(side="left", padx=(0, 6))
            self.botones_accion.append(boton)

    def dibujar_miniaturas(self, fotos):
        """Pinta una miniatura por foto: verde si es válida, rojo si no."""
        for hijo in self.marco_fotos.winfo_children():
            hijo.destroy()
        for indice, foto in enumerate(fotos):
            color = interfaz.VERDE if foto["embedding"] is not None else interfaz.ROJO
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
            ttk.Button(celda, text="✕ Quitar",
                       command=lambda i=indice: self.quitar_foto(i)).pack(fill="x")

    def leer_formulario(self):
        """Devuelve los datos del formulario como dict."""
        return {clave: variable.get() for clave, variable in self.campos.items()}

    def llenar_formulario(self, persona=None):
        """Pone en el formulario los datos de la persona, o los valores iniciales."""
        for clave, variable in self.campos.items():
            valor = VALORES_INICIALES[clave] if persona is None else persona[clave]
            variable.set("" if valor is None else valor)
        titulo = "Nueva persona" if persona is None else f"Editando: {persona['nombre_completo']}"
        self.var_titulo.set(titulo)
        self.boton_guardar.configure(text="Guardar persona" if persona is None else "Guardar cambios")

    def llenar_lista(self, personas):
        """Reemplaza las filas de la tabla por las personas indicadas."""
        self.lista.delete(*self.lista.get_children())
        for persona in personas:
            self.lista.insert("", "end", iid=str(persona["id"]),
                              values=[persona[columna] for columna in COLUMNAS])

    def actualizar_botones(self, ocupado, editando):
        """Desactiva todo mientras hay trabajo; las fotos, también al editar."""
        for boton in self.botones_accion:
            boton.configure(state="disabled" if ocupado else "normal")
        for boton in self.botones_foto:
            boton.configure(state="disabled" if ocupado or editando else "normal")

    def id_seleccionado(self):
        """Devuelve el id de la persona elegida en la lista, o None."""
        seleccion = self.lista.selection()
        if not seleccion:
            messagebox.showinfo("FaceScan", "Primero selecciona una persona de la lista.")
            return None
        return int(seleccion[0])

    def mostrar_error(self, error):
        """Muestra el error en un messagebox, con su mensaje tal como viene."""
        if isinstance(error, ERRORES_CONOCIDOS):
            messagebox.showerror("FaceScan", str(error))
        else:
            messagebox.showerror("FaceScan", f"Ocurrió un error inesperado:\n{error}")
