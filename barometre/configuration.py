"""Lecture et validation de config/regles_reperage.toml, le fichier des règles de repérage.

barometre.regles lit ce fichier au premier usage d'une règle, jamais à l'import : un programme qui
n'utilise aucune règle, comme exporter_carte.py, ne dépend pas de lui. Une erreur lève
ConfigurationInvalide, avec un message qui nomme le fichier, la clé et ce qu'il faut corriger ; ce sont
les programmes (analyser_seao.py, charger_base.py) qui l'affichent et s'arrêtent.
"""

import re
import sys
from pathlib import Path

FICHIER_REGLES = Path(__file__).resolve().parent.parent / "config" / "regles_reperage.toml"
PYTHON_MINIMUM = (3, 11)       # tomllib arrive avec Python 3.11
VERSION_ATTENDUE = 1

# Les quatre champs qui documentent chaque groupe de règles.
DOCUMENTATION = ("champs_examines", "preparation", "source", "limites")

# Les clés de chaque groupe, et leur genre :
#   motif  : une expression régulière, non vide, qui se compile et ne correspond pas au texte vide ;
#   motifs : une liste non vide de tels motifs ;
#   mots   : une liste non vide de mots cherchés tels quels, en minuscules et avec des apostrophes droites.
GROUPES = {
    "lie_eau": {"mot_eau": "motif", "mots_cles": "mots"},
    "pga_eau": {"acronyme": "motif", "mots_requis": "mots", "mot_eau": "motif"},
    "gestion_actifs_eau": {
        "gestion_actifs": "motif", "autres_actifs": "motif", "outil": "motif", "etape_actions": "motif",
        "etape_expression": "motif", "etape_cadres": "motifs", "plan_intervention": "motif",
        "reseaux_eau": "motif", "routes": "motif", "infrastructures": "motif",
    },
}

APOSTROPHES_COURBES = ("’", "ʼ")


class ConfigurationInvalide(ValueError):
    """Le fichier des règles manque ou n'est pas valide. Le message dit quoi corriger."""


def motif_etape(gestion):
    """Le motif du test « étape » : l'expression, puis l'un des cadres ou la gestion d'actifs."""
    return gestion["etape_expression"] + ".*(" + "|".join([*gestion["etape_cadres"], gestion["gestion_actifs"]]) + ")"


def charger_regles(chemin=None):
    """Lit et valide le fichier des règles (par défaut FICHIER_REGLES), et retourne son contenu."""
    chemin = Path(chemin) if chemin is not None else FICHIER_REGLES
    if sys.version_info < PYTHON_MINIMUM:
        raise ConfigurationInvalide(
            f"Python {PYTHON_MINIMUM[0]}.{PYTHON_MINIMUM[1]} ou plus récent est requis pour lire {chemin} "
            f"(version utilisée : {sys.version_info[0]}.{sys.version_info[1]}).")
    import tomllib  # après le contrôle de version : ce module n'existe pas avant Python 3.11

    if not chemin.is_file():
        raise ConfigurationInvalide(f"{chemin} : fichier des règles introuvable. Il fait partie du projet : "
                                    "le restaurer depuis le dépôt Git.")
    try:
        with chemin.open("rb") as fichier:
            donnees = tomllib.load(fichier)
    except tomllib.TOMLDecodeError as erreur:
        raise ConfigurationInvalide(f"{chemin} : syntaxe TOML invalide ({erreur}).") from erreur
    except OSError as erreur:
        raise ConfigurationInvalide(f"{chemin} : lecture impossible ({erreur}).") from erreur
    valider(donnees, chemin)
    return donnees


def valider(donnees, chemin):
    """Lève ConfigurationInvalide au premier défaut trouvé dans le contenu du fichier."""
    def refuser(message):
        raise ConfigurationInvalide(f"{chemin} : {message}")

    def cles_exactes(trouvees, attendues, prefixe=""):
        manquantes = sorted(set(attendues) - set(trouvees))
        inconnues = sorted(set(trouvees) - set(attendues))
        if manquantes:
            refuser(f"clé manquante : {', '.join(prefixe + c for c in manquantes)}.")
        if inconnues:
            refuser(f"clé inconnue : {', '.join(prefixe + c for c in inconnues)} (faute de frappe ?).")

    def motif(nom, valeur):
        if not isinstance(valeur, str):
            refuser(f"{nom} doit être une chaîne de caractères (un motif).")
        if not valeur.strip():
            refuser(f"{nom} : motif vide. Un motif vide correspondrait à tous les textes.")
        try:
            expression = re.compile(valeur)
        except re.error as erreur:
            refuser(f"{nom} : motif invalide ({erreur}).")
        if expression.search(""):
            refuser(f"{nom} : ce motif peut correspondre au texte vide, donc à tous les textes.")

    def liste(nom, valeur):
        if not isinstance(valeur, list) or not valeur:
            refuser(f"{nom} doit être une liste non vide.")
        return valeur

    def mot(nom, valeur):
        if not isinstance(valeur, str) or not valeur.strip():
            refuser(f"{nom} : chaque mot doit être une chaîne non vide.")
        if valeur != valeur.lower():
            refuser(f"{nom} : « {valeur} » contient une majuscule, alors que le texte comparé est en "
                    f"minuscules : écrire « {valeur.lower()} ».")
        if any(a in valeur for a in APOSTROPHES_COURBES):
            corrige = valeur
            for a in APOSTROPHES_COURBES:
                corrige = corrige.replace(a, "'")
            refuser(f"{nom} : « {valeur} » contient une apostrophe courbe, alors que le texte comparé a des "
                    f"apostrophes droites : écrire « {corrige} ».")

    cles_exactes(donnees, ["version", *GROUPES])
    version = donnees["version"]
    if isinstance(version, bool) or version != VERSION_ATTENDUE:
        refuser(f"version {version!r} non prise en charge : attendu « version = {VERSION_ATTENDUE} ».")
    for groupe, cles in GROUPES.items():
        section = donnees[groupe]
        if not isinstance(section, dict):
            refuser(f"[{groupe}] doit être une section.")
        cles_exactes(section, [*DOCUMENTATION, *cles], f"{groupe}.")
        for cle in DOCUMENTATION:
            nom, valeur = f"{groupe}.{cle}", section[cle]
            if cle == "champs_examines":
                for element in liste(nom, valeur):
                    if not isinstance(element, str) or not element.strip():
                        refuser(f"{nom} : chaque champ doit être une chaîne non vide.")
            elif not isinstance(valeur, str) or not valeur.strip():
                refuser(f"{nom} doit être un texte non vide.")
        for cle, genre in cles.items():
            nom, valeur = f"{groupe}.{cle}", section[cle]
            if genre == "motif":
                motif(nom, valeur)
            elif genre == "motifs":
                for i, element in enumerate(liste(nom, valeur)):
                    motif(f"{nom}[{i}]", element)
            else:
                for element in liste(nom, valeur):
                    mot(nom, element)
    motif("gestion_actifs_eau (motif recomposé du test « étape »)", motif_etape(donnees["gestion_actifs_eau"]))
