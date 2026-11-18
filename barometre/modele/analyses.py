"""Les deux tables des analyses : le classement de chaque fiche et les démarches classées à la main.

Le chargement (barometre/chargement/analyses.py) calcule les valeurs (règles de repérage, codes
permis, dossiers et fournisseurs) et garde ses contrôles ; ces classes décrivent les lignes et les écrivent.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from barometre.modele.table import Table, genere


@dataclass(slots=True, kw_only=True)
class FicheClassee(Table):
    """Le classement d'une fiche par les règles de repérage : une ligne de analyses.fiche_classee."""

    TABLE = "analyses.fiche_classee"
    CLE = ("fiche_id",)  # une fiche reclassée remplace son classement

    fiche_id: int
    nature_transaction: str          # achat, subvention_ou_contribution, vente_immeuble ou partenariat
    lie_eau: bool
    pga_eau: bool
    gestion_actifs_eau: str | None   # pga_eau, outil, etape, plan_intervention ou gestion_actifs
    version_regles: str
    calcule_le: datetime             # écrite par le programme, même si la base a une valeur par défaut


@dataclass(slots=True, kw_only=True)
class Demarche(Table):
    """Une démarche repérée et classée à la main dans demarches.csv : une ligne de analyses.demarche."""

    TABLE = "analyses.demarche"
    CLE = ()
    CONFLIT = "DO NOTHING"  # comme avant : une ligne en conflit (dossier déjà présent) est écartée sans message

    demarche_id: int | None = genere()  # numéro attribué par la base
    organisme_id: int
    plan: str                    # pga_eau
    classement: str              # elaboration, etape, plan_intervention, plan_gestion_actifs...
    etat: str                    # mandat_attribue, appel_offres_en_cours...
    date_attribution: date | None
    date_publication: date | None
    montant: Decimal | None
    dossier_id: int | None
    fournisseur_id: int | None
    lien: str | None
    source: str
    notes: str | None
