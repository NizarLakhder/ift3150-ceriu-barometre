"""Tests de completer_contexte.py : de petits cas fabriqués, inspirés de vrais homonymes.

Ils ne lisent pas les vrais fichiers du ministère. Les fichiers créés pendant
les tests vont dans des dossiers temporaires, jamais dans le projet.

Commande : python -B -m unittest -v test_completer_contexte
"""

import csv
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import completer_contexte as contexte


def municipalite(nom, designation, code_postal, code):
    """Fabrique une entrée minimale du répertoire des municipalités (MUN.csv)."""
    return ("municipalité", {"munnom": nom, "mdes": designation, "mcodpos": code_postal, "mcode": code})


class NomsTests(unittest.TestCase):
    """Le SEAO et le répertoire n'écrivent pas les noms pareil : la clé doit les rapprocher."""

    def test_designation_accents_and_articles_are_removed(self):
        self.assertEqual(contexte.cle_organisme("Ville de Sept-Îles"), "sept iles")
        self.assertEqual(contexte.cle_organisme("Ville de Sept-Îles"), contexte.cle_organisme("Sept-Îles"))

    def test_stacked_designations_are_all_removed(self):
        self.assertEqual(contexte.cle_organisme("Municipalité de la Paroisse de Saint-Louis-de-Gonzague"),
                         contexte.cle_organisme("Saint-Louis-de-Gonzague"))

    def test_purchasing_service_added_by_the_buyer_is_removed(self):
        self.assertEqual(contexte.cle_organisme("Ville de Joliette - Approvisionnement"),
                         contexte.cle_organisme("Joliette"))

    def test_expected_type_separates_an_mrc_from_a_town(self):
        # « MRC de Montmagny » et « Ville de Montmagny » ont la même clé : le début du nom les sépare.
        self.assertEqual(contexte.type_attendu("MRC de Montmagny"), "MRC ou communauté")
        self.assertEqual(contexte.type_attendu("Ville de Montmagny"), "municipalité")
        self.assertIsNone(contexte.type_attendu("Régie intermunicipale de l'eau"))


class RemplissageTests(unittest.TestCase):
    """La règle la plus importante : une valeur déjà présente n'est jamais écrasée."""

    def test_manual_value_is_never_replaced(self):
        ligne = {"population": "9999", "mrc": "À compléter", "notes": "Saisie à la main"}
        remplies, intactes = contexte.remplir_ligne(ligne, {"population": "12026", "mrc": "MRC Les Laurentides"})
        self.assertEqual(ligne["population"], "9999")
        self.assertEqual(ligne["mrc"], "MRC Les Laurentides")
        self.assertEqual(ligne["notes"], "Saisie à la main")
        self.assertEqual((remplies, intactes), (1, 1))

    def test_empty_cells_are_filled_but_empty_values_are_ignored(self):
        ligne = {"population": "", "classe_taille": "À compléter"}
        remplies, _ = contexte.remplir_ligne(ligne, {"population": "1352", "classe_taille": ""})
        self.assertEqual(ligne, {"population": "1352", "classe_taille": "À compléter"})
        self.assertEqual(remplies, 1)


class DepartagerTests(unittest.TestCase):
    """Deux municipalités portent le même nom : on ne tranche qu'avec un indice publié."""

    def test_postal_code_wins_over_a_generic_designation(self):
        # Cas réel : le SEAO écrit « Municipalité Sainte-Françoise », mais son adresse
        # est celle de la paroisse du Bas-Saint-Laurent, pas de la municipalité.
        candidats = [municipalite("Sainte-Françoise", "Paroisse", "G0L 3B0", "11030"),
                     municipalite("Sainte-Françoise", "Municipalité", "G0S2N0", "38035")]
        choix, methode = contexte.departager("Municipalité Sainte-Françoise", candidats, {"G0L3B0"})
        self.assertEqual(choix[1]["mcode"], "11030")
        self.assertEqual(methode, "code postal G0L3B0")

    def test_designation_decides_when_both_share_a_postal_code(self):
        # Cas réel : la ville et la paroisse de Disraeli ont le même code postal.
        candidats = [municipalite("Disraeli", "Ville", "G0N1E0", "31015"),
                     municipalite("Disraeli", "Paroisse", "G0N1E0", "31020")]
        choix, _ = contexte.departager("Municipalité de la Paroisse de Disraeli", candidats, {"G0N1E0"})
        self.assertEqual(choix[1]["mcode"], "31020")
        choix, _ = contexte.departager("Ville de Disraeli", candidats, {"G0N1E0"})
        self.assertEqual(choix[1]["mcode"], "31015")

    def test_generic_municipalite_is_not_a_clue(self):
        # Cas réel : deux Saint-Elzéar, sans adresse publiée dans le SEAO.
        candidats = [municipalite("Saint-Elzéar", "Municipalité", "G0S2J1", "26022"),
                     municipalite("Saint-Elzéar", "Municipalité", "G0C2W0", "05050")]
        self.assertEqual(contexte.departager("Municipalité de Saint-Elzéar", candidats, set()), (None, None))

    def test_contradicting_clues_leave_the_case_open(self):
        # Le code postal désigne la ville, mais le nom dit « Canton » : on ne choisit pas.
        candidats = [municipalite("Exemple", "Ville", "A1A1A1", "1"),
                     municipalite("Exemple", "Canton", "B2B2B2", "2")]
        self.assertEqual(contexte.departager("Municipalité du Canton d'Exemple", candidats, {"A1A1A1"}),
                         (None, None))

    def test_a_designation_word_inside_the_name_does_not_count(self):
        # « Municipalité de Ville-Marie » : « Ville » fait partie du nom, ce n'est pas une désignation.
        candidats = [municipalite("Ville-Marie", "Ville", "J9V1V0", "1"),
                     municipalite("Ville-Marie", "Municipalité", "J0Z0Z0", "2")]
        self.assertEqual(contexte.departager("Municipalité de Ville-Marie", candidats, set()), (None, None))


class SourcesTests(unittest.TestCase):
    """Lecture des fichiers de référence et des vues produites par l'analyse."""

    def test_same_perimunicipal_organism_listed_twice_counts_once(self):
        # Cas réel : le fichier du ministère liste deux fois la Société de transport de l'Outaouais.
        racine = ET.fromstring("<liste><o><NOM_L1>Société de transport de l'Outaouais</NOM_L1></o>"
                               "<o><NOM_L1>Société de transport de l'Outaouais</NOM_L1></o></liste>")
        index = contexte.construire_index([], [], list(racine))
        self.assertEqual(len(index[contexte.cle_organisme("Société de transport de l'Outaouais")]), 1)

    def test_postal_codes_are_read_from_the_analysis_views(self):
        with tempfile.TemporaryDirectory() as dossier:
            with open(Path(dossier) / "a_enrichir_test.csv", "w", encoding="utf-8-sig", newline="") as fichier:
                ecrivain = csv.DictWriter(fichier, fieldnames=["organisme", "buyer_ids", "code_postal_seao"])
                ecrivain.writeheader()
                ecrivain.writerow({"organisme": "Ville de Test", "buyer_ids": "OP-1 | OP-2",
                                   "code_postal_seao": "g0l 3b0"})
            self.assertEqual(contexte.lire_codes_postaux_seao(dossier),
                             {"OP-1": {"G0L3B0"}, "OP-2": {"G0L3B0"}})


if __name__ == "__main__":
    unittest.main()
