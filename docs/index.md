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

### Validation et Évaluation

> Indiquez comment vous évaluerez que votre solution répond aux objectifs du projet (ex. scénarios d’usage, tests, retours utilisateurs, indicateurs qualitatifs ou quantitatifs).

## Échéancier

!!! info
    Le suivi complet est disponible dans la page [Suivi de projet](suivi.md).

| Activités                      | Début   |   Fin   | Livrable                            | Statut      |
|--------------------------------|---------|---------|-------------------------------------|-------------|
| Ouverture de projet            | 4 Septembre   | 15 Septembre  | Proposition de projet               | ✅ Terminé  |
| Études préliminaires           | 4 Septembre   | 22 Septemebre  | Document d'analyse                  | 🔄 En cours |
| Présentation + Rapport         | 7 Decembre  | 14 Decembre | Présentation + Rapport              | ⏳ À venir  |
