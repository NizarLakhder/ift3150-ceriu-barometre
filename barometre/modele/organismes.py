"""Les deux tables des organismes : les organismes du contexte et leurs identifiants d'acheteur.

Le chargement (barometre/chargement/organismes.py) lit le contexte et garde ses contrôles ;
type_organisme décide du type d'un organisme d'après le répertoire ; ces classes décrivent les lignes
et les écrivent.
"""

from dataclasses import dataclass

from barometre.modele.conversions import texte
from barometre.modele.table import Table, genere


@dataclass(slots=True, kw_only=True)
class Organisme(Table):
    """Un organisme du contexte : une ligne de organismes.organisme. Le contexte fait foi : il met la ligne à jour."""

    TABLE = "organismes.organisme"
    CLE = ("nom",)

    organisme_id: int | None = genere()  # numéro attribué par la base, gardé d'un chargement à l'autre
    nom: str
    type: str                       # municipalite, mrc_ou_communaute ou non_municipal
    code_geographique: str | None   # rempli pour une municipalité seulement
    mrc_code: str | None            # rempli pour une MRC ou une communauté seulement
    type_milieu: str | None
    source_contexte: str | None
    notes: str | None


@dataclass(slots=True, kw_only=True)
class Acheteur(Table):
    """Un identifiant d'acheteur du SEAO et son organisme : une ligne de organismes.acheteur.

    Chaque source ne met à jour que sa colonne : le contexte, organisme_id ; un export, nom_seao.
    Une écriture doit donc toujours dire laquelle (mises_a_jour).
    """

    TABLE = "organismes.acheteur"
    CLE = ("acheteur_id",)
    MISES_A_JOUR_OBLIGATOIRES = True

    acheteur_id: str        # « OP-… »
    organisme_id: int
    nom_seao: str | None    # le nom publié dans le SEAO


def type_organisme(code, municipalites, mrc):
    """Le type d'un organisme d'après son code, cherché dans le répertoire.

    Un code absent du répertoire lève ValueError : il n'est pas deviné d'après sa forme.
    """
    code = texte(code)
    if code is None:
        return "non_municipal"
    if code in municipalites:
        return "municipalite"
    if code in mrc:
        return "mrc_ou_communaute"
    raise ValueError(f"le code {code} n'est ni une municipalité ni une MRC du répertoire.")
