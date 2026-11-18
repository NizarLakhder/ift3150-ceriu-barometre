"""Les dossiers et les fichiers que lit ou écrit l'analyse, relatifs au dossier courant (la racine du projet)."""

from pathlib import Path


DOSSIER_SEAO = Path("donnees_seao")
DOSSIER_SORTIES = Path("sorties")


# L'export lu sans argument, et le fichier de contexte, tenu à la main.
JSON_FILE = DOSSIER_SEAO / "hebdo_20260907_20260913.json"
CONTEXT_SOURCE_CSV = Path("contexte_municipalites.csv")
# Ancienne vue, lue une seule fois pour créer le fichier de contexte (voir load_context_source).
ANCIENNE_VUE_CONTEXTE = DOSSIER_SORTIES / "municipalites_a_enrichir.csv"


def trouver_fichier_json(nom):
    """Accepte un chemin, ou le seul nom d'un export de donnees_seao/.

    Si rien n'est trouvé, le nom revient tel quel et main() affiche l'erreur.
    """
    chemin = Path(nom)
    if chemin.exists():
        return chemin
    dans_le_dossier = DOSSIER_SEAO / chemin.name
    return dans_le_dossier if dans_le_dossier.exists() else chemin


def noms_de_sortie(fichier_json):
    """Les chemins des quatre CSV, dans un dossier par export, comme sorties/mensuel_20260801_20260831/."""
    dossier = DOSSIER_SORTIES / Path(fichier_json).stem
    return (dossier / "details.csv", dossier / "comparaison.csv",
            dossier / "a_enrichir.csv", dossier / "qualite.csv")
