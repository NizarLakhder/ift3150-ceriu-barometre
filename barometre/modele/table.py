"""La classe commune des tables de la base : une colonne = un attribut, et l'écriture des lignes.

Une classe de table décrit une table de schema.sql (tests/test_modele.py le vérifie) et sait l'écrire.
Elle ne contrôle pas les données : ses annotations décrivent les colonnes, sans rien vérifier ; les
contrôles restent dans charger_base.py et dans la base. Seule la demande d'écriture est vérifiée, avant
toute requête : le mode de conflit, les colonnes à mettre à jour (verifier_mises_a_jour) et la colonne
des numéros rendus (verifier_numero). Elle n'ouvre jamais de connexion et ne valide jamais de
transaction : elle écrit dans celle de l'appelant.
"""

from dataclasses import field, fields
from typing import ClassVar

# Si la ligne existe déjà : la remplacer, la garder, ou faire échouer la requête (None : pas de ON CONFLICT).
CONFLITS = ("DO UPDATE", "DO NOTHING", None)


def genere():
    """Une colonne que la base remplit (numéro attribué, valeur par défaut) : elle n'est jamais écrite."""
    return field(default=None, metadata={"genere": True})


def requete_insertion(table, colonnes, conflit, cle=None, mises_a_jour=None):
    """La requête INSERT d'une table, avec des paramètres nommés.

    conflit dit quoi faire si la ligne existe déjà : DO UPDATE (la remplacer, pour les données de
    référence), DO NOTHING (garder l'ancienne) ou None (pas de ON CONFLICT : la requête échoue).
    mises_a_jour limite les colonnes remplacées ; par défaut, toutes sauf la clé.
    """
    if conflit not in CONFLITS:
        raise ValueError(f"{table} : mode de conflit inconnu {conflit!r} ; permis : DO UPDATE, DO NOTHING ou None.")
    requete = f"INSERT INTO {table} ({', '.join(colonnes)}) VALUES ({', '.join('%(' + c + ')s' for c in colonnes)})"
    if conflit == "DO UPDATE":
        if mises_a_jour is None:
            mises_a_jour = [c for c in colonnes if c not in cle]
        requete += f" ON CONFLICT ({', '.join(cle)}) DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in mises_a_jour)
    elif conflit == "DO NOTHING":
        requete += " ON CONFLICT DO NOTHING"
    return requete


def inserer(connexion, table, lignes, conflit="DO NOTHING", cle=None, mises_a_jour=None):
    """Insère des lignes (des dictionnaires aux mêmes clés) dans une table ; voir requete_insertion."""
    if not lignes:
        return
    requete = requete_insertion(table, list(lignes[0]), conflit, cle, mises_a_jour)
    with connexion.cursor() as curseur:
        curseur.executemany(requete, lignes)


class Table:
    """Une table de schema.sql. Chaque sous-classe est une dataclass dont les champs sont les colonnes."""

    __slots__ = ()
    TABLE: ClassVar[str]                   # nom complet, comme « territoire.municipalite »
    CLE: ClassVar[tuple[str, ...]]         # une clé primaire ou unique de schema.sql ; DO UPDATE la vise
    CONFLIT: ClassVar[str | None] = "DO UPDATE"   # une ligne déjà en base est mise à jour (voir CONFLITS)
    # Vrai : chaque écriture doit dire quelles colonnes elle met à jour (mises_a_jour), comme pour les acheteurs.
    MISES_A_JOUR_OBLIGATOIRES: ClassVar[bool] = False
    # La colonne dont inserer_et_numeroter rend les valeurs, comme « fournisseur_id ».
    NUMERO: ClassVar[str | None] = None

    @classmethod
    def colonnes(cls):
        """Les colonnes écrites, dans l'ordre de schema.sql : toutes, sauf celles que la base remplit."""
        return [champ.name for champ in fields(cls) if not champ.metadata.get("genere")]

    def en_ligne(self):
        """Les valeurs à écrire, colonne par colonne."""
        return {colonne: getattr(self, colonne) for colonne in self.colonnes()}

    @classmethod
    def inserer(cls, connexion, objets, mises_a_jour=None):
        """Écrit les objets par inserer(), avec la table, la clé et le conflit de la classe.

        mises_a_jour limite les colonnes remplacées en cas de conflit ; verifier_mises_a_jour la contrôle
        avant toute requête.
        """
        if mises_a_jour is not None:
            mises_a_jour = list(mises_a_jour)
        cls.verifier_mises_a_jour(mises_a_jour)
        colonnes = cls.colonnes()  # une seule fois par table, pas pour chaque objet
        inserer(connexion, cls.TABLE, [{c: getattr(objet, c) for c in colonnes} for objet in objets],
                cls.CONFLIT, list(cls.CLE), mises_a_jour)

    @classmethod
    def inserer_et_numeroter(cls, connexion, objets):
        """Écrit les objets et rend les numéros que la base leur donne (RETURNING), dans l'ordre des objets.

        Avant toute requête, verifier_numero. Après, la base doit avoir rendu un résultat par objet, avec
        exactement un numéro non nul ; sinon ValueError.
        """
        cls.verifier_numero()
        objets = list(objets)
        if not objets:
            return []
        colonnes = cls.colonnes()
        requete = requete_insertion(cls.TABLE, colonnes, cls.CONFLIT, list(cls.CLE)) + f" RETURNING {cls.NUMERO}"
        with connexion.cursor() as curseur:
            curseur.executemany(requete, [{c: getattr(objet, c) for c in colonnes} for objet in objets], returning=True)
            resultats = [curseur.fetchall()]
            while curseur.nextset():
                resultats.append(curseur.fetchall())
        mauvais = sum(1 for r in resultats if len(r) != 1 or len(r[0]) != 1 or r[0][0] is None)
        if len(resultats) != len(objets) or mauvais:
            raise ValueError(f"{cls.TABLE} : la base devait rendre un numéro non nul par ligne ; {len(objets)} lignes "
                             f"envoyées, {len(resultats)} résultats, dont {mauvais} sans exactement un numéro non nul.")
        return [r[0][0] for r in resultats]

    @classmethod
    def verifier_mises_a_jour(cls, mises_a_jour):
        """Refuse un mode de conflit inconnu, et une mise à jour oubliée ou impossible ; ne touche à aucune base."""
        if cls.CONFLIT not in CONFLITS:
            raise ValueError(f"{cls.TABLE} : mode de conflit inconnu {cls.CONFLIT!r} ; permis : DO UPDATE, DO NOTHING ou None.")
        if mises_a_jour is None:
            if cls.MISES_A_JOUR_OBLIGATOIRES:
                raise ValueError(f"{cls.TABLE} : chaque écriture doit dire quelles colonnes elle met à jour "
                                 "en cas de conflit (mises_a_jour).")
            return
        if cls.CONFLIT != "DO UPDATE":
            raise ValueError(f"{cls.TABLE} : mises_a_jour est sans objet, cette table ne met rien à jour en cas de "
                             f"conflit ({cls.CONFLIT or 'pas de ON CONFLICT'}).")
        demandees = list(mises_a_jour)
        if not demandees:
            raise ValueError(f"{cls.TABLE} : mises_a_jour est vide ; donner au moins une colonne.")
        champs = {champ.name: champ for champ in fields(cls)}
        for probleme, colonnes in (
                ("inconnue(s)", [c for c in demandees if c not in champs]),
                ("remplie(s) par la base", [c for c in demandees if c in champs and champs[c].metadata.get("genere")]),
                ("de la clé", [c for c in demandees if c in cls.CLE]),
                ("répétée(s)", list(dict.fromkeys(c for i, c in enumerate(demandees) if c in demandees[:i])))):
            if colonnes:
                raise ValueError(f"{cls.TABLE} : colonne(s) {probleme} dans mises_a_jour : {', '.join(colonnes)}.")

    @classmethod
    def verifier_numero(cls):
        """Avant toute requête : NUMERO nomme une colonne de la classe remplie par la base, sans ON CONFLICT."""
        champ = next((c for c in fields(cls) if c.name == cls.NUMERO), None)
        if champ is None or not champ.metadata.get("genere"):
            raise ValueError(f"{cls.TABLE} : NUMERO doit nommer une colonne de la classe remplie par la base "
                             f"(genere()) ; NUMERO vaut {cls.NUMERO!r}.")
        if cls.CONFLIT is not None:
            raise ValueError(f"{cls.TABLE} : les numéros ne sont rendus que sans ON CONFLICT ; avec {cls.CONFLIT}, "
                             "une ligne déjà en base ne rendrait aucun numéro.")
