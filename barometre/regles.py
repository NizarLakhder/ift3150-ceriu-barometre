"""Les règles de repérage : type d'organisme, nature de la transaction, lien avec l'eau, PGA-Eau et
gestion des actifs en eau. Elles ne lisent qu'un nom, un titre, une description ou des codes.

Les mots-clés et les motifs des trois règles liées à l'eau sont dans config/regles_reperage.toml, lu au
premier usage par regles(). Ce module garde la préparation du texte, l'ordre des tests et les
classements renvoyés. Le type d'organisme et la nature de la transaction restent écrits ici."""

import re
import unicodedata
from functools import cache

from barometre import configuration
from utilitaires import clean_org_name


# Codes UNSPSC des subventions. Trop large : 9315 attrape aussi le mandat
# d'auditeur externe de Bois-des-Filion.
UNSPSC_SUBVENTION = ("9315", "84101501", "99000000")


@cache
def regles():
    """Les règles de config/regles_reperage.toml, lues et validées au premier appel, puis gardées.

    Lève configuration.ConfigurationInvalide si le fichier manque ou n'est pas valide. Un test qui
    change de fichier vide ce cache avec regles.cache_clear().
    """
    return configuration.charger_regles()


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

    Réagit au mot entier « eau » ou « eaux » (pas à « réseau ») et aux mots-clés de
    [lie_eau], dans le titre ou les classifications. Une classification comme
    « Camion-citerne à eau pour la lutte contre les incendies » suffit.
    """
    lie_eau = regles()["lie_eau"]
    # Apostrophe courbe changée en droite, comme dans les mots-clés.
    text = f"{titre} {libelles}".lower().replace("’", "'")
    if re.search(lie_eau["mot_eau"], text):
        return True
    return any(k in text for k in lie_eau["mots_cles"])


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
    pga_eau = regles()["pga_eau"]
    t = titre.lower().replace("’", "'")
    if re.search(pga_eau["acronyme"], t):
        return True
    return all(mot in t for mot in pga_eau["mots_requis"]) and re.search(pga_eau["mot_eau"], t) is not None


def texte_de_recherche(texte):
    """Le texte en minuscules, sans accents, avec des apostrophes droites : « Égout » devient « egout »."""
    texte = (texte or "").replace("’", "'").replace("ʼ", "'")
    return unicodedata.normalize("NFD", texte).encode("ascii", "ignore").decode().lower()


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
    Les motifs sont ceux de [gestion_actifs_eau], plus l'acronyme de [pga_eau] ;
    l'ordre des tests, lui, est fixé ici.
    """
    gestion = regles()["gestion_actifs_eau"]
    t = texte_de_recherche(titre)
    texte = texte_de_recherche(f"{titre} {description}")
    if is_pga_eau(titre) or re.search(regles()["pga_eau"]["acronyme"], texte):
        return "PGA-Eau"
    if re.search(gestion["autres_actifs"], t):
        return ""
    if re.search(gestion["gestion_actifs"], t) and re.search(gestion["outil"], t):
        return "outil"
    if re.search(gestion["etape_actions"], t) and re.search(configuration.motif_etape(gestion), texte):
        return "étape"
    if (re.search(gestion["plan_intervention"], t) and re.search(gestion["reseaux_eau"], texte)
            and not re.search(gestion["routes"], t)):
        return "plan d'intervention"
    if re.search(gestion["gestion_actifs"], t) and re.search(gestion["infrastructures"], t):
        return "gestion d'actifs"
    return ""
