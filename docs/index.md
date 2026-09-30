---
title: Vue d'ensemble du projet
---

<style>
    @media screen and (min-width: 76em) {
        .md-sidebar--primary {
            display: none !important;
        }
    }
</style>

# Vue d'ensemble du projet

!!! info "Informations générales"

    **Session** : Automne 2026  
    **Auteur** : Nizar Lakhder (20229915)  
    **Thèmes** : Données ouvertes, automatisation, ingénierie des données, gestion d'actifs municipale, visualisation  
    **Superviseur** : Louis-Édouard Lafontant (Université de Montréal)  
    **Collaborateur** : Jérémy Diaz (CERIU)

## Description du projet


### Contexte


Les municipalités québécoises doivent mettre en place différentes démarches liées à la gestion de leurs infrastructures, comme les plans de gestion des actifs en eau (PGA-Eau), les plans climat, les plans de gestion des actifs en bâtiment ou encore les plans d'immobilisation.

Une partie des informations liées à ces démarches est disponible publiquement, notamment dans le SEAO, sur Données Québec ou directement sur les sites des municipalités. Le problème est que ces informations sont réparties entre plusieurs sources et qu'elles ne sont pas toujours présentées de la même façon.

Ce projet, réalisé en collaboration avec le CERIU, cherche donc à voir comment on peut utiliser ces données publiques pour mieux comprendre où en sont les municipalités dans leurs démarches de gestion d'actifs.

Dans un premier temps, le projet se concentre sur le PGA-Eau.

### Problématique

Même si plusieurs informations sont publiques, il reste difficile d'avoir une vue claire de l'état d'avancement d'une municipalité dans une démarche comme le PGA-Eau.

Par exemple, le SEAO peut montrer qu'une municipalité a publié un appel d'offres ou attribué un contrat lié à un PGA-Eau, mais cela ne permet pas forcément de savoir si le plan a ensuite été terminé, approuvé ou publié.

Il faut aussi faire attention à l'interprétation des données. Le fait de ne rien trouver dans une source ne veut pas nécessairement dire qu'une municipalité n'a rien fait. L'information peut simplement être publiée ailleurs ou ne pas être disponible publiquement.

Le projet cherche donc à répondre à plusieurs questions :

- Jusqu'où peut-on suivre l'avancement d'une démarche municipale à partir de données publiques?
- Quelles informations peut-on extraire automatiquement de façon fiable?
- Quelles sont les limites des différentes sources?
- Comment les résultats obtenus se comparent-ils à ceux d'un agent automatisé et aux informations disponibles au CERIU?


### Proposition et objectifs

L'idée du projet est de développer un processus permettant de récupérer, structurer et analyser des informations publiques liées aux pratiques de gestion d'actifs municipales.

Le travail commencera avec les données ouvertes du SEAO et le PGA-Eau comme premier cas d'étude.

Un premier prototype devra permettre de repérer automatiquement les entrées potentiellement liées au PGA-Eau et d'en extraire certaines informations utiles, par exemple :

- la municipalité;
- le titre de l'avis;
- les dates disponibles;
- le fournisseur;
- les montants;
- le statut;
- le lien vers la source.

Les principaux objectifs sont les suivants :


1. développer un premier prototype d'extraction à partir des données du SEAO;
2. structurer les informations obtenues de façon cohérente;
3. vérifier manuellement une partie des résultats;
4. comparer les résultats avec ceux d'un agent automatisé, notamment Hermes, ainsi qu'avec les informations disponibles au CERIU;

### Méthodologie

Le projet sera réalisé de manière progressive afin de pouvoir valider chaque étape avant de passer à la suivante.

Les principales étapes prévues sont :

1. **Comprendre les données.** Parcourir les exports du SEAO en entier, jamais un échantillon, pour
   établir leur structure réelle : champs présents ou absents, emplacement des montants, sens des
   dates.
2. **Extraire et structurer.** Isoler les acheteurs municipaux et produire des tableaux vérifiables,
   où chaque ligne renvoie à son avis public.
3. **Ajouter le contexte.** Rattacher chaque organisme à des sources officielles, comme le répertoire
   des municipalités, pour connaître sa population, sa taille et l'état de son réseau d'eau.
4. **Valider.** Mesurer ce que la méthode trouve, ce qu'elle rate et ce qu'elle attrape à tort, sur
   des cas vérifiés à la main.
5. **Comparer.** Confronter les résultats à ceux d'un agent automatisé et aux informations du CERIU.
6. **Ensuite seulement,** proposer des indicateurs et envisager un baromètre.

Le code d'analyse se trouve à la racine du dépôt : `analyser_seao.py` et `completer_contexte.py`.
Il n'utilise que la bibliothèque standard de Python, pour que le CERIU puisse le reprendre sans rien
installer.

### Validation et Évaluation

La solution sera évaluée sur plusieurs plans :

- **Fiabilité du code** : tests automatisés sur de petits cas construits, dont la réponse est connue;
- **Reproductibilité** : une nouvelle exécution sur les mêmes fichiers doit donner exactement les
  mêmes résultats;
- **Justesse de l'extraction** : vérification manuelle de fiches représentatives, directement dans le
  JSON et sur les avis publiés;
- **Qualité de la détection** : nombre de démarches trouvées, manquées et détectées à tort, mesuré
  sur des cas vérifiés à la main;
- **Validation externe** : comparaison avec une liste de référence du CERIU, si elle peut être
  obtenue, et avec l'expertise municipale du comité aviseur.

Les seuils de réussite chiffrés restent à préciser avec le superviseur.

## Échéancier

!!! info
    Le suivi complet est disponible dans la page [Suivi de projet](suivi.md).

| Activités                      | Début   |   Fin   | Livrable                            | Statut      |
|--------------------------------|---------|---------|-------------------------------------|-------------|
| Ouverture de projet            | 4 septembre   | 15 septembre  | Proposition de projet               | ✅ Terminé  |
| Études préliminaires           | 16 septembre  | 2 octobre     | Diagnostic des données, prototype, rapport au CERIU | 🔄 En cours |
| Première mise en commun        | 2 octobre     | 2 octobre     | Présentation                        | 🔄 En cours |
| Suite du projet                | À préciser    | À préciser    | À préciser avec le superviseur      | ⏳ À venir  |
| Présentation + Rapport         | 7 décembre    | 14 décembre   | Présentation + Rapport              | ⏳ À venir  |
