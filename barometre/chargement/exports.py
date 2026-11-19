"""Un export du SEAO dans la base : chaque fiche devient des lignes de tables, et l'export est chargé d'un bloc."""

import json
from datetime import date

from psycopg.types.json import Jsonb

from barometre.chargement.fournisseurs import charger_fournisseurs
from barometre.chargement.organismes import organisme_de
from barometre.modele.conversions import entier, instant, nombre, texte
from barometre.modele.organismes import Acheteur
from barometre.modele.seao import (Attribution, Classification, Contrat, Dossier, Fiche, FicheClassification, FicheFichier,
                                   FichierSource, Nomenclature, Soumissionnaire)
from barometre.sources.seao import decrire_export, get_municipal_buyer_party, validate_identifiers
from barometre.utilitaires import clean_org_name, clean_text, date_from_release_id, empreinte


def lignes_de_la_fiche(release):
    """Découpe une fiche municipale en lignes, une liste par table.

    Retourne ocid, fiche, acheteur, classifications, nomenclature, fournisseurs,
    soumissionnaires, attributions et contrats, sans numéro de fiche : la base le
    donne au chargement. Lève ValueError si la fiche contredit le schéma : pas
    exactement un acheteur, plus d'un item, une attribution sans exactement un
    fournisseur, un contrat sans son attribution.
    """
    ocid, release_id = clean_text(release.get("ocid")), clean_text(release.get("id"))
    acheteurs = [p for p in release.get("parties", []) if "buyer" in p.get("roles", [])]
    if len(acheteurs) != 1:
        raise ValueError(f"{ocid} / {release_id} : {len(acheteurs)} acheteurs au lieu d'un seul")

    tender = release.get("tender") or {}
    periode = tender.get("tenderPeriod") or {}
    items = tender.get("items") or []
    item = items[0] if items else {}
    if len(items) > 1:
        raise ValueError(f"{ocid} / {release_id} : {len(items)} items, le schéma n'en prévoit qu'un")
    documents = tender.get("documents") or []

    fiche = {
        "release_id": release_id,
        "date_deduite_numero": (date.fromisoformat(date_from_release_id(release))
                                if date_from_release_id(release) else None),
        "date_fiche": instant(release.get("date")),
        "acheteur_id": acheteurs[0]["id"],
        "tags": list(dict.fromkeys(release.get("tag") or [])),
        "numero_avis": texte(tender.get("id")),
        "titre": texte(tender.get("title")),
        "statut": texte(tender.get("status")),
        "methode_code": texte(tender.get("procurementMethod")),
        "methode": texte(tender.get("procurementMethodDetails")),
        "justification_methode": texte(tender.get("procurementMethodRationale")),
        "categorie_principale": texte(tender.get("mainProcurementCategory")),
        "type_contrat": texte(" | ".join(c.strip() for c in tender.get("additionalProcurementCategories") or [])),
        "nomenclature_code": texte(item.get("id")),
        "date_ouverture": instant(periode.get("startDate")),
        "date_fermeture": instant(periode.get("endDate")),
        "duree_jours": entier(periode.get("durationInDay")),
        "nb_soumissionnaires": entier(tender.get("numberOfTenderers")),
        "url_avis": texte(documents[0].get("url")) if documents else None,
        "brut": Jsonb(release),
    }

    classifications, codes_vus = [], set()
    principale = item.get("classification") or {}
    for c, est_principale in [(principale, True)] + [(c, False) for c in item.get("additionalClassifications") or []]:
        code = texte(c.get("id"))
        if code and code not in codes_vus:
            codes_vus.add(code)
            classifications.append({"code": code, "libelle": texte(c.get("description")) or code,
                                    "principale": est_principale})

    nomenclature = ([{"code": fiche["nomenclature_code"], "libelle": texte(item.get("description")) or fiche["nomenclature_code"]}]
                    if fiche["nomenclature_code"] else [])

    fournisseurs = []
    for p in release.get("parties", []):
        if "buyer" in p.get("roles", []) or not p.get("id"):
            continue
        adresse = p.get("address") or {}
        fournisseurs.append({
            "identifiant": p["id"], "nom": texte(p.get("name")) or p["id"],
            "neq": texte((p.get("details") or {}).get("neq")),
            "adresse": texte(adresse.get("streetAddress")), "localite": texte(adresse.get("locality")),
            "region": texte(adresse.get("region")), "code_postal": texte(adresse.get("postalCode")),
            "pays": texte(adresse.get("countryName")),
        })

    soumissionnaires = list(dict.fromkeys(t["id"] for t in tender.get("tenderers") or [] if t.get("id")))

    # Des soumissionnaires manquent dans les parties : on les garde, avec leur seul nom.
    connus = {f["identifiant"] for f in fournisseurs}
    for t in tender.get("tenderers") or []:
        if t.get("id") and t["id"] not in connus:
            connus.add(t["id"])
            fournisseurs.append({"identifiant": t["id"], "nom": texte(t.get("name")) or t["id"], "neq": None,
                                 "adresse": None, "localite": None, "region": None, "code_postal": None, "pays": None})

    attributions = []
    for a in release.get("awards") or []:
        fournisseurs_a = a.get("suppliers") or []
        if len(fournisseurs_a) != 1 or not fournisseurs_a[0].get("id"):
            raise ValueError(f"{ocid} / {release_id} : l'attribution {a.get('id')} n'a pas exactement un fournisseur identifié")
        valeur = a.get("value") or {}
        attributions.append({
            "numero": str(a.get("id")), "identifiant_fournisseur": fournisseurs_a[0]["id"],
            "statut": texte(a.get("status")), "date_attribution": instant(a.get("date")),
            "montant": nombre(valeur.get("amount")), "montant_total": nombre(valeur.get("totalAmount")),
            "devise": texte(valeur.get("currency")),
        })

    numeros_attributions = {a["numero"] for a in attributions}
    contrats = []
    for c in release.get("contracts") or []:
        if str(c.get("awardID")) not in numeros_attributions:
            raise ValueError(f"{ocid} / {release_id} : le contrat {c.get('id')} renvoie à une attribution absente de la fiche")
        valeur = c.get("value") or {}
        contrats.append({
            "numero": str(c.get("id")), "numero_attribution": str(c.get("awardID")), "statut": texte(c.get("status")),
            "date_signature": instant(c.get("dateSigned")), "date_fin": instant((c.get("period") or {}).get("endDate")),
            "montant": nombre(valeur.get("amount")), "devise": texte(valeur.get("currency")),
        })

    # Le nom nettoyé comme dans analyser_seao.py : c'est la clé de contexte_municipalites.csv.
    acheteur = {"acheteur_id": acheteurs[0]["id"],
                "organisme": clean_org_name(acheteurs[0].get("name")),
                "nom_seao": clean_text(acheteurs[0].get("name"))}

    return {"ocid": ocid, "fiche": fiche, "acheteur": acheteur, "classifications": classifications,
            "nomenclature": nomenclature, "fournisseurs": fournisseurs, "soumissionnaires": soumissionnaires,
            "attributions": attributions, "contrats": contrats}


def forme_comparable(valeur):
    """La fiche avec ses listes triées : le SEAO republie souvent une fiche dans un autre ordre."""
    if isinstance(valeur, dict):
        return {cle: forme_comparable(v) for cle, v in valeur.items()}
    if isinstance(valeur, list):
        return sorted((forme_comparable(v) for v in valeur),
                      key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
    return valeur


def meme_contenu(fiche, autre):
    """Vrai si deux publications d'une fiche ne diffèrent que par l'ordre de leurs listes."""
    return forme_comparable(fiche) == forme_comparable(autre)


def cles_des_fiches(connexion):
    """Relie chaque fiche en base, par son dossier et son numéro, au numéro que la base lui a donné."""
    return {(o, r): f for o, r, f in connexion.execute(
        "SELECT d.ocid, f.release_id, f.fiche_id FROM seao.fiche f JOIN seao.dossier d ON d.dossier_id = f.dossier_id")}


def charger_export(connexion, chemin):
    """Charge les fiches municipales d'un export, d'un seul bloc; None s'il est déjà en base.

    Retourne (fiches municipales, fiches nouvelles, fiches publiées autrement).
    Une fiche déjà en base n'est pas recopiée : seao.fiche_fichier la relie à cet
    export, avec la version publiée si elle diffère. Un fichier modifié qui garde
    le nom d'un export chargé lève ValueError.
    """
    signature = empreinte(chemin)
    meme_nom = connexion.execute("SELECT empreinte_sha256 FROM seao.fichier_source WHERE nom = %s", (chemin.name,)).fetchone()
    if meme_nom and meme_nom[0] != signature:
        raise ValueError(f"{chemin.name} est déjà en base, mais le fichier a changé depuis. "
                         "Rien n'est chargé : vérifier le fichier, ou relancer avec --reinitialiser.")
    if connexion.execute("SELECT 1 FROM seao.fichier_source WHERE empreinte_sha256 = %s", (signature,)).fetchone():
        return None
    type_fichier, debut, fin = decrire_export(chemin.name)

    with chemin.open(encoding="utf-8-sig") as fichier:
        donnees = json.load(fichier)
    releases = donnees.get("releases", [])
    validate_identifiers(releases)      # même contrôle que le programme d'analyse
    # Triées par numéro, donc par date : le dernier nom lu est le plus récent.
    municipales = sorted((lignes_de_la_fiche(r) for r in releases if get_municipal_buyer_party(r)),
                         key=lambda n: n["fiche"]["release_id"])

    (fichier_id,) = FichierSource.inserer_et_numeroter(connexion, [FichierSource(
        nom=chemin.name, type=type_fichier, periode_debut=debut, periode_fin=fin,
        date_publication=instant(donnees.get("publishedDate")), empreinte_sha256=signature, nb_fiches=len(releases))])

    deja = cles_des_fiches(connexion)
    nouvelles = [n for n in municipales if (n["ocid"], n["fiche"]["release_id"]) not in deja]
    # La version gardée des fiches déjà en base, pour voir si cet export les publie autrement.
    gardees = dict(connexion.execute(
        "SELECT fiche_id, brut FROM seao.fiche WHERE fiche_id = ANY(%s)",
        ([deja[(n["ocid"], n["fiche"]["release_id"])] for n in municipales
          if (n["ocid"], n["fiche"]["release_id"]) in deja],)).fetchall())

    def toutes(cle):
        return [ligne for n in nouvelles for ligne in n[cle]]

    # Listes de codes, fournisseurs et acheteurs d'abord : les fiches s'y réfèrent.
    Nomenclature.inserer(connexion, [Nomenclature(**n) for n in {n["code"]: n for n in toutes("nomenclature")}.values()])
    Classification.inserer(connexion, list({c["code"]: Classification(code=c["code"], libelle=c["libelle"])
                                            for c in toutes("classifications")}.values()))
    charger_fournisseurs(connexion, toutes("fournisseurs"))

    # Les acheteurs : chaque identifiant publié est rattaché à son organisme (voir organisme_de).
    organismes = dict(connexion.execute("SELECT nom, organisme_id FROM organismes.organisme").fetchall())
    connus = dict(connexion.execute("SELECT acheteur_id, organisme_id FROM organismes.acheteur").fetchall())
    acheteurs = {n["acheteur"]["acheteur_id"]: n["acheteur"] for n in nouvelles}
    rattaches = {i: organisme_de(i, a["organisme"], connus, organismes) for i, a in acheteurs.items()}
    # Un export ne décide que du nom publié : l'organisme d'un identifiant connu ne change pas.
    Acheteur.inserer(connexion, [Acheteur(acheteur_id=i, organisme_id=rattaches[i], nom_seao=a["nom_seao"])
                                 for i, a in acheteurs.items()], mises_a_jour=("nom_seao",))

    # Les dossiers, puis les fiches : la base leur donne leur numéro.
    Dossier.inserer(connexion, [Dossier(ocid=o) for o in dict.fromkeys(n["ocid"] for n in nouvelles)])
    dossiers = dict(connexion.execute("SELECT ocid, dossier_id FROM seao.dossier").fetchall())
    Fiche.inserer(connexion, [Fiche(dossier_id=dossiers[n["ocid"]], **n["fiche"]) for n in nouvelles])
    fiches = cles_des_fiches(connexion)

    classifications, soumissionnaires, attributions = [], [], []
    for n in nouvelles:
        fiche_id = fiches[(n["ocid"], n["fiche"]["release_id"])]
        classifications += [FicheClassification(fiche_id=fiche_id, code=c["code"], principale=c["principale"])
                            for c in n["classifications"]]
        soumissionnaires += [Soumissionnaire(fiche_id=fiche_id, identifiant_fournisseur=i) for i in n["soumissionnaires"]]
        attributions += [Attribution(fiche_id=fiche_id, **a) for a in n["attributions"]]
    FicheClassification.inserer(connexion, classifications)
    Soumissionnaire.inserer(connexion, soumissionnaires)
    Attribution.inserer(connexion, attributions)

    # Un contrat renvoie à son attribution par le numéro que la base a donné à celle-ci.
    numeros = {(f, numero): a for f, numero, a in connexion.execute(
        "SELECT fiche_id, numero, attribution_id FROM seao.attribution WHERE fiche_id = ANY(%s)",
        ([fiches[(n["ocid"], n["fiche"]["release_id"])] for n in nouvelles],))}
    Contrat.inserer(connexion, [
        Contrat(attribution_id=numeros[(fiches[(n["ocid"], n["fiche"]["release_id"])], c["numero_attribution"])],
                **{k: v for k, v in c.items() if k != "numero_attribution"})
        for n in nouvelles for c in n["contrats"]])

    # Chaque fiche de l'export est reliée au fichier, avec sa version si elle diffère.
    liens = []
    for n in municipales:
        fiche_id = fiches[(n["ocid"], n["fiche"]["release_id"])]
        autrement = fiche_id in gardees and not meme_contenu(gardees[fiche_id], n["fiche"]["brut"].obj)
        liens.append(FicheFichier(fiche_id=fiche_id, fichier_id=fichier_id,
                                  version_publiee=n["fiche"]["brut"] if autrement else None))
    FicheFichier.inserer(connexion, liens)
    return len(municipales), len(nouvelles), sum(1 for l in liens if l.version_publiee is not None)
