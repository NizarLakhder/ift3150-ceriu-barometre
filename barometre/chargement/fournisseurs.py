"""Les fournisseurs : les identifiants FO regroupés par NEQ, écrits en base, et les noms en double à vérifier."""

from barometre.modele.seao import Fournisseur, IdentifiantFournisseur


def completer(infos, lecture):
    """Complète les informations d'un fournisseur par une nouvelle lecture.

    La dernière valeur lue l'emporte, mais une valeur absente n'efface jamais une
    valeur connue, comme le NEQ d'un soumissionnaire absent des parties.
    """
    return {**infos, **{k: v for k, v in lecture.items() if v is not None or k not in infos}}


def regrouper_fournisseurs(lus, connus, par_neq):
    """Décide à quelle entreprise va chaque identifiant FO d'un export, sans toucher à la base.

    lus : les fournisseurs lus dans l'export, dans l'ordre. connus et par_neq
    relient les identifiants et les NEQ déjà en base à leur entreprise. Deux
    identifiants au même NEQ vont à la même entreprise.

    Retourne les entreprises à créer, les identifiants à rattacher à une
    entreprise en base, et les mises à jour par entreprise. Un identifiant connu
    qui porte le NEQ d'une autre entreprise lève ValueError : à regrouper à la main.
    """
    infos = {}
    for lecture in lus:
        identifiant = lecture["identifiant"]
        infos[identifiant] = completer(infos.get(identifiant, {}),
                                       {k: v for k, v in lecture.items() if k != "identifiant"})

    a_creer, rattaches, a_mettre_a_jour = {}, [], {}
    for identifiant, info in infos.items():
        neq = info["neq"]
        if identifiant in connus:
            entreprise = connus[identifiant]
            if neq is not None and par_neq.get(neq, entreprise) != entreprise:
                raise ValueError(f"{identifiant} porte le NEQ {neq}, qui est déjà celui d'une autre entreprise : "
                                 "à regrouper à la main.")
            a_mettre_a_jour[entreprise] = completer(a_mettre_a_jour.get(entreprise, {}), info)
        elif neq is not None and neq in par_neq:
            rattaches.append((identifiant, par_neq[neq]))
            a_mettre_a_jour[par_neq[neq]] = completer(a_mettre_a_jour.get(par_neq[neq], {}), info)
        else:
            groupe = a_creer.setdefault(("neq", neq) if neq is not None else ("identifiant", identifiant),
                                        {"infos": {}, "identifiants": []})
            groupe["infos"] = completer(groupe["infos"], info)
            groupe["identifiants"].append(identifiant)
    return list(a_creer.values()), rattaches, a_mettre_a_jour


def charger_fournisseurs(connexion, lus):
    """Range en base les fournisseurs lus dans un export, regroupés par regrouper_fournisseurs."""
    connus = dict(connexion.execute("SELECT identifiant, fournisseur_id FROM seao.identifiant_fournisseur").fetchall())
    par_neq = dict(connexion.execute("SELECT neq, fournisseur_id FROM seao.fournisseur WHERE neq IS NOT NULL").fetchall())
    a_creer, rattaches, a_mettre_a_jour = regrouper_fournisseurs(lus, connus, par_neq)
    colonnes = ("nom", "neq", "adresse", "localite", "region", "code_postal", "pays")
    # La base attribue les numéros : on les lit dans l'ordre des entreprises envoyées.
    numeros = Fournisseur.inserer_et_numeroter(connexion, [Fournisseur(**{c: g["infos"][c] for c in colonnes})
                                                           for g in a_creer])
    rattaches += [(i, numero) for g, numero in zip(a_creer, numeros) for i in g["identifiants"]]
    IdentifiantFournisseur.inserer(connexion, [IdentifiantFournisseur(identifiant=i, fournisseur_id=f) for i, f in rattaches])
    if a_mettre_a_jour:
        with connexion.cursor() as curseur:
            curseur.executemany(
                "UPDATE seao.fournisseur SET nom = %(nom)s, "
                + ", ".join(f"{c} = coalesce(%({c})s, {c})" for c in colonnes if c != "nom")
                + " WHERE fournisseur_id = %(fournisseur_id)s",
                [{**{c: infos[c] for c in colonnes}, "fournisseur_id": f} for f, infos in a_mettre_a_jour.items()])


def fournisseurs_a_regrouper(connexion):
    """Les entreprises du même nom dont une seule a un NEQ : sans doute la même, à vérifier à la main.

    Deux NEQ différents désignent bien deux entreprises : elles ne sont pas proposées.
    """
    colonnes = ("groupe", "fournisseur_id", "identifiants", "nom", "neq", "adresse", "localite", "code_postal",
                "nb_dossiers_retenu", "nb_dossiers_soumissionnaire")
    return [dict(zip(colonnes, ligne)) for ligne in connexion.execute("""
        WITH entreprise AS (
            SELECT f.fournisseur_id, lower(f.nom) AS cle, f.nom, f.neq, f.adresse, f.localite, f.code_postal,
                   string_agg(i.identifiant, ' | ' ORDER BY i.identifiant) AS identifiants
            FROM seao.fournisseur f
            JOIN seao.identifiant_fournisseur i ON i.fournisseur_id = f.fournisseur_id
            GROUP BY f.fournisseur_id),
        groupe AS (
            SELECT cle, dense_rank() OVER (ORDER BY cle) AS numero
            FROM entreprise GROUP BY cle HAVING count(*) > 1 AND count(neq) = 1)
        SELECT g.numero, e.fournisseur_id, e.identifiants, e.nom, e.neq, e.adresse, e.localite, e.code_postal,
               (SELECT count(DISTINCT f.dossier_id) FROM seao.attribution a
                    JOIN seao.fiche f ON f.fiche_id = a.fiche_id
                    JOIN seao.identifiant_fournisseur i ON i.identifiant = a.identifiant_fournisseur
                    WHERE i.fournisseur_id = e.fournisseur_id),
               (SELECT count(DISTINCT f.dossier_id) FROM seao.soumissionnaire s
                    JOIN seao.fiche f ON f.fiche_id = s.fiche_id
                    JOIN seao.identifiant_fournisseur i ON i.identifiant = s.identifiant_fournisseur
                    WHERE i.fournisseur_id = e.fournisseur_id)
        FROM entreprise e JOIN groupe g ON g.cle = e.cle
        ORDER BY g.numero, e.neq IS NULL, e.fournisseur_id""")]
