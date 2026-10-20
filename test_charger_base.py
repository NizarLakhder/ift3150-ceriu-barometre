"""Tests de charger_base.py : la conversion des fiches en lignes de tables.

Ils n'ont pas besoin de PostgreSQL. Ce qui touche la base elle-même (ne pas
charger deux fois, redonner les chiffres des CSV) est vérifié à chaque
chargement par la fonction verifier.

Commande : python -B -m unittest -v test_charger_base
"""

import copy
import unittest
from datetime import date
from decimal import Decimal

import charger_base as base

# Cas réel, raccourci : le dossier PGA-Eau de Matagami, semaine du 7 septembre 2026.
MATAGAMI = {
    "ocid": "ocds-ec9k95-20170481", "id": "20260911172212", "date": "2026-09-11T13:22:12-04:00",
    "tag": ["contract"], "initiationType": "tender",
    "parties": [
        {"name": "Ville de Matagami", "id": "OP-70456", "roles": ["buyer"], "details": {"municipal": "1"}},
        {"name": "L'UNION DES MUNICIPALITÉS DU QUÉBEC", "id": "FO-1142385377", "roles": ["supplier"],
         "details": {"neq": "1142385377"},
         "address": {"streetAddress": "2020 Blvd Robert-Bourassa, #210", "locality": "Montréal", "region": "QC",
                     "postalCode": "H3A2A5", "countryName": "CAN"}}],
    "buyer": {"name": "Ville de Matagami", "id": "OP-70456"},
    "tender": {
        "id": "G-2026-09-004", "title": "Renforcement stratégique pour l'élaboration du PGA-EAU", "status": "complete",
        "items": [{"id": "S5", "description": "S5 - Services environnementaux",
                   "classification": {"scheme": "UNSPSC", "id": "77000000", "description": "Services environnementaux"},
                   "additionalClassifications": [
                       {"scheme": "UNSPSC", "id": "77100000", "description": "Gestion environnementale"},
                       {"scheme": "UNSPSC", "id": "77101700", "description": "Services-conseils en matière d’environnement"}]}],
        "procurementMethod": "direct", "procurementMethodDetails": "Contrat de gré à gré",
        "mainProcurementCategory": "services", "additionalProcurementCategories": ["Services professionnels"],
        "tenderPeriod": {"startDate": "2026-09-11T13:22:12-04:00"}, "numberOfTenderers": 1,
        "tenderers": [{"id": "FO-1142385377", "name": "L'UNION DES MUNICIPALITÉS DU QUÉBEC"}],
        "documents": [{"url": "https://seao.gouv.qc.ca/avis-resultat-recherche/consulter?ItemId=adb87320"}]},
    "awards": [{"id": "20165337", "status": "active", "date": "2026-09-08T00:00:00-04:00",
                "value": {"amount": 4892.19, "currency": "CAD"},
                "suppliers": [{"name": "L'UNION DES MUNICIPALITÉS DU QUÉBEC", "id": "FO-1142385377"}]}],
    "contracts": [{"id": "20165337", "awardID": "20165337", "status": "active",
                   "value": {"amount": 4892.19, "currency": "CAD"}, "dateSigned": "2026-09-08T00:00:00-04:00"}],
    "language": "fr",
}


class ConversionsTests(unittest.TestCase):
    """Les petites conversions qui transforment le texte publié en valeurs de base de données."""

    def test_amounts_stay_exact_and_missing_values_become_null(self):
        # Pas de nombre à virgule flottante : 77061.99 reste exactement 77061.99.
        self.assertEqual(base.nombre(77061.99), Decimal("77061.99"))
        self.assertEqual(base.nombre("0.56544245"), Decimal("0.56544245"))
        # Une valeur absente devient NULL, jamais zéro.
        for valeur in (None, "", "NULL", "À compléter", "pas un nombre"):
            self.assertIsNone(base.nombre(valeur))
        self.assertIsNone(base.texte("À compléter"))

    def test_fictitious_seao_date_is_dropped(self):
        self.assertIsNone(base.instant("0001-01-01T00:00:00-05:00"))
        self.assertEqual(base.instant("2026-09-08T00:00:00-04:00").date(), date(2026, 9, 8))

    def test_region_and_mrc_codes_are_read_from_their_labels(self):
        self.assertEqual(base.region_de("Saguenay--Lac-Saint-Jean (02)"), ("02", "Saguenay--Lac-Saint-Jean"))
        self.assertEqual(base.region_de(""), (None, None))
        self.assertEqual(base.code_mrc_de("MRC Bellechasse (190)"), "AR190")
        self.assertEqual(base.code_mrc_de("Communauté métropolitaine de Montréal (663)", "CM"), "CM663")
        self.assertIsNone(base.code_mrc_de(""))

    def test_period_is_read_from_the_file_name(self):
        self.assertEqual(base.periode_de("hebdo_20260907_20260913.json"), (date(2026, 9, 7), date(2026, 9, 13)))

    def test_organism_type_follows_the_code(self):
        self.assertEqual(base.type_organisme("92030"), "municipalité")
        self.assertEqual(base.type_organisme("AR930"), "MRC ou communauté")
        self.assertEqual(base.type_organisme("CM663"), "MRC ou communauté")
        self.assertEqual(base.type_organisme("À compléter"), "non municipal")


class FicheTests(unittest.TestCase):
    """Une fiche du SEAO devient des lignes, une liste par table."""

    def test_matagami_is_split_into_its_tables(self):
        lignes = base.lignes_de_la_fiche(MATAGAMI, "hebdo_20260907_20260913.json")
        fiche = lignes["fiche"]
        self.assertEqual((fiche["ocid"], fiche["release_id"]), ("ocds-ec9k95-20170481", "20260911172212"))
        self.assertEqual(fiche["date_deduite_numero"], date(2026, 9, 11))
        self.assertEqual(fiche["acheteur_id"], "OP-70456")
        self.assertEqual(fiche["nomenclature_code"], "S5")
        self.assertEqual(lignes["acheteur"]["organisme"], "Ville de Matagami")
        self.assertEqual([t["tag"] for t in lignes["tags"]], ["contract"])
        self.assertEqual([(c["code"], c["principale"]) for c in lignes["classifications"]],
                         [("77000000", True), ("77100000", False), ("77101700", False)])
        self.assertEqual(lignes["attributions"][0]["montant"], Decimal("4892.19"))
        self.assertEqual(lignes["contrats"][0]["attribution_id"], "20165337")
        self.assertEqual([f["fournisseur_id"] for f in lignes["fournisseurs"]], ["FO-1142385377"])
        self.assertEqual(lignes["fournisseurs"][0]["neq"], "1142385377")
        self.assertEqual([s["fournisseur_id"] for s in lignes["soumissionnaires"]], ["FO-1142385377"])

    def test_inconsistent_fiche_stops_the_load(self):
        # Le schéma range le fournisseur dans l'attribution : deux fournisseurs ne rentrent pas.
        fiche = copy.deepcopy(MATAGAMI)
        fiche["awards"][0]["suppliers"].append({"name": "Autre", "id": "FO-2"})
        with self.assertRaises(ValueError):
            base.lignes_de_la_fiche(fiche, "test.json")
        # Un contrat qui renvoie à une attribution absente de la fiche.
        fiche = copy.deepcopy(MATAGAMI)
        fiche["contracts"][0]["awardID"] = "99999999"
        with self.assertRaises(ValueError):
            base.lignes_de_la_fiche(fiche, "test.json")

    def test_tenderer_missing_from_parties_is_still_kept(self):
        # Cas réel : 361 soumissionnaires des deux exports ne figurent pas dans la liste des parties.
        fiche = copy.deepcopy(MATAGAMI)
        fiche["tender"]["tenderers"].append({"id": "FO-20159563", "name": "CONTROL CASE LLC"})
        lignes = base.lignes_de_la_fiche(fiche, "test.json")
        self.assertIn(("FO-20159563", "CONTROL CASE LLC"), [(f["fournisseur_id"], f["nom"]) for f in lignes["fournisseurs"]])
        self.assertEqual(len(lignes["soumissionnaires"]), 2)

    def test_missing_amount_stays_missing(self):
        # Un montant absent n'est pas un montant nul.
        fiche = copy.deepcopy(MATAGAMI)
        del fiche["awards"][0]["value"]["amount"]
        self.assertIsNone(base.lignes_de_la_fiche(fiche, "test.json")["attributions"][0]["montant"])


if __name__ == "__main__":
    unittest.main()
