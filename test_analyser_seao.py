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

    def test_supplier_is_identified_by_its_identifier_not_its_name(self):
        # Le même identifiant sous deux noms : un seul fournisseur.
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

        # Le même nom sous deux identifiants : deux fournisseurs.
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

    def test_several_versions_of_a_process_are_allowed(self):
        # Le même numéro de fiche dans deux dossiers différents.
        analyse.validate_identifiers([
            municipal_release("ocds-test-1", "20260907120000"),
            municipal_release("ocds-test-2", "20260907120000"),
        ])
        # Deux versions du même dossier et du même contrat.
        analyse.validate_identifiers([
            municipal_release("ocds-test-1", "20260907120000", contracts=[{"id": "C-1"}]),
            municipal_release("ocds-test-1", "20260908120000", contracts=[{"id": "C-1"}]),
        ])

    def test_missing_or_duplicate_identifiers_are_rejected(self):
        # La même fiche deux fois.
        with self.assertRaises(ValueError):
            analyse.validate_identifiers([municipal_release(), municipal_release()])
        # Un numéro de dossier ou de fiche absent.
        for field in ("ocid", "id"):
            for missing in (None, "", "   "):
                with self.subTest(field=field, missing=missing):
                    release = municipal_release()
                    release[field] = missing
                    with self.assertRaises(ValueError):
                        analyse.validate_identifiers([release])
        # Un contrat sans identifiant, ou deux fois le même contrat dans une fiche.
        with self.assertRaises(ValueError):
            analyse.validate_identifiers([municipal_release(contracts=[{}])])
        with self.assertRaises(ValueError):
            analyse.validate_identifiers([municipal_release(contracts=[
                {"id": "C-1"}, {"id": "C-1"},
            ])])


class PgaEauDetectionTests(unittest.TestCase):
    """Les titres réels des exports : les cinq PGA-Eau doivent être reconnus, les pièges ignorés."""

    def test_real_pga_eau_titles_are_recognized(self):
        titres = [
            "Services professionnels d'accompagnement à la préparation du Plan de gestion des actifs "
            "municipaux en eau (PGA-Eau)",                                                   # Nicolet
            "Services professionnels pour l’élaboration d’un plan de gestion des actifs en eau (PGA-Eau) "
            "pour la Ville de Sept-Îles",                                                     # Sept-Îles
            "Services professionnels pour l’élaboration d’un plan de gestion des actifs en eau (PGA – Eau) "
            "pour la Ville de Windsor",                                                       # tiret long
            "Services professionnels pour l'accompagnement dans l'élaboration d'un plan de gestion des "
            "actifs en eau",                                                                  # sans acronyme
            "Renforcement stratégique pour l'élaboration du PGA-EAU",                         # Matagami
        ]
        for titre in titres:
            with self.subTest(titre=titre[:60]):
                self.assertTrue(analyse.is_pga_eau(titre))

    def test_real_traps_are_not_taken_for_pga_eau(self):
        pieges = [
            "MANDAT D'ACCOMPGANEMENT POUR LA MISE EN PLACE D'UN COMITÉ CONSULTATIF TI",   # STM, faute de frappe
            "Plan de gestion des eaux pluviales",                                         # pas d'« actif »
            "Services professionnels pour la mise en place d’un plan de gestion des actifs et d’un plan "
            "directeur de maintien des actifs des bâtiments municipaux",                  # Dollard, bâtiments
            "Réhabilitation du puits P3 et option de remplacement de la tête du puits",   # eau, mais pas un PGA
        ]
        for titre in pieges:
            with self.subTest(titre=titre[:60]):
                self.assertFalse(analyse.is_pga_eau(titre))

    def test_pga_eau_column_and_count_per_organism(self):
        pga = municipal_release()
        pga["tender"]["title"] = "Élaboration du plan de gestion des actifs en eau (PGA-Eau)"
        autre = municipal_release("ocds-test-2")
        rows, names = rows_and_names([pga, autre])
        self.assertEqual([row["pga_eau"] for row in rows], ["oui", "non"])
        self.assertEqual(analyse.aggregate_municipalities(rows, names)[0]["nb_avis_pga_eau"], 1)


class GestionActifsEauTests(unittest.TestCase):
    """Le repérage large : tout ce qui touche à la gestion des actifs en eau, à classer ensuite à la main."""

    def test_real_water_asset_management_titles_are_recognized(self):
        cas = {
            "Mise à jour du plan d'intervention dans le cadre de la TECQ 2024-2028": "plan d'intervention",  # Laurierville
            "Mise à jour du plan d'intervention pour les réseaux d'aqueduc, d'égouts et des chaussées":
                "plan d'intervention",                                                         # Roberval
            "FOURNITURE DE SERVICES PROFESSIONNELS D’INGÉNIERIE POUR LA MISE À JOUR DU PLAN D’INTERVENTION POUR LES "
            "RÉSEAUX D’AQUEDUC": "plan d'intervention",                                       # Marieville, apostrophes courbes
            "Réalisation plan gestion des actifs des infrastructures complet": "gestion d'actifs",  # Clermont
            "GESTION D'ACTIFS - MANDAT SUR PTI": "gestion d'actifs",                           # Saguenay
            "Logiciel de gestion des actifs": "outil",                                         # Magog
            "Inspections télévisées des conduites dans le cadre de la mise à jour du plan d'intervention": "étape",  # Disraeli
            "Renforcement stratégique pour l'élaboration du PGA-EAU": "PGA-Eau",               # Matagami
        }
        for titre, famille in cas.items():
            with self.subTest(titre=titre[:60]):
                self.assertEqual(analyse.gestion_actifs_eau(titre), famille)
        # La description compte aussi, quand le titre ne dit rien.
        self.assertEqual(analyse.gestion_actifs_eau("Services professionnels en ingénierie",
                                                    "Accompagnement pour l'élaboration du PGA-Eau de la municipalité"),
                         "PGA-Eau")

    def test_other_assets_and_routine_work_are_left_aside(self):
        pieges = [
            "Élaboration d'un plan d'intervention en infrastructures routières locales (PIIRL)",  # routes
            "Plan d'intervention de sécurité routière en milieu municipal",
            "Services professionnels - Élaboration d'un plan d'intervention (Dans le cadre du PAVL 2021-2025)",
            "Services professionnels pour établir un diagnostic et élaboration d'un plan d'intervention pour certains "
            "terrains de tennis",
            "Réalisation et implantation d’un programme de gestion des actifs des bâtiments municipaux",  # plus tard
            "Fourniture et installation du mobilier pour le Centre de gestion des actifs",
            "Services professionnels pour l’accompagnement opérationnel d'un Plan stratégique de gestion des actifs",  # ARTM
            "Inspection télévisée des conduites d'égout",                                      # routine, sans plan
            "Plan de gestion des eaux pluviales",
        ]
        for titre in pieges:
            with self.subTest(titre=titre[:60]):
                self.assertEqual(analyse.gestion_actifs_eau(titre), "")


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

    def test_missing_source_is_created_once_without_losing_anything(self):
        # Sans fichier de saisie ni ancienne vue : on part d'une vue vierge.
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.csv"
            loaded = analyse.load_context_source(source, Path(directory) / "absent.csv", [context_row()])
            self.assertTrue(source.exists())
            self.assertEqual(loaded, [context_row()])

        # Avec une ancienne vue : les saisies, les colonnes ajoutées à la main et les
        # organismes absents du nouvel export sont gardés, et le fichier n'est créé qu'une fois.
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

    def test_context_line_is_found_again(self):
        # L'ordre des identifiants et l'écriture du nom ne comptent pas.
        source = context_row("Ancien nom", "OP-2 | OP-1", population="1234")
        target = context_row("Nom actuel", "OP-1 | OP-2")
        merged = analyse.merge_context_rows([target], [source])[0]
        self.assertEqual(merged["population"], "1234")
        self.assertEqual(merged["organisme"], "Nom actuel")
        self.assertEqual(target["population"], "À compléter")

        # Un organisme peut publier sous plus ou moins d'identifiants selon
        # l'export, comme la Ville de Montréal (31 identifiants une semaine,
        # 36 le mois d'août). Le même nom et un identifiant en commun suffisent
        # alors à retrouver sa ligne de contexte.
        source = context_row(buyer_ids="OP-1 | OP-2", population="1234")
        self.assertEqual(analyse.merge_context_rows([context_row()], [source])[0]["population"], "1234")

        # Une ligne saisie sans aucun identifiant se retrouve par le nom.
        source = context_row("Ville de Test.", "", population="1234")
        self.assertEqual(analyse.merge_context_rows([context_row()], [source])[0]["population"], "1234")

    def test_doubtful_matches_stop_the_program(self):
        # Le nom ne sert que si la ligne n'a aucun identifiant : un identifiant différent arrête.
        with self.assertRaises(ValueError):
            analyse.merge_context_rows([context_row()], [context_row(buyer_ids="OP-9", population="1234")])
        # Deux lignes revendiquent le même identifiant.
        with self.assertRaises(ValueError):
            analyse.merge_context_rows([context_row()], [
                context_row(population="1234"),
                context_row("Autre organisme", "OP-1 | OP-2", population="5678"),
            ])
        # Deux lignes sans identifiant portent le même nom.
        with self.assertRaises(ValueError):
            analyse.merge_context_rows([context_row()], [context_row(buyer_ids=""), context_row(buyer_ids="")])
        # Un identifiant commun ne suffit pas si le nom diffère : la population
        # d'un organisme ne doit jamais passer à un autre sans vérification.
        source = context_row("Autre ville", "OP-1 | OP-2", population="1234")
        with self.assertRaises(ValueError):
            analyse.merge_context_rows([context_row(buyer_ids="OP-1")], [source])
        # Aucun identifiant en commun.
        with self.assertRaises(ValueError):
            analyse.merge_context_rows([context_row()], [context_row(buyer_ids="OP-8 | OP-9", population="1234")])

    def test_new_organisms_are_appended_without_changing_existing_lines(self):
        # Un nouvel export fait apparaître un organisme inconnu : il est ajouté à
        # la fin du fichier, et les lignes déjà saisies restent identiques.
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.csv"
            absente = Path(directory) / "absente.csv"
            analyse.write_csv(source, [context_row(population="1234", notes="Saisie manuelle")])
            before = source.read_bytes()
            vue = [context_row(), context_row("Ville nouvelle", "OP-7")]

            nouveaux = []
            analyse.merge_context_rows(vue, analyse.load_context_source(source, absente, vue), absents=nouveaux)
            self.assertEqual([row["organisme"] for row in nouveaux], ["Ville nouvelle"])
            self.assertEqual(analyse.append_context_rows(source, nouveaux, directory), 1)
            self.assertTrue(source.read_bytes().startswith(before))

            relu = analyse.load_context_source(source, absente, vue)
            self.assertEqual(relu[0]["population"], "1234")
            self.assertEqual(relu[0]["notes"], "Saisie manuelle")
            self.assertEqual((relu[1]["organisme"], relu[1]["population"]), ("Ville nouvelle", "À compléter"))
            # La note de la nouvelle ligne naît vide : il n'y a encore rien à signaler.
            self.assertEqual(relu[1]["notes"], "")

            # Une deuxième analyse du même export n'ajoute plus rien.
            encore = []
            analyse.merge_context_rows(vue, relu, absents=encore)
            self.assertEqual(encore, [])


if __name__ == "__main__":
    unittest.main()
