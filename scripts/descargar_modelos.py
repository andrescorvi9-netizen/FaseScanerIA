"""Descarga los modelos ONNX de YuNet y SFace desde el repositorio oficial opencv_zoo."""

import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from facescan import config  # noqa: E402

URL_BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
MODELOS = {
    config.RUTA_DETECTOR: f"{URL_BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    config.RUTA_RECONOCEDOR: f"{URL_BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
TAMANO_BLOQUE = 64 * 1024


def mostrar_progreso(nombre, bajado, total):
    """Imprime en la misma línea cuánto se lleva descargado."""
    megas = bajado / 1_048_576
    if total:
        print(f"\r  {nombre}: {bajado * 100 // total:3d} % ({megas:.1f} MB)", end="", flush=True)
    else:
        print(f"\r  {nombre}: {megas:.1f} MB", end="", flush=True)


def descargar(url, destino):
    """Descarga url en destino usando un archivo .part temporal."""
    temporal = destino.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=30) as respuesta, open(temporal, "wb") as archivo:
        total = int(respuesta.headers.get("Content-Length") or 0)
        bajado = 0
        while bloque := respuesta.read(TAMANO_BLOQUE):
            archivo.write(bloque)
            bajado += len(bloque)
            mostrar_progreso(destino.name, bajado, total)
    temporal.replace(destino)
    print()


def main():
    """Descarga los modelos que falten en la carpeta modelos/."""
    config.CARPETA_MODELOS.mkdir(exist_ok=True)
    for destino, url in MODELOS.items():
        if destino.exists():
            print(f"  {destino.name}: ya existe, no se descarga.")
            continue
        try:
            descargar(url, destino)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            destino.with_suffix(".part").unlink(missing_ok=True)
            print(f"\nNo se pudo descargar {destino.name}.")
            print("Revisa tu conexión a internet e inténtalo de nuevo.")
            print(f"Detalle: {error}")
            sys.exit(1)
    print("Modelos listos en la carpeta modelos/.")


if __name__ == "__main__":
    main()
