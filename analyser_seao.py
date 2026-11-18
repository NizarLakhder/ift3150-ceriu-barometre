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

Ce programme ne fait qu'enchaîner les étapes. Le code est rangé dans barometre/ :
chemins.py, regles.py, sources/seao.py, analyse/ (fiche, organismes, qualite) et
contexte/fichier.py.

Utilisation :
    python analyser_seao.py                                  # export de la semaine du 7 septembre 2026
    python analyser_seao.py mensuel_20260801_20260831.json   # un autre export de donnees_seao/
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

# Les fonctions et constantes déplacées restent accessibles par analyser_seao : charger_base.py et les tests
# les utilisent. Les mots-clés des règles liées à l'eau sont dans config/regles_reperage.toml.
from barometre.analyse.fiche import SEUIL_PRIX_UNITAIRE, analyse_release  # noqa: F401
from barometre.analyse.organismes import aggregate_municipalities, count_suppliers, format_suppliers  # noqa: F401
from barometre.analyse.qualite import build_quality_rows
from barometre.chemins import (ANCIENNE_VUE_CONTEXTE, CONTEXT_SOURCE_CSV, DOSSIER_SEAO, DOSSIER_SORTIES,  # noqa: F401
                               JSON_FILE, noms_de_sortie, trouver_fichier_json)
from barometre.contexte.fichier import (CONTEXT_FIELDS, ContexteInvalide, EcritureEchouee,  # noqa: F401
                                        append_context_rows, build_context_rows, load_context_source,
                                        merge_context_rows)
from barometre.configuration import ConfigurationInvalide
from barometre.regles import (UNSPSC_SUBVENTION, gestion_actifs_eau, get_nature, is_pga_eau,  # noqa: F401
                              is_water_related, org_type, regles, texte_de_recherche)
from barometre.sources.seao import (get_amounts, get_categories, get_municipal_buyer_party,  # noqa: F401
                                    get_suppliers, validate_identifiers)
from utilitaires import (clean_org_name, clean_text, date_from_release_id, format_money,  # noqa: F401
                         safe_float, top, valid_date, write_csv)


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------


def main():
    """Analyse un export et écrit les quatre CSV. Rien n'est écrit avant la fin des vérifications."""
    # Les règles d'abord : si leur fichier manque ou n'est pas valide, rien n'est lu ni écrit.
    try:
        regles()
    except ConfigurationInvalide as erreur:
        print(f"Erreur : règles de repérage invalides, rien n'a été lu ni écrit.\n{erreur}", file=sys.stderr)
        return 1
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
    try:
        context_source = load_context_source(CONTEXT_SOURCE_CSV, ANCIENNE_VUE_CONTEXTE, context_rows)
    except ContexteInvalide as erreur:
        print(f"Erreur : {erreur}\nRien n'a été écrit.", file=sys.stderr)
        return 1
    nouveaux = []
    context_rows = merge_context_rows(context_rows, context_source, absents=nouveaux)

    # Les vérifications ont réussi : on peut écrire.
    try:
        ajoutes = append_context_rows(CONTEXT_SOURCE_CSV, nouveaux)
    except EcritureEchouee as erreur:
        # Arrêt immédiat, même si les organismes nouveaux sont déjà ajoutés : le message dit ce qui l'est.
        print(f"Erreur : {erreur}\nArrêt : aucun des quatre CSV n'a été écrit.", file=sys.stderr)
        return 1
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
    sys.exit(main())
