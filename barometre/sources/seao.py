"""La lecture d'un export du SEAO (format OCDS) : son nom (type et période), puis, pour chaque fiche,
l'acheteur, les fournisseurs retenus, les identifiants, les montants et les catégories. Ces fonctions
lisent sans rien décider."""

import re
from datetime import datetime

from utilitaires import clean_text, safe_float


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


# ---------------------------------------------------------------------------
# L'export : son nom et l'ordre de chargement
# ---------------------------------------------------------------------------

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


def ordre_de_chargement(chemin):
    """Les exports se chargent dans l'ordre de leur période, pour que le dernier nom lu soit le plus récent."""
    _, debut, fin = decrire_export(chemin.name)
    return fin, debut, chemin.name
