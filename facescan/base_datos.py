"""Acceso a PostgreSQL: todo el SQL de FaceScan vive aquí."""

import shutil
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import psycopg
from psycopg import errors, sql
from psycopg.rows import dict_row

from facescan import config

MENSAJES_RESTRICCION = {
    "nombre_no_vacio": "El nombre completo no puede estar vacío.",
    "carrera_no_vacia": "La carrera no puede estar vacía.",
    "edad_valida": "La edad debe estar entre 10 y 100 años.",
    "semestre_valido": "El semestre debe estar entre 1 y 10.",
    "consentimiento_obligatorio": "Sin consentimiento no se puede registrar a la persona.",
    "codigo_unico": "Ya hay una persona registrada con ese código estudiantil.",
    "embedding_de_128": "El vector del rostro no tiene 128 valores.",
}


class ErrorBaseDatos(Exception):
    """Error con un mensaje en español listo para mostrar al usuario."""


# ---------- Conexión ----------

def _mensaje_conexion(error):
    """Traduce un fallo de conexión de PostgreSQL a un mensaje claro."""
    texto = str(error).lower()
    if "password" in texto and not (config.RAIZ / ".env").exists():
        return ("No existe el archivo .env. Copia .env.ejemplo como .env y escribe "
                "la contraseña de PostgreSQL en FACESCAN_DB_PASSWORD.")
    if "password" in texto:
        return ("PostgreSQL rechazó la contraseña. Revisa FACESCAN_DB_USER y "
                "FACESCAN_DB_PASSWORD en el archivo .env.")
    if "no existe" in texto or "does not exist" in texto:
        return (f"La base de datos '{config.BD_NOMBRE}' no existe. "
                "Ejecuta: python scripts\\crear_bd.py")
    return (f"No se pudo conectar a PostgreSQL en {config.BD_HOST}:{config.BD_PUERTO}. "
            "¿Está encendido el servicio de PostgreSQL?")


def _mensaje_restriccion(error):
    """Traduce una violación de CHECK, UNIQUE o clave foránea a un mensaje claro."""
    if isinstance(error, errors.ForeignKeyViolation):
        return "La persona ya no existe en la base de datos."
    nombre = error.diag.constraint_name
    return MENSAJES_RESTRICCION.get(nombre, f"Dato no válido ({nombre}).")


@contextmanager
def conectar(nombre_bd=None, autocommit=False):
    """Abre una conexión: confirma al salir, deshace todo si hubo un error."""
    try:
        conexion = psycopg.connect(
            host=config.BD_HOST, port=config.BD_PUERTO,
            dbname=nombre_bd or config.BD_NOMBRE,
            user=config.BD_USUARIO, password=config.BD_CLAVE,
            connect_timeout=config.BD_TIEMPO_ESPERA,
            autocommit=autocommit, row_factory=dict_row,
        )
    except psycopg.OperationalError as error:
        raise ErrorBaseDatos(_mensaje_conexion(error)) from None
    try:
        with conexion:
            yield conexion
    except errors.IntegrityError as error:
        raise ErrorBaseDatos(_mensaje_restriccion(error)) from None
    except errors.UndefinedTable:
        raise ErrorBaseDatos(f"La base '{nombre_bd or config.BD_NOMBRE}' no tiene las tablas. "
                             "Ejecuta: python scripts\\crear_bd.py") from None
    except psycopg.OperationalError:
        raise ErrorBaseDatos("Se perdió la conexión con PostgreSQL.") from None
    except psycopg.Error as error:
        raise ErrorBaseDatos(f"Error de PostgreSQL: {error}") from None


def crear_base(nombre_bd):
    """Crea la base de datos indicada si todavía no existe."""
    with conectar("postgres", autocommit=True) as conexion:
        existe = conexion.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (nombre_bd,)
        ).fetchone()
        if not existe:
            # CREATE DATABASE no acepta %s: el nombre va como identificador seguro.
            conexion.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre_bd)))


def inicializar():
    """Crea las tablas si no existen ejecutando sql/esquema.sql."""
    with conectar() as conexion:
        conexion.execute(config.RUTA_ESQUEMA.read_text(encoding="utf-8"))


def reiniciar():
    """Borra todas las tablas y fotos y vuelve a crear el esquema vacío."""
    with conectar() as conexion:
        conexion.execute("DROP TABLE IF EXISTS fotos, personas, estado CASCADE")
        conexion.execute(config.RUTA_ESQUEMA.read_text(encoding="utf-8"))
    # Solo después de confirmar en la base se vacía la carpeta de fotos.
    if config.CARPETA_FOTOS.exists():
        for elemento in config.CARPETA_FOTOS.iterdir():
            if elemento.is_dir():
                shutil.rmtree(elemento)
            else:
                elemento.unlink()


# ---------- Validaciones ----------

def _validar_persona(datos):
    """Revisa y limpia los datos de una persona antes de enviarlos a la base."""
    nombre = str(datos.get("nombre_completo", "")).strip()
    carrera = str(datos.get("carrera", "")).strip()
    codigo = str(datos.get("codigo") or "").strip() or None
    try:
        edad = int(datos.get("edad"))
        semestre = int(datos.get("semestre"))
    except (TypeError, ValueError):
        raise ErrorBaseDatos("La edad y el semestre deben ser números enteros.") from None
    if not nombre:
        raise ErrorBaseDatos(MENSAJES_RESTRICCION["nombre_no_vacio"])
    if not carrera:
        raise ErrorBaseDatos(MENSAJES_RESTRICCION["carrera_no_vacia"])
    if not 10 <= edad <= 100:
        raise ErrorBaseDatos(MENSAJES_RESTRICCION["edad_valida"])
    if not 1 <= semestre <= 10:
        raise ErrorBaseDatos(MENSAJES_RESTRICCION["semestre_valido"])
    if datos.get("consentimiento") is not True:
        raise ErrorBaseDatos(MENSAJES_RESTRICCION["consentimiento_obligatorio"])
    return {"nombre_completo": nombre, "edad": edad, "carrera": carrera,
            "semestre": semestre, "codigo": codigo, "consentimiento": True}


def _validar_embedding(embedding):
    """Convierte el embedding a lista de 128 floats o lanza un error."""
    vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
    if vector.size != config.DIMENSION_EMBEDDING:
        raise ErrorBaseDatos(MENSAJES_RESTRICCION["embedding_de_128"])
    return vector.tolist()


# ---------- Ayudantes de escritura ----------

def _incrementar_version(conexion):
    """Sube estado.version para avisar al escáner que hubo cambios."""
    conexion.execute("UPDATE estado SET version = version + 1 WHERE id = 1")


def _siguiente_destino(carpeta, ruta_origen):
    """Devuelve la primera ruta libre 1.jpg, 2.jpg... dentro de la carpeta."""
    extension = Path(ruta_origen).suffix.lower() or ".jpg"
    numero = 1
    while any(carpeta.glob(f"{numero}.*")):
        numero += 1
    return carpeta / f"{numero}{extension}"


def _guardar_foto(conexion, id_persona, ruta_origen, destino, embedding):
    """Copia la foto a su destino y la inserta en la tabla fotos."""
    vector = _validar_embedding(embedding)
    try:
        shutil.copyfile(ruta_origen, destino)
    except OSError:
        raise ErrorBaseDatos(f"No se pudo copiar la foto {Path(ruta_origen).name}.") from None
    conexion.execute(
        "INSERT INTO fotos (id_persona, ruta, embedding) VALUES (%s, %s, %s)",
        (id_persona, destino.relative_to(config.RAIZ).as_posix(), vector),
    )


# ---------- Funciones públicas ----------

def registrar_persona(datos, fotos):
    """Registra una persona con sus fotos [(ruta, embedding), ...] y devuelve su id."""
    persona = _validar_persona(datos)
    if not 1 <= len(fotos) <= config.MAX_FOTOS_POR_PERSONA:
        raise ErrorBaseDatos(f"Se necesitan entre 1 y {config.MAX_FOTOS_POR_PERSONA} fotos.")
    carpeta_creada = None
    try:
        with conectar() as conexion:
            id_persona = conexion.execute(
                """INSERT INTO personas
                       (nombre_completo, edad, carrera, semestre, codigo, consentimiento)
                   VALUES (%(nombre_completo)s, %(edad)s, %(carrera)s, %(semestre)s,
                           %(codigo)s, %(consentimiento)s)
                   RETURNING id""",
                persona,
            ).fetchone()["id"]
            carpeta = config.CARPETA_FOTOS / str(id_persona)
            if carpeta.exists():
                raise ErrorBaseDatos(f"Ya existe la carpeta {carpeta.name} de una base anterior; "
                                     "bórrala o muévela antes de registrar.")
            carpeta.mkdir(parents=True)
            carpeta_creada = carpeta
            for ruta, embedding in fotos:
                destino = _siguiente_destino(carpeta, ruta)
                _guardar_foto(conexion, id_persona, ruta, destino, embedding)
            _incrementar_version(conexion)
    except Exception:
        # La transacción ya se deshizo; se borran las fotos que alcanzaron a copiarse.
        if carpeta_creada:
            shutil.rmtree(carpeta_creada, ignore_errors=True)
        raise
    return id_persona


def agregar_foto(id_persona, ruta_foto, embedding):
    """Agrega una foto más a una persona ya registrada."""
    destino = None
    try:
        with conectar() as conexion:
            # FOR UPDATE bloquea a la persona para que dos programas no superen el máximo.
            existe = conexion.execute(
                "SELECT 1 FROM personas WHERE id = %s FOR UPDATE", (id_persona,)
            ).fetchone()
            if not existe:
                raise ErrorBaseDatos("La persona ya no existe en la base de datos.")
            cantidad = conexion.execute(
                "SELECT count(*) AS n FROM fotos WHERE id_persona = %s", (id_persona,)
            ).fetchone()["n"]
            if cantidad >= config.MAX_FOTOS_POR_PERSONA:
                raise ErrorBaseDatos(f"Ya tiene el máximo de {config.MAX_FOTOS_POR_PERSONA} fotos.")
            carpeta = config.CARPETA_FOTOS / str(id_persona)
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = _siguiente_destino(carpeta, ruta_foto)
            _guardar_foto(conexion, id_persona, ruta_foto, destino, embedding)
            _incrementar_version(conexion)
    except Exception:
        if destino:
            destino.unlink(missing_ok=True)
        raise


def listar_personas():
    """Devuelve todas las personas ordenadas por nombre, con su número de fotos y la primera."""
    with conectar() as conexion:
        personas = conexion.execute(
            """SELECT p.id, p.nombre_completo, p.edad, p.carrera, p.semestre, p.codigo,
                      p.fecha_registro, count(f.id) AS num_fotos,
                      (SELECT ruta FROM fotos WHERE id_persona = p.id
                       ORDER BY id LIMIT 1) AS primera_foto
               FROM personas p LEFT JOIN fotos f ON f.id_persona = p.id
               GROUP BY p.id
               ORDER BY p.nombre_completo"""
        ).fetchall()
    for persona in personas:
        if persona["primera_foto"]:
            persona["primera_foto"] = config.RAIZ / persona["primera_foto"]
    return personas


def obtener_persona(id_persona):
    """Devuelve la ficha de una persona con las rutas de sus fotos, o None."""
    with conectar() as conexion:
        persona = conexion.execute(
            "SELECT * FROM personas WHERE id = %s", (id_persona,)
        ).fetchone()
        if persona is None:
            return None
        filas = conexion.execute(
            "SELECT ruta FROM fotos WHERE id_persona = %s ORDER BY id", (id_persona,)
        ).fetchall()
    persona["fotos"] = [config.RAIZ / fila["ruta"] for fila in filas]
    return persona


def actualizar_persona(id_persona, datos):
    """Actualiza los datos de la ficha de una persona."""
    persona = _validar_persona(datos)
    with conectar() as conexion:
        cursor = conexion.execute(
            """UPDATE personas
               SET nombre_completo = %(nombre_completo)s, edad = %(edad)s,
                   carrera = %(carrera)s, semestre = %(semestre)s, codigo = %(codigo)s
               WHERE id = %(id)s""",
            {**persona, "id": id_persona},
        )
        if cursor.rowcount == 0:
            raise ErrorBaseDatos("La persona ya no existe en la base de datos.")
        _incrementar_version(conexion)


def eliminar_persona(id_persona):
    """Elimina a una persona con sus fotos y vectores (en la base y en el disco)."""
    with conectar() as conexion:
        cursor = conexion.execute("DELETE FROM personas WHERE id = %s", (id_persona,))
        if cursor.rowcount == 0:
            raise ErrorBaseDatos("La persona ya no existe en la base de datos.")
        _incrementar_version(conexion)
    # Solo después de confirmar el borrado en la base se borran los archivos.
    shutil.rmtree(config.CARPETA_FOTOS / str(id_persona), ignore_errors=True)


def cargar_embeddings():
    """Devuelve (lista de id_persona, matriz N x 128) con todos los vectores."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT id_persona, embedding FROM fotos ORDER BY id"
        ).fetchall()
    ids = [fila["id_persona"] for fila in filas]
    if not filas:
        return ids, np.empty((0, config.DIMENSION_EMBEDDING), dtype=np.float32)
    return ids, np.array([fila["embedding"] for fila in filas], dtype=np.float32)


def version_datos():
    """Devuelve el número de versión que cambia con cada registro, edición o borrado."""
    with conectar() as conexion:
        return conexion.execute("SELECT version FROM estado WHERE id = 1").fetchone()["version"]
