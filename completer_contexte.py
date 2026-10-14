"""
Complète le contexte municipal avec les données officielles du MAMH.

Projet IFT3150 de Nizar Lakhder, Université de Montréal, automne 2026.

Le SEAO ne dit rien de la population, de la superficie ni de l'état des
réseaux d'eau. Ces informations viennent de deux jeux de données ouverts du
ministère des Affaires municipales et de l'Habitation, publiés sur Données
Québec sous licence Creative Commons avec attribution.

Ce programme ne télécharge rien. Il lit les fichiers déposés à la main dans
donnees_reference/ et reporte leurs valeurs dans contexte_municipalites.csv.
Pourquoi ne pas télécharger? Pour que les mêmes fichiers donnent toujours les
mêmes chiffres, et pour ne pas dépendre d'une adresse web qui peut changer du
jour au lendemain. La date des fichiers utilisés est notée dans la colonne
source_contexte : on peut toujours retrouver d'où vient une valeur.

Fichiers attendus dans donnees_reference/, à prendre sur Données Québec :

  Répertoire des municipalités du Québec
    MUN.csv                          obligatoire : code géographique,
                                     population, superficie, région, MRC
    MRC_CM_Arg.csv                   facultatif : MRC et communautés
                                     métropolitaines
    A01_CONVERT_XML_ORG_PER_MUN.xml  facultatif : régies, transport,
                                     habitation

  Stratégie québécoise d'économie d'eau potable 2019-2025, données de 2024
    validite_classe_2024.csv         facultatif : population desservie et
                                     validité des audits de l'eau
    fuites_classe_2024.csv           facultatif : indice de fuites
    consommation_classe_2024.csv     facultatif : consommation résidentielle

Comment un organisme du SEAO est rattaché au répertoire, dans cet ordre :

  1. par le code géographique, s'il est déjà inscrit dans le contexte. C'est
     aussi la façon de régler un cas à la main : on écrit le code dans la
     colonne code_geographique, et le programme remplit le reste;
  2. par le nom exact, une fois retirés les accents, la ponctuation, la
     désignation et les articles du début;
  3. sinon, par une règle tolérante, qui rattrape les écarts d'écriture du
     SEAO : « St » pour Saint, un « de » oublié, une précision entre
     parenthèses, une faute de frappe. Voir la section « Rapprochement
     tolérant » plus bas.

Ce que le programme s'interdit :

  - remplacer une valeur déjà saisie : il ne remplit que les cases encore
    « À compléter »;
  - choisir au hasard : quand un nom correspond à plusieurs municipalités du
    répertoire, il ne tranche qu'avec un indice publié, le code postal donné
    par le SEAO, une désignation distinctive écrite dans le nom (Canton,
    Village, Ville, Paroisse) ou une région écrite entre parenthèses. Sans
    indice, il ne remplit rien et signale le cas, avec les candidats.
    Les codes postaux sont lus dans les vues produites par analyser_seao.py
    (sorties/*enrichir*.csv) : lancer l'analyse avant ce programme;
  - se fier à une ressemblance : un nom seulement approché, raccourci ou
    allongé n'est retenu que si un indice le confirme;
  - inventer : la proximité d'un cours d'eau et le type de milieu restent
    à compléter, puisqu'aucun de ces fichiers ne les fournit.

Avant d'écrire, il copie le contexte actuel dans
sorties/contexte_municipalites.csv.bak. Il n'y a qu'une sauvegarde, remplacée
à chaque exécution. Les organismes qu'il n'a pas pu rattacher sont listés dans
sorties/contexte_a_verifier.csv. La colonne a_traiter y sépare les cas à
trancher à la main (« oui ») des organismes non municipaux, comme les régies
et les offices d'habitation, pour lesquels le répertoire n'a ni population ni
superficie à reporter (« non »).

Une seule bibliothèque externe : rapidfuzz, qui mesure l'écart entre deux
mots. Installation : pip install -r requirements.txt

Lancement :  python completer_contexte.py
"""

import csv
import re
import shutil
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

from rapidfuzz import process
from rapidfuzz.distance import DamerauLevenshtein

CONTEXTE_CSV = Path("contexte_municipalites.csv")
DOSSIER_SOURCES = Path("donnees_reference")
DOSSIER_SORTIES = Path("sorties")
A_VERIFIER_CSV = DOSSIER_SORTIES / "contexte_a_verifier.csv"

# Pour chaque fichier : son nom, s'il est obligatoire, et où le trouver sur
# Données Québec (le jeu de données, puis la ressource). Cette description est
# affichée quand le fichier manque, pour savoir quoi aller chercher.
FICHIERS = {
    "municipalites": ("MUN.csv", True,
                      "Répertoire des municipalités du Québec, « Liste des municipalités (csv) »"),
    "mrc": ("MRC_CM_Arg.csv", False,
            "Répertoire des municipalités du Québec, « Liste des MRC_CM_Arg (csv) »"),
    "perimunicipaux": ("A01_CONVERT_XML_ORG_PER_MUN.xml", False,
                       "Répertoire des municipalités du Québec, « Liste des organismes périmunicipaux »"),
    "validite": ("validite_classe_2024.csv", False,
                 "Stratégie d'économie d'eau potable, « Validité des audits de l'eau 2024, par classe de population »"),
    "fuites": ("fuites_classe_2024.csv", False,
               "Stratégie d'économie d'eau potable, « Indice de fuites (IFI) 2024, par classe de population »"),
    "consommation": ("consommation_classe_2024.csv", False,
                     "Stratégie d'économie d'eau potable, « Consommation résidentielle 2024, par classe de population »"),
}

A_COMPLETER = "À compléter"


# ---------------------------------------------------------------------------
# Lecture des fichiers de référence
# ---------------------------------------------------------------------------

def lire_fichiers():
    """Charge les fichiers présents et dit clairement lesquels manquent.

    Retourne le contenu de chaque fichier trouvé, et sa date. Attention, c'est
    la date de dernière modification sur le disque, donc en pratique le jour
    où le fichier a été téléchargé, pas la date de publication par le
    ministère. S'il manque un fichier obligatoire, retourne (None, None).
    """
    contenus, dates, absents = {}, {}, []

    for cle, (nom, obligatoire, description) in FICHIERS.items():
        chemin = DOSSIER_SOURCES / nom
        if not chemin.exists():
            absents.append((nom, obligatoire, description))
            continue
        contenus[cle] = chemin.read_bytes()
        dates[cle] = datetime.fromtimestamp(chemin.stat().st_mtime).date().isoformat()
        print(f"  {nom:36s} {chemin.stat().st_size:>9,} octets   fichier du {dates[cle]}")

    for nom, obligatoire, description in absents:
        marque = "MANQUANT" if obligatoire else "absent, facultatif"
        print(f"  {nom:36s} {marque}")
        print(f"      à prendre dans : {description}")

    if any(obligatoire for _, obligatoire, _ in absents):
        return None, None
    return contenus, dates


def lire_csv(contenu):
    """Lit un CSV reçu en octets. L'encodage « utf-8-sig » retire le BOM s'il y en a un."""
    return list(csv.DictReader(contenu.decode("utf-8-sig").splitlines()))


# ---------------------------------------------------------------------------
# Rapprochement des noms
# ---------------------------------------------------------------------------

# Désignations retirées au début des noms. Elles sont écrites sans accents,
# parce qu'on les compare à des noms déjà normalisés.
DESIGNATIONS = (r"(ville|municipalite regionale de comte|municipalite|mrc|paroisse"
                r"|cantons unis|canton|village|cite|corporation municipale"
                r"|communaute metropolitaine|comm metropolitaine)")


def normaliser(texte):
    """Minuscules, sans accents ni ponctuation : « Sainte-Anne » devient « sainte anne »."""
    texte = unicodedata.normalize("NFD", (texte or "").lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", texte)).strip()


# Le service que certains acheteurs ajoutent à leur nom. Ce n'est pas un lieu.
SERVICES = r"\b(approvisionnement|service des acquisitions)\b"


def cle_organisme(nom):
    """Réduit un nom à sa partie distinctive, pour comparer le SEAO au répertoire.

    Le SEAO n'a aucun code officiel de municipalité : on n'a que le nom. On
    retire donc la désignation (« Ville de », « Municipalité de »...) et les
    articles, pour que « Ville de Sept-Îles » et « Sept-Îles » donnent la même
    clé. On retire aussi le service que certains acheteurs ajoutent à leur
    nom, comme dans « Ville de Joliette - Approvisionnement ».
    """
    cle = normaliser(nom)
    cle = re.sub(SERVICES, "", cle)
    # Plusieurs passages, pour les noms qui empilent désignations et articles,
    # comme « Municipalité de la Paroisse de Saint-... ».
    for _ in range(3):
        cle = re.sub(rf"^{DESIGNATIONS}\b\s*", "", cle)
        cle = re.sub(r"^(de la|du|des|de|d|la|le|les)\b\s*", "", cle)
    return cle.strip()


def type_attendu(nom):
    """Déduit du début du nom SEAO si l'on cherche une municipalité ou une MRC.

    Une fois la désignation retirée, « MRC de Montmagny » et « Ville de
    Montmagny » donnent la même clé. Ce repère permet de choisir la bonne
    correspondance plutôt que de déclarer le cas ambigu. Retourne None si le
    nom ne commence par aucune désignation connue.
    """
    debut = normaliser(nom)
    # « Comm. métropolitaine » : c'est ainsi que le répertoire écrit celle de Montréal.
    if re.match(r"^(mrc|municipalite regionale de comte|communaute metropolitaine|comm metropolitaine)\b", debut):
        return "MRC ou communauté"
    if re.match(r"^(ville|municipalite|paroisse|canton|cantons unis|village|cite"
                r"|corporation municipale)\b", debut):
        return "municipalité"
    return None


def construire_index(municipalites, mrc, perimunicipaux):
    """Associe chaque clé de nom à la liste des organismes qui la portent.

    Une clé partagée reste volontairement ambiguë : il existe par exemple deux
    Saint-Donat au Québec. main() essaiera de départager (voir departager), et
    signalera le cas s'il n'y arrive pas. Je préfère un programme qui dit
    « je ne sais pas » à un programme qui devine.
    """
    index = {}

    for ligne in municipalites:
        index.setdefault(cle_organisme(ligne["munnom"]), []).append(("municipalité", ligne))

    for ligne in mrc:
        index.setdefault(cle_organisme(ligne["mrcnom"]), []).append(("MRC ou communauté", ligne))

    # Pour les organismes périmunicipaux, on ne garde que le nom et le code
    # postal : le fichier XML ne donne ni population ni superficie.
    for organisme in perimunicipaux:
        # Le ministère coupe les noms à 60 caractères, parfois au milieu d'un mot :
        # la suite est dans NOM_L2. C'est le cas de 132 organismes sur 338.
        nom = ((organisme.findtext("NOM_L1") or "") + (organisme.findtext("NOM_L2") or "")).strip()
        if nom:
            entrees = index.setdefault(cle_organisme(nom), [])
            # Le fichier du ministère liste certains organismes deux fois, comme la
            # Société de transport de l'Outaouais : un même nom ne compte qu'une fois.
            if not any(t == "organisme périmunicipal" and e["nom"] == nom for t, e in entrees):
                entrees.append(("organisme périmunicipal",
                                {"nom": nom, "code_postal": organisme.findtext("COD_POST") or ""}))

    return index


def construire_index_des_codes(municipalites, mrc):
    """Associe chaque code géographique à sa municipalité ou à sa MRC.

    Sert quand le code est déjà inscrit dans le contexte : rempli lors d'une
    exécution précédente, ou saisi à la main pour régler un cas que le nom ne
    permet pas de trancher. Les deux familles de codes ne se chevauchent pas :
    cinq chiffres pour une municipalité, « AR » suivi de trois chiffres pour
    une MRC.
    """
    codes = {}
    for ligne in municipalites:
        codes[(ligne.get("mcode") or "").strip('"').strip()] = ("municipalité", ligne)
    for ligne in mrc:
        codes[(ligne.get("mrccod") or "").strip()] = ("MRC ou communauté", ligne)
    codes.pop("", None)
    return codes


def sans_territoires_non_organises(correspondances):
    """Écarte les territoires non organisés quand un autre candidat porte le même nom.

    Un territoire non organisé n'a pas de conseil et ne passe pas de contrats :
    c'est la MRC qui l'administre. Quand une municipalité porte le même nom,
    comme Rivière-Saint-Jean, l'acheteur est donc la municipalité.
    """
    organises = [c for c in correspondances if c[1].get("mdes") != "Territoire non organisé"]
    return organises or correspondances


def decrire(correspondance):
    """Résume un candidat en une ligne, avec son code, pour la liste à vérifier."""
    type_organisme, ligne = correspondance
    if type_organisme == "municipalité":
        return f"{ligne.get('munnom')} ({ligne.get('mdes')}, code {ligne.get('mcode')}, {ligne.get('mrc') or ligne.get('regadm')})"
    if type_organisme == "MRC ou communauté":
        return f"MRC {ligne.get('mrcnom')} (code {ligne.get('mrccod')})"
    return f"{ligne.get('nom')} (organisme périmunicipal)"


# Désignations qui distinguent vraiment deux homonymes. « Municipalité » n'en fait
# pas partie : le SEAO l'emploie aussi pour des paroisses, comme Sainte-Françoise
# ou Saint-Isidore. On ne regarde que le début du nom (« Ville de… »,
# « Municipalité du Canton de… »), et un mot suivi d'un trait d'union ne compte
# pas : « Municipalité de Ville-Marie » ne désigne pas une ville.
DESIGNATION_DISTINCTIVE = re.compile(
    r"^(?:municipalite\s+(?:de\s+la\s+|du\s+|de\s+)?)?(canton|village|ville|paroisse)(?![-\w])")


def normaliser_code_postal(code):
    """« g0l 3b0 » devient « G0L3B0 », pour comparer des codes écrits différemment."""
    return re.sub(r"\s+", "", code or "").upper()


def designation_au_debut(nom):
    """Retourne Canton, Village, Ville ou Paroisse si le nom SEAO commence ainsi, sinon None."""
    # Minuscules et sans accents, mais en gardant les traits d'union (voir plus haut).
    sans_accents = "".join(c for c in unicodedata.normalize("NFD", (nom or "").lower())
                           if unicodedata.category(c) != "Mn")
    m = DESIGNATION_DISTINCTIVE.match(re.sub(r"\s+", " ", sans_accents).strip())
    return m.group(1).capitalize() if m else None


def departager(nom, correspondances, codes_postaux):
    """Choisit entre plusieurs municipalités homonymes, seulement si un indice les sépare.

    Deux indices, dans cet ordre :
      1. le code postal publié dans le SEAO, comparé à celui de l'hôtel de ville
         dans le répertoire (mcodpos);
      2. une désignation distinctive écrite au début du nom SEAO (voir
         DESIGNATION_DISTINCTIVE), comparée à celle du répertoire (mdes).
    Si les deux indices se contredisent, ou si aucun ne sépare les candidats, on
    ne choisit pas. Retourne (correspondance, explication), ou (None, None).
    """
    if any(type_organisme != "municipalité" for type_organisme, _ in correspondances):
        return None, None
    designation = designation_au_debut(nom)

    par_code = [c for c in correspondances if normaliser_code_postal(c[1].get("mcodpos")) in codes_postaux]
    if len(par_code) == 1:
        trouve = par_code[0]
        if designation and trouve[1].get("mdes") != designation:
            return None, None
        return trouve, f"code postal {normaliser_code_postal(trouve[1].get('mcodpos'))}"
    if designation:
        par_designation = [c for c in correspondances if c[1].get("mdes") == designation]
        if len(par_designation) == 1:
            return par_designation[0], f"désignation « {designation} »"
    return None, None


def lire_codes_postaux_seao(dossier=DOSSIER_SORTIES):
    """Retourne {identifiant d'acheteur : codes postaux publiés dans le SEAO}.

    Le fichier de contexte ne contient pas d'adresse : on la reprend dans les
    vues produites par analyser_seao.py, pour toutes les périodes analysées.
    """
    codes = {}
    for chemin in sorted(Path(dossier).glob("*enrichir*.csv")):
        with chemin.open(encoding="utf-8-sig", newline="") as fichier:
            for ligne in csv.DictReader(fichier):
                for identifiant in (ligne.get("buyer_ids") or "").split("|"):
                    for code in (ligne.get("code_postal_seao") or "").split("|"):
                        if identifiant.strip() and code.strip():
                            codes.setdefault(identifiant.strip(), set()).add(normaliser_code_postal(code))
    return codes


# ---------------------------------------------------------------------------
# Rapprochement tolérant
# ---------------------------------------------------------------------------
# Ces règles ne servent que lorsque le nom exact n'a rien trouvé : elles ne
# peuvent donc pas défaire un rattachement existant. Elles rattrapent les
# écarts d'écriture du SEAO, sans deviner.

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
    """Nombre de fautes acceptées dans un mot, selon la longueur du plus court des deux.

    Une faute, c'est une lettre en trop, en moins ou remplacée, ou deux lettres
    voisines inversées : « batiment » et « batimnet » sont à une faute l'un de
    l'autre. Plus un mot est court, plus une faute risque d'en faire un autre
    mot : Saint-Paul et Sainte-Paule sont deux municipalités. On n'accepte donc
    aucune faute jusqu'à 4 lettres, une de 5 à 8 lettres, deux à partir de 9.
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

    # « M. » ou « Mun. » en tête veut dire Municipalité. Une faute dans ce mot,
    # comme « Muncipalité », ne doit pas non plus empêcher de le reconnaître.
    # Les autres désignations sont trop courtes pour y tolérer une faute :
    # « Mille », dans Mille-Isles, n'est qu'à une lettre de « Ville ».
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
    """Regroupe l'index sous des clés tolérantes : abréviations développées, déterminants retirés.

    « Saint-Léon-de-Standon » y devient « saint leon standon ». Dans le
    répertoire actuel, cela ne réunit que deux noms différents, Ange-Gardien et
    L'Ange-Gardien, que la région permet ensuite de séparer.
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
    """Dit si un nom ne diffère du nom officiel que par des fautes de frappe tolérées.

    Les deux noms doivent avoir le même nombre de mots. Chaque mot est comparé
    au mot officiel de même rang, avec la tolérance de sa longueur, et le nom
    entier ne peut pas compter plus de deux fautes.
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

    Quatre règles, essayées dans l'ordre, de la plus sûre à la plus risquée :
      1. le même nom écrit autrement : abréviation, déterminant oublié,
         désignation mal placée, précision entre parenthèses;
      2. le nom officiel suivi d'une précision : « Saint-Damase-de-Matapédia »
         pour Saint-Damase, dans la MRC de La Matapédia;
      3. le nom officiel raccourci : « Saint-Majorique » pour
         Saint-Majorique-de-Grantham;
      4. un nom approché : une faute de frappe ou deux lettres inversées, selon
         la longueur du mot (voir tolerance).

    Les indices servent ensuite à choisir et à confirmer : la désignation, une
    précision de lieu comparée à la région et à la MRC du candidat, et le code
    postal. Un candidat n'est retenu que s'il est seul et qu'aucun indice ne le
    contredit. Pour les règles 2 à 4, il faut en plus qu'un indice le confirme :
    sur 36 907 fautes introduites exprès dans les noms du répertoire, cette
    confirmation n'a laissé passer aucune mauvaise municipalité.

    Retourne (correspondance, explication, candidats). La correspondance est
    None quand rien n'est retenu; les candidats restent alors utiles pour la
    vérification à la main.
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
    """Trouve l'organisme du répertoire qui correspond à une ligne du contexte.

    Trois essais, dans l'ordre : le code géographique déjà inscrit dans la
    ligne, le nom exact, puis les règles tolérantes (voir rapprocher).

    Retourne (correspondance, méthode, échec). En cas de succès, la méthode est
    le texte à noter dans la source, ou None quand le nom exact a suffi. Sinon,
    échec vaut (genre, raison) : « ambigu » quand il y a des candidats mais
    qu'on ne peut pas choisir, « absent » quand une municipalité ou une MRC
    reste introuvable, « non municipal » quand le nom n'annonce ni l'une ni
    l'autre et que le répertoire ne le connaît pas.
    """
    nom = ligne["organisme"]
    codes_ligne = set().union(*[codes_postaux.get(i.strip(), set())
                                for i in (ligne.get("buyer_ids") or "").split("|")])

    # 1. Un code déjà inscrit fait foi : il vient d'une exécution précédente, ou
    # d'une saisie à la main pour un cas que le nom ne permettait pas de trancher.
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
            # Ni « Municipalité », ni « Ville », ni « MRC » : un office d'habitation, une
            # société, une association... Le répertoire n'a rien à reporter pour lui.
            return None, None, ("non municipal", "absent du répertoire, et le nom n'annonce ni municipalité ni MRC")
        return None, None, ("absent", "aucun organisme du répertoire ne porte ce nom")

    # « MRC de Montmagny » et « Ville de Montmagny » ont la même clé : le
    # début du nom dit laquelle on cherche. Si aucun organisme de ce type ne
    # porte ce nom, on ne rattache pas : la Communauté métropolitaine de
    # Montréal avait ainsi reçu, à tort, la population de la Ville de Montréal.
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


# ---------------------------------------------------------------------------
# Construction des valeurs de contexte
# ---------------------------------------------------------------------------

def valeurs_municipalite(ligne, eau, source):
    """Prépare les valeurs de contexte d'une municipalité du répertoire.

    Deux précisions pour bien lire le résultat :
      - la superficie retenue est la superficie totale (msuperf), plans d'eau
        compris. Le répertoire donne aussi la superficie terrestre (msupft),
        qui n'est pas utilisée ici;
      - classe_taille vient de la Stratégie d'économie d'eau potable : c'est la
        classe de la population desservie par le réseau, pas celle de la
        municipalité. Mont-Tremblant compte 12 026 habitants, mais elle est
        classée « 5 000 à 9 999 personnes » parce que son réseau en dessert
        8 151. Quand la Stratégie n'a pas de classe, elle inscrit « Aucune
        donnée ».
    """
    code = (ligne.get("mcode") or "").strip('"').strip()
    donnees_eau = eau.get(code, {})

    # Les données sur l'eau tiennent dans une seule colonne de texte, facile à
    # lire. Une valeur vide ou « NULL » est simplement omise.
    morceaux = []
    for etiquette, champ, unite in (("population desservie", "pop_desservie", ""),
                                    ("indice de fuites", "indice_fuites", ""),
                                    ("validité des audits", "validite", " %"),
                                    ("consommation résidentielle", "consommation", " L/personne/jour")):
        valeur = donnees_eau.get(champ)
        if valeur not in (None, "", "NULL"):
            morceaux.append(f"{etiquette} {valeur}{unite}")

    return {
        "code_geographique": code,
        "population": ligne.get("mpopul", ""),
        "classe_taille": donnees_eau.get("classe", ""),
        "superficie_km2": ligne.get("msuperf", ""),
        "region_administrative": ligne.get("regadm", ""),
        "mrc": ligne.get("mrc", ""),
        "particularites_infrastructures": "; ".join(morceaux),
        "source_contexte": source,
    }


def valeurs_mrc(ligne, source):
    """Prépare les valeurs de contexte d'une MRC ou d'une communauté métropolitaine.

    Le fichier des MRC a ses propres noms de colonnes (mrcpopul, mrcregion,
    msupf), différents de ceux du fichier des municipalités. Il ne contient
    rien sur l'eau.
    """
    return {
        "code_geographique": (ligne.get("mrccod") or "").strip(),
        "population": ligne.get("mrcpopul", ""),
        "superficie_km2": ligne.get("msupf", ""),
        "region_administrative": ligne.get("mrcregion", ""),
        "source_contexte": source,
    }


def remplir_ligne(ligne, valeurs):
    """Reporte les valeurs trouvées dans les seules cases vides ou encore « À compléter ».

    C'est la règle la plus importante du programme : une valeur déjà présente,
    saisie à la main ou lors d'une exécution précédente, n'est jamais remplacée,
    même si le répertoire donne autre chose. Une valeur vide n'est pas reportée.
    Retourne (cases remplies, valeurs déjà présentes laissées intactes).
    """
    remplies, intactes = 0, 0
    for colonne, valeur in valeurs.items():
        if not valeur:
            continue
        actuelle = (ligne.get(colonne) or "").strip()
        if actuelle and actuelle != A_COMPLETER:
            intactes += 1
            continue
        ligne[colonne] = valeur
        remplies += 1
    return remplies, intactes


def construire_donnees_eau(fuites, validite, consommation):
    """Regroupe les trois fichiers de la Stratégie par code géographique.

    Le fichier des fuites nomme sa colonne de code num_c, les deux autres
    mun_c : c'est la même information. L'indice de fuites est coupé à cinq
    caractères (0.56544245 devient 0.565) : c'est une troncature, pas un
    arrondi.

    Attention aux codes : dans les fichiers de validité et de consommation, le
    zéro du début a disparu pour 89 municipalités (« 3005 » pour Gaspé, au lieu
    de « 03005 »). On complète donc chaque code à cinq chiffres; sans cela, 28
    organismes de l'est du Québec n'avaient que leur indice de fuites.
    """
    eau = {}
    for ligne in validite:
        eau.setdefault(ligne["mun_c"].zfill(5), {}).update(
            classe=ligne.get("cl_pop_desservie", ""),
            pop_desservie=ligne.get("pop_desservie", ""),
            validite=ligne.get("pourc_indice_validite", ""),
        )
    for ligne in fuites:
        eau.setdefault(ligne["num_c"].zfill(5), {}).update(indice_fuites=ligne.get("indice_fuites_ifi", "")[:5])
    for ligne in consommation:
        eau.setdefault(ligne["mun_c"].zfill(5), {}).update(consommation=ligne.get("consom_resid", ""))
    return eau


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main():
    """Remplit les cases « À compléter » du contexte, puis liste les cas à traiter à la main."""
    if not CONTEXTE_CSV.exists():
        print(f"Erreur : {CONTEXTE_CSV} introuvable. Lancer d'abord analyser_seao.py.")
        return

    print(f"Lecture des fichiers de référence dans {DOSSIER_SOURCES} :")
    contenus, dates = lire_fichiers()
    if contenus is None:
        print("\nIl manque un fichier obligatoire. Rien n'a été modifié.")
        return

    municipalites = lire_csv(contenus["municipalites"])
    mrc = lire_csv(contenus["mrc"]) if "mrc" in contenus else []
    perimunicipaux = list(ET.fromstring(contenus["perimunicipaux"])) if "perimunicipaux" in contenus else []
    eau = construire_donnees_eau(
        lire_csv(contenus["fuites"]) if "fuites" in contenus else [],
        lire_csv(contenus["validite"]) if "validite" in contenus else [],
        lire_csv(contenus["consommation"]) if "consommation" in contenus else [],
    )
    index = construire_index(municipalites, mrc, perimunicipaux)
    index_tolerant = construire_index_tolerant(index)
    par_code = construire_index_des_codes(municipalites, mrc)
    codes_postaux = lire_codes_postaux_seao()
    print(f"  codes postaux SEAO lus pour {len(codes_postaux)} identifiants d'acheteur")

    # Mention de provenance écrite dans chaque case remplie : quels fichiers,
    # de quelle date, et quel jour le contexte a été complété.
    source = (f"Répertoire des municipalités du Québec (MAMH), fichier du {dates['municipalites']}"
              + (f"; Stratégie québécoise d'économie d'eau potable 2024 (MAMH), fichier du {dates['validite']}"
                 if "validite" in dates else "")
              + f"; contexte rempli le {date.today().isoformat()}")

    with CONTEXTE_CSV.open(encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        colonnes = lecteur.fieldnames
        lignes = list(lecteur)

    # remplis et rapproches comptent des organismes; deja_saisis compte des cases (voir remplir_ligne).
    # ambigus et absents : les cas qu'il faut encore trancher à la main. sans_objet : les
    # organismes non municipaux, pour lesquels le répertoire n'a rien à reporter.
    remplis, rapproches, deja_saisis, ambigus, absents, sans_objet = 0, 0, 0, [], [], []

    for ligne in lignes:
        correspondance, methode, echec = rattacher(ligne, index, index_tolerant, par_code, codes_postaux)
        if echec:
            genre, raison = echec
            {"ambigu": ambigus, "absent": absents, "non municipal": sans_objet}[genre].append(
                (ligne["organisme"], raison))
            continue

        # Quand le nom exact n'a pas suffi, la source dit comment l'organisme a
        # été rattaché, pour qu'on puisse le vérifier.
        type_organisme, trouve = correspondance
        source_ligne = source + (f"; {methode}" if methode else "")
        if type_organisme == "municipalité":
            valeurs = valeurs_municipalite(trouve, eau, source_ligne)
        elif type_organisme == "MRC ou communauté":
            valeurs = valeurs_mrc(trouve, source_ligne)
        else:
            # Organisme reconnu, mais le répertoire n'a rien à reporter pour lui.
            sans_objet.append((ligne["organisme"],
                               "organisme périmunicipal : ni population ni superficie dans le répertoire"))
            continue

        remplies, intactes = remplir_ligne(ligne, valeurs)
        deja_saisis += intactes
        if remplies:
            remplis += 1
            if methode and methode.startswith("nom rapproché"):
                rapproches += 1

    # Sauvegarde avant d'écrire, pour pouvoir revenir en arrière. Attention : il
    # n'y en a qu'une, et elle est remplacée à chaque exécution.
    DOSSIER_SORTIES.mkdir(exist_ok=True)
    shutil.copy2(CONTEXTE_CSV, DOSSIER_SORTIES / (CONTEXTE_CSV.name + ".bak"))
    with CONTEXTE_CSV.open("w", encoding="utf-8-sig", newline="") as fichier:
        ecrivain = csv.DictWriter(fichier, fieldnames=colonnes)
        ecrivain.writeheader()
        ecrivain.writerows(lignes)

    with open(A_VERIFIER_CSV, "w", encoding="utf-8-sig", newline="") as fichier:
        ecrivain = csv.writer(fichier)
        # Les cas à trancher d'abord, puis ceux pour lesquels il n'y a rien à faire.
        ecrivain.writerow(["organisme", "raison", "a_traiter"])
        ecrivain.writerows(cas + ("oui",) for cas in sorted(ambigus + absents))
        ecrivain.writerows(cas + ("non",) for cas in sorted(sans_objet))

    print(f"\nOrganismes dans le contexte         : {len(lignes)}")
    print(f"Organismes enrichis                 : {remplis}")
    print(f"  dont par une règle tolérante      : {rapproches}")
    print(f"Valeurs déjà présentes, intactes : {deja_saisis}")
    print(f"À trancher à la main                : {len(ambigus) + len(absents)}")
    print(f"  candidats trouvés, non retenus    : {len(ambigus)}")
    print(f"  municipalité ou MRC introuvable   : {len(absents)}")
    print(f"Organismes non municipaux           : {len(sans_objet)}  (rien à compléter)")
    print(f"\n{CONTEXTE_CSV} mis à jour (sauvegarde dans {DOSSIER_SORTIES / (CONTEXTE_CSV.name + '.bak')})")
    print(f"{A_VERIFIER_CSV} liste les cas à traiter à la main.")
    print("La proximité d'un cours d'eau et le type de milieu restent à documenter :")
    print("aucun de ces fichiers ne fournit ces informations.")


if __name__ == "__main__":
    main()
