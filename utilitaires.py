"""
Petites fonctions partagées : nettoyer un texte, lire une date, convertir un
montant, écrire un CSV. Les règles du baromètre restent dans analyser_seao.py.
"""

import csv
import re


# ---------------------------------------------------------------------------
# Texte
# ---------------------------------------------------------------------------

def clean_text(value):
    """Réduit les espaces à un seul et retire ceux des bords; None devient une chaîne vide."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def clean_org_name(name):
    """Retire les espaces en trop et la ponctuation finale d'un nom d'organisme.

    « Ville de Lévis. » devient « Ville de Lévis ».
    """
    return clean_text(name).rstrip(" .,-")


# ---------------------------------------------------------------------------
# Montants
# ---------------------------------------------------------------------------

def safe_float(value):
    """Convertit en nombre, ou retourne None : un montant absent n'est pas un montant nul."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_money(value):
    """Écrit un montant à la québécoise, par exemple « 77 061,99 $ »."""
    if value is None:
        return "Non disponible"
    return f"{value:,.2f} $".replace(",", " ").replace(".", ",")


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def day(value):
    """Garde seulement la partie AAAA-MM-JJ d'une date ISO."""
    return clean_text(value)[:10]


def valid_date(value):
    """Retourne la date AAAA-MM-JJ, ou une chaîne vide si sa forme est incorrecte.

    La date fictive du SEAO, « 0001-01-01 », est écartée. Seule la forme est
    vérifiée, pas l'existence du jour.
    """
    d = day(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and not d.startswith("0001"):
        return d
    return ""


def date_from_release_id(release):
    """La date lue dans l'identifiant de la fiche : 20260907120000 donne 2026-09-07.

    Sans doute la date de publication (celles de l'export de la semaine tombent
    toutes entre le 7 et le 13 septembre), mais aucune définition officielle ne
    le confirme. release.date, elle, est presque toujours l'ouverture de l'avis.
    """
    rid = clean_text(release.get("id"))
    if re.fullmatch(r"\d{14}", rid):
        return f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}"
    return ""


# ---------------------------------------------------------------------------
# Résumés et fichiers
# ---------------------------------------------------------------------------

def top(counter, n=3):
    """Résume les valeurs les plus fréquentes sous la forme « a (12); b (5); c (2) »."""
    return "; ".join(f"{k} ({v})" for k, v in counter.most_common(n) if k)


def write_csv(path, rows):
    """Écrit un CSV en UTF-8 avec BOM, pour qu'Excel affiche les accents.

    Une liste vide n'écrit rien : l'ancien fichier reste en place.
    """
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
