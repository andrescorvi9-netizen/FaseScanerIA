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

# --- Cámara y escáner ---
INDICE_CAMARA = 0
BACKEND_CAMARA = "MSMF"          # "MSMF" o "DSHOW"; si falla, se prueba el otro
BRILLO_MINIMO_CAMARA = 25        # al arrancar se descartan cuadros más oscuros (0-255)...
SEGUNDOS_ARRANQUE_CAMARA = 4.0   # ...durante como máximo estos segundos (MSMF tarda unos 3)
CUADROS_ENTRE_ANALISIS = 3       # el escáner calcula embeddings 1 de cada 3 cuadros
ANALISIS_PARA_CAMBIAR_FICHA = 3  # resultados iguales seguidos antes de cambiar la ficha
MS_ENTRE_CONSULTAS_BD = 2000     # cada cuánto el escáner revisa estado.version
UMBRAL_MINIMO, UMBRAL_MAXIMO = 0.25, 0.60  # rango del control de umbral en vivo

# --- PostgreSQL (los valores reales se leen de .env) ---
load_dotenv(RAIZ / ".env")

BD_HOST = os.getenv("FACESCAN_DB_HOST") or "localhost"
BD_PUERTO = int(os.getenv("FACESCAN_DB_PORT") or 5432)
BD_NOMBRE = os.getenv("FACESCAN_DB_NAME") or "facescan"
BD_USUARIO = os.getenv("FACESCAN_DB_USER") or "postgres"
BD_CLAVE = os.getenv("FACESCAN_DB_PASSWORD") or ""
BD_NOMBRE_PRUEBAS = "facescan_test"
BD_TIEMPO_ESPERA = 3     # segundos antes de rendirse si PostgreSQL no responde
