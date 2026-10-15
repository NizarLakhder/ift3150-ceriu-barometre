---
title: Suivi du projet
---

<style>
    @media screen and (min-width: 76em) {
        .md-sidebar--primary {
            display: none !important;
        }
    }
</style>

# Suivi de projet

Cette page documente l'évolution du projet : le travail réalisé, les décisions prises et les
difficultés rencontrées, semaine après semaine.

---

## Semaines 1 et 2 (4 au 15 septembre) : ouverture et premier contact avec les données

### Objectifs de la période
- Comprendre le mandat du CERIU et le contexte des démarches municipales de gestion d'actifs
- Identifier les sources de données publiques exploitables
- Produire un premier prototype d'extraction

### Travail réalisé

!!! abstract "Avancement"
    - [x] Prise de connaissance du mandat avec le CERIU et le superviseur
    - [x] Mise en place du site de suivi avec Zensical
    - [x] Téléchargement d'un premier export hebdomadaire du SEAO sur Données Québec
          (31 août au 6 septembre 2026) et exploration de sa structure au format OCDS
    - [x] Repérage du champ `details.municipal`, qui permet d'isoler les acheteurs municipaux
    - [x] Premier script de recherche par mots-clés
        - Un cas trouvé : un mandat d'inspection d'actifs en eau de la Ville de Sherbrooke,
          réalisé dans le cadre de son PGA-Eau

### Décisions et ajustements

!!! info "Décisions"
    - Commencer par le SEAO comme première source, et par le PGA-Eau comme premier cas d'étude
    - Garder le premier script volontairement simple : il sert à passer d'une recherche manuelle
      à une première extraction automatique, pas à produire des résultats fiables

### Difficultés rencontrées

!!! warning "Difficultés"
    - Un export hebdomadaire contient aussi des mises à jour de contrats anciens : la date du fichier
      n'est pas la date du contrat. Il faut distinguer la date de publication, la date d'attribution,
      la date de signature et la période de l'avis.

---

## Semaine 3 (16 au 22 septembre) : diagnostic complet et premier prototype d'analyse

### Rencontre du 16 septembre avec le superviseur

Trois orientations fixées pour la suite :

- **Axe 1** : classer et comparer les organismes municipaux selon leur activité contractuelle,
  sans se limiter aux montants bruts;
- **Axe 2** : identifier le contexte propre à chaque municipalité, comme sa population ou sa
  géographie, avant de décider si une comparaison a du sens;
- **Livrable** : un rapport compréhensible pour le partenaire.

### Travail réalisé

!!! abstract "Avancement"
    - [x] Diagnostic complet de l'export du 7 au 13 septembre, parcouru en entier
        - 3 890 fiches, dont 1 561 pour des acheteurs municipaux, soit 346 organismes
    - [x] Programme d'analyse, aujourd'hui `analyser_seao.py`, qui produit quatre tableaux : le
          détail par fiche, un résumé par organisme, le contexte à enrichir et les points de qualité
          à relire
    - [x] Premier rapport destiné au CERIU
    - [x] Premiers tests automatisés
    - [x] Corrections après vérification : fournisseurs comptés par identifiant plutôt que par nom,
          distinction entre un événement de publication et le statut d'un contrat

### Décisions et ajustements

!!! info "Décisions"
    - **Une fiche n'est pas un contrat.** Sur 1 561 fiches municipales, seulement 403 correspondent à
      un avis ouvert pendant la semaine; la plus ancienne remonte à 2013.
    - Trois montants distincts sont conservés : montant attribué, montant du contrat et montant de
      référence. Aucun n'est présenté comme une dépense payée.
    - Les subventions et contributions financières sont séparées des achats, pour ne pas fausser les
      comparaisons.

### Difficultés rencontrées

!!! warning "Difficultés"
    - Le sens des champs du fichier n'est pas documenté et plusieurs constats ont dû être établis par
      l'analyse : la date d'une fiche est celle de l'ouverture de l'avis, la valeur estimée de l'avis
      est absente des fiches municipales, et la description des items est une nomenclature de
      45 codes plutôt qu'un texte libre.
    - Une étiquette de qualité affirmait « montant probablement unitaire », ce qui s'est révélé faux
      dans 9 cas sur 17. Elle a été renommée « montant à vérifier » et accompagnée de sa raison.

---

## Semaine 4 (23 au 29 septembre) : contexte municipal et fichier mensuel

### Rencontre du 23 septembre avec le superviseur

- Les données de contexte de l'axe 2 doivent être cherchées dans d'autres sources que le SEAO.
- Réfléchir à la façon de relier l'ensemble dans une base de données.
- Possibilité d'introduire l'agent Hermes pour le tester.

### Travail réalisé

!!! abstract "Avancement"
    - [x] Identification de deux sources officielles du ministère des Affaires municipales et de
          l'Habitation : le Répertoire des municipalités du Québec et la Stratégie québécoise
          d'économie d'eau potable
    - [x] Second programme, aujourd'hui `completer_contexte.py`, qui rapproche les organismes de
          ces sources
        - 286 des 346 organismes de la semaine ont maintenant leur population, leur superficie,
          leur région et leur MRC; 188 ont en plus des données sur l'état de leur réseau d'eau
          (le fichier de contexte compte aussi Nicolet et Windsor, saisies à la main)
    - [x] Traitement du fichier mensuel d'août : 7 476 fiches municipales, 665 organismes
    - [x] Analyse de la détection des PGA-Eau : l'export d'août contient quatre dossiers PGA-Eau,
          trois contrats attribués et un appel d'offres en cours (Windsor). Chercher le mot
          « PGA-Eau » en trouve deux; le filtre « lié à l'eau » les trouve tous, parmi 749 fiches
    - [x] Mesure de l'effet du seuil de publication : compté par contrat, 8,5 % des contrats
          d'achat de la semaine et 7,9 % de ceux d'août sont sous 25 000 $
    - [x] Réécriture du rapport destiné au CERIU et réorganisation du dossier de travail
    - [x] 23 tests automatisés

### Décisions et ajustements

!!! info "Décisions"
    - Le programme lit les fichiers de référence au lieu de les télécharger : les mêmes fichiers
      donnent toujours les mêmes résultats, et une adresse codée en dur finit par casser.
    - Quand un nom correspond à plusieurs organismes, par exemple les deux Saint-Donat du Québec,
      le programme refuse de choisir et signale le cas pour une vérification manuelle.
    - Pas de règle PGA-Eau dans le programme tant qu'elle n'est pas mesurée : mieux vaut savoir ce
      qu'une règle rate que d'élargir le filtre à l'aveugle.

### Difficultés rencontrées

!!! warning "Difficultés"
    - Le fichier de contexte empêchait de traiter le fichier mensuel, parce que la Ville de Montréal
      publie sous un identifiant par service et que cette liste change d'un export à l'autre.
      Résolu : le rapprochement accepte maintenant un changement d'identifiants si le nom est
      identique et qu'au moins un identifiant est commun.
    - Les municipalités n'écrivent pas toutes « PGA-Eau » de la même façon : l'une utilise un tiret
      long, une autre n'emploie pas l'acronyme, ce qui fait échouer une recherche du mot
      « PGA-Eau ».
    - Deux lignes du fichier de contexte ont disparu sans que la cause puisse être retrouvée. Cet
      incident motive la mise sous contrôle de version du code.

---

## Semaine 5 (30 septembre au 2 octobre) : première mise en commun

### Objectifs de la période
- Présenter le projet, la solution envisagée et l'état d'avancement lors de la mise en commun
  du 2 octobre
- Mettre le code d'analyse et la documentation dans le dépôt du projet

### Travail réalisé

!!! abstract "Avancement"
    - [x] Préparation de la présentation en cinq diapositives
    - [x] Réécriture des programmes pour les rendre plus lisibles : `analyser_seao.py` et
          `completer_contexte.py`
    - [x] Code, README et site de suivi publiés sur GitHub
    - [x] Mise en commun du 2 octobre

### Prochaines étapes

- Élargir la détection des plans de gestion d'actifs, en mesurant les faux positifs sur un
  échantillon lu à la main
- Compléter le contexte des organismes présents dans le fichier mensuel
- Départager les douze municipalités homonymes
- Produire une première comparaison ajustée à la population
- Étudier une base de données pour cumuler plusieurs périodes sans compter deux fois les mêmes
  dossiers : 476 dossiers apparaissent à la fois dans l'export hebdomadaire et dans le mensuel
- Préciser avec le CERIU l'accès à l'agent Hermes et la tâche à lui confier

---

## Semaine 6 (5 au 11 octobre) : corrections et nouvelles demandes

### Objectifs de la période
- Corriger les défauts présentés à la mise en commun avant d'ajouter de nouvelles fonctions
- Vérifier chaque correction en comparant les résultats avant et après

### Rencontre du 7 octobre avec le superviseur

Trois demandes pour la suite :

- **Compléter le contexte qui manque**, en cherchant d'autres sources, et rendre le rapprochement des
  noms tolérant : aux accents, aux déterminants, aux cédilles, et aux fautes de frappe selon la
  longueur du mot, comme « batimnet » pour « batiment »;
- **Faire lire les fiches par un modèle de langage simple**, plutôt qu'à la main;
- **Ranger les données dans une base bien structurée**, avec des tables séparées plutôt que tout
  dans le même panier.


### Travail réalisé

!!! abstract "Avancement"
    - [x] Contexte des organismes d'août : `analyser_seao.py` ajoute maintenant au fichier de
          contexte les organismes qu'un nouvel export fait apparaître (367 pour août)
        - Organismes d'août avec population : de 246 à 572 sur 665
    - [x] Homonymes : 23 départagés, 10 par le code postal publié dans le SEAO et 13 par la
          désignation écrite dans le nom (Canton, Village, Ville, Paroisse)
        - Rapprochements ambigus : de 27 à 3
        - Organismes de la semaine avec population : de 286 à 295 sur 346
    - [x] Règle de repérage du PGA-Eau intégrée au programme (colonne `pga_eau`)
        - Sur les 9 037 fiches des deux exports : 5 dossiers trouvés sur 5, sans fausse alerte,
          contre 3 avec la seule recherche de l'acronyme
    - [x] Tests : de 23 à 41, dont 13 pour `completer_contexte.py`, qui n'en avait aucun
    - [x] Pour chaque correction, sorties comparées avant et après : seules les valeurs visées changent
    - [x] Essai d'un petit modèle de langage, qwen2.5 à 3 milliards de paramètres, installé
          localement avec Ollama pour lire les fiches du SEAO
        - Le fichier entier est refusé, trop gros. Avec le réglage par défaut, un message de cinq
          fiches est coupé de plus de la moitié, sans avertissement
        - Sur une analyse ouverte de cinq fiches, il ne reconnaît aucun des trois dossiers PGA-Eau
        - Sur une question précise posée fiche par fiche, il répond juste : 14 champs sur 14, y
          compris pour un dossier PGA-Eau sans acronyme et pour un piège
        - Sur une fiche longue de 15 attributions, il n'en compte que 12
    - [x] Essai à blanc du rapprochement tolérant, sans rien modifier : 17 municipalités et MRC
          retrouvées parmi les cas restants, et 11 régies reconnues

### Décisions et ajustements

!!! info "Décisions"
    - Le fichier de contexte peut recevoir de nouvelles lignes, mais une ligne existante n'est
      jamais modifiée. Le programme le vérifie octet par octet et garde une sauvegarde.
    - Un homonyme n'est départagé qu'avec un indice publié. Le mot « Municipalité » ne compte pas,
      et la façon dont chaque cas a été tranché est écrite dans le fichier de contexte.
    - Quand les identifiants d'un organisme ne concordent qu'en partie, le nom doit aussi être
      identique : un identifiant commun ne suffit plus.
    - L'essai du modèle de langage est mis de côté pour l'instant. Un modèle simple sait extraire
      des champs précis d'une fiche, mais pas analyser un ensemble de fiches. On y reviendra en fin
      de session, sur davantage de fiches.
    - La base sera PostgreSQL plutôt que SQLite : les montants y restent exacts au cent près, les
      dates sont de vraies dates, et la recherche sans accents ou par noms proches y est intégrée.

### Difficultés rencontrées

!!! warning "Difficultés"
    - Le SEAO appelle « Municipalité » des organismes qui sont des paroisses, comme Sainte-Françoise
      et Saint-Isidore. Se fier à ce mot aurait donné la mauvaise municipalité.
    - Le fichier des organismes périmunicipaux du ministère liste deux fois la Société de transport
      de l'Outaouais, ce qui la faisait passer pour un homonyme.
    - Le modèle de langage ne signale jamais qu'il n'a lu qu'une partie du message. Sans un coup
      d'œil au journal d'Ollama, l'erreur serait passée inaperçue.

### Prochaines étapes

- Intégrer le rapprochement tolérant au programme, puis régler les cas qui restent
- Construire la base PostgreSQL pour cumuler les périodes sans double compte

---

## Semaine 7 (12 au 18 octobre) : contexte complété et base de données

### Objectifs de la période
- Intégrer le rapprochement tolérant des noms et régler les derniers cas du contexte
- Construire la base de données et vérifier qu'elle redonne les chiffres du programme

### Travail réalisé

!!! abstract "Avancement"
    - [x] Rapprochement tolérant intégré à `completer_contexte.py`. Il ne sert que si le nom exact
          ne trouve rien, et rattrape les abréviations (« Ste », « M. »), les déterminants oubliés,
          les précisions entre parenthèses, les désignations placées à la fin du nom et les fautes
          de frappe
        - 17 municipalités et MRC rattachées, et 11 régies reconnues, dont « Rougement » pour
          Rougemont
        - Sur 36 907 fautes introduites exprès dans les noms officiels, 83 % sont retrouvées, et
          aucune ne mène à une mauvaise municipalité
        - Les 7 que le code postal ne confirmait pas ont été vérifiés à la main sur la page de leur
          avis dans le SEAO : la région y est chaque fois celle du répertoire, et l'adresse ou le
          domaine du courriel aussi, sauf pour un contrat de gré à gré sans adresse
    - [x] Les derniers cas réglés à la main, chacun avec une source publique notée dans le fichier
          de contexte
        - 9 organismes rattachés grâce aux avis republiés sur AchatsCanada, qui donnent l'adresse de
          l'acheteur, et aux annonces officielles de regroupement
        - Les 75 organismes restants ne sont pas des municipalités : régies, sociétés de transport,
          offices d'habitation
        - Il ne reste aucun cas à trancher
    - [x] Trois défauts des fichiers sources corrigés
        - La Communauté métropolitaine de Montréal avait reçu la population de la Ville : 1,9 million
          d'habitants au lieu de 4,3
        - Les noms des régies étaient coupés à 60 caractères
        - Les codes de l'est du Québec avaient perdu leur zéro dans les fichiers sur l'eau : 28
          organismes n'avaient que leur indice de fuites
    - [x] Des étiquettes qui disent la vérité dans le fichier de contexte : « Sans objet », « Hors
          MRC » et « Aucune donnée » remplacent « À compléter » là où rien ne manque vraiment
    - [x] Base PostgreSQL construite et chargée avec `charger_base.py` : quatre groupes, 19 tables
          et 3 vues
        - 9 037 fiches, avec exactement les mêmes nombres de fiches, montants et dossiers PGA-Eau
          que les tableaux produits par `analyser_seao.py`
        - Un second chargement n'ajoute rien, et un contrat présent dans deux exports n'est compté
          qu'une fois
    - [x] `analyser_seao.py` allégé : ses petites fonctions utilitaires, comme le nettoyage d'un
          texte ou la lecture d'une date, sont rangées dans `utilitaires.py`. Les résultats sont
          restés identiques, octet pour octet
    - [x] Organismes avec population : de 614 à 640 sur 715
    - [x] Tests : de 41 à 96

### Décisions et ajustements

!!! info "Décisions"
    - Une ressemblance ne suffit pas. Un nom seulement approché n'est retenu que si un indice publié
      le confirme : le code postal, la désignation ou la région.
    - Un organisme dont la municipalité a été regroupée est rattaché à la nouvelle municipalité,
      avec sa population actuelle. Le fichier `regroupements.csv` garde l'ancien code et la source
      officielle de chaque regroupement. Cette convention reste à valider.
    - Un territoire non organisé est écarté quand une municipalité porte le même nom : il ne passe
      pas de contrats lui-même.
    - Dans la base, les clés viennent des données : code géographique, numéro de dossier,
      identifiants du SEAO. Seul l'organisme reçoit un numéro interne, puisque rien ne l'identifie
      officiellement.

### Difficultés rencontrées

!!! warning "Difficultés"
    - Pour les cas ambigus, les fiches du SEAO ne donnent pas l'adresse de l'acheteur. Les mêmes
      avis, republiés sur AchatsCanada, la donnent : c'est ce qui a permis de les trancher.
    - Trois des municipalités recherchées n'existent plus sous leur nom : elles ont été regroupées
      en 2025 et en 2026. Leurs données sur l'eau de 2024 portent encore leurs anciens codes.
    - Le fichier de contexte ne connaît pas tous les identifiants d'acheteur de Montréal, qui en a
      37 : la base les rattache par le nom, comme le fait déjà `analyser_seao.py`.

### Prochaines étapes

<div class="a-confirmer" markdown>

*À confirmer de ce qui sera livré la semaine prochaine:*

- Valider la règle PGA-Eau sur d'autres périodes du SEAO.
- Ajouter au modèle de données les démarches elles-mêmes (plan, date, lien, source), pour préparer
  le prototype d'interface du baromètre
- Ajouter le type de milieu, à partir de la classification de Statistique Canada par zones
  d'influence métropolitaine
- Décider quoi faire des 75 organismes non municipaux : les laisser sans population, ou les
  rattacher au territoire qu'ils desservent
- Faire une première comparaison ajustée à la population à partir de la base
</div>
