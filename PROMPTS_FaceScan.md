# FaceScan — Prompts para Claude Code (VS Code)

Carpeta del proyecto: `C:\Users\Apharius\Desktop\octavosemestre\IA\facereconer`

## Antes de empezar (manual, 2 minutos)

1. Borra el `.txt` vacío de la carpeta.
2. Copia el archivo `CLAUDE.md` (entregado junto a este documento) en la raíz de `facereconer/`.
   Claude Code lo lee solo en cada sesión: ahí quedan fijados el stack, la estructura y las reglas.
3. **No** metas el HTML viejo (`FaceScan_offline.html`) en la carpeta: pesa 10 MB porque lleva
   TensorFlow.js y los modelos incrustados en base64, y Claude Code gastaría contexto leyéndolo.
   Todo lo útil de él ya está resumido en el Prompt 0.
4. Verifica Python y PostgreSQL en la terminal de VS Code: `py -3.14 --version` y
   `psql --version` (o abre pgAdmin). Ten a mano la contraseña del usuario `postgres`
   o de otro usuario con permiso para crear bases de datos.
5. Abre la carpeta en VS Code y abre Claude Code. Pega los prompts **uno por uno, en orden**,
   y prueba lo que indica cada uno antes de pasar al siguiente.

> Consejo: pídele a Claude Code `git init` al empezar y, después de cada prompt que funcione,
> haz un commit (`git add . ; git commit -m "..."`).
> Si algo sale mal, puedes volver atrás sin perder lo anterior.

---

## Prompt 0 — Contexto y plan (no escribe código)

```
Lee CLAUDE.md. Vamos a construir FaceScan desde cero en esta carpeta.

Contexto: ya hubo un intento anterior en un solo HTML con face-api.js (TensorFlow.js) que no
funcionó. Ese intento: (1) metía los modelos en base64 y sobrescribía window.fetch para
cargarlos; (2) dependía de getUserMedia, que fallaba por permisos al abrir el archivo con
file:// o dentro de un iframe; (3) guardaba todo en localStorage y solo registraba el nombre;
(4) era un solo programa que mezclaba registro y escaneo. Por eso cambiamos a Python 3.14 +
OpenCV (YuNet + SFace) + Tkinter + PostgreSQL (psycopg 3), con dos programas separados que
comparten la base de datos.

Datos de cada persona: nombre completo, edad, carrera (texto), semestre (1 a 10),
documento o código estudiantil (opcional, único si se llena), fecha de registro,
consentimiento (sí/no) y 1 a 5 fotos del rostro.

No escribas código todavía. Dame:
1. El esquema de las tablas PostgreSQL (personas, fotos, estado) con sus columnas, tipos
   y restricciones (CHECK de edad 10-100 y semestre 1-10, UNIQUE del código).
2. Cómo se conectan los dos programas a través de la base de datos y cómo el escáner se entera
   de que se registró alguien nuevo sin reiniciarse.
3. El flujo de reconocimiento paso a paso (detectar → alinear → embedding → comparar → decidir).
4. Una lista de pasos de implementación.
Espera mi confirmación antes de crear archivos.
```

Revisa la respuesta. Si estás de acuerdo, responde "de acuerdo, continúa con el Prompt 1".

---

## Prompt 1 — Esqueleto, dependencias y modelos

```
Crea la estructura de carpetas de CLAUDE.md con archivos vacíos o mínimos, y además:

- requirements.txt con opencv-python>=5.0, numpy>=2.3, Pillow>=12, psycopg[binary]>=3.2,
  python-dotenv y pytest (todas tienen versión para Python 3.14 en Windows).
- .gitignore que excluya .venv/, .env, datos/, modelos/ y __pycache__/.
- .env.ejemplo con FACESCAN_DB_HOST=localhost, FACESCAN_DB_PORT=5432, FACESCAN_DB_NAME=facescan,
  FACESCAN_DB_USER=postgres y FACESCAN_DB_PASSWORD= (vacío).
- facescan/config.py con: RAIZ del proyecto, rutas a modelos/ y datos/fotos/, los datos de
  conexión leídos del .env con python-dotenv, UMBRAL_COSENO = 0.363 (el recomendado por OpenCV
  para SFace), INDICE_CAMARA = 0, MAX_FOTOS_POR_PERSONA = 5.
- scripts/descargar_modelos.py que descargue de los repositorios oficiales de opencv_zoo
  en GitHub los archivos face_detection_yunet_2023mar.onnx y face_recognition_sface_2021dec.onnx
  a modelos/, usando solo urllib. Si ya existen, que no los vuelva a bajar. Que muestre
  el progreso y un error claro si no hay internet.

Luego dime los comandos exactos de PowerShell para crear el venv con py -3.14, instalar,
copiar .env.ejemplo a .env y descargar los modelos.
```

**Prueba:** ejecuta los comandos y llena la contraseña en `.env`. Deben quedar los dos `.onnx` en `modelos/`.

---

## Prompt 2 — Base de datos compartida

```
Implementa la capa de PostgreSQL según el esquema que acordamos:

- sql/esquema.sql con los CREATE TABLE IF NOT EXISTS (embedding como REAL[]), la tabla estado
  con una sola fila (version BIGINT) y comentarios cortos que expliquen cada tabla.
- scripts/crear_bd.py: se conecta a la base "postgres", crea la base FACESCAN_DB_NAME si no
  existe (CREATE DATABASE necesita autocommit) y ejecuta sql/esquema.sql en ella.
  Errores claros si PostgreSQL está apagado o la contraseña del .env es incorrecta.
- facescan/base_datos.py con psycopg 3. Una función conectar() que use config, y conexiones
  cortas con "with" en cada función (sin pool: son dos apps locales).

Funciones públicas (solo estas, con docstring de una línea):
- inicializar()                       crea las tablas si no existen
- registrar_persona(datos) -> id      datos es un dict con los campos de la persona
- agregar_foto(id_persona, ruta_foto, embedding)   embedding es np.ndarray float32; guárdalo como
                                      REAL[] (embedding.tolist()) y al leerlo conviértelo
                                      de vuelta con np.array(..., dtype=np.float32)
- listar_personas() -> lista de dicts
- obtener_persona(id_persona) -> dict o None
- actualizar_persona(id_persona, datos)
- eliminar_persona(id_persona)        borra también sus fotos del disco y sus embeddings
- cargar_embeddings() -> (lista_ids, matriz_numpy)   todos los vectores para el escáner
- version_datos() -> int              lee estado.version; registrar, actualizar y eliminar la
                                      incrementan en la misma transacción

Valida edad (10 a 100) y semestre (1 a 10) en Python antes de enviar, además de los CHECK de la
tabla, y traduce las violaciones de UNIQUE/CHECK a mensajes en español.

Crea tests/test_base_datos.py con pytest contra una base facescan_test (créala en un fixture,
vacía las tablas entre pruebas y marca skip si PostgreSQL no responde). Prueba registrar,
cargar embeddings, editar, eliminar y que version_datos() cambie. Ejecuta
scripts/crear_bd.py y luego los tests.
```

---

## Prompt 3 — Motor facial

```
Implementa facescan/motor_facial.py usando cv2.FaceDetectorYN y cv2.FaceRecognizerSF.

Funciones públicas:
- cargar_modelos()                          crea detector y reconocedor una sola vez (caché);
                                            si faltan los .onnx, lanza un error que diga
                                            "Ejecuta python scripts\descargar_modelos.py"
- detectar_rostros(imagen_bgr) -> lista     cada rostro: caja (x, y, w, h), puntos y confianza.
                                            Ajusta setInputSize al tamaño de cada imagen.
- extraer_embedding(imagen_bgr, rostro)     alignCrop + feature, devuelve vector normalizado float32
- embedding_de_foto(ruta) -> embedding      para el registro: exige exactamente UN rostro;
                                            si hay 0 o más de 1, lanza error explicando cuál fue
- identificar(embedding, ids, matriz) -> (id_persona o None, similitud)
                                            similitud coseno contra toda la matriz con numpy,
                                            usando config.UMBRAL_COSENO

Lee las imágenes con cv2.imdecode + np.fromfile para que funcionen rutas de Windows con tildes
o espacios (cv2.imread falla con esas rutas).

Agrega tests/test_motor_facial.py que, si los modelos existen, pruebe que una imagen negra
no tiene rostros y que identificar() devuelve None con matriz vacía. Ejecuta los tests.
```

---

## Prompt 4 — Programa 1: Registro

```
Implementa registro_app.py con Tkinter (ventana de unos 1000x650, título "FaceScan · Registro").

Izquierda — formulario:
- Nombre completo, Edad (Spinbox), Carrera (Combobox editable con: Ingeniería de Sistemas,
  Ingeniería de Software, Administración, Contaduría, Psicología, Otra), Semestre (Spinbox 1-10),
  Código estudiantil (opcional).
- Casilla obligatoria: "La persona autoriza el uso de su rostro para este proyecto académico".
- Botones: "Cargar foto(s)" (filedialog, jpg/png/jpeg), "Tomar foto con cámara"
  (abre una ventanita con la vista de la cámara y un botón Capturar), "Guardar persona", "Limpiar".
- Vista previa de las fotos elegidas (miniaturas) con el rostro detectado recuadrado en verde;
  si una foto no tiene exactamente un rostro, márcala en rojo y no la dejes guardar.

Derecha — lista de personas registradas (Treeview: nombre, edad, carrera, semestre, n.º de fotos)
con botones "Editar", "Agregar fotos" y "Eliminar" (con confirmación).

Al guardar: copia las fotos a datos/fotos/<id_persona>/ con nombres 1.jpg, 2.jpg..., calcula
los embeddings con motor_facial y guárdalo todo con base_datos. Muestra mensajes en español con
messagebox. El cálculo de embeddings no debe congelar la ventana (usa un hilo o after()).

Mantén el archivo legible: separa la construcción de la interfaz de las acciones de los botones.
Al terminar dime cómo probarlo.
```

**Prueba:** registra 2 o 3 personas (tú y compañeros) con 2–3 fotos cada una, de frente y con buena luz.

---

## Prompt 5 — Programa 2: Escáner

```
Implementa escaner_app.py con Tkinter (título "FaceScan · Escáner").

- Vista de la cámara a la izquierda (cv2.VideoCapture con config.INDICE_CAMARA y CAP_DSHOW
  en Windows), refrescada con after() a unos 25 fps.
- Por cada rostro detectado: recuadro verde si es conocido, rojo si es "Desconocido", con el
  nombre y el % de similitud encima.
- Panel derecho "Ficha": foto registrada, nombre, edad, carrera, semestre y código de la
  persona con mayor similitud en el cuadro actual. Si no hay nadie: "Sin rostro" o "Desconocido".
- Para no saturar la CPU, calcula embeddings como máximo cada 3 cuadros y reutiliza el último
  resultado en los intermedios. Exige el mismo resultado en 3 análisis seguidos antes de
  cambiar la ficha (evita parpadeos).
- Cada 2 segundos consulta base_datos.version_datos(); si cambió, recarga los embeddings
  sin reiniciar. Así, si registro_app.py agrega a alguien, el escáner lo reconoce enseguida.
- Botones: "Pausar/Reanudar", "Cambiar cámara" (prueba índices 0 a 3), "Analizar foto"
  (abre una imagen del disco y la analiza igual que la cámara), y un Scale para ajustar
  el umbral en vivo (0.25 a 0.60).
- Si la cámara no abre, muestra un mensaje claro (¿otra app la está usando? ¿permiso de
  cámara de Windows en Configuración > Privacidad > Cámara?) en vez de cerrarse.
- Al cerrar la ventana, libera la cámara.
```

**Prueba:** abre los dos programas a la vez, registra a alguien nuevo en el 1 y comprueba que el 2 lo reconoce sin reiniciarlo.

---

## Prompt 6 — Robustez y pruebas finales

```
Revisa todo el proyecto como si fueras el docente que lo va a evaluar:
1. Ejecuta python -m pytest y corrige lo que falle.
2. Busca casos sin manejar: BD vacía, PostgreSQL apagado al abrir o a mitad de uso (el
   escáner debe seguir mostrando la cámara y avisar, y reconectar cuando vuelva), contraseña
   incorrecta en .env, carpeta modelos vacía, foto corrupta, persona eliminada mientras el
   escáner la está mostrando, y fotos que quedan en disco si falla la transacción.
3. Comprueba que ningún archivo de la app escribe SQL ni llama a cv2.FaceDetectorYN fuera
   de facescan/, y que todas las consultas están parametrizadas (nada de f-strings en SQL).
4. Dame una lista de lo que cambiaste.
```

---

## Prompt 7 — Limpieza con antislop

Primero corre la extensión **antislop** sobre el proyecto como indique su documentación
(normalmente desde la paleta de comandos de VS Code, `Ctrl+Shift+P` → antislop). Luego:

```
Ya pasé antislop por el código. Revisa sus cambios y deja el proyecto listo para exponerlo:
- Que no se haya roto nada: ejecuta pytest y abre mentalmente cada flujo.
- Elimina comentarios obvios, código muerto, prints de depuración e imports sin usar.
- Cada función pública con un docstring de una línea; nada más de documentación interna.
- Ningún archivo de la app de más de ~250 líneas; si alguno se pasa, divídelo con sentido.
- Nombres en español y consistentes en todo el proyecto.
No cambies el comportamiento ni el stack.
```

---

## Prompt 8 — README y guion de exposición

```
Escribe README.md en español con: qué hace FaceScan, captura de la estructura de carpetas,
instalación paso a paso en Windows (Python 3.14, PostgreSQL, .env, crear_bd.py),
cómo usar cada programa, cómo ver las tablas en pgAdmin, cómo funciona el reconocimiento
(YuNet detecta → alineación con 5 puntos → SFace genera un vector de 128 números →
similitud coseno contra la base → umbral decide), limitaciones (luz, ángulo, gemelos,
fotos impresas) y nota de privacidad (Ley 1581 de 2012).

Aparte, crea docs/guion_exposicion.md: en qué orden mostrar los archivos durante la
exposición (config → esquema.sql → base_datos → motor_facial → registro_app → escaner_app), qué decir de
cada uno en 2-3 frases, y una demo en vivo de 3 minutos.
```

---

## Si algo falla

- **"connection refused" / no conecta a PostgreSQL** → el servicio está apagado: `services.msc` → postgresql-x64-… → Iniciar. Revisa también el puerto en `.env` (5432 por defecto).
- **"password authentication failed"** → la contraseña de `FACESCAN_DB_PASSWORD` en `.env` no coincide con la del usuario de PostgreSQL.
- **Error de codificación al conectar en Windows** → pídele a Claude Code que agregue `client_encoding="UTF8"` en `conectar()`.

- **"No se encuentran los modelos"** → `python scripts\descargar_modelos.py` con el venv activado.
- **La cámara no abre** → cierra Teams/Zoom/la app Cámara; revisa Configuración de Windows > Privacidad > Cámara > "Permitir que las aplicaciones de escritorio accedan".
- **Reconoce mal** → registra más fotos por persona (3–5, con distintos ángulos y luz) o sube el umbral en el escáner.
- **Claude Code se desvía del stack** → recuérdale: "Sigue CLAUDE.md; no cambies el stack".
