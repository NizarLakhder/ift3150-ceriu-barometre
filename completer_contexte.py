"""
Remplit les cases « À compléter » de contexte_municipalites.csv avec deux jeux
du MAMH déposés dans donnees_reference/ : le Répertoire des municipalités et la
Stratégie québécoise d'économie d'eau potable (voir FICHIERS; seul MUN.csv est
obligatoire). Rien n'est téléchargé : les mêmes fichiers donnent toujours les
mêmes chiffres, et la date de chacun est notée dans source_contexte.

Un organisme du SEAO est rattaché au répertoire, dans l'ordre :
  1. par le code géographique déjà inscrit : c'est ainsi qu'on règle un cas à
     la main;
  2. par le nom exact, sans accents, ponctuation, désignation ni article;
  3. par une règle tolérante (« St » pour Saint, un « de » oublié, une faute de
     frappe), qui exige un indice publié : code postal, désignation ou région.
Des homonymes ne sont départagés que par un tel indice. Sans indice, rien n'est
rempli : le cas va dans sorties/contexte_a_verifier.csv, avec a_traiter à
« oui » (« non » pour un organisme non municipal).

Une valeur déjà présente n'est jamais remplacée. Une case sans chiffre porte
une étiquette qui dit pourquoi (voir A_COMPLETER et les suivantes). Le type de
milieu reste « À compléter » : aucun de ces fichiers ne le donne.

Les codes postaux du SEAO sont lus dans sorties/<export>/a_enrichir.csv :
lancer analyser_seao.py avant. Le contexte est copié dans
sorties/contexte_municipalites.csv.bak avant d'être réécrit.

Lancement : python completer_contexte.py
"""

import xml.etree.ElementTree as ET
from datetime import date

from barometre.chemins import A_VERIFIER_CSV, CONTEXT_SOURCE_CSV, DOSSIER_SORTIES
from barometre.contexte.fichier import (A_COMPLETER, AUCUNE_DONNEE, HORS_MRC, SANS_OBJET,  # noqa: F401
                                        ecrire_cas_a_verifier, lire_codes_postaux_seao, lire_contexte,
                                        reecrire_contexte)
from barometre.contexte.noms import (DESIGNATION_DISTINCTIVE, DESIGNATIONS, SERVICES, cle_organisme,  # noqa: F401
                                     construire_index, construire_index_des_codes, decrire, departager,
                                     designation_au_debut, normaliser, normaliser_code_postal,
                                     sans_territoires_non_organises, type_attendu)
from barometre.contexte.rattachement import (ABREVIATIONS, DESIGNATIONS_LUES, DETERMINANTS, MEME_NOM,  # noqa: F401
                                             NOM_ALLONGE, NOM_APPROCHE, NOM_RACCOURCI, REGLES_A_CONFIRMER,
                                             code_postal_de, construire_index_tolerant, lieu, lire_nom_seao,
                                             mots_utiles, nom_proche, rapprocher, rattacher, tolerance)
from barometre.contexte.remplissage import (construire_donnees_eau, remplir_ligne, valeurs_mrc,  # noqa: F401
                                            valeurs_municipalite, vider_note)
from barometre.sources.mamh import DOSSIER_SOURCES, FICHIERS, lire_csv, lire_fichiers  # noqa: F401

# Les fonctions sont dans barometre/ ; elles restent lisibles ici pour charger_base.py et les tests.
CONTEXTE_CSV = CONTEXT_SOURCE_CSV


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main():
    """Remplit les cases « À compléter » du contexte, puis liste les cas à traiter à la main."""
    if not CONTEXTE_CSV.exists():
        print(f"Erreur : {CONTEXTE_CSV} introuvable. Lancer d'abord analyser_seao.py.")
        return

    print(f"Lecture des fichiers de référence dans {DOSSIER_SOURCES} :")
    contenus, dates = lire_fichiers()
    if contenus is None:
        print("\nIl manque un fichier obligatoire. Rien n'a été modifié.")
        return

    municipalites = lire_csv(contenus["municipalites"])
    mrc = lire_csv(contenus["mrc"]) if "mrc" in contenus else []
    perimunicipaux = list(ET.fromstring(contenus["perimunicipaux"])) if "perimunicipaux" in contenus else []
    eau = construire_donnees_eau(
        lire_csv(contenus["fuites"]) if "fuites" in contenus else [],
        lire_csv(contenus["validite"]) if "validite" in contenus else [],
        lire_csv(contenus["consommation"]) if "consommation" in contenus else [],
    )
    index = construire_index(municipalites, mrc, perimunicipaux)
    index_tolerant = construire_index_tolerant(index)
    par_code = construire_index_des_codes(municipalites, mrc)
    codes_postaux = lire_codes_postaux_seao()
    print(f"  codes postaux SEAO lus pour {len(codes_postaux)} identifiants d'acheteur")

    # Provenance notée dans chaque case remplie : les fichiers, leur date, et le jour du remplissage.
    source = (f"Répertoire des municipalités du Québec (MAMH), fichier du {dates['municipalites']}"
              + (f"; Stratégie québécoise d'économie d'eau potable 2024 (MAMH), fichier du {dates['validite']}"
                 if "validite" in dates else "")
              + f"; contexte rempli le {date.today().isoformat()}")

    colonnes, lignes = lire_contexte(CONTEXTE_CSV)

    # remplis et rapproches comptent des organismes, deja_saisis des cases. ambigus et absents
    # restent à trancher à la main; sans_objet regroupe les organismes non municipaux.
    remplis, rapproches, deja_saisis, ambigus, absents, sans_objet = 0, 0, 0, [], [], []
    notes_videes = 0

    for ligne in lignes:
        notes_videes += vider_note(ligne)
        correspondance, methode, echec = rattacher(ligne, index, index_tolerant, par_code, codes_postaux)
        if echec:
            genre, raison = echec
            {"ambigu": ambigus, "absent": absents, "non municipal": sans_objet}[genre].append(
                (ligne["organisme"], raison))
            continue

        # Si le nom exact n'a pas suffi, la source dit comment l'organisme a été rattaché.
        type_organisme, trouve = correspondance
        source_ligne = source + (f"; {methode}" if methode else "")
        if type_organisme == "municipalité":
            valeurs = valeurs_municipalite(trouve, eau, source_ligne)
        elif type_organisme == "MRC ou communauté":
            valeurs = valeurs_mrc(trouve, source_ligne)
        else:
            # Organisme reconnu, mais le répertoire n'a rien à reporter pour lui.
            sans_objet.append((ligne["organisme"],
                               "organisme périmunicipal : ni population ni superficie dans le répertoire"))
            continue

        remplies, intactes = remplir_ligne(ligne, valeurs)
        deja_saisis += intactes
        if remplies:
            remplis += 1
            if methode and methode.startswith("nom rapproché"):
                rapproches += 1

    reecrire_contexte(CONTEXTE_CSV, colonnes, lignes, DOSSIER_SORTIES)
    ecrire_cas_a_verifier(A_VERIFIER_CSV, ambigus + absents, sans_objet)

    print(f"\nOrganismes dans le contexte         : {len(lignes)}")
    print(f"Organismes enrichis                 : {remplis}")
    print(f"  dont par une règle tolérante      : {rapproches}")
    print(f"Valeurs déjà présentes, intactes : {deja_saisis}")
    print(f"À trancher à la main                : {len(ambigus) + len(absents)}")
    print(f"  candidats trouvés, non retenus    : {len(ambigus)}")
    print(f"  municipalité ou MRC introuvable   : {len(absents)}")
    print(f"Organismes non municipaux           : {len(sans_objet)}  (rien à compléter)")
    if notes_videes:
        print(f"Notes « À compléter » vidées        : {notes_videes}  (rien à signaler)")
    print(f"\n{CONTEXTE_CSV} mis à jour (sauvegarde dans {DOSSIER_SORTIES / (CONTEXTE_CSV.name + '.bak')})")
    print(f"{A_VERIFIER_CSV} liste les cas à traiter à la main.")
    print("Le type de milieu reste à documenter : aucun de ces fichiers ne le fournit.")


if __name__ == "__main__":
    main()
