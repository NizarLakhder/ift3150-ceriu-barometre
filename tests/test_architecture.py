"""Tests de l'organisation du code : barometre/ n'importe ni un programme, ni aucun autre module du projet
posé à la racine.

Les programmes enchaînent les étapes et appellent barometre/ ; l'inverse créerait une dépendance circulaire.
Les bibliothèques de Python et les paquets installés restent permis. Seuls les vrais imports comptent, lus dans
l'arbre syntaxique : le nom d'un programme dans un commentaire ou une docstring n'en est pas un.
"""

import ast
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PROGRAMMES = {"analyser_seao", "completer_contexte", "charger_base", "exporter_carte"}


def modules_importes(arbre):
    """Les modules importés : import x, from x import y, même à l'intérieur d'une fonction."""
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            yield from (alias.name for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            yield noeud.module


def modules_de_la_racine():
    """Les modules du projet posés à la racine : chaque fichier .py et chaque dossier avec un __init__.py."""
    paquets = {p.parent.name for p in RACINE.glob("*/__init__.py")}
    return ({p.stem for p in RACINE.glob("*.py")} | paquets) - {"barometre"}


class ArchitectureTests(unittest.TestCase):

    def test_barometre_n_importe_aucun_programme(self):
        self.assertTrue(all((RACINE / f"{p}.py").is_file() for p in PROGRAMMES))
        fichiers = sorted((RACINE / "barometre").rglob("*.py"))
        self.assertGreater(len(fichiers), 20)
        fautifs = {}
        for chemin in fichiers:
            importes = {m.split(".")[0] for m in modules_importes(ast.parse(chemin.read_text(encoding="utf-8")))}
            if importes & PROGRAMMES:
                fautifs[chemin.relative_to(RACINE).as_posix()] = sorted(importes & PROGRAMMES)
        self.assertEqual(fautifs, {})

    def test_barometre_n_importe_aucun_module_de_la_racine(self):
        # Seuls les modules du projet comptent : csv, psycopg et les autres bibliothèques restent permis.
        racine = modules_de_la_racine()
        self.assertTrue(PROGRAMMES <= racine)
        vus, fautifs = set(), {}
        for chemin in sorted((RACINE / "barometre").rglob("*.py")):
            importes = {m.split(".")[0] for m in modules_importes(ast.parse(chemin.read_text(encoding="utf-8")))}
            vus |= importes
            if importes & racine:
                fautifs[chemin.relative_to(RACINE).as_posix()] = sorted(importes & racine)
        self.assertIn("barometre", vus)  # les imports ont bien été lus
        self.assertEqual(fautifs, {})


if __name__ == "__main__":
    unittest.main()
