"""Tests de config/regles_reperage.toml : sa lecture, sa validation, et les messages des programmes.

Les tests qui remplacent le fichier vident le cache de regles() avant et après : aucun ne laisse de
règles de test en mémoire pour les suivants.
"""

import io
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import analyser_seao
import charger_base
from barometre import configuration
from barometre.regles import regles

RACINE = Path(__file__).resolve().parent.parent


def regles_du_depot():
    """Une copie modifiable du contenu du fichier du dépôt, lue sans passer par le cache."""
    with configuration.FICHIER_REGLES.open("rb") as fichier:
        return tomllib.load(fichier)


class LectureTests(unittest.TestCase):
    """Le fichier : présent, absent, mal formé, et la version de Python."""

    def test_le_fichier_du_depot_se_charge_et_passe_la_validation(self):
        donnees = configuration.charger_regles()
        self.assertEqual(donnees["version"], 1)
        self.assertEqual(set(donnees) - {"version"}, set(configuration.GROUPES))

    def test_fichier_absent(self):
        with tempfile.TemporaryDirectory() as dossier:
            with self.assertRaises(configuration.ConfigurationInvalide) as contexte:
                configuration.charger_regles(Path(dossier) / "absent.toml")
        self.assertIn("absent.toml", str(contexte.exception))
        self.assertIn("introuvable", str(contexte.exception))

    def test_toml_mal_forme(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "regles.toml"
            chemin.write_text("version = = 1\n", encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationInvalide) as contexte:
                configuration.charger_regles(chemin)
        self.assertIn("syntaxe TOML invalide", str(contexte.exception))
        self.assertIn("line 1", str(contexte.exception))

    def test_version_de_python_trop_ancienne(self):
        with patch.object(configuration.sys, "version_info", (3, 10, 12)):
            with self.assertRaises(configuration.ConfigurationInvalide) as contexte:
                configuration.charger_regles()
        self.assertIn("Python 3.11 ou plus récent", str(contexte.exception))
        self.assertIn("3.10", str(contexte.exception))


class ValidationTests(unittest.TestCase):
    """Le contenu : clés, types, documentation, motifs et mots."""

    def refuse(self, modifier, *fragments):
        donnees = regles_du_depot()
        modifier(donnees)
        with self.assertRaises(configuration.ConfigurationInvalide) as contexte:
            configuration.valider(donnees, "essai.toml")
        for fragment in fragments:
            self.assertIn(fragment, str(contexte.exception))

    def test_cle_manquante(self):
        self.refuse(lambda d: d["gestion_actifs_eau"].pop("outil"), "clé manquante", "gestion_actifs_eau.outil")

    def test_cle_inconnue(self):
        self.refuse(lambda d: d["lie_eau"].update(mots_cle=["aqueduc"]), "clé inconnue", "lie_eau.mots_cle")

    def test_version_du_fichier_non_prise_en_charge(self):
        self.refuse(lambda d: d.update(version=2), "version 2", "non prise en charge")

    def test_mauvais_type(self):
        self.refuse(lambda d: d["lie_eau"].update(mots_cles="aqueduc"), "lie_eau.mots_cles", "liste non vide")

    def test_documentation_vide(self):
        self.refuse(lambda d: d["pga_eau"].update(source="   "), "pga_eau.source", "texte non vide")

    def test_motif_vide_ou_qui_correspond_au_texte_vide(self):
        for valeur, raison in (("", "motif vide"), ("   ", "motif vide"), ("logiciel|", "texte vide")):
            with self.subTest(valeur=valeur):
                self.refuse(lambda d: d["gestion_actifs_eau"].update(outil=valeur), "gestion_actifs_eau.outil", raison)

    def test_motif_invalide(self):
        self.refuse(lambda d: d["gestion_actifs_eau"].update(outil="logiciel("), "gestion_actifs_eau.outil",
                    "motif invalide")

    def test_motif_recompose_du_test_etape(self):
        # Ce cadre est valide seul, mais un drapeau global (?i) au milieu du motif recomposé ne l'est pas.
        def modifier(donnees):
            donnees["gestion_actifs_eau"]["etape_cadres"][0] = r"(?i)\bpga\b"
        self.refuse(modifier, "motif recomposé", "motif invalide")

    def test_mots_en_majuscules_ou_avec_apostrophe_courbe(self):
        cas = (("lie_eau", "mots_cles", "Aqueduc", "écrire « aqueduc »"),
               ("lie_eau", "mots_cles", "station d’épuration", "écrire « station d'épuration »"),
               ("pga_eau", "mots_requis", "Gestion", "écrire « gestion »"))
        for groupe, cle, mot, conseil in cas:
            with self.subTest(mot=mot):
                self.refuse(lambda d: d[groupe][cle].append(mot), f"{groupe}.{cle}", conseil)


class PointsEntreeTests(unittest.TestCase):
    """Avec un fichier de règles absent, les programmes affichent le message et rendent 1."""

    def setUp(self):
        regles.cache_clear()
        self.addCleanup(regles.cache_clear)
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        remplacement = patch.object(configuration, "FICHIER_REGLES", Path(dossier.name) / "absent.toml")
        remplacement.start()
        self.addCleanup(remplacement.stop)

    def test_analyser_seao_s_arrete_avant_de_lire_l_export(self):
        with patch.object(analyser_seao.sys, "argv", ["analyser_seao.py", "export_absent.json"]), \
                redirect_stdout(io.StringIO()) as sortie, redirect_stderr(io.StringIO()) as erreurs:
            self.assertEqual(analyser_seao.main(), 1)
        self.assertIn("règles de repérage invalides", erreurs.getvalue())
        self.assertIn("absent.toml", erreurs.getvalue())
        self.assertNotIn("export_absent.json", sortie.getvalue() + erreurs.getvalue())

    def test_charger_base_s_arrete_avant_toute_connexion(self):
        connecter = MagicMock()
        with patch.object(charger_base.sys, "argv", ["charger_base.py"]), \
                patch.object(charger_base, "connecter", connecter), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as erreurs:
            self.assertEqual(charger_base.main(), 1)
        connecter.assert_not_called()
        self.assertIn("avant toute connexion", erreurs.getvalue())
        self.assertIn("absent.toml", erreurs.getvalue())


class ImportsTests(unittest.TestCase):
    """Importer un programme ne lit pas les règles : exporter_carte.py n'en dépend pas."""

    def test_importer_les_programmes_ne_lit_pas_les_regles(self):
        code = ("import barometre.configuration as c\n"
                "def interdit(*args, **kwargs):\n"
                "    raise AssertionError('règles lues pendant un import')\n"
                "c.charger_regles = interdit\n"
                "import exporter_carte, charger_base, analyser_seao\n"
                "print('aucune lecture')\n")
        resultat = subprocess.run([sys.executable, "-B", "-c", code], cwd=RACINE, capture_output=True,
                                  encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertIn("aucune lecture", resultat.stdout)


if __name__ == "__main__":
    unittest.main()
