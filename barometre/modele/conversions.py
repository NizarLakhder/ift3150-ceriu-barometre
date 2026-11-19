"""Les conversions d'une valeur publiée en valeur de base : texte nettoyé, nombre exact, entier, codes.

Sans base de données. charger_base.py les réexporte ; test_charger_base.py les vérifie.
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from barometre.contexte.fichier import A_COMPLETER
from barometre.utilitaires import valid_date


def texte(valeur):
    """Un texte nettoyé, ou None : « À compléter », « NULL » et le vide deviennent None."""
    valeur = (valeur or "").strip() if isinstance(valeur, str) else valeur
    if valeur in (None, "", "NULL", A_COMPLETER):
        return None
    return valeur


def nombre(valeur):
    """Un nombre exact (Decimal), ou None : 77061.99 reste exactement 77061.99."""
    valeur = texte(valeur if isinstance(valeur, str) else (None if valeur is None else str(valeur)))
    if valeur is None:
        return None
    try:
        return Decimal(valeur)
    except InvalidOperation:
        return None


def entier(valeur):
    """Un entier, ou None."""
    n = nombre(valeur)
    return int(n) if n is not None else None


def region_de(libelle):
    """« Estrie (05) » devient ("05", "Estrie"). Retourne (None, None) si le format ne correspond pas."""
    m = re.fullmatch(r"\s*(.+?)\s*\((\d{2})\)\s*", libelle or "")
    return (m.group(2), m.group(1)) if m else (None, None)


def code_mrc_de(libelle, prefixe="AR"):
    """« MRC Bellechasse (190) » devient « AR190 ». Le fichier des MRC écrit ses codes ainsi.

    Pour une communauté métropolitaine, « Communauté métropolitaine de
    Montréal (663) » devient « CM663 » avec prefixe="CM".
    """
    m = re.search(r"\((\d{3})\)\s*$", libelle or "")
    return prefixe + m.group(1) if m else None


def instant(valeur):
    """Une date ISO du SEAO en date et heure, ou None si elle est absente ou fictive (« 0001-01-01 »)."""
    valeur = texte(valeur)
    if valeur is None or not valid_date(valeur):
        return None
    try:
        return datetime.fromisoformat(valeur)
    except ValueError:
        return None


# Libellés d'analyser_seao.py et de demarches.csv, et leur code dans les types
# énumérés de schema.sql. Un libellé absent arrête le chargement.
CODES = {
    "nature_transaction": {"achat": "achat", "subvention ou contribution": "subvention_ou_contribution",
                           "vente d'immeuble": "vente_immeuble", "partenariat": "partenariat"},
    "gestion_actifs_eau": {"PGA-Eau": "pga_eau", "outil": "outil", "étape": "etape",
                           "plan d'intervention": "plan_intervention", "gestion d'actifs": "gestion_actifs"},
    "plan": {"PGA-Eau": "pga_eau"},
    "classement": {"élaboration": "elaboration", "étape": "etape", "plan d'intervention": "plan_intervention",
                   "plan de gestion des actifs": "plan_gestion_actifs", "démarche voisine": "demarche_voisine",
                   "outil": "outil"},
    "etat": {"mandat attribué": "mandat_attribue", "appel d'offres en cours": "appel_offres_en_cours",
             "appel d'offres annulé": "appel_offres_annule", "plan adopté": "plan_adopte", "plan publié": "plan_publie"},
}


def code_de(colonne, libelle):
    """Le code que la base donne à un libellé : « mandat attribué » devient « mandat_attribue »."""
    try:
        return CODES[colonne][libelle]
    except KeyError:
        raise ValueError(f"« {libelle} » n'est pas une valeur permise pour {colonne} : "
                         + ", ".join(f"« {l} »" for l in CODES[colonne]) + ".") from None
