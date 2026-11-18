"""Le rattachement d'une ligne du contexte à un organisme du répertoire, avec les règles tolérantes."""

import re

from rapidfuzz import process
from rapidfuzz.distance import DamerauLevenshtein

from barometre.contexte.fichier import A_COMPLETER
from barometre.contexte.noms import (SERVICES, cle_organisme, decrire, departager, designation_au_debut,
                                     normaliser, normaliser_code_postal, sans_territoires_non_organises,
                                     type_attendu)

# Ces règles ne servent que si le nom exact n'a rien trouvé.

# Petits mots retirés partout dans le nom : « Saint-Léon-Standon » et
# « Saint-Léon-de-Standon » désignent le même lieu.
DETERMINANTS = {"de", "du", "des", "d", "la", "le", "les", "l", "au", "aux"}
ABREVIATIONS = {"st": "saint", "ste": "sainte"}
DESIGNATIONS_LUES = {"canton": "Canton", "village": "Village", "ville": "Ville", "paroisse": "Paroisse"}

# Les quatre règles, de la plus sûre à la plus risquée. Les trois dernières
# reposent sur une ressemblance : il faut qu'un indice les confirme.
MEME_NOM = "même nom écrit autrement"
NOM_ALLONGE = "nom officiel suivi d'une précision"
NOM_RACCOURCI = "nom officiel raccourci"
NOM_APPROCHE = "nom approché, faute de frappe probable"
REGLES_A_CONFIRMER = (NOM_ALLONGE, NOM_RACCOURCI, NOM_APPROCHE)


def tolerance(mot_a, mot_b):
    """Fautes acceptées dans un mot : aucune jusqu'à 4 lettres, une jusqu'à 8, deux au-delà.

    Une faute : une lettre en trop, en moins ou remplacée, ou deux lettres voisines
    inversées. La longueur est celle du plus court des deux mots. Un mot court ne
    tolère rien : Saint-Paul et Sainte-Paule sont deux municipalités.
    """
    longueur = min(len(mot_a), len(mot_b))
    return 0 if longueur <= 4 else 1 if longueur <= 8 else 2


def mots_utiles(texte):
    """Les mots d'un texte, abréviations développées et déterminants retirés.

    « Lac-St-Jean » et « Lac-Saint-Jean » donnent tous deux lac, saint, jean.
    """
    mots = [ABREVIATIONS.get(mot, mot) for mot in normaliser(texte).split()]
    return [mot for mot in mots if mot not in DETERMINANTS]


def lire_nom_seao(nom):
    """Décompose un nom du SEAO : les mots du nom, et les indices écrits autour.

    Retourne un dictionnaire :
      mots         les mots distinctifs du nom, sans désignation ni déterminant;
      attendu      municipalité ou MRC, d'après le début du nom (voir type_attendu);
      designation  Canton, Village, Ville ou Paroisse, quand le nom le dit au
                   début, à la fin (« Marston-Canton ») ou entre parenthèses
                   (« Melbourne (Canton) »);
      parentheses  les précisions de lieu écrites entre parenthèses, comme
                   « (Mauricie) » ou « (de L'Islet) ».
    """
    entre_parentheses = re.findall(r"\(([^)]*)\)", nom)
    mots = [ABREVIATIONS.get(mot, mot) for mot in normaliser(re.sub(r"\([^)]*\)", " ", nom)).split()]

    # « M. », « Mun. » ou une faute comme « Muncipalité » valent « Municipalité ». Les
    # autres désignations sont trop courtes pour une faute : « Mille » est à une lettre de « Ville ».
    if mots and re.match(r"\s*(m|mun)\.\s", nom, re.IGNORECASE):
        mots[0] = "municipalite"
    elif mots and 0 < DamerauLevenshtein.distance(mots[0], "municipalite") <= tolerance(mots[0], "municipalite"):
        mots[0] = "municipalite"

    texte = " ".join(mots)
    cle = cle_organisme(texte).split()

    designation = designation_au_debut(nom)
    if len(cle) > 1 and cle[-1] in DESIGNATIONS_LUES:
        designation = DESIGNATIONS_LUES[cle.pop()]

    parentheses = []
    for contenu in entre_parentheses:
        contenu = normaliser(re.sub(SERVICES, "", normaliser(contenu)))
        if contenu in DESIGNATIONS_LUES:
            designation = DESIGNATIONS_LUES[contenu]
        elif mots_utiles(contenu):
            parentheses.append(mots_utiles(contenu))

    return {"mots": [mot for mot in cle if mot not in DETERMINANTS], "attendu": type_attendu(texte),
            "designation": designation, "parentheses": parentheses}


def construire_index_tolerant(index):
    """Regroupe l'index sous des clés tolérantes, abréviations développées et déterminants retirés.

    « Saint-Léon-de-Standon » y devient « saint leon standon ».
    """
    tolerant = {}
    for cle, entrees in index.items():
        cle_tolerante = " ".join(mots_utiles(cle))
        if cle_tolerante:
            tolerant.setdefault(cle_tolerante, []).extend(entrees)
    return tolerant


def lieu(correspondance):
    """Les mots de la région et de la MRC d'un candidat, pour vérifier une précision de lieu."""
    type_organisme, ligne = correspondance
    if type_organisme == "municipalité":
        return set(mots_utiles((ligne.get("regadm") or "") + " " + (ligne.get("mrc") or "")))
    if type_organisme == "MRC ou communauté":
        return set(mots_utiles(ligne.get("mrcregion") or ""))
    return set()


def code_postal_de(correspondance):
    """Le code postal d'un candidat, quel que soit le fichier d'où il vient."""
    ligne = correspondance[1]
    return normaliser_code_postal(ligne.get("mcodpos") or ligne.get("mrccodp") or ligne.get("code_postal"))


def nom_proche(mots, cle_officielle):
    """Vrai si le nom ne diffère du nom officiel que par des fautes tolérées, deux au plus.

    Même nombre de mots; chaque mot est comparé à celui de même rang (voir tolerance).
    """
    officiels = cle_officielle.split()
    if len(officiels) != len(mots):
        return False
    fautes = 0
    for mot, officiel in zip(mots, officiels):
        ecart = DamerauLevenshtein.distance(mot, officiel)
        if ecart > tolerance(mot, officiel):
            return False
        fautes += ecart
    return 0 < fautes <= 2


def rapprocher(nom, index_tolerant, codes_postaux=frozenset()):
    """Cherche un organisme par une règle tolérante, quand le nom exact n'a rien donné.

    Quatre règles, de la plus sûre à la plus risquée :
      1. le même nom écrit autrement : abréviation, déterminant oublié, désignation
         mal placée, précision entre parenthèses;
      2. le nom officiel suivi d'une précision : « Saint-Damase-de-Matapédia »;
      3. le nom officiel raccourci : « Saint-Majorique » pour Saint-Majorique-de-Grantham;
      4. un nom approché, à une ou deux fautes près (voir tolerance).
    Un candidat est retenu s'il est seul, ou désigné par un indice (désignation,
    lieu, code postal), et si aucun indice ne le contredit. Les règles 2 à 4
    exigent en plus un indice qui le confirme.

    Retourne (correspondance ou None, explication, candidats).
    """
    lecture = lire_nom_seao(nom)
    mots = lecture["mots"]
    cle = " ".join(mots)
    precisions = list(lecture["parentheses"])
    candidats, regle = [], None

    if cle in index_tolerant:
        candidats, regle = index_tolerant[cle], MEME_NOM
    if not candidats:
        # On essaie le début du nom, du plus long au plus court. Ce qui reste
        # devient une précision de lieu à vérifier.
        for longueur in range(len(mots) - 1, 1, -1):
            debut = " ".join(mots[:longueur])
            if debut in index_tolerant:
                candidats, regle = index_tolerant[debut], NOM_ALLONGE
                precisions.append(mots[longueur:])
                break
    if not candidats and len(mots) >= 2:
        candidats = [c for cle_officielle, entrees in index_tolerant.items()
                     if cle_officielle.startswith(cle + " ") for c in entrees]
        regle = NOM_RACCOURCI
    if not candidats and cle:
        proches = process.extract(cle, list(index_tolerant), scorer=DamerauLevenshtein.distance,
                                  score_cutoff=2, limit=None)
        candidats = [c for cle_officielle, _, _ in proches if nom_proche(mots, cle_officielle)
                     for c in index_tolerant[cle_officielle]]
        regle = NOM_APPROCHE
    if not candidats:
        return None, "aucun candidat", []

    # Le début du nom dit si l'on cherche une municipalité ou une MRC.
    if lecture["attendu"]:
        du_bon_type = [c for c in candidats if c[0] == lecture["attendu"]]
        if not du_bon_type:
            return None, f"aucun candidat du type attendu ({lecture['attendu']})", candidats
        candidats = du_bon_type
    candidats = sans_territoires_non_organises(candidats)

    # Chaque indice désigne zéro, un ou plusieurs candidats.
    indices = {}
    if lecture["designation"]:
        indices[f"désignation {lecture['designation']}"] = [
            c for c in candidats if c[1].get("mdes") == lecture["designation"]]
    for precision in precisions:
        indices[f"précision « {' '.join(precision)} »"] = [c for c in candidats if set(precision) <= lieu(c)]
    if codes_postaux:
        indices["code postal " + ", ".join(sorted(codes_postaux))] = [
            c for c in candidats if code_postal_de(c) in codes_postaux]

    # Un indice qui désigne un seul candidat le confirme. Deux indices qui
    # désignent deux candidats différents se contredisent : on ne choisit pas.
    designes = [(etiquette, trouves[0]) for etiquette, trouves in indices.items() if len(trouves) == 1]
    if any(candidat is not designes[0][1] for _, candidat in designes):
        return None, "indices contradictoires : " + " / ".join(e for e, _ in designes), candidats
    if len(candidats) == 1:
        choix = candidats[0]
    elif designes:
        choix = designes[0][1]
    else:
        return None, f"{len(candidats)} candidats, aucun indice ne les sépare", candidats

    confirmations = [etiquette for etiquette, _ in designes]
    if regle in REGLES_A_CONFIRMER and not confirmations:
        return None, f"{regle}, mais aucun indice ne le confirme", candidats
    # Une région écrite entre parenthèses doit être celle du candidat. On ne le
    # demande pas aux régies, dont les parenthèses contiennent plutôt un sigle.
    if choix[0] != "organisme périmunicipal":
        for precision in lecture["parentheses"]:
            if not set(precision) <= lieu(choix):
                return None, f"la précision « {' '.join(precision)} » ne correspond pas au candidat", candidats

    explication = regle + (", confirmé par " + ", ".join(confirmations) if confirmations
                           else ", seul organisme de ce nom")
    return choix, explication, candidats


def rattacher(ligne, index, index_tolerant, par_code, codes_postaux):
    """Trouve l'organisme du répertoire d'une ligne du contexte.

    Essais : le code déjà inscrit, le nom exact, puis rapprocher. Retourne
    (correspondance, méthode, échec) : la méthode est notée dans la source (None
    si le nom exact a suffi); échec vaut (genre, raison), le genre étant
    « ambigu », « absent » ou « non municipal ».
    """
    nom = ligne["organisme"]
    codes_ligne = set().union(*[codes_postaux.get(i.strip(), set())
                                for i in (ligne.get("buyer_ids") or "").split("|")])

    # 1. Un code déjà inscrit fait foi : exécution précédente ou saisie à la main.
    code = (ligne.get("code_geographique") or "").strip()
    if code and code != A_COMPLETER:
        if code in par_code:
            return par_code[code], "rattaché par le code géographique inscrit dans le contexte", None
        return None, None, ("absent", f"le code géographique {code} est introuvable dans le répertoire")

    # 2. Le nom exact.
    correspondances = index.get(cle_organisme(nom), [])

    # 3. Sinon, les règles tolérantes.
    if not correspondances:
        choix, explication, candidats = rapprocher(nom, index_tolerant, codes_ligne)
        if choix:
            return choix, f"nom rapproché ({explication})", None
        if candidats:
            liste = " | ".join(decrire(c) for c in candidats[:5]) + (" | …" if len(candidats) > 5 else "")
            return None, None, ("ambigu", f"non retenu ({explication}) : {liste}")
        if type_attendu(nom) is None:
            # Ni municipalité ni MRC dans le nom : un office d'habitation, une société...
            return None, None, ("non municipal", "absent du répertoire, et le nom n'annonce ni municipalité ni MRC")
        return None, None, ("absent", "aucun organisme du répertoire ne porte ce nom")

    # Le début du nom dit si l'on cherche une municipalité ou une MRC. Sans organisme
    # de ce type, on ne rattache pas : la Communauté métropolitaine de Montréal avait
    # ainsi reçu, à tort, la population de la Ville de Montréal.
    attendu = type_attendu(nom)
    if attendu:
        du_bon_type = [c for c in correspondances if c[0] == attendu]
        if not du_bon_type:
            liste = " | ".join(decrire(c) for c in correspondances)
            return None, None, ("ambigu", f"aucun organisme du type attendu ({attendu}) sous ce nom : {liste}")
        correspondances = du_bon_type
    if len(correspondances) > 1:
        correspondances = sans_territoires_non_organises(correspondances)

    # Plusieurs municipalités homonymes : on cherche un indice publié qui les sépare.
    methode = None
    if len(correspondances) > 1:
        choix, indice = departager(nom, correspondances, codes_ligne)
        if choix:
            correspondances, methode = [choix], f"homonyme départagé par {indice}"

    if len(correspondances) > 1:
        liste = " | ".join(decrire(c) for c in correspondances)
        return None, None, ("ambigu", f"{len(correspondances)} correspondances, aucun indice ne les sépare : {liste}")
    return correspondances[0], methode, None
