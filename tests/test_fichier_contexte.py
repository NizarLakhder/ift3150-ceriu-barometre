"""Tests de la lecture et de la réécriture du fichier de contexte (barometre/contexte/fichier.py).

Le format couvert est celui qu'écrit reecrire_contexte : UTF-8 avec BOM, fins de ligne CRLF,
guillemets seulement autour d'une cellule qui contient une virgule, un guillemet ou un saut de ligne.
"""

import tempfile
import unittest
from pathlib import Path

from barometre.contexte.fichier import lire_contexte, reecrire_contexte

COLONNES = ["organisme", "buyer_ids", "population", "notes", "colonne_a_la_main"]
CONTENU = ("﻿" + ",".join(COLONNES) + "\r\n"
           + '"Ville de Saint-Léon-de-Standon, secteur ""est""",11 | 12,À compléter,,ajoutée à la main\r\n'
           + 'Municipalité de Lac-Mégantic,13,5 932,"note sur\r\ndeux lignes",\r\n').encode("utf-8")


class FichierContexteTests(unittest.TestCase):

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.chemin = Path(dossier.name) / "contexte.csv"
        self.chemin.write_bytes(CONTENU)
        self.sauvegardes = Path(dossier.name) / "sorties"

    def test_relire_puis_reecrire_rend_le_meme_fichier_octet_pour_octet(self):
        colonnes, lignes = lire_contexte(self.chemin)
        self.assertEqual(colonnes, COLONNES)
        self.assertEqual(lignes[0]["organisme"], 'Ville de Saint-Léon-de-Standon, secteur "est"')
        self.assertEqual(lignes[1]["notes"], "note sur\r\ndeux lignes")
        reecrire_contexte(self.chemin, colonnes, lignes, self.sauvegardes)
        self.assertEqual(self.chemin.read_bytes(), CONTENU)

    def test_la_reecriture_garde_les_colonnes_et_sauvegarde_d_abord(self):
        colonnes, lignes = lire_contexte(self.chemin)
        lignes[0]["population"] = "1 234"
        reecrire_contexte(self.chemin, colonnes, lignes, self.sauvegardes)
        self.assertEqual((self.sauvegardes / "contexte.csv.bak").read_bytes(), CONTENU)
        colonnes_relues, relues = lire_contexte(self.chemin)
        self.assertEqual(colonnes_relues, COLONNES)
        self.assertEqual(relues[0]["population"], "1 234")
        self.assertEqual(relues[0]["colonne_a_la_main"], "ajoutée à la main")

        # Une écriture qui échoue en cours de route : la sauvegarde du fichier d'avant est déjà faite.
        avant = self.chemin.read_bytes()
        self.assertNotEqual(avant, CONTENU)
        lignes[0]["colonne_inconnue"] = "x"
        with self.assertRaises(ValueError):
            reecrire_contexte(self.chemin, colonnes, lignes, self.sauvegardes)
        self.assertEqual((self.sauvegardes / "contexte.csv.bak").read_bytes(), avant)


if __name__ == "__main__":
    unittest.main()
