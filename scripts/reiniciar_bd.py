"""Deja la base de FaceScan y la carpeta de fotos vacías, por ejemplo antes de una demo."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from facescan import config, conexion  # noqa: E402


def main():
    """Pide confirmación y reinicia la base y las fotos."""
    print(f"Se borrarán TODAS las personas, fotos y vectores de la base '{config.BD_NOMBRE}'")
    print(f"y todo el contenido de {config.CARPETA_FOTOS.relative_to(config.RAIZ)}.")
    if input('Escribe SI para confirmar: ').strip() != "SI":
        print("Cancelado: no se borró nada.")
        return
    try:
        conexion.reiniciar()
    except conexion.ErrorBaseDatos as error:
        print(f"Error: {error}")
        sys.exit(1)
    print("Listo: base de datos y carpeta de fotos vacías.")


if __name__ == "__main__":
    main()
