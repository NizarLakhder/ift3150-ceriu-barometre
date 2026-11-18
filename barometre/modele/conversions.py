"""Les conversions d'une valeur publiée en valeur de base : texte nettoyé, nombre exact, entier, codes.

Sans base de données. charger_base.py les réexporte ; test_charger_base.py les vérifie.
"""

import re
from decimal import Decimal, InvalidOperation

from barometre.contexte.fichier import A_COMPLETER


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
