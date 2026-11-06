-- Esquema de FaceScan. Se puede ejecutar varias veces: solo crea lo que falta.

-- personas: una fila por persona registrada, con sus datos de la ficha.
CREATE TABLE IF NOT EXISTS personas (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre_completo TEXT        NOT NULL,
    edad            SMALLINT    NOT NULL,
    carrera         TEXT        NOT NULL,
    semestre        SMALLINT    NOT NULL,
    codigo          TEXT,                                -- opcional: NULL si no se llena
    fecha_registro  TIMESTAMPTZ NOT NULL DEFAULT now(),
    consentimiento  BOOLEAN     NOT NULL,
    CONSTRAINT nombre_no_vacio            CHECK (length(trim(nombre_completo)) > 0),
    CONSTRAINT carrera_no_vacia           CHECK (length(trim(carrera)) > 0),
    CONSTRAINT edad_valida                CHECK (edad BETWEEN 10 AND 100),
    CONSTRAINT semestre_valido            CHECK (semestre BETWEEN 1 AND 10),
    CONSTRAINT consentimiento_obligatorio CHECK (consentimiento),
    CONSTRAINT codigo_unico               UNIQUE (codigo)  -- varios NULL sí se permiten
);

-- fotos: cada foto guardada en disco y su embedding SFace (128 números).
CREATE TABLE IF NOT EXISTS fotos (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_persona   INTEGER     NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    ruta         TEXT        NOT NULL,                   -- relativa: datos/fotos/7/1.jpg
    embedding    REAL[]      NOT NULL,
    fecha_subida TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT embedding_de_128 CHECK (array_length(embedding, 1) = 128)
);

CREATE INDEX IF NOT EXISTS idx_fotos_persona ON fotos(id_persona);

-- estado: una sola fila; "version" sube con cada cambio para que el escáner recargue.
CREATE TABLE IF NOT EXISTS estado (
    id      SMALLINT PRIMARY KEY CHECK (id = 1),
    version BIGINT   NOT NULL DEFAULT 0
);

INSERT INTO estado (id, version) VALUES (1, 0) ON CONFLICT (id) DO NOTHING;
