-- Schéma de la base du baromètre des pratiques de gestion d'actifs municipales.
--
-- Projet IFT3150 de Nizar Lakhder, Université de Montréal, automne 2026.
--
-- Les tables sont rangées en quatre groupes, chacun dans son propre schéma
-- PostgreSQL, pour ne pas tout mettre dans le même panier :
--
--   territoire  ce que dit le ministère des Affaires municipales : régions,
--               MRC, municipalités, données sur l'eau potable;
--   organismes  le lien entre les acheteurs du SEAO et ce territoire;
--   seao        les fiches publiées, telles quelles, découpées en tables;
--   analyses    ce que le programme en déduit, et les vues de consultation.
--
-- Les clés viennent des données elles-mêmes (code géographique, ocid,
-- identifiants OP et FO du SEAO). Seul l'organisme reçoit un numéro interne :
-- rien dans les sources ne l'identifie de façon officielle.
--
-- Ce fichier peut être relancé sans danger : il ne crée que ce qui manque.
-- Il est appliqué par charger_base.py.

CREATE EXTENSION IF NOT EXISTS unaccent;   -- chercher sans tenir compte des accents
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- chercher des noms proches

CREATE SCHEMA IF NOT EXISTS territoire;
CREATE SCHEMA IF NOT EXISTS organismes;
CREATE SCHEMA IF NOT EXISTS seao;
CREATE SCHEMA IF NOT EXISTS analyses;   -- « analyse » est un mot réservé de PostgreSQL

-- Une configuration de recherche en français qui ignore les accents : une
-- recherche de « reseau eau » trouve « Réseau d'eau ».
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config c JOIN pg_namespace n ON n.oid = c.cfgnamespace
                   WHERE c.cfgname = 'fr_sans_accents' AND n.nspname = 'analyses') THEN
        CREATE TEXT SEARCH CONFIGURATION analyses.fr_sans_accents (COPY = pg_catalog.french);
        ALTER TEXT SEARCH CONFIGURATION analyses.fr_sans_accents
            ALTER MAPPING FOR hword, hword_part, word WITH unaccent, french_stem;
    END IF;
END
$$;


-- ===========================================================================
-- 1. Territoire : le répertoire du ministère et la Stratégie d'économie d'eau
-- ===========================================================================

-- Les fichiers de référence chargés, pour savoir d'où vient chaque valeur.
CREATE TABLE IF NOT EXISTS territoire.fichier_reference (
    nom               text PRIMARY KEY,
    description       text NOT NULL,
    date_fichier      date NOT NULL,           -- date du fichier sur le disque, donc du téléchargement
    empreinte_sha256  text NOT NULL,
    charge_le         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS territoire.region (
    code  char(2) PRIMARY KEY,                 -- « 05 » pour l'Estrie
    nom   text NOT NULL
);

-- Les MRC, mais aussi les deux communautés métropolitaines et l'Administration
-- régionale Kativik, que le ministère range dans le même fichier.
CREATE TABLE IF NOT EXISTS territoire.mrc (
    code            text PRIMARY KEY,          -- « AR930 » pour une MRC, « CM663 » pour une communauté
    nom             text NOT NULL,
    designation     text NOT NULL,
    population      integer,
    superficie_km2  numeric,
    code_postal     text,
    region_code     char(2) REFERENCES territoire.region   -- vide pour les communautés métropolitaines
);

CREATE TABLE IF NOT EXISTS territoire.municipalite (
    code_geographique        char(5) PRIMARY KEY,
    nom                      text NOT NULL,
    designation              text NOT NULL,    -- Ville, Municipalité, Paroisse, Canton, Village...
    population               integer,
    superficie_km2           numeric,          -- superficie totale, plans d'eau compris
    superficie_terrestre_km2 numeric,
    code_postal              text,             -- celui de l'hôtel de ville
    date_constitution        date,
    region_code              char(2) NOT NULL REFERENCES territoire.region,
    mrc_code                 text REFERENCES territoire.mrc,   -- vide pour 131 territoires hors MRC
    communaute_code          text REFERENCES territoire.mrc    -- communauté métropolitaine, s'il y a lieu
);

-- Une municipalité regroupée disparaît du répertoire, mais ses anciennes
-- données restent publiées sous son ancien code (celles sur l'eau, par
-- exemple). Ce fichier, tenu à la main, relie l'ancien code au nouveau.
CREATE TABLE IF NOT EXISTS territoire.regroupement (
    ancien_code        char(5) PRIMARY KEY,
    ancien_nom         text NOT NULL,
    code_geographique  char(5) NOT NULL REFERENCES territoire.municipalite,
    date_effet         date NOT NULL,
    source             text NOT NULL
);

-- Une ligne par municipalité et par année de la Stratégie. Le code est gardé
-- tel que publié; code_geographique donne la municipalité actuelle, directement
-- ou par un regroupement.
CREATE TABLE IF NOT EXISTS territoire.indicateur_eau (
    code_source                 char(5) NOT NULL,
    annee                       smallint NOT NULL,
    nom_source                  text,
    code_geographique           char(5) REFERENCES territoire.municipalite,
    classe_population           text,          -- classe de la population desservie, pas de la population totale
    population_desservie        integer,
    indice_fuites               numeric,       -- indice des fuites d'infrastructures (IFI), sans troncature
    validite_audit_pct          numeric,
    consommation_l_pers_jour    numeric,       -- consommation résidentielle
    longueur_reseau_km          numeric,
    PRIMARY KEY (code_source, annee)
);


-- ===========================================================================
-- 2. Organismes : qui achète, et à quel territoire il correspond
-- ===========================================================================

-- Un organisme réel : la Ville de Montréal, une régie, une MRC... Les chiffres
-- du territoire (population, superficie) ne sont pas recopiés ici : on les
-- retrouve par le code géographique ou le code de MRC. Ne restent que les
-- informations saisies à la main dans contexte_municipalites.csv.
CREATE TABLE IF NOT EXISTS organismes.organisme (
    organisme_id                 integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom                          text NOT NULL UNIQUE,
    type                         text NOT NULL CHECK (type IN ('municipalité', 'MRC ou communauté', 'non municipal')),
    code_geographique            char(5) REFERENCES territoire.municipalite,
    mrc_code                     text REFERENCES territoire.mrc,
    type_milieu                  text,
    source_contexte              text,
    notes                        text,
    CHECK (code_geographique IS NULL OR mrc_code IS NULL)
);

-- Les identifiants d'acheteur du SEAO. Montréal en a plusieurs dizaines, qui
-- pointent tous vers le même organisme.
CREATE TABLE IF NOT EXISTS organismes.acheteur (
    acheteur_id   text PRIMARY KEY CHECK (acheteur_id LIKE 'OP-%'),
    organisme_id  integer NOT NULL REFERENCES organismes.organisme,
    nom_seao      text                         -- le dernier nom lu dans les fiches
);


-- ===========================================================================
-- 3. SEAO : les fiches publiées
-- ===========================================================================

-- Chaque export chargé. L'empreinte empêche de charger deux fois le même
-- fichier, ou de charger sans le savoir un fichier modifié portant le même nom.
CREATE TABLE IF NOT EXISTS seao.fichier_source (
    nom                    text PRIMARY KEY,
    periode_debut          date,
    periode_fin            date,
    date_publication       timestamptz,
    empreinte_sha256       text NOT NULL,
    nb_fiches              integer NOT NULL,   -- toutes les fiches de l'export
    nb_fiches_municipales  integer NOT NULL,
    nb_fiches_ajoutees     integer NOT NULL,   -- les autres étaient déjà en base, venues d'un autre export
    charge_le              timestamptz NOT NULL DEFAULT now()
);

-- La nomenclature du SEAO, comme « S3 - Services d'architecture et d'ingénierie ».
CREATE TABLE IF NOT EXISTS seao.nomenclature (
    code     text PRIMARY KEY,
    libelle  text NOT NULL
);

CREATE TABLE IF NOT EXISTS seao.classification (
    code     text PRIMARY KEY,                 -- code UNSPSC
    libelle  text NOT NULL
);

-- Les entreprises : fournisseurs retenus et soumissionnaires.
CREATE TABLE IF NOT EXISTS seao.fournisseur (
    fournisseur_id  text PRIMARY KEY,
    nom             text NOT NULL,             -- le dernier nom lu : un même identifiant est parfois écrit autrement
    neq             text,
    adresse         text,
    localite        text,
    region          text,
    code_postal     text,
    pays            text
);

-- Une fiche : l'état d'un dossier au moment d'un export. Un dossier (ocid)
-- peut avoir plusieurs fiches, une par mise à jour. Une fiche n'est pas un contrat.
CREATE TABLE IF NOT EXISTS seao.fiche (
    ocid                   text NOT NULL,
    release_id             text NOT NULL,
    fichier_source         text NOT NULL REFERENCES seao.fichier_source,
    date_deduite_numero    date,               -- lue dans le numéro de la fiche : sans doute sa publication
    date_fiche             timestamptz,        -- release.date : en pratique, l'ouverture de l'avis
    acheteur_id            text NOT NULL REFERENCES organismes.acheteur,
    numero_avis            text,
    titre                  text,
    statut                 text,               -- active, complete, cancelled
    methode_code           text,               -- open, direct, limited, selective
    methode                text,
    justification_methode  text,
    categorie_principale   text,               -- goods, services, works
    type_contrat           text,
    nomenclature_code      text REFERENCES seao.nomenclature,
    date_ouverture         timestamptz,
    date_fermeture         timestamptz,
    duree_jours            integer,
    nb_soumissionnaires    integer,            -- tel que déclaré dans la fiche
    url_avis               text,
    brut                   jsonb NOT NULL,     -- la fiche complète, telle que publiée
    titre_recherche        tsvector GENERATED ALWAYS AS
                               (to_tsvector('analyses.fr_sans_accents'::regconfig, coalesce(titre, ''))) STORED,
    PRIMARY KEY (ocid, release_id)
);

CREATE TABLE IF NOT EXISTS seao.fiche_tag (
    ocid        text NOT NULL,
    release_id  text NOT NULL,
    tag         text NOT NULL,                 -- tender, tenderUpdate, contract, contractTermination...
    PRIMARY KEY (ocid, release_id, tag),
    FOREIGN KEY (ocid, release_id) REFERENCES seao.fiche ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS seao.fiche_classification (
    ocid        text NOT NULL,
    release_id  text NOT NULL,
    code        text NOT NULL REFERENCES seao.classification,
    principale  boolean NOT NULL,              -- faux pour les classifications additionnelles
    PRIMARY KEY (ocid, release_id, code),
    FOREIGN KEY (ocid, release_id) REFERENCES seao.fiche ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS seao.soumissionnaire (
    ocid            text NOT NULL,
    release_id      text NOT NULL,
    fournisseur_id  text NOT NULL REFERENCES seao.fournisseur,
    PRIMARY KEY (ocid, release_id, fournisseur_id),
    FOREIGN KEY (ocid, release_id) REFERENCES seao.fiche ON DELETE CASCADE
);

-- Dans les deux exports étudiés, chaque attribution a exactement un
-- fournisseur : il est donc rangé dans l'attribution. Le programme de
-- chargement s'arrête si ce n'est plus vrai.
CREATE TABLE IF NOT EXISTS seao.attribution (
    ocid              text NOT NULL,
    release_id        text NOT NULL,
    attribution_id    text NOT NULL,
    fournisseur_id    text NOT NULL REFERENCES seao.fournisseur,
    statut            text,
    date_attribution  timestamptz,
    montant           numeric,                 -- tel que publié; ce n'est pas une dépense payée
    montant_total     numeric,                 -- totalAmount, dont le sens reste à valider
    devise            text,
    PRIMARY KEY (ocid, release_id, attribution_id),
    FOREIGN KEY (ocid, release_id) REFERENCES seao.fiche ON DELETE CASCADE
);

-- Un contrat découle d'une attribution. Dans les données, il en reprend le
-- numéro, et aucune attribution n'a plus d'un contrat.
CREATE TABLE IF NOT EXISTS seao.contrat (
    ocid            text NOT NULL,
    release_id      text NOT NULL,
    contrat_id      text NOT NULL,
    attribution_id  text NOT NULL,
    statut          text,                      -- active, terminated, cancelled
    date_signature  timestamptz,
    date_fin        timestamptz,
    montant         numeric,
    devise          text,
    PRIMARY KEY (ocid, release_id, contrat_id),
    UNIQUE (ocid, release_id, attribution_id),
    FOREIGN KEY (ocid, release_id, attribution_id) REFERENCES seao.attribution ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS fiche_acheteur ON seao.fiche (acheteur_id);
CREATE INDEX IF NOT EXISTS fiche_titre_recherche ON seao.fiche USING gin (titre_recherche);
CREATE INDEX IF NOT EXISTS attribution_fournisseur ON seao.attribution (fournisseur_id);
CREATE INDEX IF NOT EXISTS municipalite_nom_proche ON territoire.municipalite USING gin (nom gin_trgm_ops);
CREATE INDEX IF NOT EXISTS organisme_nom_proche ON organismes.organisme USING gin (nom gin_trgm_ops);


-- ===========================================================================
-- 4. Analyse : ce que le programme déduit, et les vues de consultation
-- ===========================================================================

-- Les règles d'analyser_seao.py appliquées à chaque fiche. Elles évoluent :
-- la version retenue est l'empreinte du programme qui les a calculées.
CREATE TABLE IF NOT EXISTS analyses.fiche_classee (
    ocid                text NOT NULL,
    release_id          text NOT NULL,
    nature_transaction  text NOT NULL,         -- achat, subvention ou contribution, vente d'immeuble, partenariat
    lie_eau             boolean NOT NULL,
    pga_eau             boolean NOT NULL,
    gestion_actifs_eau  text,                  -- la famille du repérage large, vide si rien ne touche aux actifs en eau
    version_regles      text NOT NULL,
    calcule_le          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ocid, release_id),
    FOREIGN KEY (ocid, release_id) REFERENCES seao.fiche ON DELETE CASCADE
);
-- Pour une base créée avant le repérage large.
ALTER TABLE analyses.fiche_classee ADD COLUMN IF NOT EXISTS gestion_actifs_eau text;

-- Les démarches repérées, une ligne par dossier, tenues à la main dans
-- demarches.csv et rechargées telles quelles à chaque exécution. Un dossier du
-- SEAO n'est qu'une trace : Windsor a deux dossiers pour un seul PGA-Eau, et
-- Sherbrooke ne se voit que par des inspections faites « dans le cadre du
-- PGA-EAU ». D'autres sources, comme le site web d'une municipalité, pourront
-- s'ajouter sans numéro de dossier : d'où les états « plan adopté » et « plan
-- publié », qui ne viennent pas du SEAO.
CREATE TABLE IF NOT EXISTS analyses.demarche (
    demarche_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organisme_id      integer NOT NULL REFERENCES organismes.organisme,
    plan              text NOT NULL,                 -- « PGA-Eau » pour l'instant : la gestion des actifs en eau
    classement        text NOT NULL CHECK (classement IN ('élaboration', 'étape', 'plan d''intervention',
                                                          'plan de gestion des actifs', 'démarche voisine', 'outil')),
    etat              text NOT NULL CHECK (etat IN ('mandat attribué', 'appel d''offres en cours',
                                                    'appel d''offres annulé', 'plan adopté', 'plan publié')),
    date_attribution  date,
    date_publication  date,
    montant           numeric(14, 2),
    fournisseur       text,
    ocid              text UNIQUE,                   -- vide pour une source autre que le SEAO
    lien              text,
    source            text NOT NULL,
    notes             text
);

-- La fiche la plus récente de chaque dossier. Le numéro de fiche est un
-- horodatage à 14 chiffres : l'ordre alphabétique est aussi l'ordre du temps.
CREATE OR REPLACE VIEW analyses.derniere_fiche AS
SELECT DISTINCT ON (ocid)
       ocid, release_id, fichier_source, date_deduite_numero, acheteur_id, numero_avis,
       titre, statut, methode, categorie_principale, type_contrat, url_avis
FROM seao.fiche
ORDER BY ocid, release_id DESC;

-- La dernière version connue de chaque contrat : celle de la fiche la plus
-- récente qui le contient. C'est elle qu'il faut compter, une seule fois,
-- quand on additionne plusieurs exports.
CREATE OR REPLACE VIEW analyses.contrat_courant AS
SELECT DISTINCT ON (c.ocid, c.contrat_id)
       c.ocid, c.contrat_id, c.release_id, c.attribution_id, c.statut, c.date_signature,
       c.date_fin, c.montant, c.devise, a.fournisseur_id, f.acheteur_id
FROM seao.contrat c
JOIN seao.attribution a USING (ocid, release_id, attribution_id)
JOIN seao.fiche f USING (ocid, release_id)
ORDER BY c.ocid, c.contrat_id, c.release_id DESC;

-- Une ligne par fiche, avec son organisme, son territoire et son classement :
-- le point de départ de la plupart des questions.
CREATE OR REPLACE VIEW analyses.fiche_municipale AS
SELECT f.ocid, f.release_id, f.fichier_source, f.date_deduite_numero, f.titre, f.statut, f.methode,
       o.nom AS organisme, o.type AS type_organisme,
       coalesce(m.nom, mr.nom) AS territoire,
       coalesce(m.population, mr.population) AS population,
       coalesce(m.region_code, mr.region_code) AS region_code,
       c.nature_transaction, c.lie_eau, c.pga_eau, f.url_avis, c.gestion_actifs_eau
FROM seao.fiche f
JOIN organismes.acheteur a USING (acheteur_id)
JOIN organismes.organisme o USING (organisme_id)
LEFT JOIN territoire.municipalite m ON m.code_geographique = o.code_geographique
LEFT JOIN territoire.mrc mr ON mr.code = o.mrc_code
LEFT JOIN analyses.fiche_classee c USING (ocid, release_id);

-- L'état du PGA-Eau de chaque municipalité du répertoire, d'après les
-- démarches classées à la main. Trois niveaux : un PGA-Eau repéré (son
-- élaboration ou une de ses étapes), une démarche liée repérée (un plan
-- d'intervention des réseaux d'eau, un plan de gestion des actifs, une
-- démarche voisine ou un outil), ou aucune trace. Sans démarche connue,
-- l'état est « aucune trace dans les exports chargés », jamais « pas de plan » :
-- une partie des mandats ne passe pas par le SEAO.
DROP VIEW IF EXISTS analyses.etat_pga_eau;
CREATE VIEW analyses.etat_pga_eau AS
SELECT m.code_geographique, m.nom, m.designation, m.population, m.region_code, m.mrc_code,
       count(d.demarche_id) FILTER (WHERE d.classement IN ('élaboration', 'étape')) AS nb_dossiers_pga_eau,
       count(d.demarche_id) FILTER (WHERE d.classement NOT IN ('élaboration', 'étape')) AS nb_dossiers_lies,
       max(coalesce(d.date_attribution, d.date_publication)) AS derniere_date,
       CASE WHEN count(d.demarche_id) FILTER (WHERE d.classement IN ('élaboration', 'étape')) > 0
                THEN 'PGA-Eau repéré dans le SEAO'
            WHEN count(d.demarche_id) > 0 THEN 'démarche liée repérée dans le SEAO'
            ELSE 'aucune trace dans les exports chargés' END AS etat
FROM territoire.municipalite m
LEFT JOIN organismes.organisme o ON o.code_geographique = m.code_geographique
LEFT JOIN analyses.demarche d ON d.organisme_id = o.organisme_id AND d.plan = 'PGA-Eau'
GROUP BY m.code_geographique, m.nom, m.designation, m.population, m.region_code, m.mrc_code;
