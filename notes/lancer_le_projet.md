# Lancer le projet

Ce guide complète le [README](../README.md), qui donne l'objectif, les sources de données, les
prérequis et le bloc de commandes de la chaîne. Il sert à configurer la connexion, à comparer ses
nombres avec les nôtres, à trancher les cas qui demandent une personne, à modifier `schema.sql`, à
réagir à une erreur, à interroger la base et à construire le site. Les raisons des choix sont dans
[decisions.md](decisions.md).

## 1. Configurer la connexion

Le chargement crée les schémas et les tables dans une base PostgreSQL déjà créée. Une seule fois :

1. Créer un compte et une base réservés au projet, en administrateur :

   ```sql
   CREATE ROLE barometre LOGIN PASSWORD 'un-mot-de-passe';
   CREATE DATABASE barometre OWNER barometre;
   ```

2. Écrire ce mot de passe dans le fichier de mots de passe de PostgreSQL, hors du projet :
   `%APPDATA%\postgresql\pgpass.conf` sous Windows, `~/.pgpass` ailleurs. Le deuxième champ est le
   port de la base.

   ```text
   localhost:5433:barometre:barometre:un-mot-de-passe
   ```

3. La connexion par défaut est `localhost`, port 5433, base et compte `barometre`. Le port 5433 est
   celui de la machine de développement ; une installation standard de PostgreSQL écoute sur 5432.
   Les variables `BAROMETRE_HOTE`, `BAROMETRE_PORT`, `BAROMETRE_BASE` et `BAROMETRE_COMPTE`
   changent ces valeurs, par exemple dans PowerShell :

   ```powershell
   $env:BAROMETRE_PORT = "5432"
   ```

Le mot de passe n'est jamais écrit dans le projet. Une base hébergée, comme Supabase, se configure
avec les mêmes variables.

## 2. Comparer avec notre jeu de vérification

La chaîne traite les exports présents dans `donnees_seao/` : avec d'autres exports, les nombres
seront autres. Pour vérifier le code, nous utilisons sept exports de 2026 :
`mensuel_20260501_20260531.json`, `mensuel_20260801_20260831.json`,
`mensuel_20260901_20260930.json`, `hebdo_20260907_20260913.json`, `hebdo_20260928_20261004.json`,
`hebdo_20261005_20261011.json` et `hebdo_20261012_20261018.json`, avec les fichiers du ministère
datés du 29 septembre 2026 et les fichiers tenus à la main de ce dépôt. Le 18 novembre 2026, les
programmes ont affiché :

| Étape | Ce que le programme affiche |
|---|---|
| Analyse | 8 971, 7 476, 7 000, 1 561, 2 033, 2 181 et 1 521 fiches municipales, dans l'ordre des exports ci-dessus ; aucun organisme nouveau |
| Complément du contexte | 1 042 organismes ; 2 cas à trancher à la main (deux régies au nom mal écrit) ; 106 organismes non municipaux |
| Chargement | 28 611 fiches ; 33 démarches ; « Exports comparés : 7/7 » et « Validation complète : aucun écart avec les CSV » ; 0 dossier à classer ; 91 groupes de fournisseurs à vérifier ; code 0 |
| Carte | 1 281 municipalités : 10 « PGA-Eau repéré », 11 « démarche liée », 5 « outil seulement » et 1 255 « aucune trace » ; 2 démarches hors carte |
| Tests | 184 tests réussis |

Avec les mêmes fichiers, ces nombres servent de point de comparaison. Chaque programme les affiche
à la fin ; les états se retrouvent aussi dans la base :

```sql
SELECT etat, count(*) FROM analyses.etat_pga_eau GROUP BY etat;
```

Sur la machine de développement, le chargement a pris de 66 à 98 secondes (cinq chargements
complets, les 17 et 18 novembre 2026). C'est une observation, pas une promesse.

## 3. Les interventions humaines

Les programmes signalent ces cas ; une personne les tranche.

- **Un organisme à rattacher.** `sorties/contexte_a_verifier.csv` liste les cas que
  `completer_contexte.py` n'a pas pu rattacher au répertoire (`a_traiter` vaut « oui »). Pour en
  régler un, écrire son code géographique dans la colonne `code_geographique` de
  `contexte_municipalites.csv`, puis relancer la chaîne : `completer_contexte.py` remplit le reste.
- **Un dossier à classer.** À la fin du chargement, la ligne « Dossiers liés à la gestion des actifs
  en eau, à classer dans demarches.csv » donne leurs numéros. Pour chacun, ajouter une ligne à
  `demarches.csv`, puis relancer `charger_base.py` et `exporter_carte.py` : le fichier est relu en
  entier à chaque chargement. Colonnes : `organisme` (le nom exact du fichier de contexte), `plan`
  (`PGA-Eau`), `classement` (élaboration, étape, plan d'intervention, plan de gestion des actifs,
  démarche voisine ou outil), `etat` (mandat attribué, appel d'offres en cours, appel d'offres
  annulé, plan adopté ou plan publié), `date_attribution` et `date_publication` (AAAA-MM-JJ),
  `montant`, `fournisseur`, `ocid` (le dossier), `lien`, `source` (obligatoire) et `notes`.
  L'entreprise est retrouvée à partir du dossier : `fournisseur` dit seulement s'il doit y en avoir
  une.
- **Des fournisseurs à regrouper.** `sorties/fournisseurs_a_regrouper.csv` propose des entreprises
  du même nom, dont une seule a un NEQ. C'est une liste à relire : aucun programme ne l'applique
  encore.
- **Un regroupement de municipalités.** Ajouter une ligne à `regroupements.csv`, avec sa source
  officielle.
- **Une règle de repérage.** Suivre l'en-tête de `config/regles_reperage.toml` : un exemple et un
  contre-exemple dans les tests, les tests, puis toute la chaîne. Le chargement reclasse toutes les
  fiches à chaque passage.

## 4. Modifier `schema.sql`

Un commentaire ne demande rien. Après un changement de structure (une table, une colonne, un type,
une contrainte, une vue), lancer `python charger_base.py --reinitialiser`, puis
`python exporter_carte.py` : un chargement normal n'applique `schema.sql` que si le schéma `seao`
est absent. Cette option efface les quatre schémas du projet (`territoire`, `organismes`, `seao` et
`analyses`), toutes leurs données et ce qui en dépend ailleurs dans la base, comme une vue construite
sur leurs tables, puis recharge tout depuis les fichiers. Si le rechargement échoue, corriger la
cause et relancer `python charger_base.py`.

## 5. Dépannage

Le chargement enregistre son travail par étapes : la création des schémas, puis le territoire et
les organismes, puis chaque export, puis le classement et les démarches. Une erreur annule l'étape
en cours, pas les étapes déjà enregistrées. Un code de sortie 1 ou 2 à la vérification finale
n'annule rien non plus : les données chargées restent en base.

| Situation | Ce qui est en place | Que faire |
|---|---|---|
| Règles de repérage invalides | L'analyse ne lit ni n'écrit rien ; le chargement n'ouvre aucune connexion | Corriger `config/regles_reperage.toml` d'après le message |
| Fichier de contexte mal formé | L'analyse et le complément n'écrivent rien ; le chargement n'ouvre aucune connexion | Corriger la ligne indiquée dans le message, puis relancer |
| Contexte impossible à réécrire (fichier ouvert dans Excel, en lecture seule) | Le message dit si le nouveau contexte est en place et nomme les copies gardées ; l'analyse n'écrit aucun de ses quatre CSV | Lire l'état annoncé et mettre de côté la copie indiquée (un fichier `.tmp` ou la sauvegarde), fermer le fichier, puis relancer |
| Export au nom inattendu | Le chargement s'arrête avant de lire les exports ; le territoire et les organismes restent enregistrés | Renommer le fichier sur le modèle `hebdo_20260907_20260913.json` |
| Panne pendant le chargement d'un export (identifiant en double, fiche d'une forme imprévue) | Cet export est annulé ; les exports déjà enregistrés restent ; les suivants ne sont pas lus | Corriger la cause, souvent en retéléchargeant l'export, puis relancer : les exports déjà chargés sont reconnus par leur empreinte et sautés |
| Export modifié depuis son chargement, sous le même nom | Le chargement s'arrête à cet export | Remettre le fichier d'origine, ou tout recharger avec `--reinitialiser` |
| Ligne de `demarches.csv` refusée | Le classement et les démarches de ce passage sont annulés ; les exports restent | Corriger la ligne nommée dans le message, puis relancer |
| Code 1 à la vérification : un écart, ou un CSV illisible | Tout ce qui est chargé reste en base | Relancer l'analyse de l'export en cause, puis le chargement |
| Code 2 à la vérification : un CSV absent, ou aucun export | Tout ce qui est chargé reste en base | Analyser l'export dont le `details.csv` manque, puis relancer le chargement |
| Connexion refusée | Rien n'est fait | Vérifier que PostgreSQL tourne, le port, `pgpass.conf` et les variables `BAROMETRE_*` |
| Carte : contours incomplets | `carte/donnees.js` n'est pas réécrit | `python exporter_carte.py --contours-a-jour` |
| Carte : service des contours injoignable | `carte/donnees.js` n'est pas réécrit | Relancer plus tard |

## 6. Consulter la base

`charger_base.py` range les données dans quatre schémas, soit 21 tables et 5 vues :

| Schéma | Ce qu'il contient |
|---|---|
| `territoire` | le répertoire du ministère : régions, MRC, municipalités avec leurs anciens codes, données sur l'eau |
| `organismes` | qui achète : l'organisme réel et ses identifiants d'acheteur dans le SEAO |
| `seao` | les exports chargés et les fiches, découpées en tables : dossier, fiche, attribution, contrat, fournisseur… |
| `analyses` | le classement des fiches, les démarches classées à la main et les vues de consultation |

Chaque colonne est commentée dans `schema.sql`. Deux exemples de requêtes :

```sql
-- Les dossiers PGA-Eau, avec la population de leur municipalité.
SELECT organisme, territoire, population, titre
FROM analyses.fiche_municipale
WHERE pga_eau
ORDER BY population;

-- Les titres qui parlent d'un plan de gestion des actifs, avec ou sans accents.
SELECT titre
FROM seao.fiche
WHERE titre_recherche @@ plainto_tsquery('analyses.fr_sans_accents', 'plan gestion actifs');
```

## 7. Le site de suivi

```powershell
zensical serve --open     # ou : python -m zensical serve --open
```

Le site s'ouvre à <http://localhost:8000>. Chaque push sur `main` le reconstruit et le publie sur
GitHub Pages; le réglage à faire une seule fois dans GitHub est Settings, Pages, Build and
deployment, Source « GitHub Actions ». Il est construit avec Zensical, à partir du modèle du cours
IFT3150.
