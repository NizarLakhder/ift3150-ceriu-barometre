"""La vérification finale : export par export, la base redonne-t-elle les chiffres des CSV d'analyse ?"""

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from barometre.chemins import DOSSIER_SEAO, noms_de_sortie
from barometre.modele.conversions import code_de


@dataclass
class BilanValidation:
    """Ce qui a réellement été comparé, et ce qui empêche de conclure."""

    exports_attendus: list[str] = field(default_factory=list)
    exports_compares: list[str] = field(default_factory=list)
    fichiers_absents: list[str] = field(default_factory=list)
    erreurs_lecture: list[str] = field(default_factory=list)
    ecarts: list[str] = field(default_factory=list)

    @property
    def code_sortie(self):
        # Une erreur prime sur une comparaison manquante.
        if self.erreurs_lecture or self.ecarts:
            return 1
        if (not self.exports_attendus or self.fichiers_absents
                or self.exports_compares != self.exports_attendus):
            return 2
        return 0


def lire_csv_de_verification(chemin):
    """Refuse un CSV incomplet ou ambigu avant de calculer les comparaisons."""
    requis = {"ocid", "release_id", "montant_attribue", "pga_eau", "gestion_actifs_eau"}
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier, strict=True)
        colonnes = lecteur.fieldnames or []
        if not requis.issubset(colonnes) or len(colonnes) != len(set(colonnes)):
            raise ValueError("en-têtes CSV absents, incomplets ou dupliqués")
        details = list(lecteur)
    cles = set()
    for numero, ligne in enumerate(details, start=2):
        if None in ligne or any(v is None for v in ligne.values()):
            raise ValueError(f"ligne {numero} : nombre de cellules incorrect")
        cle = (ligne["ocid"], ligne["release_id"])
        if not all(v.strip() for v in cle):
            raise ValueError(f"ligne {numero} : identifiant absent")
        if cle in cles:
            raise ValueError(f"ligne {numero} : identifiants dupliqués {cle}")
        cles.add(cle)
        if ligne["pga_eau"] not in ("oui", "non"):
            raise ValueError(f"ligne {numero} : pga_eau doit valoir oui ou non")
        if ligne["gestion_actifs_eau"]:
            code_de("gestion_actifs_eau", ligne["gestion_actifs_eau"])
        if ligne["montant_attribue"]:
            try:
                montant = Decimal(ligne["montant_attribue"])
            except InvalidOperation as erreur:
                raise ValueError(f"ligne {numero} : montant invalide") from erreur
            if not montant.is_finite():
                raise ValueError(f"ligne {numero} : montant non fini")
    return details


def verifier(connexion):
    """Compare les exports chargés aux CSV : absence, erreur ou écart.

    Une erreur SQL remonte à main pour annuler la transaction courante.
    Une erreur de fichier est consignée pour poursuivre les autres CSV.
    """
    exports = connexion.execute("SELECT fichier_id, nom FROM seao.fichier_source ORDER BY periode_fin, periode_debut").fetchall()
    bilan = BilanValidation(exports_attendus=[nom for _, nom in exports])
    for fichier_id, nom in exports:
        details_csv = noms_de_sortie(DOSSIER_SEAO / nom)[0]
        try:
            details = lire_csv_de_verification(details_csv)
        except FileNotFoundError:
            bilan.fichiers_absents.append(str(details_csv))
            print(f"  {nom} : {details_csv} absent, comparaison impossible (lancer analyser_seao.py)")
            continue
        except (OSError, UnicodeError, csv.Error, ValueError) as erreur:
            message = f"{nom} : {details_csv} : {erreur}"
            bilan.erreurs_lecture.append(message)
            print(f"  CSV invalide ou illisible : {message}")
            continue
        # Les fiches reliées à cet export, même celles qu'un autre export avait déjà apportées.
        lignes = connexion.execute(
            "SELECT d.ocid, f.release_id, c.pga_eau, c.gestion_actifs_eau FROM seao.fiche_fichier ff "
            "JOIN seao.fiche f ON f.fiche_id = ff.fiche_id JOIN seao.dossier d ON d.dossier_id = f.dossier_id "
            "LEFT JOIN analyses.fiche_classee c ON c.fiche_id = f.fiche_id WHERE ff.fichier_id = %s", (fichier_id,)).fetchall()
        bilan.exports_compares.append(nom)
        if any(pga is None for _, _, pga, _ in lignes):
            bilan.ecarts.append(f"{nom} : classification absente en base")
        en_base = {(o, r) for o, r, _, _ in lignes}
        pga_base = {(o, r) for o, r, pga, _ in lignes if pga}
        gestion_base = {(o, r, g) for o, r, _, g in lignes if g is not None}
        somme_base = connexion.execute(
            "SELECT coalesce(sum(a.montant), 0) FROM seao.attribution a "
            "JOIN seao.fiche_fichier ff ON ff.fiche_id = a.fiche_id WHERE ff.fichier_id = %s", (fichier_id,)).fetchone()[0]
        cles = {(d["ocid"], d["release_id"]) for d in details}
        somme_csv = sum(Decimal(d["montant_attribue"]) for d in details if d["montant_attribue"])
        pga_csv = {(d["ocid"], d["release_id"]) for d in details if d["pga_eau"] == "oui"}
        gestion_csv = {(d["ocid"], d["release_id"], code_de("gestion_actifs_eau", d["gestion_actifs_eau"]))
                       for d in details if d["gestion_actifs_eau"]}
        print(f"  {nom} : {len(en_base)} fiches sur {len(details)} | montants attribués {somme_base:,.2f} $ "
              f"contre {somme_csv:,.2f} $ dans le CSV | PGA-Eau {len(pga_base)} sur {len(pga_csv)} | "
              f"gestion des actifs en eau {len(gestion_base)} sur {len(gestion_csv)}")
        if en_base != cles:
            bilan.ecarts.append(f"{nom} : fiches différentes")
        if abs(somme_base - somme_csv) > Decimal("0.01"):
            bilan.ecarts.append(f"{nom} : somme des montants différente")
        if pga_base != pga_csv:
            bilan.ecarts.append(f"{nom} : dossiers PGA-Eau différents")
        if gestion_base != gestion_csv:
            bilan.ecarts.append(f"{nom} : repérage de la gestion des actifs en eau différent")
    return bilan
