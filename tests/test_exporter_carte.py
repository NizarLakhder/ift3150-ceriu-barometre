"""Tests d'exporter_carte.py : la construction des données de la carte, sans PostgreSQL ni réseau.

Commande : python -B -m unittest -v test_exporter_carte
"""

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import exporter_carte as carte

# Les 7 exports chargés au 8 novembre 2026 : juin et juillet manquent.
EXPORTS = [
    {"nom": "mensuel_20260501_20260531.json", "type": "mensuel", "debut": date(2026, 5, 1), "fin": date(2026, 5, 31)},
    {"nom": "mensuel_20260801_20260831.json", "type": "mensuel", "debut": date(2026, 8, 1), "fin": date(2026, 8, 31)},
    {"nom": "mensuel_20260901_20260930.json", "type": "mensuel", "debut": date(2026, 9, 1), "fin": date(2026, 9, 30)},
    {"nom": "hebdo_20260907_20260913.json", "type": "hebdomadaire", "debut": date(2026, 9, 7), "fin": date(2026, 9, 13)},
    {"nom": "hebdo_20260928_20261004.json", "type": "hebdomadaire", "debut": date(2026, 9, 28), "fin": date(2026, 10, 4)},
    {"nom": "hebdo_20261005_20261011.json", "type": "hebdomadaire", "debut": date(2026, 10, 5), "fin": date(2026, 10, 11)},
    {"nom": "hebdo_20261012_20261018.json", "type": "hebdomadaire", "debut": date(2026, 10, 12), "fin": date(2026, 10, 18)},
]

CARRE = {"type": "Polygon", "coordinates": [[[-66.4, 50.2], [-66.3, 50.2], [-66.3, 50.3], [-66.4, 50.2]]]}


def contour(code, nom, site="www.exemple.qc.ca"):
    return {"type": "Feature", "geometry": CARRE,
            "properties": {"MUS_CO_GEO": code, "MUS_NM_MUN": nom, "SITE_WEB": site, "MUS_CO_VER": "V2026-10"}}


def municipalite(code, nom, etat="aucune trace dans les exports chargés", designation="Ville", region="Côte-Nord"):
    return {"code": code, "nom": nom, "designation": designation, "population": 24456, "region": region,
            "mrc": "Sept-Rivières", "genre_mrc": "Municipalité régionale de comté", "etat": etat}


# Cas réel : le mandat de PGA-Eau de Sept-Îles, attribué le 8 septembre 2025.
SEPT_ILES = {"code": "97007", "organisme": "Ville de Sept-Îles", "classement": "elaboration",
             "etat": "mandat_attribue", "date_attribution": date(2025, 9, 8), "date_publication": date(2025, 6, 25),
             "montant": Decimal("63750.00"), "fournisseur": "TÉTRA TECH QI INC.", "lien": "https://seao.gouv.qc.ca/",
             "notes": None}

# Cas réel : la régie de Grand Pré n'a pas de contour de municipalité.
GRAND_PRE = {**SEPT_ILES, "code": None, "organisme": "Régie d'aqueduc de Grand Pré",
             "date_attribution": date(2026, 5, 21), "montant": Decimal("22995.00"), "fournisseur": "Proactifs"}


class TestPeriodes(unittest.TestCase):
    def test_les_exports_qui_se_recouvrent_forment_une_periode(self):
        self.assertEqual(carte.periodes_couvertes(EXPORTS), [
            {"debut": "2026-05-01", "fin": "2026-05-31"},
            {"debut": "2026-08-01", "fin": "2026-10-18"}])

    def test_deux_semaines_qui_se_suivent_se_rejoignent(self):
        semaines = [e for e in EXPORTS if e["type"] == "hebdomadaire"][1:]
        self.assertEqual(carte.periodes_couvertes(semaines), [{"debut": "2026-09-28", "fin": "2026-10-18"}])


class TestEtiquettes(unittest.TestCase):
    def test_nom_et_region(self):
        self.assertEqual(carte.etiquettes([municipalite("97007", "Sept-Îles")]), {"97007": "Sept-Îles, Côte-Nord"})

    def test_meme_nom_dans_la_meme_region(self):
        resultat = carte.etiquettes([municipalite("32033", "Plessisville", designation="Ville"),
                                     municipalite("32040", "Plessisville", designation="Paroisse")])
        self.assertEqual(resultat["32033"], "Plessisville (Ville), Côte-Nord")
        self.assertEqual(resultat["32040"], "Plessisville (Paroisse), Côte-Nord")

    def test_meme_nom_et_meme_designation(self):
        tno = [municipalite(code, "Toponyme à venir", designation="Territoire non organisé", region="Nord-du-Québec")
               for code in ("99908", "99910")]
        self.assertEqual(carte.etiquettes(tno)["99908"], "Toponyme à venir (Territoire non organisé 99908), Nord-du-Québec")


class TestContours(unittest.TestCase):
    def test_le_trace_de_1927_est_ecarte(self):
        contours = {"features": [contour("98904", "Lac-Jérôme (Tracé de 1927)"), contour("98904", "Lac-Jérôme")]}
        garde = carte.contour_par_code(contours, {"98904": "Lac-Jérôme"})
        self.assertEqual(garde["98904"]["properties"]["MUS_NM_MUN"], "Lac-Jérôme")

    def test_adresse_du_site(self):
        self.assertEqual(carte.lien_site("www.septiles.ca"), "https://www.septiles.ca")
        self.assertEqual(carte.lien_site("http://exemple.ca"), "http://exemple.ca")
        self.assertIsNone(carte.lien_site(None))
        self.assertIsNone(carte.lien_site("  "))


class TestConstruire(unittest.TestCase):
    def construire(self, municipalites, demarches=()):
        contours = {"features": [contour(m["code"], m["nom"]) for m in municipalites]}
        return carte.construire(contours, municipalites, list(demarches), EXPORTS, date(2026, 11, 8))

    def test_etat_et_demarche(self):
        donnees = self.construire([municipalite("97007", "Sept-Îles", "PGA-Eau repéré dans le SEAO")], [SEPT_ILES])
        fiche = donnees["territoires"]["features"][0]["properties"]
        self.assertEqual(fiche["etat"], "pga")
        self.assertEqual(fiche["genre_mrc"], "MRC")
        self.assertEqual(fiche["site"], "https://www.exemple.qc.ca")
        self.assertEqual(fiche["demarches"][0]["montant"], 63750.0)
        self.assertEqual(fiche["demarches"][0]["date_attribution"], "2025-09-08")
        self.assertEqual(donnees["version_contours"], "V2026-10")

    def test_un_outil_seul_a_son_propre_etat(self):
        donnees = self.construire([municipalite("66023", "Montréal", "outil seulement repéré dans le SEAO")])
        self.assertEqual(donnees["territoires"]["features"][0]["properties"]["etat"], "outil")

    def test_une_regie_reste_hors_carte(self):
        donnees = self.construire([municipalite("97007", "Sept-Îles")], [GRAND_PRE])
        self.assertEqual(donnees["hors_carte"][0]["organisme"], "Régie d'aqueduc de Grand Pré")
        self.assertEqual(donnees["territoires"]["features"][0]["properties"]["demarches"], [])

    def test_un_montant_absent_reste_absent(self):
        windsor = {**SEPT_ILES, "etat": "appel_offres_en_cours", "date_attribution": None, "montant": None,
                   "fournisseur": None}
        donnees = self.construire([municipalite("97007", "Sept-Îles", "PGA-Eau repéré dans le SEAO")], [windsor])
        demarche = donnees["territoires"]["features"][0]["properties"]["demarches"][0]
        self.assertIsNone(demarche["montant"])
        self.assertIsNone(demarche["date_attribution"])

    def test_un_contour_manquant_arrete_tout(self):
        with self.assertRaisesRegex(ValueError, "Contour introuvable"):
            carte.construire({"features": []}, [municipalite("97007", "Sept-Îles")], [], EXPORTS, date(2026, 11, 8))

    def test_un_etat_inconnu_arrete_tout(self):
        with self.assertRaisesRegex(ValueError, "État inconnu"):
            self.construire([municipalite("97007", "Sept-Îles", "plan adopté")])


class TestEcrire(unittest.TestCase):
    def test_le_fichier_se_relit(self):
        donnees = {"genere_le": "2026-11-08", "territoires": {"type": "FeatureCollection", "features": []}}
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "donnees.js"
            carte.ecrire(donnees, chemin)
            texte = chemin.read_text(encoding="utf-8")
        self.assertTrue(texte.startswith("// Produit par exporter_carte.py"))
        json_lu = texte.split("window.DONNEES = ", 1)[1].rstrip().rstrip(";")
        self.assertEqual(json.loads(json_lu), donnees)


if __name__ == "__main__":
    unittest.main()
