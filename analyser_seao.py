"""
Lit un export JSON du SEAO, garde les fiches dont l'acheteur est municipal et
écrit quatre CSV dans sorties/<export>/ :

  details.csv      une ligne par fiche municipale;
  comparaison.csv  une ligne par organisme;
  a_enrichir.csv   le contexte de chaque organisme : population, région, eau;
  qualite.csv      les points à relire dans la source.

Une fiche (« release ») est l'état d'un dossier au moment de l'export, pas un
nouveau contrat, et aucun montant publié n'est une dépense payée. Les colonnes
type_organisme, nature_transaction, lie_eau, pga_eau et gestion_actifs_eau
viennent de règles à valider.

Les organismes nouveaux sont ajoutés à la fin de contexte_municipalites.csv,
sans toucher aux lignes existantes; completer_contexte.py remplit ensuite les
cases « À compléter ».

Utilisation :
    python analyser_seao.py                                  # export de la semaine du 7 septembre 2026
    python analyser_seao.py mensuel_20260801_20260831.json   # un autre export de donnees_seao/
"""

import csv
import json
import re
import shutil
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from utilitaires import (clean_org_name, clean_text, date_from_release_id, format_money,
                         safe_float, top, valid_date, write_csv)

DOSSIER_SEAO = Path("donnees_seao")
DOSSIER_SORTIES = Path("sorties")

# L'export lu sans argument, et le fichier de contexte, tenu à la main.
JSON_FILE = DOSSIER_SEAO / "hebdo_20260907_20260913.json"
CONTEXT_SOURCE_CSV = Path("contexte_municipalites.csv")
# Ancienne vue, lue une seule fois pour créer le fichier de contexte (voir load_context_source).
ANCIENNE_VUE_CONTEXTE = DOSSIER_SORTIES / "municipalites_a_enrichir.csv"

# Les colonnes que le SEAO ne donne pas : completer_contexte.py ou une saisie à la main les remplit.
CONTEXT_FIELDS = (
    "code_geographique", "population", "classe_taille", "superficie_km2",
    "region_administrative", "mrc", "type_milieu",
    "particularites_infrastructures", "source_contexte", "notes",
)

# Un montant sous 1 000 $ est parfois un prix unitaire : il est signalé, jamais
# retiré. Seuil choisi à l'œil.
SEUIL_PRIX_UNITAIRE = 1000

# Codes UNSPSC des subventions. Trop large : 9315 attrape aussi le mandat
# d'auditeur externe de Bois-des-Filion.
UNSPSC_SUBVENTION = ("9315", "84101501", "99000000")

# Mots liés à l'eau, en plus du mot « eau » que is_water_related cherche à part.
# Ils servent surtout aux titres sans ce mot, comme « aqueduc » ou « égout ».
MOTS_CLES_EAU = [
    "pga-eau", "pga eau", "pga_eau",
    "aqueduc", "égout", "egout", "eau potable", "eaux usées", "eaux usees",
    "eaux pluviales", "pluvial", "assainissement", "usine de filtration",
    "station d'épuration", "réseau d'eau", "borne d'incendie", "bornes d'incendie",
    "borne-fontaine", "bornes-fontaines", "surpression", "pompage",
    "compteur d'eau", "compteurs d'eau", "puits",
]


# ---------------------------------------------------------------------------
# Le type d'organisme
# ---------------------------------------------------------------------------

def org_type(name):
    """Devine le type d'organisme d'après son nom, faute de référentiel ici.

    « MRC » est testé avant « Municipalité », qui figure dans « municipalité
    régionale de comté ». Un nom sans mot repère, comme « Saint-Pie-de-Guire »,
    donne « Autre organisme municipal ».
    """
    n = clean_org_name(name).lower()
    rules = [
        ("Ville", r"^(ville|cité) d"),
        ("MRC", r"^mrc\b|municipalité régionale de comté"),
        ("Municipalité", r"^(la )?municipalité\b|^corporation municipale|^m\. |paroisse|canton|village"),
        ("Régie intermunicipale", r"^régie"),
        ("Société de transport", r"transport"),
        ("Office d'habitation", r"habitation|\bomh\b"),
    ]
    for label, pattern in rules:
        if re.search(pattern, n):
            return label
    return "Autre organisme municipal"


# ---------------------------------------------------------------------------
# Lecture d'une release
# ---------------------------------------------------------------------------

def get_municipal_buyer_party(release):
    """Retourne l'acheteur de la fiche s'il est marqué municipal, sinon None.

    Le marqueur details.municipal du SEAO comprend aussi les MRC, les régies, les
    sociétés de transport et les offices d'habitation.
    """
    for party in release.get("parties", []):
        if "buyer" in party.get("roles", []):
            if clean_text((party.get("details") or {}).get("municipal")) == "1":
                return party
    return None


def get_suppliers(release):
    """Retourne les fournisseurs retenus, sous la forme {identifiant: nom}.

    Ils sont lus dans les attributions : la liste des parties en oublie parfois
    quand un dossier a plusieurs lots. Un fournisseur sans identifiant est laissé
    de côté ici et compté à part dans analyse_release.
    """
    suppliers = {}
    for award in release.get("awards") or []:
        for supplier in award.get("suppliers") or []:
            key = clean_text(supplier.get("id"))
            if key and key not in suppliers:
                suppliers[key] = clean_text(supplier.get("name"))
    return suppliers


def count_suppliers(rows):
    """Compte, pour chaque fournisseur, le nombre de fiches où il apparaît (pas de contrats).

    On découpe la colonne des identifiants, pas celle des noms : « LASALLE | NHC
    INC. » contient lui-même une barre verticale.
    """
    counts = Counter()
    for row in rows:
        counts.update(sorted({sid for sid in row["fournisseurs_ids"].split(" | ") if sid}))
    return counts


def format_suppliers(counter, supplier_names_by_id=None, n=3):
    """Les fournisseurs les plus fréquents : nom, identifiant et nombre de fiches.

    Quand un identifiant a plusieurs noms, on affiche le premier dans l'ordre alphabétique.
    """
    names_by_id = supplier_names_by_id or {}
    labels = []
    for supplier_id, count in counter.most_common(n):
        names = sorted(name for name in names_by_id.get(supplier_id, set()) if name)
        name = names[0] if names else "Nom non renseigné"
        labels.append(f"{name} [{supplier_id}] ({count})")
    return "; ".join(labels)


def validate_identifiers(releases):
    """Lève ValueError si un identifiant manque ou se répète, avant toute écriture.

      - le couple (ocid, id) doit être unique : l'id seul se répète d'un dossier à l'autre;
      - chaque contrat a un identifiant, unique dans sa fiche.
    Un même contrat peut revenir dans une autre fiche du dossier : c'est une
    nouvelle version, pas un contrat de plus.
    """
    seen = set()
    for release in releases:
        key = (clean_text(release.get("ocid")), clean_text(release.get("id")))
        if not all(key):
            raise ValueError(f"Identifiant de fiche incomplet : {key}")
        if key in seen:
            raise ValueError(f"Paire (ocid, release_id) dupliquée : {key}")
        seen.add(key)
        contract_ids = set()
        for contract in release.get("contracts") or []:
            contract_id = clean_text(contract.get("id"))
            if not contract_id or contract_id in contract_ids:
                raise ValueError(f"Identifiant de contrat absent ou dupliqué dans {key} : {contract_id!r}")
            contract_ids.add(contract_id)


def get_amounts(release):
    """Les montants d'une fiche. Aucun n'est une dépense payée.

      montant_attribue        somme des awards[].value.amount;
      montant_attribue_total  somme des awards[].value.totalAmount, dont le sens reste à valider;
      montant_contrat         somme des contracts[].value.amount;
      montant_reference       pour chaque attribution, le montant de son contrat (relié
                              par awardID), sinon le montant attribué.

    Le montant de référence n'oublie pas les attributions sans contrat publié : un
    dossier peut en avoir dix pour un seul contrat. Le montant de l'appel
    d'offres (tender.value) n'est jamais publié pour les acheteurs municipaux.
    """
    # On retrouve le contrat de chaque attribution grâce à son awardID.
    contracts_by_award = {}
    for contract in release.get("contracts") or []:
        contracts_by_award[contract.get("awardID")] = contract

    attribue, attribue_total, contrat, reference = [], [], [], []
    sources = set()

    for award in release.get("awards") or []:
        value = award.get("value") or {}
        a = safe_float(value.get("amount"))
        if a is not None:
            attribue.append(a)
        t = safe_float(value.get("totalAmount"))
        if t is not None:
            attribue_total.append(t)

        contract = contracts_by_award.get(award.get("id"))
        c = safe_float((contract.get("value") or {}).get("amount")) if contract else None
        if c is not None:
            reference.append(c)
            sources.add("contrat")
        elif a is not None:
            reference.append(a)
            sources.add("attribution")

    for contract in release.get("contracts") or []:
        c = safe_float((contract.get("value") or {}).get("amount"))
        if c is not None:
            contrat.append(c)

    def total(values):
        return round(sum(values), 2) if values else None

    return {
        "montant_attribue": total(attribue),
        "montant_attribue_total": total(attribue_total),
        "montant_contrat": total(contrat),
        "montant_reference": total(reference),
        "source_montant": " + ".join(sorted(sources)) if sources else "aucun",
    }


def get_categories(release):
    """Les quatre façons dont une fiche décrit ce qui est acheté.

      categorie_principale  mainProcurementCategory : services, travaux ou biens;
                            absente pour les ventes, les partenariats et « Autres »;
      type_contrat_seao     additionalProcurementCategories : une liste, mais une
                            seule valeur en pratique;
      nomenclature_seao     items.description : malgré son nom, un code de la
                            nomenclature SEAO, comme « C02 - Ouvrages de génie civil »;
      unspsc_*              la classification UNSPSC et ses codes additionnels, qui
                            précisent parfois ce que le titre ne dit pas.
    """
    tender = release.get("tender") or {}
    nomenclature, unspsc_ids, unspsc_labels, extras = [], [], [], []

    for item in tender.get("items") or []:
        if item.get("description"):
            nomenclature.append(clean_text(item["description"]))
        classification = item.get("classification") or {}
        if classification.get("id"):
            unspsc_ids.append(clean_text(classification["id"]))
            unspsc_labels.append(clean_text(classification.get("description")))
        for extra in item.get("additionalClassifications") or []:
            extras.append(f"{clean_text(extra.get('id'))} {clean_text(extra.get('description'))}".strip())

    return {
        "categorie_principale": clean_text(tender.get("mainProcurementCategory")),
        "type_contrat_seao": " | ".join(clean_text(c) for c in tender.get("additionalProcurementCategories") or []),
        "nomenclature_seao": " | ".join(nomenclature),
        "unspsc_id": " | ".join(unspsc_ids),
        "unspsc_libelle": " | ".join(unspsc_labels),
        "unspsc_segment": unspsc_ids[0][:2] if unspsc_ids else "",
        "unspsc_additionnels": " | ".join(extras),
    }


def get_nature(type_contrat, unspsc_id, titre):
    """Classe la fiche : achat, subvention ou contribution, vente d'immeuble ou partenariat.

    Les subventions sont retirées des totaux d'achats, mais leur règle (quelques
    codes UNSPSC, « subvention » ou « contribution financière » dans le titre)
    reste grossière : à valider. Tout le reste est un achat.
    """
    if type_contrat == "Ventes de biens immeubles":
        return "vente d'immeuble"
    if type_contrat == "Partenariat":
        return "partenariat"
    t = titre.lower()
    if unspsc_id.startswith(UNSPSC_SUBVENTION) or "contribution financi" in t or "subvention" in t:
        return "subvention ou contribution"
    return "achat"


def is_water_related(titre, libelles):
    """Vrai si la fiche parle d'eau : un filet large, pas un repérage du PGA-Eau.

    Réagit au mot entier « eau » ou « eaux » (pas à « réseau ») et aux mots de
    MOTS_CLES_EAU, dans le titre ou les classifications. Une classification comme
    « Camion-citerne à eau pour la lutte contre les incendies » suffit.
    """
    # Apostrophe courbe changée en droite, comme dans MOTS_CLES_EAU.
    text = f"{titre} {libelles}".lower().replace("’", "'")
    if re.search(r"\beaux?\b", text):
        return True
    return any(k in text for k in MOTS_CLES_EAU)


def is_pga_eau(titre):
    """Vrai si le titre annonce un plan de gestion des actifs en eau (PGA-Eau).

    Deux formes :
      1. « PGA » puis « eau », quelle que soit la ponctuation : « PGA-EAU », ou
         « PGA – Eau » avec un tiret long, comme à Windsor;
      2. « gestion », « actif » et « eau » dans le même titre, sans l'acronyme,
         comme à Mont-Tremblant.
    « PGA » et « eau » doivent être des mots entiers : « ACCOMPGANEMENT » ne
    compte pas, ni un « plan de gestion des eaux pluviales », faute d'« actif ».
    """
    t = titre.lower().replace("’", "'")
    if re.search(r"\bpga[\W_]*eaux?\b", t):
        return True
    return "gestion" in t and "actif" in t and re.search(r"\beaux?\b", t) is not None


def texte_de_recherche(texte):
    """Le texte en minuscules, sans accents, avec des apostrophes droites : « Égout » devient « egout »."""
    texte = (texte or "").replace("’", "'").replace("ʼ", "'")
    return unicodedata.normalize("NFD", texte).encode("ascii", "ignore").decode().lower()


# Le repérage large de la gestion des actifs en eau. Les mots sont écrits sans accents.
GESTION_ACTIFS = r"gestion (des|d'|de l')\s*actifs?"
MOTS_RESEAUX_EAU = r"aqueduc|egout|eaux? potable|eaux? usee|conduite|pluvial|hydrauli|sanitaire|assainissement|tecq|\beaux?\b"
# Les autres actifs attendront leur propre repérage : bâtiments, routes, véhicules...
MOTS_AUTRES_ACTIFS = r"batiment|immeuble|immobili|vehicule|flotte|tennis|mobilier|transport"
MOTS_ROUTES = r"routier|piirl|pisrmm|pavl|securite routiere"


def gestion_actifs_eau(titre, description=""):
    """Retourne la famille de gestion des actifs en eau d'une fiche, ou une chaîne vide.

    Plus large que is_pga_eau : il propose aussi les démarches voisines, classées
    ensuite à la main dans demarches.csv. Les tests, dans l'ordre :
      - « PGA-Eau » : is_pga_eau sur le titre, ou l'acronyme dans la description;
      - un titre sur un autre actif (bâtiment, véhicule, transport...) est écarté;
      - « outil » : un logiciel, une licence ou une solution de gestion d'actifs;
      - « étape » : une inspection, une auscultation, un portrait ou un inventaire
        fait « dans le cadre » d'un PGA, d'un plan d'intervention ou de gestion;
      - « plan d'intervention » : sur les réseaux d'eau, pas un plan routier (PIIRL);
      - « gestion d'actifs » : un plan de gestion des actifs des infrastructures
        qui ne dit pas « eau », comme celui de Clermont.
    """
    t = texte_de_recherche(titre)
    texte = texte_de_recherche(f"{titre} {description}")
    if is_pga_eau(titre) or re.search(r"\bpga[\W_]*eaux?\b", texte):
        return "PGA-Eau"
    if re.search(MOTS_AUTRES_ACTIFS, t):
        return ""
    if re.search(GESTION_ACTIFS, t) and re.search(r"logiciel|licence|abonnement|solution|plateforme|progiciel", t):
        return "outil"
    if (re.search(r"inspection|auscultation|portrait|inventaire", t)
            and re.search(r"dans le cadre (du|de la|des|d'un|d'une)\b.*(\bpga\b|plans? d'intervention|plans? de gestion|"
                          + GESTION_ACTIFS + ")", texte)):
        return "étape"
    if re.search(r"plans? d'intervention", t) and re.search(MOTS_RESEAUX_EAU, texte) and not re.search(MOTS_ROUTES, t):
        return "plan d'intervention"
    if re.search(GESTION_ACTIFS, t) and re.search(r"infrastructure|ingenierie|\bpti\b|municipa|reseau", t):
        return "gestion d'actifs"
    return ""


def analyse_release(release):
    """Une fiche municipale devient une ligne de details.csv; None si l'acheteur n'est pas municipal.

    Une ligne résume tous les lots, attributions et contrats de la fiche.
    """
    party = get_municipal_buyer_party(release)
    if party is None:
        return None

    tender = release.get("tender") or {}
    buyer = release.get("buyer") or {}
    address = party.get("address") or {}
    awards = release.get("awards") or []
    contracts = release.get("contracts") or []
    bids = release.get("bids") or []          # liste simple propre au SEAO, pas le format OCDS standard
    documents = tender.get("documents") or []

    organisme = clean_org_name(party.get("name"))
    titre = clean_text(tender.get("title"))
    categories = get_categories(release)
    amounts = get_amounts(release)
    suppliers = get_suppliers(release)
    supplier_mentions = [s for award in awards for s in award.get("suppliers") or []]

    # Plusieurs contrats : on garde la première attribution, la première
    # signature et la dernière fin prévue.
    award_dates = [valid_date(a.get("date")) for a in awards]
    signed_dates = [valid_date(c.get("dateSigned")) for c in contracts]
    end_dates = [valid_date((c.get("period") or {}).get("endDate")) for c in contracts]

    # Attributions et contrats publiés sans montant.
    nb_montants_absents = sum(1 for a in awards if safe_float((a.get("value") or {}).get("amount")) is None)
    nb_montants_absents += sum(1 for c in contracts if safe_float((c.get("value") or {}).get("amount")) is None)

    # Deux indices d'un prix unitaire possible. Aucun n'est une preuve : on note
    # la raison, on ne retire aucun montant.
    raisons_montant = []
    if any(clean_text(b.get("valueUnit")) not in ("", "1") for b in bids):
        raisons_montant.append("unité de soumission différente de 1")
    if amounts["montant_reference"] is not None and amounts["montant_reference"] < SEUIL_PRIX_UNITAIRE:
        raisons_montant.append(f"montant de référence inférieur à {SEUIL_PRIX_UNITAIRE} $")

    nature = get_nature(categories["type_contrat_seao"], categories["unspsc_id"], titre)
    lie_eau = is_water_related(titre, categories["unspsc_libelle"] + " " + categories["unspsc_additionnels"])

    row = {
        "organisme": organisme,
        "type_organisme": org_type(organisme),
        "organisme_nom_brut": party.get("name") or "",
        "acheteur_detaille": clean_org_name(buyer.get("name")),
        "buyer_id": clean_text(party.get("id") or buyer.get("id")),
        "localite": clean_text(address.get("locality")),
        "region": clean_text(address.get("region")),
        "code_postal": clean_text(address.get("postalCode")),
        "ocid": clean_text(release.get("ocid")),
        "release_id": clean_text(release.get("id")),
        "date_deduite_id_release": date_from_release_id(release),
        "date_release": valid_date(release.get("date")),
        "date_ouverture_avis": valid_date((tender.get("tenderPeriod") or {}).get("startDate")),
        "date_fermeture_avis": valid_date((tender.get("tenderPeriod") or {}).get("endDate")),
        "date_attribution": min([d for d in award_dates if d], default=""),
        "date_signature": min([d for d in signed_dates if d], default=""),
        "fin_contrat": max([d for d in end_dates if d], default=""),
        "tags": " | ".join(release.get("tag") or []),
        "statut": clean_text(tender.get("status")),
        "titre": titre,
        "methode_code": clean_text(tender.get("procurementMethod")),
        "methode": clean_text(tender.get("procurementMethodDetails")),
        "justification_methode": clean_text(tender.get("procurementMethodRationale")),
        "nature_transaction": nature,
        "lie_eau": "oui" if lie_eau else "non",
        "pga_eau": "oui" if is_pga_eau(titre) else "non",
        "gestion_actifs_eau": gestion_actifs_eau(titre, clean_text(tender.get("description"))),
        # Pour la lecture seulement : les deux colonnes sont triées séparément, le
        # 2e nom n'est pas forcément celui du 2e identifiant.
        "fournisseurs": " | ".join(sorted({clean_text(s.get("name")) for s in supplier_mentions if clean_text(s.get("name"))})),
        "fournisseurs_ids": " | ".join(sorted(suppliers)),
        "nb_identifiants_fournisseurs": len(suppliers),
        "nb_mentions_fournisseur_sans_id": sum(not clean_text(s.get("id")) for s in supplier_mentions),
        "nb_soumissionnaires": len(tender.get("tenderers") or []),
        "nb_soumissions": len(bids),
        "nb_lots": len(tender.get("lots") or []),
        "nb_attributions": len(awards),
        "nb_contrats": len(contracts),
        "nb_contrats_statut_terminated": sum(c.get("status") == "terminated" for c in contracts),
        "ids_contrats": " | ".join(clean_text(c.get("id")) for c in contracts if c.get("id")),
        "montant_a_verifier": "oui" if raisons_montant else "non",
        "raison_montant_a_verifier": " ; ".join(raisons_montant),
        "nb_montants_absents": nb_montants_absents,
        "date_attribution_invalide": "oui" if awards and not all(award_dates) else "non",
        "url_seao": clean_text(documents[0].get("url")) if documents else "",
    }
    row.update(categories)
    row.update(amounts)
    return row


# ---------------------------------------------------------------------------
# Agrégations
# ---------------------------------------------------------------------------

def aggregate_municipalities(rows, supplier_names_by_id=None):
    """Résume les fiches par organisme, une ligne par nom nettoyé.

    Montréal devient ainsi un seul organisme, malgré un identifiant par
    arrondissement ou service. Totaux et médianes ne portent que sur les achats,
    montants à relire compris.
    """
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["organisme"]].append(row)

    summaries = []
    for organisme, items in grouped.items():
        achats = [r for r in items if r["nature_transaction"] == "achat"]
        montants = [r["montant_reference"] for r in achats if r["montant_reference"] is not None]
        subventions = [r["montant_reference"] for r in items
                       if r["nature_transaction"] == "subvention ou contribution" and r["montant_reference"] is not None]

        tags = Counter(t for r in items for t in r["tags"].split(" | ") if t)
        fournisseurs = count_suppliers(items)

        summaries.append({
            "organisme": organisme,
            "type_organisme": items[0]["type_organisme"],
            "buyer_ids": " | ".join(sorted({r["buyer_id"] for r in items if r["buyer_id"]})),
            "nb_sous_unites": len({r["acheteur_detaille"] for r in items}),
            "localites_observees": " | ".join(sorted({r["localite"] for r in items if r["localite"]})),
            "nb_avis": len(items),
            # Étiquette « tender », quelle que soit la date d'ouverture.
            "nb_releases_tag_tender": sum(1 for r in items if "tender" in r["tags"].split(" | ")),
            "nb_avis_en_cours": sum(1 for r in items if r["statut"] == "active"),
            "nb_avis_avec_contrat": sum(1 for r in items if r["nb_contrats"] > 0),
            "nb_contrats": sum(r["nb_contrats"] for r in items),
            # Des fiches. La colonne suivante compte des contrats au statut « terminated ».
            "nb_releases_tag_contractTermination": sum(1 for r in items if "contractTermination" in r["tags"].split(" | ")),
            "nb_contrats_statut_terminated": sum(r["nb_contrats_statut_terminated"] for r in items),
            "nb_annulations": tags["tenderCancellation"],
            "nb_subventions": sum(1 for r in items if r["nature_transaction"] == "subvention ou contribution"),
            "nb_avis_eau": sum(1 for r in items if r["lie_eau"] == "oui"),
            "nb_avis_pga_eau": sum(1 for r in items if r["pga_eau"] == "oui"),
            "nb_identifiants_fournisseurs": len(fournisseurs),
            "nb_achats_avec_montant": len(montants),
            "montant_total_achats": round(sum(montants), 2) if montants else None,
            "montant_median_achats": round(statistics.median(montants), 2) if montants else None,
            "montant_max_achats": max(montants) if montants else None,
            "montant_total_subventions": round(sum(subventions), 2) if subventions else None,
            "part_gre_a_gre_pct": round(100 * sum(1 for r in items if r["methode_code"] == "direct") / len(items)),
            # Achats seulement : une subvention ne dit rien des travaux d'un organisme.
            "types_contrat_frequents": top(Counter(r["type_contrat_seao"] for r in achats)),
            "nomenclatures_frequentes": top(Counter(r["nomenclature_seao"] for r in achats)),
            "unspsc_frequents": top(Counter(r["unspsc_libelle"] for r in achats)),
            "methodes_frequentes": top(Counter(r["methode"] for r in items)),
            "tags_frequents": top(tags),
            "fournisseurs_frequents": format_suppliers(fournisseurs, supplier_names_by_id),
        })

    summaries.sort(key=lambda s: (s["nb_avis"], s["montant_total_achats"] or 0), reverse=True)
    return summaries


def build_context_rows(summaries, rows):
    """Une ligne de contexte par organisme, tout à « À compléter ».

    merge_context_rows y reporte ensuite la saisie. La localité et le code postal
    du SEAO sont repris : ils servent à départager les homonymes.
    """
    by_org = defaultdict(list)
    for row in rows:
        by_org[row["organisme"]].append(row)

    context = []
    for s in summaries:
        items = by_org[s["organisme"]]
        localites = sorted({r["localite"] for r in items if r["localite"]})
        codes = sorted({r["code_postal"] for r in items if r["code_postal"]})
        context.append({
            "organisme": s["organisme"],
            "type_organisme": s["type_organisme"],
            "buyer_ids": s["buyer_ids"],
            "localite_seao": " | ".join(localites),
            "code_postal_seao": " | ".join(codes),
            "adresse_disponible_seao": "oui" if localites or codes else "non",
            "nb_avis_observes": s["nb_avis"],
            "code_geographique": "À compléter",
            "population": "À compléter",
            "classe_taille": "À compléter",
            "superficie_km2": "À compléter",
            "region_administrative": "À compléter",
            "mrc": "À compléter",
            "type_milieu": "À compléter",
            "particularites_infrastructures": "À compléter",
            "source_contexte": "À compléter",
            # Champ libre : vide, il n'y a rien à signaler.
            "notes": "",
        })
    return context


def merge_context_rows(context_rows, source_rows, absents=None):
    """Reporte le contexte saisi sur les organismes de l'export. Dans le doute, lève ValueError.

    La ligne de contexte d'un organisme se cherche dans cet ordre :
      1. les mêmes identifiants d'acheteur, dans n'importe quel ordre;
      2. un identifiant commun et le même nom, avec un avertissement : la liste de
         Montréal change d'un export à l'autre. Un nom différent, ou plusieurs
         lignes visées, arrête tout;
      3. le même nom, si la ligne de contexte n'a aucun identifiant (sinon, erreur);
      4. sinon l'organisme est nouveau : il reste « À compléter » et va dans
         absents, si la liste est fournie (voir append_context_rows).
    Seules les cases remplies sont reportées.
    """
    def buyer_ids(row):
        return frozenset(part.strip() for part in row.get("buyer_ids", "").split(" | ") if part.strip())

    # Un identifiant dans deux lignes, ou un nom sans identifiant répété, rend
    # le rattachement ambigu : on s'arrête.
    by_ids, by_name, owner_by_id = {}, defaultdict(list), {}
    for source in source_rows:
        name = clean_org_name(source.get("organisme"))
        ids = buyer_ids(source)
        if not name:
            raise ValueError("Le contexte contient une ligne sans nom d'organisme.")
        if ids:
            if ids in by_ids or any(sid in owner_by_id for sid in ids):
                raise ValueError(f"Identifiants d'acheteur ambigus dans le contexte : {name}")
            by_ids[ids] = source
            for sid in ids:
                owner_by_id[sid] = source
        elif any(not buyer_ids(other) for other in by_name[name]):
            raise ValueError(f"Nom sans identifiant répété dans le contexte : {name}")
        by_name[name].append(source)

    merged, used_sources, seen_targets = [], set(), set()
    for row in context_rows:
        result = dict(row)
        ids = buyer_ids(row)
        name = clean_org_name(row.get("organisme"))
        key = ("ids", ids) if ids else ("nom", name)
        if key in seen_targets:
            raise ValueError(f"Organisme ambigu dans la vue de contexte : {name}")
        seen_targets.add(key)
        source = by_ids.get(ids) if ids else None
        if source is None:
            candidates = by_name.get(name, [])
            communs = {sid for sid in ids if sid in owner_by_id}
            if communs:
                # Règle 2 : un identifiant commun et le même nom.
                proprietaires = {id(owner_by_id[sid]): owner_by_id[sid] for sid in communs}
                if len(proprietaires) > 1 or len(candidates) > 1:
                    raise ValueError(f"Correspondance de contexte incertaine pour {name}; "
                                     "plusieurs lignes de contexte visent cet organisme.")
                source = next(iter(proprietaires.values()))
                if clean_org_name(source.get("organisme")) != name:
                    raise ValueError(f"Correspondance de contexte incertaine pour {name} : un identifiant "
                                     f"est commun avec « {source.get('organisme')} », mais le nom diffère.")
                anciens = buyer_ids(source)
                print(f"  contexte : liste d'acheteurs modifiée pour {name} "
                      f"({len(anciens)} identifiants enregistrés, {len(ids)} dans cet export)")
            else:
                if len(candidates) > 1 or any(buyer_ids(c) for c in candidates):
                    raise ValueError(f"Correspondance de contexte incertaine pour {name}; vérifier les identifiants.")
                source = candidates[0] if candidates else None
        if source is not None:
            # Une même ligne de contexte ne doit jamais servir à deux organismes.
            if id(source) in used_sources:
                raise ValueError(f"Une ligne de contexte correspond à plusieurs organismes : {name}")
            used_sources.add(id(source))
            for field in CONTEXT_FIELDS:
                value = source.get(field, "")
                if clean_text(value) and clean_text(value) != "À compléter":
                    result[field] = value
        elif absents is not None:
            absents.append(result)
        merged.append(result)
    return merged


def append_context_rows(source_path, rows, dossier_sauvegarde=DOSSIER_SORTIES):
    """Ajoute à la fin du fichier de contexte les organismes nouveaux; retourne leur nombre.

    Le fichier est d'abord copié. Si son début change d'un seul octet, la copie
    est remise en place et ValueError est levée.
    """
    if not rows:
        return 0
    source_path = Path(source_path)
    avant = source_path.read_bytes()
    with source_path.open("r", encoding="utf-8-sig", newline="") as file:
        fields = csv.DictReader(file).fieldnames
    Path(dossier_sauvegarde).mkdir(exist_ok=True)
    sauvegarde = Path(dossier_sauvegarde) / (source_path.name + ".avant_ajout")
    shutil.copy2(source_path, sauvegarde)

    nouvelles = [{field: row.get(field, "") if field in ("organisme", "buyer_ids")
                  else ("À compléter" if field in CONTEXT_FIELDS and field != "notes" else "")
                  for field in fields} for row in rows]
    # Pas « utf-8-sig » en ajout : le BOM se retrouverait au milieu du fichier.
    with source_path.open("a", encoding="utf-8", newline="") as file:
        if avant and not avant.endswith(b"\n"):
            file.write("\r\n")
        csv.DictWriter(file, fieldnames=fields).writerows(nouvelles)

    if not source_path.read_bytes().startswith(avant):
        shutil.copy2(sauvegarde, source_path)
        raise ValueError("Le début du fichier de contexte a changé : ajout annulé, ancien fichier restauré.")
    return len(nouvelles)


def load_context_source(source_path, generated_path, context_rows):
    """Retourne les lignes du fichier de contexte, sans jamais le réécrire.

    Leur rattachement aux organismes de l'export est vérifié (merge_context_rows).
    S'il n'existe pas, le fichier est créé une seule fois : à partir de l'ancienne
    vue generated_path si elle existe (lignes et colonnes ajoutées à la main
    comprises), sinon à partir de context_rows.
    """
    def read_rows(path):
        with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fields = reader.fieldnames or []
            if not {"organisme", "buyer_ids"}.issubset(fields):
                raise ValueError(f"Colonnes organisme et buyer_ids requises dans {path}")
            rows = list(reader)
            # Trop ou trop peu de cellules : une virgule de trop dans une saisie, par exemple.
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError(f"Ligne CSV incomplète ou mal délimitée dans {path}")
            return rows, fields

    source_path, generated_path = Path(source_path), Path(generated_path)
    if source_path.exists():
        source_rows, _ = read_rows(source_path)
        merge_context_rows(context_rows, source_rows)
        return source_rows

    if generated_path.exists():
        previous_rows, previous_fields = read_rows(generated_path)
    else:
        previous_rows = context_rows
        previous_fields = list(context_rows[0]) if context_rows else []

    fields = ["organisme", "buyer_ids", *CONTEXT_FIELDS]
    generated_fields = {"organisme", "type_organisme", "buyer_ids", "localite_seao",
                        "code_postal_seao", "adresse_disponible_seao", "nb_avis_observes", *CONTEXT_FIELDS}
    fields.extend(field for field in previous_fields if field not in generated_fields)
    source_rows = [{field: row.get(field, "À compléter" if field in CONTEXT_FIELDS else "")
                    for field in fields} for row in previous_rows]
    # Vérifié avant d'écrire : en cas d'ambiguïté, rien n'est créé.
    merge_context_rows(context_rows, source_rows)
    # Le mode « x » refuse d'écraser un fichier apparu entre-temps.
    with source_path.open("x", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(source_rows)
    return source_rows


def build_quality_rows(rows, supplier_names_by_id):
    """Les points à relire, avec le lien vers l'avis. Un signalement n'est pas une erreur.

    Une fiche peut être signalée plusieurs fois. Un avis sans attribution n'est
    pas signalé pour son absence de montant.
    """
    issues = []

    def add(row, probleme, detail=""):
        issues.append({
            "organisme": row["organisme"],
            "ocid": row["ocid"],
            "release_id": row["release_id"],
            "tags": row["tags"],
            "titre": row["titre"],
            "probleme": probleme,
            "detail": detail,
            "url_seao": row["url_seao"],
        })

    for row in rows:
        if row["nb_mentions_fournisseur_sans_id"]:
            add(row, "Fournisseur mentionné sans identifiant",
                f"{row['nb_mentions_fournisseur_sans_id']} mention(s); exclues du décompte des identifiants")
        if row["organisme_nom_brut"] != row["organisme"]:
            add(row, "Nom d'organisme avec ponctuation ou espaces superflus", repr(row["organisme_nom_brut"]))

        if row["acheteur_detaille"] != row["organisme"]:
            add(row, "Acheteur détaillé différent de l'organisme (sous-unité)", row["acheteur_detaille"])

        if not row["nomenclature_seao"] and not row["unspsc_id"]:
            add(row, "Aucun item ni classification")

        if row["nb_attributions"] > 0 and row["nb_contrats"] == 0:
            add(row, "Attribution sans contrat publié", f"{row['nb_attributions']} attribution(s), statut {row['statut']}")

        if 0 < row["nb_contrats"] < row["nb_attributions"]:
            add(row, "Moins de contrats que d'attributions",
                f"{row['nb_attributions']} attributions, {row['nb_contrats']} contrat(s)")

        a, c = row["montant_attribue"], row["montant_contrat"]
        if row["nb_attributions"] == row["nb_contrats"] and a is not None and c is not None and abs(a - c) > 0.01:
            add(row, "Montant du contrat différent du montant attribué",
                f"attribué {format_money(a)} ; contrat {format_money(c)}")

        t = row["montant_attribue_total"]
        if t is not None and a is not None and abs(t - a) > 0.01:
            add(row, "Montant total d'attribution (totalAmount) différent du montant attribué",
                f"attribué {format_money(a)} ; total {format_money(t)}")

        if row["nb_montants_absents"]:
            add(row, "Montant absent alors qu'une attribution ou un contrat existe",
                f"{row['nb_montants_absents']} valeur(s) sans montant")

        if row["montant_a_verifier"] == "oui":
            add(row, "Montant à relire avant de l'additionner",
                f"{row['raison_montant_a_verifier']}; montant de référence "
                f"{format_money(row['montant_reference'])}")

        if row["date_attribution_invalide"] == "oui":
            add(row, "Date d'attribution absente ou invalide")

        for supplier_id in row["fournisseurs_ids"].split(" | "):
            names = supplier_names_by_id.get(supplier_id, set())
            if len(names) > 1:
                add(row, "Variantes de nom pour un même fournisseur", " / ".join(sorted(names)))
                break                             # un signalement par fiche suffit

    return issues


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

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


def main():
    """Analyse un export et écrit les quatre CSV. Rien n'est écrit avant la fin des vérifications."""
    fichier_json = trouver_fichier_json(sys.argv[1]) if len(sys.argv) > 1 else JSON_FILE
    details_csv, summary_csv, context_csv, quality_csv = noms_de_sortie(fichier_json)
    DOSSIER_SORTIES.mkdir(exist_ok=True)

    json_path = Path(fichier_json)
    if not json_path.exists():
        print(f"Erreur : fichier introuvable : {fichier_json}")
        return

    print(f"Lecture de {fichier_json}...")
    with json_path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)

    releases = data.get("releases", [])
    print(f"Nombre total de releases : {len(releases)}")
    # Un doublon d'identifiant arrête tout : mieux vaut une erreur qu'un total faux.
    validate_identifiers(releases)

    details = []
    supplier_names_by_id = defaultdict(set)

    for release in releases:
        row = analyse_release(release)
        if row is None:
            continue
        details.append(row)
        for supplier_id, name in get_suppliers(release).items():
            supplier_names_by_id[supplier_id].add(name)

    summaries = aggregate_municipalities(details, supplier_names_by_id)
    context_rows = build_context_rows(summaries, details)
    quality_rows = build_quality_rows(details, supplier_names_by_id)
    context_source = load_context_source(CONTEXT_SOURCE_CSV, ANCIENNE_VUE_CONTEXTE, context_rows)
    nouveaux = []
    context_rows = merge_context_rows(context_rows, context_source, absents=nouveaux)

    # Les vérifications ont réussi : on peut écrire.
    ajoutes = append_context_rows(CONTEXT_SOURCE_CSV, nouveaux)
    details_csv.parent.mkdir(exist_ok=True)
    write_csv(details_csv, details)
    write_csv(summary_csv, summaries)
    write_csv(context_csv, context_rows)
    write_csv(quality_csv, quality_rows)

    print(f"Releases municipales retenues : {len(details)}")
    print(f"Organismes municipaux distincts : {len(summaries)}")
    print(f"Points à vérifier : {len(quality_rows)}")
    print("\nQuatre CSV de sortie :")
    for path in (details_csv, summary_csv, context_csv, quality_csv):
        print(f"- {path}")
    print(f"Contexte à saisir dans {CONTEXT_SOURCE_CSV} : {ajoutes} nouvel(s) organisme(s) ajouté(s) "
          "à la fin, lignes existantes inchangées.")


if __name__ == "__main__":
    main()
