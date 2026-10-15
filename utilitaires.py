"""
Les petites fonctions utilitaires du projet : nettoyer un texte, lire une
date, convertir un montant, écrire un CSV.

Projet IFT3150 de Nizar Lakhder, Université de Montréal, automne 2026.

Ces fonctions ne savent rien du baromètre lui-même. Les règles du projet,
comme ce qui compte pour une fiche municipale ou un dossier PGA-Eau, restent
dans analyser_seao.py. Les ranger à part allège ce programme et permet de
s'en servir ailleurs, comme le fait charger_base.py.
"""

import csv
import re


# ---------------------------------------------------------------------------
# Texte
# ---------------------------------------------------------------------------

def clean_text(value):
    """Réduit les suites d'espaces à un seul et retire ceux des bords.

    Une valeur absente devient une chaîne vide, pour éviter d'écrire « None »
    dans les CSV.
    """
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def clean_org_name(name):
    """Nettoie un nom d'organisme : espaces en trop et ponctuation finale.

    « Ville de Lévis. » devient « Ville de Lévis ». Deux écritures qui ne
    diffèrent que par ces détails se retrouvent ainsi regroupées. Les autres
    variantes restent séparées : ce nettoyage ne remplace pas un vrai
    identifiant municipal.
    """
    return clean_text(name).rstrip(" .,-")


# ---------------------------------------------------------------------------
# Montants
# ---------------------------------------------------------------------------

def safe_float(value):
    """Convertit en nombre, ou retourne None si ce n'est pas possible.

    Un montant absent n'est pas un montant nul : on ne le remplace jamais par
    zéro, sinon il ferait baisser les médianes sans raison.
    """
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
    """Retourne la date AAAA-MM-JJ si sa forme est correcte, sinon une chaîne vide.

    Le SEAO utilise « 0001-01-01 » comme date fictive : on l'écarte aussi.
    On vérifie seulement la forme du texte, pas que le jour existe dans le
    calendrier.
    """
    d = day(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and not d.startswith("0001"):
        return d
    return ""


def date_from_release_id(release):
    """Lit la date contenue dans l'identifiant de la fiche.

    L'identifiant est un horodatage à 14 chiffres, comme 20260907120000; ses
    huit premiers chiffres donnent une date. Dans l'export de la semaine, ces
    dates tombent toutes entre le 7 et le 13 septembre; dans celui d'août,
    entre le 1er août et le 1er septembre. C'est donc très probablement la
    date de publication de la fiche, mais aucune définition officielle ne le
    confirme : la colonne s'appelle « date_deduite_id_release » pour le rappeler.

    À ne pas confondre avec release.date, qui est presque toujours la date
    d'ouverture de l'avis (1 518 fiches municipales sur 1 561 dans l'export de
    la semaine). Et l'identifiant seul n'est pas unique : deux dossiers
    différents peuvent le partager.
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
    """Écrit un CSV, en remplaçant celui qui existe.

    L'encodage UTF-8 avec BOM permet à Excel d'afficher les accents
    correctement. Si la liste est vide, rien n'est écrit, et un ancien fichier
    du même nom reste en place.
    """
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
