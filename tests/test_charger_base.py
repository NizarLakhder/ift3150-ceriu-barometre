"""Tests de charger_base.py : la conversion des fiches en lignes de tables, sans PostgreSQL.

La base elle-même est vérifiée à chaque chargement, par la fonction verifier.

Commande : python -B -m unittest -v test_charger_base
"""

import copy
import csv
import io
import tempfile
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import MagicMock, patch
import unittest
from datetime import date
from decimal import Decimal

import charger_base as base

# Cas réel, raccourci : le dossier PGA-Eau de Matagami, semaine du 7 septembre 2026.
MATAGAMI = {
    "ocid": "ocds-ec9k95-20170481", "id": "20260911172212", "date": "2026-09-11T13:22:12-04:00",
    "tag": ["contract"], "initiationType": "tender",
    "parties": [
        {"name": "Ville de Matagami", "id": "OP-70456", "roles": ["buyer"], "details": {"municipal": "1"}},
        {"name": "L'UNION DES MUNICIPALITÉS DU QUÉBEC", "id": "FO-1142385377", "roles": ["supplier"],
         "details": {"neq": "1142385377"},
         "address": {"streetAddress": "2020 Blvd Robert-Bourassa, #210", "locality": "Montréal", "region": "QC",
                     "postalCode": "H3A2A5", "countryName": "CAN"}}],
    "buyer": {"name": "Ville de Matagami", "id": "OP-70456"},
    "tender": {
        "id": "G-2026-09-004", "title": "Renforcement stratégique pour l'élaboration du PGA-EAU", "status": "complete",
        "items": [{"id": "S5", "description": "S5 - Services environnementaux",
                   "classification": {"scheme": "UNSPSC", "id": "77000000", "description": "Services environnementaux"},
                   "additionalClassifications": [
                       {"scheme": "UNSPSC", "id": "77100000", "description": "Gestion environnementale"},
                       {"scheme": "UNSPSC", "id": "77101700", "description": "Services-conseils en matière d’environnement"}]}],
        "procurementMethod": "direct", "procurementMethodDetails": "Contrat de gré à gré",
        "mainProcurementCategory": "services", "additionalProcurementCategories": ["Services professionnels"],
        "tenderPeriod": {"startDate": "2026-09-11T13:22:12-04:00"}, "numberOfTenderers": 1,
        "tenderers": [{"id": "FO-1142385377", "name": "L'UNION DES MUNICIPALITÉS DU QUÉBEC"}],
        "documents": [{"url": "https://seao.gouv.qc.ca/avis-resultat-recherche/consulter?ItemId=adb87320"}]},
    "awards": [{"id": "20165337", "status": "active", "date": "2026-09-08T00:00:00-04:00",
                "value": {"amount": 4892.19, "currency": "CAD"},
                "suppliers": [{"name": "L'UNION DES MUNICIPALITÉS DU QUÉBEC", "id": "FO-1142385377"}]}],
    "contracts": [{"id": "20165337", "awardID": "20165337", "status": "active",
                   "value": {"amount": 4892.19, "currency": "CAD"}, "dateSigned": "2026-09-08T00:00:00-04:00"}],
    "language": "fr",
}


def fournisseur(identifiant, nom, neq=None, adresse=None):
    """Un fournisseur tel que lignes_de_la_fiche le lit dans une fiche."""
    return {"identifiant": identifiant, "nom": nom, "neq": neq, "adresse": adresse, "localite": None,
            "region": None, "code_postal": None, "pays": None}


class ConversionsTests(unittest.TestCase):
    """Les petites conversions qui transforment le texte publié en valeurs de base de données."""

    def test_amounts_stay_exact_and_missing_values_become_null(self):
        # Pas de nombre à virgule flottante : 77061.99 reste exactement 77061.99.
        self.assertEqual(base.nombre(77061.99), Decimal("77061.99"))
        self.assertEqual(base.nombre("0.56544245"), Decimal("0.56544245"))
        # Une valeur absente devient NULL, jamais zéro.
        for valeur in (None, "", "NULL", "À compléter", "pas un nombre"):
            self.assertIsNone(base.nombre(valeur))
        self.assertIsNone(base.texte("À compléter"))

    def test_fictitious_seao_date_is_dropped(self):
        self.assertIsNone(base.instant("0001-01-01T00:00:00-05:00"))
        self.assertEqual(base.instant("2026-09-08T00:00:00-04:00").date(), date(2026, 9, 8))

    def test_region_and_mrc_codes_are_read_from_their_labels(self):
        self.assertEqual(base.region_de("Saguenay--Lac-Saint-Jean (02)"), ("02", "Saguenay--Lac-Saint-Jean"))
        self.assertEqual(base.region_de(""), (None, None))
        self.assertEqual(base.code_mrc_de("MRC Bellechasse (190)"), "AR190")
        self.assertEqual(base.code_mrc_de("Communauté métropolitaine de Montréal (663)", "CM"), "CM663")
        self.assertIsNone(base.code_mrc_de(""))

    def test_export_type_and_period_are_read_from_the_file_name(self):
        self.assertEqual(base.decrire_export("hebdo_20260907_20260913.json"),
                         ("hebdomadaire", date(2026, 9, 7), date(2026, 9, 13)))
        self.assertEqual(base.decrire_export("mensuel_20260801_20260831.json"),
                         ("mensuel", date(2026, 8, 1), date(2026, 8, 31)))
        # Un nom d'une autre forme ne dit ni le type ni la période : il arrête tout.
        with self.assertRaises(ValueError):
            base.decrire_export("export_septembre.json")

    def test_labels_become_the_codes_of_the_base(self):
        self.assertEqual(base.code_de("etat", "mandat attribué"), "mandat_attribue")
        self.assertEqual(base.code_de("gestion_actifs_eau", "plan d'intervention"), "plan_intervention")
        self.assertEqual(base.code_de("nature_transaction", "subvention ou contribution"), "subvention_ou_contribution")
        # Un libellé inconnu, même à une faute près, arrête le chargement.
        with self.assertRaises(ValueError):
            base.code_de("etat", "mandat attribue")

    def test_known_buyer_identifier_wins_over_a_new_spelling_of_the_name(self):
        connus = {"OP-81577": 1}
        organismes = {"Municipalité D'Amherst": 1, "Ville de Montréal": 2}
        # Cas réel : l'export de septembre écrit « d'Amherst », le contexte « D'Amherst ».
        self.assertEqual(base.organisme_de("OP-81577", "Municipalité d'Amherst", connus, organismes), 1)
        # Un identifiant inconnu est rattaché par le nom.
        self.assertEqual(base.organisme_de("OP-99", "Ville de Montréal", connus, organismes), 2)
        # Un nom absent du contexte, ou qui désigne un autre organisme, arrête tout.
        with self.assertRaises(ValueError):
            base.organisme_de("OP-99", "Municipalité inconnue", connus, organismes)
        with self.assertRaises(ValueError):
            base.organisme_de("OP-81577", "Ville de Montréal", connus, organismes)

    def test_organism_type_is_found_in_the_directory(self):
        municipalites, mrc = {"92030"}, {"AR930", "CM663"}
        self.assertEqual(base.type_organisme("92030", municipalites, mrc), "municipalite")
        self.assertEqual(base.type_organisme("AR930", municipalites, mrc), "mrc_ou_communaute")
        self.assertEqual(base.type_organisme("CM663", municipalites, mrc), "mrc_ou_communaute")
        self.assertEqual(base.type_organisme("À compléter", municipalites, mrc), "non_municipal")
        # Un code absent du répertoire n'est pas deviné d'après sa forme.
        with self.assertRaises(ValueError):
            base.type_organisme("AR999", municipalites, mrc)


class FicheTests(unittest.TestCase):
    """Une fiche du SEAO devient des lignes, une liste par table."""

    def test_matagami_is_split_into_its_tables(self):
        lignes = base.lignes_de_la_fiche(MATAGAMI)
        fiche = lignes["fiche"]
        self.assertEqual((lignes["ocid"], fiche["release_id"]), ("ocds-ec9k95-20170481", "20260911172212"))
        self.assertEqual(fiche["date_deduite_numero"], date(2026, 9, 11))
        self.assertEqual(fiche["acheteur_id"], "OP-70456")
        self.assertEqual(fiche["nomenclature_code"], "S5")
        # Les étiquettes restent dans la fiche, sous forme de liste.
        self.assertEqual(fiche["tags"], ["contract"])
        self.assertEqual(lignes["acheteur"]["organisme"], "Ville de Matagami")
        self.assertEqual([(c["code"], c["principale"]) for c in lignes["classifications"]],
                         [("77000000", True), ("77100000", False), ("77101700", False)])
        self.assertEqual(lignes["attributions"][0]["montant"], Decimal("4892.19"))
        self.assertEqual(lignes["attributions"][0]["identifiant_fournisseur"], "FO-1142385377")
        self.assertEqual(lignes["contrats"][0]["numero_attribution"], "20165337")
        self.assertEqual([f["identifiant"] for f in lignes["fournisseurs"]], ["FO-1142385377"])
        self.assertEqual(lignes["fournisseurs"][0]["neq"], "1142385377")
        self.assertEqual(lignes["soumissionnaires"], ["FO-1142385377"])

    def test_inconsistent_fiche_stops_the_load(self):
        # Le schéma range le fournisseur dans l'attribution : deux fournisseurs ne rentrent pas.
        fiche = copy.deepcopy(MATAGAMI)
        fiche["awards"][0]["suppliers"].append({"name": "Autre", "id": "FO-2"})
        with self.assertRaises(ValueError):
            base.lignes_de_la_fiche(fiche)
        # Un contrat qui renvoie à une attribution absente de la fiche.
        fiche = copy.deepcopy(MATAGAMI)
        fiche["contracts"][0]["awardID"] = "99999999"
        with self.assertRaises(ValueError):
            base.lignes_de_la_fiche(fiche)

    def test_tenderer_missing_from_parties_is_still_kept(self):
        # Cas réel : 361 soumissionnaires des deux exports ne figurent pas dans la liste des parties.
        fiche = copy.deepcopy(MATAGAMI)
        fiche["tender"]["tenderers"].append({"id": "FO-20159563", "name": "CONTROL CASE LLC"})
        lignes = base.lignes_de_la_fiche(fiche)
        self.assertIn(("FO-20159563", "CONTROL CASE LLC"), [(f["identifiant"], f["nom"]) for f in lignes["fournisseurs"]])
        self.assertEqual(len(lignes["soumissionnaires"]), 2)

    def test_same_fiche_in_another_order_is_not_another_version(self):
        # Cas réel : le SEAO republie souvent une fiche avec ses parties dans un autre ordre.
        autre_ordre = copy.deepcopy(MATAGAMI)
        autre_ordre["parties"].reverse()
        self.assertTrue(base.meme_contenu(MATAGAMI, autre_ordre))
        # Mais il change parfois aussi ses étiquettes : c'est une autre version.
        autres_etiquettes = copy.deepcopy(MATAGAMI)
        autres_etiquettes["tag"] = ["contractUpdate", "tenderUpdate"]
        self.assertFalse(base.meme_contenu(MATAGAMI, autres_etiquettes))

    def test_missing_amount_stays_missing(self):
        # Un montant absent n'est pas un montant nul.
        fiche = copy.deepcopy(MATAGAMI)
        del fiche["awards"][0]["value"]["amount"]
        self.assertIsNone(base.lignes_de_la_fiche(fiche)["attributions"][0]["montant"])


class FournisseursTests(unittest.TestCase):
    """Les identifiants FO d'un export, rangés par entreprise."""

    def test_same_neq_means_same_company(self):
        lus = [fournisseur("FO-1", "Aqua Data inc.", neq="1111111111"),
               fournisseur("FO-2", "AQUA DATA INC.", neq="1111111111"),
               fournisseur("FO-3", "Autre inc.")]
        a_creer, rattaches, a_mettre_a_jour = base.regrouper_fournisseurs(lus, {}, {})
        # Deux identifiants, un seul NEQ : une seule entreprise, qui garde le dernier nom lu.
        self.assertEqual([g["identifiants"] for g in a_creer], [["FO-1", "FO-2"], ["FO-3"]])
        self.assertEqual(a_creer[0]["infos"]["nom"], "AQUA DATA INC.")
        self.assertEqual((rattaches, a_mettre_a_jour), ([], {}))

    def test_new_identifier_with_a_known_neq_joins_its_company(self):
        a_creer, rattaches, a_mettre_a_jour = base.regrouper_fournisseurs(
            [fournisseur("FO-9", "Aqua Data inc.", neq="1111111111")], {"FO-1": 7}, {"1111111111": 7})
        self.assertEqual((a_creer, rattaches), ([], [("FO-9", 7)]))
        self.assertEqual(a_mettre_a_jour[7]["nom"], "Aqua Data inc.")

    def test_missing_neq_or_address_never_erases_a_known_one(self):
        # Le même fournisseur lu deux fois : dans les parties, puis comme simple soumissionnaire.
        lus = [fournisseur("FO-1", "Aqua Data inc.", neq="1111111111", adresse="1 rue de l'Eau"),
               fournisseur("FO-1", "AQUA DATA")]
        infos = base.regrouper_fournisseurs(lus, {}, {})[0][0]["infos"]
        self.assertEqual((infos["nom"], infos["neq"], infos["adresse"]), ("AQUA DATA", "1111111111", "1 rue de l'Eau"))

    def test_known_identifier_with_another_company_neq_stops_the_load(self):
        with self.assertRaises(ValueError):
            base.regrouper_fournisseurs([fournisseur("FO-1", "A", neq="2222222222")], {"FO-1": 7}, {"2222222222": 8})


class DemarchesTests(unittest.TestCase):
    """Une ligne de demarches.csv, classée à la main, devient une ligne de table."""

    LIGNE = {"organisme": "Ville de Nicolet", "plan": "PGA-Eau", "classement": "élaboration",
             "etat": "mandat attribué", "date_attribution": "2026-07-28", "date_publication": "2026-08-05",
             "montant": "77061.99", "fournisseur": "LES SERVICES EXP INC.", "ocid": "ocds-ec9k95-20163303",
             "lien": "", "source": "SEAO", "notes": ""}

    def convertir(self, **changements):
        return base.ligne_de_demarche({**self.LIGNE, **changements}, {"Ville de Nicolet": 7},
                                      {"ocds-ec9k95-20163303": 3, "ocds-ec9k95-1": 4}, {3: {12}})

    def test_demarche_line_is_converted_and_linked_to_its_dossier(self):
        rangee = self.convertir()
        self.assertEqual((rangee["organisme_id"], rangee["dossier_id"], rangee["fournisseur_id"]), (7, 3, 12))
        self.assertEqual((rangee["plan"], rangee["classement"], rangee["etat"]), ("pga_eau", "elaboration", "mandat_attribue"))
        self.assertEqual(rangee["date_attribution"], date(2026, 7, 28))
        self.assertEqual(rangee["montant"], Decimal("77061.99"))
        self.assertIsNone(rangee["lien"])

    def test_call_for_tenders_has_no_amount_and_no_supplier(self):
        # Un appel d'offres en cours n'a ni date d'attribution, ni montant, ni fournisseur : ils restent vides.
        en_cours = self.convertir(etat="appel d'offres en cours", date_attribution="", montant="", fournisseur="",
                                  ocid="ocds-ec9k95-1")
        self.assertEqual((en_cours["date_attribution"], en_cours["montant"], en_cours["fournisseur_id"]), (None, None, None))

    def test_unknown_organism_dossier_or_supplier_stops_everything(self):
        with self.assertRaises(ValueError):
            base.ligne_de_demarche(self.LIGNE, {}, {"ocds-ec9k95-20163303": 3}, {3: {12}})
        with self.assertRaises(ValueError):
            self.convertir(ocid="ocds-ec9k95-absent")
        # Le fichier nomme un fournisseur, mais le dossier n'en a aucun.
        with self.assertRaises(ValueError):
            self.convertir(ocid="ocds-ec9k95-1")


class VerificationFinaleTests(unittest.TestCase):
    """Petits exports synthétiques ; aucune connexion à PostgreSQL."""

    COLONNES = ["ocid", "release_id", "montant_attribue", "pga_eau", "gestion_actifs_eau"]
    LIGNE = {"ocid": "ocds-test-1", "release_id": "20260101000000",
             "montant_attribue": "10.00", "pga_eau": "oui", "gestion_actifs_eau": "PGA-Eau"}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name)
        self.sorties = patch.object(base.analyser_seao, "noms_de_sortie",
                                    side_effect=lambda chemin: (self.racine / (chemin.stem + ".csv"),))
        self.sorties.start()
        self.addCleanup(self.sorties.stop)
        self.exports = [(1, "premier.json"), (2, "second.json")]
        self.connexion = MagicMock()
        self.connexion.execute.side_effect = self.requete
        self.lignes_base = [("ocds-test-1", "20260101000000", True, "pga_eau")]
        self.montant_base = Decimal("10.00")

    def requete(self, sql, params=None):
        resultat = MagicMock()
        if "SELECT fichier_id, nom" in sql:
            resultat.fetchall.return_value = self.exports
        elif "SELECT d.ocid, f.release_id" in sql:
            resultat.fetchall.return_value = self.lignes_base
        elif "sum(a.montant)" in sql:
            resultat.fetchone.return_value = (self.montant_base,)
        else:
            raise AssertionError(f"Requête inattendue : {sql}")
        return resultat

    def ecrire(self, nom, lignes=None, colonnes=None):
        chemin = self.racine / (Path(nom).stem + ".csv")
        with chemin.open("w", encoding="utf-8-sig", newline="") as fichier:
            ecrivain = csv.DictWriter(fichier, fieldnames=colonnes or self.COLONNES)
            ecrivain.writeheader()
            ecrivain.writerows([self.LIGNE] if lignes is None else lignes)
        return chemin

    def verifier(self):
        with redirect_stdout(io.StringIO()):
            return base.verifier(self.connexion)

    def test_tous_les_exports_sont_compares(self):
        for _, nom in self.exports:
            self.ecrire(nom)
        bilan = self.verifier()
        self.assertEqual(bilan.code_sortie, 0)
        self.assertEqual(bilan.exports_attendus, [n for _, n in self.exports])
        self.assertEqual(bilan.exports_compares, bilan.exports_attendus)
        self.assertEqual((bilan.ecarts, bilan.erreurs_lecture, bilan.fichiers_absents), ([], [], []))

    def test_un_csv_absent_ne_masque_pas_la_comparaison_restante(self):
        self.ecrire("second.json")
        bilan = self.verifier()
        self.assertEqual(bilan.code_sortie, 2)
        self.assertEqual(bilan.exports_compares, ["second.json"])
        self.assertEqual(len(bilan.fichiers_absents), 1)

    def test_tous_les_csv_absents(self):
        bilan = self.verifier()
        self.assertEqual(bilan.code_sortie, 2)
        self.assertEqual(len(bilan.fichiers_absents), 2)
        self.assertEqual(bilan.exports_compares, [])

    def test_aucun_export(self):
        self.exports = []
        bilan = self.verifier()
        self.assertEqual(bilan.code_sortie, 2)
        self.assertEqual(bilan.exports_attendus, [])

    def test_entetes_invalides_ou_fichier_vide(self):
        self.exports = self.exports[:1]
        chemin = self.ecrire("premier.json", [], ["autre"])
        for contenu in (chemin.read_bytes(), b"", b"ocid,ocid,release_id,montant_attribue,pga_eau,gestion_actifs_eau\n"):
            with self.subTest(contenu=contenu):
                chemin.write_bytes(contenu)
                bilan = self.verifier()
                self.assertEqual(bilan.code_sortie, 1)
                self.assertEqual(len(bilan.erreurs_lecture), 1)

    def test_csv_illisible(self):
        self.exports = self.exports[:1]
        self.ecrire("premier.json")
        with patch.object(Path, "open", side_effect=PermissionError("accès refusé")):
            bilan = self.verifier()
        self.assertEqual(bilan.code_sortie, 1)
        self.assertIn("accès refusé", bilan.erreurs_lecture[0])

    def test_encodage_invalide(self):
        self.exports = self.exports[:1]
        self.ecrire("premier.json").write_bytes(b"\xff\xfe\xff")
        self.assertEqual(self.verifier().code_sortie, 1)

    def test_identifiants_dupliques(self):
        self.ecrire("premier.json", [self.LIGNE, self.LIGNE])
        bilan = self.verifier()
        self.assertEqual(bilan.code_sortie, 1)  # prime sur le second CSV absent
        self.assertIn("dupliqués", bilan.erreurs_lecture[0])

    def test_cellules_et_valeurs_invalides(self):
        self.exports = self.exports[:1]
        for changement in ({"ocid": ""}, {"montant_attribue": "abc"},
                           {"montant_attribue": "NaN"}, {"montant_attribue": "Infinity"},
                           {"pga_eau": "peut-être"}, {"gestion_actifs_eau": "inconnu"}):
            with self.subTest(changement=changement):
                self.ecrire("premier.json", [{**self.LIGNE, **changement}])
                self.assertEqual(self.verifier().code_sortie, 1)
        chemin = self.ecrire("premier.json")
        with chemin.open("a", encoding="utf-8") as fichier:
            fichier.write("trop,court\n")
        self.assertEqual(self.verifier().code_sortie, 1)

    def test_ecart_de_montant(self):
        self.ecrire("premier.json")
        self.montant_base = Decimal("12.00")
        bilan = self.verifier()
        self.assertEqual(bilan.code_sortie, 1)
        self.assertTrue(any("montants" in e for e in bilan.ecarts))

    def test_ecarts_de_classification(self):
        self.ecrire("premier.json")
        for pga, famille in ((False, "pga_eau"), (True, "outil"), (None, None)):
            with self.subTest(pga=pga, famille=famille):
                self.lignes_base = [("ocds-test-1", "20260101000000", pga, famille)]
                bilan = self.verifier()
                self.assertEqual(bilan.code_sortie, 1)
                self.assertTrue(bilan.ecarts)

    def test_ecart_identifiants(self):
        self.ecrire("premier.json")
        self.lignes_base = [("autre", "20260101000000", True, "pga_eau")]
        self.assertIn("premier.json : fiches différentes", self.verifier().ecarts)

    def test_entetes_seuls_valides_si_aucune_fiche_attendue(self):
        self.exports = self.exports[:1]
        self.ecrire("premier.json", [])
        self.lignes_base = []
        self.montant_base = Decimal(0)
        self.assertEqual(self.verifier().code_sortie, 0)

    def test_erreur_sql_remonte_sans_poursuivre_transaction(self):
        self.ecrire("premier.json")
        self.connexion.execute.side_effect = RuntimeError("requête interrompue")
        with self.assertRaisesRegex(RuntimeError, "interrompue"):
            self.verifier()


class CodesDeSortieTests(unittest.TestCase):
    def test_main_transmet_les_trois_codes_et_conserve_les_commits(self):
        cas = [base.BilanValidation(["a"], ["a"]),
               base.BilanValidation(["a"], ["a"], ecarts=["écart synthétique"]),
               base.BilanValidation(["a"], fichiers_absents=["a.csv"])]
        for attendu, bilan in enumerate(cas):
            with self.subTest(code=attendu), ExitStack() as pile:
                connexion = MagicMock()
                connexion.__enter__.return_value = connexion
                connexion.execute.return_value.fetchone.return_value = (1,)
                pile.enter_context(patch.object(base, "connecter", return_value=connexion))
                pile.enter_context(patch.object(base.sys, "argv", ["charger_base.py"]))
                pile.enter_context(patch.object(Path, "glob", return_value=[]))
                for nom, retour in (("charger_territoire", None), ("charger_organismes", (1, 1)),
                                    ("classer_fiches", 1), ("charger_demarches", 1),
                                    ("version_des_regles", "test"), ("verifier", bilan),
                                    ("dossiers_a_classer", []), ("fournisseurs_a_regrouper", []),
                                    ("write_csv", None)):
                    pile.enter_context(patch.object(base, nom, return_value=retour))
                sortie = pile.enter_context(redirect_stdout(io.StringIO()))
                self.assertEqual(base.main(), attendu)
                self.assertEqual(connexion.commit.call_count, 3)
                self.assertEqual("Validation complète" in sortie.getvalue(), attendu == 0)
                if attendu:
                    self.assertIn("restent enregistrées", sortie.getvalue())

    def test_erreur_apres_commit_conserve_les_etapes_precedentes(self):
        connexion = MagicMock()
        connexion.__enter__.return_value = connexion
        connexion.execute.return_value.fetchone.return_value = (1,)
        with patch.object(base.sys, "argv", ["charger_base.py"]), \
                patch.object(base, "connecter", return_value=connexion), \
                patch.object(base, "charger_territoire", side_effect=ValueError("référence invalide")), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as sortie:
            self.assertEqual(base.main(), 1)
        self.assertEqual(connexion.commit.call_count, 1)
        self.assertIs(connexion.__exit__.call_args.args[0], ValueError)
        self.assertIn("commits précédents", sortie.getvalue())

    def test_erreur_technique_retourne_un_et_explique_les_commits(self):
        with patch.object(base.sys, "argv", ["charger_base.py"]), \
                patch.object(base, "executer_chargement", side_effect=RuntimeError("panne synthétique")), \
                redirect_stderr(io.StringIO()) as sortie:
            self.assertEqual(base.main(), 1)
        self.assertIn("panne synthétique", sortie.getvalue())
        self.assertIn("commits précédents", sortie.getvalue())


if __name__ == "__main__":
    unittest.main()
