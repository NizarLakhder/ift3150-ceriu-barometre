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
avis, attributions et contrats des organismes publics, dont les acheteurs municipaux. Sept exports
ont été analysés en entier : les mois de mai, août et septembre 2026, la semaine du 7 au
13 septembre 2026 et les trois semaines du 28 septembre au 18 octobre 2026.

**Ministère des Affaires municipales et de l'Habitation.** *Répertoire des municipalités du Québec*.
Données Québec, licence Creative Commons avec attribution.
<https://www.donneesquebec.ca/recherche/dataset/repertoire-des-municipalites-du-quebec>

Source de la population, de la superficie et de la région de chaque organisme. Trois fichiers en
sont tirés : la liste des municipalités, qui donne le code géographique, la population décrétée, la
superficie, la région administrative, la MRC, le code postal de l'hôtel de ville et la date de
constitution; la liste des MRC et des communautés métropolitaines, avec leur population et leur
superficie; et la liste des organismes périmunicipaux, qui permet de reconnaître les régies et les
sociétés de transport. Sert au contexte municipal de l'axe 2, puisque le SEAO ne contient aucune de
ces informations.

**Ministère des Affaires municipales et de l'Habitation.** *Stratégie québécoise d'économie d'eau
potable 2019-2025*. Données Québec, licence Creative Commons avec attribution.
<https://www.donneesquebec.ca/recherche/dataset/sqeep-2019-2025>

Fournit, pour 1 104 municipalités ayant un réseau de distribution, la population desservie, un indice
de fuites dans les infrastructures, la validité des audits de l'eau, la consommation résidentielle et
la longueur du réseau. Ces données décrivent l'état des réseaux et se relient au répertoire par le
code géographique. Dans deux des trois fichiers utilisés, le zéro du début de certains codes a
disparu (« 3005 » pour Gaspé) : les programmes le rétablissent.

### Sources consultées pour les cas tranchés à la main

Dix-huit organismes ne pouvaient pas être rattachés par leur seul nom, et sept rattachements obtenus par
les règles tolérantes demandaient une vérification. Chaque cas a été tranché ou vérifié avec une
source publique, citée cas par cas dans la colonne `notes` de `contexte_municipalites.csv`.

**Secrétariat du Conseil du trésor.** *Système électronique d'appel d'offres (SEAO)*, pages d'avis
consultées une à une. <https://seao.gouv.qc.ca/>

Elles donnent l'adresse prévue pour la réception des soumissions et la région de livraison. Onze pages
ont été consultées.

**Gouvernement du Canada.** *AchatsCanada*, avis republiés depuis le SEAO.
<https://canadabuys.canada.ca/>

Le site fédéral republie les avis du SEAO sous le même numéro, précédé de « qc », et donne l'adresse
de l'acheteur. C'est ce qui a permis de distinguer les deux Saint-Donat du Québec, et de reconnaître
Saint-Simon-de-Rimouski, écrit « Saint-Simon-de-Rimsouki » dans le SEAO.

**Gouvernement du Québec.** Annonces officielles des trois regroupements municipaux récents,
consignés avec leur source dans `regroupements.csv` :

- Hébertville, avec Saint-Bruno et Hébertville-Station, le 1er janvier 2026 :
  <https://www.quebec.ca/nouvelles/actualites/details/saint-bruno-hebertville-et-hebertville-station-se-regroupent-et-consolident-leurs-services-67814>
- Amos, avec Saint-Félix-de-Dalquier, le 1er janvier 2025 :
  <https://www.quebec.ca/nouvelles/actualites/details/la-ville-damos-et-la-municipalite-de-saint-felix-de-dalquier-formeront-la-nouvelle-ville-damos-des-le-1er-janvier-2025-60261>
- La Pocatière, avec Sainte-Anne-de-la-Pocatière et Saint-Onésime-d'Ixworth, le 3 septembre 2025,
  selon un avis du ministère de la Justice :
  <https://cdn-contenu.quebec.ca/cdn-contenu/adm/min/justice/publications-adm/avis-publics/Avis_Regroupement_La_Pocatiere.pdf>

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

**Statistique Canada.** *Glossaire illustré : Classification des secteurs statistiques (CSS)*,
Recensement de 2021.
<https://www150.statcan.gc.ca/pub/92-195-x/2021001/other-autre/sac-css/sac-css-fra.htm>

Classe chaque subdivision de recensement, qui correspond en général à une municipalité, selon
qu'elle fait partie d'une région métropolitaine, d'une agglomération, ou d'une zone sous influence
métropolitaine forte, modérée, faible ou nulle. C'est la piste la plus directe pour le type de
milieu.

**Ministère de l'Environnement du Québec.** *Zones de gestion intégrée de l'eau par bassin versant*.
Données Québec.
<https://www.donneesquebec.ca/recherche/dataset/zgiebv>

Piste pour rattacher chaque municipalité à son bassin versant. Disponible seulement en format
cartographique, ce qui demande un traitement géographique.

## Outils

**Python Software Foundation.** *Bibliothèque standard de Python* : modules `csv`, `json`,
`hashlib` et `unittest`. <https://docs.python.org/3/library/>

Au départ, les programmes n'utilisaient que la bibliothèque standard, pour que le CERIU puisse les
reprendre sans rien installer. Depuis octobre 2026, avec l'accord du superviseur, deux bibliothèques
s'y ajoutent, quand elles évitent de réécrire ce qui existe déjà.

**RapidFuzz.** <https://rapidfuzz.github.io/RapidFuzz/>

Mesure l'écart entre deux mots, en comptant les lettres ajoutées, retirées, remplacées ou inversées.
Sert à reconnaître un nom de municipalité malgré une faute de frappe.

**Psycopg.** <https://www.psycopg.org/>

Relie Python à PostgreSQL. Sert à charger les données dans la base du projet.

**PostgreSQL Global Development Group.** *PostgreSQL*. <https://www.postgresql.org/>

Accueille la base de données du projet. Ses extensions `unaccent` et `pg_trgm` servent à chercher
sans tenir compte des accents, et par noms proches.

**Ollama.** <https://ollama.com/>

A servi à faire tourner sur un ordinateur personnel un petit modèle de langage, qwen2.5 à
3 milliards de paramètres, pour lire les fiches du SEAO une à une.

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

> **ChatGPT (OpenAI)**
>
> Utilisé principalement pour explorer différentes stratégies de traitement des données et générer des pistes d'implémentation. Les propositions obtenues ont été vérifiées à partir de la documentation officielle et adaptées à l'architecture du projet avant leur intégration.

> **GitHub Copilot**
>
> Utilisé ponctuellement pour assister la rédaction de code répétitif et de tests. Le code généré a été révisé et testé par l'équipe avant d'être conservé dans le projet.

## Références

> Ajoutez vos références ci-dessous en utilisant une présentation cohérente.