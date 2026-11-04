-- Schéma de la base du baromètre des pratiques de gestion d'actifs municipales.
--
-- Quatre groupes, un schéma PostgreSQL chacun :
--   territoire  le répertoire du ministère : régions, MRC, municipalités, eau potable;
--   organismes  les acheteurs du SEAO et leur territoire;
--   seao        les fiches publiées, découpées en tables;
--   analyses    ce que les programmes en déduisent, et les vues de consultation.
--
-- Un code officiel (région, MRC, code géographique, nomenclature, UNSPSC) sert de
-- clé. Ailleurs, la base donne son propre numéro et l'identifiant publié devient
-- une colonne unique : un nom de fichier peut changer, une fiche ne s'identifie
-- qu'avec deux numéros, une entreprise a parfois plusieurs identifiants FO. Seules
-- les tables de correspondance organismes.acheteur et seao.identifiant_fournisseur
-- ont pour clé l'identifiant publié.
--
-- Une colonne aux valeurs connues a son type énuméré : les codes OCDS gardent leur
-- orthographe, nos catégories prennent un code court sans accent.
--
-- charger_base.py applique ce fichier à une base vide. Après une modification,
-- « python charger_base.py --reinitialiser » efface tout et recharge.

CREATE EXTENSION IF NOT EXISTS unaccent;   -- chercher sans tenir compte des accents
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- chercher des noms proches

CREATE SCHEMA territoire;
CREATE SCHEMA organismes;
CREATE SCHEMA seao;
CREATE SCHEMA analyses;   -- « analyse » est un mot réservé de PostgreSQL

-- Une configuration de recherche en français qui ignore les accents : une
-- recherche de « reseau eau » trouve « Réseau d'eau ».
CREATE TEXT SEARCH CONFIGURATION analyses.fr_sans_accents (COPY = pg_catalog.french);
ALTER TEXT SEARCH CONFIGURATION analyses.fr_sans_accents
    ALTER MAPPING FOR hword, hword_part, word WITH unaccent, french_stem;


-- ===========================================================================
-- 1. Territoire : le répertoire du ministère et la Stratégie d'économie d'eau
-- ===========================================================================

-- Les fichiers de référence chargés (répertoire, eau, fichiers tenus à la main),
-- dans leur version actuelle seulement.
CREATE TABLE territoire.fichier_reference (
    fichier_reference_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- numéro attribué par la base
    nom                   text NOT NULL UNIQUE,               -- nom du fichier, comme « MUN.csv »
    description           text NOT NULL,                      -- ce que contient le fichier, et où le trouver
    date_fichier          date NOT NULL,                      -- date du fichier sur le disque, donc de son téléchargement
    empreinte_sha256      text NOT NULL,                      -- empreinte SHA-256 du contenu
    charge_le             timestamptz NOT NULL DEFAULT now()  -- moment du chargement
);

-- Les régions administratives du Québec.
CREATE TABLE territoire.region (
    code  char(2) PRIMARY KEY,  -- code officiel, comme « 05 » pour l'Estrie
    nom   text NOT NULL         -- nom de la région
);

-- Les MRC, mais aussi les deux communautés métropolitaines et l'Administration
-- régionale Kativik, que le ministère range dans le même fichier.
CREATE TABLE territoire.mrc (
    code            text PRIMARY KEY,                     -- « AR930 » pour une MRC, « CM663 » pour une communauté
    nom             text NOT NULL,                        -- nom de la MRC ou de la communauté
    designation     text NOT NULL,                        -- MRC, communauté métropolitaine...
    population      integer,                              -- population publiée dans le répertoire
    superficie_km2  numeric,                              -- superficie, en kilomètres carrés
    code_postal     text,                                 -- code postal publié dans le répertoire
    region_code     char(2) REFERENCES territoire.region  -- vide pour les communautés métropolitaines
);

-- Les municipalités actuelles du répertoire. Une municipalité regroupée laisse
-- son code et son nom à celle qui l'a absorbée : ses données sur l'eau sont encore
-- publiées sous l'ancien code. Les sources sont dans regroupements.csv.
CREATE TABLE territoire.municipalite (
    code_geographique         char(5) PRIMARY KEY,              -- code géographique officiel, à cinq chiffres
    nom                       text NOT NULL,                    -- nom de la municipalité
    designation               text NOT NULL,                    -- Ville, Municipalité, Paroisse, Canton, Village...
    population                integer,                          -- population publiée dans le répertoire
    superficie_km2            numeric,                          -- superficie totale, plans d'eau compris
    superficie_terrestre_km2  numeric,                          -- superficie sans les plans d'eau
    code_postal               text,                             -- celui de l'hôtel de ville
    date_constitution         date,                             -- date de constitution de la municipalité
    region_code               char(2) NOT NULL REFERENCES territoire.region,  -- région administrative
    mrc_code                  text REFERENCES territoire.mrc,   -- vide pour un territoire hors MRC
    communaute_code           text REFERENCES territoire.mrc,   -- communauté métropolitaine, s'il y a lieu
    anciens_codes             char(5)[] NOT NULL DEFAULT '{}',  -- codes des municipalités regroupées dans celle-ci
    anciens_noms              text[] NOT NULL DEFAULT '{}',     -- leurs noms, dans le même ordre
    CHECK (cardinality(anciens_codes) = cardinality(anciens_noms))  -- un nom pour chaque ancien code
);

-- Les données de la Stratégie québécoise d'économie d'eau potable : une ligne
-- par municipalité et par année.
CREATE TABLE territoire.indicateur_eau (
    code_source               char(5) NOT NULL,   -- code tel que publié, parfois un ancien code
    annee                     smallint NOT NULL,  -- année des données
    nom_source                text,               -- nom tel que publié
    code_geographique         char(5) REFERENCES territoire.municipalite,  -- la municipalité actuelle, même par un ancien code
    classe_population         text,               -- classe de la population desservie, pas de la population totale
    population_desservie      integer,            -- population desservie par le réseau
    indice_fuites             numeric,            -- indice des fuites d'infrastructures (IFI), sans troncature
    validite_audit_pct        numeric,            -- validité de l'audit de l'eau, en pour cent
    consommation_l_pers_jour  numeric,            -- consommation résidentielle, en litres par personne et par jour
    longueur_reseau_km        numeric,            -- longueur du réseau, en kilomètres
    PRIMARY KEY (code_source, annee)
);


-- ===========================================================================
-- 2. Organismes : qui achète, et à quel territoire il correspond
-- ===========================================================================

-- Municipalité, MRC ou communauté métropolitaine, ou organisme non municipal
-- (régie, société de transport, office d'habitation...).
CREATE TYPE organismes.type_organisme AS ENUM ('municipalite', 'mrc_ou_communaute', 'non_municipal');

-- Un organisme réel (la Ville de Montréal, une régie, une MRC...), tiré de
-- contexte_municipalites.csv. Sa population se lit dans son territoire.
CREATE TABLE organismes.organisme (
    organisme_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- numéro attribué par la base
    nom                text NOT NULL UNIQUE,                -- nom tel qu'écrit dans contexte_municipalites.csv
    type               organismes.type_organisme NOT NULL,  -- municipalité, MRC ou communauté, ou non municipal
    code_geographique  char(5) REFERENCES territoire.municipalite,  -- la municipalité, pour un organisme municipal
    mrc_code           text REFERENCES territoire.mrc,      -- la MRC ou la communauté, pour un organisme de ce type
    type_milieu        text,                                -- urbain ou rural : vide pour l'instant
    source_contexte    text,                                -- d'où viennent les informations de contexte
    notes              text,                                -- remarques saisies à la main
    -- le type doit suivre le lien vers le territoire
    CHECK ((type = 'municipalite') = (code_geographique IS NOT NULL)),
    CHECK ((type = 'mrc_ou_communaute') = (mrc_code IS NOT NULL))
);

-- Les identifiants d'acheteur du SEAO et leur organisme. Montréal en a plusieurs
-- dizaines, un par arrondissement ou service.
CREATE TABLE organismes.acheteur (
    acheteur_id   text PRIMARY KEY CHECK (acheteur_id LIKE 'OP-%'),  -- identifiant publié par le SEAO, comme « OP-70456 »
    organisme_id  integer NOT NULL REFERENCES organismes.organisme,  -- l'organisme réel
    nom_seao      text  -- le dernier nom lu dans les fiches
);


-- ===========================================================================
-- 3. SEAO : les fiches publiées
-- ===========================================================================

-- Les listes fermées du standard OCDS 1.1, que suit le SEAO, dans l'ordre :
-- releaseTag, tenderStatus, method, procurementCategory, awardStatus, contractStatus.
CREATE TYPE seao.tag AS ENUM ('planning', 'planningUpdate', 'tender', 'tenderAmendment', 'tenderUpdate',
                              'tenderCancellation', 'award', 'awardUpdate', 'awardCancellation', 'contract',
                              'contractUpdate', 'contractAmendment', 'implementation', 'implementationUpdate',
                              'contractTermination', 'compiled');
CREATE TYPE seao.statut_avis AS ENUM ('planning', 'planned', 'active', 'cancelled', 'unsuccessful', 'complete', 'withdrawn');
CREATE TYPE seao.methode AS ENUM ('open', 'selective', 'limited', 'direct');
CREATE TYPE seao.categorie AS ENUM ('goods', 'works', 'services');
CREATE TYPE seao.statut_attribution AS ENUM ('pending', 'active', 'cancelled', 'unsuccessful');
CREATE TYPE seao.statut_contrat AS ENUM ('pending', 'active', 'cancelled', 'terminated');

-- Le dollar canadien, seule devise rencontrée : une autre arrête le chargement.
CREATE TYPE seao.devise AS ENUM ('CAD');

-- Les deux sortes d'exports publiés sur Données Québec.
CREATE TYPE seao.type_fichier AS ENUM ('hebdomadaire', 'mensuel');

-- Les exports du SEAO chargés. L'empreinte empêche de recharger un même fichier,
-- même renommé.
CREATE TABLE seao.fichier_source (
    fichier_id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- numéro attribué par la base
    nom               text NOT NULL UNIQUE,                -- comme « hebdo_20260907_20260913.json »
    type              seao.type_fichier NOT NULL,          -- hebdomadaire ou mensuel, lu dans le nom du fichier
    periode_debut     date NOT NULL,                       -- premier jour couvert, lu dans le nom du fichier
    periode_fin       date NOT NULL,                       -- dernier jour couvert, lu dans le nom du fichier
    date_publication  timestamptz,                         -- date de publication de l'export (publishedDate)
    empreinte_sha256  text NOT NULL UNIQUE,                -- empreinte SHA-256 du fichier
    nb_fiches         integer NOT NULL,                    -- toutes les fiches de l'export, municipales ou non
    charge_le         timestamptz NOT NULL DEFAULT now(),  -- moment du chargement
    CHECK (periode_debut <= periode_fin)
);

-- La nomenclature du SEAO, comme « S3 - Services d'architecture et d'ingénierie ».
CREATE TABLE seao.nomenclature (
    code     text PRIMARY KEY,  -- code de la nomenclature, comme « S3 »
    libelle  text NOT NULL      -- libellé publié dans la fiche
);

-- Les codes UNSPSC employés dans les fiches.
CREATE TABLE seao.classification (
    code     text PRIMARY KEY,  -- code UNSPSC, à huit chiffres
    libelle  text NOT NULL      -- libellé publié dans la fiche
);

-- Les entreprises, retenues ou soumissionnaires. Une entreprise peut avoir
-- plusieurs identifiants FO (seao.identifiant_fournisseur).
CREATE TABLE seao.fournisseur (
    fournisseur_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- numéro attribué par la base
    nom             text NOT NULL,  -- le dernier nom lu : un même identifiant est parfois écrit autrement
    neq             text UNIQUE,    -- numéro d'entreprise du Québec (NEQ), tel que publié
    adresse         text,           -- dernière adresse publiée
    localite        text,           -- ville de l'adresse
    region          text,           -- province de l'adresse, comme « QC »
    code_postal     text,           -- code postal de l'adresse
    pays            text            -- pays de l'adresse, comme « CAN »
);

-- Les identifiants FO du SEAO et leur entreprise. Même NEQ, même entreprise; les
-- autres regroupements se font à la main. Les fiches gardent l'identifiant
-- publié : regrouper deux identifiants ne change qu'une ligne ici.
CREATE TABLE seao.identifiant_fournisseur (
    identifiant     text PRIMARY KEY CHECK (identifiant LIKE 'FO-%'),  -- identifiant publié par le SEAO, comme « FO-1142385377 »
    fournisseur_id  integer NOT NULL REFERENCES seao.fournisseur  -- l'entreprise
);

-- Un dossier du SEAO : un appel d'offres ou un contrat, suivi d'une publication
-- à l'autre. Chaque mise à jour du dossier est une nouvelle fiche.
CREATE TABLE seao.dossier (
    dossier_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- numéro attribué par la base
    ocid        text NOT NULL UNIQUE  -- numéro OCDS du dossier, comme « ocds-ec9k95-20170481 » : il ne change pas
);

-- Une publication d'un dossier, avec son état à ce moment : pas un contrat.
-- release_id est un horodatage à la seconde, unique seulement avec le dossier.
-- La base garde la version du premier export chargé, dans l'ordre des périodes.
CREATE TABLE seao.fiche (
    fiche_id               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- numéro attribué par la base
    dossier_id             integer NOT NULL REFERENCES seao.dossier,  -- le dossier dont la fiche est une publication
    release_id             text NOT NULL,                      -- numéro de la fiche, un horodatage à la seconde
    date_deduite_numero    date,                               -- lue dans le numéro de la fiche : sans doute sa publication
    date_fiche             timestamptz,                        -- release.date : en pratique, l'ouverture de l'avis
    acheteur_id            text NOT NULL REFERENCES organismes.acheteur,  -- l'identifiant d'acheteur publié
    tags                   seao.tag[] NOT NULL,                -- étiquettes de la fiche : tender, contract...
    numero_avis            text,                               -- numéro de l'avis donné par l'organisme (tender.id)
    titre                  text,                               -- titre de l'avis
    statut                 seao.statut_avis,                   -- statut de l'appel d'offres
    methode_code           seao.methode,                       -- mode de sollicitation, en code du standard
    methode                text,                               -- le même en toutes lettres, comme « Contrat de gré à gré »
    justification_methode  text,                               -- justification publiée du mode de sollicitation
    categorie_principale   seao.categorie,                     -- biens, travaux ou services
    type_contrat           text,                               -- catégorie du SEAO, comme « Services professionnels »
    nomenclature_code      text REFERENCES seao.nomenclature,  -- code de la nomenclature du SEAO
    date_ouverture         timestamptz,                        -- début de la période de soumission
    date_fermeture         timestamptz,                        -- fin de la période de soumission
    duree_jours            integer,                            -- durée de cette période, en jours, telle que publiée
    nb_soumissionnaires    integer,                            -- nombre de soumissionnaires, tel que déclaré dans la fiche
    url_avis               text,                               -- lien vers l'avis sur le site du SEAO
    brut                   jsonb NOT NULL,                     -- la fiche complète, telle que publiée
    titre_recherche        tsvector GENERATED ALWAYS AS        -- le titre, prêt pour une recherche sans accents
                               (to_tsvector('analyses.fr_sans_accents'::regconfig, coalesce(titre, ''))) STORED,
    UNIQUE (dossier_id, release_id)
);

-- Les exports où figure chaque fiche. Une fiche hebdomadaire revient souvent dans
-- le mensuel, parfois avec d'autres étiquettes ou un autre rôle pour une
-- entreprise. Un simple changement d'ordre des listes n'est pas une autre version.
CREATE TABLE seao.fiche_fichier (
    fiche_id         integer NOT NULL REFERENCES seao.fiche ON DELETE CASCADE,  -- la fiche
    fichier_id       integer NOT NULL REFERENCES seao.fichier_source,  -- un export où elle figure
    version_publiee  jsonb,  -- la version de cet export, si elle diffère de celle gardée dans seao.fiche
    PRIMARY KEY (fiche_id, fichier_id)
);

-- Les codes UNSPSC de chaque fiche : le principal et les additionnels.
CREATE TABLE seao.fiche_classification (
    fiche_id    integer NOT NULL REFERENCES seao.fiche ON DELETE CASCADE,  -- la fiche
    code        text NOT NULL REFERENCES seao.classification,  -- le code UNSPSC
    principale  boolean NOT NULL,                              -- vrai pour le code principal, faux pour les autres
    PRIMARY KEY (fiche_id, code)
);

-- Les entreprises qui ont soumissionné, fiche par fiche.
CREATE TABLE seao.soumissionnaire (
    fiche_id                 integer NOT NULL REFERENCES seao.fiche ON DELETE CASCADE,  -- la fiche
    identifiant_fournisseur  text NOT NULL REFERENCES seao.identifiant_fournisseur,  -- l'identifiant FO publié du soumissionnaire
    PRIMARY KEY (fiche_id, identifiant_fournisseur)
);

-- Les attributions de chaque fiche. Chacune a exactement un fournisseur dans les
-- exports chargés : il est rangé ici, et le chargement s'arrête sinon.
CREATE TABLE seao.attribution (
    attribution_id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- numéro attribué par la base
    fiche_id                 integer NOT NULL REFERENCES seao.fiche ON DELETE CASCADE,  -- la fiche qui la publie
    numero                   text NOT NULL,            -- numéro de l'attribution dans la fiche (award.id)
    identifiant_fournisseur  text NOT NULL REFERENCES seao.identifiant_fournisseur,  -- l'identifiant FO publié du fournisseur
    statut                   seao.statut_attribution,  -- statut de l'attribution
    date_attribution         timestamptz,              -- date de l'attribution
    montant                  numeric,                  -- tel que publié; ce n'est pas une dépense payée
    montant_total            numeric,                  -- totalAmount, dont le sens reste à valider
    devise                   seao.devise,              -- devise des montants
    UNIQUE (fiche_id, numero)
);

-- Un contrat découle d'une attribution. Dans les données, il en reprend le
-- numéro, et aucune attribution n'a plus d'un contrat.
CREATE TABLE seao.contrat (
    contrat_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- numéro attribué par la base
    attribution_id  integer NOT NULL UNIQUE REFERENCES seao.attribution ON DELETE CASCADE,  -- l'attribution dont il découle
    numero          text NOT NULL,        -- numéro du contrat dans la fiche (contract.id)
    statut          seao.statut_contrat,  -- statut du contrat
    date_signature  timestamptz,          -- date de signature
    date_fin        timestamptz,          -- fin prévue du contrat
    montant         numeric,              -- montant du contrat, tel que publié
    devise          seao.devise           -- devise du montant
);

CREATE INDEX fiche_acheteur ON seao.fiche (acheteur_id);
CREATE INDEX fiche_tags ON seao.fiche USING gin (tags);
CREATE INDEX fiche_titre_recherche ON seao.fiche USING gin (titre_recherche);
CREATE INDEX fiche_fichier_fichier ON seao.fiche_fichier (fichier_id);
CREATE INDEX identifiant_fournisseur_entreprise ON seao.identifiant_fournisseur (fournisseur_id);
CREATE INDEX attribution_fournisseur ON seao.attribution (identifiant_fournisseur);
CREATE INDEX soumissionnaire_fournisseur ON seao.soumissionnaire (identifiant_fournisseur);
CREATE INDEX municipalite_nom_proche ON territoire.municipalite USING gin (nom gin_trgm_ops);
CREATE INDEX organisme_nom_proche ON organismes.organisme USING gin (nom gin_trgm_ops);


-- ===========================================================================
-- 4. Analyse : ce que le programme déduit, et les vues de consultation
-- ===========================================================================

-- La nature d'une transaction selon les règles d'analyser_seao.py.
CREATE TYPE analyses.nature_transaction AS ENUM ('achat', 'subvention_ou_contribution', 'vente_immeuble', 'partenariat');

-- Les familles du repérage large (voir gestion_actifs_eau dans analyser_seao.py).
CREATE TYPE analyses.famille_actifs_eau AS ENUM ('pga_eau', 'outil', 'etape', 'plan_intervention', 'gestion_actifs');

-- Le plan visé par une démarche : le PGA-Eau pour l'instant. Les autres plans
-- du baromètre, comme le plan climat, s'ajouteront ici.
CREATE TYPE analyses.plan AS ENUM ('pga_eau');

-- Ce que le dossier montre de la démarche, classé à la main dans demarches.csv.
CREATE TYPE analyses.classement_demarche AS ENUM ('elaboration', 'etape', 'plan_intervention', 'plan_gestion_actifs',
                                                  'demarche_voisine', 'outil');

-- Où en est la démarche. Les deux derniers états, plan adopté et plan publié,
-- ne peuvent pas venir du SEAO.
CREATE TYPE analyses.etat_demarche AS ENUM ('mandat_attribue', 'appel_offres_en_cours', 'appel_offres_annule',
                                            'plan_adopte', 'plan_publie');

-- Le classement de chaque fiche par les règles d'analyser_seao.py, avec la
-- version de ces règles.
CREATE TABLE analyses.fiche_classee (
    fiche_id            integer PRIMARY KEY REFERENCES seao.fiche ON DELETE CASCADE,  -- la fiche classée
    nature_transaction  analyses.nature_transaction NOT NULL,  -- achat, subvention ou contribution, vente d'immeuble, partenariat
    lie_eau             boolean NOT NULL,                      -- la fiche parle d'eau : un filet large
    pga_eau             boolean NOT NULL,                      -- le titre annonce un PGA-Eau
    gestion_actifs_eau  analyses.famille_actifs_eau,           -- la famille du repérage large, ou vide
    version_regles      text NOT NULL,                         -- empreinte d'analyser_seao.py et d'utilitaires.py
    calcule_le          timestamptz NOT NULL DEFAULT now()     -- moment du calcul
);

-- Les démarches classées à la main dans demarches.csv, une ligne par dossier,
-- rechargées telles quelles. Un dossier n'est qu'une trace : Windsor a deux
-- dossiers pour un seul PGA-Eau. Une démarche tirée d'une autre source, comme le
-- site d'une municipalité, n'aura pas de dossier.
CREATE TABLE analyses.demarche (
    demarche_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- numéro attribué par la base
    organisme_id      integer NOT NULL REFERENCES organismes.organisme,  -- l'organisme qui mène la démarche
    plan              analyses.plan NOT NULL,                  -- le plan visé
    classement        analyses.classement_demarche NOT NULL,   -- ce que le dossier montre de la démarche
    etat              analyses.etat_demarche NOT NULL,         -- où en est la démarche
    date_attribution  date,                                    -- date d'attribution du mandat, recopiée de l'avis
    date_publication  date,                                    -- date de publication de l'avis
    montant           numeric(14, 2),                          -- montant attribué, recopié de l'avis
    dossier_id        integer UNIQUE REFERENCES seao.dossier,  -- le dossier du SEAO; vide pour une autre source
    fournisseur_id    integer REFERENCES seao.fournisseur,     -- le fournisseur retenu, retrouvé dans les attributions du dossier
    lien              text,                                    -- lien vers la source
    source            text NOT NULL,                           -- d'où vient l'information : « SEAO » pour l'instant
    notes             text                                     -- remarques sur le classement
);

-- La fiche la plus récente de chaque dossier. Le numéro de fiche est un
-- horodatage à 14 chiffres : l'ordre alphabétique est aussi l'ordre du temps.
CREATE VIEW analyses.derniere_fiche AS
SELECT DISTINCT ON (f.dossier_id)
       f.fiche_id, f.dossier_id, d.ocid, f.release_id, f.date_deduite_numero, f.acheteur_id, f.numero_avis,
       f.titre, f.statut, f.methode, f.categorie_principale, f.type_contrat, f.url_avis
FROM seao.fiche f
JOIN seao.dossier d ON d.dossier_id = f.dossier_id
ORDER BY f.dossier_id, f.release_id DESC;

-- La dernière version de chaque contrat, celle de sa fiche la plus récente :
-- c'est elle qu'on compte quand on additionne plusieurs exports.
CREATE VIEW analyses.contrat_courant AS
SELECT DISTINCT ON (f.dossier_id, c.numero)
       c.contrat_id, f.dossier_id, d.ocid, c.numero, f.fiche_id, f.release_id, c.statut, c.date_signature,
       c.date_fin, c.montant, c.devise, a.identifiant_fournisseur, i.fournisseur_id, f.acheteur_id
FROM seao.contrat c
JOIN seao.attribution a ON a.attribution_id = c.attribution_id
JOIN seao.fiche f ON f.fiche_id = a.fiche_id
JOIN seao.dossier d ON d.dossier_id = f.dossier_id
JOIN seao.identifiant_fournisseur i ON i.identifiant = a.identifiant_fournisseur
ORDER BY f.dossier_id, c.numero, f.release_id DESC;

-- Une ligne par fiche, avec son organisme, son territoire et son classement :
-- le point de départ de la plupart des questions.
CREATE VIEW analyses.fiche_municipale AS
SELECT f.fiche_id, d.ocid, f.release_id, f.date_deduite_numero, f.titre, f.statut, f.methode,
       o.nom AS organisme, o.type AS type_organisme,
       coalesce(m.nom, mr.nom) AS territoire,
       coalesce(m.population, mr.population) AS population,
       coalesce(m.region_code, mr.region_code) AS region_code,
       c.nature_transaction, c.lie_eau, c.pga_eau, c.gestion_actifs_eau, f.url_avis
FROM seao.fiche f
JOIN seao.dossier d ON d.dossier_id = f.dossier_id
JOIN organismes.acheteur a ON a.acheteur_id = f.acheteur_id
JOIN organismes.organisme o ON o.organisme_id = a.organisme_id
LEFT JOIN territoire.municipalite m ON m.code_geographique = o.code_geographique
LEFT JOIN territoire.mrc mr ON mr.code = o.mrc_code
LEFT JOIN analyses.fiche_classee c ON c.fiche_id = f.fiche_id;

-- Ce que contient chaque export : les fiches qu'il partage avec un autre export,
-- et celles qu'on ne trouve que chez lui. Ce compte ne dépend pas de l'ordre de
-- chargement.
CREATE VIEW analyses.contenu_fichier AS
SELECT s.fichier_id, s.nom, s.type, s.periode_debut, s.periode_fin, s.nb_fiches,
       count(ff.fiche_id) AS nb_fiches_municipales,  -- les fiches municipales de l'export, toutes chargées
       count(ff.fiche_id) FILTER (WHERE EXISTS (SELECT 1 FROM seao.fiche_fichier autre
                                                WHERE autre.fiche_id = ff.fiche_id AND autre.fichier_id <> ff.fichier_id))
           AS nb_fiches_partagees,  -- celles qui figurent aussi dans un autre export
       count(ff.fiche_id) FILTER (WHERE NOT EXISTS (SELECT 1 FROM seao.fiche_fichier autre
                                                    WHERE autre.fiche_id = ff.fiche_id AND autre.fichier_id <> ff.fichier_id))
           AS nb_fiches_propres,  -- celles qu'on ne trouve que dans cet export
       count(ff.version_publiee) AS nb_fiches_publiees_autrement  -- celles qu'il publie autrement que la version gardée
FROM seao.fichier_source s
LEFT JOIN seao.fiche_fichier ff ON ff.fichier_id = s.fichier_id
GROUP BY s.fichier_id;

-- L'état du PGA-Eau de chaque municipalité, d'après les démarches classées à la
-- main : PGA-Eau repéré (élaboration ou étape), démarche liée repérée, ou aucune
-- trace dans les exports chargés. Jamais « pas de plan » : une partie des
-- mandats ne passe pas par le SEAO.
CREATE VIEW analyses.etat_pga_eau AS
SELECT m.code_geographique, m.nom, m.designation, m.population, m.region_code, m.mrc_code,
       count(d.demarche_id) FILTER (WHERE d.classement IN ('elaboration', 'etape')) AS nb_dossiers_pga_eau,
       count(d.demarche_id) FILTER (WHERE d.classement NOT IN ('elaboration', 'etape')) AS nb_dossiers_lies,
       max(coalesce(d.date_attribution, d.date_publication)) AS derniere_date,  -- l'attribution, à défaut la publication
       CASE WHEN count(d.demarche_id) FILTER (WHERE d.classement IN ('elaboration', 'etape')) > 0
                THEN 'PGA-Eau repéré dans le SEAO'
            WHEN count(d.demarche_id) > 0 THEN 'démarche liée repérée dans le SEAO'
            ELSE 'aucune trace dans les exports chargés' END AS etat
FROM territoire.municipalite m
LEFT JOIN organismes.organisme o ON o.code_geographique = m.code_geographique
LEFT JOIN analyses.demarche d ON d.organisme_id = o.organisme_id AND d.plan = 'pga_eau'
GROUP BY m.code_geographique, m.nom, m.designation, m.population, m.region_code, m.mrc_code;
