"""La classe commune des tables de la base : une colonne = un attribut, et l'écriture des lignes.

Une classe de table décrit une table de schema.sql (tests/test_modele.py le vérifie) et sait l'écrire.
Elle ne contrôle rien : ses annotations décrivent les colonnes, sans rien vérifier ; les contrôles
restent dans charger_base.py et dans la base. Elle n'ouvre jamais de connexion et ne valide jamais
de transaction : elle écrit dans celle de l'appelant.
"""

from dataclasses import field, fields
from typing import ClassVar


def genere():
    """Une colonne que la base remplit (numéro attribué, valeur par défaut) : elle n'est jamais écrite."""
    return field(default=None, metadata={"genere": True})


def inserer(connexion, table, lignes, conflit="DO NOTHING", cle=None):
    """Insère des lignes (des dictionnaires aux mêmes clés) dans une table.

    conflit dit quoi faire si la ligne existe déjà : DO NOTHING (garder
    l'ancienne) ou DO UPDATE (la remplacer, pour les données de référence).
    """
    if not lignes:
        return
    colonnes = list(lignes[0])
    requete = (f"INSERT INTO {table} ({', '.join(colonnes)}) VALUES ({', '.join('%(' + c + ')s' for c in colonnes)}) "
               f"ON CONFLICT")
    if conflit == "DO UPDATE":
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

    @classmethod
    def colonnes(cls):
        """Les colonnes écrites, dans l'ordre de schema.sql : toutes, sauf celles que la base remplit."""
        return [champ.name for champ in fields(cls) if not champ.metadata.get("genere")]

    def en_ligne(self):
        """Les valeurs à écrire, colonne par colonne."""
        return {colonne: getattr(self, colonne) for colonne in self.colonnes()}

    @classmethod
    def inserer(cls, connexion, objets):
        """Écrit les objets par inserer(), avec la table, la clé et le conflit de la classe."""
        colonnes = cls.colonnes()  # une seule fois par table, pas pour chaque objet
        inserer(connexion, cls.TABLE, [{c: getattr(objet, c) for c in colonnes} for objet in objets],
                cls.CONFLIT, list(cls.CLE))
