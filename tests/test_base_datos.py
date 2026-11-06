"""Pruebas de facescan/base_datos.py contra la base facescan_test."""

import numpy as np
import pytest

from facescan import base_datos, config
from facescan.base_datos import ErrorBaseDatos


@pytest.fixture(scope="module")
def base_pruebas():
    """Crea facescan_test una vez; omite las pruebas si PostgreSQL no responde."""
    try:
        base_datos.crear_base(config.BD_NOMBRE_PRUEBAS)
    except ErrorBaseDatos as error:
        pytest.skip(f"PostgreSQL no disponible: {error}")


@pytest.fixture
def bd(base_pruebas, monkeypatch, tmp_path):
    """Apunta la app a facescan_test y a una carpeta temporal, con las tablas vacías."""
    monkeypatch.setattr(config, "BD_NOMBRE", config.BD_NOMBRE_PRUEBAS)
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(config, "CARPETA_FOTOS", tmp_path / "datos" / "fotos")
    base_datos.inicializar()
    with base_datos.conectar() as conexion:
        conexion.execute("TRUNCATE personas, fotos RESTART IDENTITY CASCADE")
    return tmp_path


def datos_persona(**cambios):
    """Devuelve los datos de una persona válida, con los cambios indicados."""
    datos = {"nombre_completo": "Ana Pérez", "edad": 21, "carrera": "Ingeniería de Sistemas",
             "semestre": 8, "codigo": "", "consentimiento": True}
    datos.update(cambios)
    return datos


def foto_falsa(carpeta, nombre="foto.jpg", semilla=0):
    """Crea un archivo de foto y un embedding normalizado para las pruebas."""
    ruta = carpeta / nombre
    ruta.write_bytes(b"no es una imagen real")
    vector = np.random.default_rng(semilla).standard_normal(128).astype(np.float32)
    return ruta, vector / np.linalg.norm(vector)


def test_registrar_y_obtener(bd):
    fotos = [foto_falsa(bd, "a.jpg", 1), foto_falsa(bd, "b.png", 2)]
    id_persona = base_datos.registrar_persona(datos_persona(codigo=" 2020123 "), fotos)

    persona = base_datos.obtener_persona(id_persona)
    assert persona["nombre_completo"] == "Ana Pérez"
    assert persona["codigo"] == "2020123"
    assert persona["fecha_registro"] is not None
    assert [ruta.name for ruta in persona["fotos"]] == ["1.jpg", "2.png"]
    assert all(ruta.exists() for ruta in persona["fotos"])
    assert base_datos.listar_personas()[0]["num_fotos"] == 2


def test_obtener_persona_inexistente(bd):
    assert base_datos.obtener_persona(999) is None


def test_cargar_embeddings(bd):
    foto_a = foto_falsa(bd, "a.jpg", 1)
    foto_b = foto_falsa(bd, "b.jpg", 2)
    id_ana = base_datos.registrar_persona(datos_persona(), [foto_a])
    id_luis = base_datos.registrar_persona(datos_persona(nombre_completo="Luis"), [foto_b])

    ids, matriz = base_datos.cargar_embeddings()
    assert ids == [id_ana, id_luis]
    assert matriz.shape == (2, 128) and matriz.dtype == np.float32
    np.testing.assert_allclose(matriz[0], foto_a[1], rtol=1e-6)


def test_cargar_embeddings_con_base_vacia(bd):
    ids, matriz = base_datos.cargar_embeddings()
    assert ids == [] and matriz.shape == (0, 128)


def test_actualizar_persona(bd):
    id_persona = base_datos.registrar_persona(datos_persona(), [foto_falsa(bd)])
    base_datos.actualizar_persona(id_persona, datos_persona(edad=22, semestre=9))
    persona = base_datos.obtener_persona(id_persona)
    assert (persona["edad"], persona["semestre"]) == (22, 9)


def test_eliminar_borra_fotos_y_vectores(bd):
    id_persona = base_datos.registrar_persona(datos_persona(), [foto_falsa(bd)])
    carpeta = config.CARPETA_FOTOS / str(id_persona)
    assert carpeta.exists()

    base_datos.eliminar_persona(id_persona)
    assert base_datos.obtener_persona(id_persona) is None
    assert base_datos.cargar_embeddings()[0] == []
    assert not carpeta.exists()
    with pytest.raises(ErrorBaseDatos, match="ya no existe"):
        base_datos.eliminar_persona(id_persona)


def test_version_cambia_con_cada_escritura(bd):
    versiones = [base_datos.version_datos()]
    id_persona = base_datos.registrar_persona(datos_persona(), [foto_falsa(bd)])
    versiones.append(base_datos.version_datos())
    base_datos.agregar_foto(id_persona, *foto_falsa(bd, "otra.jpg", 5))
    versiones.append(base_datos.version_datos())
    base_datos.actualizar_persona(id_persona, datos_persona(edad=30))
    versiones.append(base_datos.version_datos())
    base_datos.eliminar_persona(id_persona)
    versiones.append(base_datos.version_datos())
    assert versiones == sorted(set(versiones))  # cinco valores distintos y crecientes


@pytest.mark.parametrize("cambio, mensaje", [
    ({"edad": 9}, "edad"),
    ({"semestre": 11}, "semestre"),
    ({"nombre_completo": "   "}, "nombre"),
    ({"carrera": "  "}, "carrera"),
    ({"consentimiento": False}, "consentimiento"),
])
def test_validaciones_en_python(bd, cambio, mensaje):
    with pytest.raises(ErrorBaseDatos, match=mensaje):
        base_datos.registrar_persona(datos_persona(**cambio), [foto_falsa(bd)])
    assert base_datos.listar_personas() == []


def test_check_de_carrera_en_la_tabla(bd):
    with pytest.raises(ErrorBaseDatos, match="carrera"):
        with base_datos.conectar() as conexion:
            conexion.execute(
                """INSERT INTO personas (nombre_completo, edad, carrera, semestre, consentimiento)
                   VALUES ('Ana', 20, '   ', 3, TRUE)"""
            )


def test_codigo_unico_pero_opcional(bd):
    base_datos.registrar_persona(datos_persona(codigo="123"), [foto_falsa(bd)])
    with pytest.raises(ErrorBaseDatos, match="código"):
        base_datos.registrar_persona(datos_persona(codigo="123"), [foto_falsa(bd)])
    base_datos.registrar_persona(datos_persona(codigo=""), [foto_falsa(bd)])
    base_datos.registrar_persona(datos_persona(codigo=None), [foto_falsa(bd)])
    assert len(base_datos.listar_personas()) == 3


def test_registro_fallido_borra_carpeta_y_no_deja_rastro(bd):
    version_antes = base_datos.version_datos()
    foto_buena = foto_falsa(bd, "buena.jpg")
    foto_perdida = (bd / "no_existe.jpg", foto_buena[1])

    with pytest.raises(ErrorBaseDatos, match="No se pudo copiar"):
        base_datos.registrar_persona(datos_persona(), [foto_buena, foto_perdida])

    assert base_datos.listar_personas() == []
    assert base_datos.version_datos() == version_antes
    assert not any(config.CARPETA_FOTOS.glob("*"))  # la carpeta 1/ con 1.jpg se borró


def test_maximo_de_fotos(bd):
    fotos = [foto_falsa(bd, f"{n}.jpg", n) for n in range(config.MAX_FOTOS_POR_PERSONA)]
    id_persona = base_datos.registrar_persona(datos_persona(), fotos)
    with pytest.raises(ErrorBaseDatos, match="máximo"):
        base_datos.agregar_foto(id_persona, *foto_falsa(bd, "sexta.jpg"))
    carpeta = config.CARPETA_FOTOS / str(id_persona)
    assert len(list(carpeta.iterdir())) == config.MAX_FOTOS_POR_PERSONA


def test_reiniciar_deja_todo_vacio(bd):
    assert config.BD_NOMBRE == config.BD_NOMBRE_PRUEBAS  # nunca sobre la base real
    base_datos.registrar_persona(datos_persona(), [foto_falsa(bd)])
    (config.CARPETA_FOTOS / "99").mkdir()  # carpeta vieja de una base anterior

    base_datos.reiniciar()

    assert base_datos.listar_personas() == []
    assert base_datos.version_datos() == 0
    assert not any(config.CARPETA_FOTOS.iterdir())
    id_nuevo = base_datos.registrar_persona(datos_persona(), [foto_falsa(bd)])
    assert id_nuevo == 1  # los ids vuelven a empezar sin chocar con carpetas viejas


def test_agregar_foto_a_persona_inexistente(bd):
    with pytest.raises(ErrorBaseDatos, match="ya no existe"):
        base_datos.agregar_foto(999, *foto_falsa(bd))
