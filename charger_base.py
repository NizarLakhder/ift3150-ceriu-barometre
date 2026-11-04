"""
Charge dans PostgreSQL le répertoire des municipalités, le contexte, les
exports du SEAO et les démarches classées à la main, puis vérifie que la base
redonne les chiffres des CSV d'analyser_seao.py.

Ordre de chargement :
  1. le territoire : donnees_reference/ et regroupements.csv;
  2. les organismes et leurs identifiants d'acheteur : contexte_municipalites.csv;
  3. les exports de donnees_seao/ pas encore chargés, dans l'ordre de leur
     période, fiches municipales seulement;
  4. le classement de chaque fiche, avec les règles d'analyser_seao.py;
  5. les démarches de demarches.csv.

Chaque export est chargé une seule fois (son empreinte est notée), d'un seul
bloc. Les fichiers sources ne sont jamais modifiés. Le programme écrit aussi
sorties/fournisseurs_a_regrouper.csv, les identifiants FO à vérifier à la main.

Les tables sont créées à partir de schema.sql si le schéma seao n'existe pas.
Connexion : localhost, port 5433, base et compte « barometre », ou les
variables BAROMETRE_HOTE, BAROMETRE_PORT, BAROMETRE_BASE et BAROMETRE_COMPTE.
Le mot de passe est lu dans pgpass.conf, jamais dans le projet.

Utilisation :
    python charger_base.py                  # charge ce qui manque, puis vérifie
    python charger_base.py --reinitialiser  # efface tout et recharge, après une modification de schema.sql
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
from utilitaires import clean_org_name, clean_text, date_from_release_id, valid_date, write_csv

SCHEMA_SQL = Path("schema.sql")
REGROUPEMENTS_CSV = Path("regroupements.csv")
DEMARCHES_CSV = Path("demarches.csv")
A_REGROUPER_CSV = analyser_seao.DOSSIER_SORTIES / "fournisseurs_a_regrouper.csv"
A_COMPLETER = "À compléter"

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


# ---------------------------------------------------------------------------
# Conversions sans base de données, vérifiées par test_charger_base.py
# ---------------------------------------------------------------------------

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


def instant(valeur):
    """Une date ISO du SEAO en date et heure, ou None si elle est absente ou fictive (« 0001-01-01 »)."""
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


def decrire_export(nom_fichier):
    """« hebdo_20260907_20260913.json » donne ("hebdomadaire", 7 septembre 2026, 13 septembre 2026).

    Le type et la période d'un export ne sont écrits que dans son nom : un nom
    d'une autre forme arrête le chargement.
    """
    m = re.fullmatch(r"(hebdo|mensuel)_(\d{8})_(\d{8})\.json", nom_fichier)
    if not m:
        raise ValueError(f"{nom_fichier} : nom d'export inattendu, il devrait ressembler à hebdo_20260907_20260913.json.")
    debut, fin = (datetime.strptime(d, "%Y%m%d").date() for d in m.group(2, 3))
    return ("hebdomadaire" if m.group(1) == "hebdo" else "mensuel"), debut, fin


def empreinte(chemin):
    """L'empreinte SHA-256 d'un fichier."""
    calcul = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(1 << 20), b""):
            calcul.update(bloc)
    return calcul.hexdigest()


def code_de(colonne, libelle):
    """Le code que la base donne à un libellé : « mandat attribué » devient « mandat_attribue »."""
    try:
        return CODES[colonne][libelle]
    except KeyError:
        raise ValueError(f"« {libelle} » n'est pas une valeur permise pour {colonne} : "
                         + ", ".join(f"« {l} »" for l in CODES[colonne]) + ".") from None


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


def lignes_de_la_fiche(release):
    """Découpe une fiche municipale en lignes, une liste par table.

    Retourne ocid, fiche, acheteur, classifications, nomenclature, fournisseurs,
    soumissionnaires, attributions et contrats, sans numéro de fiche : la base le
    donne au chargement. Lève ValueError si la fiche contredit le schéma : pas
    exactement un acheteur, plus d'un item, une attribution sans exactement un
    fournisseur, un contrat sans son attribution.
    """
    ocid, release_id = clean_text(release.get("ocid")), clean_text(release.get("id"))
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
        "release_id": release_id,
        "date_deduite_numero": (date.fromisoformat(date_from_release_id(release))
                                if date_from_release_id(release) else None),
        "date_fiche": instant(release.get("date")),
        "acheteur_id": acheteurs[0]["id"],
        "tags": list(dict.fromkeys(release.get("tag") or [])),
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

    classifications, codes_vus = [], set()
    principale = item.get("classification") or {}
    for c, est_principale in [(principale, True)] + [(c, False) for c in item.get("additionalClassifications") or []]:
        code = texte(c.get("id"))
        if code and code not in codes_vus:
            codes_vus.add(code)
            classifications.append({"code": code, "libelle": texte(c.get("description")) or code,
                                    "principale": est_principale})

    nomenclature = ([{"code": fiche["nomenclature_code"], "libelle": texte(item.get("description")) or fiche["nomenclature_code"]}]
                    if fiche["nomenclature_code"] else [])

    fournisseurs = []
    for p in release.get("parties", []):
        if "buyer" in p.get("roles", []) or not p.get("id"):
            continue
        adresse = p.get("address") or {}
        fournisseurs.append({
            "identifiant": p["id"], "nom": texte(p.get("name")) or p["id"],
            "neq": texte((p.get("details") or {}).get("neq")),
            "adresse": texte(adresse.get("streetAddress")), "localite": texte(adresse.get("locality")),
            "region": texte(adresse.get("region")), "code_postal": texte(adresse.get("postalCode")),
            "pays": texte(adresse.get("countryName")),
        })

    soumissionnaires = list(dict.fromkeys(t["id"] for t in tender.get("tenderers") or [] if t.get("id")))

    # Des soumissionnaires manquent dans les parties : on les garde, avec leur seul nom.
    connus = {f["identifiant"] for f in fournisseurs}
    for t in tender.get("tenderers") or []:
        if t.get("id") and t["id"] not in connus:
            connus.add(t["id"])
            fournisseurs.append({"identifiant": t["id"], "nom": texte(t.get("name")) or t["id"], "neq": None,
                                 "adresse": None, "localite": None, "region": None, "code_postal": None, "pays": None})

    attributions = []
    for a in release.get("awards") or []:
        fournisseurs_a = a.get("suppliers") or []
        if len(fournisseurs_a) != 1 or not fournisseurs_a[0].get("id"):
            raise ValueError(f"{ocid} / {release_id} : l'attribution {a.get('id')} n'a pas exactement un fournisseur identifié")
        valeur = a.get("value") or {}
        attributions.append({
            "numero": str(a.get("id")), "identifiant_fournisseur": fournisseurs_a[0]["id"],
            "statut": texte(a.get("status")), "date_attribution": instant(a.get("date")),
            "montant": nombre(valeur.get("amount")), "montant_total": nombre(valeur.get("totalAmount")),
            "devise": texte(valeur.get("currency")),
        })

    numeros_attributions = {a["numero"] for a in attributions}
    contrats = []
    for c in release.get("contracts") or []:
        if str(c.get("awardID")) not in numeros_attributions:
            raise ValueError(f"{ocid} / {release_id} : le contrat {c.get('id')} renvoie à une attribution absente de la fiche")
        valeur = c.get("value") or {}
        contrats.append({
            "numero": str(c.get("id")), "numero_attribution": str(c.get("awardID")), "statut": texte(c.get("status")),
            "date_signature": instant(c.get("dateSigned")), "date_fin": instant((c.get("period") or {}).get("endDate")),
            "montant": nombre(valeur.get("amount")), "devise": texte(valeur.get("currency")),
        })

    # Le nom nettoyé comme dans analyser_seao.py : c'est la clé de contexte_municipalites.csv.
    acheteur = {"acheteur_id": acheteurs[0]["id"],
                "organisme": clean_org_name(acheteurs[0].get("name")),
                "nom_seao": clean_text(acheteurs[0].get("name"))}

    return {"ocid": ocid, "fiche": fiche, "acheteur": acheteur, "classifications": classifications,
            "nomenclature": nomenclature, "fournisseurs": fournisseurs, "soumissionnaires": soumissionnaires,
            "attributions": attributions, "contrats": contrats}


def forme_comparable(valeur):
    """La fiche avec ses listes triées : le SEAO republie souvent une fiche dans un autre ordre."""
    if isinstance(valeur, dict):
        return {cle: forme_comparable(v) for cle, v in valeur.items()}
    if isinstance(valeur, list):
        return sorted((forme_comparable(v) for v in valeur),
                      key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
    return valeur


def meme_contenu(fiche, autre):
    """Vrai si deux publications d'une fiche ne diffèrent que par l'ordre de leurs listes."""
    return forme_comparable(fiche) == forme_comparable(autre)


def completer(infos, lecture):
    """Complète les informations d'un fournisseur par une nouvelle lecture.

    La dernière valeur lue l'emporte, mais une valeur absente n'efface jamais une
    valeur connue, comme le NEQ d'un soumissionnaire absent des parties.
    """
    return {**infos, **{k: v for k, v in lecture.items() if v is not None or k not in infos}}


def regrouper_fournisseurs(lus, connus, par_neq):
    """Décide à quelle entreprise va chaque identifiant FO d'un export, sans toucher à la base.

    lus : les fournisseurs lus dans l'export, dans l'ordre. connus et par_neq
    relient les identifiants et les NEQ déjà en base à leur entreprise. Deux
    identifiants au même NEQ vont à la même entreprise.

    Retourne les entreprises à créer, les identifiants à rattacher à une
    entreprise en base, et les mises à jour par entreprise. Un identifiant connu
    qui porte le NEQ d'une autre entreprise lève ValueError : à regrouper à la main.
    """
    infos = {}
    for lecture in lus:
        identifiant = lecture["identifiant"]
        infos[identifiant] = completer(infos.get(identifiant, {}),
                                       {k: v for k, v in lecture.items() if k != "identifiant"})

    a_creer, rattaches, a_mettre_a_jour = {}, [], {}
    for identifiant, info in infos.items():
        neq = info["neq"]
        if identifiant in connus:
            entreprise = connus[identifiant]
            if neq is not None and par_neq.get(neq, entreprise) != entreprise:
                raise ValueError(f"{identifiant} porte le NEQ {neq}, qui est déjà celui d'une autre entreprise : "
                                 "à regrouper à la main.")
            a_mettre_a_jour[entreprise] = completer(a_mettre_a_jour.get(entreprise, {}), info)
        elif neq is not None and neq in par_neq:
            rattaches.append((identifiant, par_neq[neq]))
            a_mettre_a_jour[par_neq[neq]] = completer(a_mettre_a_jour.get(par_neq[neq], {}), info)
        else:
            groupe = a_creer.setdefault(("neq", neq) if neq is not None else ("identifiant", identifiant),
                                        {"infos": {}, "identifiants": []})
            groupe["infos"] = completer(groupe["infos"], info)
            groupe["identifiants"].append(identifiant)
    return list(a_creer.values()), rattaches, a_mettre_a_jour


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
    """Charge régions, MRC, municipalités avec leurs anciens codes, et données sur l'eau.

    Une nouvelle version d'un fichier remplace les valeurs déjà en base.
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

    # Une municipalité regroupée laisse son code et son nom à celle qui l'a absorbée.
    # L'ancien code doit avoir quitté le répertoire, et la nouvelle municipalité y être.
    with REGROUPEMENTS_CSV.open(encoding="utf-8-sig", newline="") as fichier:
        regroupements = list(csv.DictReader(fichier))
    noter_fichier_reference(connexion, REGROUPEMENTS_CSV, "Regroupements de municipalités, tenus à la main avec leur source")
    actuels = {m["mcode"].strip() for m in municipalites}
    successeurs, anciens = {}, {}
    for r in regroupements:
        if r["ancien_code"] in actuels or r["ancien_code"] in successeurs or r["code_geographique"] not in actuels:
            raise ValueError(f"regroupements.csv : l'ancien code {r['ancien_code']} ou la municipalité "
                             f"{r['code_geographique']} ne correspond pas au répertoire.")
        successeurs[r["ancien_code"]] = r["code_geographique"]
        codes, noms = anciens.setdefault(r["code_geographique"], ([], []))
        codes.append(r["ancien_code"])
        noms.append(r["ancien_nom"])

    inserer(connexion, "territoire.municipalite", [{
        "code_geographique": m["mcode"].strip(), "nom": m["munnom"].strip(), "designation": m["mdes"].strip(),
        "population": entier(m["mpopul"]), "superficie_km2": nombre(m["msuperf"]),
        "superficie_terrestre_km2": nombre(m["msupft"]), "code_postal": texte(m["mcodpos"]),
        "date_constitution": date.fromisoformat(m["mdatcons"]) if texte(m["mdatcons"]) else None,
        "region_code": region_de(m["regadm"])[0], "mrc_code": code_mrc_de(m["mrc"]),
        "communaute_code": code_mrc_de(m["mcm"], "CM"),
        "anciens_codes": anciens.get(m["mcode"].strip(), ([], []))[0],
        "anciens_noms": anciens.get(m["mcode"].strip(), ([], []))[1],
    } for m in municipalites], "DO UPDATE", ["code_geographique"])

    # Les trois fichiers de la Stratégie, réunis par code et par année. Le zéro
    # du début manque parfois : on complète chaque code à cinq chiffres.
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

    Le fichier fait foi : il met à jour les organismes déjà en base. « À compléter » devient NULL.
    """
    with completer_contexte.CONTEXTE_CSV.open(encoding="utf-8-sig", newline="") as fichier:
        contexte = list(csv.DictReader(fichier))
    municipalites = {c for (c,) in connexion.execute("SELECT code_geographique FROM territoire.municipalite")}
    mrc = {c for (c,) in connexion.execute("SELECT code FROM territoire.mrc")}

    organismes = []
    for ligne in contexte:
        code = texte(ligne["code_geographique"])
        try:
            sorte = type_organisme(code, municipalites, mrc)
        except ValueError as erreur:
            raise ValueError(f"contexte_municipalites.csv, « {ligne['organisme']} » : {erreur}") from None
        organismes.append({
            "nom": ligne["organisme"], "type": sorte,
            "code_geographique": code if sorte == "municipalite" else None,
            "mrc_code": code if sorte == "mrc_ou_communaute" else None,
            "type_milieu": texte(ligne["type_milieu"]), "source_contexte": texte(ligne["source_contexte"]),
            "notes": texte(ligne["notes"]),
        })
    inserer(connexion, "organismes.organisme", organismes, "DO UPDATE", ["nom"])

    ids = dict(connexion.execute("SELECT nom, organisme_id FROM organismes.organisme").fetchall())
    acheteurs = [{"acheteur_id": i.strip(), "organisme_id": ids[ligne["organisme"]], "nom_seao": None}
                 for ligne in contexte for i in ligne["buyer_ids"].split("|") if i.strip()]
    with connexion.cursor() as curseur:
        curseur.executemany(
            "INSERT INTO organismes.acheteur (acheteur_id, organisme_id, nom_seao) "
            "VALUES (%(acheteur_id)s, %(organisme_id)s, %(nom_seao)s) "
            "ON CONFLICT (acheteur_id) DO UPDATE SET organisme_id = EXCLUDED.organisme_id", acheteurs)
    return len(contexte), len(acheteurs)


def organisme_de(identifiant, nom, connus, organismes):
    """Trouve l'organisme d'un identifiant d'acheteur publié dans une fiche.

    connus relie les identifiants en base à leur organisme, organismes les noms du
    contexte au leur. Un identifiant connu fait foi, même si le nom change
    d'écriture (« D'Amherst » devient « d'Amherst » en septembre). Un identifiant
    inconnu est rattaché par le nom : le contexte n'a pas tous ceux de Montréal.
    Lève ValueError si le nom est absent du contexte ou désigne un autre organisme.
    """
    par_nom = organismes.get(nom)
    if identifiant in connus:
        if par_nom is not None and par_nom != connus[identifiant]:
            raise ValueError(f"L'identifiant {identifiant} est rattaché à un autre organisme que « {nom} ».")
        return connus[identifiant]
    if par_nom is None:
        raise ValueError(f"{nom} ({identifiant}) n'est pas dans contexte_municipalites.csv : "
                         "lancer d'abord analyser_seao.py sur cet export.")
    return par_nom


def charger_fournisseurs(connexion, lus):
    """Range en base les fournisseurs lus dans un export, regroupés par regrouper_fournisseurs."""
    connus = dict(connexion.execute("SELECT identifiant, fournisseur_id FROM seao.identifiant_fournisseur").fetchall())
    par_neq = dict(connexion.execute("SELECT neq, fournisseur_id FROM seao.fournisseur WHERE neq IS NOT NULL").fetchall())
    a_creer, rattaches, a_mettre_a_jour = regrouper_fournisseurs(lus, connus, par_neq)
    colonnes = ("nom", "neq", "adresse", "localite", "region", "code_postal", "pays")
    with connexion.cursor() as curseur:
        if a_creer:
            # La base attribue les numéros : on les lit dans l'ordre des entreprises envoyées.
            curseur.executemany(f"INSERT INTO seao.fournisseur ({', '.join(colonnes)}) "
                                f"VALUES ({', '.join('%(' + c + ')s' for c in colonnes)}) RETURNING fournisseur_id",
                                [{c: g["infos"][c] for c in colonnes} for g in a_creer], returning=True)
            numeros = []
            while True:
                numeros.append(curseur.fetchone()[0])
                if not curseur.nextset():
                    break
            rattaches += [(i, numero) for g, numero in zip(a_creer, numeros) for i in g["identifiants"]]
        if rattaches:
            curseur.executemany("INSERT INTO seao.identifiant_fournisseur (identifiant, fournisseur_id) VALUES (%s, %s)",
                                rattaches)
        if a_mettre_a_jour:
            curseur.executemany(
                "UPDATE seao.fournisseur SET nom = %(nom)s, "
                + ", ".join(f"{c} = coalesce(%({c})s, {c})" for c in colonnes if c != "nom")
                + " WHERE fournisseur_id = %(fournisseur_id)s",
                [{**{c: infos[c] for c in colonnes}, "fournisseur_id": f} for f, infos in a_mettre_a_jour.items()])


def cles_des_fiches(connexion):
    """Relie chaque fiche en base, par son dossier et son numéro, au numéro que la base lui a donné."""
    return {(o, r): f for o, r, f in connexion.execute(
        "SELECT d.ocid, f.release_id, f.fiche_id FROM seao.fiche f JOIN seao.dossier d ON d.dossier_id = f.dossier_id")}


def charger_export(connexion, chemin):
    """Charge les fiches municipales d'un export, d'un seul bloc; None s'il est déjà en base.

    Retourne (fiches municipales, fiches nouvelles, fiches publiées autrement).
    Une fiche déjà en base n'est pas recopiée : seao.fiche_fichier la relie à cet
    export, avec la version publiée si elle diffère. Un fichier modifié qui garde
    le nom d'un export chargé lève ValueError.
    """
    signature = empreinte(chemin)
    meme_nom = connexion.execute("SELECT empreinte_sha256 FROM seao.fichier_source WHERE nom = %s", (chemin.name,)).fetchone()
    if meme_nom and meme_nom[0] != signature:
        raise ValueError(f"{chemin.name} est déjà en base, mais le fichier a changé depuis. "
                         "Rien n'est chargé : vérifier le fichier, ou relancer avec --reinitialiser.")
    if connexion.execute("SELECT 1 FROM seao.fichier_source WHERE empreinte_sha256 = %s", (signature,)).fetchone():
        return None
    type_fichier, debut, fin = decrire_export(chemin.name)

    with chemin.open(encoding="utf-8-sig") as fichier:
        donnees = json.load(fichier)
    releases = donnees.get("releases", [])
    analyser_seao.validate_identifiers(releases)      # même contrôle que le programme d'analyse
    # Triées par numéro, donc par date : le dernier nom lu est le plus récent.
    municipales = sorted((lignes_de_la_fiche(r) for r in releases if analyser_seao.get_municipal_buyer_party(r)),
                         key=lambda n: n["fiche"]["release_id"])

    fichier_id = connexion.execute(
        "INSERT INTO seao.fichier_source (nom, type, periode_debut, periode_fin, date_publication, empreinte_sha256, nb_fiches) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING fichier_id",
        (chemin.name, type_fichier, debut, fin, instant(donnees.get("publishedDate")), signature, len(releases))).fetchone()[0]

    deja = cles_des_fiches(connexion)
    nouvelles = [n for n in municipales if (n["ocid"], n["fiche"]["release_id"]) not in deja]
    # La version gardée des fiches déjà en base, pour voir si cet export les publie autrement.
    gardees = dict(connexion.execute(
        "SELECT fiche_id, brut FROM seao.fiche WHERE fiche_id = ANY(%s)",
        ([deja[(n["ocid"], n["fiche"]["release_id"])] for n in municipales
          if (n["ocid"], n["fiche"]["release_id"]) in deja],)).fetchall())

    def toutes(cle):
        return [ligne for n in nouvelles for ligne in n[cle]]

    # Listes de codes, fournisseurs et acheteurs d'abord : les fiches s'y réfèrent.
    inserer(connexion, "seao.nomenclature", list({n["code"]: n for n in toutes("nomenclature")}.values()))
    inserer(connexion, "seao.classification",
            list({c["code"]: {"code": c["code"], "libelle": c["libelle"]} for c in toutes("classifications")}.values()))
    charger_fournisseurs(connexion, toutes("fournisseurs"))

    # Les acheteurs : chaque identifiant publié est rattaché à son organisme (voir organisme_de).
    organismes = dict(connexion.execute("SELECT nom, organisme_id FROM organismes.organisme").fetchall())
    connus = dict(connexion.execute("SELECT acheteur_id, organisme_id FROM organismes.acheteur").fetchall())
    acheteurs = {n["acheteur"]["acheteur_id"]: n["acheteur"] for n in nouvelles}
    rattaches = {i: organisme_de(i, a["organisme"], connus, organismes) for i, a in acheteurs.items()}
    with connexion.cursor() as curseur:
        curseur.executemany(
            "INSERT INTO organismes.acheteur (acheteur_id, organisme_id, nom_seao) VALUES (%s, %s, %s) "
            "ON CONFLICT (acheteur_id) DO UPDATE SET nom_seao = EXCLUDED.nom_seao",
            [(i, rattaches[i], a["nom_seao"]) for i, a in acheteurs.items()])

    # Les dossiers, puis les fiches : la base leur donne leur numéro.
    inserer(connexion, "seao.dossier", [{"ocid": o} for o in dict.fromkeys(n["ocid"] for n in nouvelles)])
    dossiers = dict(connexion.execute("SELECT ocid, dossier_id FROM seao.dossier").fetchall())
    inserer(connexion, "seao.fiche", [{"dossier_id": dossiers[n["ocid"]], **n["fiche"]} for n in nouvelles])
    fiches = cles_des_fiches(connexion)

    classifications, soumissionnaires, attributions = [], [], []
    for n in nouvelles:
        fiche_id = fiches[(n["ocid"], n["fiche"]["release_id"])]
        classifications += [{"fiche_id": fiche_id, "code": c["code"], "principale": c["principale"]}
                            for c in n["classifications"]]
        soumissionnaires += [{"fiche_id": fiche_id, "identifiant_fournisseur": i} for i in n["soumissionnaires"]]
        attributions += [{"fiche_id": fiche_id, **a} for a in n["attributions"]]
    inserer(connexion, "seao.fiche_classification", classifications)
    inserer(connexion, "seao.soumissionnaire", soumissionnaires)
    inserer(connexion, "seao.attribution", attributions)

    # Un contrat renvoie à son attribution par le numéro que la base a donné à celle-ci.
    numeros = {(f, numero): a for f, numero, a in connexion.execute(
        "SELECT fiche_id, numero, attribution_id FROM seao.attribution WHERE fiche_id = ANY(%s)",
        ([fiches[(n["ocid"], n["fiche"]["release_id"])] for n in nouvelles],))}
    inserer(connexion, "seao.contrat", [
        {"attribution_id": numeros[(fiches[(n["ocid"], n["fiche"]["release_id"])], c["numero_attribution"])],
         **{k: v for k, v in c.items() if k != "numero_attribution"}}
        for n in nouvelles for c in n["contrats"]])

    # Chaque fiche de l'export est reliée au fichier, avec sa version si elle diffère.
    liens = []
    for n in municipales:
        fiche_id = fiches[(n["ocid"], n["fiche"]["release_id"])]
        autrement = fiche_id in gardees and not meme_contenu(gardees[fiche_id], n["fiche"]["brut"].obj)
        liens.append({"fiche_id": fiche_id, "fichier_id": fichier_id,
                      "version_publiee": n["fiche"]["brut"] if autrement else None})
    inserer(connexion, "seao.fiche_fichier", liens)
    return len(municipales), len(nouvelles), sum(1 for l in liens if l["version_publiee"] is not None)


def ordre_de_chargement(chemin):
    """Les exports se chargent dans l'ordre de leur période, pour que le dernier nom lu soit le plus récent."""
    _, debut, fin = decrire_export(chemin.name)
    return fin, debut, chemin.name


def version_des_regles():
    """L'empreinte d'analyser_seao.py et d'utilitaires.py : elle change dès qu'une règle change."""
    fichiers = [Path(analyser_seao.__file__), Path(analyser_seao.__file__).with_name("utilitaires.py")]
    return "analyser_seao.py " + hashlib.sha256(b"".join(f.read_bytes() for f in fichiers)).hexdigest()[:12]


def classer_fiches(connexion):
    """Classe toutes les fiches en base avec analyse_release, la fonction même qui produit les CSV."""
    version = version_des_regles()
    lignes = []
    for fiche_id, brut in connexion.execute("SELECT fiche_id, brut FROM seao.fiche"):
        ligne = analyser_seao.analyse_release(brut)
        famille = texte(ligne["gestion_actifs_eau"])
        lignes.append({"fiche_id": fiche_id,
                       "nature_transaction": code_de("nature_transaction", ligne["nature_transaction"]),
                       "lie_eau": ligne["lie_eau"] == "oui", "pga_eau": ligne["pga_eau"] == "oui",
                       "gestion_actifs_eau": code_de("gestion_actifs_eau", famille) if famille else None,
                       "version_regles": version, "calcule_le": datetime.now(timezone.utc)})
    inserer(connexion, "analyses.fiche_classee", lignes, "DO UPDATE", ["fiche_id"])
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
    inserer(connexion, "analyses.demarche", [ligne_de_demarche(d, organismes, dossiers, fournisseurs) for d in demarches])
    return len(demarches)


def dossiers_a_classer(connexion):
    """Les dossiers repérés (pga_eau ou gestion_actifs_eau) sans ligne dans demarches.csv."""
    return [ocid for (ocid,) in connexion.execute(
        "SELECT DISTINCT d.ocid FROM analyses.fiche_classee c JOIN seao.fiche f ON f.fiche_id = c.fiche_id "
        "JOIN seao.dossier d ON d.dossier_id = f.dossier_id WHERE (c.pga_eau OR c.gestion_actifs_eau IS NOT NULL) "
        "AND NOT EXISTS (SELECT 1 FROM analyses.demarche m WHERE m.dossier_id = d.dossier_id) ORDER BY d.ocid")]


def fournisseurs_a_regrouper(connexion):
    """Les entreprises du même nom dont une seule a un NEQ : sans doute la même, à vérifier à la main.

    Deux NEQ différents désignent bien deux entreprises : elles ne sont pas proposées.
    """
    colonnes = ("groupe", "fournisseur_id", "identifiants", "nom", "neq", "adresse", "localite", "code_postal",
                "nb_dossiers_retenu", "nb_dossiers_soumissionnaire")
    return [dict(zip(colonnes, ligne)) for ligne in connexion.execute("""
        WITH entreprise AS (
            SELECT f.fournisseur_id, lower(f.nom) AS cle, f.nom, f.neq, f.adresse, f.localite, f.code_postal,
                   string_agg(i.identifiant, ' | ' ORDER BY i.identifiant) AS identifiants
            FROM seao.fournisseur f
            JOIN seao.identifiant_fournisseur i ON i.fournisseur_id = f.fournisseur_id
            GROUP BY f.fournisseur_id),
        groupe AS (
            SELECT cle, dense_rank() OVER (ORDER BY cle) AS numero
            FROM entreprise GROUP BY cle HAVING count(*) > 1 AND count(neq) = 1)
        SELECT g.numero, e.fournisseur_id, e.identifiants, e.nom, e.neq, e.adresse, e.localite, e.code_postal,
               (SELECT count(DISTINCT f.dossier_id) FROM seao.attribution a
                    JOIN seao.fiche f ON f.fiche_id = a.fiche_id
                    JOIN seao.identifiant_fournisseur i ON i.identifiant = a.identifiant_fournisseur
                    WHERE i.fournisseur_id = e.fournisseur_id),
               (SELECT count(DISTINCT f.dossier_id) FROM seao.soumissionnaire s
                    JOIN seao.fiche f ON f.fiche_id = s.fiche_id
                    JOIN seao.identifiant_fournisseur i ON i.identifiant = s.identifiant_fournisseur
                    WHERE i.fournisseur_id = e.fournisseur_id)
        FROM entreprise e JOIN groupe g ON g.cle = e.cle
        ORDER BY g.numero, e.neq IS NULL, e.fournisseur_id""")]


# ---------------------------------------------------------------------------
# Vérifications
# ---------------------------------------------------------------------------

def verifier(connexion):
    """Compare la base aux CSV d'analyser_seao.py, export par export.

    Pour chaque export : mêmes fiches municipales, même somme des montants
    attribués, mêmes dossiers PGA-Eau, même repérage de la gestion des actifs
    en eau. Retourne la liste des écarts; elle doit être vide.
    """
    ecarts = []
    exports = connexion.execute("SELECT fichier_id, nom FROM seao.fichier_source ORDER BY periode_fin, periode_debut").fetchall()
    for fichier_id, nom in exports:
        details_csv = analyser_seao.noms_de_sortie(analyser_seao.DOSSIER_SEAO / nom)[0]
        if not details_csv.exists():
            print(f"  {nom} : {details_csv} absent, comparaison impossible (lancer analyser_seao.py)")
            continue
        with details_csv.open(encoding="utf-8-sig", newline="") as fichier:
            details = list(csv.DictReader(fichier))
        # Les fiches reliées à cet export, même celles qu'un autre export avait déjà apportées.
        lignes = connexion.execute(
            "SELECT d.ocid, f.release_id, c.pga_eau, c.gestion_actifs_eau FROM seao.fiche_fichier ff "
            "JOIN seao.fiche f ON f.fiche_id = ff.fiche_id JOIN seao.dossier d ON d.dossier_id = f.dossier_id "
            "LEFT JOIN analyses.fiche_classee c ON c.fiche_id = f.fiche_id WHERE ff.fichier_id = %s", (fichier_id,)).fetchall()
        en_base = {(o, r) for o, r, _, _ in lignes}
        pga_base = {(o, r) for o, r, pga, _ in lignes if pga}
        gestion_base = {(o, r, g) for o, r, _, g in lignes if g is not None}
        somme_base = connexion.execute(
            "SELECT coalesce(sum(a.montant), 0) FROM seao.attribution a "
            "JOIN seao.fiche_fichier ff ON ff.fiche_id = a.fiche_id WHERE ff.fichier_id = %s", (fichier_id,)).fetchone()[0]
        cles = {(d["ocid"], d["release_id"]) for d in details}
        somme_csv = sum(Decimal(d["montant_attribue"]) for d in details if d["montant_attribue"])
        pga_csv = {(d["ocid"], d["release_id"]) for d in details if d["pga_eau"] == "oui"}
        gestion_csv = {(d["ocid"], d["release_id"], code_de("gestion_actifs_eau", d["gestion_actifs_eau"]))
                       for d in details if d["gestion_actifs_eau"]}
        print(f"  {nom} : {len(en_base)} fiches sur {len(details)} | montants attribués {somme_base:,.2f} $ "
              f"contre {somme_csv:,.2f} $ dans le CSV | PGA-Eau {len(pga_base)} sur {len(pga_csv)} | "
              f"gestion des actifs en eau {len(gestion_base)} sur {len(gestion_csv)}")
        if en_base != cles:
            ecarts.append(f"{nom} : fiches différentes")
        if abs(somme_base - somme_csv) > Decimal("0.01"):
            ecarts.append(f"{nom} : somme des montants différente")
        if pga_base != pga_csv:
            ecarts.append(f"{nom} : dossiers PGA-Eau différents")
        if gestion_base != gestion_csv:
            ecarts.append(f"{nom} : repérage de la gestion des actifs en eau différent")
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
        if connexion.execute("SELECT to_regnamespace('seao')").fetchone()[0] is None:
            connexion.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
            print("Base créée à partir de schema.sql.")
        connexion.commit()

        print("Territoire et organismes...")
        charger_territoire(connexion)
        nb_organismes, nb_acheteurs = charger_organismes(connexion)
        connexion.commit()
        print(f"  {nb_organismes} organismes, {nb_acheteurs} identifiants d'acheteur")

        for chemin in sorted(analyser_seao.DOSSIER_SEAO.glob("*.json"), key=ordre_de_chargement):
            charge = charger_export(connexion, chemin)
            connexion.commit()          # un export entier, ou rien
            print(f"  {chemin.name} : " + ("déjà chargé" if charge is None else
                                            f"{charge[0]} fiches municipales, dont {charge[1]} nouvelles"
                                            + (f" et {charge[2]} publiées autrement qu'avant" if charge[2] else "")))

        print(f"Classement : {classer_fiches(connexion)} fiches ({version_des_regles()})")
        print(f"Démarches : {charger_demarches(connexion)} dossiers classés à la main")
        connexion.commit()

        print("\nVérifications :")
        ecarts = verifier(connexion)
        print("  Aucun écart avec les CSV." if not ecarts else "  ÉCARTS : " + "; ".join(ecarts))
        a_classer = dossiers_a_classer(connexion)
        print(f"  Dossiers liés à la gestion des actifs en eau, à classer dans demarches.csv : {len(a_classer)}"
              + (" (" + ", ".join(a_classer) + ")" if a_classer else ""))
        a_regrouper = fournisseurs_a_regrouper(connexion)
        write_csv(A_REGROUPER_CSV, a_regrouper)
        print(f"  Fournisseurs du même nom, dont un seul a un NEQ, à vérifier : "
              f"{len({l['groupe'] for l in a_regrouper})} groupes ({A_REGROUPER_CSV})")

        print("\nContenu de la base :")
        for table in ("territoire.municipalite", "territoire.mrc", "territoire.indicateur_eau", "organismes.organisme",
                      "organismes.acheteur", "seao.dossier", "seao.fiche", "seao.fiche_fichier", "seao.attribution",
                      "seao.contrat", "seao.fournisseur", "seao.identifiant_fournisseur", "analyses.contrat_courant"):
            print(f"  {table:<28} {connexion.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:>7}")


if __name__ == "__main__":
    main()
