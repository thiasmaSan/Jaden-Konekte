-- Système d'information indicatif — Jaden Konekté
-- PostgreSQL 16 + TimescaleDB (chargé automatiquement par infra/compose.yaml).
-- Vous êtes libres de l'adapter : justifiez vos choix dans le rapport.

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;          -- pgvector, pour le RAG (voir ia/rag)

CREATE TABLE utilisateur (
  id            SERIAL PRIMARY KEY,
  prenom        VARCHAR(40)  NOT NULL,
  nom           VARCHAR(40)  NOT NULL,
  courriel      VARCHAR(120) NOT NULL UNIQUE,
  mot_de_passe  VARCHAR(255) NOT NULL,           -- haché (argon2 / bcrypt), jamais en clair
  photo_url     VARCHAR(255),
  cree_le       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE exploitation (
  id       SERIAL PRIMARY KEY,
  code     VARCHAR(30)  NOT NULL UNIQUE,         -- utilisé dans les topics MQTT (ex. expl-1)
  nom      VARCHAR(80)  NOT NULL,
  commune  VARCHAR(80)  NOT NULL,
  lat      DOUBLE PRECISION,
  lon      DOUBLE PRECISION
);

CREATE TABLE membre (
  utilisateur   INT NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
  exploitation  INT NOT NULL REFERENCES exploitation(id) ON DELETE CASCADE,
  role          VARCHAR(20) NOT NULL CHECK (role IN ('exploitant', 'technicien', 'admin')),
  depuis        DATE NOT NULL DEFAULT current_date,
  PRIMARY KEY (utilisateur, exploitation)
);

CREATE TABLE parcelle (
  id            SERIAL PRIMARY KEY,
  exploitation  INT NOT NULL REFERENCES exploitation(id) ON DELETE CASCADE,
  code          VARCHAR(30) NOT NULL,            -- ex. p1 (topics MQTT)
  nom           VARCHAR(80) NOT NULL,
  culture       VARCHAR(30) NOT NULL,            -- tomate, igname, christophine…
  surface_m2    NUMERIC(10,2),
  seuil_sec     NUMERIC(5,2) DEFAULT 25,         -- humidité du sol (%) déclenchant l'arrosage
  UNIQUE (exploitation, code)
);

CREATE TABLE capteur (
  id        SERIAL PRIMARY KEY,
  parcelle  INT NOT NULL REFERENCES parcelle(id) ON DELETE CASCADE,
  type      VARCHAR(20) NOT NULL,                -- sol, air, pluvio
  grandeur  VARCHAR(20) NOT NULL,                -- humidite, temperature, luminosite, intensite
  unite     VARCHAR(10) NOT NULL,
  min_valide NUMERIC,                            -- bornes physiques pour la validation
  max_valide NUMERIC,
  actif     BOOLEAN NOT NULL DEFAULT true
);

-- Série temporelle : une ligne par mesure
CREATE TABLE mesure (
  ts        TIMESTAMPTZ NOT NULL,
  capteur   INT NOT NULL REFERENCES capteur(id) ON DELETE CASCADE,
  valeur    DOUBLE PRECISION NOT NULL,
  valide    BOOLEAN NOT NULL DEFAULT true,       -- false si hors bornes (conservée pour la maintenance)
  PRIMARY KEY (capteur, ts)                      -- idempotence : un doublon MQTT (QoS 1) est ignoré
);
SELECT create_hypertable('mesure', 'ts');

CREATE TABLE equipement (
  id        SERIAL PRIMARY KEY,
  parcelle  INT NOT NULL REFERENCES parcelle(id) ON DELETE CASCADE,
  type      VARCHAR(20) NOT NULL DEFAULT 'vanne',
  etat      VARCHAR(20) NOT NULL DEFAULT 'fermee',
  maj_le    TIMESTAMPTZ
);

CREATE TABLE commande (
  id          VARCHAR(40) PRIMARY KEY,           -- identifiant envoyé dans le message MQTT
  equipement  INT NOT NULL REFERENCES equipement(id) ON DELETE CASCADE,
  action      VARCHAR(20) NOT NULL,
  duree_s     INT,
  origine     VARCHAR(20) NOT NULL,              -- manuelle, regle, agent
  auteur      INT REFERENCES utilisateur(id),
  statut      VARCHAR(20) NOT NULL DEFAULT 'envoyee',  -- envoyee, confirmee, echec
  cree_le     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE regle (
  id          SERIAL PRIMARY KEY,
  parcelle    INT NOT NULL REFERENCES parcelle(id) ON DELETE CASCADE,
  nom         VARCHAR(80) NOT NULL,
  condition   JSONB NOT NULL,   -- ex. {"et": [{"capteur":"sol/humidite","op":"<","valeur":25},{"meteo":"pluie_6h","op":"<","valeur":2}]}
  action      JSONB NOT NULL,   -- ex. {"equipement":"vanne","action":"ouvrir","duree_s":600}
  active      BOOLEAN NOT NULL DEFAULT true,
  derniere_execution TIMESTAMPTZ
);

CREATE TABLE diagnostic (
  id          SERIAL PRIMARY KEY,
  parcelle    INT REFERENCES parcelle(id) ON DELETE SET NULL,
  auteur      INT REFERENCES utilisateur(id),
  image_url   VARCHAR(255) NOT NULL,
  statut      VARCHAR(20) NOT NULL DEFAULT 'en_cours',  -- en_cours, termine, echec
  classe      VARCHAR(80),
  score       REAL,
  modele      VARCHAR(60),                              -- version du modèle utilisé
  confirme    BOOLEAN,                                  -- validation par l'exploitant
  cree_le     TIMESTAMPTZ NOT NULL DEFAULT now(),
  termine_le  TIMESTAMPTZ
);

CREATE TABLE alerte (
  id          VARCHAR(40) PRIMARY KEY,                  -- id du serveur central ou local
  origine     VARCHAR(20) NOT NULL,                     -- locale, reseau
  emetteur    VARCHAR(80),
  type        VARCHAR(20) NOT NULL,
  culture     VARCHAR(30),
  maladie     VARCHAR(80),
  gravite     VARCHAR(10),
  commune     VARCHAR(80),
  contenu     JSONB NOT NULL,
  recue_le    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE historique (
  id          BIGSERIAL PRIMARY KEY,
  ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
  exploitation INT REFERENCES exploitation(id) ON DELETE CASCADE,
  utilisateur INT REFERENCES utilisateur(id),
  type        VARCHAR(30) NOT NULL,                     -- connexion, commande, regle, diagnostic…
  details     JSONB
);

-- Passages des fiches techniques pour le RAG (dimension selon le modèle d'embedding choisi)
CREATE TABLE passage (
  id          SERIAL PRIMARY KEY,
  source      VARCHAR(120) NOT NULL,                    -- nom du fichier
  section     VARCHAR(200),
  contenu     TEXT NOT NULL,
  index_corpus VARCHAR(64),
  embedding   vector(384)
);

CREATE INDEX passage_index_corpus ON passage (index_corpus);
