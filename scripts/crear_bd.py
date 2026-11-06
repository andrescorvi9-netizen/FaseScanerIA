"""Crea la base de datos de FaceScan si no existe y ejecuta sql/esquema.sql."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from facescan import base_datos, config  # noqa: E402


def main():
    """Crea la base indicada en .env y sus tablas."""
    try:
        base_datos.crear_base(config.BD_NOMBRE)
        base_datos.inicializar()
    except base_datos.ErrorBaseDatos as error:
        print(f"Error: {error}")
        sys.exit(1)
    print(f"Base de datos '{config.BD_NOMBRE}' lista, con las tablas personas, fotos y estado.")


if __name__ == "__main__":
    main()
