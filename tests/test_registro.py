"""Pruebas de las funciones de registro_app.py que no necesitan abrir ventanas."""

import cv2
import numpy as np
import pytest

from facescan import config
from registro_app import analizar_foto

hay_modelos = config.RUTA_DETECTOR.exists() and config.RUTA_RECONOCEDOR.exists()


@pytest.mark.skipif(not hay_modelos, reason="Faltan los modelos .onnx")
def test_foto_sin_rostro_queda_en_rojo(tmp_path):
    ruta = tmp_path / "negra.png"
    cv2.imencode(".png", np.zeros((200, 200, 3), dtype=np.uint8))[1].tofile(str(ruta))
    foto = analizar_foto(ruta)
    assert foto["estado"] == "Sin rostro" and foto["embedding"] is None


def test_foto_dañada_queda_en_rojo(tmp_path):
    ruta = tmp_path / "dañada.jpg"
    ruta.write_bytes(b"no es imagen")
    foto = analizar_foto(ruta)
    assert foto["estado"] == "No se pudo abrir" and foto["embedding"] is None
