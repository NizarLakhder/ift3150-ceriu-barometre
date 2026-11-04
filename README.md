# Baromètre CERIU (projet IFT3150)

Projet IFT3150, Université de Montréal, automne 2026.
Étudiant : Nizar Lakhder. Superviseur : Louis-Édouard Lafontant.
Partenaire : CERIU, Pôle Données & Informations.

Le projet mesure jusqu'où les données publiques permettent de suivre les démarches de gestion
d'actifs des municipalités québécoises, en commençant par le plan de gestion des actifs en eau
(PGA-Eau).

Site de suivi : <https://nizarlakhder.github.io/ift3150-ceriu-barometre/>

## État au 3 novembre 2026

- **7 exports du SEAO lus en entier** : les mois de mai, août et septembre 2026, et quatre semaines
  de septembre et d'octobre, soit 28 611 fiches municipales distinctes, rangées dans une base
  PostgreSQL de 21 tables.
- **33 dossiers liés à la gestion des actifs en eau**, tous classés à la main dans `demarches.csv` :
  15 repérés par la règle PGA-Eau, et 18 par un repérage plus large (8 plans d'intervention des
  réseaux d'eau, un plan de gestion de tous les actifs, 3 démarches voisines et 6 logiciels).
- **L'état de chaque municipalité** : 10 ont un PGA-Eau repéré dans le SEAO, 16 une démarche liée,
  et 1 255 aucune trace dans les exports chargés, ce qui ne veut pas dire qu'elles n'ont pas de plan.
- **Le contexte municipal** : 934 des 1 042 organismes rencontrés sont rattachés au répertoire du
  ministère, avec leur population. Les 108 autres ne sont pas des municipalités.
- **77 tests automatisés.** Les mêmes fichiers donnent toujours les mêmes chiffres.

## Ce que les données montrent

**Le SEAO ne montre qu'une partie d'une démarche** : le mandat confié à une firme ou à un organisme
externe. Une municipalité absente du SEAO peut faire son plan à l'interne, ou payer un mandat sous
le seuil de publication. Et un contrat prouve qu'un mandat a été confié, pas qu'un plan existe.

| Étape officielle du PGA-Eau | Ce que le SEAO montre | Ce qui manque |
|---|---|---|
| S'engager, avant le 31 décembre 2026 | rien | la résolution du conseil municipal |
| Produire le plan | un avis, un contrat, un fournisseur, un montant, des dates | le plan lui-même et sa conformité |
| Suivi annuel, à partir de 2028 | rien | les rapports transmis au ministère |

- **Le mot « PGA-Eau » ne suffit pas.** Windsor écrit « PGA – Eau » avec un tiret long, et
  Mont-Tremblant n'emploie pas l'acronyme. Le filtre large « lié à l'eau » les trouve, mais parmi
  749 fiches pour le seul mois d'août. Et le repérage ne voit pas un mandat dont le titre et la
  description n'emploient aucun de ces mots.
- **Une fiche n'est pas un contrat.** Dans la semaine du 7 septembre 2026, seulement 403 des 1 561
  fiches municipales portent sur un avis ouvert cette semaine-là; la plus ancienne remonte à 2013.
  Un même dossier revient d'un export à l'autre : 476 paraissent à la fois dans cette semaine et
  dans le mois d'août.
- **Aucun montant n'est une dépense payée.** Le SEAO publie un montant attribué, un montant de
  contrat et un `totalAmount` dont le sens reste à valider. Le montant estimé de l'appel d'offres
  n'est jamais publié pour les acheteurs municipaux.
- **Les petits mandats passent inaperçus.** Seulement 8,5 % des contrats d'achat chiffrés de la
  semaine, et 7,9 % de ceux d'août, sont sous 25 000 \$. La semaine compte 18 contrats entre
  20 000 et 25 000 \$, contre 58 entre 25 000 et 30 000 \$ : sans doute l'effet de l'obligation de
  publication.
- **Le SEAO écrit mal certains noms** : « St » pour Saint, un « de » oublié, « Rougement » pour
  Rougemont. Le rattachement au répertoire les tolère, mais seulement si un indice publié le
  confirme : code postal, désignation ou région. Sur 36 907 fautes introduites exprès dans les noms
  officiels, 83 % sont retrouvées, et aucune ne mène à une mauvaise municipalité. Les 18 cas
  qu'aucun indice ne tranchait ont été réglés à la main, chacun avec sa source publique.
- **Les fichiers du ministère ont trois défauts, contournés.** Le répertoire abrège « Comm.
  métropolitaine de Montréal », et la communauté recevait la population de la Ville : 1,9 million
  d'habitants au lieu de 4,3. Les noms des organismes périmunicipaux sont coupés à 60 caractères
  (132 organismes sur 338). Deux fichiers de la Stratégie perdent le zéro du début des codes :
  « 3005 » pour Gaspé.
- **Le SEAO republie parfois une fiche autrement** : 103 des 2 132 fiches communes à deux exports
  changent d'étiquettes, ou du rôle d'une entreprise.
- **Les plans de gestion des actifs des bâtiments sont visibles eux aussi**, à Dollard-des-Ormeaux,
  Pointe-Claire ou Repentigny : la même méthode pourra servir pour eux.
- **Un petit modèle de langage**, qwen2.5 à 3 milliards de paramètres, installé avec Ollama, remplit
  correctement 14 champs précis d'une seule fiche. Mais invité à analyser cinq fiches à la fois, il
  ne reconnaît aucun des trois dossiers PGA-Eau, et il coupe sans prévenir un message trop long
  pour sa fenêtre de lecture.

Le détail, semaine par semaine, est sur le site de suivi.

## La base de données

`charger_base.py` range les données dans PostgreSQL, en quatre groupes, chacun dans son schéma :
21 tables et 5 vues.

| Groupe | Ce qu'il contient |
|---|---|
| `territoire` | le répertoire du ministère : régions, MRC, municipalités avec leurs anciens codes, données sur l'eau |
| `organismes` | qui achète : l'organisme réel et ses identifiants d'acheteur dans le SEAO |
| `seao` | les exports chargés et les fiches, découpées en tables : dossier, fiche, attribution, contrat, fournisseur… |
| `analyses` | le classement des fiches, les démarches classées à la main et les vues de consultation |

- **Des numéros attribués par la base**, sauf pour les codes officiels : région, MRC, code
  géographique, nomenclature du SEAO, UNSPSC. L'identifiant publié devient une colonne unique, car
  une fiche ne s'identifie qu'avec deux numéros, et une entreprise a parfois plusieurs
  identifiants `FO`.
- **Une fiche, plusieurs exports** : une fiche n'est copiée qu'une fois, et `seao.fiche_fichier` la
  relie à chaque export où elle figure, avec la version publiée si elle diffère.
- **Des valeurs permises** : les statuts, les modes de sollicitation, les étiquettes, la devise et
  nos catégories ont chacun leur type énuméré. Une valeur inconnue arrête le chargement.
- **Un commentaire pour chaque colonne**, dans `schema.sql`.

À chaque chargement, un export déjà chargé est reconnu par son empreinte, et la base doit redonner
les chiffres d'`analyser_seao.py`, export par export : les mêmes fiches, la même somme des montants
attribués, les mêmes dossiers repérés. La vue `analyses.contrat_courant` compte chaque contrat une
seule fois, dans sa dernière version.

## Contenu du dépôt

| Emplacement | Contenu |
|---|---|
| `analyser_seao.py` | lit un export du SEAO et produit quatre tableaux |
| `completer_contexte.py` | complète le contexte municipal avec les fichiers du ministère |
| `charger_base.py` | range le tout dans PostgreSQL, puis vérifie le résultat |
| `utilitaires.py` | les petites fonctions partagées : texte, dates, montants, CSV |
| `schema.sql` | la structure de la base |
| `contexte_municipalites.csv` | le contexte de chaque organisme : les programmes y ajoutent des lignes et remplissent les cases « À compléter », sans jamais écraser une valeur |
| `regroupements.csv` | les municipalités regroupées depuis 2025, avec leurs sources officielles |
| `demarches.csv` | les démarches de gestion des actifs en eau, une ligne par dossier, classées à la main avec leur source |
| `test_*.py` | les 77 tests, sur de petits cas construits, sans les vrais exports ni la base |
| `requirements.txt` | les bibliothèques à installer |
| `docs/`, `zensical.toml`, `.github/workflows/docs.yml` | le site de suivi et sa publication |

Les dossiers `donnees_seao/`, `donnees_reference/` et `sorties/` ne sont pas versionnés : les deux
premiers contiennent des données publiques retéléchargeables, le troisième ce que les programmes
régénèrent.

## Lancer l'analyse

Il faut Python 3.10 ou plus récent.

```powershell
pip install -r requirements.txt

python analyser_seao.py                                  # l'export de la semaine du 7 septembre 2026
python analyser_seao.py mensuel_20260801_20260831.json   # un autre export de donnees_seao/
python completer_contexte.py                             # après l'analyse : il y lit les codes postaux
python charger_base.py                                   # voir « Préparer la base de données »
python -B -m unittest -v                                 # les 77 tests
```

Après `completer_contexte.py`, relancez l'analyse pour que `sorties/` en tienne compte. Les tableaux
sont écrits dans un dossier par export, comme `sorties/mensuel_20260801_20260831/`, et remplacés à
chaque exécution. Les fichiers tenus à la main sont `contexte_municipalites.csv`,
`regroupements.csv` et `demarches.csv`. Pour régler un cas de contexte, il suffit d'écrire le code
géographique de l'organisme : le programme remplit le reste.

## Préparer la base de données

Il faut PostgreSQL 13 ou plus récent; le projet est testé avec la version 18. Une seule fois :

1. Créer un compte et une base réservés au projet, en administrateur :

   ```sql
   CREATE ROLE barometre LOGIN PASSWORD 'un-mot-de-passe';
   CREATE DATABASE barometre OWNER barometre;
   ```

2. Écrire ce mot de passe dans le fichier de mots de passe de PostgreSQL, hors du projet :
   `%APPDATA%\postgresql\pgpass.conf` sous Windows, `~/.pgpass` ailleurs.

   ```text
   localhost:5433:barometre:barometre:un-mot-de-passe
   ```

3. Lancer `python charger_base.py`. Il crée les tables si elles n'existent pas, charge ce qui
   manque, puis compare la base aux tableaux d'`analyser_seao.py`. Un export déjà chargé est laissé
   de côté. Après une modification de `schema.sql`, `python charger_base.py --reinitialiser` efface
   tout et recharge.

La connexion par défaut est `localhost`, port 5433, compte et base `barometre`. Les variables
`BAROMETRE_HOTE`, `BAROMETRE_PORT`, `BAROMETRE_BASE` et `BAROMETRE_COMPTE` permettent d'en changer.

Deux exemples de requêtes :

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

## Obtenir les données

Les programmes ne téléchargent rien : les fichiers se déposent à la main.

- **Les exports du SEAO**, dans `donnees_seao/` : le jeu « Système électronique d'appel d'offres
  (SEAO) » sur Données Québec,
  <https://www.donneesquebec.ca/recherche/dataset/systeme-electronique-dappel-doffres-seao>.
- **Le contexte municipal**, dans `donnees_reference/` : deux jeux du ministère des Affaires
  municipales et de l'Habitation sur Données Québec, le
  [Répertoire des municipalités du Québec](https://www.donneesquebec.ca/recherche/dataset/repertoire-des-municipalites-du-quebec)
  et la
  [Stratégie québécoise d'économie d'eau potable 2019-2025](https://www.donneesquebec.ca/recherche/dataset/sqeep-2019-2025).

| Jeu de données | Ressource à prendre | Fichier |
|---|---|---|
| Répertoire des municipalités du Québec | Liste des municipalités (csv) | `MUN.csv`, obligatoire |
| Répertoire des municipalités du Québec | Liste des MRC_CM_Arg (csv) | `MRC_CM_Arg.csv` |
| Répertoire des municipalités du Québec | Liste des organismes périmunicipaux | `A01_CONVERT_XML_ORG_PER_MUN.xml` |
| Stratégie québécoise d'économie d'eau potable 2019-2025 | validité des audits 2024, par classe de population | `validite_classe_2024.csv` |
| Stratégie québécoise d'économie d'eau potable 2019-2025 | indice de fuites 2024, par classe de population | `fuites_classe_2024.csv` |
| Stratégie québécoise d'économie d'eau potable 2019-2025 | consommation résidentielle 2024, par classe de population | `consommation_classe_2024.csv` |

Les cas réglés à la main s'appuient sur d'autres sources publiques : les pages d'avis du SEAO, les
avis republiés sur le site fédéral AchatsCanada, qui donnent l'adresse de l'acheteur quand la fiche
ne la donne pas, les annonces de regroupement du gouvernement du Québec et un avis du ministère de
la Justice. Chacune est citée dans la page [Références](docs/references.md) du site et dans la
colonne `notes` du fichier de contexte.

Ces données sont publiées sous licence Creative Commons avec attribution. Les échéances du PGA-Eau
viennent de la page « Préparer un plan de gestion des actifs en eau », sur quebec.ca.

## Questions ouvertes

1. **Qu'est-ce qui compte comme trace de démarche?** Un accompagnement à 4 892 \$, comme celui de
   Matagami, vaut-il un mandat d'élaboration du plan?
2. **Que faire des 108 organismes non municipaux?** Quand une régie mène un PGA-Eau, comme la Régie
   d'aqueduc de Grand Pré, les municipalités qu'elle dessert restent « sans trace ». Faut-il les
   rattacher au territoire desservi, ou montrer les régies à part?
3. **Que faire des municipalités regroupées?** Un contrat signé par Saint-Bruno avant son
   regroupement est rattaché à Hébertville, avec sa population actuelle : la convention reste à
   valider.
4. **Comment mesurer ce que la méthode rate?** Une liste de référence, même partielle, de
   municipalités engagées dans une démarche permettrait de le mesurer plutôt que de l'estimer.

## Prochaines étapes

1. Mettre la base à l'essai sur Supabase, une base PostgreSQL hébergée.
2. Regrouper les entreprises inscrites plusieurs fois : `sorties/fournisseurs_a_regrouper.csv` en
   propose 91 groupes, à vérifier à la main.
3. Essayer un autre petit modèle de langage avec Ollama, et le comparer à qwen2.5.
4. Décider de la place des organismes non municipaux (question 2).
5. Construire l'interface du baromètre à partir des vues de la base, avec des comparaisons ajustées
   à la population.
6. Ajouter le type de milieu, d'après la classification de Statistique Canada par zones d'influence
   métropolitaine.
7. Suivre une démarche de bout en bout pour une municipalité, avec la résolution du conseil et la
   publication du plan, trouvées dans d'autres sources publiques.

## Le site de suivi

```powershell
zensical serve --open     # ou : python -m zensical serve --open
```

Le site s'ouvre à <http://localhost:8000>. Chaque push sur `main` le reconstruit et le publie sur
GitHub Pages; le réglage à faire une seule fois dans GitHub est Settings, Pages, Build and
deployment, Source « GitHub Actions ». Il est construit avec Zensical, à partir du modèle du cours
IFT3150.
