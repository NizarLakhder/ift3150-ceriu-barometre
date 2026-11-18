"""Le territoire : régions, MRC, municipalités avec leurs anciens codes, et indicateurs d'eau du MAMH.

Chaque fichier de référence chargé est noté avec son empreinte et sa date (territoire.fichier_reference).
"""

import csv
from datetime import datetime

from barometre.chemins import REGROUPEMENTS_CSV
from barometre.modele.conversions import entier, nombre, region_de, texte
from barometre.modele.territoire import FichierReference, IndicateurEau, Mrc, Municipalite, Region
from barometre.sources.mamh import DOSSIER_SOURCES, FICHIERS, lire_csv
from utilitaires import empreinte


def noter_fichier_reference(connexion, chemin, description):
    """Garde la trace d'un fichier de référence : son empreinte, qui identifie la version chargée,
    et la date du fichier sur le disque.

    Cette date peut venir d'un téléchargement, d'une copie ou d'une extraction : elle ne prouve
    ni la publication, ni le téléchargement, ni la dernière modification du contenu.
    """
    FichierReference.inserer(connexion, [FichierReference(
        nom=chemin.name, description=description,
        date_fichier=datetime.fromtimestamp(chemin.stat().st_mtime).date(),
        empreinte_sha256=empreinte(chemin))])


def charger_territoire(connexion):
    """Charge régions, MRC, municipalités avec leurs anciens codes, et données sur l'eau.

    Une nouvelle version d'un fichier remplace les valeurs déjà en base.
    """
    dossier = DOSSIER_SOURCES

    def lire(cle):
        nom, _, description = FICHIERS[cle]
        chemin = dossier / nom
        noter_fichier_reference(connexion, chemin, description)
        return lire_csv(chemin.read_bytes())

    municipalites, mrc = lire("municipalites"), lire("mrc")

    regions = {}
    for libelle in [m["regadm"] for m in municipalites] + [m["mrcregion"] for m in mrc]:
        code, nom = region_de(libelle)
        if code:
            if code in regions and regions[code] != nom:
                raise ValueError(f"La région {code} porte deux noms : {regions[code]} et {nom}")
            regions[code] = nom
    Region.inserer(connexion, [Region(code=c, nom=n) for c, n in sorted(regions.items())])

    Mrc.inserer(connexion, [Mrc.depuis_repertoire(m) for m in mrc])

    # Une municipalité regroupée laisse son code et son nom à celle qui l'a absorbée.
    # L'ancien code doit avoir quitté le répertoire, et la nouvelle municipalité y être.
    with REGROUPEMENTS_CSV.open(encoding="utf-8-sig", newline="") as fichier:
        regroupements = list(csv.DictReader(fichier))
    noter_fichier_reference(connexion, REGROUPEMENTS_CSV, "Regroupements de municipalités, tenus à la main avec leur source")
    actuels = {m["mcode"].strip() for m in municipalites}
    successeurs, anciens = {}, {}
    for r in regroupements:
        if r["ancien_code"] in actuels or r["ancien_code"] in successeurs or r["code_geographique"] not in actuels:
            raise ValueError(f"regroupements.csv : l'ancien code {r['ancien_code']} ou la municipalité "
                             f"{r['code_geographique']} ne correspond pas au répertoire.")
        successeurs[r["ancien_code"]] = r["code_geographique"]
        codes, noms = anciens.setdefault(r["code_geographique"], ([], []))
        codes.append(r["ancien_code"])
        noms.append(r["ancien_nom"])

    Municipalite.inserer(connexion, [Municipalite.depuis_repertoire(m, anciens) for m in municipalites])

    # Les trois fichiers de la Stratégie, réunis par code et par année. Le zéro
    # du début manque parfois : on complète chaque code à cinq chiffres.
    eau = {}
    for cle, colonne_code, champs in (
            ("validite", "mun_c", {"classe_population": "cl_pop_desservie", "population_desservie": "pop_desservie",
                                   "validite_audit_pct": "pourc_indice_validite"}),
            ("fuites", "num_c", {"indice_fuites": "indice_fuites_ifi", "longueur_reseau_km": "long_reseau_km"}),
            ("consommation", "mun_c", {"consommation_l_pers_jour": "consom_resid"})):
        for ligne in lire(cle):
            code = ligne[colonne_code].strip().zfill(5)
            rangee = eau.setdefault((code, int(ligne["annee"])), {
                "code_source": code, "annee": int(ligne["annee"]),
                "nom_source": texte(ligne.get("mun_n") or ligne.get("num_n")),
                "code_geographique": code if code in actuels else successeurs.get(code),
                "classe_population": None, "population_desservie": None, "indice_fuites": None,
                "validite_audit_pct": None, "consommation_l_pers_jour": None, "longueur_reseau_km": None})
            for colonne, source in champs.items():
                valeur = texte(ligne.get(source))
                rangee[colonne] = (valeur if colonne == "classe_population"
                                   else entier(valeur) if colonne == "population_desservie" else nombre(valeur))
    IndicateurEau.inserer(connexion, [IndicateurEau(**rangee) for rangee in eau.values()])
