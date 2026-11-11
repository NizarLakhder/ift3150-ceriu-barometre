"""
Prépare les données de la carte du baromètre : carte/donnees.js.

Lit la base (vue etat_pga_eau et démarches) et les contours officiels des
municipalités, puis écrit un seul fichier que carte/index.html lit directement.
La base n'est pas modifiée.

Commande, après chaque chargement :
    python exporter_carte.py
Les contours sont téléchargés une fois, dans donnees_reference/. Pour en
reprendre une version plus récente :
    python exporter_carte.py --contours-a-jour
"""

import argparse
import json
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from charger_base import connecter

DOSSIER = Path(__file__).resolve().parent
CONTOURS = DOSSIER / "donnees_reference" / "contours_municipalites.geojson"
SORTIE = DOSSIER / "carte" / "donnees.js"

# Service web du ministère des Ressources naturelles et des Forêts (découpages
# administratifs, couche 2 : municipalités). Il simplifie lui-même les contours :
# environ 300 m de précision, assez pour une carte de la province.
SERVICE_CONTOURS = ("https://servicescarto.mern.gouv.qc.ca/pes/rest/services/"
                    "Territoire/SDA_WMS/MapServer/2/query")
PARAMETRES_CONTOURS = {
    "where": "1=1", "outFields": "MUS_CO_GEO,MUS_NM_MUN,SITE_WEB,MUS_CO_VER",
    "returnGeometry": "true", "outSR": "4326", "maxAllowableOffset": "0.003",
    "geometryPrecision": "4", "f": "geojson",
}

# Le texte de la vue etat_pga_eau, ramené à un mot court pour la carte.
ETATS = {
    "PGA-Eau repéré dans le SEAO": "pga",
    "démarche liée repérée dans le SEAO": "liee",
    "outil seulement repéré dans le SEAO": "outil",
    "aucune trace dans les exports chargés": "aucune",
}

# Les MRC et l'Administration régionale Kativik sont rangées dans la même table.
GENRES_MRC = {"Municipalité régionale de comté": "MRC", "Administration régionale": "Administration régionale"}


# ---------------------------------------------------------------------------
# Contours
# ---------------------------------------------------------------------------

def telecharger_contours(chemin):
    """Télécharge les contours des municipalités et les garde dans chemin."""
    url = SERVICE_CONTOURS + "?" + urllib.parse.urlencode(PARAMETRES_CONTOURS)
    requete = urllib.request.Request(url, headers={"User-Agent": "barometre-pga-eau (exporter_carte.py)"})
    with urllib.request.urlopen(requete, timeout=180) as reponse:
        contours = json.load(reponse)
    # Le service coupe sa réponse au-delà de 2 000 territoires, et il le signale.
    if contours.get("exceededTransferLimit") or contours.get("properties", {}).get("exceededTransferLimit"):
        raise ValueError("Le service des contours a coupé sa réponse : il manque des territoires.")
    chemin.parent.mkdir(exist_ok=True)
    chemin.write_text(json.dumps(contours, ensure_ascii=False), encoding="utf-8")
    return contours


def lire_contours(chemin, a_jour=False):
    """Lit les contours gardés sur le disque, ou les télécharge s'ils manquent."""
    if a_jour or not chemin.exists():
        print("Téléchargement des contours des municipalités...")
        return telecharger_contours(chemin)
    return json.loads(chemin.read_text(encoding="utf-8"))


def contour_par_code(contours, noms):
    """Un contour par code géographique.

    Deux territoires de la Côte-Nord ont un second contour, le « tracé de 1927 » de
    la frontière du Labrador. On garde celui qui porte le nom du répertoire.
    """
    par_code = {}
    for entite in contours["features"]:
        code = entite["properties"]["MUS_CO_GEO"]
        deja = par_code.get(code)
        if deja is None or (deja["properties"]["MUS_NM_MUN"] != noms.get(code)
                            and entite["properties"]["MUS_NM_MUN"] == noms.get(code)):
            par_code[code] = entite
    return par_code


def lien_site(adresse):
    """« www.ville.alma.qc.ca » devient « https://www.ville.alma.qc.ca »; vide reste vide."""
    adresse = (adresse or "").strip()
    if not adresse:
        return None
    return adresse if adresse.startswith(("http://", "https://")) else "https://" + adresse


# ---------------------------------------------------------------------------
# Données de la base
# ---------------------------------------------------------------------------

def lire_base(connexion):
    """Les municipalités avec leur état, les démarches et les exports chargés."""
    municipalites = [dict(zip(("code", "nom", "designation", "population", "region", "mrc", "genre_mrc", "etat"), ligne))
                     for ligne in connexion.execute("""
        SELECT e.code_geographique, e.nom, e.designation, e.population, r.nom, mrc.nom, mrc.designation, e.etat
        FROM analyses.etat_pga_eau e
        JOIN territoire.region r ON r.code = e.region_code
        LEFT JOIN territoire.mrc mrc ON mrc.code = e.mrc_code""")]
    demarches = [dict(zip(("code", "organisme", "classement", "etat", "date_attribution", "date_publication",
                           "montant", "fournisseur", "lien", "notes"), ligne))
                 for ligne in connexion.execute("""
        SELECT o.code_geographique, o.nom, d.classement::text, d.etat::text, d.date_attribution,
               d.date_publication, d.montant, f.nom, d.lien, d.notes
        FROM analyses.demarche d
        JOIN organismes.organisme o USING (organisme_id)
        LEFT JOIN seao.fournisseur f USING (fournisseur_id)
        WHERE d.plan = 'pga_eau'
        ORDER BY coalesce(d.date_attribution, d.date_publication) DESC NULLS LAST""")]
    exports = [dict(zip(("nom", "type", "debut", "fin"), ligne))
               for ligne in connexion.execute(
                   "SELECT nom, type::text, periode_debut, periode_fin FROM seao.fichier_source ORDER BY periode_debut")]
    return municipalites, demarches, exports


# ---------------------------------------------------------------------------
# Construction de la carte
# ---------------------------------------------------------------------------

def periodes_couvertes(exports):
    """Les périodes couvertes par les exports, sans chevauchement.

    Le mensuel de septembre et l'hebdo du 7 au 13 septembre se recouvrent : ils
    forment une seule période. Un mois manquant laisse un trou.
    """
    periodes = []
    for export in sorted(exports, key=lambda e: e["debut"]):
        if periodes and export["debut"] <= periodes[-1][1] + timedelta(days=1):
            periodes[-1][1] = max(periodes[-1][1], export["fin"])
        else:
            periodes.append([export["debut"], export["fin"]])
    return [{"debut": debut.isoformat(), "fin": fin.isoformat()} for debut, fin in periodes]


def etiquettes(municipalites):
    """Le texte proposé par la recherche, unique pour chaque municipalité.

    « Nom, Région », et la désignation quand deux municipalités de la même région
    portent le même nom, comme Plessisville (Ville) et Plessisville (Paroisse).
    Si ça ne suffit pas, comme pour les territoires « Toponyme à venir » du Nord,
    on ajoute le code géographique.
    """
    simples = {m["code"]: f"{m['nom']}, {m['region']}" for m in municipalites}
    avec_designation = {m["code"]: f"{m['nom']} ({m['designation']}), {m['region']}" for m in municipalites}
    compte_simple, compte_designation = Counter(simples.values()), Counter(avec_designation.values())
    resultat = {}
    for m in municipalites:
        texte = simples[m["code"]]
        if compte_simple[texte] > 1:
            texte = avec_designation[m["code"]]
            if compte_designation[texte] > 1:
                texte = f"{m['nom']} ({m['designation']} {m['code']}), {m['region']}"
        resultat[m["code"]] = texte
    doublons = [texte for texte, n in Counter(resultat.values()).items() if n > 1]
    if doublons:
        raise ValueError(f"Deux municipalités ont le même nom affiché : {doublons}")
    return resultat


def montant(valeur):
    """Un montant en nombre, ou None : un montant absent n'est pas un montant nul."""
    return None if valeur is None else float(valeur)


def construire(contours, municipalites, demarches, exports, genere_le):
    """Les données de la carte : un territoire GeoJSON par municipalité, avec sa fiche."""
    noms = {m["code"]: m["nom"] for m in municipalites}
    par_code = contour_par_code(contours, noms)
    manquants = [f"{m['nom']} ({m['code']})" for m in municipalites if m["code"] not in par_code]
    if manquants:
        raise ValueError(f"Contour introuvable pour {len(manquants)} municipalités, comme {manquants[:5]}. "
                         "Relancez avec --contours-a-jour.")

    demarches_par_code = defaultdict(list)
    hors_carte = []
    for d in demarches:
        fiche = {"classement": d["classement"], "etat": d["etat"],
                 "date_attribution": d["date_attribution"] and d["date_attribution"].isoformat(),
                 "date_publication": d["date_publication"] and d["date_publication"].isoformat(),
                 "montant": montant(d["montant"]), "fournisseur": d["fournisseur"], "lien": d["lien"],
                 "notes": d["notes"]}
        if d["code"] is None:
            # Une régie ou une MRC : elle n'a pas de contour de municipalité.
            hors_carte.append({"organisme": d["organisme"], **fiche})
        else:
            demarches_par_code[d["code"]].append(fiche)

    textes = etiquettes(municipalites)
    territoires = []
    for m in municipalites:
        if m["etat"] not in ETATS:
            raise ValueError(f"État inconnu dans etat_pga_eau : {m['etat']!r}")
        contour = par_code[m["code"]]
        territoires.append({"type": "Feature", "geometry": contour["geometry"], "properties": {
            "code": m["code"], "nom": m["nom"], "designation": m["designation"], "etiquette": textes[m["code"]],
            "region": m["region"], "mrc": m["mrc"], "genre_mrc": GENRES_MRC.get(m["genre_mrc"]),
            "population": m["population"], "etat": ETATS[m["etat"]],
            "site": lien_site(contour["properties"].get("SITE_WEB")),
            "demarches": demarches_par_code.get(m["code"], [])}})

    versions = sorted({e["properties"].get("MUS_CO_VER") for e in par_code.values()} - {None})
    return {
        "genere_le": genere_le.isoformat(),
        "exports": [{"nom": e["nom"], "type": e["type"], "debut": e["debut"].isoformat(),
                     "fin": e["fin"].isoformat()} for e in exports],
        "periodes": periodes_couvertes(exports),
        "version_contours": versions[-1] if versions else None,
        "hors_carte": hors_carte,
        "territoires": {"type": "FeatureCollection", "features": territoires},
    }


def ecrire(donnees, chemin):
    """Écrit les données dans un fichier JavaScript, pour que la page s'ouvre sans serveur."""
    chemin.parent.mkdir(exist_ok=True)
    texte = json.dumps(donnees, ensure_ascii=False, separators=(",", ":"))
    chemin.write_text("// Produit par exporter_carte.py. Ne pas modifier à la main.\n"
                      f"window.DONNEES = {texte};\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Prépare les données de la carte du baromètre (carte/donnees.js).")
    parser.add_argument("--contours-a-jour", action="store_true",
                        help="télécharge de nouveau les contours des municipalités")
    args = parser.parse_args()

    contours = lire_contours(CONTOURS, args.contours_a_jour)
    with connecter() as connexion:
        municipalites, demarches, exports = lire_base(connexion)
    donnees = construire(contours, municipalites, demarches, exports, date.today())
    ecrire(donnees, SORTIE)

    etats = Counter(t["properties"]["etat"] for t in donnees["territoires"]["features"])
    print(f"{SORTIE.relative_to(DOSSIER)} : {len(municipalites)} municipalités "
          f"({etats['pga']} PGA-Eau repéré, {etats['liee']} démarche liée, {etats['outil']} outil seulement, "
          f"{etats['aucune']} aucune trace), "
          f"{len(donnees['hors_carte'])} démarches hors carte, {SORTIE.stat().st_size / 1e6:.1f} Mo.")


if __name__ == "__main__":
    main()
