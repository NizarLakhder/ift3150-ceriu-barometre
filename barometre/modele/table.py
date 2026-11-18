"""La classe commune des tables de la base : une colonne = un attribut, et l'écriture des lignes.

Une classe de table décrit une table de schema.sql (tests/test_modele.py le vérifie) et sait l'écrire.
Elle ne contrôle pas les données : ses annotations décrivent les colonnes, sans rien vérifier ; les
contrôles restent dans charger_base.py et dans la base. Seule la demande de mise à jour est vérifiée
(verifier_mises_a_jour). Elle n'ouvre jamais de connexion et ne valide jamais de transaction : elle
écrit dans celle de l'appelant.
"""

from dataclasses import field, fields
from typing import ClassVar


def genere():
    """Une colonne que la base remplit (numéro attribué, valeur par défaut) : elle n'est jamais écrite."""
    return field(default=None, metadata={"genere": True})


def inserer(connexion, table, lignes, conflit="DO NOTHING", cle=None, mises_a_jour=None):
    """Insère des lignes (des dictionnaires aux mêmes clés) dans une table.

    conflit dit quoi faire si la ligne existe déjà : DO NOTHING (garder
    l'ancienne) ou DO UPDATE (la remplacer, pour les données de référence).
    mises_a_jour limite les colonnes remplacées ; par défaut, toutes sauf la clé.
    """
    if not lignes:
        return
    colonnes = list(lignes[0])
    requete = (f"INSERT INTO {table} ({', '.join(colonnes)}) VALUES ({', '.join('%(' + c + ')s' for c in colonnes)}) "
               f"ON CONFLICT")
    if conflit == "DO UPDATE":
        if mises_a_jour is None:
            mises_a_jour = [c for c in colonnes if c not in cle]
        requete += f" ({', '.join(cle)}) DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in mises_a_jour)
    else:
        requete += " DO NOTHING"
    with connexion.cursor() as curseur:
        curseur.executemany(requete, lignes)


class Table:
    """Une table de schema.sql. Chaque sous-classe est une dataclass dont les champs sont les colonnes."""

    __slots__ = ()
    TABLE: ClassVar[str]                   # nom complet, comme « territoire.municipalite »
    CLE: ClassVar[tuple[str, ...]]         # la clé primaire ou unique visée par ON CONFLICT
    CONFLIT: ClassVar[str] = "DO UPDATE"   # une ligne déjà en base est mise à jour
    # Vrai : chaque écriture doit dire quelles colonnes elle met à jour (mises_a_jour), comme pour les acheteurs.
    MISES_A_JOUR_OBLIGATOIRES: ClassVar[bool] = False

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

        mises_a_jour limite les colonnes remplacées en cas de conflit. Elle est vérifiée avant toute
        requête : ValueError si elle manque alors qu'elle est obligatoire, si elle est vide, ou si elle
        nomme une colonne inconnue, remplie par la base ou de la clé.
        """
        cls.verifier_mises_a_jour(mises_a_jour)
        colonnes = cls.colonnes()  # une seule fois par table, pas pour chaque objet
        inserer(connexion, cls.TABLE, [{c: getattr(objet, c) for c in colonnes} for objet in objets],
                cls.CONFLIT, list(cls.CLE), None if mises_a_jour is None else list(mises_a_jour))

    @classmethod
    def verifier_mises_a_jour(cls, mises_a_jour):
        """Refuse une mise à jour oubliée ou impossible ; ne touche à aucune base."""
        if mises_a_jour is None:
            if cls.MISES_A_JOUR_OBLIGATOIRES:
                raise ValueError(f"{cls.TABLE} : chaque écriture doit dire quelles colonnes elle met à jour "
                                 "en cas de conflit (mises_a_jour).")
            return
        if not mises_a_jour:
            raise ValueError(f"{cls.TABLE} : mises_a_jour est vide ; donner au moins une colonne.")
        champs = {champ.name: champ for champ in fields(cls)}
        for probleme, colonnes in (
                ("inconnue(s)", [c for c in mises_a_jour if c not in champs]),
                ("remplie(s) par la base", [c for c in mises_a_jour if c in champs and champs[c].metadata.get("genere")]),
                ("de la clé", [c for c in mises_a_jour if c in cls.CLE])):
            if colonnes:
                raise ValueError(f"{cls.TABLE} : colonne(s) {probleme} dans mises_a_jour : {', '.join(colonnes)}.")
