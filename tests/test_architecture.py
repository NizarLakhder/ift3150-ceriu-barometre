"""Test de l'organisation du code : barometre/ n'importe jamais un programme.

Les programmes enchaînent les étapes et appellent barometre/ ; l'inverse créerait une dépendance circulaire.
Seuls les vrais imports comptent, lus dans l'arbre syntaxique : le nom d'un programme dans un commentaire ou
une docstring n'en est pas un.
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


if __name__ == "__main__":
    unittest.main()
