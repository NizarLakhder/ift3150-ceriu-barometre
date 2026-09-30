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
  dans les deux fichiers étudiés.
- **Aucun montant n'est une dépense payée.** Le fichier contient un montant attribué et un montant de
  contrat, qui diffèrent parfois. Le programme les garde séparés.
- **Un seuil de publication crée un angle mort.** Compté par contrat, seulement 8,5 % des contrats
  d'achat de la semaine du 7 septembre sont sous 25 000 $, et 7,9 % en août, contre 24,4 % et 28,6 %
  entre 25 000 $ et 50 000 $. Une petite municipalité qui paie son plan moins cher est donc presque
  invisible.
- **Reconnaître une démarche est plus difficile qu'extraire les données.** L'export d'août contient
  quatre dossiers PGA-Eau : trois contrats attribués et un appel d'offres en cours (Windsor).
  Chercher le mot « PGA-Eau » en trouve deux sur quatre : Windsor écrit « PGA – Eau » avec un tiret
  long, et Mont-Tremblant n'emploie pas l'acronyme. Le filtre large « lié à l'eau » les trouve
  toutes, mais parmi 749 fiches, soit 10 % du mois : une règle trop étroite rate des cas, une règle
  trop large noie les bons.
- **Le SEAO ne contient pas le contexte.** Population, superficie et état des réseaux doivent venir
  d'autres sources, qui existent en données ouvertes au ministère des Affaires municipales et de
  l'Habitation.

### Les choix qui en découlent

- Commencer par comprendre et documenter les données avant de construire des indicateurs.
- Mesurer ce qu'une règle de détection trouve, rate et attrape à tort avant de l'intégrer au
  programme, plutôt que de l'élargir à l'aveugle.
- Ne jamais inventer une donnée de contexte : une valeur non trouvée reste « À compléter ».
- Écrire un code simple, en Python sans dépendance externe, que le CERIU pourra reprendre.

## 2. Réalisation

- **Un programme d'analyse**, `analyser_seao.py`, qui lit un export du SEAO, garde les acheteurs
  municipaux et produit quatre tableaux : le détail par fiche avec un lien vers l'avis public, un
  résumé par organisme, l'état du contexte municipal, et une liste de points à relire.
- **Un programme de contexte**, `completer_contexte.py`, qui rattache les organismes au répertoire
  des municipalités et aux données sur l'eau potable. Sur les 346 organismes de la semaine, 286 ont
  maintenant leur population, leur superficie, leur région et leur MRC, et 188 ont des données sur
  l'état de leur réseau d'eau. Le fichier de contexte ajoute Nicolet et Windsor, saisies à la main,
  d'où 288 lignes sur 348 avec une population.
- **Un fichier de contexte protégé**, `contexte_municipalites.csv`, où les saisies manuelles ne sont
  jamais écrasées par les programmes.
- **Un rapport destiné au CERIU**, qui présente les résultats, leurs limites et les décisions
  attendues du partenaire.

## 3. Évaluation

Ce qui a pu être vérifié à ce stade :

- 23 tests automatisés vérifient les comportements délicats du code, comme l'identification des
  fournisseurs et la protection des saisies manuelles;
- les programmes donnent exactement les mêmes résultats d'une exécution à l'autre;
- des fiches représentatives ont été examinées directement dans le JSON et sur les avis publiés;
- la détection des PGA-Eau a été mesurée : chercher le mot « PGA-Eau » trouve deux des quatre
  dossiers de l'export d'août, et le filtre « lié à l'eau » les trouve tous, parmi 749 fiches. Une
  règle affinée, testée à part et pas encore intégrée au programme, trouve les cinq dossiers des
  deux exports sans faux positif. Ce résultat reste à confirmer sur d'autres périodes.

Ce qui reste à valider :

- le sens exact des champs de montant, auprès de la documentation du SEAO;
- la couverture réelle de la méthode, par comparaison avec une liste de référence du CERIU;
- l'interprétation des résultats avec l'expertise municipale du comité aviseur.

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