# Template de site web pour IFT3150 — Projet informatique

Ce répertoire contient un **template de site web de projet pour le cours IFT3150**, construit avec **Zensical**.

Le site accompagne le projet tout au long de la session. Il sert notamment à :

* présenter le projet et ses objectifs ;
* documenter son évolution et le travail réalisé ;
* synthétiser les études, réalisations et résultats obtenus ;
* conserver les principales références et ressources utilisées ;
* centraliser la documentation de l'équipe dans un format clair et accessible.

## Prérequis

Assurez-vous d'avoir les outils suivants installés :

* Python **3.11** ou plus récent ;
* `pip`, le gestionnaire de paquets Python ;
* Git, pour cloner et versionner le projet.

## Installation

### 1. Récupérer le template

Clonez le dépôt :

```bash
git clone git@github.com:udem-diro/template-projet.git
```

Puis placez-vous dans le répertoire du projet :

```bash
cd template-projet
```

Vous pouvez ensuite renommer le dossier ou associer le projet à votre propre dépôt Git.

### 2. Installer les dépendances

Installez les dépendances du projet :

```bash
pip install -r requirements.txt
```

Cette commande installe notamment **Zensical**, utilisé pour construire et prévisualiser le site.

## Utilisation

Vous devez au minimum :

1. modifier les pages Markdown dans le dossier `docs/` ;
2. adapter la présentation et la description du projet ;
3. maintenir le suivi du travail réalisé durant la session ;
4. compléter progressivement la synthèse et les références.

Le contenu fourni dans le template sert de **structure de départ**. Adaptez-le à la nature de votre projet.

### Travailler en local

Pour lancer le site sur votre poste :

```bash
zensical serve
```

Le site sera accessible à l'adresse :

```text
http://localhost:8000
```

Les modifications apportées aux fichiers du dossier `docs/` sont automatiquement prises en compte lors du développement.

Vous pouvez également demander à Zensical d'ouvrir automatiquement le site dans votre navigateur :

```bash
zensical serve --open
```

## Construction du site

Pour générer la version statique du site :

```bash
zensical build
```

Les fichiers générés sont placés par défaut dans le dossier `site/`.

Pour reconstruire complètement le site en supprimant les données de construction précédentes :

```bash
zensical build --clean
```

> Cette étape n'est généralement pas nécessaire lorsque vous travaillez avec `zensical serve`, mais elle peut être utile pour vérifier la version finale du site.

## Déploiement sur GitHub Pages

Le template utilise **GitHub Actions** pour construire et publier automatiquement le site sur GitHub Pages.

Le workflow de déploiement se trouve dans :

```text
.github/workflows/docs.yml
```

Une fois GitHub Pages configuré pour utiliser **GitHub Actions**, le déploiement se fait automatiquement lorsque des modifications sont envoyées vers la branche principale du dépôt.

Votre workflow habituel devient donc simplement :

```bash
git add .
git commit -m "Mise à jour du projet"
git push
```

GitHub se charge ensuite de construire et de publier le site.

## Structure du projet

```text
.
├── .github/
│   └── workflows/
│       └── docs.yml          # Construction et déploiement GitHub Pages
│
├── docs/
│   ├── index.md              # Présentation et vue d'ensemble du projet
│   ├── suivi.md              # Suivi périodique du travail
│   ├── synthese.md           # Synthèse des travaux et résultats
│   └── references.md         # Références, ressources et utilisation de l'IA
│
├── zensical.toml             # Configuration du site et de la navigation
├── requirements.txt          # Dépendances Python
└── site/                     # Site généré lors de la construction
```

> L'essentiel du contenu que vous aurez à modifier se trouve dans le dossier `docs/`.

## Pages du site

### `index.md` — Présentation du projet

Présente le contexte, le problème abordé, les objectifs du projet, l'équipe ainsi que les principales informations permettant de comprendre le mandat.

### `suivi.md` — Suivi

Documente périodiquement l'évolution du projet, le travail réalisé, les difficultés rencontrées et les prochaines étapes.

Cette page doit être mise à jour **tout au long de la session**.

### `synthese.md` — Synthèse

Présente une vue d'ensemble du travail accompli autour de quatre phases :

1. **Études préliminaires**
2. **Réalisation**
3. **Évaluation**
4. **Bilan**

La structure est volontairement générale afin de pouvoir être adaptée aux différents types de projets.

### `references.md` — Références

Rassemble les principales sources et ressources ayant contribué au projet.

Pour chaque référence importante, précisez brièvement **comment elle a été utilisée ou en quoi elle a influencé le travail réalisé**.

Cette page permet également de documenter l'utilisation d'outils d'**intelligence artificielle** dans le cadre du projet.

## Personnalisation

La configuration principale du site se trouve dans :

```text
zensical.toml
```

Vous pouvez notamment y modifier :

* le nom du site ;
* la navigation ;
* l'adresse du site publié ;
* le dépôt Git associé ;
* les fonctionnalités du thème.

Le contenu des pages se trouve dans `docs/` et est rédigé en Markdown.

Vous pouvez ajouter des pages ou réorganiser la navigation lorsque cela est pertinent pour votre projet.

## Licence

Ce template est distribué sous licence MIT. Consultez le fichier `LICENSE` pour plus de détails.

## Questions ou problèmes ?

En cas de problème avec le template ou son utilisation, vous pouvez ouvrir une issue sur le dépôt GitHub ou communiquer avec le coordonnateur du cours.
