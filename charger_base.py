"""
Charge dans PostgreSQL le répertoire des municipalités, le contexte, les
exports du SEAO et les démarches classées à la main, puis vérifie que la base
redonne les chiffres des CSV d'analyser_seao.py.

Ordre de chargement :
  1. le territoire : donnees_reference/ et regroupements.csv;
  2. les organismes et leurs identifiants d'acheteur : contexte_municipalites.csv;
  3. les exports de donnees_seao/ pas encore chargés, dans l'ordre de leur
     période, fiches municipales seulement;
  4. le classement de chaque fiche, avec les règles d'analyser_seao.py;
  5. les démarches de demarches.csv.

Chaque export est chargé une seule fois (son empreinte est notée), d'un seul
bloc. Les fichiers sources ne sont jamais modifiés. Le programme écrit aussi
sorties/fournisseurs_a_regrouper.csv, les identifiants FO à vérifier à la main.

Les tables sont créées à partir de schema.sql si le schéma seao n'existe pas.
Connexion : localhost, port 5433, base et compte « barometre », ou les
variables BAROMETRE_HOTE, BAROMETRE_PORT, BAROMETRE_BASE et BAROMETRE_COMPTE.
Le mot de passe est lu dans pgpass.conf, jamais dans le projet.

Utilisation :
    python charger_base.py                  # charge ce qui manque, puis vérifie
    python charger_base.py --reinitialiser  # efface les quatre schémas et recharge, après une modification de schema.sql
"""

import argparse
import sys

# Le programme enchaîne les étapes ; le code est dans barometre/. Les fonctions déplacées restent lisibles ici,
# pour les tests et pour les outils qui les importent depuis charger_base (comme connecter).
from barometre.chargement.analyses import (charger_demarches, classer_fiches, dossiers_a_classer,  # noqa: F401
                                           ligne_de_demarche, version_des_regles)
from barometre.chargement.base_de_donnees import connecter, preparer_schemas
from barometre.chargement.exports import (charger_export, cles_des_fiches, forme_comparable,  # noqa: F401
                                          lignes_de_la_fiche, meme_contenu)
from barometre.chargement.fournisseurs import (charger_fournisseurs, completer, fournisseurs_a_regrouper,  # noqa: F401
                                               regrouper_fournisseurs)
from barometre.chargement.organismes import charger_organismes, organisme_de  # noqa: F401
from barometre.chargement.territoire import charger_territoire, noter_fichier_reference  # noqa: F401
from barometre.chargement.verification import BilanValidation, lire_csv_de_verification, verifier  # noqa: F401
from barometre.chemins import (A_REGROUPER_CSV, CONTEXT_SOURCE_CSV, DEMARCHES_CSV, DOSSIER_SEAO,  # noqa: F401
                               REGROUPEMENTS_CSV, SCHEMA_SQL)
from barometre.configuration import ConfigurationInvalide
from barometre.contexte.fichier import A_COMPLETER, COLONNES_CONTEXTE, ContexteInvalide, lire_contexte  # noqa: F401
from barometre.modele.conversions import (CODES, code_de, code_mrc_de, entier, instant, nombre,  # noqa: F401
                                          region_de, texte)
from barometre.modele.organismes import type_organisme  # noqa: F401
from barometre.regles import regles
from barometre.sources.seao import decrire_export, ordre_de_chargement  # noqa: F401
from utilitaires import empreinte, write_csv  # noqa: F401


def main():
    """Vérifie les règles et le contexte avant toute connexion, puis charge ; rend le code de sortie.

    0 : tout concorde avec les CSV ; 1 : échec ou écart ; 2 : vérification incomplète (CSV absents).
    """
    parser = argparse.ArgumentParser(description="Charge le SEAO, le répertoire et le contexte dans PostgreSQL.")
    parser.add_argument("--reinitialiser", action="store_true",
                        help="efface les quatre schémas et recharge tout depuis les fichiers")
    args = parser.parse_args()

    # Les règles d'abord, avant toute connexion : un fichier de règles invalide ne doit jamais arrêter
    # un chargement à moitié fait.
    try:
        regles()
    except ConfigurationInvalide as erreur:
        print("ÉCHEC avant toute connexion : les règles de repérage sont invalides. Aucune connexion n'a été "
              "ouverte et rien n'a été chargé.", file=sys.stderr)
        print(erreur, file=sys.stderr)
        return 1

    # Le contexte aussi : sinon, --reinitialiser effacerait la base avant de découvrir l'erreur.
    try:
        lire_contexte(CONTEXT_SOURCE_CSV, COLONNES_CONTEXTE)
    except (ContexteInvalide, OSError) as erreur:
        print("ÉCHEC avant toute connexion : le fichier de contexte est illisible ou mal formé. Aucune "
              "connexion n'a été ouverte et rien n'a été chargé.", file=sys.stderr)
        print(erreur, file=sys.stderr)
        return 1

    try:
        return executer_chargement(args)
    except Exception as erreur:
        print(f"ÉCHEC : {type(erreur).__name__} : {erreur}", file=sys.stderr)
        print("Certaines étapes peuvent déjà avoir été enregistrées par les commits précédents. "
              "La transaction courante est annulée ; le chargement entier n'est pas annulé.", file=sys.stderr)
        return 1


def executer_chargement(args):
    """Conserve les transactions existantes et retourne le code du bilan final."""
    with connecter() as connexion:
        preparer_schemas(connexion, args.reinitialiser)
        connexion.commit()

        print("Territoire et organismes...")
        charger_territoire(connexion)
        nb_organismes, nb_acheteurs = charger_organismes(connexion)
        connexion.commit()
        print(f"  {nb_organismes} organismes, {nb_acheteurs} identifiants d'acheteur")

        for chemin in sorted(DOSSIER_SEAO.glob("*.json"), key=ordre_de_chargement):
            charge = charger_export(connexion, chemin)
            connexion.commit()          # un export entier, ou rien
            print(f"  {chemin.name} : " + ("déjà chargé" if charge is None else
                                            f"{charge[0]} fiches municipales, dont {charge[1]} nouvelles"
                                            + (f" et {charge[2]} publiées autrement qu'avant" if charge[2] else "")))

        print(f"Classement : {classer_fiches(connexion)} fiches ({version_des_regles()})")
        print(f"Démarches : {charger_demarches(connexion)} dossiers classés à la main")
        connexion.commit()

        print("\nVérifications :")
        bilan = verifier(connexion)
        print(f"  Exports comparés : {len(bilan.exports_compares)}/{len(bilan.exports_attendus)}")
        if bilan.code_sortie == 0:
            print("  Validation complète : aucun écart avec les CSV.")
        elif bilan.code_sortie == 1:
            print("  ÉCHEC de la validation : " + "; ".join(bilan.ecarts + bilan.erreurs_lecture))
        else:
            print("  VÉRIFICATION INCOMPLÈTE : CSV absents ou aucun export disponible.")
        if bilan.code_sortie != 0:
            print("  Les étapes déjà validées par commit restent enregistrées. "
                  "Ce bilan n'annule pas les imports.")
        a_classer = dossiers_a_classer(connexion)
        print(f"  Dossiers liés à la gestion des actifs en eau, à classer dans demarches.csv : {len(a_classer)}"
              + (" (" + ", ".join(a_classer) + ")" if a_classer else ""))
        a_regrouper = fournisseurs_a_regrouper(connexion)
        write_csv(A_REGROUPER_CSV, a_regrouper)
        print(f"  Fournisseurs du même nom, dont un seul a un NEQ, à vérifier : "
              f"{len({l['groupe'] for l in a_regrouper})} groupes ({A_REGROUPER_CSV})")

        print("\nContenu de la base :")
        afficher_contenu(connexion)

        return bilan.code_sortie


def afficher_contenu(connexion):
    """Le nombre de lignes des principales tables, à la fin du chargement."""
    for table in ("territoire.municipalite", "territoire.mrc", "territoire.indicateur_eau", "organismes.organisme",
                  "organismes.acheteur", "seao.dossier", "seao.fiche", "seao.fiche_fichier", "seao.attribution",
                  "seao.contrat", "seao.fournisseur", "seao.identifiant_fournisseur", "analyses.contrat_courant"):
        print(f"  {table:<28} {connexion.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:>7}")


if __name__ == "__main__":
    sys.exit(main())
