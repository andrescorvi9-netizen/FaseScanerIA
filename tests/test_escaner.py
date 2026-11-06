"""Pruebas del escáner con una cámara simulada (sin cámara real ni base de datos)."""

import tkinter as tk

import numpy as np
import pytest

import escaner_app
from escaner_app import DESCONOCIDO, SIN_ROSTRO, elegir_candidato
from facescan import interfaz


class CamaraFalsa:
    """Imita una cámara abierta que entrega cuadros grises."""

    def __init__(self):
        self.abierta = True

    def read(self):
        return True, np.full((480, 640, 3), 120, dtype=np.uint8)

    def release(self):
        self.abierta = False

    def getBackendName(self):
        return "FALSA"


@pytest.fixture
def escaner(monkeypatch):
    """Abre el escáner con cámaras falsas y sin consultar PostgreSQL."""
    camaras = []

    def abrir_camara_falsa(indice):
        camaras.append(CamaraFalsa())
        return camaras[-1]

    monkeypatch.setattr(interfaz, "abrir_camara", abrir_camara_falsa)
    monkeypatch.setattr(escaner_app.AppEscaner, "consultar_base", lambda self: None)
    ventana = tk.Tk()
    app = escaner_app.AppEscaner(ventana)
    esperar(ventana, lambda: app.camara is not None)
    yield app, camaras
    app.cerrar()


def esperar(ventana, condicion, intentos=200):
    """Procesa eventos de Tkinter hasta que se cumpla la condición."""
    for _ in range(intentos):
        ventana.update()
        if condicion():
            return
        ventana.after(10)
    raise AssertionError("La condición no se cumplió a tiempo")


def test_pausar_suelta_la_camara_y_reanudar_la_abre(escaner):
    app, camaras = escaner
    app.alternar_pausa()
    assert app.camara is None and not camaras[0].abierta  # libre para el registro
    app.alternar_pausa()
    esperar(app.ventana, lambda: app.camara is not None)
    assert len(camaras) == 2 and camaras[1].abierta


@pytest.mark.parametrize("resultados, esperado", [
    ([], SIN_ROSTRO),
    ([{"id": None, "similitud": 0.2}], DESCONOCIDO),
    ([{"id": 7, "similitud": 0.5}, {"id": 9, "similitud": 0.8}, {"id": None, "similitud": 0.1}], 9),
])
def test_elegir_candidato(resultados, esperado):
    assert elegir_candidato(resultados) == esperado
