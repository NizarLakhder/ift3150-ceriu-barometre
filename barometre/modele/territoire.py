"""Les cinq tables du territoire : fichiers de référence, régions, MRC, municipalités, indicateurs d'eau.

Une classe par table du schéma territoire de schema.sql, et la lecture d'une ligne du répertoire du
MAMH. charger_base.py décide quand écrire et dans quelle transaction ; ses contrôles restent chez lui.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from barometre.modele.conversions import code_mrc_de, entier, nombre, region_de, texte
from barometre.modele.table import Table, genere


@dataclass(slots=True, kw_only=True)
class FichierReference(Table):
    """Un fichier de référence chargé, comme MUN.csv ou demarches.csv : une ligne de territoire.fichier_reference."""

    TABLE = "territoire.fichier_reference"
    CLE = ("nom",)

    fichier_reference_id: int | None = genere()  # numéro attribué par la base
    nom: str
    description: str
    date_fichier: date
    empreinte_sha256: str
    charge_le: datetime | None = genere()        # rempli par la base au chargement


@dataclass(slots=True, kw_only=True)
class Region(Table):
    """Une région administrative : une ligne de territoire.region."""

    TABLE = "territoire.region"
    CLE = ("code",)

    code: str  # « 05 » pour l'Estrie
    nom: str


@dataclass(slots=True, kw_only=True)
class Mrc(Table):
    """Une MRC ou une communauté métropolitaine du répertoire : une ligne de territoire.mrc."""

    TABLE = "territoire.mrc"
    CLE = ("code",)

    code: str  # « AR190 », ou « CM663 » pour une communauté métropolitaine
    nom: str
    designation: str
    population: int | None
    superficie_km2: Decimal | None
    code_postal: str | None
    region_code: str | None

    @classmethod
    def depuis_repertoire(cls, m):
        """Une ligne de MRC_CM_Arg.csv."""
        return cls(code=m["mrccod"].strip(), nom=m["mrcnom"].strip(), designation=m["mrcdescdesi"].strip(),
                   population=entier(m["mrcpopul"]), superficie_km2=nombre(m["msupf"]),
                   code_postal=texte(m["mrccodp"]), region_code=region_de(m["mrcregion"])[0])


@dataclass(slots=True, kw_only=True)
class Municipalite(Table):
    """Une municipalité du répertoire du MAMH : une ligne de territoire.municipalite."""

    TABLE = "territoire.municipalite"
    CLE = ("code_geographique",)  # une nouvelle version du répertoire met la ligne à jour

    code_geographique: str
    nom: str
    designation: str
    population: int | None
    superficie_km2: Decimal | None
    superficie_terrestre_km2: Decimal | None
    code_postal: str | None
    date_constitution: date | None
    region_code: str
    mrc_code: str | None
    communaute_code: str | None
    anciens_codes: list[str]
    anciens_noms: list[str]

    @classmethod
    def depuis_repertoire(cls, m, anciens):
        """Une ligne de MUN.csv ; anciens relie un code à ses anciens codes et noms (regroupements.csv)."""
        return cls(code_geographique=m["mcode"].strip(), nom=m["munnom"].strip(), designation=m["mdes"].strip(),
                   population=entier(m["mpopul"]), superficie_km2=nombre(m["msuperf"]),
                   superficie_terrestre_km2=nombre(m["msupft"]), code_postal=texte(m["mcodpos"]),
                   date_constitution=date.fromisoformat(m["mdatcons"]) if texte(m["mdatcons"]) else None,
                   region_code=region_de(m["regadm"])[0], mrc_code=code_mrc_de(m["mrc"]),
                   communaute_code=code_mrc_de(m["mcm"], "CM"),
                   anciens_codes=anciens.get(m["mcode"].strip(), ([], []))[0],
                   anciens_noms=anciens.get(m["mcode"].strip(), ([], []))[1])


@dataclass(slots=True, kw_only=True)
class IndicateurEau(Table):
    """Les données d'une municipalité dans la Stratégie de l'eau, pour une année : une ligne de territoire.indicateur_eau."""

    TABLE = "territoire.indicateur_eau"
    CLE = ("code_source", "annee")

    code_source: str               # le code tel que publié, complété à cinq chiffres
    annee: int
    nom_source: str | None
    code_geographique: str | None  # vide si le code n'est plus dans le répertoire
    classe_population: str | None
    population_desservie: int | None
    indice_fuites: Decimal | None
    validite_audit_pct: Decimal | None
    consommation_l_pers_jour: Decimal | None
    longueur_reseau_km: Decimal | None
