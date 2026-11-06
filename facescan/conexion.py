"""Conexión a PostgreSQL, mensajes de error en español y creación del esquema."""

import shutil
from contextlib import contextmanager

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
