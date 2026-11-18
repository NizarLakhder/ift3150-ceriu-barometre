"""Les valeurs de contexte tirées du répertoire et de la Stratégie, reportées dans les seules cases libres."""

from barometre.contexte.fichier import A_COMPLETER, AUCUNE_DONNEE, HORS_MRC, SANS_OBJET


def valeurs_municipalite(ligne, eau, source):
    """Les valeurs de contexte d'une municipalité du répertoire.

    La superficie est la superficie totale (msuperf), plans d'eau compris.
    classe_taille est la classe de la population desservie par le réseau :
    Mont-Tremblant (12 026 habitants) est classée « 5 000 à 9 999 personnes »,
    car son réseau en dessert 8 151.
    """
    code = (ligne.get("mcode") or "").strip('"').strip()
    donnees_eau = eau.get(code, {})

    # Les données sur l'eau, en une colonne de texte; une valeur vide ou « NULL » est omise.
    morceaux = []
    for etiquette, champ, unite in (("population desservie", "pop_desservie", ""),
                                    ("indice de fuites", "indice_fuites", ""),
                                    ("validité des audits", "validite", " %"),
                                    ("consommation résidentielle", "consommation", " L/personne/jour")):
        valeur = donnees_eau.get(champ)
        if valeur not in (None, "", "NULL"):
            morceaux.append(f"{etiquette} {valeur}{unite}")

    # Des valeurs publiées; la municipalité publiée sans valeur; ou absente des
    # fichiers, et la case reste à compléter.
    if morceaux:
        eau_texte = "; ".join(morceaux)
    elif code in eau:
        eau_texte = AUCUNE_DONNEE
    else:
        eau_texte = ""

    return {
        "code_geographique": code,
        "population": ligne.get("mpopul", ""),
        "classe_taille": donnees_eau.get("classe", ""),
        "superficie_km2": ligne.get("msuperf", ""),
        "region_administrative": ligne.get("regadm", ""),
        # Case vide dans le répertoire : Montréal, Laval ou Longueuil ne font partie d'aucune MRC.
        "mrc": ligne.get("mrc") or HORS_MRC,
        "particularites_infrastructures": eau_texte,
        "source_contexte": source,
    }


def valeurs_mrc(ligne, source):
    """Les valeurs de contexte d'une MRC ou d'une communauté métropolitaine.

    La MRC, la classe de taille et les données sur l'eau ne s'appliquent pas à une
    MRC : « Sans objet ». Une communauté métropolitaine n'a pas de région dans le
    répertoire : « Sans objet » aussi.
    """
    return {
        "code_geographique": (ligne.get("mrccod") or "").strip(),
        "population": ligne.get("mrcpopul", ""),
        "superficie_km2": ligne.get("msupf", ""),
        "region_administrative": (ligne.get("mrcregion") or "").strip() or SANS_OBJET,
        "mrc": SANS_OBJET,
        "classe_taille": SANS_OBJET,
        "particularites_infrastructures": SANS_OBJET,
        "source_contexte": source,
    }


def remplir_ligne(ligne, valeurs):
    """Reporte les valeurs dans les seules cases vides ou « À compléter ».

    Une valeur déjà présente n'est jamais remplacée, même si le répertoire dit
    autre chose. Retourne (cases remplies, valeurs laissées intactes).
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


def vider_note(ligne):
    """Vide une note restée « À compléter » et retourne True; une note écrite n'est pas touchée.

    Une note vide veut seulement dire qu'il n'y a rien à signaler.
    """
    if (ligne.get("notes") or "").strip() == A_COMPLETER:
        ligne["notes"] = ""
        return True
    return False


def construire_donnees_eau(fuites, validite, consommation):
    """Regroupe les trois fichiers de la Stratégie par code géographique.

    Le code s'appelle num_c dans le fichier des fuites, mun_c ailleurs. Il est
    complété à cinq chiffres : la validité et la consommation écrivent « 3005 »
    pour Gaspé. L'indice de fuites est tronqué à cinq caractères (0.565).
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
