"""Les organismes de contexte_municipalites.csv et leurs identifiants d'acheteur (« OP-… »)."""

from barometre.chemins import CONTEXT_SOURCE_CSV
from barometre.contexte.fichier import COLONNES_CONTEXTE, lire_contexte
from barometre.modele.conversions import texte
from barometre.modele.organismes import Acheteur, Organisme, type_organisme


def charger_organismes(connexion):
    """Charge les organismes du contexte et leurs identifiants d'acheteur.

    Le fichier fait foi : il met à jour les organismes déjà en base. « À compléter » devient NULL.
    """
    _, contexte = lire_contexte(CONTEXT_SOURCE_CSV, COLONNES_CONTEXTE)
    # Les codes du répertoire, déjà chargés par charger_territoire : ils décident du type de chaque organisme.
    municipalites = {c for (c,) in connexion.execute("SELECT code_geographique FROM territoire.municipalite")}
    mrc = {c for (c,) in connexion.execute("SELECT code FROM territoire.mrc")}

    organismes = []
    for ligne in contexte:
        code = texte(ligne["code_geographique"])
        try:
            sorte = type_organisme(code, municipalites, mrc)
        except ValueError as erreur:
            raise ValueError(f"contexte_municipalites.csv, « {ligne['organisme']} » : {erreur}") from None
        # Une municipalité garde son code géographique ; une MRC ou une communauté, son code de MRC.
        organismes.append(Organisme(
            nom=ligne["organisme"], type=sorte,
            code_geographique=code if sorte == "municipalite" else None,
            mrc_code=code if sorte == "mrc_ou_communaute" else None,
            type_milieu=texte(ligne["type_milieu"]), source_contexte=texte(ligne["source_contexte"]),
            notes=texte(ligne["notes"]),
        ))
    Organisme.inserer(connexion, organismes)

    # Les numéros que la base vient de donner, pour rattacher chaque identifiant d'acheteur à son organisme.
    # Une ligne du contexte peut en avoir plusieurs, séparés par « | » : Montréal en a des dizaines.
    ids = dict(connexion.execute("SELECT nom, organisme_id FROM organismes.organisme").fetchall())
    acheteurs = [Acheteur(acheteur_id=i.strip(), organisme_id=ids[ligne["organisme"]], nom_seao=None)
                 for ligne in contexte for i in ligne["buyer_ids"].split("|") if i.strip()]
    # Le contexte ne décide que de l'organisme : le nom publié (nom_seao) vient des exports.
    Acheteur.inserer(connexion, acheteurs, mises_a_jour=("organisme_id",))
    return len(contexte), len(acheteurs)


def organisme_de(identifiant, nom, connus, organismes):
    """Trouve l'organisme d'un identifiant d'acheteur publié dans une fiche.

    connus relie les identifiants en base à leur organisme, organismes les noms du
    contexte au leur. Un identifiant connu fait foi, même si le nom change
    d'écriture (« D'Amherst » devient « d'Amherst » en septembre). Un identifiant
    inconnu est rattaché par le nom : le contexte n'a pas tous ceux de Montréal.
    Lève ValueError si le nom est absent du contexte ou désigne un autre organisme.
    """
    par_nom = organismes.get(nom)
    if identifiant in connus:
        if par_nom is not None and par_nom != connus[identifiant]:
            raise ValueError(f"L'identifiant {identifiant} est rattaché à un autre organisme que « {nom} ».")
        return connus[identifiant]
    if par_nom is None:
        raise ValueError(f"{nom} ({identifiant}) n'est pas dans contexte_municipalites.csv : "
                         "lancer d'abord analyser_seao.py sur cet export.")
    return par_nom
