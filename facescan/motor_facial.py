"""Detección (YuNet), alineación y embeddings (SFace) y comparación de rostros."""

import functools
import threading
from pathlib import Path

import cv2
import numpy as np

from facescan import config

# YuNet y SFace no son seguros entre hilos: el registro calcula en un hilo aparte.
_candado = threading.Lock()


class ErrorMotorFacial(Exception):
    """Error con un mensaje en español listo para mostrar al usuario."""


@functools.cache
def cargar_modelos():
    """Crea el detector y el reconocedor una sola vez y los reutiliza."""
    for ruta in (config.RUTA_DETECTOR, config.RUTA_RECONOCEDOR):
        if not ruta.exists():
            raise ErrorMotorFacial(f"Falta el modelo {ruta.name}. "
                                   "Ejecuta python scripts\\descargar_modelos.py")
    # Oculta avisos internos de OpenCV 5 que no afectan el resultado.
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    detector = cv2.FaceDetectorYN.create(
        str(config.RUTA_DETECTOR), "", (320, 320), config.UMBRAL_DETECCION
    )
    reconocedor = cv2.FaceRecognizerSF.create(str(config.RUTA_RECONOCEDOR), "")
    return detector, reconocedor


def leer_imagen(ruta):
    """Lee una imagen del disco (acepta tildes y espacios) y la reduce si es muy grande."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ErrorMotorFacial(f"No existe el archivo {ruta.name}.")
    # cv2.imread falla con rutas con tildes en Windows; np.fromfile no.
    imagen = cv2.imdecode(np.fromfile(ruta, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        raise ErrorMotorFacial(f"{ruta.name} no es una imagen válida o está dañada.")
    alto, ancho = imagen.shape[:2]
    escala = config.LADO_MAXIMO_IMAGEN / max(alto, ancho)
    if escala < 1:
        imagen = cv2.resize(imagen, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    return imagen


def detectar_rostros(imagen_bgr):
    """Devuelve los rostros de la imagen, del más grande al más pequeño."""
    detector, _ = cargar_modelos()
    alto, ancho = imagen_bgr.shape[:2]
    with _candado:
        detector.setInputSize((ancho, alto))
        _, filas = detector.detect(imagen_bgr)
    if filas is None:
        return []
    # Cada fila de YuNet: x, y, w, h, 5 puntos (x, y) y la confianza.
    rostros = [{
        "caja": tuple(int(v) for v in fila[0:4]),
        "puntos": [(int(fila[i]), int(fila[i + 1])) for i in range(4, 14, 2)],
        "confianza": float(fila[14]),
        "fila": fila,
    } for fila in filas]
    return sorted(rostros, key=lambda r: r["caja"][2] * r["caja"][3], reverse=True)


def extraer_embedding(imagen_bgr, rostro):
    """Alinea el rostro con sus 5 puntos y devuelve su vector SFace normalizado."""
    _, reconocedor = cargar_modelos()
    with _candado:
        recorte = reconocedor.alignCrop(imagen_bgr, rostro["fila"])
        vector = reconocedor.feature(recorte).reshape(-1).astype(np.float32)
    return vector / np.linalg.norm(vector)


def embedding_de_foto(ruta):
    """Devuelve el embedding de una foto que debe tener exactamente un rostro."""
    imagen = leer_imagen(ruta)
    rostros = detectar_rostros(imagen)
    nombre = Path(ruta).name
    if not rostros:
        raise ErrorMotorFacial(f"No se encontró ningún rostro en {nombre}. "
                               "Usa una foto de frente y con buena luz.")
    if len(rostros) > 1:
        raise ErrorMotorFacial(f"Se encontraron {len(rostros)} rostros en {nombre}; "
                               "la foto debe tener solo a la persona que se registra.")
    return extraer_embedding(imagen, rostros[0])


def identificar(embedding, ids, matriz, umbral=None):
    """Devuelve (id_persona o None, similitud) del vector más parecido de la matriz."""
    if len(ids) == 0:
        return None, 0.0
    umbral = config.UMBRAL_COSENO if umbral is None else umbral
    # Con vectores normalizados, la similitud coseno es el producto punto.
    similitudes = matriz @ embedding
    mejor = int(np.argmax(similitudes))
    similitud = float(similitudes[mejor])
    return (ids[mejor] if similitud >= umbral else None), similitud
