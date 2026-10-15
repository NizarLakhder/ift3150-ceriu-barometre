---
title: Synthèse
---

<style>
    @media screen and (min-width: 76em) {
        .md-sidebar--primary {
            display: none !important;
        }
    }
</style>


# Synthèse

Cette page présente une vue d'ensemble du projet. Elle est complétée au fil de la session.

## 1. Études préliminaires

### Le contexte

Les municipalités québécoises doivent s'engager dans un plan de gestion des actifs en eau avant le
31 décembre 2026, puis produire ce plan et en assurer le suivi à partir de 2028. Les municipalités
engagées obtiennent des bonifications dans des programmes de subvention. Il n'existe toutefois
aucune liste publique des municipalités engagées ou ayant terminé leur plan. Le projet cherche à
savoir si les données publiques permettent de combler ce manque.

### Ce que l'exploration des données a appris

Deux exports du SEAO ont été analysés en entier : la semaine du 7 au 13 septembre 2026, avec
1 561 fiches municipales, et le mois d'août 2026, avec 7 476 fiches municipales. Plusieurs constats
ont directement orienté la suite du projet.

- **Une fiche n'est pas un contrat.** Un export contient surtout des mises à jour de dossiers plus
  anciens. Sur 1 561 fiches, seulement 403 correspondent à un avis ouvert pendant la semaine.
  Additionner plusieurs exports compterait deux fois les mêmes dossiers : 476 apparaissent à la fois
  dans les deux fichiers étudiés, et le montant d'un même contrat peut changer d'un export à l'autre.
- **Aucun montant n'est une dépense payée.** Le fichier contient un montant attribué et un montant de
  contrat, qui diffèrent parfois. Le programme les garde séparés.
- **Un seuil de publication crée un angle mort.** Compté par contrat, seulement 8,5 % des contrats
  d'achat de la semaine du 7 septembre sont sous 25 000 $, et 7,9 % en août, contre 24,4 % et 28,6 %
  entre 25 000 $ et 50 000 $. Un petit mandat peut donc passer inaperçu.
- **Reconnaître une démarche est plus difficile qu'extraire les données.** L'export d'août contient
  quatre dossiers PGA-Eau : trois contrats attribués et un appel d'offres en cours (Windsor).
  Chercher le mot « PGA-Eau » en trouve deux sur quatre : Windsor écrit « PGA – Eau » avec un tiret
  long, et Mont-Tremblant n'emploie pas l'acronyme. Le filtre large « lié à l'eau » les trouve
  toutes, mais parmi 749 fiches, soit 10 % du mois : une règle trop étroite rate des cas, une règle
  trop large noie les bons.
- **Le SEAO ne contient pas le contexte.** Population, superficie et état des réseaux doivent venir
  d'autres sources, qui existent en données ouvertes au ministère des Affaires municipales et de
  l'Habitation.
- **Le nom ne suffit pas toujours à reconnaître une municipalité.** Le SEAO abrège (« St »,
  « Ste »), oublie un « de », ajoute une région entre parenthèses ou fait une faute de frappe. Et
  certaines municipalités ont été regroupées depuis avec leurs voisines. Le rattachement doit tolérer
  ces écarts, sans jamais deviner.

### Les choix qui en découlent

- Commencer par comprendre et documenter les données avant de construire des indicateurs.
- Mesurer ce qu'une règle de détection trouve, rate et attrape à tort avant de l'intégrer au
  programme, plutôt que de l'élargir à l'aveugle.
- Ne jamais inventer une donnée de contexte : une valeur non trouvée reste « À compléter », et une
  case qui ne s'applique pas le dit (« Sans objet »).
- Écrire un code simple et commenté. Il n'utilisait d'abord que la bibliothèque standard de Python.
  En octobre, avec l'accord du superviseur, deux bibliothèques s'y sont ajoutées, parce qu'elles
  évitaient de réécrire ce qui existe déjà : `rapidfuzz`, pour comparer des noms malgré les fautes,
  et `psycopg`, pour écrire dans PostgreSQL.

## 2. Réalisation

- **Un programme d'analyse**, `analyser_seao.py`, qui lit un export du SEAO, garde les acheteurs
  municipaux et produit quatre tableaux : le détail par fiche avec un lien vers l'avis public, un
  résumé par organisme, l'état du contexte municipal, et une liste de points à relire. Il repère
  aussi les dossiers PGA-Eau avec une règle dédiée (colonne `pga_eau`).
- **Un programme de contexte**, `completer_contexte.py`, qui rattache les organismes au répertoire
  des municipalités et aux données sur l'eau potable. Il tolère les écarts d'écriture du SEAO, mais
  n'accepte un nom seulement approché que si un indice publié le confirme. Population, superficie et
  région sont renseignées pour 305 des 346 organismes de la semaine et 593 des 665 organismes
  d'août. Les autres ne sont pas des municipalités : des régies, des sociétés de transport, des
  offices d'habitation. Les neuf cas qu'aucun indice ne permettait de trancher ont été réglés à la
  main, chacun avec sa source publique.
- **Un fichier de contexte protégé**, `contexte_municipalites.csv`, qui reçoit les organismes de
  chaque nouvel export sans qu'aucune ligne existante ni aucune saisie manuelle ne soit modifiée. Une
  case sans chiffre y dit pourquoi : à compléter, sans objet, hors MRC ou aucune donnée.
- **Une base PostgreSQL**, remplie par `charger_base.py`. Elle range les données en quatre groupes,
  le territoire, les organismes, les fiches du SEAO et les analyses, soit 19 tables. Elle cumule
  plusieurs exports sans compter deux fois un même dossier, et garde la dernière version de chaque
  contrat.
- **Un essai de modèle de langage** : qwen2.5, un petit modèle installé avec Ollama sur un ordinateur
  personnel, pour lire les fiches du SEAO une à une.
- **Un rapport destiné au CERIU**, qui présente les résultats, leurs limites et les décisions
  attendues du partenaire.

## 3. Évaluation

Ce qui a pu être vérifié à ce stade :

- 96 tests automatisés vérifient les comportements délicats du code, comme l'identification des
  fournisseurs, la protection des saisies manuelles, le départage des homonymes et la tolérance aux
  fautes de frappe;
- les programmes donnent exactement les mêmes résultats d'une exécution à l'autre, et chaque
  correction a été vérifiée en comparant les sorties avant et après;
- des fiches représentatives ont été examinées directement dans le JSON et sur les avis publiés;
- la tolérance aux fautes a été mise à l'épreuve : sur 36 907 fautes introduites exprès dans les noms
  officiels, 83 % sont retrouvées, et aucune ne mène à une mauvaise municipalité;
- la base de données redonne exactement les chiffres du programme d'analyse : mêmes fiches, mêmes
  montants au cent près, mêmes dossiers PGA-Eau. Un second chargement n'ajoute rien;
- la détection des PGA-Eau a été mesurée : chercher le mot « PGA-Eau » trouve deux des quatre
  dossiers de l'export d'août, et le filtre « lié à l'eau » les trouve tous, parmi 749 fiches. La
  règle maintenant intégrée au programme trouve les cinq dossiers des deux exports sans faux
  positif. Ce résultat reste à confirmer sur d'autres périodes. Et ces cinq dossiers ont eux-mêmes
  été repérés par leur titre : la règle ne dit rien des mandats dont le titre ne parle ni de PGA ni
  de gestion d'actifs;
- le petit modèle de langage sait extraire des champs précis d'une fiche, mais quand on lui demande
  d'analyser cinq fiches à la fois, il ne reconnaît aucun des trois dossiers PGA-Eau. Il coupe aussi,
  sans prévenir, un message trop long pour sa fenêtre de lecture.

Ce qui reste à valider :

- le sens exact des champs de montant, auprès de la documentation du SEAO;
- la couverture réelle de la méthode, par comparaison avec une liste de référence du CERIU;
- l'interprétation des résultats avec l'expertise municipale du comité aviseur;
- la place des organismes non municipaux et des municipalités regroupées dans les comparaisons;
- la part des mandats de gestion d'actifs que la règle ne voit pas, faute de mots clés dans leur
  titre, et celle qui ne passe jamais par le SEAO.

## 4. Bilan

> Prenez du recul sur l'ensemble du projet.
>
> Présentez notamment :
>
> * les principales contributions du projet ;
> * les objectifs atteints, partiellement atteints ou non atteints ;
> * les forces et limites du résultat obtenu ;
> * les difficultés ou contraintes importantes rencontrées ;
> * les apprentissages techniques ou méthodologiques réalisés ;
> * les éléments qui mériteraient d'être poursuivis ou améliorés.
>
> Le bilan doit permettre de comprendre **où en est réellement le projet à la fin de la session**, ce qui a été appris et quelles seraient les prochaines étapes pertinentes.
