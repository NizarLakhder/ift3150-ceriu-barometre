# Baromètre CERIU (projet IFT3150)

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

**État au 14 octobre 2026.** Deux exports du SEAO ont été analysés : la semaine du 7 au
13 septembre 2026, qui sert de référence, et le mois d'août 2026. Depuis la première mise en commun
du 2 octobre, trois chantiers ont avancé. Le contexte municipal est maintenant complet pour toutes
les municipalités et MRC rencontrées. Un petit modèle de langage a été mis à l'essai pour lire les
fiches à notre place. Enfin, les données sont rangées dans une base PostgreSQL, qui permet de
cumuler plusieurs exports sans compter deux fois le même dossier.

## En bref

- **Le SEAO laisse voir des démarches PGA-Eau, mais seulement une partie.** On voit les mandats
  confiés à une firme ou à un organisme externe. On ne voit ni l'engagement du conseil municipal, ni
  le dépôt du plan au ministère.
- **Reconnaître une démarche est plus difficile qu'extraire les données.** L'export d'août contient
  quatre dossiers PGA-Eau ; chercher le mot « PGA-Eau » en trouve deux, et le filtre large « lié à
  l'eau » les trouve tous, mais parmi 749 fiches. La semaine de septembre en ajoute un cinquième, à
  Matagami.
- **Peu de petits contrats sont publiés.** Seulement 8,5 % des contrats d'achat chiffrés de la
  semaine, et 7,9 % de ceux d'août, sont sous 25 000 \$. Il y en a plus de trois fois plus juste
  au-dessus du seuil que juste en dessous : un petit mandat peut passer inaperçu.
- **Le contexte municipal se rattache même quand le SEAO écrit mal un nom.** « St » pour Saint, un
  « de » oublié, une faute de frappe comme « Rougement » pour Rougemont : le programme les rattrape,
  mais il n'accepte un nom seulement approché que si un indice publié le confirme. 640 des 715
  organismes rencontrés ont maintenant leur population ; les 75 autres ne sont pas des municipalités.
- **Une base de données cumule les exports sans double compte.** Un même dossier peut revenir d'un
  export à l'autre, avec un montant différent : la base garde chaque version, mais ne compte que la
  dernière.
- **Tout est reproductible** : trois programmes Python, 65 tests, et les mêmes fichiers donnent
  toujours les mêmes chiffres.

## Ce qui a été fait

1. **Comprendre la structure réelle du SEAO.** Deux exports ont été lus en entier, sans
   échantillon : la semaine du 7 au 13 septembre 2026 et le mois d'août 2026. Les points établis sont
   résumés plus bas.
2. **Extraire et structurer.** `analyser_seao.py` garde les acheteurs que le SEAO marque comme
   municipaux et produit quatre tableaux : le détail par fiche, un résumé par organisme, le contexte
   de chaque organisme et une liste de points à relire. Chaque ligne renvoie à son avis public.
3. **Ajouter le contexte municipal.** `completer_contexte.py` rattache chaque organisme au Répertoire
   des municipalités et aux données de la Stratégie québécoise d'économie d'eau potable, deux jeux du
   ministère des Affaires municipales et de l'Habitation. Il tolère les écarts d'écriture du SEAO.
   Les quelques cas qu'aucun indice ne permettait de trancher ont été réglés à la main, chacun avec
   sa source publique.
4. **Repérer les démarches PGA-Eau.** Le programme marque les fiches liées à l'eau au sens large
   (colonne `lie_eau`) et, avec une règle plus précise, les dossiers PGA-Eau (colonne `pga_eau`).
5. **Documenter la qualité des données**, pour savoir ce qu'il faut relire avant de compter.
6. **Cumuler les exports dans une base PostgreSQL.** `charger_base.py` range les fiches, le
   répertoire et le contexte dans une base de 19 tables, puis vérifie qu'elle redonne exactement les
   chiffres que donne `analyser_seao.py`.
7. **Mettre un modèle de langage à l'essai.** Un petit modèle, qwen2.5, a été installé avec Ollama
   sur un ordinateur personnel pour lire les fiches à la place d'une lecture à la main. Les
   difficultés et les résultats sont décrits plus bas.

| | Semaine du 7 au 13 sept. 2026 | Mois d'août 2026 |
|---|---:|---:|
| Fiches dans l'export | 3 890 | 15 423 |
| Fiches d'acheteurs municipaux | 1 561 | 7 476 |
| Organismes municipaux distincts | 346 | 665 |
| Contrats présents | 1 084 | 6 577 |
| Fiches liées à l'eau (filet large) | 178 | 749 |

**476 dossiers apparaissent dans les deux exports.** Additionner les deux colonnes les compterait
deux fois. La base de données règle ce problème : une fiche n'y entre qu'une fois, et la vue
`contrat_courant` ne garde que la dernière version de chaque contrat. Seize contrats figurent dans
les deux exports ; l'un d'eux passe de 42 669,55 \$ en août à 16 121,55 \$ en septembre.

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

Le programme applique maintenant une règle entre les deux (colonne `pga_eau`) : l'acronyme PGA
suivi du mot « eau », quelle que soit la ponctuation, ou les mots « gestion », « actif » et « eau »
dans le même titre. Sur les 9 037 fiches municipales des deux exports, elle retrouve les cinq
dossiers lus à la main, Matagami compris, et aucun autre. Cinq cas restent trop peu pour conclure :
la règle est à valider sur d'autres périodes. Surtout, ces cinq dossiers ont eux-mêmes été repérés
par leur titre. La règle ne dit donc rien des mandats de gestion d'actifs dont le titre ne mentionne
ni PGA ni gestion d'actifs, et qui pourraient être nombreux : c'est la prochaine chose à mesurer.

**Sur les prix.** Les montants vont de 4 892 \$ (Matagami, un « renforcement stratégique » confié à
l'UMQ, semaine de septembre) à 77 062 \$ (Nicolet, un « accompagnement à la préparation » du plan).
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

On compte 18 contrats entre 20 000 et 25 000 \$, contre 58 entre 25 000 et 30 000 \$. Ce saut juste
au-dessus du seuil est très probablement l'effet de l'obligation de publication. Conséquence directe :
une petite municipalité qui paie son plan moins de 25 000 \$ risque de ne laisser aucune trace.
Matagami montre que ce n'est pas systématique, puisque son contrat de 4 892 \$ est publié.

Le mois d'août, compté de la même façon, donne le même portrait : sur 6 305 contrats d'achat
chiffrés, 497 sont sous 25 000 \$ (7,9%), 1 802 entre 25 000 et 50 000 \$ (28,6 %) et 4 006 à
50 000 \$ ou plus (63,5 %). On y compte 130 contrats entre 20 000 et 25 000 \$, contre 470 entre
25 000 et 30 000 \$.

### Le contexte municipal

Le SEAO ne donne ni population, ni superficie, ni état des réseaux. Le rattachement au Répertoire
des municipalités se fait par le nom, puisque le SEAO ne porte aucun code géographique officiel.

| | Semaine (346 organismes) | Août (665 organismes) |
|---|---:|---:|
| Population, superficie et région | 305 | 593 |
| MRC | 245 | 498 |
| Données sur le réseau d'eau | 199 | 368 |

Les écarts entre ces lignes ont tous une explication. Dans la semaine, 31 villes ne font partie
d'aucune MRC, comme Montréal, Laval ou Longueuil, et pour 74 municipalités la Stratégie publie
elle-même « Aucune donnée » sur l'eau.

Pour Matagami, on obtient ainsi : 1 352 habitants, 1 278 personnes desservies par le réseau, un
indice de fuites de 3,14 et une validité des audits de l'eau de 58 %.

Ce dernier indicateur mérite l'attention. Il ne mesure pas l'état du réseau,
mais la qualité des données qu'une municipalité tient sur son eau : c'est presque une mesure de
maturité en gestion d'actifs.

**Comment un nom est rattaché.** Le programme essaie trois choses, dans l'ordre : le code
géographique déjà inscrit dans le contexte, le nom exact, puis des règles tolérantes. Celles-ci
rattrapent ce que le SEAO écrit autrement : une abréviation (« Ste-Gertrude-Manneville »), un
déterminant oublié (« Saint-Léon-Standon » pour Saint-Léon-de-Standon), une précision entre
parenthèses (« Saint-Léon-le-Grand (Mauricie) »), une désignation placée à la fin
(« Marston-Canton ») ou une faute de frappe. La tolérance dépend de la longueur du mot : aucune
faute jusqu'à quatre lettres, une de cinq à huit, deux au-delà. C'est voulu, puisqu'une seule lettre
sépare Saint-Paul de Sainte-Paule.

Une ressemblance ne suffit jamais. Un nom seulement approché n'est retenu que si un indice publié le
confirme : le code postal, la désignation ou la région. Pour vérifier cette prudence, 36 907 fautes
ont été introduites exprès dans les noms officiels : 83 % sont retrouvées, et aucune ne mène à une
mauvaise municipalité. Les sept rattachements que le code postal ne confirmait pas ont aussi été
vérifiés à la main, sur la page de leur avis dans le SEAO : la région y est chaque fois celle du
répertoire, et l'adresse ou le domaine du courriel aussi, sauf pour un contrat de gré à gré dont la
page ne donne pas d'adresse.

**Quand un nom correspond à plusieurs municipalités**, le programme ne tranche qu'avec un indice
publié : le code postal donné par le SEAO, comparé à celui de l'hôtel de ville, ou une désignation
distinctive écrite dans le nom (Canton, Village, Ville, Paroisse). Le mot « Municipalité » ne compte
pas : le SEAO l'emploie aussi pour des paroisses, comme Sainte-Françoise. 23 homonymes ont été
départagés ainsi. Sans indice, le programme refuse de choisir.

**Neuf cas ont été réglés à la main**, chacun avec sa source publique, notée dans le fichier de
contexte. Pour ces cas, les fiches du SEAO ne donnent pas l'adresse de l'acheteur. On la trouve en
revanche sur le site fédéral AchatsCanada, qui republie les avis du SEAO : c'est ainsi que
« Municipalité de Saint-Donat » a été rattachée à la municipalité de Lanaudière plutôt qu'à celle du
Bas-Saint-Laurent.
Trois des organismes cherchés n'existent plus sous leur nom : Saint-Bruno, Sainte-Anne-de-la-Pocatière
et Saint-Onésime-d'Ixworth ont été regroupées en 2025 et en 2026 avec des voisines. Elles sont
rattachées à la nouvelle municipalité, et le fichier `regroupements.csv` garde la trace de chaque
regroupement, avec sa source officielle.

**Il ne reste aucun cas à trancher.** Les 41 organismes de la semaine encore sans population ne sont
pas des municipalités. Le répertoire en connaît 23, des régies et des sociétés de transport, mais
sans leur donner de population. Les 18 autres n'y figurent pas, comme les offices d'habitation ou la
Société du Parc Jean-Drapeau.

**Ce que disent les cases sans chiffre.** Le fichier `contexte_municipalites.csv` compte 715 lignes,
une par organisme rencontré dans les deux exports. Chaque nouvel export y ajoute ceux qu'il fait
apparaître, sans jamais modifier une ligne existante. Une case sans chiffre y dit pourquoi :

| Mot | Sens |
|---|---|
| `À compléter` | la donnée peut exister, mais on ne l'a pas encore trouvée |
| `Sans objet` | le champ ne s'applique pas, comme la MRC dont ferait partie une MRC |
| `Hors MRC` | la ville ne fait partie d'aucune MRC, d'après le répertoire |
| `Aucune donnée` | la Stratégie publie la municipalité, mais sans aucune valeur |

Une note vide veut simplement dire qu'il n'y a rien à signaler. Une colonne reste à compléter pour
tout le monde, faute de source : le type de milieu.

**Trois défauts des fichiers sources ont été trouvés en chemin, et contournés.**

- Le répertoire écrit « Comm. métropolitaine de Montréal ». Faute de reconnaître l'abréviation, la
  communauté avait reçu la population de la Ville de Montréal : 1,9 million d'habitants au lieu
  de 4,3.
- Le fichier des organismes périmunicipaux coupe les noms à 60 caractères, et met la suite dans un
  second champ : 132 organismes sur 338 sont touchés.
- Deux des trois fichiers de la Stratégie perdent le zéro du début des codes de l'est du Québec :
  « 3005 » pour Gaspé, au lieu de « 03005 ». 28 organismes n'avaient que leur indice de fuites.

### Un modèle de langage pour lire les fiches

Lire des milliers de fiches à la main prend du temps. Un petit modèle de langage, qwen2.5 à
3 milliards de paramètres, a donc été installé avec Ollama sur un ordinateur personnel, pour lire les
fiches du SEAO.

**Les difficultés rencontrées :**

- **Il ne lit pas un export entier.** Le fichier de la semaine pèse 16 Mo, et il est refusé : il faut
  lui donner les fiches une à une.
- **Il coupe sans prévenir.** Avec le réglage par défaut, un message de cinq fiches a été tronqué de
  plus de la moitié, et le modèle a répondu comme s'il avait tout lu. Il a fallu agrandir sa fenêtre
  de lecture, et vérifier dans le journal d'Ollama ce qu'il avait vraiment reçu.
- **Les fiches longues lui posent problème.** Sur une fiche de 15 attributions, il en a compté 12.

**Les résultats :**

- **Sur une question précise, il répond juste.** Avec une seule fiche et une liste de champs à
  remplir, il donne les 14 champs correctement, y compris pour le dossier de Mont-Tremblant, qui
  n'emploie pas l'acronyme PGA-Eau, et pour un piège, un plan de gestion des actifs des bâtiments,
  qu'il ne prend pas pour un PGA-Eau. Sur sept fiches courtes, il donne les mêmes nombres
  d'attributions et de contrats, les mêmes statuts et les mêmes montants que le programme.
- **Sur une analyse ouverte, il échoue.** Invité à analyser cinq fiches à la fois, dont trois dossiers
  PGA-Eau, il n'en reconnaît aucun, et il prête à une fiche des renseignements qui viennent d'une
  autre.

Un petit modèle peut donc extraire des champs précis, fiche par fiche, mais pas analyser un ensemble
de fiches, et il ne remplace pas la lecture complète que fait le programme. L'essai est mis de côté
pour l'instant, et sera repris sur davantage de fiches.

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

- Une fiche est l'état d'un dossier au moment de l'export, pas un nouveau contrat. Un même dossier
  revient d'un export à l'autre, et son montant peut changer entre-temps.
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
  218 fiches dans l'export de la semaine, 37 identifiants en comptant le mois d'août.
- Dans les deux exports, chaque attribution a exactement un fournisseur, et chaque contrat découle
  d'une seule attribution. En revanche, 361 soumissionnaires ne figurent pas dans la liste des
  parties de leur fiche.

## La base de données

La base range les données en quatre groupes, chacun dans son propre schéma PostgreSQL :

| Groupe | Ce qu'il contient |
|---|---|
| `territoire` | ce que dit le ministère : régions, MRC, municipalités, regroupements, données sur l'eau |
| `organismes` | qui achète : l'organisme réel et ses identifiants d'acheteur dans le SEAO |
| `seao` | les fiches publiées, découpées en tables : fiche, attribution, contrat, fournisseur… |
| `analyses` | ce que le programme en déduit, et les vues qui servent à l'interroger |

Les clés viennent des données elles-mêmes : le code géographique d'une municipalité, le numéro de
dossier (`ocid`), les identifiants `OP` et `FO` du SEAO. Chaque fiche est aussi conservée telle
qu'elle a été publiée, pour toujours pouvoir revenir à la source.

Trois vérifications sont faites à chaque chargement :

- **un export n'entre qu'une fois** : son empreinte est notée, et un fichier modifié qui porte le nom
  d'un export déjà chargé est refusé ;
- **la base redonne les chiffres du programme** : 1 561 et 7 476 fiches, 609 861 803,11 \$ et
  5 219 780 511,76 \$ de montants attribués, les cinq dossiers PGA-Eau ;
- **un contrat n'est compté qu'une fois** : la vue `analyses.contrat_courant` garde sa dernière
  version.

Les montants y sont exacts au cent près, les dates sont de vraies dates, et les titres se cherchent
sans tenir compte des accents.

## Questions ouvertes

1. **Qu'est-ce qui compte comme trace de démarche?** Un accompagnement à 4 892 $, comme celui de
   Matagami, vaut-il un mandat d'élaboration du plan? La réponse change ce que le baromètre
   affichera.
2. **Quelles unités comparer?** Les 75 organismes non municipaux, comme les régies, les sociétés de
   transport et les offices d'habitation, n'ont ni population ni territoire propre. Faut-il les
   comparer entre eux, les rattacher au territoire qu'ils desservent, ou les exclure des comparaisons
   ajustées?
3. **Que faire des municipalités regroupées?** Un contrat signé par Saint-Bruno avant son
   regroupement est rattaché à la nouvelle municipalité d'Hébertville, avec sa population actuelle.
   C'est la convention retenue pour l'instant, mais elle reste à valider.
4. **Comment mesurer ce que la méthode rate?** Une liste de référence, même partielle, de
   municipalités dont on sait qu'elles ont engagé une démarche permettrait de le mesurer, plutôt que
   de l'estimer.

## Prochaines étapes

1. Ajouter le type de milieu, à partir de la classification de Statistique Canada par zones
   d'influence métropolitaine, publiée par subdivision de recensement, dont le code est celui du
   répertoire précédé de 24.
2. Faire une première comparaison ajustée à la population, sur un petit groupe de municipalités
   comparables, à partir de la base.
3. Valider la règle PGA-Eau sur d'autres périodes : la base permet maintenant d'en charger plusieurs.
4. Reprendre l'essai du modèle de langage sur davantage de fiches, surtout les plus longues, avec des
   questions précises plutôt qu'une analyse ouverte.
5. Documenter une démarche de bout en bout pour une municipalité, en cherchant dans d'autres sources
   publiques la résolution du conseil et la publication du plan.

## Contenu du dépôt

| Emplacement | Contenu |
|---|---|
| `analyser_seao.py` | programme principal : lit un export du SEAO et produit quatre tableaux |
| `completer_contexte.py` | complète le contexte municipal à partir des fichiers du ministère, en tolérant les écarts d'écriture du SEAO |
| `charger_base.py` | range les exports, le répertoire et le contexte dans PostgreSQL, puis vérifie le résultat |
| `utilitaires.py` | les petites fonctions partagées : nettoyer un texte, lire une date, convertir un montant, écrire un CSV |
| `schema.sql` | la structure de la base, en quatre groupes de tables |
| `contexte_municipalites.csv` | le contexte de chaque organisme : les programmes y ajoutent des lignes et remplissent les cases « À compléter », mais **n'écrasent jamais une valeur** |
| `regroupements.csv` | les municipalités regroupées depuis 2025, avec leurs sources officielles |
| `test_analyser_seao.py` | 17 tests de l'analyse, sur de petits cas construits, sans lire le vrai export |
| `test_completer_contexte.py` | 35 tests du contexte, inspirés de vrais homonymes et de vraies fautes d'écriture |
| `test_charger_base.py` | 9 tests de la conversion des fiches, sans base de données |
| `test_utilitaires.py` | 4 tests des petites fonctions partagées |
| `requirements.txt` | les bibliothèques à installer |
| `docs/` | les pages du site de suivi |
| `zensical.toml` | la configuration du site |
| `.github/workflows/docs.yml` | la publication automatique du site |

Les dossiers `donnees_seao/`, `donnees_reference/` et `sorties/` ne sont pas versionnés : les deux
premiers contiennent des données publiques retéléchargeables, le troisième ce que les programmes
régénèrent.

## Lancer l'analyse

Il faut Python 3.10 ou plus récent. Les programmes s'appuient sur deux bibliothèques : `rapidfuzz`,
qui mesure l'écart entre deux mots, et `psycopg`, qui écrit dans PostgreSQL. Une seule commande les
installe, avec ce qu'il faut pour le site :

```powershell
pip install -r requirements.txt
```

Puis, dans l'ordre :

```powershell
# Analyser l'export hebdomadaire de référence, déposé dans donnees_seao/.
python analyser_seao.py

# Analyser un autre export, déposé dans donnees_seao/.
python analyser_seao.py mensuel_20260801_20260831.json

# Compléter le contexte municipal (après l'analyse : il y lit les codes postaux).
python completer_contexte.py

# Ranger le tout dans la base PostgreSQL (voir plus bas pour la préparer).
python charger_base.py

# Lancer les 65 tests.
python -B -m unittest -v
```

Après avoir complété le contexte, relancez l'analyse pour que les tableaux de `sorties/` en
tiennent compte.

Les tableaux produits sont écrits dans `sorties/`. Tout ce qui s'y trouve est remplacé à chaque
exécution : n'y saisissez rien. Le seul fichier à remplir à la main est `contexte_municipalites.csv`.
Pour régler un cas à la main, il suffit d'y écrire le code géographique de l'organisme : le
programme remplit le reste à la prochaine exécution.

## Préparer la base de données

Il faut PostgreSQL 13 ou plus récent ; le projet est testé avec la version 18. La préparation se
fait une seule fois.

**1. Créer un compte et une base réservés au projet**, en administrateur, par exemple avec `psql` ou
l'outil de requête de pgAdmin :

```sql
CREATE ROLE barometre LOGIN PASSWORD 'un-mot-de-passe';
CREATE DATABASE barometre OWNER barometre;
```

**2. Enregistrer ce mot de passe dans le fichier prévu par PostgreSQL**, hors du projet, pour qu'il
ne se retrouve jamais dans le dépôt. Sous Windows, ce fichier est `%APPDATA%\postgresql\pgpass.conf`
; ailleurs, c'est `~/.pgpass`. Il contient une ligne de cette forme :

```text
localhost:5433:barometre:barometre:un-mot-de-passe
```

**3. Charger.** `python charger_base.py` crée les tables qui manquent, charge ce qui n'est pas
encore en base, puis compare le résultat aux tableaux d'`analyser_seao.py`. On peut le relancer sans
crainte : un export déjà chargé est reconnu et laissé de côté. `python charger_base.py
--reinitialiser` efface tout et recharge depuis les fichiers.

Par défaut, le programme se connecte à `localhost`, port 5433, avec le compte et la base
`barometre`. Les variables d'environnement `BAROMETRE_HOTE`, `BAROMETRE_PORT`, `BAROMETRE_BASE` et
`BAROMETRE_COMPTE` permettent d'en changer.

Deux exemples de questions qu'on peut lui poser :

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

Les exports du SEAO se téléchargent sur Données Québec, dans le jeu « Système électronique d'appel
d'offres (SEAO) », et se déposent dans `donnees_seao/` :
<https://www.donneesquebec.ca/recherche/dataset/systeme-electronique-dappel-doffres-seao>

La population, la superficie, la région, la MRC et l'état des réseaux d'eau viennent de deux jeux de
données du ministère des Affaires municipales et de l'Habitation, sur Données Québec :

- le Répertoire des municipalités du Québec, pour la population, la superficie, la région et la MRC :
  <https://www.donneesquebec.ca/recherche/dataset/repertoire-des-municipalites-du-quebec>
- la Stratégie québécoise d'économie d'eau potable 2019-2025, pour la population desservie, l'indice
  de fuites, la validité des audits et la consommation :
  <https://www.donneesquebec.ca/recherche/dataset/sqeep-2019-2025>

Le programme ne télécharge rien : déposez vous-même ces fichiers dans `donnees_reference/`.

| Jeu de données | Ressource à prendre | Fichier |
|---|---|---|
| Répertoire des municipalités du Québec | Liste des municipalités (csv) | `MUN.csv`, obligatoire |
| Répertoire des municipalités du Québec | Liste des MRC_CM_Arg (csv) | `MRC_CM_Arg.csv` |
| Répertoire des municipalités du Québec | Liste des organismes périmunicipaux | `A01_CONVERT_XML_ORG_PER_MUN.xml` |
| Stratégie québécoise d'économie d'eau potable 2019-2025 | validité des audits 2024, par classe de population | `validite_classe_2024.csv` |
| Stratégie québécoise d'économie d'eau potable 2019-2025 | indice de fuites 2024, par classe de population | `fuites_classe_2024.csv` |
| Stratégie québécoise d'économie d'eau potable 2019-2025 | consommation résidentielle 2024, par classe de population | `consommation_classe_2024.csv` |

Les mêmes fichiers donnent toujours les mêmes résultats, et la date de chaque fichier utilisé est
inscrite dans le contexte. Le fichier `regroupements.csv`, lui, est tenu à la main : chaque ligne y
cite l'annonce ou l'avis officiel du regroupement.

Les neuf cas réglés à la main s'appuient sur d'autres sources publiques : les avis du SEAO
republiés sur le site fédéral AchatsCanada, qui donnent l'adresse de l'acheteur, les annonces de
regroupement du gouvernement du Québec et un avis du ministère de la Justice. Chacune est citée, avec
son lien, dans la page [Références](docs/references.md) du site et dans la colonne `notes` du
fichier de contexte.

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
