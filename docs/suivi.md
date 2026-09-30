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

## Semaines 1 et 2 (4 au 15 septembre) — Ouverture et premier contact avec les données

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

## Semaine 3 (16 au 22 septembre) — Diagnostic complet et premier prototype d'analyse

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

## Semaine 4 (23 au 29 septembre) — Contexte municipal et fichier mensuel

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
      Résolu : le rapprochement accepte maintenant un changement d'identifiants dès qu'au moins
      un identifiant est commun.
    - Les municipalités n'écrivent pas toutes « PGA-Eau » de la même façon : l'une utilise un tiret
      long, une autre n'emploie pas l'acronyme, ce qui fait échouer une recherche du mot
      « PGA-Eau ».
    - Deux lignes du fichier de contexte ont disparu sans que la cause puisse être retrouvée. Cet
      incident motive la mise sous contrôle de version du code.

---

## Semaine 5 (30 septembre au 2 octobre) — Première mise en commun

### Objectifs de la période
- Présenter le projet, la solution envisagée et l'état d'avancement lors de la mise en commun
  du 2 octobre
- Mettre le code d'analyse et la documentation dans le dépôt du projet

### Travail réalisé

!!! abstract "Avancement"
    - [x] Préparation de la présentation en cinq diapositives
    - [x] Réécriture des programmes pour les rendre plus lisibles : `analyser_seao.py` et
          `completer_contexte.py`
    - [ ] Mise en commun du 2 octobre

### Prochaines étapes

- Élargir la détection des plans de gestion d'actifs, en mesurant les faux positifs sur un
  échantillon lu à la main
- Compléter le contexte des organismes présents dans le fichier mensuel
- Départager les douze municipalités homonymes
- Produire une première comparaison ajustée à la population
- Étudier une base de données pour cumuler plusieurs périodes sans compter deux fois les mêmes
  dossiers : 476 dossiers apparaissent à la fois dans l'export hebdomadaire et dans le mensuel
- Préciser avec le CERIU l'accès à l'agent Hermes et la tâche à lui confier
