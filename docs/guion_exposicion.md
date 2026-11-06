# Guion de exposición: FaceScan

Expositor: Carlos Cortes · IA, 8.º semestre · Ingeniería en Sistemas y Computación, Universidad de Cundinamarca

Duración sugerida: unos 10 minutos de código, 3 de demo y preguntas.

---

## Checklist antes de exponer

- [ ] **PostgreSQL encendido.** En `services.msc`, el servicio `postgresql-x64-…` debe estar
      "En ejecución". Prueba rápida: `python scripts\crear_bd.py` debe decir "lista". Se
      puede ejecutar cuantas veces se quiera: no borra nada.
- [ ] **Cámara destapada y encendida.** Revisa el obturador de privacidad y la tecla de
      cámara de la laptop. Cierra Teams, Zoom y la app Cámara.
- [ ] **Venv activado** en las dos terminales: `.venv\Scripts\Activate.ps1`. Abre las dos
      terminales en la carpeta `facereconer`.
- [ ] **Buena luz de frente.** Con buena luz la cámara da un brillo medio de ~114; de noche
      con luz de celular la imagen salió casi negra. Si es de noche, ten la luz del celular a mano.
- [ ] Tu registro tiene **4 fotos**: con ellas la similitud en vivo fue de 52 % a 90 % (mediana
      77 %), incluso girando la cara. Si el escáner te marca "Desconocido", ponte de frente.
- [ ] **Ensaya la demo con el compañero antes de exponer.** La prueba completa con dos
      personas a la vez todavía no se ha hecho (los pasos de pausar y reanudar sí: 5 de 5).
- [ ] **pgAdmin abierto** en *facescan > Schemas > public > Tables*.
- [ ] **Compañero para la demo:** que acepte de antemano ser registrado y luego eliminado.
- [ ] Ejecuta `python -m pytest` una vez: deben salir 45 pruebas en verde.
- [ ] ⚠️ **NO ejecutar `scripts\reiniciar_bd.py`.** Borra todas las personas y fotos,
      incluido tu registro, y el escáner ya no te reconocería en la demo.

---

## Recorrido por el código

Abre cada archivo en VS Code en este orden. Busca la función con `Ctrl+Shift+O`.

### 1. `facescan/config.py`
- **Qué decir:** "Todo lo ajustable vive en un solo archivo: rutas, umbrales, la cámara y la
  conexión. La contraseña no está en el código: se lee del archivo `.env`, que no se sube
  a GitHub."
- **Señalar:** `UMBRAL_COSENO = 0.363`, `UMBRAL_DETECCION = 0.7`, `BACKEND_CAMARA = "MSMF"`,
  `CUADROS_ENTRE_ANALISIS = 3` y `load_dotenv(RAIZ / ".env")`.

### 2. `sql/esquema.sql`
- **Qué decir:** "Son tres tablas. `personas` guarda la ficha; `fotos` guarda la ruta en
  disco y el vector de 128 números como `REAL[]`, que se puede ver en pgAdmin; `estado`
  tiene una sola fila con un número de versión. Las reglas también están en la base: si la
  interfaz fallara, PostgreSQL igual rechazaría una edad de 9 o un registro sin
  consentimiento."
- **Señalar:** `CONSTRAINT edad_valida`, `consentimiento_obligatorio`, `codigo_unico`,
  `REFERENCES personas(id) ON DELETE CASCADE`, `embedding_de_128` y la tabla `estado`.

### 3. `facescan/conexion.py`
- **Qué decir:** "Aquí se abre cada conexión. `conectar()` confirma la transacción si todo
  sale bien y la deshace si algo falla. Además traduce los errores de PostgreSQL a mensajes
  en español para el usuario, sin trazas de Python."
- **Señalar:** `conectar` (el `with conexion:` y los `except`), `_mensaje_conexion`,
  `MENSAJES_RESTRICCION` y, en `crear_base`, `sql.Identifier`: así se evita armar SQL con
  f-strings.

### 4. `facescan/base_datos.py`
- **Qué decir:** "Es el único lugar donde están las consultas de datos, todas con `%s`,
  nunca con texto concatenado. Registrar a una persona es una sola transacción: la persona,
  sus fotos y la subida de versión. Si algo falla, se deshace todo y se borran las fotos
  que se alcanzaron a copiar."
- **Señalar:** `registrar_persona` (el `try`/`except` que hace `shutil.rmtree`),
  `_incrementar_version`, `agregar_foto` (el `FOR UPDATE`), `cargar_embeddings` y
  `version_datos`.

### 5. `facescan/motor_facial.py` (el corazón del proyecto)
- **Qué decir:** "YuNet detecta el rostro y 5 puntos. `alignCrop` lo endereza a 112×112.
  SFace lo convierte en un vector de 128 números, que normalizamos a longitud 1. Comparar
  es un producto punto contra la matriz de toda la base, una sola línea con numpy."
- **Señalar:** `cargar_modelos` (`@functools.cache`: se cargan una sola vez),
  `leer_imagen` (`np.fromfile` + `cv2.imdecode`, para rutas con tildes),
  `detectar_rostros` (el comentario que enumera los valores de cada fila de YuNet), `extraer_embedding`
  (`alignCrop`, `feature`, `np.linalg.norm`) e `identificar` (`similitudes = matriz @ embedding`).

### 6. `facescan/interfaz.py`
- **Qué decir:** "Son ayudas compartidas por las dos ventanas. Abrir la cámara con un
  backend de respaldo y saltando los cuadros negros del arranque. Dibujar los nombres con
  Pillow, porque OpenCV no dibuja tildes. Y hacer el trabajo pesado en un hilo sin congelar
  la ventana."
- **Señalar:** `abrir_camara` y `_esperar_imagen`, `dibujar_rostros` (el comentario sobre
  `cv2.putText`) y `en_segundo_plano` (el `queue` y el `after`: Tkinter solo se toca desde
  el hilo principal).

### 7. `registro_ventana.py` → `registro_app.py`
- **Qué decir:** "Cada programa está partido en dos. La ventana solo arma los widgets; la
  app hereda de ella y decide qué hace cada botón. Al agregar una foto se analiza en
  segundo plano y se pinta en verde o rojo; guardar le pasa a `base_datos` las fotos con
  sus vectores."
- **Señalar:** en la ventana, `construir_formulario` (la casilla de consentimiento) y
  `dibujar_miniaturas`. En la app, `analizar_foto`, `ejecutar` y `guardar` (las
  validaciones antes de `registrar_persona`).

### 8. `escaner_ventana.py` → `escaner_app.py`
- **Qué decir:** "El ciclo de la cámara se reprograma con `after()`, a unos 26 cuadros por
  segundo. Solo 1 de cada 3 cuadros se analiza, y la ficha cambia solo si 3 análisis
  seguidos coinciden. Cada 2 segundos, en otro hilo, pregunta la versión a la base: si
  cambió, recarga los vectores. Por eso reconoce a alguien nuevo sin reiniciarse."
- **Señalar:** `ciclo_camara`, `procesar_cuadro`, `decidir_ficha` (el `deque` de 3
  resultados), `consultar_base`/`al_consultar` y `alternar_pausa` (suelta la cámara).

---

## Demo en vivo (3 minutos)

Antes de empezar, el escáner y el registro están cerrados y pgAdmin está abierto.

| Tiempo | Qué hacer | Qué decir |
|---|---|---|
| 0:00 | Terminal 1: `python escaner_app.py`. Ponte frente a la cámara. | "Me reconoce: recuadro verde, mi nombre y el % de similitud. La ficha muestra mis datos." |
| 0:30 | Terminal 2: `python registro_app.py`. Acomoda las dos ventanas lado a lado. | "Son dos programas independientes conectados solo por PostgreSQL." |
| 0:45 | En el escáner, pulsa **Pausar**. | "En Windows solo un programa a la vez puede usar la cámara. Pausar la suelta para el registro." |
| 0:50 | En el registro, llena los datos del compañero, marca la casilla y pulsa **Tomar foto con cámara**. Captura 2 fotos con el recuadro en verde y pulsa **Guardar persona**. | "Sin la casilla de consentimiento no se puede guardar: es un dato sensible según la Ley 1581." |
| 1:40 | En el escáner, pulsa **Reanudar** y pon al compañero frente a la cámara. | "No reinicié el escáner. Notó que la versión cambió y recargó los vectores: lo reconoce en unos 2 segundos." |
| 2:05 | En pgAdmin, `SELECT * FROM personas;`, `SELECT * FROM estado;` y `SELECT id_persona, array_length(embedding, 1) FROM fotos;`. | "Aquí está su fila, el vector de 128 valores y la versión, que subió." |
| 2:25 | En el escáner, mueve el **Umbral** hacia 0,60 y luego vuelve a 0,36. | "Más alto es más estricto: con poca luz puede pasar a Desconocido. 0,363 es el valor recomendado por OpenCV." |
| 2:40 | En el registro, selecciona al compañero y pulsa **Eliminar** y luego **Sí**. Con él frente a la cámara, mira el escáner. | "Se borran sus datos, fotos y vectores. En unos 2 segundos pasa a Desconocido." |
| 3:00 | Fin. | "Preguntas." |

Si la cámara falla en vivo, en el escáner usa **Analizar foto** con `datos\fotos\1\1.jpeg`:
debe dar Carlos Cortes al 100 %, porque es la misma foto registrada.

---

## Preguntas probables del docente

**1. ¿Por qué OpenCV y no TensorFlow?**
El primer intento con face-api.js (TensorFlow.js en un HTML) falló por permisos de cámara y
por cargar los modelos en el navegador. OpenCV trae el módulo DNN listo para Windows con
`pip`. Los modelos ONNX pesan 0,2 MB y 37 MB y corren rápido en CPU. TensorFlow o PyTorch
pesan cientos de MB, y dlib exige compilar en Windows.

**2. ¿Qué es un embedding?**
Es un vector de números, aquí 128, que la red SFace calcula a partir del rostro alineado.
Está entrenada para que dos fotos de la misma persona den vectores parecidos y dos personas
distintas den vectores alejados. Se calcula una vez al registrar y se guarda en la base.

**3. ¿Por qué similitud coseno?**
Compara la dirección de los vectores, no su tamaño, y así le afectan menos cambios
generales como la iluminación. Además, con vectores normalizados a longitud 1, el coseno es
solo un producto punto: `matriz @ vector` compara contra todas las fotos en una operación.

**4. ¿Por qué el umbral 0,363?**
Es el valor que recomienda OpenCV para SFace con distancia coseno. En nuestras pruebas, la
misma persona en vivo dio entre 0,52 y 0,90 (mediana 0,77) con 4 fotos registradas, y dos
personas distintas dieron 0,13 con las imágenes de muestra de OpenCV, así que el umbral
queda en medio. Con solo 2 fotos, girar la cara bajó a 0,36: por eso conviene registrar
varias. Se puede ajustar en vivo con el control del escáner.

**5. ¿Qué pasa con una foto impresa?**
Lo más probable es que la reconozca como la persona: el sistema no tiene detección de
vida. Para evitarlo haría falta verificar parpadeo o movimiento, o usar una cámara de
profundidad o infrarroja. Por eso es un proyecto académico y no un control de acceso real.
