# FaceScan — Reconocedor facial académico

## Qué es
Proyecto de la materia de IA (8.º semestre, Ingeniería de Sistemas, Universidad de Cundinamarca).
Son dos programas de escritorio conectados por una base de datos PostgreSQL común:

1. **Registro** (`registro_app.py`): formulario para dar de alta a una persona con sus datos
   (nombre, edad, carrera, semestre) y una o varias fotos de su rostro.
2. **Escáner** (`escaner_app.py`): abre la cámara, detecta rostros en vivo y muestra la ficha
   de la persona reconocida o "Desconocido".

## Stack (no cambiarlo sin preguntar)
- **Python 3.14** en Windows 10/11, entorno virtual en `.venv/` (`py -3.14 -m venv .venv`).
- OpenCV (`opencv-python` 5.x) con sus modelos ONNX oficiales:
  - Detección: **YuNet** (`cv2.FaceDetectorYN`) → `modelos/face_detection_yunet_2023mar.onnx`
  - Reconocimiento: **SFace** (`cv2.FaceRecognizerSF`) → `modelos/face_recognition_sface_2021dec.onnx`
- Interfaz: **Tkinter** (viene con Python) + `Pillow` para mostrar imágenes.
- Base de datos: **PostgreSQL** (ya instalado en el equipo) con **psycopg 3**
  (`psycopg[binary]`). Nada de SQLAlchemy ni ORMs: SQL explícito para poder explicarlo.
- No se levanta ningún servidor web ni API: son apps de escritorio que hablan directo con
  PostgreSQL (puerto 5432). Si alguna vez hiciera falta un puerto HTTP, **no usar 8080 ni 8081**
  (están ocupados por otros proyectos del equipo).
- Credenciales en un archivo `.env` (leído con `python-dotenv`), nunca en el código.
  Se entrega `.env.ejemplo` con las claves vacías.
- `numpy` para los vectores. Nada de dlib, face_recognition, TensorFlow, PyTorch ni pgvector
  (exigen compiladores o extensiones extra en Windows).

## Estructura
```
facereconer/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── .env.ejemplo             # FACESCAN_DB_HOST, _PORT, _NAME, _USER, _PASSWORD
├── registro_app.py          # Programa 1: acciones de los botones (python registro_app.py)
├── registro_ventana.py      # Programa 1: construcción de la ventana (formulario, tabla)
├── escaner_app.py           # Programa 2: cámara, reconocimiento, recarga desde la base
├── escaner_ventana.py       # Programa 2: construcción de la ventana (vista, ficha)
├── facescan/                # Código compartido por los dos programas
│   ├── __init__.py
│   ├── config.py            # Rutas, umbrales, cámara, datos de conexión desde .env
│   ├── conexion.py          # Conexión a PostgreSQL, errores en español, crear/reiniciar
│   ├── base_datos.py        # Personas, fotos y vectores (también copia y borra las fotos)
│   ├── motor_facial.py      # Leer imagen, detectar, alinear, extraer embedding, comparar
│   └── interfaz.py          # Ayudas Tkinter: cámara, recuadros, hilos, arranque de apps
├── sql/
│   └── esquema.sql          # CREATE TABLE ... (se puede abrir en pgAdmin)
├── scripts/
│   ├── descargar_modelos.py
│   ├── crear_bd.py          # Crea la base "facescan" si no existe y ejecuta esquema.sql
│   └── reiniciar_bd.py      # Vacía tablas y datos/fotos/ (pide escribir SI)
├── modelos/                 # .onnx descargados (no se suben a git)
├── datos/fotos/             # Fotos registradas (no se suben a git)
└── tests/
    ├── test_base_datos.py   # Contra la base facescan_test
    ├── test_motor_facial.py
    ├── test_interfaz.py     # Cámara simulada: backends y cuadros negros
    └── test_registro.py
```

## Base de datos
- Tablas `personas`, `fotos` (ruta en disco + embedding) y `estado` (una fila con `version`).
- El embedding de SFace (128 valores) se guarda como `REAL[]`, para que se vea en pgAdmin.
- La comparación se hace en Python con numpy: el escáner carga todos los vectores en memoria.
- `fotos.id_persona` con `ON DELETE CASCADE`.
- Cada registro, edición o borrado incrementa `estado.version` en la misma transacción;
  el escáner consulta ese número cada 2 s y recarga los vectores si cambió.
- Las pruebas usan una base aparte, `facescan_test`, y se omiten (skip) si PostgreSQL no responde.

## Reglas de código
- Código, nombres de variables, comentarios y mensajes de la interfaz **en español**.
- El código se va a exponer en clase: funciones cortas, nombres claros, un docstring de una
  línea por función pública. Sin abstracciones innecesarias, sin clases si una función basta.
- Los dos programas **nunca** escriben SQL directamente: usan `facescan/base_datos.py`
  (el SQL vive solo en `base_datos.py` y `conexion.py`).
- Cada programa son dos archivos: `*_ventana.py` arma los widgets y `*_app.py` (que hereda de
  la ventana) tiene el estado y las acciones. Ningún archivo de la app pasa de ~250 líneas.
- Los dos programas **nunca** llaman a OpenCV DNN directamente: usan `facescan/motor_facial.py`.
- Consultas siempre parametrizadas (`%s`), nunca con f-strings.
- Los valores ajustables (umbral de similitud, cámara, tamaño de entrada) van en `config.py`.
- Rutas con `pathlib.Path` relativas a la carpeta del proyecto, nunca rutas absolutas.
- Manejar errores con mensajes claros para el usuario (PostgreSQL apagado o contraseña
  incorrecta, cámara ocupada, foto sin rostro, modelos sin descargar), no con trazas de Python.

## Comandos (PowerShell)
```
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.ejemplo .env        # y llenar la contraseña de PostgreSQL
python scripts\descargar_modelos.py
python scripts\crear_bd.py
python registro_app.py
python escaner_app.py
python -m pytest
```

## Privacidad
Las fotos y embeddings son datos biométricos (dato sensible, Ley 1581 de 2012).
El registro exige marcar una casilla de consentimiento; existe opción de eliminar a una persona
con todas sus fotos y vectores. `.env`, `datos/` y `modelos/` van en `.gitignore`.
