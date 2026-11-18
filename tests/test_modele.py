"""Tests des classes de tables (barometre/modele/) : fidèles à schema.sql, et la même écriture qu'avant.

Aucune connexion : une doublure de connexion note la requête et les valeurs passées à executemany.
"""

import re
import typing
import unittest
from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import NoneType, UnionType
from unittest.mock import MagicMock

from barometre.modele.territoire import FichierReference, IndicateurEau, Mrc, Municipalite, Region

RACINE = Path(__file__).resolve().parent.parent
CLASSES = (FichierReference, Region, Mrc, Municipalite, IndicateurEau)
TYPES_SQL = {"text": str, "char": str, "varchar": str, "integer": int, "smallint": int, "bigint": int,
             "numeric": Decimal, "date": date, "timestamptz": datetime, "boolean": bool}
CONTRAINTES = r"\s+(?:NOT|NULL|PRIMARY|UNIQUE|REFERENCES|DEFAULT|CHECK|GENERATED|COLLATE|CONSTRAINT)\b"


def tables_du_schema():
    """{table : colonnes et clés} lus dans schema.sql : nom, type, case vide permise, identité, défaut."""
    tables = {}
    for nom, corps in re.findall(r"CREATE TABLE\s+([\w.]+)\s*\((.*?)\n\);", (RACINE / "schema.sql").read_text(encoding="utf-8"), re.S):
        colonnes, cles = [], []
        for ligne in corps.splitlines():
            ligne = ligne.split("--")[0].strip().rstrip(",")
            if not ligne:
                continue
            contrainte = re.match(r"(PRIMARY KEY|UNIQUE)\s*\(([^)]*)\)", ligne)
            if contrainte:
                cles.append(tuple(c.strip() for c in contrainte.group(2).split(",")))
                continue
            if re.match(r"(CHECK|FOREIGN KEY|CONSTRAINT|EXCLUDE)\b", ligne):
                continue
            colonne, reste = ligne.split(None, 1)
            if "PRIMARY KEY" in reste or re.search(r"\bUNIQUE\b", reste):
                cles.append((colonne,))
            colonnes.append({"nom": colonne, "type": re.split(CONTRAINTES, reste, maxsplit=1)[0].strip(),
                             "vide_permis": "NOT NULL" not in reste and "PRIMARY KEY" not in reste,
                             "identite": "GENERATED" in reste, "defaut": "DEFAULT" in reste})
        tables[nom] = {"colonnes": colonnes, "cles": cles}
    return tables


SCHEMA = tables_du_schema()


def type_du_schema(colonne):
    """(type Python de base, liste ou non, case vide permise) d'une colonne de schema.sql."""
    return TYPES_SQL[re.match(r"[a-z]+", colonne["type"]).group()], colonne["type"].endswith("[]"), colonne["vide_permis"]


def type_annote(annotation):
    """(type de base, liste ou non, case vide permise) de l'annotation d'un champ."""
    vide = False
    if isinstance(annotation, UnionType):
        arguments = [a for a in typing.get_args(annotation) if a is not NoneType]
        vide = len(arguments) < len(typing.get_args(annotation))
        (annotation,) = arguments
    if typing.get_origin(annotation) is list:
        return typing.get_args(annotation)[0], True, vide
    return annotation, False, vide


def municipalite(**valeurs):
    champs = dict(code_geographique="66097", nom="Pointe-Claire", designation="Ville", population=31380,
                  superficie_km2=Decimal("34.5"), superficie_terrestre_km2=Decimal("18.9"), code_postal="H9R 4S9",
                  date_constitution=date(1911, 3, 14), region_code="06", mrc_code=None, communaute_code="CM663",
                  anciens_codes=[], anciens_noms=[])
    champs.update(valeurs)
    return Municipalite(**champs)


def appels_ecrits(classe, objets):
    """Les appels à executemany que fait classe.inserer, sur une doublure de connexion."""
    connexion = MagicMock()
    classe.inserer(connexion, objets)
    return [appel.args for appel in connexion.cursor.return_value.__enter__.return_value.executemany.call_args_list]


class SchemaTests(unittest.TestCase):
    """Chaque classe décrit exactement sa table de schema.sql."""

    def test_chaque_classe_a_les_colonnes_de_sa_table_dans_le_meme_ordre(self):
        for classe in CLASSES:
            with self.subTest(table=classe.TABLE):
                self.assertIn(classe.TABLE, SCHEMA)
                self.assertEqual([c.name for c in fields(classe)], [c["nom"] for c in SCHEMA[classe.TABLE]["colonnes"]])

    def test_les_types_et_les_cases_vides_correspondent_au_schema(self):
        for classe in CLASSES:
            colonnes = {c["nom"]: c for c in SCHEMA[classe.TABLE]["colonnes"]}
            for champ in fields(classe):
                with self.subTest(colonne=f"{classe.TABLE}.{champ.name}"):
                    base, liste, vide = type_annote(champ.type)
                    base_sql, liste_sql, vide_sql = type_du_schema(colonnes[champ.name])
                    self.assertEqual((base, liste), (base_sql, liste_sql))
                    if not champ.metadata.get("genere"):  # une colonne générée est vide avant l'écriture
                        self.assertEqual(vide, vide_sql)

    def test_la_cle_de_chaque_classe_est_une_cle_primaire_ou_unique_du_schema(self):
        for classe in CLASSES:
            with self.subTest(table=classe.TABLE):
                self.assertIn(set(classe.CLE), [set(cle) for cle in SCHEMA[classe.TABLE]["cles"]])
                self.assertEqual(classe.CONFLIT, "DO UPDATE")  # le comportement des conflits d'avant

    def test_les_colonnes_generees_par_la_base_sont_marquees_et_jamais_ecrites(self):
        for classe in CLASSES:
            colonnes = {c["nom"]: c for c in SCHEMA[classe.TABLE]["colonnes"]}
            generees = {c.name for c in fields(classe) if c.metadata.get("genere")}
            with self.subTest(table=classe.TABLE):
                self.assertLessEqual({nom for nom, c in colonnes.items() if c["identite"]}, generees)
                self.assertTrue(all(colonnes[nom]["identite"] or colonnes[nom]["defaut"] for nom in generees))
                self.assertEqual(classe.colonnes(), [nom for nom in colonnes if nom not in generees])
        self.assertEqual({c.name for c in fields(FichierReference) if c.metadata.get("genere")},
                         {"fichier_reference_id", "charge_le"})


class TableTests(unittest.TestCase):
    """inserer écrit, pour chaque classe, la requête et les valeurs qu'écrivait charger_base.py."""

    def test_inserer_ecrit_la_requete_et_les_valeurs_attendues(self):
        objets = [municipalite(), municipalite(code_geographique="66102", nom="Kirkland", population=None)]
        ((requete, valeurs),) = appels_ecrits(Municipalite, objets)
        colonnes = [c.name for c in fields(Municipalite)]
        parametres = ", ".join("%(" + c + ")s" for c in colonnes)
        mises_a_jour = ", ".join(f"{c} = EXCLUDED.{c}" for c in colonnes if c != "code_geographique")
        self.assertEqual(requete, f"INSERT INTO territoire.municipalite ({', '.join(colonnes)}) VALUES ({parametres}) "
                                  f"ON CONFLICT (code_geographique) DO UPDATE SET {mises_a_jour}")
        self.assertEqual(valeurs, [objet.en_ligne() for objet in objets])
        self.assertEqual(list(valeurs[0]), colonnes)
        self.assertIsNone(valeurs[1]["population"])

    def test_une_cle_composee_et_des_colonnes_generees(self):
        eau = IndicateurEau(code_source="03005", annee=2024, nom_source="Gaspé", code_geographique="03005",
                            classe_population="10 000 à 24 999 personnes", population_desservie=14000,
                            indice_fuites=Decimal("0.565"), validite_audit_pct=Decimal("100"),
                            consommation_l_pers_jour=Decimal("250"), longueur_reseau_km=None)
        ((requete, _),) = appels_ecrits(IndicateurEau, [eau])
        self.assertIn("ON CONFLICT (code_source, annee) DO UPDATE SET nom_source = EXCLUDED.nom_source", requete)
        self.assertNotIn("code_source = EXCLUDED", requete)
        self.assertNotIn("annee = EXCLUDED", requete)

        fichier = FichierReference(nom="MUN.csv", description="Répertoire des municipalités",
                                   date_fichier=date(2026, 9, 29), empreinte_sha256="ab" * 32)
        ((requete, valeurs),) = appels_ecrits(FichierReference, [fichier])
        self.assertEqual(requete, "INSERT INTO territoire.fichier_reference (nom, description, date_fichier, empreinte_sha256) "
                                  "VALUES (%(nom)s, %(description)s, %(date_fichier)s, %(empreinte_sha256)s) "
                                  "ON CONFLICT (nom) DO UPDATE SET description = EXCLUDED.description, "
                                  "date_fichier = EXCLUDED.date_fichier, empreinte_sha256 = EXCLUDED.empreinte_sha256")
        self.assertEqual(valeurs, [{"nom": "MUN.csv", "description": "Répertoire des municipalités",
                                    "date_fichier": date(2026, 9, 29), "empreinte_sha256": "ab" * 32}])

    def test_inserer_sans_objet_n_ecrit_rien(self):
        connexion = MagicMock()
        Region.inserer(connexion, [])
        connexion.cursor.assert_not_called()


class TerritoireTests(unittest.TestCase):
    """La lecture d'une ligne du répertoire du MAMH, comme le faisait charger_territoire."""

    def test_une_municipalite_lue_dans_le_repertoire(self):
        ligne = {"mcode": " 66097 ", "munnom": " Pointe-Claire ", "mdes": "Ville", "mpopul": "31380", "msuperf": "34.5",
                 "msupft": "18.9", "mcodpos": "H9R 4S9", "mdatcons": "1911-03-14", "regadm": "Montréal (06)", "mrc": "",
                 "mcm": "Communauté métropolitaine de Montréal (663)"}
        anciens = {"66097": (["66102"], ["Ancienne municipalité"])}
        self.assertEqual(Municipalite.depuis_repertoire(ligne, anciens).en_ligne(), {
            "code_geographique": "66097", "nom": "Pointe-Claire", "designation": "Ville", "population": 31380,
            "superficie_km2": Decimal("34.5"), "superficie_terrestre_km2": Decimal("18.9"), "code_postal": "H9R 4S9",
            "date_constitution": date(1911, 3, 14), "region_code": "06", "mrc_code": None, "communaute_code": "CM663",
            "anciens_codes": ["66102"], "anciens_noms": ["Ancienne municipalité"]})
        vide = Municipalite.depuis_repertoire({**ligne, "mpopul": "À compléter", "mdatcons": "", "msupft": "NULL"}, {})
        self.assertEqual((vide.population, vide.date_constitution, vide.superficie_terrestre_km2, vide.anciens_codes),
                         (None, None, None, []))

    def test_une_mrc_lue_dans_le_repertoire(self):
        ligne = {"mrccod": " AR190 ", "mrcnom": " Bellechasse ", "mrcdescdesi": "MRC ", "mrcpopul": "38000",
                 "msupf": "1765.32", "mrccodp": "", "mrcregion": "Chaudière-Appalaches (12)"}
        self.assertEqual(Mrc.depuis_repertoire(ligne).en_ligne(), {
            "code": "AR190", "nom": "Bellechasse", "designation": "MRC", "population": 38000,
            "superficie_km2": Decimal("1765.32"), "code_postal": None, "region_code": "12"})


if __name__ == "__main__":
    unittest.main()
