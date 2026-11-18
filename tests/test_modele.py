"""Tests des classes de tables (barometre/modele/) : fidèles à schema.sql, et la même écriture qu'avant.

Aucune connexion : une doublure de connexion note la requête et les valeurs passées à executemany.
"""

import csv
import json
import re
import tempfile
import typing
import unittest
from contextlib import ExitStack
from dataclasses import fields
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import NoneType, UnionType
from unittest.mock import MagicMock, patch

from psycopg.types.json import Jsonb

import charger_base
import completer_contexte
from barometre.modele.analyses import Demarche, FicheClassee
from barometre.modele.organismes import Acheteur, Organisme
from barometre.modele.seao import (Attribution, Classification, Contrat, Dossier, Fiche, FicheClassification, FicheFichier,
                                   FichierSource, Fournisseur, IdentifiantFournisseur, Nomenclature, Soumissionnaire)
from barometre.modele.territoire import FichierReference, IndicateurEau, Mrc, Municipalite, Region
from tests.test_charger_base import MATAGAMI

RACINE = Path(__file__).resolve().parent.parent
CLASSES = (FichierReference, Region, Mrc, Municipalite, IndicateurEau, Organisme, Acheteur, FicheClassee, Demarche,
           FichierSource, Nomenclature, Classification, Fournisseur, IdentifiantFournisseur, Dossier, Fiche,
           FicheFichier, FicheClassification, Soumissionnaire, Attribution, Contrat)
# Le comportement des conflits d'avant, table par table ; None : pas de ON CONFLICT, un doublon arrête l'export.
CONFLITS_ATTENDUS = {FichierReference: "DO UPDATE", Region: "DO UPDATE", Mrc: "DO UPDATE", Municipalite: "DO UPDATE",
                     IndicateurEau: "DO UPDATE", Organisme: "DO UPDATE", Acheteur: "DO UPDATE",
                     FicheClassee: "DO UPDATE", Demarche: "DO NOTHING",
                     FichierSource: None, Nomenclature: "DO NOTHING", Classification: "DO NOTHING", Fournisseur: None,
                     IdentifiantFournisseur: None, Dossier: "DO NOTHING", Fiche: "DO NOTHING", FicheFichier: "DO NOTHING",
                     FicheClassification: "DO NOTHING", Soumissionnaire: "DO NOTHING", Attribution: "DO NOTHING",
                     Contrat: "DO NOTHING"}
TYPES_SQL = {"text": str, "char": str, "varchar": str, "integer": int, "smallint": int, "bigint": int,
             "numeric": Decimal, "date": date, "timestamptz": datetime, "boolean": bool, "jsonb": Jsonb, "tsvector": str}
CONTRAINTES = r"\s+(?:NOT|NULL|PRIMARY|UNIQUE|REFERENCES|DEFAULT|CHECK|GENERATED|COLLATE|CONSTRAINT)\b"


def tables_du_schema():
    """{table : colonnes et clés} lus dans schema.sql : nom, type, case vide permise, identité, défaut."""
    tables = {}
    for nom, corps in re.findall(r"CREATE TABLE\s+([\w.]+)\s*\((.*?)\n\);", (RACINE / "schema.sql").read_text(encoding="utf-8"), re.S):
        colonnes, cles = [], []
        for ligne in corps.splitlines():
            ligne = ligne.split("--")[0].strip().rstrip(",")
            if not ligne or ligne.startswith("("):  # « ( » : suite d'une colonne calculée (GENERATED ... STORED)
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
                             "identite": "GENERATED" in reste, "defaut": "DEFAULT" in reste,
                             "numerotee": "IDENTITY" in reste})
        tables[nom] = {"colonnes": colonnes, "cles": cles}
    return tables


SCHEMA = tables_du_schema()
# Les types énumérés de schema.sql, comme organismes.type_organisme : leurs valeurs sont des textes.
ENUMS = set(re.findall(r"CREATE TYPE\s+([\w.]+)\s+AS ENUM", (RACINE / "schema.sql").read_text(encoding="utf-8")))


def type_du_schema(colonne):
    """(type Python de base, liste ou non, case vide permise) d'une colonne de schema.sql."""
    nom = colonne["type"].removesuffix("[]")
    base = str if nom in ENUMS else TYPES_SQL[re.match(r"[a-z]+", nom).group()]
    return base, colonne["type"].endswith("[]"), colonne["vide_permis"]


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
                self.assertEqual(classe.CONFLIT, CONFLITS_ATTENDUS[classe])  # le comportement des conflits d'avant
                if classe.CLE:
                    self.assertIn(set(classe.CLE), [set(cle) for cle in SCHEMA[classe.TABLE]["cles"]])
                else:  # sans clé visée, un conflit ne peut qu'écarter la ligne, ou arrêter l'écriture
                    self.assertIn(classe.CONFLIT, ("DO NOTHING", None))

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

    def test_le_numero_rendu_est_une_colonne_numerotee_par_la_base(self):
        avec_numero = [classe for classe in CLASSES if classe.NUMERO is not None]
        self.assertEqual(avec_numero, [FichierSource, Fournisseur])  # RETURNING seulement pour ces deux tables
        for classe in avec_numero:
            colonnes = {c["nom"]: c for c in SCHEMA[classe.TABLE]["colonnes"]}
            with self.subTest(table=classe.TABLE):
                self.assertTrue(colonnes[classe.NUMERO]["numerotee"])  # GENERATED ALWAYS AS IDENTITY
                self.assertIsNone(classe.CONFLIT)


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


def organisme(**valeurs):
    champs = dict(nom="Ville de Test", type="municipalite", code_geographique="66097", mrc_code=None,
                  type_milieu=None, source_contexte="Répertoire des municipalités", notes=None)
    champs.update(valeurs)
    return Organisme(**champs)


ACHETEUR = Acheteur(acheteur_id="OP-1", organisme_id=7, nom_seao=None)


class OrganismesEtAnalysesTests(unittest.TestCase):
    """Les organismes, les acheteurs, les fiches classées et les démarches : mêmes écritures qu'avant."""

    def test_le_contexte_ne_met_a_jour_que_l_organisme_d_un_acheteur(self):
        # charger_organismes sur un petit contexte, avec une doublure de connexion : le nom publié
        # (nom_seao) d'un acheteur déjà en base ne doit pas être effacé par le contexte.
        colonnes = ["organisme", "buyer_ids", "code_geographique", "population", "classe_taille", "superficie_km2",
                    "region_administrative", "mrc", "type_milieu", "particularites_infrastructures",
                    "source_contexte", "notes"]
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "contexte_municipalites.csv"
            with chemin.open("w", encoding="utf-8-sig", newline="") as fichier:
                ecrivain = csv.writer(fichier)
                ecrivain.writerow(colonnes)
                ecrivain.writerow(["Ville de Test", "OP-1 | OP-2", "66097"] + ["À compléter"] * 8 + [""])

            def reponse(requete, parametres=None):
                resultat = MagicMock()
                resultat.__iter__.return_value = iter([("66097",)] if "territoire.municipalite" in requete else [])
                resultat.fetchall.return_value = [("Ville de Test", 7)]
                return resultat
            connexion = MagicMock()
            connexion.execute.side_effect = reponse
            with patch.object(completer_contexte, "CONTEXTE_CSV", chemin):
                self.assertEqual(charger_base.charger_organismes(connexion), (1, 2))
        appels = [a.args for a in connexion.cursor.return_value.__enter__.return_value.executemany.call_args_list]
        ((requete, valeurs),) = [a for a in appels if a[0].startswith("INSERT INTO organismes.acheteur")]
        self.assertEqual(requete, "INSERT INTO organismes.acheteur (acheteur_id, organisme_id, nom_seao) "
                                  "VALUES (%(acheteur_id)s, %(organisme_id)s, %(nom_seao)s) "
                                  "ON CONFLICT (acheteur_id) DO UPDATE SET organisme_id = EXCLUDED.organisme_id")
        self.assertNotIn("nom_seao = EXCLUDED", requete)
        self.assertEqual(valeurs, [{"acheteur_id": "OP-1", "organisme_id": 7, "nom_seao": None},
                                   {"acheteur_id": "OP-2", "organisme_id": 7, "nom_seao": None}])

    def test_un_acheteur_ecrit_sans_mises_a_jour_echoue_avant_toute_requete(self):
        for objets in ([ACHETEUR], []):
            with self.subTest(objets=len(objets)):
                connexion = MagicMock()
                with self.assertRaises(ValueError) as contexte:
                    Acheteur.inserer(connexion, objets)
                self.assertIn("mises_a_jour", str(contexte.exception))
                connexion.cursor.assert_not_called()
                connexion.execute.assert_not_called()

    def test_des_colonnes_de_mise_a_jour_invalides_sont_refusees_avant_toute_requete(self):
        cas = [("colonne inconnue", Acheteur, ACHETEUR, ("organisme_idd",), "inconnue"),
               ("colonne remplie par la base", Organisme, organisme(), ("organisme_id",), "remplie(s) par la base"),
               ("colonne de la clé", Acheteur, ACHETEUR, ("acheteur_id",), "de la clé"),
               ("liste vide, mise à jour obligatoire", Acheteur, ACHETEUR, (), "vide"),
               ("liste vide, mise à jour facultative", Organisme, organisme(), (), "vide")]
        for nom, classe, objet, mises_a_jour, fragment in cas:
            with self.subTest(cas=nom):
                connexion = MagicMock()
                with self.assertRaises(ValueError) as contexte:
                    classe.inserer(connexion, [objet], mises_a_jour=mises_a_jour)
                self.assertIn(fragment, str(contexte.exception))
                connexion.cursor.assert_not_called()

    def test_un_organisme_est_mis_a_jour_par_son_nom_sans_toucher_a_son_numero(self):
        ((requete, valeurs),) = appels_ecrits(Organisme, [organisme()])
        self.assertEqual(requete, "INSERT INTO organismes.organisme (nom, type, code_geographique, mrc_code, type_milieu, "
                                  "source_contexte, notes) VALUES (%(nom)s, %(type)s, %(code_geographique)s, %(mrc_code)s, "
                                  "%(type_milieu)s, %(source_contexte)s, %(notes)s) ON CONFLICT (nom) DO UPDATE SET "
                                  "type = EXCLUDED.type, code_geographique = EXCLUDED.code_geographique, "
                                  "mrc_code = EXCLUDED.mrc_code, type_milieu = EXCLUDED.type_milieu, "
                                  "source_contexte = EXCLUDED.source_contexte, notes = EXCLUDED.notes")
        self.assertNotIn("organisme_id", requete)
        self.assertEqual(valeurs, [organisme().en_ligne()])

    def test_une_fiche_reclassee_remplace_son_classement(self):
        calcul = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
        fiche = FicheClassee(fiche_id=12, nature_transaction="achat", lie_eau=True, pga_eau=True,
                             gestion_actifs_eau="pga_eau", version_regles="regles test", calcule_le=calcul)
        ((requete, valeurs),) = appels_ecrits(FicheClassee, [fiche])
        self.assertTrue(requete.startswith("INSERT INTO analyses.fiche_classee (fiche_id, nature_transaction, lie_eau, "
                                           "pga_eau, gestion_actifs_eau, version_regles, calcule_le) VALUES ("))
        self.assertTrue(requete.endswith("ON CONFLICT (fiche_id) DO UPDATE SET nature_transaction = EXCLUDED.nature_transaction, "
                                         "lie_eau = EXCLUDED.lie_eau, pga_eau = EXCLUDED.pga_eau, "
                                         "gestion_actifs_eau = EXCLUDED.gestion_actifs_eau, "
                                         "version_regles = EXCLUDED.version_regles, calcule_le = EXCLUDED.calcule_le"))
        self.assertEqual(valeurs[0]["calcule_le"], calcul)

    def test_une_demarche_en_conflit_est_ecartee_sans_mise_a_jour(self):
        demarche = Demarche(organisme_id=7, plan="pga_eau", classement="elaboration", etat="mandat_attribue",
                            date_attribution=date(2026, 5, 21), date_publication=None, montant=Decimal("22995.00"),
                            dossier_id=3, fournisseur_id=12, lien=None, source="SEAO", notes=None)
        ((requete, valeurs),) = appels_ecrits(Demarche, [demarche])
        self.assertTrue(requete.startswith("INSERT INTO analyses.demarche (organisme_id, plan, classement, etat, "))
        self.assertTrue(requete.endswith(" ON CONFLICT DO NOTHING"))
        self.assertNotIn("demarche_id", requete)
        self.assertEqual(valeurs, [demarche.en_ligne()])


FOURNISSEUR = Fournisseur(nom="L'UNION DES MUNICIPALITÉS DU QUÉBEC", neq="1142385377",
                          adresse="2020 Blvd Robert-Bourassa, #210", localite="Montréal", region="QC",
                          code_postal="H3A2A5", pays="CAN")
IDENTIFIANT = IdentifiantFournisseur(identifiant="FO-1142385377", fournisseur_id=7)


def connexion_qui_numerote(*resultats):
    """Une doublure de connexion : executemany(..., returning=True) rend ces résultats, dans l'ordre."""
    connexion = MagicMock()
    curseur = connexion.cursor.return_value.__enter__.return_value
    curseur.fetchall.side_effect = list(resultats)
    curseur.nextset.side_effect = [True] * (len(resultats) - 1) + [None]
    return connexion, curseur


class EcritureTests(unittest.TestCase):
    """Les modes de conflit, les mises à jour demandées et les numéros rendus : refusés avant toute requête s'ils sont faux."""

    def test_mises_a_jour_est_refusee_quand_le_conflit_ne_met_rien_a_jour(self):
        for classe, objet, mises_a_jour in ((Dossier, Dossier(ocid="ocds-ec9k95-20170481"), ("ocid",)),
                                            (IdentifiantFournisseur, IDENTIFIANT, ("fournisseur_id",))):
            with self.subTest(table=classe.TABLE):
                connexion = MagicMock()
                with self.assertRaises(ValueError) as contexte:
                    classe.inserer(connexion, [objet], mises_a_jour=mises_a_jour)
                self.assertIn("ne met rien à jour", str(contexte.exception))
                connexion.cursor.assert_not_called()

    def test_une_colonne_repetee_dans_mises_a_jour_est_refusee(self):
        connexion = MagicMock()
        with self.assertRaises(ValueError) as contexte:
            Acheteur.inserer(connexion, [ACHETEUR], mises_a_jour=("nom_seao", "nom_seao"))
        self.assertIn("colonne(s) répétée(s) dans mises_a_jour : nom_seao.", str(contexte.exception))
        connexion.cursor.assert_not_called()

    def test_un_mode_de_conflit_inconnu_est_refuse_avant_toute_requete(self):
        for objets in ([Dossier(ocid="ocds-ec9k95-20170481")], []):  # même sans ligne à écrire
            with self.subTest(objets=len(objets)):
                connexion = MagicMock()
                with patch.object(Dossier, "CONFLIT", "DO NOTHNG"), self.assertRaises(ValueError) as contexte:
                    Dossier.inserer(connexion, objets)
                self.assertIn("mode de conflit inconnu", str(contexte.exception))
                connexion.cursor.assert_not_called()

    def test_les_numeros_rendus_suivent_l_ordre_des_objets(self):
        autre = Fournisseur(nom="Fournisseur sans NEQ", neq=None, adresse=None, localite=None, region=None,
                            code_postal=None, pays=None)
        connexion, curseur = connexion_qui_numerote([(41,)], [(42,)])
        self.assertEqual(Fournisseur.inserer_et_numeroter(connexion, [FOURNISSEUR, autre]), [41, 42])
        ((requete, valeurs), options) = curseur.executemany.call_args
        self.assertEqual(requete, "INSERT INTO seao.fournisseur (nom, neq, adresse, localite, region, code_postal, pays) "
                                  "VALUES (%(nom)s, %(neq)s, %(adresse)s, %(localite)s, %(region)s, %(code_postal)s, "
                                  "%(pays)s) RETURNING fournisseur_id")
        self.assertEqual(options, {"returning": True})
        self.assertEqual(valeurs, [FOURNISSEUR.en_ligne(), autre.en_ligne()])
        vide = MagicMock()
        self.assertEqual(Fournisseur.inserer_et_numeroter(vide, []), [])
        vide.cursor.assert_not_called()

    def test_un_numero_n_est_rendu_que_pour_une_colonne_generee_sans_conflit_permis(self):
        cas = [("sans NUMERO", IdentifiantFournisseur, {}, [IDENTIFIANT], "NUMERO doit nommer"),
               ("sans NUMERO, liste vide", IdentifiantFournisseur, {}, [], "NUMERO doit nommer"),
               ("colonne inconnue", Fournisseur, {"NUMERO": "numero_inconnu"}, [FOURNISSEUR], "NUMERO doit nommer"),
               ("colonne écrite, pas remplie par la base", Fournisseur, {"NUMERO": "neq"}, [FOURNISSEUR], "NUMERO doit nommer"),
               ("table en DO NOTHING", Fournisseur, {"CONFLIT": "DO NOTHING"}, [FOURNISSEUR], "que sans ON CONFLICT"),
               ("table en DO UPDATE", Fournisseur, {"CONFLIT": "DO UPDATE"}, [FOURNISSEUR], "que sans ON CONFLICT")]
        for nom, classe, attributs, objets, fragment in cas:
            with self.subTest(cas=nom):
                connexion, _ = connexion_qui_numerote([(1,)])  # sans le refus, l'écriture irait jusqu'au bout
                with ExitStack() as pile:
                    for attribut, valeur in attributs.items():
                        pile.enter_context(patch.object(classe, attribut, valeur))
                    with self.assertRaises(ValueError) as contexte:
                        classe.inserer_et_numeroter(connexion, objets)
                self.assertIn(fragment, str(contexte.exception))
                connexion.cursor.assert_not_called()

    def test_un_resultat_inattendu_de_la_base_arrete_l_ecriture(self):
        cas = [("un résultat de moins", ([(41,)],)),
               ("un résultat sans ligne", ([(41,)], [])),
               ("deux lignes dans un résultat", ([(41,)], [(42,), (43,)])),
               ("deux valeurs dans une ligne", ([(41,)], [(42, 43)])),
               ("un numéro nul", ([(41,)], [(None,)]))]
        for nom, resultats in cas:
            with self.subTest(cas=nom):
                connexion, _ = connexion_qui_numerote(*resultats)
                with self.assertRaises(ValueError) as contexte:
                    Fournisseur.inserer_et_numeroter(connexion, [FOURNISSEUR, FOURNISSEUR])
                self.assertIn("un numéro non nul par ligne", str(contexte.exception))

    def test_une_ligne_en_double_arrete_l_ecriture_sans_on_conflict(self):
        # Exports, fournisseurs et identifiants : pas de ON CONFLICT, comme avant ; un doublon fait échouer la requête.
        self.assertEqual([classe for classe in CLASSES if classe.CONFLIT is None],
                         [FichierSource, Fournisseur, IdentifiantFournisseur])
        ((requete, valeurs),) = appels_ecrits(IdentifiantFournisseur, [IDENTIFIANT])
        self.assertEqual(requete, "INSERT INTO seao.identifiant_fournisseur (identifiant, fournisseur_id) "
                                  "VALUES (%(identifiant)s, %(fournisseur_id)s)")
        self.assertEqual(valeurs, [{"identifiant": "FO-1142385377", "fournisseur_id": 7}])
        fichier = FichierSource(nom="hebdo_20260907_20260913.json", type="hebdomadaire", periode_debut=date(2026, 9, 7),
                                periode_fin=date(2026, 9, 13), date_publication=None, empreinte_sha256="ab" * 32,
                                nb_fiches=1)
        connexion, curseur = connexion_qui_numerote([(3,)])
        self.assertEqual(FichierSource.inserer_et_numeroter(connexion, [fichier]), [3])
        self.assertEqual(curseur.executemany.call_args.args[0],
                         "INSERT INTO seao.fichier_source (nom, type, periode_debut, periode_fin, date_publication, "
                         "empreinte_sha256, nb_fiches) VALUES (%(nom)s, %(type)s, %(periode_debut)s, %(periode_fin)s, "
                         "%(date_publication)s, %(empreinte_sha256)s, %(nb_fiches)s) RETURNING fichier_id")


class Resultat(list):
    """Les lignes d'une lecture, comme les rend psycopg."""

    def fetchall(self):
        return list(self)

    def fetchone(self):
        return self[0] if self else None


class CurseurFactice:
    def __init__(self, base):
        self.base, self.resultats = base, []

    def __enter__(self):
        return self

    def __exit__(self, *erreur):
        return False

    def executemany(self, requete, lignes, returning=False):
        self.resultats = self.base.ecrire(requete, list(lignes), returning)

    def fetchall(self):
        return self.resultats[0]

    def nextset(self):
        self.resultats = self.resultats[1:]
        return True if self.resultats else None


class BaseFactice:
    """Une doublure de base pour charger_export : elle répond aux lectures et note les écritures, dans l'ordre.

    organismes et acheteurs : ce que le contexte a déjà chargé ; fournisseurs : les identifiants FO déjà en base.
    """

    def __init__(self, organismes, acheteurs, fournisseurs):
        self.organismes, self.acheteurs, self.fournisseurs = organismes, acheteurs, fournisseurs
        self.ecritures = []   # (« INSERT seao.fiche », requête, lignes), dans l'ordre
        self.dossiers, self.fiches, self.attributions, self.dernier = {}, {}, {}, 100

    def numero(self):
        self.dernier += 1
        return self.dernier

    def cursor(self):
        return CurseurFactice(self)

    def ecrire(self, requete, lignes, returning):
        mots = requete.split()
        table = mots[2] if mots[0] == "INSERT" else mots[1]
        self.ecritures.append((f"{mots[0]} {table}", requete, lignes))
        if table == "seao.dossier":
            for ligne in lignes:
                self.dossiers.setdefault(ligne["ocid"], self.numero())
        elif table == "seao.fiche":
            ocids = {d: o for o, d in self.dossiers.items()}
            for ligne in lignes:
                self.fiches[(ocids[ligne["dossier_id"]], ligne["release_id"])] = self.numero()
        elif table == "seao.attribution":
            for ligne in lignes:
                self.attributions[(ligne["fiche_id"], ligne["numero"])] = self.numero()
        return [[(self.numero(),)] for _ in lignes] if returning else []

    def execute(self, requete, parametres=None):
        lectures = {
            "SELECT empreinte_sha256 FROM seao.fichier_source": [],
            "SELECT 1 FROM seao.fichier_source": [],
            "SELECT d.ocid, f.release_id, f.fiche_id": [(o, r, f) for (o, r), f in self.fiches.items()],
            "SELECT fiche_id, brut FROM seao.fiche": [],
            "SELECT identifiant, fournisseur_id FROM seao.identifiant_fournisseur": list(self.fournisseurs.items()),
            "SELECT neq, fournisseur_id FROM seao.fournisseur": [("1142385377", f) for f in self.fournisseurs.values()],
            "SELECT nom, organisme_id FROM organismes.organisme": list(self.organismes.items()),
            "SELECT acheteur_id, organisme_id FROM organismes.acheteur": list(self.acheteurs.items()),
            "SELECT ocid, dossier_id FROM seao.dossier": list(self.dossiers.items()),
            "SELECT fiche_id, numero, attribution_id FROM seao.attribution":
                [(f, n, a) for (f, n), a in self.attributions.items()],
        }
        lecture = next((lignes for debut, lignes in lectures.items() if requete.startswith(debut)), None)
        if lecture is None:
            raise AssertionError(f"lecture inattendue : {requete}")
        return Resultat(lecture)


class ExportTests(unittest.TestCase):
    """charger_export sur un export d'une seule fiche, le dossier PGA-Eau de Matagami, avec une base factice."""

    def charger(self, acheteurs, fournisseurs=None):
        organisme = charger_base.lignes_de_la_fiche(MATAGAMI)["acheteur"]["organisme"]
        base = BaseFactice({organisme: 7}, acheteurs, fournisseurs or {})
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "hebdo_20260907_20260913.json"
            chemin.write_text(json.dumps({"publishedDate": "2026-09-14T08:00:00-04:00", "releases": [MATAGAMI]}),
                              encoding="utf-8")
            retour = charger_base.charger_export(base, chemin)
        return base, retour

    def test_un_export_ecrit_ses_tables_dans_le_meme_ordre(self):
        avant = ["INSERT seao.fichier_source", "INSERT seao.nomenclature", "INSERT seao.classification"]
        apres = ["INSERT organismes.acheteur", "INSERT seao.dossier", "INSERT seao.fiche",
                 "INSERT seao.fiche_classification", "INSERT seao.soumissionnaire", "INSERT seao.attribution",
                 "INSERT seao.contrat", "INSERT seao.fiche_fichier"]
        cas = [("fournisseur nouveau", None, ["INSERT seao.fournisseur", "INSERT seao.identifiant_fournisseur"]),
               ("fournisseur déjà en base", {"FO-1142385377": 3}, ["UPDATE seao.fournisseur"])]
        for nom, fournisseurs, milieu in cas:
            with self.subTest(cas=nom):
                base, retour = self.charger({"OP-70456": 7}, fournisseurs)
                self.assertEqual(retour, (1, 1, 0))
                self.assertEqual([table for table, _, _ in base.ecritures], avant + milieu + apres)

    def test_un_export_ne_met_a_jour_que_le_nom_publie_d_un_acheteur(self):
        acheteur = charger_base.lignes_de_la_fiche(MATAGAMI)["acheteur"]
        for nom, acheteurs in (("identifiant déjà rattaché par le contexte", {"OP-70456": 7}),
                               ("identifiant nouveau, rattaché par le nom", {})):
            with self.subTest(cas=nom):
                base, _ = self.charger(acheteurs)
                ((requete, lignes),) = [(r, l) for t, r, l in base.ecritures if t == "INSERT organismes.acheteur"]
                self.assertEqual(requete, "INSERT INTO organismes.acheteur (acheteur_id, organisme_id, nom_seao) "
                                          "VALUES (%(acheteur_id)s, %(organisme_id)s, %(nom_seao)s) "
                                          "ON CONFLICT (acheteur_id) DO UPDATE SET nom_seao = EXCLUDED.nom_seao")
                self.assertEqual(lignes, [{"acheteur_id": "OP-70456", "organisme_id": 7, "nom_seao": acheteur["nom_seao"]}])


if __name__ == "__main__":
    unittest.main()
