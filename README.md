# Baromètre CERIU — Projet IFT3150

Projet IFT3150, Université de Montréal, automne 2026.
Étudiant : Nizar Lakhder. Superviseur : Louis-Édouard Lafontant.
Partenaire : CERIU, Pôle Données & Informations.

Le projet cherche à savoir jusqu'où les données publiques permettent de suivre les démarches de
gestion d'actifs des municipalités québécoises, en commençant par le plan de gestion des actifs en
eau (PGA-Eau). L'objectif n'est pas encore de produire un tableau de bord, mais de mesurer ce que les
données permettent réellement d'observer, et d'en documenter les limites.

Site de suivi : <https://nizarlakhder.github.io/ift3150-ceriu-barometre/>

Ce document résume ce qui a été fait à ce jour, ce que les données montrent, les questions qui
restent ouvertes, puis la façon de relancer le travail.

**État au 30 septembre 2026.** Deux exports du SEAO ont été analysés : la semaine du 7 au
13 septembre 2026, qui sert de référence, et le mois d'août 2026. Pour le mois, le contexte des
367 organismes absents de la semaine n'est pas encore créé, et la règle propre au PGA-Eau n'est
pas encore dans le programme.

## En bref

- **Le SEAO laisse voir des démarches PGA-Eau, mais seulement une partie.** On voit les mandats
  confiés à une firme ou à un organisme externe. On ne voit ni l'engagement du conseil municipal, ni
  le dépôt du plan au ministère.
- **Reconnaître une démarche est plus difficile qu'extraire les données.** L'export d'août contient
  quatre dossiers PGA-Eau ; chercher le mot « PGA-Eau » en trouve deux, et le filtre large « lié à
  l'eau » les trouve tous, mais parmi 749 fiches. La semaine de septembre en ajoute un cinquième, à
  Matagami.
- **Les petits contrats sont presque invisibles.** Seulement 8,5 % des contrats d'achat chiffrés de
  la semaine, et 7,9 % de ceux d'août, sont sous 25 000 $. Il y en a plus de trois fois plus juste
  au-dessus du seuil que juste en dessous.
- **Le contexte municipal est rattaché automatiquement** pour 286 des 346 organismes : population,
  superficie, région, MRC, et l'état du réseau d'eau pour 188 d'entre eux.
- **Tout est reproductible** : deux programmes Python sans dépendance externe, 23 tests, et les mêmes
  fichiers donnent toujours les mêmes chiffres.

## Ce qui a été fait

1. **Comprendre la structure réelle du SEAO.** Deux exports ont été lus en entier, sans
   échantillon : la semaine du 7 au 13 septembre 2026 et le mois d'août 2026. Les points établis sont
   résumés plus bas.
2. **Extraire et structurer.** `analyser_seao.py` garde les acheteurs que le SEAO marque comme
   municipaux et produit quatre tableaux : le détail par fiche, un résumé par organisme, le contexte
   de chaque organisme et une liste de points à relire. Chaque ligne renvoie à son avis public.
3. **Ajouter le contexte municipal.** `completer_contexte.py` rattache chaque organisme au Répertoire
   des municipalités et aux données de la Stratégie québécoise d'économie d'eau potable, deux jeux du
   ministère des Affaires municipales et de l'Habitation.
4. **Préparer le repérage des démarches.** Le programme marque aujourd'hui les fiches liées à l'eau au
   sens large. Une règle propre au PGA-Eau est en préparation.
5. **Documenter la qualité des données**, pour savoir ce qu'il faut relire avant de compter.

| | Semaine du 7 au 13 sept. 2026 | Mois d'août 2026 |
|---|---:|---:|
| Fiches dans l'export | 3 890 | 15 423 |
| Fiches d'acheteurs municipaux | 1 561 | 7 476 |
| Organismes municipaux distincts | 346 | 665 |
| Contrats présents | 1 084 | 6 577 |
| Fiches liées à l'eau (filet large) | 178 | 749 |

**476 dossiers apparaissent dans les deux exports.** Additionner les deux colonnes compterait ces
dossiers deux fois : pour cumuler plusieurs périodes, il faudra retirer les doublons.

## Ce que les données montrent

### Les plans de gestion d'actifs visibles la semaine du 7 septembre

Quatre fiches portent sur un plan de gestion ou de maintien des actifs. Trois concernent les
bâtiments, d'après leur titre ou leur classification UNSPSC :

| Organisme | Ce que montre le SEAO | Mode | Montant publié |
|---|---|---|---:|
| Ville de Matagami | « Renforcement stratégique pour l'élaboration du PGA-EAU », contrat attribué le 8 septembre 2026 à l'Union des municipalités du Québec | gré à gré | 4 892 $ |
| Ville de Dollard-des-Ormeaux | plan de gestion des actifs de ses bâtiments municipaux ; appel d'offres fermé le 8 septembre 2026, sans attribution dans cet export | appel d'offres | aucun |
| Ville de Pointe-Claire | « SERVICES PROFESSIONNELS – PLAN DIRECTEUR DE MAINTIEN D'ACTIFS », classé en ingénierie des bâtiments ; appel d'offres ouvert jusqu'au 13 octobre 2026, sans attribution | appel d'offres | aucun |
| Ville de Repentigny | « Mise à jour du plan directeur de maintien d'actifs des chalets de parcs (PDMA) » ; appel d'offres fermé le 22 septembre 2026, sans attribution dans cet export | appel d'offres | aucun |

Matagami est la seule trace explicite d'une démarche PGA-Eau dans cet export. C'est un
accompagnement, pas forcément un mandat complet d'élaboration du plan : c'est l'objet de la première
question plus bas. Les trois autres fiches montrent que le PGA-Bâtiment est lui aussi visible dans
le SEAO, et que la même méthode pourra servir pour lui.

### Les dossiers PGA-Eau de l'export d'août

L'export d'août contient quatre dossiers PGA-Eau : trois contrats attribués et un appel d'offres en
cours.

| Municipalité | Ce que montre le SEAO | Mode | Montant publié | Titre |
|---|---|---|---:|---|
| Nicolet | contrat attribué le 28 juillet 2026 | gré à gré | 77 062 $ | « … (PGA-Eau) » |
| Sept-Îles | contrat attribué le 8 septembre 2025 | appel d'offres | 63 750 $ | « … (PGA-Eau) … » |
| Mont-Tremblant | contrat attribué le 11 août 2025 | gré à gré | 54 596 $ | acronyme absent |
| Windsor | appel d'offres en cours, sans attribution dans le mois | appel d'offres | aucun | « (PGA – Eau) », tiret long |

Ces dossiers figurent dans l'export d'août, mais deux des contrats datent de 2025 : une fiche n'est
pas un contrat nouveau.

**Sur la détection.** Chercher le mot « PGA-Eau » en trouve deux sur quatre : Windsor écrit
« PGA – Eau » avec un tiret long, et Mont-Tremblant n'emploie pas l'acronyme. Le filtre large « lié
à l'eau » les trouve toutes, mais parmi 749 fiches, soit 10 % du mois : une règle trop étroite rate
des cas, une règle trop large noie les bons.

**Sur les prix.** Les montants vont de 4 892 $ (Matagami, un « renforcement stratégique » confié à
l'UMQ, semaine de septembre) à 77 062 $ (Nicolet, un « accompagnement à la préparation » du plan).
Ces mandats ne sont pas forcément de même nature : c'est l'objet de la première question plus bas.

### Ce qu'un contrat prouve, et ce qu'il ne prouve pas

| Étape officielle du PGA-Eau | Ce que le SEAO montre | Ce qui manque |
|---|---|---|
| S'engager, avant le 31 décembre 2026 | rien | la résolution du conseil municipal |
| Produire le plan | un avis, un contrat, un fournisseur, un montant, des dates | le plan lui-même et sa conformité |
| Suivi annuel, à partir de 2028 | rien | les rapports transmis au ministère |

Une municipalité absente du SEAO n'est pas forcément inactive : elle peut produire son plan à
l'interne, ou payer un mandat sous le seuil de publication. Et un contrat signé ne prouve pas qu'un
plan existe : il prouve qu'un mandat a été confié.

### Le seuil de 25 000 $

Sur les 1 000 contrats d'achat chiffrés de l'export de la semaine, chaque contrat compté une fois :

| Tranche | Contrats | Part |
|---|---:|---:|
| Sous 25 000 $ | 85 | 8,5 % |
| De 25 000 à 50 000 $ | 244 | 24,4 % |
| 50 000 $ et plus | 671 | 67,1 % |

On compte 18 contrats entre 20 000 et 25 000 $, contre 58 entre 25 000 et 30 000 $. Ce saut juste
au-dessus du seuil est très probablement l'effet de l'obligation de publication. Conséquence directe :
une petite municipalité qui paie son plan moins de 25 000 $ risque de ne laisser aucune trace.
Matagami montre que ce n'est pas systématique, puisque son contrat de 4 892 $ est publié.

Le mois d'août, compté de la même façon, donne le même portrait : sur 6 305 contrats d'achat
chiffrés, 497 sont sous 25 000 $ (7,9 %), 1 802 entre 25 000 et 50 000 $ (28,6 %) et 4 006 à
50 000 $ ou plus (63,5 %). On y compte 130 contrats entre 20 000 et 25 000 $, contre 470 entre
25 000 et 30 000 $.

### Le contexte municipal

Le SEAO ne donne ni population, ni superficie, ni état des réseaux. Le rattachement au Répertoire
des municipalités se fait par le nom, puisque le SEAO ne porte aucun code géographique officiel.

Sur les 346 organismes de la semaine, 286 ont maintenant leur population, leur superficie, leur
région et leur MRC, et 188 ont en plus des données sur leur réseau d'eau. Les 60 organismes restants se
répartissent ainsi :

- **34** ne portent aucun nom du répertoire. Ce sont surtout des régies, des offices d'habitation et
  des sociétés paramunicipales, comme la Société du Parc Jean-Drapeau, mais aussi 7 municipalités
  dont le nom s'écrit autrement dans le SEAO, comme « Saint-Donat-de-Rimouski ».
- **14** sont des organismes périmunicipaux reconnus, mais le répertoire ne donne pour eux ni
  population ni superficie.
- **12** sont des homonymes, comme les deux Saint-Donat du Québec. Le programme refuse de choisir
  entre eux et les signale pour une vérification à la main.

Le fichier de contexte compte 348 lignes : ces 346 organismes, plus Nicolet et Windsor, saisies à la
main pour suivre leurs dossiers PGA-Eau. D'où 288 lignes sur 348 avec une population dans le
fichier, et 286 sur 346 pour les organismes de la semaine. En août, 367 des 665 organismes n'ont pas
encore de ligne de contexte : seuls 246 ont une population.

Pour Matagami, on obtient ainsi : 1 352 habitants, 1 278 personnes desservies par le réseau, un
indice de fuites de 3,14 et une validité des audits de l'eau de 58 %.

Ce dernier indicateur mérite l'attention. Il ne mesure pas l'état du réseau,
mais la qualité des données qu'une municipalité tient sur son eau : c'est presque une mesure de
maturité en gestion d'actifs.

### La qualité des données

Le programme relève 1 081 points à relire sur 897 fiches. Ce ne sont pas 1 081 erreurs : la plupart
décrivent simplement la façon dont la source est construite.

| Point relevé | Nombre | Ce que c'est |
|---|---:|---|
| Nom d'organisme avec ponctuation superflue | 494 | « Ville de Lévis. », avec un point final |
| Acheteur détaillé différent de l'organisme | 218 | les arrondissements et services de Montréal |
| Montant du contrat différent du montant attribué | 164 | montant révisé en cours de route |
| Variantes de nom pour un même fournisseur | 98 | même identifiant, écriture différente |
| Montant total d'attribution différent du montant attribué | 57 | sens exact à valider |
| Montant à relire avant de l'additionner | 17 | prix possiblement unitaire, ou montant sous 1 000 $ |
| Autres | 33 | attributions sans contrat, items ou montants manquants, dates invalides |

### Ce qu'on sait maintenant de la structure du SEAO

- Une fiche est l'état d'un dossier au moment de l'export, pas un nouveau contrat.
- La date d'une fiche (`release.date`) est presque toujours la date d'ouverture de l'avis : c'est le
  cas pour 1 518 des 1 561 fiches municipales. La date de publication semble plutôt inscrite dans
  l'identifiant de la fiche.
- Il existe trois montants, et aucun n'est une dépense payée : le montant attribué, le montant du
  contrat, et un montant de référence qui est une convention de calcul documentée dans le code. Le
  montant estimé de l'appel d'offres n'est jamais publié pour les acheteurs municipaux.
- Le champ `items.description` n'est pas un texte libre, mais un code de nomenclature SEAO, par
  exemple « C02 - Ouvrages de génie civil ».
- Le marqueur « municipal » du SEAO est large : il comprend aussi les MRC, régies, sociétés de
  transport et offices d'habitation.
- La Ville de Montréal publie sous un identifiant par arrondissement ou service : 31 identifiants et
  218 fiches dans l'export.

## Questions ouvertes

1. **Qu'est-ce qui compte comme trace de démarche?** Un accompagnement à 4 892 $, comme celui de
   Matagami, vaut-il un mandat d'élaboration du plan? La réponse change ce que le baromètre
   affichera.
2. **Quelles unités comparer?** Les régies, sociétés de transport et offices d'habitation n'ont ni
   population ni territoire propre. Faut-il les comparer entre eux, ou les exclure des comparaisons
   ajustées?
3. **Comment mesurer ce que la méthode rate?** Une liste de référence, même partielle, de
   municipalités dont on sait qu'elles ont engagé une démarche permettrait de le mesurer, plutôt que
   de l'estimer.

## Prochaines étapes

1. Créer les lignes de contexte des 367 organismes de l'export d'août absents de la semaine, puis les
   compléter.
2. Intégrer au programme une règle propre au PGA-Eau, et mesurer ce qu'elle trouve, ce qu'elle rate et
   ce qu'elle attrape à tort.
3. Cumuler plusieurs périodes sans compter deux fois les mêmes dossiers, puisque 476 dossiers
   apparaissent dans les deux exports. Une petite base de données SQLite suffirait.
4. Départager automatiquement la plupart des 12 homonymes, grâce au code postal publié dans le SEAO
   et à la désignation écrite dans le nom (ville, paroisse, canton…).
5. Faire une première comparaison ajustée à la population sur un petit groupe de municipalités
   comparables.
6. Documenter une démarche de bout en bout pour une municipalité, en cherchant dans d'autres sources
   publiques la résolution du conseil et la publication du plan.

## Contenu du dépôt

| Emplacement | Contenu |
|---|---|
| `analyser_seao.py` | programme principal : lit un export du SEAO et produit quatre tableaux |
| `completer_contexte.py` | complète le contexte municipal à partir des fichiers du MAMH |
| `test_analyser_seao.py` | 23 tests sur de petits cas construits, sans lire le vrai export |
| `contexte_municipalites.csv` | **saisie manuelle** du contexte, jamais écrasée par les programmes |
| `docs/` | les pages du site de suivi |
| `zensical.toml` | la configuration du site |
| `.github/workflows/docs.yml` | la publication automatique du site |

Les dossiers `donnees_seao/`, `donnees_reference/` et `sorties/` ne sont pas versionnés : les deux
premiers contiennent des données publiques retéléchargeables, le troisième ce que les programmes
régénèrent.

## Lancer l'analyse

Il faut Python 3.10 ou plus récent. Les programmes n'utilisent que la bibliothèque standard, il n'y
a rien à installer.

```powershell
# Analyser l'export hebdomadaire de référence, déposé dans donnees_seao/.
python analyser_seao.py

# Analyser un autre export, déposé dans donnees_seao/.
python analyser_seao.py mensuel_20260801_20260831.json

# Compléter le contexte municipal.
python completer_contexte.py

# Lancer les tests.
python -B -m unittest -v test_analyser_seao
```

Les tableaux produits sont écrits dans `sorties/`. Tout ce qui s'y trouve est remplacé à chaque
exécution : n'y saisissez rien. Le seul fichier à remplir à la main est `contexte_municipalites.csv`.

## Obtenir les données

Les exports du SEAO se téléchargent sur Données Québec, dans le jeu « Système électronique d'appel
d'offres (SEAO) », et se déposent dans `donnees_seao/`.

Le contexte municipal vient de deux jeux de données du ministère des Affaires municipales et de
l'Habitation, sur Données Québec. Le programme ne télécharge rien : déposez vous-même ces fichiers
dans `donnees_reference/`.

| Jeu de données | Ressource à prendre | Fichier |
|---|---|---|
| Répertoire des municipalités du Québec | Liste des municipalités (csv) | `MUN.csv`, obligatoire |
| Répertoire des municipalités du Québec | Liste des MRC_CM_Arg (csv) | `MRC_CM_Arg.csv` |
| Répertoire des municipalités du Québec | Liste des organismes périmunicipaux | `A01_CONVERT_XML_ORG_PER_MUN.xml` |
| Stratégie québécoise d'économie d'eau potable 2019-2025 | validité des audits 2024, par classe de population | `validite_classe_2024.csv` |
| Stratégie québécoise d'économie d'eau potable 2019-2025 | indice de fuites 2024, par classe de population | `fuites_classe_2024.csv` |
| Stratégie québécoise d'économie d'eau potable 2019-2025 | consommation résidentielle 2024, par classe de population | `consommation_classe_2024.csv` |

Les mêmes fichiers donnent toujours les mêmes résultats, et la date de chaque fichier utilisé est
inscrite dans le contexte.

Toutes ces données sont publiées sous licence Creative Commons avec attribution. Les échéances du
PGA-Eau viennent de la page « Préparer un plan de gestion des actifs en eau », sur quebec.ca.

## Trois limites à connaître

**Une fiche n'est pas un contrat.** Un export contient surtout des mises à jour de dossiers plus
anciens. Sur les 1 561 fiches municipales de la semaine du 7 septembre 2026, seulement 403
correspondent à un avis ouvert cette semaine-là ; la plus ancienne remonte à 2013.

**Les montants publiés ne sont pas des dépenses payées.** Le programme distingue le montant attribué,
le montant du contrat et un montant de référence, qui est une convention de calcul documentée dans le
code.

**Le repérage par mots-clés est imparfait.** Un avis repéré comme lié à l'eau n'est pas forcément une
démarche PGA-Eau, et l'absence de trace dans le SEAO ne prouve pas l'inaction.

## Consulter le site en local

```powershell
pip install -r requirements.txt
zensical serve --open
```

Si Windows répond que la commande `zensical` est introuvable, lancez plutôt
`python -m zensical serve --open`. Le site s'ouvre à l'adresse <http://localhost:8000>.

## Publication du site

Chaque push sur la branche `main` reconstruit et publie le site sur GitHub Pages. Le réglage à faire
une seule fois dans GitHub : Settings, Pages, Build and deployment, Source « GitHub Actions ».

Ce dépôt a été créé à partir du modèle de site du cours IFT3150, construit avec Zensical.
