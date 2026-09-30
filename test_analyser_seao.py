"""Tests de régression : de petits cas fabriqués à la main, dont on connaît la bonne réponse.

Ils ne lisent pas les vrais exports du SEAO. La plupart vérifient un piège
rencontré pour de vrai dans les données, pour qu'il ne revienne pas sans
qu'on s'en aperçoive. Les fichiers créés pendant les tests vont dans des
dossiers temporaires, jamais dans le projet.

Commande : python -B -m unittest -v test_analyser_seao
"""

import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

import analyser_seao as analyse


def municipal_release(ocid="ocds-test-1", release_id="20260907120000", *,
                      suppliers=(), contracts=(), tags=()):
    """Fabrique une fiche municipale minimale. Chaque fournisseur reçoit sa propre attribution."""
    return {
        "ocid": ocid,
        "id": release_id,
        "buyer": {"id": "OP-1", "name": "Ville de Test"},
        "parties": [{
            "id": "OP-1",
            "name": "Ville de Test",
            "roles": ["buyer"],
            "details": {"municipal": "1"},
        }],
        "tag": list(tags),
        "tender": {"title": "Entretien du réseau", "status": "complete"},
        "awards": [
            {"id": f"A-{index}", "suppliers": [supplier]}
            for index, supplier in enumerate(suppliers, 1)
        ],
        "contracts": list(contracts),
    }


def rows_and_names(releases):
    """Analyse les fiches comme le fait main(), et retourne aussi les noms connus de chaque fournisseur."""
    rows = [analyse.analyse_release(release) for release in releases]
    names = defaultdict(set)
    for release in releases:
        for supplier_id, name in analyse.get_suppliers(release).items():
            names[supplier_id].add(name)
    return rows, names


class SupplierIdentityTests(unittest.TestCase):
    """Un fournisseur se reconnaît à son identifiant, pas à son nom.

    Pièges réels : un même fournisseur écrit de deux façons différentes, et un
    nom qui contient une barre verticale, « LASALLE | NHC INC. », que la
    première version du code coupait en deux fournisseurs.
    """

    def test_same_identifier_with_several_names_is_one_supplier(self):
        releases = [
            municipal_release(suppliers=[{"id": "FO-1", "name": "Entreprise ABC"}]),
            municipal_release("ocds-test-2", suppliers=[{
                "id": "FO-1", "name": "ENTREPRISE ABC INC."
            }]),
        ]
        rows, names = rows_and_names(releases)
        summary = analyse.aggregate_municipalities(rows, names)[0]
        self.assertEqual(summary["nb_identifiants_fournisseurs"], 1)
        self.assertEqual(analyse.count_suppliers(rows), Counter({"FO-1": 2}))
        display = analyse.format_suppliers(analyse.count_suppliers(rows), names)
        self.assertIn("FO-1", display)
        self.assertTrue(any(name in display for name in names["FO-1"]))

    def test_same_name_with_two_identifiers_stays_two_suppliers(self):
        rows, names = rows_and_names([municipal_release(suppliers=[
            {"id": "FO-1", "name": "Entreprise ABC"},
            {"id": "FO-2", "name": "Entreprise ABC"},
        ])])
        self.assertEqual(rows[0]["nb_identifiants_fournisseurs"], 2)
        self.assertEqual(
            analyse.aggregate_municipalities(rows, names)[0]["nb_identifiants_fournisseurs"],
            2,
        )
        self.assertEqual(analyse.count_suppliers(rows), Counter({"FO-1": 1, "FO-2": 1}))

    def test_vertical_bar_in_name_is_preserved(self):
        supplier_name = "LASALLE | NHC INC."
        rows, names = rows_and_names([municipal_release(suppliers=[{
            "id": "FO-3", "name": supplier_name,
        }])])
        counter = analyse.count_suppliers(rows)
        self.assertEqual(counter, Counter({"FO-3": 1}))
        self.assertIn(supplier_name, analyse.format_suppliers(counter, names))
        self.assertEqual(
            analyse.aggregate_municipalities(rows, names)[0]["nb_identifiants_fournisseurs"],
            1,
        )

    def test_supplier_frequency_counts_releases_not_awards(self):
        rows, _ = rows_and_names([municipal_release(suppliers=[
            {"id": "FO-1", "name": "Entreprise ABC"},
            {"id": "FO-1", "name": "Entreprise ABC"},
        ])])
        self.assertEqual(rows[0]["nb_attributions"], 2)
        self.assertEqual(analyse.count_suppliers(rows), Counter({"FO-1": 1}))

    def test_missing_identifier_is_reported_without_using_name_as_identifier(self):
        release = municipal_release(suppliers=[
            {"id": "FO-1", "name": "Entreprise connue"},
            {"name": "Fournisseur sans identifiant"},
        ])
        row = analyse.analyse_release(release)
        self.assertEqual(analyse.get_suppliers(release), {"FO-1": "Entreprise connue"})
        self.assertEqual(row["nb_identifiants_fournisseurs"], 1)
        self.assertEqual(row["nb_mentions_fournisseur_sans_id"], 1)
        self.assertEqual(analyse.count_suppliers([row]), Counter({"FO-1": 1}))


class PublicationAndStatusTests(unittest.TestCase):
    """Ne pas confondre ce qu'une fiche annonce (son étiquette) avec l'état actuel
    de ses contrats, ni l'étiquette « tender » avec une date d'ouverture."""

    def test_publication_event_and_contract_status_are_counted_separately(self):
        releases = [
            municipal_release(tags=["contractTermination"], contracts=[
                {"id": "C-1", "status": "terminated"},
                {"id": "C-2", "status": "terminated"},
                {"id": "C-3", "status": "active"},
            ]),
            municipal_release("ocds-test-2", tags=["contractUpdate"], contracts=[
                {"id": "C-4", "status": "terminated"},
                {"id": "C-5", "status": "cancelled"},
            ]),
        ]
        rows, names = rows_and_names(releases)
        self.assertEqual(rows[0]["nb_contrats_statut_terminated"], 2)
        summary = analyse.aggregate_municipalities(rows, names)[0]
        self.assertEqual(summary["nb_releases_tag_contractTermination"], 1)
        self.assertEqual(summary["nb_contrats_statut_terminated"], 3)
        self.assertEqual(summary["nb_contrats"], 5)

    def test_new_tender_tag_is_not_inferred_from_opening_date(self):
        release = municipal_release(tags=["tender"])
        release["tender"]["tenderPeriod"] = {"startDate": "2020-01-01T00:00:00Z"}
        update = municipal_release("ocds-test-2", tags=["tenderUpdate"])
        update["tender"]["tenderPeriod"] = {"startDate": "2026-09-07T00:00:00Z"}
        rows, names = rows_and_names([release, update])
        summary = analyse.aggregate_municipalities(rows, names)[0]
        self.assertEqual(summary["nb_releases_tag_tender"], 1)
        self.assertEqual(rows[0]["date_deduite_id_release"], "2026-09-07")


class IdentifierValidationTests(unittest.TestCase):
    """Plusieurs versions d'un même dossier sont acceptées; un identifiant absent
    ou en double arrête le programme."""

    def test_same_release_identifier_in_different_processes_is_allowed(self):
        analyse.validate_identifiers([
            municipal_release("ocds-test-1", "20260907120000"),
            municipal_release("ocds-test-2", "20260907120000"),
        ])

    def test_several_versions_of_process_and_contract_are_allowed(self):
        analyse.validate_identifiers([
            municipal_release("ocds-test-1", "20260907120000", contracts=[{"id": "C-1"}]),
            municipal_release("ocds-test-1", "20260908120000", contracts=[{"id": "C-1"}]),
        ])

    def test_duplicate_process_release_pair_is_rejected(self):
        with self.assertRaises(ValueError):
            analyse.validate_identifiers([municipal_release(), municipal_release()])

    def test_missing_process_or_release_identifier_is_rejected(self):
        for field in ("ocid", "id"):
            for missing in (None, "", "   "):
                with self.subTest(field=field, missing=missing):
                    release = municipal_release()
                    release[field] = missing
                    with self.assertRaises(ValueError):
                        analyse.validate_identifiers([release])

    def test_missing_contract_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            analyse.validate_identifiers([municipal_release(contracts=[{}])])

    def test_duplicate_contract_identifier_within_release_is_rejected(self):
        with self.assertRaises(ValueError):
            analyse.validate_identifiers([municipal_release(contracts=[
                {"id": "C-1"}, {"id": "C-1"},
            ])])


def context_row(name="Ville de Test", buyer_ids="OP-1", **values):
    """Fabrique une ligne de contexte où tout est « À compléter », sauf les valeurs données."""
    row = {"organisme": name, "buyer_ids": buyer_ids,
           **{field: "À compléter" for field in analyse.CONTEXT_FIELDS}}
    row.update(values)
    return row


class ContextPreservationTests(unittest.TestCase):
    """Une saisie manuelle du contexte ne doit jamais être perdue, ni rattachée
    au mauvais organisme."""

    def test_existing_source_is_read_without_modifying_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.csv"
            generated = Path(directory) / "vue.csv"
            saved = context_row(population="1234", source_contexte="Source officielle, 2026")
            analyse.write_csv(source, [saved])
            before = source.read_bytes()
            # Une ancienne vue générée ne doit jamais l'emporter sur le fichier de saisie.
            analyse.write_csv(generated, [context_row(population="999")])
            loaded = analyse.load_context_source(source, generated, [context_row()])
            self.assertEqual(loaded, [saved])
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(analyse.merge_context_rows([context_row()], loaded)[0]["population"], "1234")

    def test_first_migration_keeps_manual_values_extra_columns_and_absent_organisms(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.csv"
            generated = Path(directory) / "vue.csv"
            previous = [
                context_row(population="1234", notes="À confirmer", reference_personnelle="page 8"),
                context_row("Ville absente du nouvel export", "OP-2", population="456", reference_personnelle="page 9"),
            ]
            analyse.write_csv(generated, previous)
            loaded = analyse.load_context_source(source, generated, [context_row()])
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0]["population"], "1234")
            self.assertEqual(loaded[0]["notes"], "À confirmer")
            self.assertEqual(loaded[0]["reference_personnelle"], "page 8")
            self.assertEqual(loaded[1]["population"], "456")
            before = source.read_bytes()
            analyse.load_context_source(source, generated, [context_row()])
            self.assertEqual(source.read_bytes(), before)

    def test_first_run_without_previous_csv_creates_blank_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.csv"
            loaded = analyse.load_context_source(source, Path(directory) / "absent.csv", [context_row()])
            self.assertTrue(source.exists())
            self.assertEqual(loaded, [context_row()])

    def test_identifier_order_and_organism_spelling_do_not_erase_context(self):
        source = context_row("Ancien nom", "OP-2 | OP-1", population="1234")
        target = context_row("Nom actuel", "OP-1 | OP-2")
        merged = analyse.merge_context_rows([target], [source])[0]
        self.assertEqual(merged["population"], "1234")
        self.assertEqual(merged["organisme"], "Nom actuel")
        self.assertEqual(target["population"], "À compléter")

    def test_name_fallback_only_when_source_has_no_identifiers(self):
        source = context_row("Ville de Test.", "", population="1234")
        self.assertEqual(analyse.merge_context_rows([context_row()], [source])[0]["population"], "1234")
        with self.assertRaises(ValueError):
            analyse.merge_context_rows([context_row()], [context_row(buyer_ids="OP-9", population="1234")])

    def test_ambiguous_source_identifiers_are_rejected(self):
        with self.assertRaises(ValueError):
            analyse.merge_context_rows([context_row()], [
                context_row(population="1234"),
                context_row("Autre organisme", "OP-1 | OP-2", population="5678"),
            ])

    def test_ambiguous_names_without_identifiers_are_rejected(self):
        with self.assertRaises(ValueError):
            analyse.merge_context_rows([context_row()], [context_row(buyer_ids=""), context_row(buyer_ids="")])

    def test_partly_changed_identifier_set_keeps_the_context(self):
        # Un organisme peut publier sous plus ou moins d'identifiants selon
        # l'export, comme la Ville de Montréal (31 identifiants une semaine,
        # 36 le mois d'août). Un identifiant en commun suffit alors à retrouver
        # sa ligne de contexte.
        source = context_row(buyer_ids="OP-1 | OP-2", population="1234")
        merged = analyse.merge_context_rows([context_row()], [source])[0]
        self.assertEqual(merged["population"], "1234")

    def test_identifier_set_with_nothing_in_common_is_rejected(self):
        with self.assertRaises(ValueError):
            analyse.merge_context_rows([context_row()], [context_row(buyer_ids="OP-8 | OP-9", population="1234")])

    def test_failed_migration_does_not_create_source_or_modify_old_view(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.csv"
            generated = Path(directory) / "vue.csv"
            analyse.write_csv(generated, [context_row(buyer_ids="OP-9", population="1234")])
            before = generated.read_bytes()
            with self.assertRaises(ValueError):
                analyse.load_context_source(source, generated, [context_row()])
            self.assertFalse(source.exists())
            self.assertEqual(generated.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
