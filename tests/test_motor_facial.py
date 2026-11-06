"""Pruebas de facescan/motor_facial.py."""

import cv2
import numpy as np
import pytest

from facescan import config, motor_facial
from facescan.motor_facial import ErrorMotorFacial

hay_modelos = config.RUTA_DETECTOR.exists() and config.RUTA_RECONOCEDOR.exists()
requiere_modelos = pytest.mark.skipif(not hay_modelos, reason="Faltan los modelos .onnx")


def vector_unitario(semilla):
    """Devuelve un vector aleatorio de 128 valores con norma 1."""
    vector = np.random.default_rng(semilla).standard_normal(128).astype(np.float32)
    return vector / np.linalg.norm(vector)


@requiere_modelos
def test_imagen_negra_no_tiene_rostros():
    negra = np.zeros((480, 640, 3), dtype=np.uint8)
    assert motor_facial.detectar_rostros(negra) == []


@requiere_modelos
def test_foto_sin_rostro_en_ruta_con_tildes(tmp_path):
    carpeta = tmp_path / "fotos de prueba ñandú"
    carpeta.mkdir()
    ruta = carpeta / "imagen negra.png"
    ruta.write_bytes(_png_negro())
    with pytest.raises(ErrorMotorFacial, match="ningún rostro"):
        motor_facial.embedding_de_foto(ruta)


def test_foto_dañada(tmp_path):
    ruta = tmp_path / "dañada.jpg"
    ruta.write_bytes(b"esto no es un jpg")
    with pytest.raises(ErrorMotorFacial, match="no es una imagen válida"):
        motor_facial.leer_imagen(ruta)


def test_foto_inexistente(tmp_path):
    with pytest.raises(ErrorMotorFacial, match="No existe"):
        motor_facial.leer_imagen(tmp_path / "no_esta.jpg")


def test_imagen_grande_se_reduce(tmp_path):
    ruta = tmp_path / "grande.png"
    ruta.write_bytes(_png_negro(alto=2000, ancho=3000))
    assert max(motor_facial.leer_imagen(ruta).shape[:2]) == config.LADO_MAXIMO_IMAGEN


def test_faltan_modelos(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RUTA_DETECTOR", tmp_path / "no_esta.onnx")
    motor_facial.cargar_modelos.cache_clear()
    try:
        with pytest.raises(ErrorMotorFacial, match="descargar_modelos.py"):
            motor_facial.cargar_modelos()
    finally:
        motor_facial.cargar_modelos.cache_clear()


def test_identificar_con_matriz_vacia():
    matriz = np.empty((0, 128), dtype=np.float32)
    assert motor_facial.identificar(vector_unitario(1), [], matriz) == (None, 0.0)


def test_identificar_elige_el_mas_parecido():
    ana, luis = vector_unitario(1), vector_unitario(2)
    matriz = np.stack([ana, luis, luis])
    parecido_a_luis = luis + 0.1 * vector_unitario(3)
    parecido_a_luis /= np.linalg.norm(parecido_a_luis)

    id_persona, similitud = motor_facial.identificar(parecido_a_luis, [7, 9, 9], matriz)
    assert id_persona == 9 and similitud > 0.9


def test_identificar_bajo_el_umbral_es_desconocido():
    matriz = np.stack([vector_unitario(1)])
    id_persona, similitud = motor_facial.identificar(vector_unitario(2), [7], matriz)
    assert id_persona is None and similitud < config.UMBRAL_COSENO
    assert motor_facial.identificar(vector_unitario(2), [7], matriz, umbral=-1.0)[0] == 7


def _png_negro(alto=480, ancho=640):
    """Devuelve los bytes de una imagen PNG negra."""
    _, datos = cv2.imencode(".png", np.zeros((alto, ancho, 3), dtype=np.uint8))
    return datos.tobytes()
