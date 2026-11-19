# Baromètre CERIU (projet IFT3150)

Projet IFT3150, Université de Montréal, automne 2026.
Étudiant : Nizar Lakhder. Superviseur : Louis-Édouard Lafontant.
Partenaire : CERIU, Pôle Données & Informations.

Une municipalité mène plusieurs démarches pour gérer ses infrastructures. Une partie laisse des
traces publiques, mais réparties entre plusieurs sources et présentées de façons différentes.

Le projet mesure jusqu'où les données publiques permettent de suivre les démarches de gestion
d'actifs des municipalités québécoises, en commençant par le plan de gestion des actifs en eau
(PGA-Eau). Il lit les exports du système électronique d'appel d'offres (SEAO), repère les appels
d'offres et les contrats liés à la gestion des actifs en eau, range le tout dans une base PostgreSQL
et prépare une carte de l'état de chaque municipalité.

## Ce que le projet dit, et ce qu'il ne dit pas

- **« Aucune trace » ne veut pas dire « pas de plan ».** Cela veut dire qu'aucune démarche liée
  à la gestion des actifs en eau n'a été repérée dans les exports chargés.
- **Le SEAO permet de repérer des appels d'offres et des contrats liés aux démarches.** Il ne
  permet pas, à lui seul, de savoir si le plan est terminé ou adopté. Un plan fait à l'interne et un
  mandat sous le seuil de publication n'y apparaissent pas.
- **Le repérage propose, une personne tranche.** Les règles lisent surtout les titres, et chaque
  dossier repéré est classé à la main, avec sa source. Ce n'est pas un taux de détection.
- **Une fiche n'est pas un contrat**, et aucun montant publié n'est une dépense payée.

Avec les sept exports de 2026 chargés le 18 novembre 2026, sur 1 281 municipalités : 10 ont un
PGA-Eau repéré dans le SEAO, 11 une démarche liée, 5 un outil seulement, et 1 255 aucune trace.

## Les sources de données

Les programmes ne téléchargent rien d'autre que les contours de la carte : les fichiers se déposent
à la main.

- **Les exports du SEAO**, dans `donnees_seao/`, pris dans le jeu « Système électronique d'appel
  d'offres (SEAO) » de Données Québec :
  <https://www.donneesquebec.ca/recherche/dataset/systeme-electronique-dappel-doffres-seao>. La
  chaîne traite tous les exports présents. Le chargement lit la période dans le nom du fichier, qui
  doit avoir la forme `hebdo_20260907_20260913.json` ou `mensuel_20260801_20260831.json`.
- **Les fichiers du ministère des Affaires municipales et de l'Habitation**, dans
  `donnees_reference/`, pris dans deux jeux de Données Québec : le
  [Répertoire des municipalités du Québec](https://www.donneesquebec.ca/recherche/dataset/repertoire-des-municipalites-du-quebec)
  et la
  [Stratégie québécoise d'économie d'eau potable 2019-2025](https://www.donneesquebec.ca/recherche/dataset/sqeep-2019-2025).
  Le tableau ci-dessous dit lesquels prendre.
- **Les contours des municipalités**, que `exporter_carte.py` télécharge une fois depuis le service
  web des découpages administratifs du ministère des Ressources naturelles et des Forêts, et range
  dans `donnees_reference/contours_municipalites.geojson`.
- **Les fichiers tenus à la main**, versionnés : `contexte_municipalites.csv` (le contexte de chaque
  organisme acheteur), `regroupements.csv` (les regroupements de municipalités, avec leur source
  officielle), `demarches.csv` (les dossiers classés à la main) et `config/regles_reperage.toml`
  (les mots et les motifs des règles de repérage). La section 3 du
  [guide](notes/lancer_le_projet.md) dit comment les modifier.

| Fichier | Ressource à prendre | Rôle | `completer_contexte.py` | `charger_base.py` |
|---|---|---|---|---|
| `MUN.csv` | Liste des municipalités (csv) | les municipalités : code géographique, nom, désignation, région, MRC, population | obligatoire | obligatoire |
| `MRC_CM_Arg.csv` | Liste des MRC_CM_Arg (csv) | les MRC, les communautés métropolitaines et l'Administration régionale Kativik | facultatif | obligatoire |
| `A01_CONVERT_XML_ORG_PER_MUN.xml` | Liste des organismes périmunicipaux | reconnaître les régies, offices et sociétés, qui ne sont pas des municipalités | facultatif | non lu |
| `validite_classe_2024.csv` | validité des audits 2024, par classe de population | données sur l'eau | facultatif | obligatoire |
| `fuites_classe_2024.csv` | indice de fuites 2024, par classe de population | données sur l'eau | facultatif | obligatoire |
| `consommation_classe_2024.csv` | consommation résidentielle 2024, par classe de population | données sur l'eau | facultatif | obligatoire |

Les trois fichiers sur l'eau remplissent la colonne `particularites_infrastructures` du contexte et
la table `territoire.indicateur_eau`.

Les cas réglés à la main s'appuient sur d'autres sources publiques : les pages d'avis du SEAO, les
avis republiés sur le site fédéral AchatsCanada, qui donnent l'adresse de l'acheteur quand la fiche
ne la donne pas, les annonces de regroupement du gouvernement du Québec et un avis du ministère de
la Justice. Chacune est citée dans la page [Références](docs/references.md) du site et dans la
colonne `notes` du fichier de contexte.

Les trois jeux de Données Québec utilisés, celui du SEAO, le Répertoire des municipalités et la
Stratégie d'économie d'eau potable, sont publiés sous la licence Attribution (CC-BY 4.0), indiquée
sur la page de chaque jeu (vérifié le 18 novembre 2026) : <https://www.donneesquebec.ca/licence/#cc-by>.

## Le parcours des données

```text
 donnees_seao/ : les exports du SEAO, déposés à la main
        │
        ▼
 1. analyser_seao.py ──────► 4 CSV par export, dans sorties/
        │
        ▼
 2. completer_contexte.py ─► contexte_municipalites.csv, complété avec les fichiers du ministère
        │
        ▼
 3. analyser_seao.py ──────► les mêmes CSV, avec le contexte complété
        │
        ▼
 4. charger_base.py ───────► base PostgreSQL, vérifiée contre les CSV
        │
        ▼
 5. exporter_carte.py ─────► carte/donnees.js, que carte/index.html affiche
```

**Pourquoi deux analyses.** La première ajoute les organismes nouveaux à la fin de
`contexte_municipalites.csv`, et écrit dans `sorties/<export>/a_enrichir.csv` les codes postaux que
lit `completer_contexte.py`. La deuxième réécrit les quatre CSV de chaque export avec le contexte
complété.

**Ce que vérifie le chargement.** `charger_base.py` relit les exports JSON, y ajoute les démarches
classées à la main (`demarches.csv`), puis vérifie la base contre les CSV de l'analyse, export par
export (décision 8 de [decisions.md](notes/decisions.md)). D'où l'ordre : un acheteur absent du
fichier de contexte arrête le chargement, et un export sans son `details.csv` rend la vérification
incomplète (code 2). Les CSV servent aussi à consulter les résultats et à relire les données.

## Avant de lancer

- **Python 3.11 ou plus récent** : les règles de repérage sont lues avec `tomllib`, apparu avec
  Python 3.11. À la racine du projet : `pip install -r requirements.txt` (psycopg pour PostgreSQL,
  rapidfuzz pour les noms proches, zensical pour le site seulement).
- **PostgreSQL 13 ou plus récent** : c'est la version minimale, à cause des extensions qu'installe
  `schema.sql` (décision 4 de [decisions.md](notes/decisions.md)). Versions essayées : 18, et
  17 sur Supabase.
- **Une base PostgreSQL déjà créée, et la connexion configurée** : le chargement y crée les schémas
  et les tables. La section 1 du [guide](notes/lancer_le_projet.md) dit comment créer la base et
  son compte, où écrire le mot de passe et comment choisir le port (5433 par défaut, alors qu'une
  installation standard écoute sur 5432).
- **Les fichiers de la section « Les sources de données »**, déposés dans `donnees_seao/` et
  `donnees_reference/`.
- **Internet**, pour la carte seulement : `exporter_carte.py` télécharge une fois les contours des
  municipalités, et la page de la carte charge Leaflet et le fond OpenStreetMap.

## Lancer la chaîne

Dans PowerShell, depuis la racine du projet. Le bloc entre `& {` et `}` s'exécute d'un seul tenant :
au premier échec, `throw` arrête tout et dit quelle étape a échoué.

```powershell
& {
    # Les tests d'abord : ils n'ont besoin ni des exports ni de la base.
    python -B -m unittest -v
    if ($LASTEXITCODE -ne 0) { throw "Tests : échec." }

    $exports = @(Get-ChildItem donnees_seao -Filter *.json -File -ErrorAction Stop)
    if ($exports.Count -eq 0) { throw "Aucun export dans donnees_seao/ : rien à analyser." }

    # 1. Première analyse de chaque export
    foreach ($export in $exports) {
        python analyser_seao.py $export.Name
        if ($LASTEXITCODE -ne 0) { throw "Première analyse : échec sur $($export.Name)." }
    }

    # 2. Complément du contexte
    python completer_contexte.py
    if ($LASTEXITCODE -ne 0) { throw "Complément du contexte : échec." }

    # 3. Deuxième analyse de chaque export
    foreach ($export in $exports) {
        python analyser_seao.py $export.Name
        if ($LASTEXITCODE -ne 0) { throw "Deuxième analyse : échec sur $($export.Name)." }
    }

    # 4. Chargement dans PostgreSQL, puis vérification contre les CSV
    python charger_base.py
    if ($LASTEXITCODE -ne 0) { throw "Chargement : code $LASTEXITCODE (1 : échec ou écart ; 2 : vérification incomplète)." }

    # 5. Données de la carte
    python exporter_carte.py
    if ($LASTEXITCODE -ne 0) { throw "Carte : échec." }
}
```

**Si le bloc s'arrête**, son message nomme l'étape en échec, et ce que le programme a écrit juste
au-dessus en donne la cause. Les étapes déjà terminées restent en place, et un code 1 ou 2 du
chargement n'annule pas les données chargées. Corriger la cause, puis relancer le bloc : la
section 5 du [guide](notes/lancer_le_projet.md) dit, pour chaque situation, ce qui est en place et
que faire.

**Limite connue**, à corriger dans un lot séparé : si on donne à `analyser_seao.py` le nom d'un
export qui n'existe pas, il affiche « Erreur : fichier introuvable », mais rend le code 0. La boucle
ci-dessus ne lui passe que des fichiers présents.

**Après le lancement**, une personne tranche les cas que les programmes signalent : les organismes
à rattacher (`sorties/contexte_a_verifier.csv`), les dossiers à classer dans `demarches.csv` (leurs
numéros s'affichent à la fin du chargement) et les fournisseurs à regrouper
(`sorties/fournisseurs_a_regrouper.csv`). Le guide dit quoi faire de chacun (section 3) et donne
les nombres de notre jeu de vérification, pour comparer (section 2).

## Ce que la chaîne produit

Pour chaque export, `analyser_seao.py` écrit quatre CSV dans `sorties/<export>/`, par exemple
`sorties/mensuel_20260801_20260831/` :

| Fichier | Une ligne par | Ce qu'on y trouve |
|---|---|---|
| `details.csv` | fiche municipale | l'organisme, le dossier, le titre, les dates, les fournisseurs, le lien vers l'avis et le résultat des règles de repérage |
| `comparaison.csv` | organisme | le nombre d'avis, de contrats et d'avis liés à l'eau ou au PGA-Eau, les montants, la part de gré à gré et les fournisseurs fréquents |
| `a_enrichir.csv` | organisme | la localité et le code postal donnés par le SEAO, et le contexte : population, région, MRC, données sur l'eau |
| `qualite.csv` | point à relire | ce qui mérite une relecture dans la source : un fournisseur sans identifiant, un montant différent du montant attribué, une date d'attribution absente… Un signalement n'est pas une erreur. |

`completer_contexte.py` complète `contexte_municipalites.csv` (population, région, MRC, données sur
l'eau) et liste dans `sorties/contexte_a_verifier.csv` les cas à trancher à la main.
`charger_base.py` range les données dans la base, en quatre schémas (`territoire`, `organismes`,
`seao` et `analyses`), affiche le bilan de sa vérification contre les CSV et écrit
`sorties/fournisseurs_a_regrouper.csv`. La section 6 du guide décrit la base, avec des exemples de
requêtes.

**La carte.** `exporter_carte.py` lit la base, puis produit `carte/donnees.js`. Le navigateur lit
ce fichier quand on ouvre `carte/index.html`, sans serveur. Chaque municipalité y prend la couleur
de son état : PGA-Eau repéré, démarche liée, outil seulement ou aucune trace. Un champ de recherche
retrouve une municipalité par son nom.

## Le dépôt

```text
ift3150-ceriu-barometre/
├── analyser_seao.py             les quatre programmes de la chaîne,
├── completer_contexte.py        dans l'ordre où on les lance
├── charger_base.py
├── exporter_carte.py
├── barometre/                   le code appelé par les programmes, rangé par sujet : analyse/,
│                                contexte/, sources/, chargement/, modele/ (une classe par table),
│                                les règles et la lecture de leur fichier, et utilitaires.py, les
│                                petites fonctions partagées : texte, dates, montants, CSV
├── config/                      regles_reperage.toml, les règles de repérage, commentées
├── schema.sql                   la structure de la base, avec un commentaire par colonne
├── contexte_municipalites.csv   les fichiers tenus à la main
├── regroupements.csv
├── demarches.csv
├── carte/                       la page de la carte, et donnees.js, produit par exporter_carte.py
├── tests/                       les tests
├── notes/                       le guide détaillé et les décisions
├── docs/                        le site de suivi, construit avec zensical.toml et publié par
│                                .github/workflows/docs.yml
├── requirements.txt             les bibliothèques à installer
├── donnees_seao/                les exports du SEAO
├── donnees_reference/           les fichiers du ministère et les contours
└── sorties/                     ce que les programmes écrivent
```

`donnees_seao/`, `donnees_reference/` et `sorties/` ne sont pas versionnés : les deux premiers
contiennent des données publiques à retélécharger, le troisième ce que les programmes régénèrent,
dont les sauvegardes du contexte.

## Les tests

```powershell
python -B -m unittest -v
```

Les 184 tests portent sur de petits cas construits, sans les vrais exports ni la base. On peut les
lancer seuls après un changement du code ou des règles de repérage ; le bloc de lancement commence
aussi par eux.

## Pour aller plus loin

- **Le guide détaillé**, [notes/lancer_le_projet.md](notes/lancer_le_projet.md) : la configuration
  de la connexion, la comparaison avec notre jeu de vérification, les cas à trancher à la main, les
  changements de `schema.sql`, le dépannage, la base et le site.
- **Les décisions**, [notes/decisions.md](notes/decisions.md) : les choix du projet, avec le besoin,
  la justification et les limites de chacun.
- **Le site de suivi**, pour l'historique du projet, semaine par semaine :
  <https://nizarlakhder.github.io/ift3150-ceriu-barometre/>.
