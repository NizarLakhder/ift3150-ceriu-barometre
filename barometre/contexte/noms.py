"""Les noms d'organismes : leur forme normalisée, les index du répertoire, et le choix entre homonymes."""

import re
import unicodedata

# Désignations retirées au début des noms, sans accents comme les noms normalisés.
DESIGNATIONS = (r"(ville|municipalite regionale de comte|municipalite|mrc|paroisse"
                r"|cantons unis|canton|village|cite|corporation municipale"
                r"|communaute metropolitaine|comm metropolitaine)")


def normaliser(texte):
    """Minuscules, sans accents ni ponctuation : « Sainte-Anne » devient « sainte anne »."""
    texte = unicodedata.normalize("NFD", (texte or "").lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", texte)).strip()


# Service ajouté au nom par certains acheteurs, comme « Ville de Joliette - Approvisionnement ».
SERVICES = r"\b(approvisionnement|service des acquisitions)\b"


def cle_organisme(nom):
    """Réduit un nom à sa partie distinctive, pour le comparer au répertoire.

    « Ville de Sept-Îles » et « Sept-Îles » donnent « sept iles » : désignation,
    articles du début et service ajouté par l'acheteur sont retirés.
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
    """« municipalité », « MRC ou communauté » ou None, d'après le début du nom SEAO.

    Sépare « MRC de Montmagny » de « Ville de Montmagny », qui ont la même clé.
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

    Une clé partagée, comme celle des deux Saint-Donat, reste ambiguë : departager
    tranche ensuite, ou le cas est signalé.
    """
    index = {}

    for ligne in municipalites:
        index.setdefault(cle_organisme(ligne["munnom"]), []).append(("municipalité", ligne))

    for ligne in mrc:
        index.setdefault(cle_organisme(ligne["mrcnom"]), []).append(("MRC ou communauté", ligne))

    # Le fichier XML ne donne que le nom et le code postal des organismes périmunicipaux.
    for organisme in perimunicipaux:
        # Les noms sont coupés à 60 caractères, la suite dans NOM_L2 (132 organismes sur 338).
        nom = ((organisme.findtext("NOM_L1") or "") + (organisme.findtext("NOM_L2") or "")).strip()
        if nom:
            entrees = index.setdefault(cle_organisme(nom), [])
            # Certains organismes sont listés deux fois, comme la Société de transport de l'Outaouais.
            if not any(t == "organisme périmunicipal" and e["nom"] == nom for t, e in entrees):
                entrees.append(("organisme périmunicipal",
                                {"nom": nom, "code_postal": organisme.findtext("COD_POST") or ""}))

    return index


def construire_index_des_codes(municipalites, mrc):
    """Associe chaque code géographique ou code de MRC à son organisme du répertoire.

    Sert quand le code est déjà inscrit dans le contexte.
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

    Un territoire non organisé ne passe pas de contrats : c'est sa MRC qui l'administre.
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


# Désignations qui départagent deux homonymes, lues au début du nom. « Municipalité »
# n'en est pas une : le SEAO l'emploie aussi pour des paroisses, comme Sainte-Françoise.
# Un mot suivi d'un trait d'union ne compte pas : « Ville-Marie » n'est pas une ville.
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
    """Choisit entre des municipalités homonymes, seulement si un indice publié les sépare.

    Indices, dans l'ordre : le code postal du SEAO comparé à celui de l'hôtel de
    ville (mcodpos), puis la désignation au début du nom comparée à mdes.
    Retourne (correspondance, explication), ou (None, None) si les indices se
    contredisent ou ne séparent rien.
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
