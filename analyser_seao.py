"""
Premier portrait de l'activité contractuelle municipale, à partir d'un export du SEAO.

Projet IFT3150 de Nizar Lakhder, Université de Montréal, automne 2026.
Supervision : Louis-Édouard Lafontant. Partenaire : CERIU, Jérémy Diaz.

L'idée est simple : avant de construire un baromètre, il faut comprendre ce
que les données disent vraiment. Ce programme lit un export JSON du SEAO, ne
garde que les fiches dont l'acheteur est municipal, et les met à plat dans
quatre tableaux :

  1. le détail          : une ligne par fiche municipale;
  2. la comparaison     : une ligne par organisme;
  3. le contexte        : ce qu'on sait de chaque organisme (population,
                          région, état du réseau d'eau) et ce qui manque;
  4. la qualité         : les points à relire dans la source.

Un mot de vocabulaire, pour éviter le contresens le plus fréquent. Le SEAO
publie des « releases », qu'on appelle ici des fiches. Une fiche est l'état
d'un dossier au moment de l'export : un avis, une attribution, un contrat, ou
la simple mise à jour d'un dossier ancien. Une fiche n'est donc pas un nouveau
contrat. Dans l'export de la semaine du 7 au 13 septembre 2026, seulement 403
des 1 561 fiches municipales portent sur un avis ouvert cette semaine-là; la
plus ancienne remonte à 2013.

Deux prudences à garder en tête en lisant les résultats :
  - aucun montant publié n'est une dépense payée;
  - trois classements sont des propositions à valider avec le CERIU : le
    repérage des dossiers liés à l'eau, celui des subventions, et le type
    d'organisme deviné à partir du nom.

Utilisation :
    python analyser_seao.py                                  # export de la semaine
    python analyser_seao.py mensuel_20260801_20260831.json   # un autre export

Sans argument, les sorties gardent leurs noms habituels, ceux vers lesquels
pointe le rapport destiné au CERIU. Avec un autre export, elles portent le nom
de la période, pour que deux périodes puissent coexister dans sorties/.

Le contexte municipal vit dans contexte_municipalites.csv. Ce programme le crée
au premier lancement, puis se contente de le lire. Seul completer_contexte.py y
ajoute des valeurs, et uniquement dans les cases encore « À compléter ».
Le rapport pour le CERIU s'écrit à la main : ce programme n'en génère aucun.
"""

import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Les fichiers sont rangés selon leur rôle : les exports bruts du SEAO d'un
# côté, ce que le programme produit de l'autre. Seul le fichier de contexte
# reste à la racine, parce que c'est le seul qu'on remplit à la main.
DOSSIER_SEAO = Path("donnees_seao")
DOSSIER_SORTIES = Path("sorties")

# L'export analysé quand on ne donne aucun argument, et ses quatre sorties.
# Ces noms datent d'avant le renommage du script (analyse_municipalites.py);
# on les garde parce que d'autres documents renvoient vers eux.
JSON_FILE = DOSSIER_SEAO / "hebdo_20260907_20260913.json"
DETAILS_CSV = DOSSIER_SORTIES / "analyse_municipalites_details.csv"
SUMMARY_CSV = DOSSIER_SORTIES / "comparaison_municipalites.csv"
CONTEXT_CSV = DOSSIER_SORTIES / "municipalites_a_enrichir.csv"
CONTEXT_SOURCE_CSV = Path("contexte_municipalites.csv")
QUALITY_CSV = DOSSIER_SORTIES / "qualite_donnees.csv"

# Les colonnes de contexte. Le SEAO n'en fournit aucune : elles se remplissent
# à la main ou avec completer_contexte.py.
CONTEXT_FIELDS = (
    "code_geographique", "population", "classe_taille", "superficie_km2",
    "region_administrative", "mrc", "proximite_fleuve_lac_riviere", "type_milieu",
    "particularites_infrastructures", "source_contexte", "notes",
)

# Sous 1 000 $, un montant mérite qu'on le relise avant de l'additionner : c'est
# parfois un prix à l'unité plutôt qu'un total. Le seuil est choisi à l'œil;
# il sert à signaler un montant, jamais à le retirer.
SEUIL_PRIX_UNITAIRE = 1000

# Codes UNSPSC qui servent à repérer les subventions. C'est un premier filtre,
# encore trop large : le préfixe 9315 attrape aussi des services financiers,
# comme un mandat d'auditeur externe à Bois-des-Filion.
UNSPSC_SUBVENTION = ("9315", "84101501", "99000000")

# Mots qui signalent un dossier lié à l'eau. Le mot « eau » lui-même n'est pas
# dans la liste : is_water_related le cherche à part, comme mot entier. Du coup,
# certaines entrées (« pga-eau », « eaux usées »...) ne changent rien au
# résultat; la liste compte surtout pour les titres qui n'emploient pas le mot
# « eau », comme « aqueduc » ou « égout ».
# Attention : lié à l'eau ne veut pas dire PGA-Eau (voir is_water_related).
MOTS_CLES_EAU = [
    "pga-eau", "pga eau", "pga_eau",
    "aqueduc", "égout", "egout", "eau potable", "eaux usées", "eaux usees",
    "eaux pluviales", "pluvial", "assainissement", "usine de filtration",
    "station d'épuration", "réseau d'eau", "borne d'incendie", "bornes d'incendie",
    "borne-fontaine", "bornes-fontaines", "surpression", "pompage",
    "compteur d'eau", "compteurs d'eau", "puits",
]


# ---------------------------------------------------------------------------
# Petites fonctions utilitaires
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


def org_type(name):
    """Devine le type d'organisme à partir de son seul nom.

    C'est une devinette assumée : on n'a pas de référentiel ici. « MRC » est
    testé avant « Municipalité », sinon une municipalité régionale de comté
    serait prise pour une municipalité. Un nom sans mot repère, comme
    « Saint-Pie-de-Guire », finit dans « Autre organisme municipal » : ce
    classement est à relire.
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


def top(counter, n=3):
    """Résume les valeurs les plus fréquentes sous la forme « a (12); b (5); c (2) »."""
    return "; ".join(f"{k} ({v})" for k, v in counter.most_common(n) if k)


# ---------------------------------------------------------------------------
# Lecture d'une release
# ---------------------------------------------------------------------------

def get_municipal_buyer_party(release):
    """Retourne l'acheteur de la fiche s'il est municipal, sinon None.

    On se fie au champ details.municipal du SEAO plutôt qu'au nom : c'est plus
    sûr que de deviner. Dans l'export de la semaine, les 3 890 fiches ont
    chacune un acheteur, marqué « 0 » ou « 1 ». Attention, « municipal » au
    sens du SEAO est large : il comprend aussi les MRC, les régies, les
    sociétés de transport et les offices d'habitation.
    """
    for party in release.get("parties", []):
        if "buyer" in party.get("roles", []):
            if clean_text((party.get("details") or {}).get("municipal")) == "1":
                return party
    return None


def get_suppliers(release):
    """Retourne les fournisseurs retenus, sous la forme {identifiant: nom}.

    On les lit dans les attributions plutôt que dans la liste des parties, qui
    oublie parfois des fournisseurs quand un dossier a plusieurs lots.
    L'identifiant permet de reconnaître un fournisseur même quand son nom
    change d'une fiche à l'autre; le nom ne sert qu'à l'affichage. Un
    fournisseur sans identifiant est compté à part (voir analyse_release) :
    on ne fabrique pas d'identifiant à partir de son nom.
    """
    suppliers = {}
    for award in release.get("awards") or []:
        for supplier in award.get("suppliers") or []:
            key = clean_text(supplier.get("id"))
            if key and key not in suppliers:
                suppliers[key] = clean_text(supplier.get("name"))
    return suppliers


def count_suppliers(rows):
    """Compte, pour chaque fournisseur, le nombre de fiches où il apparaît.

    Un fournisseur présent dans trois lots d'une même fiche compte une fois.
    On découpe la colonne des identifiants, jamais celle des noms : un nom
    comme « LASALLE | NHC INC. » contient lui-même une barre verticale et
    serait coupé en deux. Le résultat est un nombre de fiches, pas de contrats.
    """
    counts = Counter()
    for row in rows:
        counts.update(sorted({sid for sid in row["fournisseurs_ids"].split(" | ") if sid}))
    return counts


def format_suppliers(counter, supplier_names_by_id=None, n=3):
    """Affiche les fournisseurs les plus fréquents : nom, identifiant, nombre de fiches.

    Quand un fournisseur a plusieurs écritures de son nom, on affiche la
    première dans l'ordre alphabétique.
    """
    names_by_id = supplier_names_by_id or {}
    labels = []
    for supplier_id, count in counter.most_common(n):
        names = sorted(name for name in names_by_id.get(supplier_id, set()) if name)
        name = names[0] if names else "Nom non renseigné"
        labels.append(f"{name} [{supplier_id}] ({count})")
    return "; ".join(labels)


def validate_identifiers(releases):
    """Vérifie les identifiants avant d'écrire quoi que ce soit.

    Si quelque chose cloche, le programme s'arrête, plutôt que de supprimer ou
    de fusionner des fiches en silence. Deux règles :
      - le couple (ocid, identifiant de fiche) doit être unique dans l'export,
        car l'identifiant de fiche seul peut se répéter d'un dossier à l'autre;
      - chaque contrat doit avoir un identifiant, sans doublon dans sa fiche.

    En revanche, un même contrat peut revenir dans une autre fiche du même
    dossier : c'est une nouvelle version, pas un nouveau contrat à additionner.
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
    """Calcule les montants d'une fiche. Aucun n'est une dépense payée.

      montant_attribue       : la somme des montants au moment de l'attribution
                               (awards[].value.amount);
      montant_attribue_total : la somme des totalAmount des attributions, qui
                               diffère parfois du montant attribué; son sens
                               reste à valider;
      montant_contrat        : la somme des montants inscrits aux contrats
                               (contracts[].value.amount), dont le sens exact
                               reste lui aussi à confirmer;
      montant_reference      : notre convention de calcul. Pour chaque
                               attribution, on prend le montant du contrat lié
                               s'il existe, sinon le montant attribué.

    Pourquoi un montant de référence? Parce qu'un dossier peut avoir dix
    attributions et un seul contrat publié : additionner les seuls contrats
    ferait oublier neuf attributions. Le lien entre les deux passe par awardID.
    Si un montant manque des deux côtés, le total reste partiel.

    Dans les données étudiées, chaque contrat a son attribution, et aucun
    awardID n'a plus d'un contrat. Le montant de l'appel d'offres lui-même
    (tender.value, tender.minValue) n'est jamais publié pour les acheteurs
    municipaux : on ne s'en sert donc pas.
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
    """Rassemble les quatre façons dont une fiche décrit ce qui est acheté.

      categorie_principale : services, travaux ou biens (mainProcurementCategory).
                             Absente pour les ventes, les partenariats et
                             la catégorie « Autres »;
      type_contrat_seao    : le type de contrat SEAO. Le champ est une liste
                             (additionalProcurementCategories), mais il
                             contient en pratique une seule valeur parmi sept;
      nomenclature_seao    : un code de la nomenclature SEAO, comme
                             « C02 - Ouvrages de génie civil ». Malgré le nom
                             du champ (items.description), ce n'est pas un
                             texte libre;
      unspsc_*             : la classification UNSPSC, beaucoup plus fine, et
                             ses classifications additionnelles. On garde ces
                             dernières, car elles précisent parfois ce que le
                             titre ne dit pas.

    Pour donner une idée : 45 codes de nomenclature et 590 codes UNSPSC dans
    l'export de la semaine, 51 et 1 512 dans celui d'août. Dans l'export de la
    semaine, toutes les fiches municipales ont zéro ou un item.
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
    """Classe la fiche : achat, subvention, vente d'immeuble ou partenariat.

    Ce classement a des conséquences, car les subventions sont retirées des
    totaux d'achats. Or la règle des subventions est encore grossière : elle
    repose sur quelques codes UNSPSC et sur les mots « subvention » ou
    « contribution financière » dans le titre, et elle classe à tort le mandat
    d'auditeur externe de Bois-des-Filion. À valider avant de se servir des
    totaux comme indicateurs. Tout ce qui n'entre dans aucune case est un achat.
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
    """Repère les fiches qui parlent d'eau, pour savoir quoi lire en priorité.

    C'est un filet large, pas une détection du PGA-Eau. Il réagit au mot « eau »
    pris comme mot entier (pour ne pas attraper « réseau »), ou à un mot de
    MOTS_CLES_EAU, dans le titre comme dans les classifications. Une simple
    classification comme « Condenseur refroidi à l'eau » suffit donc.

    Il marque 178 fiches dans l'export de la semaine et 749 dans celui d'août.
    Les quatre dossiers PGA-Eau d'août en font partie, mais noyés dans le reste.
    Reconnaître un vrai PGA-Eau demande une règle plus précise, qui n'est pas
    encore dans ce programme.
    """
    # L'apostrophe typographique devient une apostrophe droite, pour que
    # « station d’épuration » corresponde bien à la liste de mots-clés.
    text = f"{titre} {libelles}".lower().replace("’", "'")
    if re.search(r"\beaux?\b", text):
        return True
    return any(k in text for k in MOTS_CLES_EAU)


def analyse_release(release):
    """Transforme une fiche municipale en une ligne du tableau détaillé.

    Retourne None si l'acheteur n'est pas municipal. Une ligne peut résumer
    plusieurs lots, attributions ou contrats : pour le détail de chacun, il
    faut revenir au JSON, ou suivre le lien url_seao vers l'avis.
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

    # Une fiche peut contenir plusieurs contrats. La ligne garde la première date
    # d'attribution, la première signature et la dernière fin de contrat.
    # Attention : une date de fin ne prouve pas que les travaux ont été faits.
    award_dates = [valid_date(a.get("date")) for a in awards]
    signed_dates = [valid_date(c.get("dateSigned")) for c in contracts]
    end_dates = [valid_date((c.get("period") or {}).get("endDate")) for c in contracts]

    # Attributions et contrats publiés sans montant.
    nb_montants_absents = sum(1 for a in awards if safe_float((a.get("value") or {}).get("amount")) is None)
    nb_montants_absents += sum(1 for c in contracts if safe_float((c.get("value") or {}).get("amount")) is None)

    # Deux indices font qu'un montant mérite d'être relu avant d'être additionné.
    # Aucun ne prouve que le montant est unitaire : souvent, la soumission est
    # à l'unité alors que le contrat porte bien un total. On note donc la raison
    # du signalement, et on ne retire aucun montant.
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
        # Ces noms servent à la lecture, jamais au calcul. Les deux colonnes sont
        # triées chacune de leur côté : le 2e nom ne correspond pas forcément au
        # 2e identifiant. Le lien exact nom-identifiant reste dans le JSON.
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

    Regrouper par nom a une conséquence visible : la Ville de Montréal devient
    un seul organisme, alors qu'elle publie sous un identifiant par
    arrondissement ou service (31 dans l'export de la semaine, 36 dans celui
    d'août). Ce choix reste à discuter.

    Les totaux et médianes ne portent que sur les achats. Les montants à relire
    y restent : on les signale, on ne les retire pas. Les colonnes
    « fréquents » disent ce qui revient souvent dans cet export, pas une
    habitude démontrée dans le temps.
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
            # Fiches que le SEAO étiquette « tender », sans regarder leur date
            # d'ouverture.
            "nb_releases_tag_tender": sum(1 for r in items if "tender" in r["tags"].split(" | ")),
            "nb_avis_en_cours": sum(1 for r in items if r["statut"] == "active"),
            "nb_avis_avec_contrat": sum(1 for r in items if r["nb_contrats"] > 0),
            "nb_contrats": sum(r["nb_contrats"] for r in items),
            # Fiches étiquetées « contractTermination ». À ne pas confondre avec
            # la colonne suivante, qui compte les contrats dont le statut actuel
            # est « terminated » : une fiche peut en contenir plusieurs.
            "nb_releases_tag_contractTermination": sum(1 for r in items if "contractTermination" in r["tags"].split(" | ")),
            "nb_contrats_statut_terminated": sum(r["nb_contrats_statut_terminated"] for r in items),
            "nb_annulations": tags["tenderCancellation"],
            "nb_subventions": sum(1 for r in items if r["nature_transaction"] == "subvention ou contribution"),
            "nb_avis_eau": sum(1 for r in items if r["lie_eau"] == "oui"),
            "nb_identifiants_fournisseurs": len(fournisseurs),
            "nb_achats_avec_montant": len(montants),
            "montant_total_achats": round(sum(montants), 2) if montants else None,
            "montant_median_achats": round(statistics.median(montants), 2) if montants else None,
            "montant_max_achats": max(montants) if montants else None,
            "montant_total_subventions": round(sum(subventions), 2) if subventions else None,
            "part_gre_a_gre_pct": round(100 * sum(1 for r in items if r["methode_code"] == "direct") / len(items)),
            # Les catégories fréquentes ne regardent que les achats : une
            # subvention ne dit rien du type de travaux d'un organisme.
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
    """Prépare la vue de contexte : une ligne par organisme, tout à « À compléter ».

    On n'invente rien ici. C'est merge_context_rows qui y reporte ensuite ce
    qui a été saisi dans contexte_municipalites.csv. La localité et le code
    postal du SEAO sont repris, parce qu'ils aident à départager deux
    municipalités qui portent le même nom.
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
            "proximite_fleuve_lac_riviere": "À compléter",
            "type_milieu": "À compléter",
            "particularites_infrastructures": "À compléter",
            "source_contexte": "À compléter",
            "notes": "À compléter",
        })
    return context


def merge_context_rows(context_rows, source_rows):
    """Reporte le contexte saisi à la main sur les organismes de l'export.

    Le principe : ne jamais rattacher une ligne de contexte au mauvais
    organisme. Dans le doute, le programme s'arrête et demande de vérifier.

    Pour chaque organisme, on cherche sa ligne de contexte dans cet ordre :
      1. les mêmes identifiants d'acheteur, peu importe leur ordre;
      2. sinon, au moins un identifiant en commun. On accepte en prévenant,
         et le nom n'est pas comparé. C'est le cas de la Ville de Montréal,
         dont la liste d'identifiants change d'un export à l'autre (31 dans
         celui de la semaine, 36 dans celui d'août). Si ces identifiants
         mènent à plusieurs lignes, on refuse;
      3. sinon, le même nom, mais seulement si la ligne de contexte n'a aucun
         identifiant. Si elle en a d'autres, on refuse : ce pourrait être un
         autre organisme qui porte le même nom;
      4. sinon, l'organisme est nouveau et ses cases restent « À compléter ».

    Seules les cases remplies sont reportées : une valeur saisie n'est jamais
    remplacée par « À compléter ». Ce lien est technique; ce n'est ni un code
    municipal officiel ni une règle de fusion d'organismes.
    """
    def buyer_ids(row):
        return frozenset(part.strip() for part in row.get("buyer_ids", "").split(" | ") if part.strip())

    # D'abord, on indexe les lignes de contexte. Un identifiant qui apparaît
    # dans deux lignes, ou un même nom sans identifiant répété, rendrait le
    # rattachement ambigu : on s'arrête tout de suite.
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
                # Au moins un identifiant en commun : on retient cette ligne en
                # prévenant, car la liste des acheteurs a changé depuis la saisie.
                proprietaires = {id(owner_by_id[sid]): owner_by_id[sid] for sid in communs}
                if len(proprietaires) > 1 or len(candidates) > 1:
                    raise ValueError(f"Correspondance de contexte incertaine pour {name}; "
                                     "plusieurs lignes de contexte visent cet organisme.")
                source = next(iter(proprietaires.values()))
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
        merged.append(result)
    return merged


def load_context_source(source_path, generated_path, context_rows):
    """Retourne les lignes du fichier de contexte, en le créant s'il n'existe pas.

    S'il existe, on le lit sans jamais le réécrire. On vérifie seulement qu'il
    se rattache sans ambiguïté aux organismes de l'export.

    S'il n'existe pas encore, on le crée, une seule fois. On repart alors de
    l'ancienne vue générée (generated_path) si elle existe, pour ne perdre
    aucune saisie faite avant que ce fichier existe : les lignes d'organismes
    absents de l'export courant sont gardées, tout comme les colonnes
    ajoutées à la main. Sinon, on part d'une vue vierge.
    """
    def read_rows(path):
        with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fields = reader.fieldnames or []
            if not {"organisme", "buyer_ids"}.issubset(fields):
                raise ValueError(f"Colonnes organisme et buyer_ids requises dans {path}")
            rows = list(reader)
            # Une ligne avec trop ou trop peu de cellules trahit un CSV abîmé,
            # par exemple une virgule de trop dans une saisie sans guillemets.
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
    # On vérifie le rattachement avant de créer le fichier : en cas
    # d'ambiguïté, rien n'est écrit.
    merge_context_rows(context_rows, source_rows)
    # Le mode « x » refuse d'écrire si le fichier est apparu entre-temps :
    # impossible d'écraser une saisie par accident.
    with source_path.open("x", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(source_rows)
    return source_rows


def build_quality_rows(rows, supplier_names_by_id):
    """Dresse la liste des points à relire, avec le lien vers chaque avis.

    Une même fiche peut être signalée plusieurs fois. Un signalement n'est pas
    une erreur : un nom avec un point final ou une sous-unité de Montréal sont
    normaux, il vaut juste mieux les connaître avant de compter. Un avis encore
    sans attribution n'est pas signalé pour son absence de montant : à ce
    stade, il est normal qu'il n'y en ait pas.
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
# Écriture des fichiers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def trouver_fichier_json(nom):
    """Accepte un chemin complet, ou seulement le nom d'un export rangé dans donnees_seao/.

    Si le fichier est introuvable, on retourne le nom tel quel : main()
    affichera l'erreur.
    """
    chemin = Path(nom)
    if chemin.exists():
        return chemin
    dans_le_dossier = DOSSIER_SEAO / chemin.name
    return dans_le_dossier if dans_le_dossier.exists() else chemin


def noms_de_sortie(fichier_json):
    """Choisit les noms des quatre CSV selon l'export analysé.

    Pour l'export de la semaine, on garde les noms habituels, vers lesquels
    d'autres documents renvoient. Pour tout autre export, les sorties
    prennent le nom de la période, par exemple
    details_mensuel_20260801_20260831.csv : deux périodes peuvent ainsi
    coexister sans que l'une écrase l'autre.
    """
    if Path(fichier_json) == JSON_FILE:
        return DETAILS_CSV, SUMMARY_CSV, CONTEXT_CSV, QUALITY_CSV
    periode = Path(fichier_json).stem
    return (DOSSIER_SORTIES / f"details_{periode}.csv",
            DOSSIER_SORTIES / f"comparaison_{periode}.csv",
            DOSSIER_SORTIES / f"a_enrichir_{periode}.csv",
            DOSSIER_SORTIES / f"qualite_{periode}.csv")


def main():
    """Analyse un export du SEAO et écrit les quatre CSV.

    Les étapes : lire le JSON, vérifier les identifiants, garder les fiches
    municipales, résumer par organisme, préparer le contexte et la liste des
    points à relire, puis écrire. Aucune sortie n'est écrite tant que les
    vérifications n'ont pas réussi.

    L'export à analyser peut être donné en argument; sans argument, c'est
    celui de la semaine du 7 au 13 septembre. Les autres fonctions peuvent
    aussi s'utiliser seules, en mémoire, comme le font les tests.
    """
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
    # Au moindre doublon d'identifiant, on s'arrête : mieux vaut une erreur
    # qu'un total faux.
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
    context_source = load_context_source(CONTEXT_SOURCE_CSV, CONTEXT_CSV, context_rows)
    context_rows = merge_context_rows(context_rows, context_source)

    # Toutes les vérifications ont réussi. À partir d'ici, on n'écrit plus que
    # dans sorties/; le fichier de contexte n'est plus touché.
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
    print(f"Contexte à saisir dans {CONTEXT_SOURCE_CSV} (lu sans réécriture s'il existe).")


if __name__ == "__main__":
    main()
