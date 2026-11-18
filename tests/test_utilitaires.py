"""Tests d'utilitaires.py : les petites fonctions partagées par les programmes.

Commande : python -B -m unittest -v test_utilitaires
"""

import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import utilitaires as u


class UtilitairesTests(unittest.TestCase):

    def test_text_and_organism_names_are_cleaned(self):
        self.assertEqual(u.clean_text("  Ville   de\tMatagami "), "Ville de Matagami")
        self.assertEqual(u.clean_text(None), "")
        # Cas réel : le SEAO écrit souvent « Ville de Lévis. », avec un point final.
        self.assertEqual(u.clean_org_name("Ville de Lévis. "), "Ville de Lévis")
        self.assertEqual(u.clean_org_name("Municipalité  de Saint-Elzéar"), "Municipalité de Saint-Elzéar")

    def test_missing_amount_is_none_not_zero(self):
        self.assertEqual(u.safe_float("4892.19"), 4892.19)
        self.assertIsNone(u.safe_float(None))
        self.assertIsNone(u.safe_float("n/d"))
        # À l'affichage, un montant s'écrit à la québécoise, et un montant absent ne devient pas 0 $.
        self.assertEqual(u.format_money(77061.99), "77 061,99 $")
        self.assertEqual(u.format_money(None), "Non disponible")

    def test_fictitious_seao_date_and_malformed_dates_are_dropped(self):
        self.assertEqual(u.valid_date("2026-09-08T00:00:00-04:00"), "2026-09-08")
        self.assertEqual(u.valid_date("0001-01-01T00:00:00-05:00"), "")
        self.assertEqual(u.valid_date("8 septembre"), "")
        # La date se lit aussi dans le numéro de la fiche.
        self.assertEqual(u.date_from_release_id({"id": "20260911172212"}), "2026-09-11")
        self.assertEqual(u.date_from_release_id({"id": "abc"}), "")

    def test_summaries_and_csv_files_are_readable(self):
        self.assertEqual(u.top(Counter({"gré à gré": 3, "": 9, "appel d'offres": 2})),
                         "gré à gré (3); appel d'offres (2)")
        # Le BOM du début de fichier permet à Excel d'afficher les accents. Une liste vide n'écrit rien.
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "test.csv"
            u.write_csv(chemin, [{"organisme": "Ville de Matagami", "population": "1352"}])
            self.assertTrue(chemin.read_bytes().startswith(b"\xef\xbb\xbf"))
            with chemin.open(encoding="utf-8-sig", newline="") as fichier:
                self.assertEqual(list(csv.DictReader(fichier)), [{"organisme": "Ville de Matagami", "population": "1352"}])
            u.write_csv(Path(dossier) / "vide.csv", [])
            self.assertFalse((Path(dossier) / "vide.csv").exists())


if __name__ == "__main__":
    unittest.main()
