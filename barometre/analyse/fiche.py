"""Une fiche municipale devient une ligne de details.csv, avec les règles appliquées."""

from barometre.regles import gestion_actifs_eau, get_nature, is_pga_eau, is_water_related, org_type
from barometre.sources.seao import get_amounts, get_categories, get_municipal_buyer_party, get_suppliers
from utilitaires import clean_org_name, clean_text, date_from_release_id, safe_float, valid_date


# Un montant sous 1 000 $ est parfois un prix unitaire : il est signalé, jamais
# retiré. Seuil choisi à l'œil.
SEUIL_PRIX_UNITAIRE = 1000


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
