"""Pruebas de abrir_camara() con una cámara falsa (no se necesita cámara real)."""

import sys

import cv2
import numpy as np
import pytest

from facescan import config, interfaz
from facescan.interfaz import ErrorCamara

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="MSMF y DSHOW son de Windows")
NEGRO = np.zeros((48, 64, 3), dtype=np.uint8)
IMAGEN = np.full((48, 64, 3), 120, dtype=np.uint8)


def camara_falsa(backends_que_abren, cuadros_negros=0):
    """Devuelve una clase que imita cv2.VideoCapture y anota qué backends se probaron."""
    probados = []

    class CamaraFalsa:
        def __init__(self, indice, api):
            probados.append(api)
            self.abierta = api in backends_que_abren
            self.negros = cuadros_negros

        def isOpened(self):
            return self.abierta

        def read(self):
            if not self.abierta:
                return False, None
            if self.negros > 0:
                self.negros -= 1
                return True, NEGRO
            return True, IMAGEN

        def release(self):
            self.abierta = False

    return CamaraFalsa, probados


@pytest.mark.parametrize("preferido, orden", [
    ("MSMF", [cv2.CAP_MSMF, cv2.CAP_DSHOW]),
    ("dshow", [cv2.CAP_DSHOW, cv2.CAP_MSMF]),
    ("inventado", [cv2.CAP_MSMF, cv2.CAP_DSHOW]),
])
def test_orden_de_backends(monkeypatch, preferido, orden):
    monkeypatch.setattr(config, "BACKEND_CAMARA", preferido)
    assert interfaz._backends_en_orden() == orden


def test_si_falla_msmf_prueba_dshow(monkeypatch):
    clase, probados = camara_falsa({cv2.CAP_DSHOW})
    monkeypatch.setattr(interfaz.cv2, "VideoCapture", clase)
    monkeypatch.setattr(config, "BACKEND_CAMARA", "MSMF")
    camara = interfaz.abrir_camara(0)
    assert probados == [cv2.CAP_MSMF, cv2.CAP_DSHOW] and camara.isOpened()


def test_si_fallan_los_dos_da_mensaje_claro(monkeypatch):
    clase, _ = camara_falsa(set())
    monkeypatch.setattr(interfaz.cv2, "VideoCapture", clase)
    with pytest.raises(ErrorCamara, match="Privacidad"):
        interfaz.abrir_camara(0)


def test_descarta_cuadros_negros_del_arranque(monkeypatch):
    clase, _ = camara_falsa({cv2.CAP_MSMF}, cuadros_negros=20)
    monkeypatch.setattr(interfaz.cv2, "VideoCapture", clase)
    camara = interfaz.abrir_camara(0)
    assert camara.negros == 0                     # se saltaron los 20 negros
    assert camara.read()[1].mean() > config.BRILLO_MINIMO_CAMARA


def test_camara_tapada_igual_se_abre_tras_la_espera(monkeypatch):
    clase, _ = camara_falsa({cv2.CAP_MSMF}, cuadros_negros=10**9)
    monkeypatch.setattr(interfaz.cv2, "VideoCapture", clase)
    monkeypatch.setattr(config, "SEGUNDOS_ARRANQUE_CAMARA", 0.2)
    assert interfaz.abrir_camara(0).isOpened()
