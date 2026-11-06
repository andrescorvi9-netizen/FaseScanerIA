"""Configuración de FaceScan: rutas, umbrales, cámara y conexión a PostgreSQL."""

import os
from pathlib import Path

from dotenv import load_dotenv

# --- Rutas (todas relativas a la carpeta del proyecto) ---
RAIZ = Path(__file__).resolve().parent.parent
CARPETA_MODELOS = RAIZ / "modelos"
CARPETA_DATOS = RAIZ / "datos"
CARPETA_FOTOS = CARPETA_DATOS / "fotos"
RUTA_ESQUEMA = RAIZ / "sql" / "esquema.sql"

RUTA_DETECTOR = CARPETA_MODELOS / "face_detection_yunet_2023mar.onnx"
RUTA_RECONOCEDOR = CARPETA_MODELOS / "face_recognition_sface_2021dec.onnx"

# --- Reconocimiento ---
UMBRAL_DETECCION = 0.8   # confianza mínima de YuNet para aceptar un rostro
UMBRAL_COSENO = 0.363    # similitud mínima de SFace recomendada por OpenCV
LADO_MAXIMO_IMAGEN = 1280  # las fotos más grandes se reducen antes de detectar
MAX_FOTOS_POR_PERSONA = 5
DIMENSION_EMBEDDING = 128  # tamaño del vector que produce SFace

# --- Cámara ---
INDICE_CAMARA = 0

# --- PostgreSQL (los valores reales se leen de .env) ---
load_dotenv(RAIZ / ".env")

BD_HOST = os.getenv("FACESCAN_DB_HOST") or "localhost"
BD_PUERTO = int(os.getenv("FACESCAN_DB_PORT") or 5432)
BD_NOMBRE = os.getenv("FACESCAN_DB_NAME") or "facescan"
BD_USUARIO = os.getenv("FACESCAN_DB_USER") or "postgres"
BD_CLAVE = os.getenv("FACESCAN_DB_PASSWORD") or ""
BD_NOMBRE_PRUEBAS = "facescan_test"
BD_TIEMPO_ESPERA = 3     # segundos antes de rendirse si PostgreSQL no responde
