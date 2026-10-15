"""
Charge les exports du SEAO, le répertoire des municipalités et le contexte dans PostgreSQL.

Projet IFT3150 de Nizar Lakhder, Université de Montréal, automne 2026.

Les fichiers CSV de analyser_seao.py décrivent un export à la fois. La base
permet de les cumuler : une fiche déjà chargée par un autre export n'est
jamais ajoutée deux fois, et la vue analyses.contrat_courant donne la dernière
version de chaque contrat. Le schéma est décrit dans schema.sql.

Ce que le programme charge, dans l'ordre :
  1. le territoire : régions, MRC, municipalités, regroupements et données
     sur l'eau, à partir de donnees_reference/ et de regroupements.csv;
  2. les organismes et leurs identifiants d'acheteur, à partir de
     contexte_municipalites.csv;
  3. chaque export de donnees_seao/ qui n'a pas encore été chargé : seulement
     les fiches municipales, comme analyser_seao.py;
  4. le classement de chaque fiche (nature, lié à l'eau, PGA-Eau), calculé
     avec les règles mêmes d'analyser_seao.py.
Il termine par des vérifications : la base doit redonner les chiffres des
CSV produits par analyser_seao.py.

Ce que le programme s'interdit :
  - charger deux fois un export : son empreinte est notée, et un fichier
    modifié qui porte le nom d'un export déjà chargé est refusé;
  - charger un export à moitié : chaque export est chargé d'un seul bloc, et
    la moindre incohérence annule tout le bloc;
  - modifier un fichier source : il ne fait que les lire.

Connexion : PostgreSQL sur localhost, port 5433, base et compte « barometre »
par défaut. Les variables BAROMETRE_HOTE, BAROMETRE_PORT, BAROMETRE_BASE et
BAROMETRE_COMPTE permettent d'en changer. Le mot de passe n'est jamais écrit
dans le projet : PostgreSQL le lit dans son fichier pgpass.conf.

Utilisation :
    python charger_base.py                  # charge ce qui manque, puis vérifie
    python charger_base.py --reinitialiser  # efface la base et recharge tout
"""

import argparse
import csv
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

import analyser_seao
import completer_contexte
from utilitaires import clean_org_name, clean_text, date_from_release_id, valid_date

SCHEMA_SQL = Path("schema.sql")
REGROUPEMENTS_CSV = Path("regroupements.csv")
A_COMPLETER = "À compléter"


# ---------------------------------------------------------------------------
# Petites conversions, sans base de données (ce sont elles que les tests vérifient)
# ---------------------------------------------------------------------------

def texte(valeur):
    """Un texte nettoyé, ou None : « À compléter », « NULL » et le vide deviennent None."""
    valeur = (valeur or "").strip() if isinstance(valeur, str) else valeur
    if valeur in (None, "", "NULL", A_COMPLETER):
        return None
    return valeur


def nombre(valeur):
    """Un nombre exact (Decimal), ou None.

    On passe par le texte publié plutôt que par un nombre à virgule flottante :
    77061.99 reste exactement 77061.99.
    """
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


def instant(valeur):
    """Une date ISO du SEAO convertie en date et heure, ou None si elle est absente ou fictive.

    Le SEAO emploie « 0001-01-01 » comme date fictive : on l'écarte, comme
    utilitaires.valid_date.
    """
    valeur = texte(valeur)
    if valeur is None or not valid_date(valeur):
        return None
    try:
        return datetime.fromisoformat(valeur)
    except ValueError:
        return None


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


def periode_de(nom_fichier):
    """« hebdo_20260907_20260913.json » donne les dates du 7 et du 13 septembre 2026."""
    m = re.search(r"(\d{8})_(\d{8})", nom_fichier)
    if not m:
        return None, None
    return tuple(datetime.strptime(d, "%Y%m%d").date() for d in m.groups())


def empreinte(chemin):
    """L'empreinte SHA-256 d'un fichier : deux fichiers identiques ont la même."""
    calcul = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(1 << 20), b""):
            calcul.update(bloc)
    return calcul.hexdigest()


def type_organisme(code):
    """Le type d'un organisme d'après le code inscrit dans le contexte."""
    code = texte(code)
    if code is None:
        return "non municipal"
    return "MRC ou communauté" if code[:2] in ("AR", "CM") else "municipalité"


def lignes_de_la_fiche(release, fichier):
    """Découpe une fiche municipale en lignes, une liste par table.

    Retourne un dictionnaire : fiche (une ligne), acheteur (son identifiant
    et l'organisme auquel son nom le rattache), tags, classifications,
    nomenclature, fournisseurs, soumissionnaires, attributions, contrats.
    S'arrête avec ValueError si la fiche contredit ce que le schéma suppose :
    un seul acheteur, un seul fournisseur par attribution, un contrat relié à
    une attribution de la même fiche.
    """
    ocid, release_id = clean_text(release.get("ocid")), clean_text(release.get("id"))
    cle = (ocid, release_id)
    acheteurs = [p for p in release.get("parties", []) if "buyer" in p.get("roles", [])]
    if len(acheteurs) != 1:
        raise ValueError(f"{ocid} / {release_id} : {len(acheteurs)} acheteurs au lieu d'un seul")

    tender = release.get("tender") or {}
    periode = tender.get("tenderPeriod") or {}
    items = tender.get("items") or []
    item = items[0] if items else {}
    if len(items) > 1:
        raise ValueError(f"{ocid} / {release_id} : {len(items)} items, le schéma n'en prévoit qu'un")
    documents = tender.get("documents") or []

    fiche = {
        "ocid": ocid, "release_id": release_id, "fichier_source": fichier,
        "date_deduite_numero": (date.fromisoformat(date_from_release_id(release))
                                if date_from_release_id(release) else None),
        "date_fiche": instant(release.get("date")),
        "acheteur_id": acheteurs[0]["id"],
        "numero_avis": texte(tender.get("id")),
        "titre": texte(tender.get("title")),
        "statut": texte(tender.get("status")),
        "methode_code": texte(tender.get("procurementMethod")),
        "methode": texte(tender.get("procurementMethodDetails")),
        "justification_methode": texte(tender.get("procurementMethodRationale")),
        "categorie_principale": texte(tender.get("mainProcurementCategory")),
        "type_contrat": texte(" | ".join(c.strip() for c in tender.get("additionalProcurementCategories") or [])),
        "nomenclature_code": texte(item.get("id")),
        "date_ouverture": instant(periode.get("startDate")),
        "date_fermeture": instant(periode.get("endDate")),
        "duree_jours": entier(periode.get("durationInDay")),
        "nb_soumissionnaires": entier(tender.get("numberOfTenderers")),
        "url_avis": texte(documents[0].get("url")) if documents else None,
        "brut": Jsonb(release),
    }

    tags = [{"ocid": ocid, "release_id": release_id, "tag": t} for t in dict.fromkeys(release.get("tag") or [])]

    classifications, codes_vus = [], set()
    principale = item.get("classification") or {}
    for c, est_principale in [(principale, True)] + [(c, False) for c in item.get("additionalClassifications") or []]:
        code = texte(c.get("id"))
        if code and code not in codes_vus:
            codes_vus.add(code)
            classifications.append({"ocid": ocid, "release_id": release_id, "code": code,
                                    "libelle": texte(c.get("description")) or code, "principale": est_principale})

    nomenclature = ([{"code": fiche["nomenclature_code"], "libelle": texte(item.get("description")) or fiche["nomenclature_code"]}]
                    if fiche["nomenclature_code"] else [])

    fournisseurs = []
    for p in release.get("parties", []):
        if "buyer" in p.get("roles", []) or not p.get("id"):
            continue
        adresse = p.get("address") or {}
        fournisseurs.append({
            "fournisseur_id": p["id"], "nom": texte(p.get("name")) or p["id"],
            "neq": texte((p.get("details") or {}).get("neq")),
            "adresse": texte(adresse.get("streetAddress")), "localite": texte(adresse.get("locality")),
            "region": texte(adresse.get("region")), "code_postal": texte(adresse.get("postalCode")),
            "pays": texte(adresse.get("countryName")),
        })

    soumissionnaires = [{"ocid": ocid, "release_id": release_id, "fournisseur_id": t["id"]}
                        for t in {t.get("id"): t for t in tender.get("tenderers") or [] if t.get("id")}.values()]

    # Quelques soumissionnaires ne figurent pas dans la liste des parties de la
    # fiche : on les ajoute quand même, avec le seul nom publié.
    connus = {f["fournisseur_id"] for f in fournisseurs}
    for t in tender.get("tenderers") or []:
        if t.get("id") and t["id"] not in connus:
            connus.add(t["id"])
            fournisseurs.append({"fournisseur_id": t["id"], "nom": texte(t.get("name")) or t["id"], "neq": None,
                                 "adresse": None, "localite": None, "region": None, "code_postal": None, "pays": None})

    attributions = []
    for a in release.get("awards") or []:
        fournisseurs_a = a.get("suppliers") or []
        if len(fournisseurs_a) != 1 or not fournisseurs_a[0].get("id"):
            raise ValueError(f"{ocid} / {release_id} : l'attribution {a.get('id')} n'a pas exactement un fournisseur identifié")
        valeur = a.get("value") or {}
        attributions.append({
            "ocid": ocid, "release_id": release_id, "attribution_id": str(a.get("id")),
            "fournisseur_id": fournisseurs_a[0]["id"], "statut": texte(a.get("status")),
            "date_attribution": instant(a.get("date")), "montant": nombre(valeur.get("amount")),
            "montant_total": nombre(valeur.get("totalAmount")), "devise": texte(valeur.get("currency")),
        })

    ids_attributions = {a["attribution_id"] for a in attributions}
    contrats = []
    for c in release.get("contracts") or []:
        if str(c.get("awardID")) not in ids_attributions:
            raise ValueError(f"{ocid} / {release_id} : le contrat {c.get('id')} renvoie à une attribution absente de la fiche")
        valeur = c.get("value") or {}
        contrats.append({
            "ocid": ocid, "release_id": release_id, "contrat_id": str(c.get("id")),
            "attribution_id": str(c.get("awardID")), "statut": texte(c.get("status")),
            "date_signature": instant(c.get("dateSigned")), "date_fin": instant((c.get("period") or {}).get("endDate")),
            "montant": nombre(valeur.get("amount")), "devise": texte(valeur.get("currency")),
        })

    # L'organisme se déduit du nom, avec la règle même d'analyser_seao.py : c'est
    # sous ce nom qu'il figure dans contexte_municipalites.csv.
    acheteur = {"acheteur_id": acheteurs[0]["id"],
                "organisme": clean_org_name(acheteurs[0].get("name")),
                "nom_seao": clean_text(acheteurs[0].get("name"))}

    return {"fiche": fiche, "acheteur": acheteur, "tags": tags, "classifications": classifications, "nomenclature": nomenclature,
            "fournisseurs": fournisseurs, "soumissionnaires": soumissionnaires,
            "attributions": attributions, "contrats": contrats}


# ---------------------------------------------------------------------------
# Écriture dans la base
# ---------------------------------------------------------------------------

def inserer(connexion, table, lignes, conflit="DO NOTHING", cle=None):
    """Insère des lignes (des dictionnaires aux mêmes clés) dans une table.

    conflit dit quoi faire si la ligne existe déjà : DO NOTHING (garder
    l'ancienne) ou DO UPDATE (la remplacer, pour les données de référence).
    """
    if not lignes:
        return
    colonnes = list(lignes[0])
    requete = (f"INSERT INTO {table} ({', '.join(colonnes)}) VALUES ({', '.join('%(' + c + ')s' for c in colonnes)}) "
               f"ON CONFLICT")
    if conflit == "DO UPDATE":
        mises_a_jour = [c for c in colonnes if c not in cle]
        requete += f" ({', '.join(cle)}) DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in mises_a_jour)
    else:
        requete += " DO NOTHING"
    with connexion.cursor() as curseur:
        curseur.executemany(requete, lignes)


def noter_fichier_reference(connexion, chemin, description):
    """Garde la trace d'un fichier de référence : sa date et son empreinte."""
    inserer(connexion, "territoire.fichier_reference", [{
        "nom": chemin.name, "description": description,
        "date_fichier": datetime.fromtimestamp(chemin.stat().st_mtime).date(),
        "empreinte_sha256": empreinte(chemin)}], "DO UPDATE", ["nom"])


def charger_territoire(connexion):
    """Charge régions, MRC, municipalités, regroupements et données sur l'eau.

    Ces données décrivent l'état actuel du répertoire : une nouvelle version
    du fichier remplace les valeurs déjà en base.
    """
    dossier = completer_contexte.DOSSIER_SOURCES

    def lire(cle):
        nom, _, description = completer_contexte.FICHIERS[cle]
        chemin = dossier / nom
        noter_fichier_reference(connexion, chemin, description)
        return completer_contexte.lire_csv(chemin.read_bytes())

    municipalites, mrc = lire("municipalites"), lire("mrc")

    regions = {}
    for libelle in [m["regadm"] for m in municipalites] + [m["mrcregion"] for m in mrc]:
        code, nom = region_de(libelle)
        if code:
            if code in regions and regions[code] != nom:
                raise ValueError(f"La région {code} porte deux noms : {regions[code]} et {nom}")
            regions[code] = nom
    inserer(connexion, "territoire.region", [{"code": c, "nom": n} for c, n in sorted(regions.items())], "DO UPDATE", ["code"])

    inserer(connexion, "territoire.mrc", [{
        "code": m["mrccod"].strip(), "nom": m["mrcnom"].strip(), "designation": m["mrcdescdesi"].strip(),
        "population": entier(m["mrcpopul"]), "superficie_km2": nombre(m["msupf"]),
        "code_postal": texte(m["mrccodp"]), "region_code": region_de(m["mrcregion"])[0],
    } for m in mrc], "DO UPDATE", ["code"])

    inserer(connexion, "territoire.municipalite", [{
        "code_geographique": m["mcode"].strip(), "nom": m["munnom"].strip(), "designation": m["mdes"].strip(),
        "population": entier(m["mpopul"]), "superficie_km2": nombre(m["msuperf"]),
        "superficie_terrestre_km2": nombre(m["msupft"]), "code_postal": texte(m["mcodpos"]),
        "date_constitution": date.fromisoformat(m["mdatcons"]) if texte(m["mdatcons"]) else None,
        "region_code": region_de(m["regadm"])[0], "mrc_code": code_mrc_de(m["mrc"]),
        "communaute_code": code_mrc_de(m["mcm"], "CM"),
    } for m in municipalites], "DO UPDATE", ["code_geographique"])

    with REGROUPEMENTS_CSV.open(encoding="utf-8-sig", newline="") as fichier:
        regroupements = list(csv.DictReader(fichier))
    noter_fichier_reference(connexion, REGROUPEMENTS_CSV, "Regroupements de municipalités, tenus à la main avec leur source")
    inserer(connexion, "territoire.regroupement", [{
        "ancien_code": r["ancien_code"], "ancien_nom": r["ancien_nom"], "code_geographique": r["code_geographique"],
        "date_effet": date.fromisoformat(r["date_effet"]), "source": r["source"],
    } for r in regroupements], "DO UPDATE", ["ancien_code"])

    # Les trois fichiers de la Stratégie, réunis par code et par année. Le zéro
    # du début manque parfois : on complète chaque code à cinq chiffres.
    actuels = {m["mcode"].strip() for m in municipalites}
    successeurs = {r["ancien_code"]: r["code_geographique"] for r in regroupements}
    eau = {}
    for cle, colonne_code, champs in (
            ("validite", "mun_c", {"classe_population": "cl_pop_desservie", "population_desservie": "pop_desservie",
                                   "validite_audit_pct": "pourc_indice_validite"}),
            ("fuites", "num_c", {"indice_fuites": "indice_fuites_ifi", "longueur_reseau_km": "long_reseau_km"}),
            ("consommation", "mun_c", {"consommation_l_pers_jour": "consom_resid"})):
        for ligne in lire(cle):
            code = ligne[colonne_code].strip().zfill(5)
            rangee = eau.setdefault((code, int(ligne["annee"])), {
                "code_source": code, "annee": int(ligne["annee"]),
                "nom_source": texte(ligne.get("mun_n") or ligne.get("num_n")),
                "code_geographique": code if code in actuels else successeurs.get(code),
                "classe_population": None, "population_desservie": None, "indice_fuites": None,
                "validite_audit_pct": None, "consommation_l_pers_jour": None, "longueur_reseau_km": None})
            for colonne, source in champs.items():
                valeur = texte(ligne.get(source))
                rangee[colonne] = (valeur if colonne == "classe_population"
                                   else entier(valeur) if colonne == "population_desservie" else nombre(valeur))
    inserer(connexion, "territoire.indicateur_eau", list(eau.values()), "DO UPDATE", ["code_source", "annee"])


def charger_organismes(connexion):
    """Charge les organismes du contexte et leurs identifiants d'acheteur.

    Le contexte fait foi : un organisme déjà en base reçoit les valeurs
    actuelles du fichier. Les cases « À compléter » deviennent des valeurs
    absentes (NULL).
    """
    with completer_contexte.CONTEXTE_CSV.open(encoding="utf-8-sig", newline="") as fichier:
        contexte = list(csv.DictReader(fichier))

    inserer(connexion, "organismes.organisme", [{
        "nom": ligne["organisme"], "type": type_organisme(ligne["code_geographique"]),
        "code_geographique": texte(ligne["code_geographique"]) if type_organisme(ligne["code_geographique"]) == "municipalité" else None,
        "mrc_code": texte(ligne["code_geographique"]) if type_organisme(ligne["code_geographique"]) == "MRC ou communauté" else None,
        "proximite_fleuve_lac_riviere": texte(ligne["proximite_fleuve_lac_riviere"]),
        "type_milieu": texte(ligne["type_milieu"]), "source_contexte": texte(ligne["source_contexte"]),
        "notes": texte(ligne["notes"]),
    } for ligne in contexte], "DO UPDATE", ["nom"])

    ids = dict(connexion.execute("SELECT nom, organisme_id FROM organismes.organisme").fetchall())
    acheteurs = [{"acheteur_id": i.strip(), "organisme_id": ids[ligne["organisme"]], "nom_seao": None}
                 for ligne in contexte for i in ligne["buyer_ids"].split("|") if i.strip()]
    with connexion.cursor() as curseur:
        curseur.executemany(
            "INSERT INTO organismes.acheteur (acheteur_id, organisme_id, nom_seao) "
            "VALUES (%(acheteur_id)s, %(organisme_id)s, %(nom_seao)s) "
            "ON CONFLICT (acheteur_id) DO UPDATE SET organisme_id = EXCLUDED.organisme_id", acheteurs)
    return len(contexte), len(acheteurs)


def charger_export(connexion, chemin):
    """Charge les fiches municipales d'un export, d'un seul bloc.

    Retourne le nombre de fiches ajoutées, ou None si l'export était déjà en
    base. Une fiche déjà présente, venue d'un autre export qui la contenait
    aussi, n'est pas ajoutée une seconde fois.
    """
    signature = empreinte(chemin)
    deja = connexion.execute("SELECT empreinte_sha256 FROM seao.fichier_source WHERE nom = %s", (chemin.name,)).fetchone()
    if deja:
        if deja[0] != signature:
            raise ValueError(f"{chemin.name} est déjà en base, mais le fichier a changé depuis. "
                             "Rien n'est chargé : vérifier le fichier, ou relancer avec --reinitialiser.")
        return None

    with chemin.open(encoding="utf-8-sig") as fichier:
        donnees = json.load(fichier)
    releases = donnees.get("releases", [])
    analyser_seao.validate_identifiers(releases)      # même contrôle que le programme d'analyse
    municipales = [r for r in releases if analyser_seao.get_municipal_buyer_party(r)]

    existantes = set(connexion.execute("SELECT ocid, release_id FROM seao.fiche").fetchall())
    nouvelles = [lignes_de_la_fiche(r, chemin.name) for r in municipales]
    nouvelles = [n for n in nouvelles if (n["fiche"]["ocid"], n["fiche"]["release_id"]) not in existantes]

    debut, fin = periode_de(chemin.name)
    inserer(connexion, "seao.fichier_source", [{
        "nom": chemin.name, "periode_debut": debut, "periode_fin": fin,
        "date_publication": instant(donnees.get("publishedDate")), "empreinte_sha256": signature,
        "nb_fiches": len(releases), "nb_fiches_municipales": len(municipales), "nb_fiches_ajoutees": len(nouvelles)}])

    def toutes(cle):
        return [ligne for n in nouvelles for ligne in n[cle]]

    # Fournisseurs et listes de codes d'abord : les fiches s'y réfèrent.
    fournisseurs = {f["fournisseur_id"]: f for f in toutes("fournisseurs")}
    inserer(connexion, "seao.fournisseur", list(fournisseurs.values()), "DO UPDATE", ["fournisseur_id"])
    inserer(connexion, "seao.nomenclature", list({n["code"]: n for n in toutes("nomenclature")}.values()))
    inserer(connexion, "seao.classification",
            list({c["code"]: {"code": c["code"], "libelle": c["libelle"]} for c in toutes("classifications")}.values()))

    # Les acheteurs. Le contexte ne connaît pas toujours tous les identifiants
    # d'un organisme : Montréal en a 36 dans l'export d'août, mais le contexte,
    # où les identifiants d'une ligne existante ne sont jamais mis à jour, ne
    # connaît que les 31 de la semaine du 7 septembre. Un identifiant inconnu
    # est donc rattaché par le nom de l'organisme, comme le fait
    # analyser_seao.py. Un organisme absent du contexte arrête tout.
    organismes = dict(connexion.execute("SELECT nom, organisme_id FROM organismes.organisme").fetchall())
    connus = dict(connexion.execute("SELECT acheteur_id, organisme_id FROM organismes.acheteur").fetchall())
    acheteurs = {n["acheteur"]["acheteur_id"]: n["acheteur"] for n in nouvelles}
    for identifiant, acheteur in acheteurs.items():
        if acheteur["organisme"] not in organismes:
            raise ValueError(f"{acheteur['organisme']} ({identifiant}) n'est pas dans contexte_municipalites.csv : "
                             "lancer d'abord analyser_seao.py sur cet export.")
        if identifiant in connus and connus[identifiant] != organismes[acheteur["organisme"]]:
            raise ValueError(f"L'identifiant {identifiant} est rattaché à un autre organisme que « {acheteur['organisme']} ».")
    with connexion.cursor() as curseur:
        curseur.executemany(
            "INSERT INTO organismes.acheteur (acheteur_id, organisme_id, nom_seao) VALUES (%s, %s, %s) "
            "ON CONFLICT (acheteur_id) DO UPDATE SET nom_seao = EXCLUDED.nom_seao",
            [(i, organismes[a["organisme"]], a["nom_seao"]) for i, a in acheteurs.items()])

    inserer(connexion, "seao.fiche", [n["fiche"] for n in nouvelles])
    inserer(connexion, "seao.fiche_tag", toutes("tags"))
    inserer(connexion, "seao.fiche_classification",
            [{k: c[k] for k in ("ocid", "release_id", "code", "principale")} for c in toutes("classifications")])
    inserer(connexion, "seao.soumissionnaire", toutes("soumissionnaires"))
    inserer(connexion, "seao.attribution", toutes("attributions"))
    inserer(connexion, "seao.contrat", toutes("contrats"))
    return len(nouvelles)


def version_des_regles():
    """L'empreinte d'analyser_seao.py et d'utilitaires.py : elle change dès qu'une règle change.

    Les règles sont dans analyser_seao.py, mais elles s'appuient sur les
    outils d'utilitaires.py, comme la lecture des dates : les deux comptent.
    """
    fichiers = [Path(analyser_seao.__file__), Path(analyser_seao.__file__).with_name("utilitaires.py")]
    return "analyser_seao.py " + hashlib.sha256(b"".join(f.read_bytes() for f in fichiers)).hexdigest()[:12]


def classer_fiches(connexion):
    """Applique les règles d'analyser_seao.py à toutes les fiches, et range le résultat.

    On réutilise analyse_release, la fonction même qui produit les CSV : la
    base et les CSV ne peuvent donc pas classer une fiche différemment.
    """
    version = version_des_regles()
    lignes = []
    for ocid, release_id, brut in connexion.execute("SELECT ocid, release_id, brut FROM seao.fiche"):
        ligne = analyser_seao.analyse_release(brut)
        lignes.append({"ocid": ocid, "release_id": release_id, "nature_transaction": ligne["nature_transaction"],
                       "lie_eau": ligne["lie_eau"] == "oui", "pga_eau": ligne["pga_eau"] == "oui",
                       "version_regles": version, "calcule_le": datetime.now(timezone.utc)})
    inserer(connexion, "analyses.fiche_classee", lignes, "DO UPDATE", ["ocid", "release_id"])
    return len(lignes)


# ---------------------------------------------------------------------------
# Vérifications
# ---------------------------------------------------------------------------

def verifier(connexion):
    """Compare la base aux CSV d'analyser_seao.py, export par export.

    Pour chaque export : même nombre de fiches municipales, même somme des
    montants attribués, mêmes dossiers PGA-Eau. Retourne la liste des écarts;
    elle doit être vide.
    """
    ecarts = []
    exports = connexion.execute("SELECT nom, nb_fiches_municipales FROM seao.fichier_source ORDER BY nom").fetchall()
    for nom, nb_municipales in exports:
        details_csv = analyser_seao.noms_de_sortie(analyser_seao.DOSSIER_SEAO / nom)[0]
        if not details_csv.exists():
            print(f"  {nom} : {details_csv} absent, comparaison impossible (lancer analyser_seao.py)")
            continue
        with details_csv.open(encoding="utf-8-sig", newline="") as fichier:
            details = list(csv.DictReader(fichier))
        # Les fiches de cet export, même celles déjà chargées par un autre export.
        cles = {(d["ocid"], d["release_id"]) for d in details}
        en_base = {(o, r) for o, r in connexion.execute("SELECT ocid, release_id FROM seao.fiche").fetchall()} & cles
        somme_csv = sum(Decimal(d["montant_attribue"]) for d in details if d["montant_attribue"])
        somme_base = connexion.execute(
            "SELECT coalesce(sum(montant), 0) FROM seao.attribution WHERE (ocid, release_id) IN "
            "(SELECT ocid, release_id FROM unnest(%s::text[], %s::text[]) AS t(ocid, release_id))",
            ([c[0] for c in cles], [c[1] for c in cles])).fetchone()[0]
        pga_csv = {(d["ocid"], d["release_id"]) for d in details if d["pga_eau"] == "oui"}
        pga_base = {(o, r) for o, r in connexion.execute(
            "SELECT ocid, release_id FROM analyses.fiche_classee WHERE pga_eau").fetchall()} & cles
        print(f"  {nom} : {len(en_base)} fiches sur {len(details)} | montants attribués {somme_base:,.2f} $ "
              f"contre {somme_csv:,.2f} $ dans le CSV | PGA-Eau {len(pga_base)} sur {len(pga_csv)}")
        if len(en_base) != len(details) or nb_municipales != len(details):
            ecarts.append(f"{nom} : nombre de fiches différent")
        if abs(somme_base - somme_csv) > Decimal("0.01"):
            ecarts.append(f"{nom} : somme des montants différente")
        if pga_base != pga_csv:
            ecarts.append(f"{nom} : dossiers PGA-Eau différents")
    return ecarts


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def connecter():
    """Ouvre la connexion. Le mot de passe vient du fichier pgpass.conf de PostgreSQL."""
    return psycopg.connect(
        host=os.environ.get("BAROMETRE_HOTE", "localhost"), port=int(os.environ.get("BAROMETRE_PORT", "5433")),
        dbname=os.environ.get("BAROMETRE_BASE", "barometre"), user=os.environ.get("BAROMETRE_COMPTE", "barometre"),
        connect_timeout=10)


def main():
    parser = argparse.ArgumentParser(description="Charge le SEAO, le répertoire et le contexte dans PostgreSQL.")
    parser.add_argument("--reinitialiser", action="store_true",
                        help="efface les quatre schémas et recharge tout depuis les fichiers")
    args = parser.parse_args()

    with connecter() as connexion:
        if args.reinitialiser:
            connexion.execute("DROP SCHEMA IF EXISTS analyses, seao, organismes, territoire CASCADE")
            print("Base effacée.")
        connexion.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        connexion.commit()

        print("Territoire et organismes...")
        charger_territoire(connexion)
        nb_organismes, nb_acheteurs = charger_organismes(connexion)
        connexion.commit()
        print(f"  {nb_organismes} organismes, {nb_acheteurs} identifiants d'acheteur")

        for chemin in sorted(analyser_seao.DOSSIER_SEAO.glob("*.json")):
            ajoutees = charger_export(connexion, chemin)
            connexion.commit()          # un export entier, ou rien
            print(f"  {chemin.name} : " + ("déjà chargé" if ajoutees is None else f"{ajoutees} fiches ajoutées"))

        print(f"Classement : {classer_fiches(connexion)} fiches ({version_des_regles()})")
        connexion.commit()

        print("\nVérifications :")
        ecarts = verifier(connexion)
        print("  Aucun écart avec les CSV." if not ecarts else "  ÉCARTS : " + "; ".join(ecarts))

        print("\nContenu de la base :")
        for table in ("territoire.municipalite", "territoire.mrc", "territoire.indicateur_eau", "organismes.organisme",
                      "organismes.acheteur", "seao.fiche", "seao.attribution", "seao.contrat", "seao.fournisseur",
                      "analyses.contrat_courant"):
            print(f"  {table:<28} {connexion.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:>7}")


if __name__ == "__main__":
    main()
