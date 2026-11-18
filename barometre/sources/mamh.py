"""Les fichiers de référence du MAMH, déposés à la main dans donnees_reference/ (rien n'est téléchargé)."""

import csv
from datetime import datetime
from pathlib import Path

DOSSIER_SOURCES = Path("donnees_reference")

# Pour chaque fichier : son nom, s'il est obligatoire, et où le trouver sur
# Données Québec (affiché quand il manque).
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


def lire_fichiers():
    """Lit les fichiers de référence présents et affiche ceux qui manquent.

    Retourne (contenus, dates), la date étant celle du fichier sur le disque, donc
    de son téléchargement; (None, None) s'il manque un fichier obligatoire.
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
