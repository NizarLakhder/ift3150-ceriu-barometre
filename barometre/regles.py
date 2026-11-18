"""Les règles de repérage : type d'organisme, nature de la transaction, lien avec l'eau, PGA-Eau et
gestion des actifs en eau. Elles ne lisent qu'un nom, un titre, une description ou des codes."""

import re
import unicodedata

from utilitaires import clean_org_name


# Codes UNSPSC des subventions. Trop large : 9315 attrape aussi le mandat
# d'auditeur externe de Bois-des-Filion.
UNSPSC_SUBVENTION = ("9315", "84101501", "99000000")


# Mots liés à l'eau, en plus du mot « eau » que is_water_related cherche à part.
# Ils servent surtout aux titres sans ce mot, comme « aqueduc » ou « égout ».
MOTS_CLES_EAU = [
    "pga-eau", "pga eau", "pga_eau",
    "aqueduc", "égout", "egout", "eau potable", "eaux usées", "eaux usees",
    "eaux pluviales", "pluvial", "assainissement", "usine de filtration",
    "station d'épuration", "réseau d'eau", "borne d'incendie", "bornes d'incendie",
    "borne-fontaine", "bornes-fontaines", "surpression", "pompage",
    "compteur d'eau", "compteurs d'eau", "puits",
]


# ---------------------------------------------------------------------------
# Le type d'organisme
# ---------------------------------------------------------------------------

def org_type(name):
    """Devine le type d'organisme d'après son nom, faute de référentiel ici.

    « MRC » est testé avant « Municipalité », qui figure dans « municipalité
    régionale de comté ». Un nom sans mot repère, comme « Saint-Pie-de-Guire »,
    donne « Autre organisme municipal ».
    """
    n = clean_org_name(name).lower()
    rules = [
        ("Ville", r"^(ville|cité) d"),
        ("MRC", r"^mrc\b|municipalité régionale de comté"),
        ("Municipalité", r"^(la )?municipalité\b|^corporation municipale|^m\. |paroisse|canton|village"),
        ("Régie intermunicipale", r"^régie"),
        ("Société de transport", r"transport"),
        ("Office d'habitation", r"habitation|\bomh\b"),
    ]
    for label, pattern in rules:
        if re.search(pattern, n):
            return label
    return "Autre organisme municipal"


def get_nature(type_contrat, unspsc_id, titre):
    """Classe la fiche : achat, subvention ou contribution, vente d'immeuble ou partenariat.

    Les subventions sont retirées des totaux d'achats, mais leur règle (quelques
    codes UNSPSC, « subvention » ou « contribution financière » dans le titre)
    reste grossière : à valider. Tout le reste est un achat.
    """
    if type_contrat == "Ventes de biens immeubles":
        return "vente d'immeuble"
    if type_contrat == "Partenariat":
        return "partenariat"
    t = titre.lower()
    if unspsc_id.startswith(UNSPSC_SUBVENTION) or "contribution financi" in t or "subvention" in t:
        return "subvention ou contribution"
    return "achat"


def is_water_related(titre, libelles):
    """Vrai si la fiche parle d'eau : un filet large, pas un repérage du PGA-Eau.

    Réagit au mot entier « eau » ou « eaux » (pas à « réseau ») et aux mots de
    MOTS_CLES_EAU, dans le titre ou les classifications. Une classification comme
    « Camion-citerne à eau pour la lutte contre les incendies » suffit.
    """
    # Apostrophe courbe changée en droite, comme dans MOTS_CLES_EAU.
    text = f"{titre} {libelles}".lower().replace("’", "'")
    if re.search(r"\beaux?\b", text):
        return True
    return any(k in text for k in MOTS_CLES_EAU)


def is_pga_eau(titre):
    """Vrai si le titre annonce un plan de gestion des actifs en eau (PGA-Eau).

    Deux formes :
      1. « PGA » puis « eau », quelle que soit la ponctuation : « PGA-EAU », ou
         « PGA – Eau » avec un tiret long, comme à Windsor;
      2. « gestion », « actif » et « eau » dans le même titre, sans l'acronyme,
         comme à Mont-Tremblant.
    « PGA » et « eau » doivent être des mots entiers : « ACCOMPGANEMENT » ne
    compte pas, ni un « plan de gestion des eaux pluviales », faute d'« actif ».
    """
    t = titre.lower().replace("’", "'")
    if re.search(r"\bpga[\W_]*eaux?\b", t):
        return True
    return "gestion" in t and "actif" in t and re.search(r"\beaux?\b", t) is not None


def texte_de_recherche(texte):
    """Le texte en minuscules, sans accents, avec des apostrophes droites : « Égout » devient « egout »."""
    texte = (texte or "").replace("’", "'").replace("ʼ", "'")
    return unicodedata.normalize("NFD", texte).encode("ascii", "ignore").decode().lower()


# Le repérage large de la gestion des actifs en eau. Les mots sont écrits sans accents.
GESTION_ACTIFS = r"gestion (des|d'|de l')\s*actifs?"
MOTS_RESEAUX_EAU = r"aqueduc|egout|eaux? potable|eaux? usee|conduite|pluvial|hydrauli|sanitaire|assainissement|tecq|\beaux?\b"
# Les autres actifs attendront leur propre repérage : bâtiments, routes, véhicules...
MOTS_AUTRES_ACTIFS = r"batiment|immeuble|immobili|vehicule|flotte|tennis|mobilier|transport"
MOTS_ROUTES = r"routier|piirl|pisrmm|pavl|securite routiere"


def gestion_actifs_eau(titre, description=""):
    """Retourne la famille de gestion des actifs en eau d'une fiche, ou une chaîne vide.

    Plus large que is_pga_eau : il propose aussi les démarches voisines, classées
    ensuite à la main dans demarches.csv. Les tests, dans l'ordre :
      - « PGA-Eau » : is_pga_eau sur le titre, ou l'acronyme dans la description;
      - un titre sur un autre actif (bâtiment, véhicule, transport...) est écarté;
      - « outil » : un logiciel, une licence ou une solution de gestion d'actifs;
      - « étape » : une inspection, une auscultation, un portrait ou un inventaire
        fait « dans le cadre » d'un PGA, d'un plan d'intervention ou de gestion;
      - « plan d'intervention » : sur les réseaux d'eau, pas un plan routier (PIIRL);
      - « gestion d'actifs » : un plan de gestion des actifs des infrastructures
        qui ne dit pas « eau », comme celui de Clermont.
    """
    t = texte_de_recherche(titre)
    texte = texte_de_recherche(f"{titre} {description}")
    if is_pga_eau(titre) or re.search(r"\bpga[\W_]*eaux?\b", texte):
        return "PGA-Eau"
    if re.search(MOTS_AUTRES_ACTIFS, t):
        return ""
    if re.search(GESTION_ACTIFS, t) and re.search(r"logiciel|licence|abonnement|solution|plateforme|progiciel", t):
        return "outil"
    if (re.search(r"inspection|auscultation|portrait|inventaire", t)
            and re.search(r"dans le cadre (du|de la|des|d'un|d'une)\b.*(\bpga\b|plans? d'intervention|plans? de gestion|"
                          + GESTION_ACTIFS + ")", texte)):
        return "étape"
    if re.search(r"plans? d'intervention", t) and re.search(MOTS_RESEAUX_EAU, texte) and not re.search(MOTS_ROUTES, t):
        return "plan d'intervention"
    if re.search(GESTION_ACTIFS, t) and re.search(r"infrastructure|ingenierie|\bpti\b|municipa|reseau", t):
        return "gestion d'actifs"
    return ""
