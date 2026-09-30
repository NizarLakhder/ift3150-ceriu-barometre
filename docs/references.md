---
title: Références
---

<style>
    @media screen and (min-width: 76em) {
        .md-sidebar--primary {
            display: none !important;
        }
    }
</style>

# Références

Cette page rassemble les principales sources utilisées dans le projet, et précise le rôle que
chacune a joué dans le travail réalisé.

## Données

**Secrétariat du Conseil du trésor.** *Système électronique d'appel d'offres (SEAO)*. Données
Québec, licence Creative Commons avec attribution.
<https://www.donneesquebec.ca/recherche/dataset/systeme-electronique-dappel-doffres-seao>

Source principale du projet. Les exports hebdomadaires et mensuels au format JSON fournissent les
avis, attributions et contrats des organismes publics, dont les acheteurs municipaux. Deux exports
ont été analysés en entier : la semaine du 7 au 13 septembre 2026 et le mois d'août 2026.

**Ministère des Affaires municipales et de l'Habitation.** *Répertoire des municipalités du Québec*.
Données Québec, licence Creative Commons avec attribution.
<https://www.donneesquebec.ca/recherche/dataset/repertoire-des-municipalites-du-quebec>

Fournit le code géographique, la population décrétée, la superficie, la région administrative et la
MRC de chaque municipalité. Sert au contexte municipal de l'axe 2, puisque le SEAO ne contient aucune
de ces informations.

**Ministère des Affaires municipales et de l'Habitation.** *Stratégie québécoise d'économie d'eau
potable 2019-2025*. Données Québec, licence Creative Commons avec attribution.
<https://www.donneesquebec.ca/recherche/dataset/sqeep-2019-2025>

Fournit, pour 1 104 municipalités ayant un réseau de distribution, la population desservie, un indice
de fuites dans les infrastructures et la validité des audits de l'eau. Ces données décrivent l'état
des réseaux et se relient au répertoire par le code géographique.

## Documentation

**Gouvernement du Québec.** *Préparer un plan de gestion des actifs en eau (PGA-Eau)*.
<https://www.quebec.ca/habitation-territoire/infrastructures-municipales/plan-gestion-actif-pga/eau>

A permis de comprendre les trois étapes officielles d'un PGA-Eau et l'échéance d'engagement du
31 décembre 2026. A aussi montré qu'il n'existe pas de liste publique des municipalités engagées,
ce qui justifie la démarche du projet.

**Open Contracting Partnership.** *Open Contracting Data Standard (OCDS)*, version 1.1.
<https://standard.open-contracting.org/>

A servi à comprendre la structure des exports du SEAO, qui suivent ce standard : fiches, parties,
avis, attributions et contrats. L'analyse a aussi montré des écarts entre le standard et les
fichiers réels, par exemple le bloc des soumissions.

**Centre d'expertise et de recherche en infrastructures urbaines (CERIU).** Charte de projet du
baromètre, document interne non diffusé, 2026.

Précise le mandat du partenaire, les livrables attendus et les autres démarches à étudier par la
suite, comme le PGA-Bâtiment et le plan climat.

### Pistes explorées, pas encore utilisées

**Statistique Canada.** *Classification des centres de population et des régions rurales.*

Définit un centre de population comme un territoire d'au moins 1 000 habitants et 400 habitants au
kilomètre carré. Piste pour remplir le type de milieu des municipalités à partir de données déjà
disponibles.

**Ministère de l'Environnement du Québec.** *Zones de gestion intégrée de l'eau par bassin versant*.
Données Québec.
<https://www.donneesquebec.ca/recherche/dataset/zgiebv>

Piste pour rattacher chaque municipalité à son bassin versant. Disponible seulement en format
cartographique, ce qui demande un traitement géographique.

## Outils

**Python Software Foundation.** *Bibliothèque standard de Python* : modules `csv`, `json` et
`unittest`. <https://docs.python.org/3/library/>

Les programmes d'analyse n'utilisent que la bibliothèque standard, pour que le CERIU puisse les
reprendre sans rien installer.

**Zensical.** <https://zensical.org/>

Génère et publie ce site de suivi.

## Utilisation de l'intelligence artificielle

> Documentez les principaux usages de **systèmes d'intelligence artificielle générative ou d'assistants basés sur des modèles de langage** dans le cadre du projet.
>
> L'objectif n'est pas de retranscrire l'ensemble des conversations ou requêtes effectuées, mais de rendre explicite **le rôle joué par ces outils dans votre démarche**.

### Pour chaque outil utilisé

> Indiquez, lorsque pertinent :
>
> * le nom de l'outil ou du modèle utilisé ;
> * les principales tâches pour lesquelles il a été employé ;
> * la manière dont les résultats produits ont été vérifiés, adaptés ou intégrés au projet ;
> * les limites ou problèmes rencontrés lors de son utilisation.

### Exemple

> **ChatGPT — OpenAI**
>
> Utilisé principalement pour explorer différentes stratégies de traitement des données et générer des pistes d'implémentation. Les propositions obtenues ont été vérifiées à partir de la documentation officielle et adaptées à l'architecture du projet avant leur intégration.

> **GitHub Copilot**
>
> Utilisé ponctuellement pour assister la rédaction de code répétitif et de tests. Le code généré a été révisé et testé par l'équipe avant d'être conservé dans le projet.

## Références

> Ajoutez vos références ci-dessous en utilisant une présentation cohérente.