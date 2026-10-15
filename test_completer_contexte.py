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


def municipalite(nom, designation, code_postal, code, region="", mrc=""):
    """Fabrique une entrée minimale du répertoire des municipalités (MUN.csv)."""
    return ("municipalité", {"munnom": nom, "mdes": designation, "mcodpos": code_postal, "mcode": code,
                             "regadm": region, "mrc": mrc})


def petit_repertoire():
    """Un répertoire réduit, fait de vraies municipalités, pour essayer les règles tolérantes.

    Retourne (index, index tolérant, index des codes). Les noms, les codes
    géographiques et les codes postaux sont ceux du répertoire du ministère.
    """
    municipalites = [m[1] for m in (
        municipalite("Saint-Léon-de-Standon", "Paroisse", "G0R4L0", "19020", "Chaudière-Appalaches (12)", "MRC Bellechasse (190)"),
        municipalite("Saint-Léon-le-Grand", "Paroisse", "J0K2W0", "51035", "Mauricie (04)", "MRC Maskinongé (510)"),
        municipalite("Saint-Léon-le-Grand", "Paroisse", "G0J2W0", "07030", "Bas-Saint-Laurent (01)", "MRC La Matapédia (070)"),
        municipalite("Saint-Damase", "Municipalité", "J0H1J0", "54017", "Montérégie (16)", "MRC Les Maskoutains (540)"),
        municipalite("Saint-Damase", "Paroisse", "G0J2J0", "07105", "Bas-Saint-Laurent (01)", "MRC La Matapédia (070)"),
        municipalite("Saint-Simon", "Municipalité", "J0H1Y0", "54090", "Montérégie (16)", "MRC Les Maskoutains (540)"),
        municipalite("Saint-Majorique-de-Grantham", "Paroisse", "J2B8A8", "49095", "Centre-du-Québec (17)", "MRC Drummond (490)"),
        municipalite("Notre-Dame-du-Bon-Conseil", "Village", "J0C1A0", "49075", "Centre-du-Québec (17)", "MRC Drummond (490)"),
        municipalite("Notre-Dame-du-Bon-Conseil", "Paroisse", "J0C1A0", "49080", "Centre-du-Québec (17)", "MRC Drummond (490)"),
        municipalite("Albanel", "Municipalité", "G8M3J5", "92030", "Saguenay--Lac-Saint-Jean (02)", "MRC Maria-Chapdelaine (920)"),
        municipalite("Rivière-Saint-Jean", "Municipalité", "G0G2N0", "98050", "Côte-Nord (09)", "MRC Minganie (981)"),
        municipalite("Rivière-Saint-Jean", "Territoire non organisé", "", "03902", "Gaspésie--Îles-de-la-Madeleine (11)", "MRC La Côte-de-Gaspé (030)"),
        municipalite("Saint-René", "Paroisse", "G0M1Z0", "29050", "Chaudière-Appalaches (12)", "MRC Beauce-Sartigan (290)"),
        municipalite("Sainte-Irène", "Paroisse", "G0J2P0", "07040", "Bas-Saint-Laurent (01)", "MRC La Matapédia (070)"),
        municipalite("Mille-Isles", "Municipalité", "J0R1A0", "76030", "Laurentides (15)", "MRC Argenteuil (760)"),
        municipalite("Montréal", "Ville", "H2Y1C6", "66023", "Montréal (06)", ""),
    )]
    mrc = [{"mrcnom": "Lac-Saint-Jean-Est", "mrccod": "AR930", "mrccodp": "G8B1V3",
            "mrcregion": "Saguenay--Lac-Saint-Jean (02)"},
           # Le répertoire abrège le nom de cette communauté, et pas celui de Québec.
           {"mrcnom": "Comm. métropolitaine de Montréal", "mrccod": "CM663", "mrccodp": "H3A2N4", "mrcregion": ""}]
    # Le nom de la régie est coupé en deux champs, comme dans le fichier du ministère.
    perimunicipaux = list(ET.fromstring(
        "<liste><o><NOM_L1>Régie intermunicipale d'assainissement des eaux usées de Rougemo</NOM_L1>"
        "<NOM_L2>nt/Saint-Césaire</NOM_L2><COD_POST>J0L1T0</COD_POST></o></liste>"))
    index = contexte.construire_index(municipalites, mrc, perimunicipaux)
    return index, contexte.construire_index_tolerant(index), contexte.construire_index_des_codes(municipalites, mrc)


def code_de(correspondance):
    """Le code géographique d'une correspondance, ou son nom pour un organisme périmunicipal."""
    ligne = correspondance[1]
    return ligne.get("mcode") or ligne.get("mrccod") or ligne.get("nom")


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


class LectureDuNomTests(unittest.TestCase):
    """Avant de comparer, on sépare le nom lui-même des indices écrits autour."""

    def test_tolerance_grows_with_the_length_of_the_word(self):
        self.assertEqual(contexte.tolerance("paul", "paule"), 0)        # 4 lettres : aucune faute
        self.assertEqual(contexte.tolerance("simon", "simeon"), 1)      # 5 à 8 lettres : une faute
        self.assertEqual(contexte.tolerance("temiscamingue", "temiscaming"), 2)   # 9 lettres ou plus : deux

    def test_two_swapped_letters_count_as_one_mistake(self):
        # L'exemple donné en rencontre : « batiment » et « batimnet ».
        self.assertTrue(contexte.nom_proche(["batimnet"], "batiment"))
        self.assertFalse(contexte.nom_proche(["batiment"], "batiment"))   # identique : ce n'est pas un nom approché
        self.assertFalse(contexte.nom_proche(["paul"], "paule"))          # mot trop court pour tolérer une faute

    def test_abbreviations_and_determiners_do_not_matter(self):
        self.assertEqual(contexte.mots_utiles("Lac-St-Jean-Est"), contexte.mots_utiles("Lac-Saint-Jean-Est"))
        self.assertEqual(contexte.mots_utiles("Saint-Léon-de-Standon"), ["saint", "leon", "standon"])
        self.assertEqual(contexte.mots_utiles("Ste-Gertrude-Manneville"), ["sainte", "gertrude", "manneville"])

    def test_designation_is_read_at_the_end_or_in_parentheses(self):
        self.assertEqual(contexte.lire_nom_seao("Municipalité de Marston-Canton")["designation"], "Canton")
        self.assertEqual(contexte.lire_nom_seao("Municipalité de Marston-Canton")["mots"], ["marston"])
        self.assertEqual(contexte.lire_nom_seao("Municipalité de Melbourne (Canton)")["designation"], "Canton")

    def test_place_in_parentheses_is_kept_as_a_clue(self):
        lecture = contexte.lire_nom_seao("Municipalité de Saint-Stanislas (Saguenay Lac-St-Jean)")
        self.assertEqual(lecture["mots"], ["saint", "stanislas"])
        self.assertEqual(lecture["parentheses"], [["saguenay", "lac", "saint", "jean"]])

    def test_misspelled_or_abbreviated_municipalite_is_recognised(self):
        self.assertEqual(contexte.lire_nom_seao("Muncipalité d'Albanel")["mots"], ["albanel"])
        self.assertEqual(contexte.lire_nom_seao("M. Baie Sainte Catherine")["mots"], ["baie", "sainte", "catherine"])
        self.assertEqual(contexte.lire_nom_seao("M. Baie Sainte Catherine")["attendu"], "municipalité")

    def test_short_designations_are_not_guessed(self):
        # « Mille » n'est qu'à une lettre de « Ville » : on ne le prend pas pour une désignation.
        self.assertEqual(contexte.lire_nom_seao("Mille-Isles (Laurentides)")["mots"], ["mille", "isles"])


class RapprochementTolerantTests(unittest.TestCase):
    """Quand le nom exact ne trouve rien : rattraper l'écriture du SEAO, sans deviner."""

    def setUp(self):
        self.index, self.tolerant, self.par_code = petit_repertoire()

    def rapprocher(self, nom, codes_postaux=frozenset()):
        return contexte.rapprocher(nom, self.tolerant, codes_postaux)

    def test_missing_determiner_finds_the_same_name(self):
        choix, explication, _ = self.rapprocher("Municipalité de Saint-Léon-Standon")
        self.assertEqual(code_de(choix), "19020")
        self.assertIn(contexte.MEME_NOM, explication)

    def test_region_in_parentheses_separates_two_homonyms(self):
        choix, _, _ = self.rapprocher("Municipalité de Saint-Léon-le-Grand (Mauricie)")
        self.assertEqual(code_de(choix), "51035")

    def test_region_that_fits_no_candidate_blocks_the_match(self):
        # Une seule Albanel existe, mais elle n'est pas en Estrie : on ne la retient pas.
        choix, _, candidats = self.rapprocher("Municipalité d'Albanel (Estrie)")
        self.assertIsNone(choix)
        self.assertEqual([code_de(c) for c in candidats], ["92030"])

    def test_designation_at_the_end_separates_village_and_parish(self):
        # Le village et la paroisse ont le même code postal : seule la désignation les sépare.
        choix, _, _ = self.rapprocher("Municipalité de Notre-Dame-du-Bon-Conseil Village", {"J0C1A0"})
        self.assertEqual(code_de(choix), "49075")

    def test_precision_added_to_the_name_must_be_confirmed(self):
        # « Matapédia » est la MRC d'un des deux Saint-Damase : la précision confirme.
        choix, _, _ = self.rapprocher("Municipalité de Saint-Damase-de-Matapédia")
        self.assertEqual(code_de(choix), "07105")
        # « Bagot » n'est ni une région ni une MRC : sans code postal, on ne retient rien.
        choix, _, candidats = self.rapprocher("Municipalité de Saint-Simon-de-Bagot")
        self.assertIsNone(choix)
        self.assertEqual([code_de(c) for c in candidats], ["54090"])
        choix, _, _ = self.rapprocher("Municipalité de Saint-Simon-de-Bagot", {"J0H1Y0"})
        self.assertEqual(code_de(choix), "54090")

    def test_shortened_name_must_be_confirmed(self):
        choix, explication, candidats = self.rapprocher("Municipalité de Saint-Majorique")
        self.assertIsNone(choix)
        self.assertIn("aucun indice", explication)
        self.assertEqual([code_de(c) for c in candidats], ["49095"])
        choix, _, _ = self.rapprocher("Municipalité de Saint-Majorique", {"J2B8A8"})
        self.assertEqual(code_de(choix), "49095")

    def test_typo_is_accepted_only_with_a_confirming_clue(self):
        # « Albanle » : deux lettres inversées dans un mot de 7 lettres.
        choix, _, candidats = self.rapprocher("Municipalité d'Albanle")
        self.assertIsNone(choix)
        self.assertEqual([code_de(c) for c in candidats], ["92030"])
        choix, explication, _ = self.rapprocher("Municipalité d'Albanle", {"G8M3J5"})
        self.assertEqual(code_de(choix), "92030")
        self.assertIn(contexte.NOM_APPROCHE, explication)

    def test_typo_close_to_another_town_is_not_accepted_without_a_clue(self):
        # Cas trouvé en introduisant des fautes exprès : « Sainte-Irène » avec une lettre en
        # moins ressemble à « Saint-René ». Sans indice, on propose le candidat sans le retenir.
        choix, _, candidats = self.rapprocher("Municipalité de Sainte-Rene")
        self.assertIsNone(choix)
        self.assertEqual([code_de(c) for c in candidats], ["29050"])

    def test_unorganised_territory_is_set_aside(self):
        # Rivière-Saint-Jean est une municipalité de la Côte-Nord et un territoire non organisé de Gaspésie.
        choix, _, _ = self.rapprocher("Municipalité de Rivière St-Jean")
        self.assertEqual(code_de(choix), "98050")

    def test_expected_type_is_respected(self):
        choix, _, _ = self.rapprocher("MRC de Lac-St-Jean-Est")
        self.assertEqual(code_de(choix), "AR930")
        # Aucune municipalité ne porte ce nom : on ne rattache pas une municipalité à une MRC.
        choix, explication, _ = self.rapprocher("Municipalité de Lac-St-Jean-Est")
        self.assertIsNone(choix)
        self.assertIn("type attendu", explication)

    def test_contradicting_clues_leave_the_case_open(self):
        # Le nom désigne le Saint-Damase de La Matapédia, le code postal celui de la Montérégie.
        choix, explication, _ = self.rapprocher("Municipalité de Saint-Damase-de-Matapédia", {"J0H1J0"})
        self.assertIsNone(choix)
        self.assertIn("contradictoires", explication)

    def test_typo_in_an_intermunicipal_board_name(self):
        # Cas réel : le SEAO écrit « Rougement » pour Rougemont, et « St » pour Saint.
        nom = "Régie Intermunicipale d'assainissement des eaux usées de Rougement/St-Césaire"
        self.assertIsNone(self.rapprocher(nom)[0])
        choix, _, _ = self.rapprocher(nom, {"J0L1T0"})
        self.assertEqual(choix[0], "organisme périmunicipal")

    def test_unknown_name_finds_nothing(self):
        self.assertEqual(self.rapprocher("Bixi Montréal"), (None, "aucun candidat", []))


class RattachementTests(unittest.TestCase):
    """L'ordre des essais : le code déjà inscrit, le nom exact, puis les règles tolérantes."""

    def setUp(self):
        self.index, self.tolerant, self.par_code = petit_repertoire()

    def rattacher(self, organisme, code="À compléter"):
        ligne = {"organisme": organisme, "buyer_ids": "OP-1", "code_geographique": code}
        return contexte.rattacher(ligne, self.index, self.tolerant, self.par_code, {})

    def test_code_written_in_the_context_wins_over_the_name(self):
        # C'est ainsi qu'on règle un homonyme à la main : on écrit le code, le programme fait le reste.
        correspondance, methode, echec = self.rattacher("Municipalité de Saint-Damase", code="07105")
        self.assertEqual(code_de(correspondance), "07105")
        self.assertIn("code géographique", methode)
        self.assertIsNone(echec)

    def test_unknown_code_is_reported_not_guessed(self):
        correspondance, _, echec = self.rattacher("Municipalité de Saint-Damase", code="99999")
        self.assertIsNone(correspondance)
        self.assertEqual(echec[0], "absent")
        self.assertIn("99999", echec[1])

    def test_exact_name_needs_no_explanation(self):
        correspondance, methode, echec = self.rattacher("Municipalité d'Albanel")
        self.assertEqual(code_de(correspondance), "92030")
        self.assertIsNone(methode)
        self.assertIsNone(echec)

    def test_homonyms_without_a_clue_are_listed_with_their_codes(self):
        correspondance, _, echec = self.rattacher("Municipalité de Saint-Damase")
        self.assertIsNone(correspondance)
        self.assertEqual(echec[0], "ambigu")
        self.assertIn("07105", echec[1])
        self.assertIn("54017", echec[1])

    def test_type_announced_by_the_name_must_exist_in_the_directory(self):
        # Cas réel : le répertoire écrit « Comm. métropolitaine de Montréal ». Tant que ce nom
        # n'était pas reconnu, la communauté recevait la population de la Ville de Montréal.
        correspondance, _, _ = self.rattacher("Communauté métropolitaine de Montréal")
        self.assertEqual(code_de(correspondance), "CM663")
        correspondance, _, _ = self.rattacher("Ville de Montréal")
        self.assertEqual(code_de(correspondance), "66023")
        # Aucune MRC ne s'appelle Albanel : on ne donne pas à une MRC les chiffres d'une municipalité.
        correspondance, _, echec = self.rattacher("MRC d'Albanel")
        self.assertIsNone(correspondance)
        self.assertEqual(echec[0], "ambigu")
        self.assertIn("type attendu", echec[1])

    def test_non_municipal_organisms_are_set_apart(self):
        # Ni municipalité ni MRC dans le nom, et inconnu du répertoire : rien à compléter.
        self.assertEqual(self.rattacher("Bixi Montréal")[2][0], "non municipal")
        # Un nom qui annonce une municipalité devrait être dans le répertoire : il reste à vérifier.
        self.assertEqual(self.rattacher("Municipalité de Quelquepart")[2][0], "absent")

    def test_tolerant_rule_is_named_in_the_method(self):
        _, methode, _ = self.rattacher("Muncipalité d'Albanel")
        self.assertTrue(methode.startswith("nom rapproché"))


class EtiquettesTests(unittest.TestCase):
    """Une case sans chiffre dit pourquoi : à compléter, sans objet, hors MRC ou aucune donnée."""

    def test_fields_that_do_not_apply_to_an_mrc_are_marked(self):
        valeurs = contexte.valeurs_mrc({"mrccod": "AR930", "mrcpopul": "53866", "msupf": "2789.5",
                                        "mrcregion": "Saguenay--Lac-Saint-Jean (02)"}, "source")
        self.assertEqual(valeurs["region_administrative"], "Saguenay--Lac-Saint-Jean (02)")
        for champ in ("mrc", "classe_taille", "particularites_infrastructures"):
            self.assertEqual(valeurs[champ], contexte.SANS_OBJET)

    def test_metropolitan_community_has_no_single_region(self):
        # Cas réel : le répertoire ne donne aucune région aux deux communautés métropolitaines.
        valeurs = contexte.valeurs_mrc({"mrccod": "CM663", "mrcpopul": "4305251", "mrcregion": ""}, "source")
        self.assertEqual(valeurs["region_administrative"], contexte.SANS_OBJET)

    def test_town_outside_any_mrc_is_marked(self):
        # Cas réel : Montréal ne fait partie d'aucune MRC, et le répertoire laisse la case vide.
        valeurs = contexte.valeurs_municipalite({"mcode": "66023", "mpopul": "1913561", "mrc": ""}, {}, "source")
        self.assertEqual(valeurs["mrc"], contexte.HORS_MRC)

    def test_water_data_published_without_values_says_so(self):
        eau = {"12345": {"classe": "Aucune donnée", "pop_desservie": "NULL", "validite": ""}}
        valeurs = contexte.valeurs_municipalite({"mcode": "12345", "mrc": "MRC Test (123)"}, eau, "source")
        self.assertEqual(valeurs["classe_taille"], "Aucune donnée")
        self.assertEqual(valeurs["particularites_infrastructures"], contexte.AUCUNE_DONNEE)

    def test_town_missing_from_the_water_files_stays_to_complete(self):
        # Absente des fichiers, la donnée pourrait venir dans une prochaine édition : rien n'est inscrit.
        valeurs = contexte.valeurs_municipalite({"mcode": "14082", "mrc": "MRC Kamouraska (140)"}, {}, "source")
        self.assertEqual(valeurs["particularites_infrastructures"], "")

    def test_labels_never_replace_a_value_already_written(self):
        ligne = {"mrc": "MRC saisie à la main", "classe_taille": "À compléter"}
        contexte.remplir_ligne(ligne, {"mrc": contexte.SANS_OBJET, "classe_taille": contexte.SANS_OBJET})
        self.assertEqual(ligne, {"mrc": "MRC saisie à la main", "classe_taille": contexte.SANS_OBJET})

    def test_empty_note_becomes_blank_but_a_written_note_is_kept(self):
        vide, ecrite = {"notes": "À compléter"}, {"notes": "Vérifié par téléphone"}
        self.assertTrue(contexte.vider_note(vide))
        self.assertFalse(contexte.vider_note(ecrite))
        self.assertEqual((vide["notes"], ecrite["notes"]), ("", "Vérifié par téléphone"))


class SourcesTests(unittest.TestCase):
    """Lecture des fichiers de référence et des vues produites par l'analyse."""

    def test_water_codes_without_leading_zero_are_completed(self):
        # Cas réel : le fichier de validité écrit « 3005 » pour Gaspé, celui des fuites « 03005 ».
        eau = contexte.construire_donnees_eau(
            fuites=[{"num_c": "03005", "indice_fuites_ifi": "1.8100"}],
            validite=[{"mun_c": "3005", "cl_pop_desservie": "10 000 à 24 999 personnes",
                       "pop_desservie": "12000", "pourc_indice_validite": "80"}],
            consommation=[{"mun_c": "3005", "consom_resid": "250"}])
        self.assertEqual(list(eau), ["03005"])
        self.assertEqual(eau["03005"]["classe"], "10 000 à 24 999 personnes")
        self.assertEqual(eau["03005"]["indice_fuites"], "1.810")
        self.assertEqual(eau["03005"]["consommation"], "250")

    def test_name_cut_in_two_fields_is_put_back_together(self):
        # Le ministère coupe les noms à 60 caractères : la suite est dans NOM_L2.
        index, _, _ = petit_repertoire()
        cle = contexte.cle_organisme("Régie intermunicipale d'assainissement des eaux usées de Rougemont/Saint-Césaire")
        self.assertEqual(index[cle][0][1]["code_postal"], "J0L1T0")

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
