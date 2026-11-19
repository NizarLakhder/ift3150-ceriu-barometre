"""Le classement de chaque fiche par les règles de repérage, et les démarches classées à la main (demarches.csv)."""

import csv
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

from barometre.analyse.fiche import analyse_release
from barometre.chargement.territoire import noter_fichier_reference
from barometre.chemins import DEMARCHES_CSV
from barometre.modele.analyses import Demarche, FicheClassee
from barometre.modele.conversions import code_de, nombre, texte


def version_des_regles():
    """L'empreinte du code et du fichier qui classent les fiches.

    Elle couvre deux fichiers nommés explicitement, analyser_seao.py et config/regles_reperage.toml,
    et tous les modules de barometre/, dont utilitaires.py. S'il manque l'un des deux, elle échoue
    plutôt que de calculer une empreinte sans lui. Elle change dès qu'une règle change. Les
    fichiers sont pris dans l'ordre de leur chemin, chacun précédé de ce chemin, et leurs fins de ligne
    sont ramenées à LF : la même version donne la même empreinte sous Windows comme ailleurs.
    """
    racine = Path(__file__).resolve().parents[2]  # la racine du projet, au-dessus de barometre/chargement/
    explicites = [racine / "analyser_seao.py", racine / "config" / "regles_reperage.toml"]
    manquants = [f.relative_to(racine).as_posix() for f in explicites if not f.is_file()]
    if manquants:
        raise FileNotFoundError(f"Version des règles impossible à calculer : {', '.join(manquants)} introuvable.")
    fichiers = [*explicites, *(racine / "barometre").rglob("*.py")]
    empreinte = hashlib.sha256()
    for chemin in sorted(fichiers, key=lambda f: f.relative_to(racine).as_posix()):
        empreinte.update(chemin.relative_to(racine).as_posix().encode("utf-8") + b"\0")
        empreinte.update(chemin.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return "regles " + empreinte.hexdigest()[:12]


def classer_fiches(connexion):
    """Classe toutes les fiches en base avec analyse_release, la fonction même qui produit les CSV."""
    version = version_des_regles()
    lignes = []
    for fiche_id, brut in connexion.execute("SELECT fiche_id, brut FROM seao.fiche"):
        ligne = analyse_release(brut)
        famille = texte(ligne["gestion_actifs_eau"])
        lignes.append(FicheClassee(fiche_id=fiche_id,
                                   nature_transaction=code_de("nature_transaction", ligne["nature_transaction"]),
                                   lie_eau=ligne["lie_eau"] == "oui", pga_eau=ligne["pga_eau"] == "oui",
                                   gestion_actifs_eau=code_de("gestion_actifs_eau", famille) if famille else None,
                                   version_regles=version, calcule_le=datetime.now(timezone.utc)))
    FicheClassee.inserer(connexion, lignes)
    return len(lignes)


def ligne_de_demarche(ligne, organismes, dossiers, fournisseurs):
    """Convertit une ligne de demarches.csv en ligne de analyses.demarche.

    organismes relie les noms du contexte à leur numéro, dossiers les ocid au
    leur, et fournisseurs chaque dossier à ses entreprises retenues. Le
    fournisseur vient du dossier, pas du nom écrit dans le fichier. Lève
    ValueError pour un organisme ou un dossier inconnu, ou un dossier qui n'a pas
    exactement le fournisseur attendu.
    """
    if ligne["organisme"] not in organismes:
        raise ValueError(f"demarches.csv : « {ligne['organisme']} » n'est pas dans contexte_municipalites.csv.")
    ocid, nomme = texte(ligne["ocid"]), texte(ligne["fournisseur"]) is not None
    if ocid is not None and ocid not in dossiers:
        raise ValueError(f"demarches.csv : le dossier {ocid} n'est pas dans la base.")
    dossier_id = dossiers.get(ocid)
    retenus = sorted(fournisseurs.get(dossier_id, ()))
    if len(retenus) != (1 if nomme else 0):
        raise ValueError(f"demarches.csv : la ligne de « {ligne['organisme']} » ({ocid or 'sans dossier'}) "
                         f"{'nomme un fournisseur' if nomme else 'ne nomme aucun fournisseur'}, "
                         f"mais le dossier en compte {len(retenus)}.")
    attribution, publication = texte(ligne["date_attribution"]), texte(ligne["date_publication"])
    return {
        "organisme_id": organismes[ligne["organisme"]], "plan": code_de("plan", ligne["plan"]),
        "classement": code_de("classement", ligne["classement"]), "etat": code_de("etat", ligne["etat"]),
        "date_attribution": date.fromisoformat(attribution) if attribution else None,
        "date_publication": date.fromisoformat(publication) if publication else None,
        "montant": nombre(ligne["montant"]), "dossier_id": dossier_id,
        "fournisseur_id": retenus[0] if retenus else None, "lien": texte(ligne["lien"]),
        "source": ligne["source"], "notes": texte(ligne["notes"]),
    }


def charger_demarches(connexion):
    """Recharge demarches.csv tel quel : le fichier, tenu à la main, fait foi."""
    with DEMARCHES_CSV.open(encoding="utf-8-sig", newline="") as fichier:
        demarches = list(csv.DictReader(fichier))
    noter_fichier_reference(connexion, DEMARCHES_CSV, "Démarches repérées, classées à la main avec leur source")
    organismes = dict(connexion.execute("SELECT nom, organisme_id FROM organismes.organisme").fetchall())
    dossiers = dict(connexion.execute("SELECT ocid, dossier_id FROM seao.dossier").fetchall())
    fournisseurs = {}
    for dossier_id, fournisseur_id in connexion.execute(
            "SELECT DISTINCT f.dossier_id, i.fournisseur_id FROM seao.attribution a "
            "JOIN seao.fiche f ON f.fiche_id = a.fiche_id "
            "JOIN seao.identifiant_fournisseur i ON i.identifiant = a.identifiant_fournisseur"):
        fournisseurs.setdefault(dossier_id, set()).add(fournisseur_id)
    connexion.execute("DELETE FROM analyses.demarche")
    Demarche.inserer(connexion, [Demarche(**ligne_de_demarche(d, organismes, dossiers, fournisseurs)) for d in demarches])
    return len(demarches)


def dossiers_a_classer(connexion):
    """Les dossiers repérés (pga_eau ou gestion_actifs_eau) sans ligne dans demarches.csv."""
    return [ocid for (ocid,) in connexion.execute(
        "SELECT DISTINCT d.ocid FROM analyses.fiche_classee c JOIN seao.fiche f ON f.fiche_id = c.fiche_id "
        "JOIN seao.dossier d ON d.dossier_id = f.dossier_id WHERE (c.pga_eau OR c.gestion_actifs_eau IS NOT NULL) "
        "AND NOT EXISTS (SELECT 1 FROM analyses.demarche m WHERE m.dossier_id = d.dossier_id) ORDER BY d.ocid")]
