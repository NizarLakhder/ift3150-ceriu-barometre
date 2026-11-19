"""Les points à relire dans la source (qualite.csv). Un signalement n'est pas une erreur."""

from barometre.utilitaires import format_money


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
