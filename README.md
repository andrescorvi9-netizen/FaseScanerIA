# FaceScan — Reconocedor facial académico

FaceScan son **dos programas de escritorio** que comparten una base de datos PostgreSQL:

1. **Registro** (`registro_app.py`): da de alta a una persona con sus datos (nombre, edad,
   carrera, semestre, código opcional) y de 1 a 5 fotos de su rostro, cargadas del disco o
   tomadas con la cámara.
2. **Escáner** (`escaner_app.py`): abre la cámara, detecta los rostros en vivo y muestra la
   ficha de la persona reconocida, o "Desconocido".

Si el registro agrega, edita o elimina a alguien, el escáner se entera en unos 2 segundos,
sin reiniciarse.

**Autor:** Carlos Cortes, Ingeniería de Sistemas, Universidad de Cundinamarca. Materia de
Inteligencia Artificial, 8.º semestre.

**Tecnologías:** Python 3.14, OpenCV 5 (modelos YuNet y SFace en ONNX), Tkinter + Pillow,
PostgreSQL con psycopg 3 y numpy. No usa TensorFlow, PyTorch ni dlib.

---

## Estructura de carpetas

```
facereconer/
├── registro_app.py          # Programa 1: acciones de los botones
├── registro_ventana.py      # Programa 1: construcción de la ventana (formulario, tabla)
├── escaner_app.py           # Programa 2: cámara, reconocimiento, recarga desde la base
├── escaner_ventana.py       # Programa 2: construcción de la ventana (vista, ficha)
├── facescan/                # Código compartido por los dos programas
│   ├── config.py            # Rutas, umbrales, cámara y conexión (lee .env)
│   ├── conexion.py          # Conexión a PostgreSQL, errores en español, crear/reiniciar
│   ├── base_datos.py        # Personas, fotos y vectores (todas las consultas)
│   ├── motor_facial.py      # Leer imagen, detectar, alinear, embedding, comparar
│   └── interfaz.py          # Cámara, recuadros con tildes, hilos, arranque de las apps
├── sql/esquema.sql          # Tablas personas, fotos y estado
├── scripts/
│   ├── descargar_modelos.py # Baja los dos .onnx del repositorio oficial opencv_zoo
│   ├── crear_bd.py          # Crea la base "facescan" y sus tablas
│   └── reiniciar_bd.py      # Borra TODO (pide escribir SI)
├── tests/                   # 45 pruebas con pytest
├── requirements.txt
├── .env.ejemplo             # Plantilla de credenciales (el .env real no se sube)
├── modelos/                 # .onnx descargados (no se suben a git)
└── datos/fotos/<id>/        # Fotos registradas (no se suben a git)
```

Cada programa está dividido en dos archivos. `*_ventana.py` solo arma los widgets.
`*_app.py` hereda de la ventana y tiene el estado y lo que hace cada botón. Los programas
nunca escriben SQL ni llaman a OpenCV DNN directamente: usan `facescan/base_datos.py` y
`facescan/motor_facial.py`.

---

## Instalación en Windows

**Requisitos:** Windows 10/11, [Python 3.14](https://www.python.org/downloads/) y
[PostgreSQL](https://www.postgresql.org/download/windows/) instalado, con su servicio
encendido. Anota la contraseña del usuario `postgres` que elegiste al instalarlo.

En PowerShell, dentro de la carpeta del proyecto:

```powershell
# 1. Bajar el proyecto
git clone https://github.com/andrescorvi9-netizen/FaseScanerIA.git facereconer
cd facereconer

# 2. Entorno virtual
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
```

> **Si `Activate.ps1` falla** con "la ejecución de scripts está deshabilitada en este
> sistema", ejecuta una sola vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`,
> responde `S` y vuelve a activar el entorno.

```powershell
# 3. Dependencias
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Credenciales de PostgreSQL
copy .env.ejemplo .env
notepad .env
```

En `.env` basta con llenar la contraseña. Las claves vacías usan los valores por defecto
(`localhost`, `5432`, `facescan`, `postgres`):

```
FACESCAN_DB_HOST=localhost
FACESCAN_DB_PORT=5432
FACESCAN_DB_NAME=facescan
FACESCAN_DB_USER=postgres
FACESCAN_DB_PASSWORD=tu_contraseña
```

```powershell
# 5. Modelos (unos 37 MB) y base de datos
python scripts\descargar_modelos.py
python scripts\crear_bd.py

# 6. Comprobar que todo funciona
python -m pytest
```

### Errores comunes

| Mensaje | Qué hacer |
|---|---|
| "No se pudo conectar a PostgreSQL… ¿Está encendido el servicio?" | Abre `services.msc` e inicia el servicio `postgresql-x64-…`. |
| "PostgreSQL rechazó la contraseña" | Revisa `FACESCAN_DB_PASSWORD` en `.env`. |
| "No existe el archivo .env" | Ejecuta `copy .env.ejemplo .env` y escribe la contraseña. |
| "La base 'facescan' no existe" o "no tiene las tablas" | Ejecuta `python scripts\crear_bd.py`. |
| "Falta el modelo…" o "Un modelo… está dañado" | Borra los `.onnx` de `modelos/` y ejecuta `python scripts\descargar_modelos.py`. |
| "No se pudo abrir la cámara" | Cierra Teams, Zoom o la app Cámara. Revisa *Configuración > Privacidad y seguridad > Cámara > Permitir que las aplicaciones de escritorio accedan a la cámara*. |
| La cámara se ve negra | Revisa que no esté tapada (obturador de privacidad) ni apagada con la tecla de la laptop, y que no la tenga abierta otro programa: si el escáner está corriendo, púlsale **Pausar** antes de tomar fotos en el registro. |
| La cámara va lenta | En `facescan/config.py` está `BACKEND_CAMARA = "MSMF"`. Prueba `"DSHOW"`. Si el elegido falla, el programa prueba el otro solo. |

---

## Cómo usar los programas

Con el entorno virtual activado, abre cada programa en su propia terminal. Pueden estar
abiertos a la vez.

### Registro: `python registro_app.py`

1. Llena nombre, edad, carrera y semestre. El código estudiantil es opcional, pero no se
   puede repetir.
2. Marca la casilla **"La persona autoriza el uso de su rostro…"**. Sin ella no se guarda.
3. Agrega de 1 a 5 fotos con **Cargar foto(s)** o **Tomar foto con cámara**. En la ventana
   de la cámara, captura cuando el recuadro esté verde.
4. Cada miniatura sale en **verde** si tiene exactamente un rostro, o en **rojo** si no
   tiene rostro, tiene varios o está dañada. Quita las rojas con "✕ Quitar".
5. Pulsa **Guardar persona**.

En la tabla de la derecha puedes **Editar** datos, **Agregar fotos** o **Eliminar** a una
persona. Eliminar borra también sus fotos del disco y sus vectores.

### Escáner: `python escaner_app.py`

- **Recuadro verde** con nombre y % de similitud: persona reconocida. **Recuadro rojo**:
  "Desconocido".
- La **ficha** de la derecha muestra la foto registrada y los datos de la persona más
  parecida. Solo cambia cuando 3 análisis seguidos coinciden, para que no parpadee.
- **Pausar** suelta la cámara y **Reanudar** la vuelve a abrir. En Windows solo un programa
  a la vez puede usar la cámara: pausa el escáner antes de usar "Tomar foto con cámara" en
  el registro.
- **Cambiar cámara** prueba los índices 0 a 3. **Analizar foto** analiza una imagen del
  disco igual que la cámara.
- El control **Umbral** (de 0,25 a 0,60) hace el reconocimiento más estricto o más
  permisivo en vivo.
- Si PostgreSQL se cae, la cámara sigue funcionando, la barra de estado lo avisa y el
  escáner se reconecta solo cuando el servicio vuelve.

### Ver las tablas en pgAdmin

En pgAdmin: *Servers > PostgreSQL > Databases > facescan > Schemas > public > Tables*. Clic
derecho sobre una tabla, *View/Edit Data > All Rows*. También puedes usar *Tools > Query
Tool*:

```sql
SELECT * FROM personas;
SELECT id, id_persona, ruta, array_length(embedding, 1) AS valores FROM fotos;
SELECT * FROM estado;    -- la versión que vigila el escáner
```

---

## Cómo funciona el reconocimiento

```
 Imagen (cámara o foto)
        │
        ▼
 ┌──────────────┐   caja (x, y, w, h) + 5 puntos: ojos, nariz, comisuras
 │ YuNet        │──────────────────────────────────────────────┐
 │ (detección)  │                                              │
 └──────────────┘                                              ▼
                                                ┌───────────────────────────┐
                                                │ alignCrop                 │
                                                │ rota y escala con los     │
                                                │ 5 puntos → rostro 112×112 │
                                                └─────────────┬─────────────┘
                                                              ▼
                                                ┌───────────────────────────┐
                                                │ SFace (reconocimiento)    │
                                                │ → vector de 128 valores   │
                                                │ → normalización L2 (‖v‖=1)│
                                                └─────────────┬─────────────┘
                                                              ▼
 matriz de la base (N fotos × 128)  ──►  similitudes = matriz @ vector
                                                              │
                                                              ▼
                                         mejor ≥ 0,363  →  persona reconocida
                                         mejor < 0,363  →  "Desconocido"
```

1. **Detectar.** YuNet (`cv2.FaceDetectorYN`) devuelve por cada rostro su caja, 5 puntos
   de referencia y una confianza. Solo se aceptan rostros con confianza ≥ 0,7
   (`UMBRAL_DETECCION`).
2. **Alinear.** `alignCrop` usa los 5 puntos para enderezar y recortar el rostro a 112×112,
   así los ojos quedan siempre en el mismo lugar.
3. **Embedding.** SFace (`cv2.FaceRecognizerSF`) convierte el rostro alineado en un vector
   de 128 números. Fotos de la misma persona dan vectores que apuntan en direcciones
   parecidas.
4. **Normalizar.** Se divide el vector por su norma L2 para que mida 1.
5. **Comparar.** Con vectores de norma 1, la similitud coseno es un producto punto. Por eso
   una sola multiplicación `matriz @ vector` compara contra todas las fotos registradas a
   la vez.
6. **Decidir.** Si la mejor similitud es ≥ 0,363 (el umbral recomendado por OpenCV para
   SFace), se devuelve esa persona. Si no, "Desconocido".

El escáner hace este análisis 1 de cada 3 cuadros y reutiliza el resultado en los
intermedios.

---

## Cómo se conectan los dos programas

```
 registro_app.py ──escribe──►  PostgreSQL "facescan"  ◄──lee cada 2 s── escaner_app.py
                               ├── personas
                               ├── fotos (ruta + embedding REAL[128])
                               └── estado (una fila: version)
```

- Cada registro, edición o borrado suma 1 a `estado.version` **en la misma transacción**:
  o se guarda todo, o nada.
- Cada 2 segundos el escáner ejecuta `SELECT version FROM estado`, una consulta mínima, en
  un hilo aparte para no congelar la cámara. Si el número cambió, recarga todos los
  vectores en memoria. Así reconoce a una persona recién registrada sin reiniciarse.
- Si el registro falla a mitad de camino, se deshace la transacción y se borran las fotos
  que alcanzaron a copiarse en `datos/fotos/<id>/`.

---

## Resultados de las pruebas

**Con las imágenes de muestra de OpenCV:**

| Prueba | Resultado |
|---|---|
| Misma persona, foto en espejo (imagen de muestra de OpenCV) | similitud **0,91** |
| Misma persona, foto oscurecida | similitud **0,97** |
| Dos personas distintas (imágenes de muestra de OpenCV) | similitud **0,13** |

**En vivo con la cámara del autor** (30 s de frente y luego girando la cara a los lados):

| Condición | Cuadros con la ficha correcta | Similitud mín. / mediana / máx. | Análisis en "Desconocido" |
|---|---|---|---|
| De noche, luz de celular (imagen casi negra), 2 fotos registradas | 94–100 % | 43 % / 61–65 % / 79 % | — |
| Buena luz, **2 fotos** registradas | **99 %** | 36 % / 60 % / 77 % | 2 de 167 (al girar la cara) |
| Buena luz, **4 fotos** registradas | **99 %** | **52 % / 77 % / 90 %** | **0 de 157** |

Con 4 fotos, la similitud mediana subió de 60 % a 77 %, y la mínima (con la cara girada)
pasó de 36 %, debajo del umbral, a 52 %. Parte de la mejora se debe a que las 2 fotos
nuevas se tomaron con la misma cámara y la misma luz de la prueba. Por eso conviene
registrar de 3 a 5 fotos en las condiciones en que se va a usar el escáner. No hubo
ningún falso positivo, pero con una sola persona registrada eso todavía no se puede medir
del todo.

**Otras mediciones:**

| Prueba | Resultado |
|---|---|
| Cámara con MSMF (buena luz) | brillo medio 114/255, **30 cuadros por segundo** |
| Escáner con un rostro en cuadro | **~26 cuadros por segundo** (YuNet ~21 ms y SFace ~16 ms, 1 de cada 3 cuadros) |
| Pausar el escáner → tomar foto en el registro → Reanudar | **5 de 5**; el registro abre la cámara en 1,3–1,7 s y la imagen vuelve en 1,1–1,5 s |
| Nuevo registro visible en el escáner | **~1,3 s**, sin reiniciar |
| "Analizar foto" con una foto registrada | 100 %, en 0,9 s |
| Pruebas automáticas (`python -m pytest`) | **45 pruebas en verde** |

Las pruebas automáticas cubren la base de datos (contra una base aparte, `facescan_test`),
el motor facial, la apertura de la cámara y la pausa del escáner (con una cámara simulada)
y el análisis de fotos del registro. También cubren los errores: PostgreSQL apagado,
contraseña incorrecta, base sin tablas, modelo dañado y foto corrupta.

---

## Limitaciones

- **Luz y ángulo:** con poca luz o con el rostro muy de lado, la similitud baja. Con solo
  2 fotos registradas, girar la cara la bajó a 36 %, por debajo del umbral. Conviene
  registrar 3 a 5 fotos con distintos ángulos y luz.
- **Gemelos y personas muy parecidas:** pueden superar el umbral y confundirse.
- **No detecta suplantación:** una foto impresa o en un celular puede ser reconocida como
  la persona. Hacerlo exigiría detección de vida (parpadeo, profundidad o cámara
  infrarroja), que este proyecto no incluye. Por eso FaceScan no debe usarse como control
  de acceso real.
- **Escala:** compara contra todos los vectores en memoria. Va bien para un curso, pero
  con miles de personas haría falta un índice vectorial.

---

## Privacidad

Las fotos y los vectores faciales son **datos biométricos, un dato sensible según la Ley
1581 de 2012** de Colombia (protección de datos personales). Por eso:

- El registro **exige marcar la casilla de consentimiento**, y la base de datos rechaza un
  registro sin consentimiento (restricción `consentimiento_obligatorio`).
- **Eliminar** a una persona borra sus datos, sus vectores y sus fotos del disco.
- `datos/`, `modelos/` y `.env` están en `.gitignore`: ni las fotos ni la contraseña se
  suben al repositorio.
- Los datos se usan solo con fines académicos dentro de este proyecto.
