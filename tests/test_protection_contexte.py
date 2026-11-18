"""Tests de la lecture contrôlée du fichier de contexte, et d'une écriture qui ne le laisse jamais abîmé.

Les tests d'écriture vérifient les octets du contexte, ceux de la sauvegarde précédente, les
temporaires de l'appel, et qu'un temporaire étranger reste intact. Au niveau du module, seuls des noms
qui existaient avant ce lot sont importés : la contre-épreuve lance aussi ces tests sur l'ancien code.
"""

import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import analyser_seao
import charger_base
import completer_contexte
from barometre.contexte import fichier

RACINE = Path(__file__).resolve().parent.parent
COLONNES = ["organisme", "buyer_ids", "code_geographique", "population", "classe_taille", "superficie_km2",
            "region_administrative", "mrc", "type_milieu", "particularites_infrastructures", "source_contexte",
            "notes"]
ENTETE = ",".join(COLONNES)
A = "À compléter"
# Le répertoire réduit à une municipalité, pour lancer completer_contexte.py.
MUN = ("mcode,munnom,mdes,regadm,mrc,mpopul,msuperf,mcodpos\r\n"
       "66097,Pointe-Claire,Ville,Montréal (06),,31380,34.5,H9R 4S9\r\n").encode("utf-8")


def ligne(organisme="Ville de Test", buyer_ids="OP-1", **valeurs):
    """Une ligne de contexte : tout à « À compléter », note vide, sauf les valeurs données."""
    cellules = {colonne: A for colonne in COLONNES}
    cellules.update(organisme=organisme, buyer_ids=buyer_ids, notes="")
    cellules.update(valeurs)
    return cellules


def csv_octets(lignes, colonnes=COLONNES, bom=True, fin="\r\n", guillemets=csv.QUOTE_MINIMAL):
    sortie = io.StringIO(newline="")
    ecrivain = csv.DictWriter(sortie, fieldnames=colonnes, lineterminator=fin, quoting=guillemets)
    ecrivain.writeheader()
    ecrivain.writerows(lignes)
    return (("\ufeff" if bom else "") + sortie.getvalue()).encode("utf-8")


def brut(*lignes_texte):
    """Un fichier écrit ligne par ligne, tel quel, en UTF-8 avec BOM et CRLF."""
    return ("\ufeff" + "".join(texte + "\r\n" for texte in lignes_texte)).encode("utf-8")


def cellules(nombre, organisme="Ville de Test"):
    """Une ligne brute de nombre cellules."""
    return ",".join([organisme, "OP-1"] + ["x"] * (nombre - 2))


def fiche_municipale(organisme="Ville nouvelle", acheteur="OP-77"):
    """Une fiche minimale du SEAO dont l'acheteur est municipal."""
    return {"ocid": "ocds-test-1", "id": "20260907120000", "buyer": {"id": acheteur, "name": organisme},
            "parties": [{"id": acheteur, "name": organisme, "roles": ["buyer"], "details": {"municipal": "1"}}],
            "tag": [], "tender": {"title": "Entretien du réseau", "status": "complete"}, "awards": [], "contracts": []}


class EcrivainQuiCasse:
    """Remplace csv.writer : la deuxième ligne écrite lève une erreur de disque."""

    vrai = csv.writer

    def __init__(self, *args, **kwargs):
        self.ecrivain, self.lignes = self.vrai(*args, **kwargs), 0

    def writerow(self, ligne_csv):
        self.lignes += 1
        if self.lignes == 2:
            raise OSError(28, "disque plein (simulé)")
        return self.ecrivain.writerow(ligne_csv)

    def writerows(self, lignes_csv):
        for ligne_csv in lignes_csv:
            self.writerow(ligne_csv)


class Dossier(unittest.TestCase):
    """Un dossier temporaire par test, avec son fichier de contexte."""

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        self.contexte = self.dossier / "contexte_municipalites.csv"
        self.sorties = self.dossier / "sorties"

    def ecrire(self, octets):
        self.contexte.write_bytes(octets)
        return octets

    def refuse(self, octets, *fragments):
        """lire_contexte, avec ses colonnes par défaut, doit refuser ce fichier et le dire."""
        self.ecrire(octets)
        with self.assertRaises(ValueError) as contexte:
            fichier.lire_contexte(self.contexte)
        for fragment in fragments:
            self.assertIn(fragment, str(contexte.exception))

    def dans_le_dossier(self, repertoire=True):
        """Les programmes lisent des chemins relatifs : on se place dans le dossier du test."""
        ancien = os.getcwd()
        os.chdir(self.dossier)
        self.addCleanup(os.chdir, ancien)
        if repertoire:
            (self.dossier / "donnees_reference").mkdir()
            (self.dossier / "donnees_reference" / "MUN.csv").write_bytes(MUN)


class LectureTests(Dossier):
    """Les contrôles de lecture : un fichier mal formé est refusé, avec la ligne et quoi corriger."""

    def test_un_fichier_valide_est_lu_comme_avant(self):
        octets = self.ecrire(csv_octets([ligne(population="1 234", notes="une note, avec virgule"),
                                         ligne("Ville de Deux", "OP-2 | OP-3")], COLONNES + ["colonne_a_la_main"]))
        lecteur = csv.DictReader(io.StringIO(octets.decode("utf-8-sig"), newline=""))
        self.assertEqual(fichier.lire_contexte(self.contexte), (lecteur.fieldnames, list(lecteur)))

    def test_les_cellules_entre_guillemets_valides_sont_acceptees(self):
        valeurs = ligne('Ville de "Les Saules"', notes="note sur\r\ndeux lignes", mrc="MRC, avec virgule",
                        source_contexte='il dit "oui"', type_milieu="saut\nLF")
        variantes = {
            "format habituel": csv_octets([valeurs]),
            "LF, sans BOM, guillemets partout": csv_octets([valeurs], bom=False, fin="\n", guillemets=csv.QUOTE_ALL),
        }
        for nom, octets in variantes.items():
            with self.subTest(variante=nom):
                self.ecrire(octets)
                self.assertEqual(fichier.lire_contexte(self.contexte), (COLONNES, [valeurs]))
        with self.subTest(variante="guillemet au milieu d'une cellule sans guillemets"):
            self.ecrire(brut(ENTETE, cellules(12, 'Ville de "Les Saules"')))
            self.assertEqual(fichier.lire_contexte(self.contexte)[1][0]["organisme"], 'Ville de "Les Saules"')

    def test_les_guillemets_mal_fermes_sont_refuses_avec_la_ligne(self):
        reste = ",".join(["x"] * 10)
        cas = {
            "jamais refermé": (brut(ENTETE, cellules(12), f'"Ville de Deux,OP-2,{reste}'), "ligne 3"),
            "texte après le guillemet fermant": (brut(ENTETE, f'"Ville de Test"secteur,OP-1,{reste}'), "ligne 2"),
            "refermé par un autre plus loin": (brut(ENTETE, f'"Ville de Test,OP-1,{reste}',
                                                    f'Ville de Deux,"OP-2",{reste}'), "ligne 2"),
        }
        for nom, (octets, ligne_fautive) in cas.items():
            with self.subTest(cas=nom):
                self.refuse(octets, ligne_fautive, "guillemet")

    def test_une_ligne_au_mauvais_nombre_de_cellules_est_refusee(self):
        for nombre, conseil in ((13, "virgule de trop"), (11, "virgule manque")):
            with self.subTest(cellules=nombre):
                self.refuse(brut(ENTETE, cellules(12), cellules(nombre)), "ligne 3",
                            f"{nombre} cellules au lieu de 12", conseil)

    def test_une_colonne_exigee_absente_est_refusee(self):
        with self.subTest(cas="buyer_ids supprimée"):
            entete = ",".join(colonne for colonne in COLONNES if colonne != "buyer_ids")
            self.refuse(brut(entete, ",".join(["Ville de Test"] + ["x"] * 10)), "colonne(s) manquante(s) : buyer_ids")
        with self.subTest(cas="séparé par des points-virgules"):
            self.refuse(brut(";".join(COLONNES), ";".join(["Ville de Test", "OP-1"] + ["x"] * 10)),
                        "organisme, buyer_ids", "points-virgules")

    def test_deux_colonnes_du_meme_nom_sont_refusees(self):
        self.refuse(brut(ENTETE.replace("type_milieu", "notes"), cellules(12)), "plusieurs colonnes s'appellent « notes »")

    def test_un_fichier_pas_en_utf8_est_refuse_avec_la_ligne(self):
        texte = "\r\n".join([ENTETE, cellules(12), cellules(12, "Ville de Lévis")]) + "\r\n"
        self.refuse(texte.encode("cp1252"), "n'est pas en UTF-8", "ligne 3")

    def test_un_fichier_vide_est_refuse(self):
        for octets in (b"", b"\xef\xbb\xbf"):
            with self.subTest(octets=octets):
                self.refuse(octets, "est vide")

    def test_un_organisme_vide_est_refuse(self):
        self.refuse(brut(ENTETE, cellules(12), cellules(12, "  ")), "ligne 3", "la colonne organisme est vide")

    def test_l_analyse_n_exige_que_organisme_et_buyer_ids(self):
        octets = self.ecrire(brut("organisme,buyer_ids,population", "Ville de Test,OP-1,1 234"))
        lignes = fichier.load_context_source(self.contexte, self.dossier / "absente.csv", [])
        self.assertEqual(lignes, [{"organisme": "Ville de Test", "buyer_ids": "OP-1", "population": "1 234"}])
        self.assertEqual(self.contexte.read_bytes(), octets)

    def test_le_complement_et_le_chargement_exigent_les_douze_colonnes(self):
        self.assertEqual(fichier.COLONNES_CONTEXTE, tuple(COLONNES))
        self.ecrire(brut("organisme,buyer_ids,population", "Ville de Test,OP-1,1 234"))
        with self.assertRaises(fichier.ContexteInvalide) as contexte:
            fichier.lire_contexte(self.contexte, fichier.COLONNES_CONTEXTE)
        self.assertIn("colonne(s) manquante(s) : code_geographique, classe_taille", str(contexte.exception))


class ReecritureTests(Dossier):
    """La réécriture de completer_contexte.py : jamais un fichier à moitié écrit, ni une sauvegarde perdue."""

    def setUp(self):
        super().setUp()
        self.avant = self.ecrire(csv_octets([ligne(population="1 234"), ligne("Ville de Deux", "OP-2")]))
        os.utime(self.contexte, (1_700_000_000, 1_700_000_000))
        self.sorties.mkdir()
        self.bak = self.sorties / "contexte_municipalites.csv.bak"
        self.bak.write_bytes(b"sauvegarde precedente")
        self.etrangers = {self.dossier / "contexte_municipalites.csv.etranger.tmp": b"temporaire d'un autre",
                          self.sorties / "contexte_municipalites.csv.bak.etranger.tmp": b"autre"}
        for chemin, octets in self.etrangers.items():
            chemin.write_bytes(octets)
        self.colonnes, self.lignes = fichier.lire_contexte(self.contexte)
        self.lignes[0]["population"] = "5 678"
        self.nouveau = csv_octets(self.lignes, self.colonnes)

    def reecrire(self, **options):
        fichier.reecrire_contexte(self.contexte, self.colonnes, self.lignes, self.sorties, **options)

    def temporaires(self):
        return {chemin for chemin in self.dossier.rglob("*.tmp") if chemin not in self.etrangers}

    def verifier_temporaires(self, gardes=()):
        """Les temporaires étrangers sont intacts ; il ne reste de cet appel que les copies gardées."""
        for chemin, octets in self.etrangers.items():
            self.assertEqual(chemin.read_bytes(), octets)
        self.assertEqual(self.temporaires(), set(gardes))

    def verifier_intact(self):
        self.assertEqual(self.contexte.read_bytes(), self.avant)
        self.assertEqual(self.bak.read_bytes(), b"sauvegarde precedente")
        self.verifier_temporaires()

    def remplacement(self, cible_refusee=None, interrompre_apres=None, puis_ecrire=None):
        """Un os.replace qui refuse une cible, ou s'interrompt (Ctrl+C) après avoir remplacé une cible."""
        vrai = os.replace

        def remplacer(source, cible):
            if cible_refusee is not None and Path(cible) == cible_refusee:
                raise PermissionError(13, "accès refusé (simulé)")
            if interrompre_apres == "avant":
                raise KeyboardInterrupt
            vrai(source, cible)
            if interrompre_apres is not None and Path(cible) == interrompre_apres:
                if puis_ecrire is not None:
                    Path(cible).write_bytes(puis_ecrire)
                raise KeyboardInterrupt
        return patch.object(fichier.os, "replace", side_effect=remplacer)

    def test_une_ligne_impossible_a_ecrire_ne_touche_a_rien(self):
        self.lignes[1]["colonne_inconnue"] = "x"
        with self.assertRaises(ValueError):
            fichier.reecrire_contexte(self.contexte, self.colonnes, self.lignes, self.sorties)
        self.verifier_intact()

    def test_un_disque_plein_pendant_le_temporaire_ne_touche_a_rien(self):
        with patch.object(fichier.os, "fsync", side_effect=OSError(28, "disque plein (simulé)")):
            with self.assertRaises(fichier.EcritureEchouee) as contexte:
                self.reecrire()
        self.assertIs(contexte.exception.nouveau_en_place, False)
        self.assertIn("inchangé (vérifié sur ses octets)", str(contexte.exception))
        self.verifier_intact()

    def test_un_remplacement_refuse_ne_touche_a_rien(self):
        with self.remplacement(cible_refusee=self.contexte):
            with self.assertRaises(fichier.EcritureEchouee) as contexte:
                self.reecrire()
        self.assertIs(contexte.exception.nouveau_en_place, False)
        self.assertIn("ouvert dans un autre programme", str(contexte.exception))
        self.assertIn("inchangé (vérifié sur ses octets)", str(contexte.exception))
        self.verifier_intact()

    def test_un_fichier_modifie_pendant_l_execution_n_est_pas_remplace(self):
        saisie = self.ecrire(self.avant.replace(b"1 234", b"9 999"))  # enregistrée après la lecture
        with self.assertRaises(fichier.EcritureEchouee) as contexte:
            self.reecrire(avant=self.avant)
        self.assertIs(contexte.exception.nouveau_en_place, False)
        self.assertIn("a changé depuis sa lecture", str(contexte.exception))
        self.assertIn("pas un verrou", str(contexte.exception))
        self.assertEqual(self.contexte.read_bytes(), saisie)
        self.assertEqual(self.bak.read_bytes(), b"sauvegarde precedente")
        self.verifier_temporaires()

    def test_une_sauvegarde_impossible_apres_le_remplacement_garde_la_copie(self):
        with self.remplacement(cible_refusee=self.bak):
            with self.assertRaises(fichier.EcritureEchouee) as contexte:
                self.reecrire()
        erreur = contexte.exception
        self.assertIs(erreur.nouveau_en_place, True)
        self.assertIn("est en place (vérifié sur ses octets)", str(erreur))
        self.assertNotIn("inchangé", str(erreur))
        self.assertEqual(self.contexte.read_bytes(), self.nouveau)
        self.assertEqual(self.bak.read_bytes(), b"sauvegarde precedente")
        (copie,) = erreur.conserves
        self.assertEqual(copie.read_bytes(), self.avant)
        self.assertIn(str(copie), str(erreur))
        self.verifier_temporaires(gardes=[copie])

    def test_un_ctrl_c_avant_le_remplacement_laisse_le_contexte_inchange(self):
        with self.remplacement(interrompre_apres="avant"):
            with self.assertRaises(KeyboardInterrupt) as contexte:
                self.reecrire()
        note = " ".join(getattr(contexte.exception, "__notes__", []))
        self.assertIn("inchangé (vérifié sur ses octets)", note)
        self.verifier_intact()

    def test_un_ctrl_c_apres_le_remplacement_annonce_le_nouveau_contexte(self):
        with self.remplacement(interrompre_apres=self.contexte):
            with self.assertRaises(KeyboardInterrupt) as contexte:
                self.reecrire()
        note = " ".join(getattr(contexte.exception, "__notes__", []))
        self.assertIn("est en place (vérifié sur ses octets)", note)
        self.assertNotIn("inchangé", note)
        self.assertEqual(self.contexte.read_bytes(), self.nouveau)
        self.assertEqual(self.bak.read_bytes(), b"sauvegarde precedente")
        (copie,) = self.temporaires()
        self.assertEqual(copie.read_bytes(), self.avant)
        self.assertIn(str(copie), note)
        self.verifier_temporaires(gardes=[copie])

    def test_un_etat_indetermine_garde_les_copies_et_donne_leur_chemin(self):
        # Après le remplacement, le fichier n'a ni l'ancien ni le nouveau contenu : rien n'est supprimé.
        with self.remplacement(interrompre_apres=self.contexte, puis_ecrire=b"un troisieme contenu"):
            with self.assertRaises(KeyboardInterrupt) as contexte:
                self.reecrire()
        note = " ".join(getattr(contexte.exception, "__notes__", []))
        self.assertIn("n'a pas pu être vérifié : rien n'est supprimé", note)
        self.assertNotIn("inchangé", note)
        (copie,) = self.temporaires()
        self.assertEqual(copie.read_bytes(), self.avant)
        self.assertIn(str(copie), note)
        self.assertEqual(self.bak.read_bytes(), b"sauvegarde precedente")

    def test_une_reecriture_reussie_ne_laisse_aucun_temporaire(self):
        fichier.reecrire_contexte(self.contexte, self.colonnes, self.lignes, self.sorties)
        self.assertEqual(self.contexte.read_bytes(), self.nouveau)
        self.assertEqual(self.bak.read_bytes(), self.avant)
        self.assertEqual(self.bak.stat().st_mtime, 1_700_000_000)  # la sauvegarde garde la date de l'ancien
        self.verifier_temporaires()


class AjoutTests(Dossier):
    """L'ajout de l'analyse : les octets existants restent tels quels, même en cas d'échec."""

    def setUp(self):
        super().setUp()
        self.sorties.mkdir()
        self.precedente = self.sorties / "contexte_municipalites.csv.avant_ajout"
        self.precedente.write_bytes(b"ajout precedent")

    def test_l_ajout_garde_les_octets_existants_dans_un_autre_format(self):
        # LF, sans BOM, guillemets superflus, sans saut de ligne final : un format accepté, mais pas le nôtre.
        avant = self.ecrire('organisme,buyer_ids,code_geographique,population\n"Ville de Test","OP-1","66097","1 234"'
                            .encode("utf-8"))
        ajoutes = fichier.append_context_rows(self.contexte, [{"organisme": "Ville nouvelle", "buyer_ids": "OP-7"}],
                                              self.sorties)
        self.assertEqual(ajoutes, 1)
        self.assertEqual(self.contexte.read_bytes(),
                         avant + "\r\nVille nouvelle,OP-7,À compléter,À compléter\r\n".encode("utf-8"))
        self.assertEqual(self.precedente.read_bytes(), avant)
        self.assertEqual(list(self.dossier.rglob("*.tmp")), [])

    def test_un_ajout_interrompu_ne_touche_a_rien(self):
        avant = self.ecrire(csv_octets([ligne()]))
        nouvelles = [{"organisme": f"Organisme nouveau {k}", "buyer_ids": f"OP-{k + 10}"} for k in range(3)]
        with patch("csv.writer", EcrivainQuiCasse):
            with self.assertRaises(OSError):
                fichier.append_context_rows(self.contexte, nouvelles, self.sorties)
        self.assertEqual(self.contexte.read_bytes(), avant)
        self.assertEqual(self.precedente.read_bytes(), b"ajout precedent")
        self.assertEqual(list(self.dossier.rglob("*.tmp")), [])

    def test_un_ajout_au_remplacement_refuse_ne_touche_a_rien(self):
        avant = self.ecrire(csv_octets([ligne()]))
        vrai = os.replace

        def remplacer(source, cible):
            if Path(cible) == self.contexte:
                raise PermissionError(13, "accès refusé (simulé)")
            return vrai(source, cible)
        with patch.object(fichier.os, "replace", side_effect=remplacer):
            with self.assertRaises(fichier.EcritureEchouee) as contexte:
                fichier.append_context_rows(self.contexte, [{"organisme": "Ville nouvelle", "buyer_ids": "OP-7"}],
                                            self.sorties)
        self.assertIs(contexte.exception.nouveau_en_place, False)
        self.assertEqual(self.contexte.read_bytes(), avant)
        self.assertEqual(self.precedente.read_bytes(), b"ajout precedent")
        self.assertEqual(list(self.dossier.rglob("*.tmp")), [])


class ProgrammesTests(Dossier):
    """Les trois programmes refusent un contexte mal formé sans rien toucher, avec le code de sortie 1."""

    def test_completer_contexte_refuse_un_contexte_invalide_sans_rien_modifier(self):
        self.dans_le_dossier()
        # Une municipalité du répertoire réduit : le programme aurait des cases à remplir.
        pointe_claire = ",".join(["Ville de Pointe-Claire", "OP-1"] + [A] * 9 + [""])
        cas = {
            "virgule de trop": brut(ENTETE, pointe_claire, cellules(13)),
            "virgule oubliée": brut(ENTETE, pointe_claire, cellules(11)),
            "colonne superficie_km2 supprimée": brut(
                ",".join(colonne for colonne in COLONNES if colonne != "superficie_km2"),
                ",".join(["Ville de Pointe-Claire", "OP-1"] + [A] * 8 + [""])),
            "deux colonnes notes": brut(  # la première « notes » est à la place de type_milieu
                ENTETE.replace("type_milieu", "notes"),
                ",".join(["Ville de Pointe-Claire", "OP-1"] + [A] * 6 + ["saisie à garder", A, A, ""])),
            "guillemet jamais refermé": brut(ENTETE, pointe_claire, '"Ville de Deux,OP-2,' + ",".join(["x"] * 10)),
        }
        for nom, octets in cas.items():
            with self.subTest(cas=nom):
                shutil.rmtree(self.sorties, ignore_errors=True)
                self.ecrire(octets)
                sortie = io.StringIO()
                with redirect_stdout(sortie), redirect_stderr(io.StringIO()):
                    try:
                        code = completer_contexte.main()
                    except Exception as erreur:  # l'ancien comportement : une exception en pleine écriture
                        code = erreur
                self.assertEqual(self.contexte.read_bytes(), octets)
                self.assertEqual(code, 1)
                self.assertIn("Rien n'a été modifié", sortie.getvalue())
                self.assertFalse((self.sorties / "contexte_municipalites.csv.bak").exists())
                self.assertFalse((self.sorties / "contexte_a_verifier.csv").exists())

    def sauvegarde_refusee(self, sauvegarde):
        """Un os.replace qui remplace le contexte, puis refuse la sauvegarde (comme un fichier en lecture seule)."""
        vrai = os.replace

        def remplacer(source, cible):
            if Path(cible).resolve() == sauvegarde.resolve():
                raise PermissionError(13, "accès refusé (simulé)")
            return vrai(source, cible)
        return patch.object(fichier.os, "replace", side_effect=remplacer)

    def test_completer_contexte_s_arrete_si_la_sauvegarde_est_refusee_apres_le_remplacement(self):
        self.dans_le_dossier()
        avant = self.ecrire(brut(ENTETE, ",".join(["Ville de Pointe-Claire", "OP-1"] + [A] * 9 + [""])))
        self.sorties.mkdir()
        bak = self.sorties / "contexte_municipalites.csv.bak"
        bak.write_bytes(b"sauvegarde precedente")
        with self.sauvegarde_refusee(bak), redirect_stdout(io.StringIO()) as sortie, redirect_stderr(io.StringIO()):
            code = completer_contexte.main()
        texte = sortie.getvalue()
        self.assertEqual(code, 1)
        self.assertIn(b"31380", self.contexte.read_bytes())  # le nouveau contexte est en place
        self.assertEqual(bak.read_bytes(), b"sauvegarde precedente")
        (copie,) = self.sorties.glob("contexte_municipalites.csv.bak.*.tmp")
        self.assertEqual(copie.read_bytes(), avant)
        self.assertIn(copie.name, texte)
        self.assertIn("est en place (vérifié sur ses octets)", texte)
        self.assertNotIn("inchangé", texte)
        # Arrêt immédiat : contexte_a_verifier.csv n'est pas écrit, sorties/ ne contient rien d'autre.
        self.assertEqual(sorted(p.name for p in self.sorties.iterdir()), sorted([bak.name, copie.name]))

    def test_analyser_seao_s_arrete_si_la_sauvegarde_est_refusee_apres_l_ajout(self):
        self.dans_le_dossier(repertoire=False)
        avant = self.ecrire(csv_octets([ligne()]))  # l'export apporte un organisme nouveau, Ville nouvelle
        self.sorties.mkdir()
        precedente = self.sorties / "contexte_municipalites.csv.avant_ajout"
        precedente.write_bytes(b"ajout precedent")
        export = self.dossier / "export_test.json"
        export.write_text(json.dumps({"releases": [fiche_municipale()]}), encoding="utf-8")
        with self.sauvegarde_refusee(precedente), \
                patch.object(analyser_seao.sys, "argv", ["analyser_seao.py", str(export)]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as erreurs:
            code = analyser_seao.main()
        texte = erreurs.getvalue()
        self.assertEqual(code, 1)
        self.assertTrue(self.contexte.read_bytes().startswith(avant))
        self.assertIn("Ville nouvelle,OP-77".encode("utf-8"), self.contexte.read_bytes())  # l'ajout est en place
        self.assertEqual(precedente.read_bytes(), b"ajout precedent")
        (copie,) = self.sorties.glob("contexte_municipalites.csv.avant_ajout.*.tmp")
        self.assertEqual(copie.read_bytes(), avant)
        self.assertIn(copie.name, texte)
        self.assertIn("est en place (vérifié sur ses octets)", texte)
        self.assertNotIn("inchangé", texte)
        # Arrêt immédiat : aucun des quatre CSV (sorties/export_test/) n'est écrit.
        self.assertEqual(sorted(p.name for p in self.sorties.iterdir()), sorted([precedente.name, copie.name]))

    def test_completer_contexte_rend_1_si_le_contexte_est_introuvable(self):
        self.dans_le_dossier(repertoire=False)
        with redirect_stdout(io.StringIO()) as sortie:
            code = completer_contexte.main()
        self.assertEqual(code, 1)
        self.assertIn("introuvable", sortie.getvalue())
        self.assertEqual(list(self.dossier.iterdir()), [])

    def test_completer_contexte_rend_1_si_un_fichier_obligatoire_manque(self):
        self.dans_le_dossier(repertoire=False)
        octets = self.ecrire(csv_octets([ligne()]))
        with redirect_stdout(io.StringIO()) as sortie:
            code = completer_contexte.main()
        self.assertEqual(code, 1)
        self.assertIn("Il manque un fichier obligatoire. Rien n'a été modifié.", sortie.getvalue())
        self.assertEqual(self.contexte.read_bytes(), octets)

    def test_completer_contexte_sort_avec_le_code_1_comme_programme(self):
        resultat = subprocess.run([sys.executable, "-B", str(RACINE / "completer_contexte.py")], cwd=self.dossier,
                                  capture_output=True, encoding="utf-8", errors="replace",
                                  env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(resultat.returncode, 1, resultat.stdout + resultat.stderr)
        self.assertIn("introuvable", resultat.stdout)

    def charger(self, *options):
        """Lance charger_base.main avec un contexte mal formé ; connecter() échouerait s'il était appelé."""
        self.ecrire(brut(ENTETE, cellules(13)))
        connecter = MagicMock(side_effect=AssertionError("une connexion a été ouverte"))
        with patch.object(charger_base, "CONTEXT_SOURCE_CSV", self.contexte), \
                patch.object(charger_base, "connecter", connecter), \
                patch.object(charger_base.sys, "argv", ["charger_base.py", *options]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as erreurs:
            code = charger_base.main()
        return code, connecter, erreurs.getvalue()

    def test_charger_base_refuse_un_contexte_invalide_avant_toute_connexion(self):
        code, connecter, erreurs = self.charger()
        self.assertEqual(code, 1)
        connecter.assert_not_called()
        self.assertIn("avant toute connexion", erreurs)
        self.assertIn("ligne 2 : 13 cellules au lieu de 12", erreurs)

    def test_charger_base_reinitialiser_avec_un_contexte_invalide_n_ouvre_aucune_connexion(self):
        code, connecter, erreurs = self.charger("--reinitialiser")
        self.assertEqual(code, 1)
        connecter.assert_not_called()
        self.assertIn("avant toute connexion", erreurs)

    def test_analyser_seao_refuse_un_contexte_invalide_sans_rien_ecrire(self):
        self.dans_le_dossier(repertoire=False)
        octets = self.ecrire(brut(ENTETE.replace("type_milieu", "notes"), cellules(12)))
        export = self.dossier / "export_vide.json"
        export.write_text(json.dumps({"releases": []}), encoding="utf-8")
        with patch.object(analyser_seao.sys, "argv", ["analyser_seao.py", str(export)]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as erreurs:
            code = analyser_seao.main()
        self.assertEqual(self.contexte.read_bytes(), octets)
        self.assertEqual(code, 1)
        self.assertIn("plusieurs colonnes s'appellent « notes »", erreurs.getvalue())
        self.assertEqual([p for p in self.sorties.rglob("*") if p.is_file()], [])


if __name__ == "__main__":
    unittest.main()
