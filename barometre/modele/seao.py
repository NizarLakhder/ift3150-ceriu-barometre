"""Les tables du SEAO : les exports chargés, les fiches et ce qu'elles publient, les fournisseurs.

charger_base.py lit les exports, regroupe les fournisseurs et garde ses contrôles ; ces classes décrivent
les lignes et les écrivent. Comme avant, une ligne déjà en base est gardée telle quelle (DO NOTHING), sauf
pour les exports, les fournisseurs et leurs identifiants : un doublon y arrête l'export (CONFLIT = None).
Seules ces deux premières tables rendent les numéros que la base leur donne (NUMERO).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from psycopg.types.json import Jsonb

from barometre.modele.table import Table, genere


@dataclass(slots=True, kw_only=True)
class FichierSource(Table):
    """Un export du SEAO chargé : une ligne de seao.fichier_source."""

    TABLE = "seao.fichier_source"
    CLE = ("nom",)
    CONFLIT = None
    NUMERO = "fichier_id"  # les liens fiche_fichier y renvoient

    fichier_id: int | None = genere()
    nom: str                       # comme « hebdo_20260907_20260913.json »
    type: str                      # hebdomadaire ou mensuel, lu dans le nom
    periode_debut: date
    periode_fin: date
    date_publication: datetime | None
    empreinte_sha256: str
    nb_fiches: int                 # toutes les fiches de l'export, municipales ou non
    charge_le: datetime | None = genere()


@dataclass(slots=True, kw_only=True)
class Nomenclature(Table):
    """Un code de la nomenclature du SEAO, comme « S3 » : une ligne de seao.nomenclature."""

    TABLE = "seao.nomenclature"
    CLE = ("code",)
    CONFLIT = "DO NOTHING"  # un code connu garde son premier libellé

    code: str
    libelle: str


@dataclass(slots=True, kw_only=True)
class Classification(Table):
    """Un code UNSPSC employé dans une fiche : une ligne de seao.classification."""

    TABLE = "seao.classification"
    CLE = ("code",)
    CONFLIT = "DO NOTHING"  # un code connu garde son premier libellé

    code: str
    libelle: str


@dataclass(slots=True, kw_only=True)
class Fournisseur(Table):
    """Une entreprise, retenue ou soumissionnaire : une ligne de seao.fournisseur."""

    TABLE = "seao.fournisseur"
    CLE = ()                   # le NEQ peut manquer : pas de clé naturelle sûre
    CONFLIT = None
    NUMERO = "fournisseur_id"  # ses identifiants FO y sont rattachés

    fournisseur_id: int | None = genere()
    nom: str                   # le dernier nom lu
    neq: str | None
    adresse: str | None
    localite: str | None
    region: str | None
    code_postal: str | None
    pays: str | None


@dataclass(slots=True, kw_only=True)
class IdentifiantFournisseur(Table):
    """Un identifiant FO du SEAO et son entreprise : une ligne de seao.identifiant_fournisseur."""

    TABLE = "seao.identifiant_fournisseur"
    CLE = ("identifiant",)
    CONFLIT = None

    identifiant: str               # « FO-… »
    fournisseur_id: int


@dataclass(slots=True, kw_only=True)
class Dossier(Table):
    """Un dossier du SEAO, suivi d'une publication à l'autre : une ligne de seao.dossier."""

    TABLE = "seao.dossier"
    CLE = ("ocid",)
    CONFLIT = "DO NOTHING"  # un dossier déjà connu garde son numéro

    dossier_id: int | None = genere()
    ocid: str


@dataclass(slots=True, kw_only=True)
class Fiche(Table):
    """Une publication d'un dossier, avec son état à ce moment : une ligne de seao.fiche."""

    TABLE = "seao.fiche"
    CLE = ("dossier_id", "release_id")
    CONFLIT = "DO NOTHING"  # la base garde la version du premier export chargé

    fiche_id: int | None = genere()
    dossier_id: int
    release_id: str                # un horodatage à la seconde, unique avec le dossier
    date_deduite_numero: date | None
    date_fiche: datetime | None
    acheteur_id: str
    tags: list[str]                # tender, contract...
    numero_avis: str | None
    titre: str | None
    statut: str | None
    methode_code: str | None
    methode: str | None
    justification_methode: str | None
    categorie_principale: str | None
    type_contrat: str | None
    nomenclature_code: str | None
    date_ouverture: datetime | None
    date_fermeture: datetime | None
    duree_jours: int | None
    nb_soumissionnaires: int | None
    url_avis: str | None
    brut: Jsonb                    # la fiche complète, telle que publiée
    titre_recherche: str | None = genere()  # calculée par la base à partir du titre


@dataclass(slots=True, kw_only=True)
class FicheFichier(Table):
    """Un export où figure une fiche : une ligne de seao.fiche_fichier."""

    TABLE = "seao.fiche_fichier"
    CLE = ("fiche_id", "fichier_id")
    CONFLIT = "DO NOTHING"

    fiche_id: int
    fichier_id: int
    version_publiee: Jsonb | None  # la version de cet export, si elle diffère de celle gardée


@dataclass(slots=True, kw_only=True)
class FicheClassification(Table):
    """Un code UNSPSC d'une fiche, principal ou non : une ligne de seao.fiche_classification."""

    TABLE = "seao.fiche_classification"
    CLE = ("fiche_id", "code")
    CONFLIT = "DO NOTHING"

    fiche_id: int
    code: str
    principale: bool


@dataclass(slots=True, kw_only=True)
class Soumissionnaire(Table):
    """Une entreprise qui a soumissionné, fiche par fiche : une ligne de seao.soumissionnaire."""

    TABLE = "seao.soumissionnaire"
    CLE = ("fiche_id", "identifiant_fournisseur")
    CONFLIT = "DO NOTHING"

    fiche_id: int
    identifiant_fournisseur: str


@dataclass(slots=True, kw_only=True)
class Attribution(Table):
    """Une attribution publiée dans une fiche, avec son fournisseur : une ligne de seao.attribution."""

    TABLE = "seao.attribution"
    CLE = ("fiche_id", "numero")
    CONFLIT = "DO NOTHING"

    attribution_id: int | None = genere()
    fiche_id: int
    numero: str
    identifiant_fournisseur: str
    statut: str | None
    date_attribution: datetime | None
    montant: Decimal | None        # tel que publié ; ce n'est pas une dépense payée
    montant_total: Decimal | None
    devise: str | None


@dataclass(slots=True, kw_only=True)
class Contrat(Table):
    """Un contrat, qui découle d'une attribution : une ligne de seao.contrat."""

    TABLE = "seao.contrat"
    CLE = ("attribution_id",)
    CONFLIT = "DO NOTHING"

    contrat_id: int | None = genere()
    attribution_id: int
    numero: str
    statut: str | None
    date_signature: datetime | None
    date_fin: datetime | None
    montant: Decimal | None
    devise: str | None
