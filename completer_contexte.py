"""
Complète le contexte municipal avec les données officielles du MAMH.

Projet IFT3150 de Nizar Lakhder, Université de Montréal, automne 2026.

Le SEAO ne dit rien de la population, de la superficie ni de l'état des
réseaux d'eau. Ces informations viennent de deux jeux de données ouverts du
ministère des Affaires municipales et de l'Habitation, publiés sur Données
Québec sous licence Creative Commons avec attribution.

Ce programme ne télécharge rien. Il lit les fichiers déposés à la main dans
donnees_reference/ et reporte leurs valeurs dans contexte_municipalites.csv.
Pourquoi ne pas télécharger? Pour que les mêmes fichiers donnent toujours les
mêmes chiffres, et pour ne pas dépendre d'une adresse web qui peut changer du
jour au lendemain. La date des fichiers utilisés est notée dans la colonne
source_contexte : on peut toujours retrouver d'où vient une valeur.

Fichiers attendus dans donnees_reference/, à prendre sur Données Québec :

  Répertoire des municipalités du Québec
    MUN.csv                          obligatoire : code géographique,
                                     population, superficie, région, MRC
    MRC_CM_Arg.csv                   facultatif : MRC et communautés
                                     métropolitaines
    A01_CONVERT_XML_ORG_PER_MUN.xml  facultatif : régies, transport,
                                     habitation

  Stratégie québécoise d'économie d'eau potable 2019-2025, données de 2024
    validite_classe_2024.csv         facultatif : population desservie et
                                     validité des audits de l'eau
    fuites_classe_2024.csv           facultatif : indice de fuites
    consommation_classe_2024.csv     facultatif : consommation résidentielle

Ce que le programme s'interdit :

  - remplacer une valeur déjà saisie : il ne remplit que les cases encore
    « À compléter »;
  - choisir au hasard : quand un nom correspond à plusieurs organismes du
    répertoire, il ne remplit rien et signale le cas;
  - inventer : la proximité d'un cours d'eau et le type de milieu restent
    à compléter, puisqu'aucun de ces fichiers ne les fournit.

Avant d'écrire, il copie le contexte actuel dans
sorties/contexte_municipalites.csv.bak. Il n'y a qu'une sauvegarde, remplacée
à chaque exécution. Les cas ambigus et les organismes introuvables sont
listés dans sorties/contexte_a_verifier.csv, à traiter à la main.

Lancement :  python completer_contexte.py
"""

import csv
import re
import shutil
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

CONTEXTE_CSV = Path("contexte_municipalites.csv")
DOSSIER_SOURCES = Path("donnees_reference")
DOSSIER_SORTIES = Path("sorties")
A_VERIFIER_CSV = DOSSIER_SORTIES / "contexte_a_verifier.csv"

# Pour chaque fichier : son nom, s'il est obligatoire, et où le trouver sur
# Données Québec (le jeu de données, puis la ressource). Cette description est
# affichée quand le fichier manque, pour savoir quoi aller chercher.
FICHIERS = {
    "municipalites": ("MUN.csv", True,
                      "Répertoire des municipalités du Québec, « Liste des municipalités (csv) »"),
    "mrc": ("MRC_CM_Arg.csv", False,
            "Répertoire des municipalités du Québec, « Liste des MRC_CM_Arg (csv) »"),
    "perimunicipaux": ("A01_CONVERT_XML_ORG_PER_MUN.xml", False,
                       "Répertoire des municipalités du Québec, « Liste des organismes périmunicipaux »"),
    "validite": ("validite_classe_2024.csv", False,
                 "Stratégie d'économie d'eau potable, « Validité des audits de l'eau 2024, par classe de population »"),
    "fuites": ("fuites_classe_2024.csv", False,
               "Stratégie d'économie d'eau potable, « Indice de fuites (IFI) 2024, par classe de population »"),
    "consommation": ("consommation_classe_2024.csv", False,
                     "Stratégie d'économie d'eau potable, « Consommation résidentielle 2024, par classe de population »"),
}

A_COMPLETER = "À compléter"


# ---------------------------------------------------------------------------
# Lecture des fichiers de référence
# ---------------------------------------------------------------------------

def lire_fichiers():
    """Charge les fichiers présents et dit clairement lesquels manquent.

    Retourne le contenu de chaque fichier trouvé, et sa date. Attention, c'est
    la date de dernière modification sur le disque, donc en pratique le jour
    où le fichier a été téléchargé, pas la date de publication par le
    ministère. S'il manque un fichier obligatoire, retourne (None, None).
    """
    contenus, dates, absents = {}, {}, []

    for cle, (nom, obligatoire, description) in FICHIERS.items():
        chemin = DOSSIER_SOURCES / nom
        if not chemin.exists():
            absents.append((nom, obligatoire, description))
            continue
        contenus[cle] = chemin.read_bytes()
        dates[cle] = datetime.fromtimestamp(chemin.stat().st_mtime).date().isoformat()
        print(f"  {nom:36s} {chemin.stat().st_size:>9,} octets   fichier du {dates[cle]}")

    for nom, obligatoire, description in absents:
        marque = "MANQUANT" if obligatoire else "absent, facultatif"
        print(f"  {nom:36s} {marque}")
        print(f"      à prendre dans : {description}")

    if any(obligatoire for _, obligatoire, _ in absents):
        return None, None
    return contenus, dates


def lire_csv(contenu):
    """Lit un CSV reçu en octets. L'encodage « utf-8-sig » retire le BOM s'il y en a un."""
    return list(csv.DictReader(contenu.decode("utf-8-sig").splitlines()))


# ---------------------------------------------------------------------------
# Rapprochement des noms
# ---------------------------------------------------------------------------

# Désignations retirées au début des noms. Elles sont écrites sans accents,
# parce qu'on les compare à des noms déjà normalisés.
DESIGNATIONS = (r"(ville|municipalite regionale de comte|municipalite|mrc|paroisse"
                r"|cantons unis|canton|village|cite|corporation municipale"
                r"|communaute metropolitaine)")


def normaliser(texte):
    """Minuscules, sans accents ni ponctuation : « Sainte-Anne » devient « sainte anne »."""
    texte = unicodedata.normalize("NFD", (texte or "").lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", texte)).strip()


def cle_organisme(nom):
    """Réduit un nom à sa partie distinctive, pour comparer le SEAO au répertoire.

    Le SEAO n'a aucun code officiel de municipalité : on n'a que le nom. On
    retire donc la désignation (« Ville de », « Municipalité de »...) et les
    articles, pour que « Ville de Sept-Îles » et « Sept-Îles » donnent la même
    clé. On retire aussi le service que certains acheteurs ajoutent à leur
    nom, comme dans « Ville de Joliette - Approvisionnement ».
    """
    cle = normaliser(nom)
    # Sans effet pour l'instant : normaliser() a déjà remplacé « / » et « ( »
    # par des espaces, donc ce motif ne trouve jamais rien.
    cle = re.sub(r"\s*[/(].*$", "", cle)
    cle = re.sub(r"\b(approvisionnement|service des acquisitions)\b", "", cle)
    # Plusieurs passages, pour les noms qui empilent désignations et articles,
    # comme « Municipalité de la Paroisse de Saint-... ».
    for _ in range(3):
        cle = re.sub(rf"^{DESIGNATIONS}\b\s*", "", cle)
        cle = re.sub(r"^(de la|du|des|de|d|la|le|les)\b\s*", "", cle)
    return cle.strip()


def type_attendu(nom):
    """Déduit du début du nom SEAO si l'on cherche une municipalité ou une MRC.

    Une fois la désignation retirée, « MRC de Montmagny » et « Ville de
    Montmagny » donnent la même clé. Ce repère permet de choisir la bonne
    correspondance plutôt que de déclarer le cas ambigu. Retourne None si le
    nom ne commence par aucune désignation connue.
    """
    debut = normaliser(nom)
    if re.match(r"^(mrc|municipalite regionale de comte|communaute metropolitaine)\b", debut):
        return "MRC ou communauté"
    if re.match(r"^(ville|municipalite|paroisse|canton|cantons unis|village|cite"
                r"|corporation municipale)\b", debut):
        return "municipalité"
    return None


def construire_index(municipalites, mrc, perimunicipaux):
    """Associe chaque clé de nom à la liste des organismes qui la portent.

    Une clé partagée reste volontairement ambiguë : il existe par exemple deux
    Saint-Donat au Québec. main() essaiera de départager avec la désignation,
    et signalera le cas s'il n'y arrive pas. Je préfère un programme qui dit
    « je ne sais pas » à un programme qui devine.
    """
    index = {}

    for ligne in municipalites:
        index.setdefault(cle_organisme(ligne["munnom"]), []).append(("municipalité", ligne))

    for ligne in mrc:
        index.setdefault(cle_organisme(ligne["mrcnom"]), []).append(("MRC ou communauté", ligne))

    # Pour les organismes périmunicipaux, on ne garde que le nom : le fichier
    # XML ne donne ni population ni superficie.
    for organisme in perimunicipaux:
        nom = organisme.findtext("NOM_L1", "").strip()
        if nom:
            index.setdefault(cle_organisme(nom), []).append(("organisme périmunicipal", {"nom": nom}))

    return index


# ---------------------------------------------------------------------------
# Construction des valeurs de contexte
# ---------------------------------------------------------------------------

def valeurs_municipalite(ligne, eau, source):
    """Prépare les valeurs de contexte d'une municipalité du répertoire.

    Deux précisions pour bien lire le résultat :
      - la superficie retenue est la superficie totale (msuperf), plans d'eau
        compris. Le répertoire donne aussi la superficie terrestre (msupft),
        qui n'est pas utilisée ici;
      - classe_taille vient de la Stratégie d'économie d'eau potable : c'est la
        classe de la population desservie par le réseau, pas celle de la
        municipalité. Mont-Tremblant compte 12 026 habitants, mais elle est
        classée « 5 000 à 9 999 personnes » parce que son réseau en dessert
        8 151. Quand la Stratégie n'a pas de classe, elle inscrit « Aucune
        donnée ».
    """
    code = (ligne.get("mcode") or "").strip('"').strip()
    donnees_eau = eau.get(code, {})

    # Les données sur l'eau tiennent dans une seule colonne de texte, facile à
    # lire. Une valeur vide ou « NULL » est simplement omise.
    morceaux = []
    for etiquette, champ, unite in (("population desservie", "pop_desservie", ""),
                                    ("indice de fuites", "indice_fuites", ""),
                                    ("validité des audits", "validite", " %"),
                                    ("consommation résidentielle", "consommation", " L/personne/jour")):
        valeur = donnees_eau.get(champ)
        if valeur not in (None, "", "NULL"):
            morceaux.append(f"{etiquette} {valeur}{unite}")

    return {
        "code_geographique": code,
        "population": ligne.get("mpopul", ""),
        "classe_taille": donnees_eau.get("classe", ""),
        "superficie_km2": ligne.get("msuperf", ""),
        "region_administrative": ligne.get("regadm", ""),
        "mrc": ligne.get("mrc", ""),
        "particularites_infrastructures": "; ".join(morceaux),
        "source_contexte": source,
    }


def valeurs_mrc(ligne, source):
    """Prépare les valeurs de contexte d'une MRC ou d'une communauté métropolitaine.

    Le fichier des MRC a ses propres noms de colonnes (mrcpopul, mrcregion,
    msupf), différents de ceux du fichier des municipalités. Il ne contient
    rien sur l'eau.
    """
    return {
        "code_geographique": (ligne.get("mrccod") or "").strip(),
        "population": ligne.get("mrcpopul", ""),
        "superficie_km2": ligne.get("msupf", ""),
        "region_administrative": ligne.get("mrcregion", ""),
        "source_contexte": source,
    }


def construire_donnees_eau(fuites, validite, consommation):
    """Regroupe les trois fichiers de la Stratégie par code géographique.

    Le fichier des fuites nomme sa colonne de code num_c, les deux autres
    mun_c : c'est la même information. L'indice de fuites est coupé à cinq
    caractères (0.56544245 devient 0.565) : c'est une troncature, pas un
    arrondi.
    """
    eau = {}
    for ligne in validite:
        eau.setdefault(ligne["mun_c"], {}).update(
            classe=ligne.get("cl_pop_desservie", ""),
            pop_desservie=ligne.get("pop_desservie", ""),
            validite=ligne.get("pourc_indice_validite", ""),
        )
    for ligne in fuites:
        eau.setdefault(ligne["num_c"], {}).update(indice_fuites=ligne.get("indice_fuites_ifi", "")[:5])
    for ligne in consommation:
        eau.setdefault(ligne["mun_c"], {}).update(consommation=ligne.get("consom_resid", ""))
    return eau


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main():
    """Remplit les cases « À compléter » du contexte, puis liste les cas à traiter à la main."""
    if not CONTEXTE_CSV.exists():
        print(f"Erreur : {CONTEXTE_CSV} introuvable. Lancer d'abord analyser_seao.py.")
        return

    print(f"Lecture des fichiers de référence dans {DOSSIER_SOURCES} :")
    contenus, dates = lire_fichiers()
    if contenus is None:
        print("\nIl manque un fichier obligatoire. Rien n'a été modifié.")
        return

    municipalites = lire_csv(contenus["municipalites"])
    mrc = lire_csv(contenus["mrc"]) if "mrc" in contenus else []
    perimunicipaux = list(ET.fromstring(contenus["perimunicipaux"])) if "perimunicipaux" in contenus else []
    eau = construire_donnees_eau(
        lire_csv(contenus["fuites"]) if "fuites" in contenus else [],
        lire_csv(contenus["validite"]) if "validite" in contenus else [],
        lire_csv(contenus["consommation"]) if "consommation" in contenus else [],
    )
    index = construire_index(municipalites, mrc, perimunicipaux)

    # Mention de provenance écrite dans chaque case remplie : quels fichiers,
    # de quelle date, et quel jour le contexte a été complété.
    source = (f"Répertoire des municipalités du Québec (MAMH), fichier du {dates['municipalites']}"
              + (f"; Stratégie québécoise d'économie d'eau potable 2024 (MAMH), fichier du {dates['validite']}"
                 if "validite" in dates else "")
              + f"; contexte rempli le {date.today().isoformat()}")

    with CONTEXTE_CSV.open(encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        colonnes = lecteur.fieldnames
        lignes = list(lecteur)

    # remplis compte des organismes; deja_saisis compte des cases.
    remplis, deja_saisis, ambigus, absents = 0, 0, [], []

    for ligne in lignes:
        correspondances = index.get(cle_organisme(ligne["organisme"]), [])

        if not correspondances:
            absents.append((ligne["organisme"], "aucun organisme du répertoire ne porte ce nom"))
            continue

        # « MRC de Montmagny » et « Ville de Montmagny » ont la même clé : on
        # départage avec la désignation écrite dans le nom de l'acheteur.
        if len(correspondances) > 1:
            attendu = type_attendu(ligne["organisme"])
            filtrees = [c for c in correspondances if c[0] == attendu]
            if len(filtrees) == 1:
                correspondances = filtrees

        if len(correspondances) > 1:
            details = "; ".join(t for t, _ in correspondances)
            ambigus.append((ligne["organisme"], f"{len(correspondances)} correspondances : {details}"))
            continue

        type_organisme, trouve = correspondances[0]
        if type_organisme == "municipalité":
            valeurs = valeurs_municipalite(trouve, eau, source)
        elif type_organisme == "MRC ou communauté":
            valeurs = valeurs_mrc(trouve, source)
        else:
            # Organisme reconnu, mais le répertoire n'a rien à reporter pour lui.
            absents.append((ligne["organisme"],
                            "organisme périmunicipal : ni population ni superficie dans le répertoire"))
            continue

        modifie = False
        for colonne, valeur in valeurs.items():
            if not valeur:
                continue
            actuelle = (ligne.get(colonne) or "").strip()
            if actuelle and actuelle != A_COMPLETER:
                deja_saisis += 1          # une valeur saisie à la main n'est jamais remplacée
                continue
            ligne[colonne] = valeur
            modifie = True
        if modifie:
            remplis += 1

    # Sauvegarde avant d'écrire, pour pouvoir revenir en arrière. Attention : il
    # n'y en a qu'une, et elle est remplacée à chaque exécution.
    DOSSIER_SORTIES.mkdir(exist_ok=True)
    shutil.copy2(CONTEXTE_CSV, DOSSIER_SORTIES / (CONTEXTE_CSV.name + ".bak"))
    with CONTEXTE_CSV.open("w", encoding="utf-8-sig", newline="") as fichier:
        ecrivain = csv.DictWriter(fichier, fieldnames=colonnes)
        ecrivain.writeheader()
        ecrivain.writerows(lignes)

    with open(A_VERIFIER_CSV, "w", encoding="utf-8-sig", newline="") as fichier:
        ecrivain = csv.writer(fichier)
        ecrivain.writerow(["organisme", "raison"])
        ecrivain.writerows(sorted(ambigus + absents))

    print(f"\nOrganismes dans le contexte         : {len(lignes)}")
    print(f"Organismes enrichis                 : {remplis}")
    print(f"Valeurs manuelles laissées intactes : {deja_saisis}")
    print(f"Noms ambigus                        : {len(ambigus)}")
    print(f"Sans correspondance                 : {len(absents)}")
    print(f"\n{CONTEXTE_CSV} mis à jour (sauvegarde dans {DOSSIER_SORTIES / (CONTEXTE_CSV.name + '.bak')})")
    print(f"{A_VERIFIER_CSV} liste les cas à traiter à la main.")
    print("La proximité d'un cours d'eau et le type de milieu restent à documenter :")
    print("aucun de ces fichiers ne fournit ces informations.")


if __name__ == "__main__":
    main()
