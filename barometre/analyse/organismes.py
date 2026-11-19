"""Le résumé par organisme (comparaison.csv), avec le décompte des fournisseurs."""

import statistics
from collections import Counter, defaultdict

from barometre.utilitaires import top


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
