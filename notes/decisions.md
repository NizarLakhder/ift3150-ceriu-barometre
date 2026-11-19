# Les décisions du projet

Pour chaque choix : le besoin, le choix, sa justification et ses limites. Une alternative n'est
nommée que si une trace écrite et datée montre qu'elle a été envisagée à l'époque. Chaque
justification dit si elle a été notée à l'époque, et où, ou si elle est donnée aujourd'hui, le
18 novembre 2026. Les chiffres du 18 novembre 2026 viennent du jeu de vérification décrit dans
[lancer_le_projet.md](lancer_le_projet.md).

## Les données

### 1. Les exports du SEAO comme source

- **Besoin :** suivre avec des données publiques les démarches de gestion des actifs en eau des
  municipalités.
- **Choix :** les exports JSON du SEAO publiés sur Données Québec, lus en entier ; seules les fiches
  dont l'acheteur est municipal sont gardées. Le JSON fait foi : le chargement le relit, et les CSV
  de l'analyse servent à vérifier le chargement, à consulter les résultats et à relire les données.
- **Justification, donnée aujourd'hui :** les municipalités publient dans le SEAO leurs appels
  d'offres et leurs contrats, et ses exports sont publics, réguliers et lisibles par un programme.
- **Limites :** le SEAO ne permet pas, à lui seul, de savoir si le plan est terminé ou adopté. Ni
  l'engagement du conseil, attendu avant le 31 décembre 2026, ni le plan lui-même, ni les rapports
  annuels attendus à partir de 2028 n'y figurent (échéances de la page « Préparer un plan de gestion
  des actifs en eau », sur quebec.ca). Une municipalité peut faire son plan à l'interne, ou payer un
  mandat sous le seuil de publication. Une fiche est l'état d'un dossier au moment de l'export, pas
  un nouveau contrat, et aucun montant publié n'est une dépense payée.

### 2. Des fichiers déposés à la main

- **Besoin :** que les mêmes fichiers donnent toujours les mêmes chiffres.
- **Choix :** aucun programme ne télécharge les exports ni les fichiers du ministère, et la date de
  chaque fichier de référence est notée avec les valeurs qu'il a fournies. Seuls les contours de la
  carte sont téléchargés, une fois, par `exporter_carte.py`.
- **Justification, notée à l'époque :** « Les mêmes fichiers donnent toujours les mêmes résultats, et
  la date de chaque fichier utilisé est inscrite dans le contexte » (README du 30 septembre 2026).
- **Limites :** chaque mise à jour demande de télécharger et de déposer les fichiers à la main. Les
  contours viennent d'un service du ministère des Ressources naturelles et des Forêts, que le projet
  ne contrôle pas.

## La base de données

### 3. Une base, en plus des fichiers

- **Besoin :** cumuler les exports sans compter deux fois ce qu'ils ont en commun.
- **Choix :** une base PostgreSQL. Une fiche n'y est copiée qu'une fois, et `seao.fiche_fichier` la
  relie à chaque export où elle figure.
- **Justification, notée à l'époque :** « Construire la base PostgreSQL pour cumuler les périodes
  sans double compte » (site de suivi, semaine 6, du 5 au 11 octobre 2026). Le 18 novembre 2026,
  2 132 des 28 611 fiches figuraient dans deux exports.
- **Limites :** un logiciel à installer et à configurer, et deux calculs à garder d'accord, celui
  des CSV et celui de la base : d'où la vérification à la fin de chaque chargement (décision 8).

### 4. PostgreSQL

- **Besoin :** des montants exacts, de vraies dates, et une recherche qui tolère les accents et les
  noms proches.
- **Choix :** PostgreSQL, version 13 ou plus récente.
- **Alternative envisagée :** SQLite, proposée dans une note de travail d'octobre 2026, puis écartée.
- **Justification, notée à l'époque :** « La base sera PostgreSQL plutôt que SQLite : les montants y
  restent exacts au cent près, les dates sont de vraies dates, et la recherche sans accents ou par
  noms proches y est intégrée » (site de suivi, semaine 6).
- **Justification, donnée aujourd'hui,** à une question posée par le superviseur le 11 novembre
  2026, « pourquoi PostgreSQL plutôt que MongoDB » : nos questions relient des tables (quelle
  municipalité derrière quels identifiants d'acheteur, quel export contient quelle fiche), la base
  garantit ces liens par ses contraintes, et elle garde aussi chaque fiche entière (décision 6).
  Aucune trace ne montre qu'une base de documents ait été envisagée avant ce choix.
- **Limites :** un schéma à maintenir. La version 13 est la minimale justifiée : `schema.sql`
  installe les extensions `unaccent` et `pg_trgm`, qu'un compte non administrateur ne peut installer
  qu'à partir de cette version. Versions essayées : 18, avec le schéma actuel, et 17 sur Supabase,
  avec le schéma du 4 novembre 2026 ; cette copie sur Supabase n'a pas suivi les changements
  suivants.

### 5. Le découpage en tables

- **Besoin :** relier sans ambiguïté les fiches, les dossiers, les exports, les acheteurs et les
  entreprises.
- **Choix**, fait le 1er novembre 2026 d'après les retours du superviseur du 28 octobre : des
  numéros attribués par la base, sauf pour les codes officiels (région, MRC, code géographique,
  nomenclature du SEAO, UNSPSC) ; le dossier séparé de la fiche ; une ligne par export et un lien
  entre fiche et export ; des types énumérés, pour qu'une valeur inconnue arrête le chargement ; les
  étiquettes en tableau dans la fiche ; les anciens codes dans la municipalité ; les entreprises et
  leurs identifiants FO dans deux tables.
- **Alternative envisagée :** pour les FO, une colonne qui liste les identifiants d'une entreprise,
  suggérée le 28 octobre. Une table de correspondance a été retenue le 1er novembre : la base
  garantit alors qu'un FO n'appartient qu'à une seule entreprise.
- **Justification, notée à l'époque** (README du 3 novembre 2026) : une fiche ne s'identifie
  qu'avec deux numéros, et une entreprise a parfois plusieurs identifiants FO. Le 18 novembre 2026 :
  28 611 fiches pour 24 862 dossiers, 1 479 numéros de fiche portés par plus d'un dossier, et
  42 identifiants d'acheteur pour la seule Ville de Montréal.
- **Limites :** le regroupement automatique par NEQ existe ; le 18 novembre 2026, il ne réunissait
  aucun identifiant (12 782 entreprises pour 12 782 FO). Les rapprochements proposés sur la base du
  nom dans `fournisseurs_a_regrouper.csv` (91 groupes) ne sont pas appliqués automatiquement.

### 6. La fiche entière, gardée en JSONB

- **Besoin :** reclasser les fiches ou ajouter une colonne sans relire les exports, et voir ce qui
  change quand le SEAO republie une fiche.
- **Choix :** chaque fiche garde sa version complète (colonne `brut`) ; quand un autre export la
  publie autrement, `seao.fiche_fichier` garde cette autre version.
- **Justification, donnée aujourd'hui :** c'est ce qui permet au chargement de reclasser toutes les
  fiches à chaque passage. Le 18 novembre 2026, 103 des 2 132 fiches présentes dans deux exports y
  étaient publiées autrement : d'autres étiquettes, ou une entreprise qui change de rôle.
- **Limites :** de la place, et une information en double avec les colonnes.

### 7. Les vues

- **Besoin :** définir une règle à un seul endroit, et offrir des tables prêtes à lire.
- **Choix :** cinq vues, dont `analyses.etat_pga_eau`, l'état de chaque municipalité, et
  `analyses.contrat_courant`, chaque contrat compté une fois, dans sa dernière version.
- **Justification, donnée aujourd'hui :** la règle de calcul est définie à un seul endroit, dans une
  vue ordinaire dont la requête s'exécute lorsqu'elle est consultée ; `exporter_carte.py` lit cette
  vue telle quelle.
- **Limites :** une vue que rien n'utilise est du code à maintenir pour rien. Le 11 novembre 2026,
  le superviseur a demandé de justifier chaque vue et de retirer celles qui ne servent pas à
  l'interface ; cette revue reste à faire.

### 8. Un chargement par étapes, vérifié à la fin

- **Besoin :** ne jamais laisser un export à moitié chargé, pouvoir relancer après une panne, et
  savoir si la base redonne les chiffres de l'analyse.
- **Choix :** une transaction par étape : les schémas, le territoire et les organismes, chaque
  export, le classement et les démarches. Un export déjà chargé est reconnu par son empreinte et
  sauté ; un export modifié sous le même nom est refusé. À la fin, la base est comparée aux CSV,
  export par export (mêmes fiches, même somme des montants attribués, mêmes fiches PGA-Eau, mêmes
  familles), avec un code de sortie : 0 si tout concorde, 1 pour un écart ou une erreur, 2 si la
  vérification est incomplète. La connexion se règle par des variables ; le mot de passe
  reste dans le fichier `pgpass.conf` de chaque utilisateur, jamais dans le projet.
- **Justification, notée à l'époque :** le README du 3 novembre 2026 pour l'empreinte et la
  comparaison aux CSV ; la vérification plus stricte et ses codes de sortie datent du 11 novembre
  2026.
- **Limites :** une erreur n'annule que l'étape en cours, et un code final 1 ou 2 n'annule rien.
  `schema.sql` n'est appliqué que si le schéma `seao` est absent : un changement de structure demande
  `--reinitialiser`. Cette option supprime les quatre schémas avec `DROP SCHEMA … CASCADE`, donc
  aussi les objets qui en dépendent ailleurs dans la base. La suppression et la recréation forment
  une seule transaction, mais le rechargement qui suit se fait par étapes.

## Le repérage

### 9. Des règles qui proposent, une personne qui classe

- **Besoin :** trouver, parmi des dizaines de milliers de fiches, les appels d'offres et les
  contrats liés à la gestion des actifs en eau.
- **Choix :** trois règles, de la plus large à la plus précise. Elles proposent ; chaque dossier est
  ensuite classé à la main dans `demarches.csv`, avec sa source.
  - « Lié à l'eau » lit le titre et les libellés de classification (UNSPSC) : 3 264 des 28 611
    fiches le 18 novembre 2026.
  - La règle PGA-Eau lit le titre seulement : 15 dossiers.
  - Le repérage large, en six familles, lit le titre, et y ajoute la description pour trois tests :
    l'acronyme PGA-Eau, le cadre d'une étape (« dans le cadre d'un… ») et le mot de réseau d'eau d'un
    plan d'intervention. Il propose 33 dossiers.
- **Justification, notée à l'époque :** les champs `source` et `limites` de chaque règle, dans
  `config/regles_reperage.toml`.
- **Limites :** un mandat dont ces textes ne nomment pas le plan passe inaperçu. Ce n'est pas un
  taux de détection : les
  dossiers retrouvés à la lecture avaient eux-mêmes été trouvés par leur titre, et aucune liste de
  référence ne permet encore de mesurer ce que la méthode rate. Ce qui compte comme trace reste à
  préciser : un accompagnement à 4 892 \$, comme celui de Matagami, vaut-il un mandat
  d'élaboration ?

### 10. Les règles dans un fichier de configuration

- **Besoin :** changer un mot-clé sans toucher au Python, comme l'a demandé le superviseur le
  11 novembre 2026.
- **Choix :** les mots et les motifs dans `config/regles_reperage.toml`, depuis le 17 novembre 2026.
  Le fichier est validé à son premier usage : s'il est invalide, l'analyse ne lit ni n'écrit rien,
  et le chargement n'ouvre aucune connexion. La version des règles, une empreinte de ce fichier,
  d'`analyser_seao.py`, d'`utilitaires.py` et de tout `barometre/`, est notée avec le classement de
  chaque fiche.
- **Alternatives envisagées :** YAML et CSV, pesés dans le plan de restructuration du 12 novembre
  2026.
- **Justification, notée à l'époque** (même plan) : un TOML se lit facilement, accepte des
  commentaires, et Python le lit sans bibliothèque de plus ; YAML en demandait une, et un CSV se prête
  mal aux motifs et aux explications.
- **Limites :** l'ordre des tests et la préparation du texte restent dans `barometre/regles.py`.
  Toute modification de ces fichiers, même d'un commentaire, change la version des règles.

### 11. « Aucune trace », jamais « pas de plan »

- **Besoin :** dire l'état de chaque municipalité sans conclure plus que les données.
- **Choix :** quatre états, calculés par la vue `analyses.etat_pga_eau` à partir des démarches
  classées : PGA-Eau repéré (une démarche d'élaboration ou une étape), démarche liée repérée (plan
  d'intervention, démarche voisine…), outil seulement, et aucune trace dans les exports chargés. Le
  18 novembre 2026 : 10, 11, 5 et 1 255 municipalités. L'état « outil seulement » a été séparé des
  démarches liées le 11 novembre 2026.
- **Justification, notée à l'époque :** le commentaire de la vue dans `schema.sql` : « Un logiciel
  de gestion d'actifs n'est pas une démarche de plan : il a son propre état. Jamais « pas de plan » :
  une partie des mandats ne passe pas par le SEAO. »
- **Limites :** une démarche portée par une régie ou une MRC ne change l'état d'aucune
  municipalité ; la façon de la montrer reste à décider.

## Le contexte municipal

### 12. Le rattachement au répertoire du ministère

- **Besoin :** connaître la municipalité derrière chaque acheteur, avec sa population et sa région.
- **Choix :** dans l'ordre, le code géographique déjà inscrit (c'est ainsi qu'on règle un cas à la
  main), le nom exact, puis une règle tolérante (« St » pour Saint, un « de » oublié, une faute de
  frappe), qui exige un indice publié : code postal, désignation ou région. Sans indice, rien n'est
  rempli, et le cas va dans `sorties/contexte_a_verifier.csv`.
- **Justification, notée à l'époque :** « Un homonyme n'est départagé qu'avec un indice publié »
  (site de suivi, semaine 6). En octobre 2026, sur 36 907 fautes introduites exprès dans les noms
  officiels, 83 % ont été retrouvées, et aucune n'a mené à une mauvaise municipalité (site de suivi,
  page Synthèse ; le script de cet essai n'est pas dans le dépôt).
- **Limites :** le 18 novembre 2026, 2 cas restent à trancher (deux régies au nom mal écrit), et
  106 organismes ne sont pas des municipalités. Le type de milieu n'est dans aucun des fichiers
  utilisés. Les fichiers du ministère ont des défauts que le code contourne : des codes sans leur
  zéro initial, des noms coupés.

### 13. Le fichier de contexte, tenu à la main

- **Besoin :** garder la saisie humaine, que les programmes ne doivent jamais écraser.
- **Choix :** les programmes ajoutent des lignes et remplissent les cases « À compléter », sans
  jamais remplacer une valeur. Le fichier est lu strictement (UTF-8, en-tête, nombre de colonnes,
  guillemets) et réécrit d'un seul coup, avec une sauvegarde de l'ancien contenu dans `sorties/`.
- **Justification, notée à l'époque :** pour l'analyse, « Le fichier de contexte peut recevoir de
  nouvelles lignes, mais une ligne existante n'est jamais modifiée » (site de suivi, semaine 6) ;
  pour le complément, « Une valeur déjà présente n'est jamais remplacée » (`completer_contexte.py`).
  La lecture stricte et la réécriture d'un seul coup datent du 18 novembre 2026 : des essais avaient
  montré qu'une virgule de trop pouvait laisser le fichier presque vide.
- **Limites :** le contrôle d'une modification pendant l'écriture n'est pas un verrou : il faut
  éviter de lancer deux programmes en même temps sur ce fichier. La sauvegarde
  (`contexte_municipalites.csv.bak` pour le complément, `contexte_municipalites.csv.avant_ajout`
  pour l'analyse) n'existe qu'après une première réécriture, et peut être ancienne. Si l'écriture
  échoue pendant le remplacement, le message dit si le nouveau contenu est en place et nomme la copie
  à garder, souvent un fichier `.tmp`.

### 14. Les municipalités regroupées et les organismes non municipaux

- **Besoin :** rattacher un contrat même quand la municipalité a changé depuis, et ne pas compter
  une régie ou une société comme une municipalité.
- **Choix :** `regroupements.csv` donne chaque regroupement depuis 2025, avec sa source officielle,
  et la municipalité garde ses anciens codes. Les organismes non municipaux restent dans la base,
  sans état sur la carte.
- **Justification, donnée aujourd'hui :** un contrat ne doit pas se perdre parce qu'une
  municipalité a été regroupée, et une régie n'a ni population ni contour de municipalité.
- **Limites :** un contrat signé avant un regroupement est rattaché à la nouvelle municipalité, avec
  sa population actuelle, comme celui de Saint-Bruno, rattaché à Hébertville : la convention reste à
  valider.

## Le code et la carte

### 15. Des programmes courts, le code dans `barometre/`

- **Besoin :** un code qu'une autre personne peut reprendre, comme l'a demandé le superviseur le
  11 novembre 2026.
- **Choix :** les quatre commandes restent à la racine. Trois d'entre elles, `analyser_seao.py`,
  `completer_contexte.py` et `charger_base.py`, ne font plus qu'enchaîner les étapes, et leur code
  est rangé par sujet dans `barometre/`. Un test vérifie que `barometre/` n'importe jamais un
  programme.
- **Justification, notée à l'époque :** plan de restructuration du 12 novembre 2026 : rien ne change
  pour la personne qui lance les commandes.
- **Limites :** `exporter_carte.py` garde encore ses traitements : il ne prend dans `barometre/` que
  la connexion. Les trois autres réexportent encore les noms déplacés, pour les tests et les outils
  qui les importent.

### 16. Une classe simple par table

- **Besoin :** écrire chaque table de la même façon, sans répéter le SQL.
- **Choix :** une `dataclass` par table, dans `barometre/modele/`, qui décrit ses colonnes et écrit
  ses lignes dans la transaction du programme.
- **Alternative envisagée :** SQLAlchemy, écarté dans le plan de restructuration du 12 novembre
  2026.
- **Justification, notée à l'époque** (même plan) : avec SQLAlchemy, il aurait fallu décrire la base
  une deuxième fois à côté de `schema.sql`, et apprendre un outil de plus.
- **Limites :** les colonnes sont tout de même écrites deux fois, dans `schema.sql` et dans les
  classes ; un test vérifie que chaque classe décrit exactement sa table.

### 17. Des tests, et une restructuration vérifiée contre une référence

- **Besoin :** changer l'organisation du code sans changer les résultats.
- **Choix :** 184 tests sur de petits cas construits, sans les vrais exports ni la base ; une valeur
  attendue n'est jamais modifiée pour faire passer un test. La restructuration des 17 et 18 novembre
  2026 a été vérifiée lot par lot contre une exécution de référence, faite le 17 novembre sur le
  commit `763ab78` puis figée : mêmes CSV, même base et même carte.
- **Justification, notée à l'époque :** plan de restructuration du 12 novembre 2026, et décision du
  17 novembre pour la référence.
- **Limites :** les tests ne lisent pas les vrais exports. Les outils de la vérification par
  référence (scripts, journaux, base dédiée) ne sont pas fournis dans ce dépôt.

### 18. La carte

- **Besoin :** voir d'un coup d'œil l'état de chaque municipalité.
- **Choix :** `exporter_carte.py` lit la base (la vue `etat_pga_eau` et les démarches) et les
  contours officiels des municipalités, puis produit `carte/donnees.js`. Le navigateur lit ce
  fichier quand on ouvre `carte/index.html`, sans serveur.
- **Justification, donnée aujourd'hui :** la règle de l'état reste dans la base, et la page s'ouvre
  sur n'importe quel poste.
- **Limites :** la carte montre la base au moment de l'export. Elle demande Internet pour Leaflet et
  le fond OpenStreetMap. Les contours, simplifiés à environ 300 m, viennent d'un service extérieur.

### 19. Le petit modèle de langage, mis de côté

- **Besoin :** le CERIU souhaite qu'un modèle de langage aide à trancher les cas ambigus.
- **Choix :** des essais avec qwen2.5, un modèle de 3 milliards de paramètres lancé localement avec
  Ollama ; le modèle est mis de côté pour l'instant.
- **Justification, notée à l'époque :** « Un modèle simple sait extraire des champs précis d'une
  fiche, mais pas analyser un ensemble de fiches » (site de suivi, semaine 6). Il remplissait
  correctement 14 champs d'une seule fiche, mais avec cinq fiches à la fois, il ne reconnaissait
  aucun des trois dossiers PGA-Eau, et il coupait sans prévenir un message trop long. Un second
  essai, sur 61 dossiers, n'a écarté aucun des 28 pièges (site de suivi, semaine 10, du 2 au
  8 novembre 2026).
- **Limites :** un seul modèle, petit, avec des consignes peut-être pas assez claires ; un autre
  modèle reste à essayer.
