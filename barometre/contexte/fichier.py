"""Le fichier de contexte (contexte_municipalites.csv), seul endroit où il est lu ou écrit.

Pour l'analyse : la vue à enrichir, le rattachement de la saisie aux organismes de l'export, et
l'ajout des organismes nouveaux à la fin. Pour completer_contexte.py : la lecture, la réécriture
après sauvegarde, et la liste des cas à vérifier. Pour le chargement : la lecture.

Toute lecture passe par controler_contexte, toute écriture qui remplace le fichier par
remplacer_fichier : il n'est jamais laissé à moitié écrit. Une seule écriture à la fois : rien
n'empêche deux programmes de le modifier en même temps.
"""

import codecs
import csv
import io
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from barometre.chemins import DOSSIER_SORTIES
from barometre.contexte.noms import normaliser_code_postal
from utilitaires import clean_org_name, clean_text


# Les colonnes que le SEAO ne donne pas : completer_contexte.py ou une saisie à la main les remplit.
CONTEXT_FIELDS = (
    "code_geographique", "population", "classe_taille", "superficie_km2",
    "region_administrative", "mrc", "type_milieu",
    "particularites_infrastructures", "source_contexte", "notes",
)
# Les 12 colonnes que l'analyse crée : completer_contexte.py et charger_base.py les exigent.
COLONNES_CONTEXTE = ("organisme", "buyer_ids", *CONTEXT_FIELDS)
# Le minimum, exigé par défaut. L'analyse s'en contente : elle lit aussi l'ancienne vue, à laquelle des
# colonnes peuvent manquer.
COLONNES_ANALYSE = ("organisme", "buyer_ids")

# Les étiquettes d'une case sans valeur chiffrée.
A_COMPLETER = "À compléter"      # la donnée peut exister, on ne l'a pas encore trouvée
SANS_OBJET = "Sans objet"        # le champ ne s'applique pas, comme la MRC d'une MRC
HORS_MRC = "Hors MRC"            # ce que dit le répertoire des villes qui ne font partie d'aucune MRC
AUCUNE_DONNEE = "Aucune donnée"  # ce que publie la Stratégie pour une municipalité sans données sur l'eau


class ContexteInvalide(ValueError):
    """Le fichier de contexte est mal formé : le message dit où, et quoi corriger."""


class EcritureEchouee(OSError):
    """Un remplacement n'a pas abouti. Le message dit l'état réel, vérifié sur les octets du fichier.

    nouveau_en_place : False si le fichier a son contenu d'avant, True si le nouveau est en place mais
    pas la sauvegarde, None si l'état n'a pas pu être vérifié. conserves : les copies gardées.
    """

    def __init__(self, message, nouveau_en_place, conserves=()):
        super().__init__(message)
        self.nouveau_en_place = nouveau_en_place
        self.conserves = tuple(conserves)


class _FichierModifie(Exception):
    """Le fichier n'a plus les octets lus au départ."""


def controler_contexte(octets, chemin, colonnes_requises=COLONNES_ANALYSE):
    """Lit les octets d'un fichier de contexte : retourne (colonnes, lignes), ou lève ContexteInvalide.

    Contrôles, dans l'ordre : UTF-8 (avec ou sans BOM), en-tête présent, pas deux colonnes du même
    nom, colonnes requises, guillemets bien fermés, autant de cellules que de colonnes, organisme
    jamais vide. Une cellule entre guillemets peut contenir virgules et sauts de ligne.
    """
    nom = Path(chemin).name
    corps = octets[len(codecs.BOM_UTF8):] if octets.startswith(codecs.BOM_UTF8) else octets
    try:
        texte = corps.decode("utf-8")
    except UnicodeDecodeError as erreur:
        ligne = corps[:erreur.start].count(b"\n") + 1
        raise ContexteInvalide(f"{nom} n'est pas en UTF-8 (ligne {ligne}) : l'enregistrer en UTF-8 "
                               "(dans Excel : « CSV UTF-8 »).") from None

    # Le mode strict refuse un guillemet mal fermé, au lieu d'avaler la suite du fichier.
    lecteur = csv.DictReader(io.StringIO(texte, newline=""), strict=True)
    guillemets = ("CSV mal formé, probablement un guillemet mal fermé. Une cellule entre guillemets doit "
                  "finir par un guillemet ; un guillemet à l'intérieur s'écrit \"\".")
    try:
        colonnes = lecteur.fieldnames
    except csv.Error:
        raise ContexteInvalide(f"{nom}, ligne 1 : {guillemets}") from None
    if not colonnes:
        raise ContexteInvalide(f"{nom} est vide : la ligne d'en-tête manque.")
    doublons = sorted({c for c in colonnes if colonnes.count(c) > 1})
    if doublons:
        raise ContexteInvalide(f"{nom} : plusieurs colonnes s'appellent "
                               + ", ".join(f"« {c} »" for c in doublons) + " : renommer ou supprimer les doubles.")
    manquantes = [c for c in colonnes_requises if c not in colonnes]
    if manquantes:
        conseil = (" Le fichier semble séparé par des points-virgules : il doit l'être par des virgules."
                   if ";" in "".join(colonnes) else "")
        raise ContexteInvalide(f"{nom} : colonne(s) manquante(s) : {', '.join(manquantes)}.{conseil}")

    lignes = []
    while True:
        debut = lecteur.line_num + 1
        try:
            ligne = next(lecteur)
        except StopIteration:
            break
        except csv.Error:
            raise ContexteInvalide(f"{nom}, ligne {debut} : {guillemets}") from None
        trop = ligne.get(None, [])
        presentes = sum(valeur is not None for cle, valeur in ligne.items() if cle is not None)
        if trop or presentes < len(colonnes):
            conseil = ("Une virgule de trop ? Une cellule qui contient une virgule doit être entre guillemets."
                       if trop else "Une virgule manque ?")
            if lecteur.line_num > debut:
                conseil += f" La ligne se poursuit jusqu'à la ligne {lecteur.line_num} : un guillemet mal fermé ?"
            raise ContexteInvalide(f"{nom}, ligne {debut} : {len(colonnes) + len(trop) if trop else presentes} "
                                   f"cellules au lieu de {len(colonnes)}. {conseil}")
        if not ligne["organisme"].strip():
            raise ContexteInvalide(f"{nom}, ligne {debut} : la colonne organisme est vide.")
        lignes.append(ligne)
    return colonnes, lignes


def lire_contexte(chemin, colonnes_requises=COLONNES_ANALYSE):
    """Retourne (colonnes, lignes) du fichier de contexte, après les contrôles de controler_contexte."""
    return controler_contexte(Path(chemin).read_bytes(), chemin, colonnes_requises)


def _temporaire(dossier, nom):
    """Crée un fichier vide au nom unique, <nom>.<aléa>.tmp, dans dossier ; retourne son chemin."""
    descripteur, chemin = tempfile.mkstemp(dir=dossier, prefix=nom + ".", suffix=".tmp")
    os.close(descripteur)
    return Path(chemin)


def remplacer_fichier(chemin, contenu, avant, dossier_sauvegarde, nom_sauvegarde):
    """Remplace chemin par contenu sans jamais le laisser à moitié écrit, puis met sa sauvegarde à jour.

    avant : les octets lus au départ. Étapes :
      1. contenu dans un temporaire au nom unique à côté du fichier, forcé sur le disque, puis relu ;
      2. copie du fichier, avec sa date, dans un second temporaire à côté de la sauvegarde : elle doit
         être identique à avant, sinon le fichier a changé depuis sa lecture et rien n'est remplacé ;
      3. os.replace du fichier, puis seulement de l'ancienne sauvegarde.
    Avant l'étape 3, ni le fichier ni l'ancienne sauvegarde ne sont touchés. Le contrôle de l'étape 2
    n'est pas un verrou : une seule écriture à la fois reste nécessaire. En cas d'échec, l'état est
    vérifié sur les octets du fichier, seuls les temporaires de cet appel sont supprimés, et
    EcritureEchouee est levée ; une interruption (Ctrl+C) est relancée, avec cet état en note.
    """
    chemin, dossier_sauvegarde = Path(chemin), Path(dossier_sauvegarde)
    temporaire = copie = None
    remplacement_lance, etape = False, "écriture"
    try:
        temporaire = _temporaire(chemin.parent, chemin.name)
        with temporaire.open("wb") as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        if os.name != "nt":  # les droits du fichier ; sous Windows, le mode ne dit que « lecture seule »
            shutil.copymode(chemin, temporaire)
        if temporaire.read_bytes() != contenu:
            raise OSError(f"{temporaire.name}, relu, ne correspond pas au contenu prévu")
        dossier_sauvegarde.mkdir(exist_ok=True)
        copie = _temporaire(dossier_sauvegarde, nom_sauvegarde)
        shutil.copy2(chemin, copie)
        if copie.read_bytes() != avant:
            raise _FichierModifie()
        remplacement_lance, etape = True, chemin.name
        os.replace(temporaire, chemin)
        etape = nom_sauvegarde
        os.replace(copie, dossier_sauvegarde / nom_sauvegarde)
    except BaseException as erreur:
        message, nouveau_en_place, conserves = _constater(chemin, avant, contenu, temporaire, copie,
                                                          remplacement_lance, etape, erreur)
        if not isinstance(erreur, Exception):  # Ctrl+C : on s'arrête, en disant où l'on en est
            erreur.add_note(f"Interruption pendant l'écriture : {message}")
            raise
        raise EcritureEchouee(message, nouveau_en_place, conserves) from erreur


def _constater(chemin, avant, contenu, temporaire, copie, remplacement_lance, etape, erreur):
    """Après un échec : l'état réel du fichier, d'après ses octets ; supprime les temporaires inutiles.

    Retourne (message, nouveau_en_place, copies gardées). Dans le doute, rien n'est supprimé.
    """
    nom = chemin.name
    try:
        actuel = chemin.read_bytes()
    except OSError:
        actuel = None

    def identique(fichier, octets):
        try:
            return fichier.read_bytes() == octets
        except OSError:
            return False

    if actuel is None:
        etat = "indéterminé"
    elif actuel == avant:
        etat = "inchangé"
    elif not remplacement_lance:
        etat = "modifié"  # ce programme n'a rien remplacé, mais le fichier a changé depuis sa lecture
    elif actuel == contenu:
        etat = "remplacé"
    else:
        etat = "indéterminé"

    presents = [p for p in (temporaire, copie) if p is not None and p.exists()]
    sauvegarde_faite = copie is not None and not copie.exists()
    if etat == "indéterminé":
        gardes = presents
    elif copie in presents and (etat == "remplacé" or (etat == "modifié" and identique(copie, avant))):
        gardes = [copie]
    else:
        gardes = []
    non_supprimes = []
    for fichier in presents:
        if fichier not in gardes:
            try:
                fichier.unlink()
            except OSError:
                non_supprimes.append(fichier)

    if etat == "inchangé":
        texte = (f"{nom} est inchangé (vérifié sur ses octets) ; "
                 + ("sa sauvegarde a été refaite avec ce même contenu." if sauvegarde_faite
                    else "sa sauvegarde précédente aussi."))
        nouveau_en_place = False
    elif etat == "modifié":
        texte = (f"{nom} a changé depuis sa lecture (une saisie en cours ?) : il n'a pas été remplacé, et sa "
                 "sauvegarde précédente est inchangée. Relancez quand plus rien ne le modifie : ce contrôle "
                 "n'est pas un verrou." + (f" Copie de la version lue : {copie}." if gardes else ""))
        nouveau_en_place = False
    elif etat == "remplacé":
        texte = (f"le nouveau {nom} est en place (vérifié sur ses octets), mais sa sauvegarde n'a pas été mise "
                 f"à jour : la copie de l'ancien contenu est dans {copie}." if gardes
                 else f"le nouveau {nom} et sa sauvegarde sont en place (vérifié sur ses octets).")
        nouveau_en_place = True
    else:
        texte = (f"l'état de {nom} n'a pas pu être vérifié : rien n'est supprimé."
                 + (f" Copie de l'ancien contenu : {copie}." if copie in gardes else "")
                 + (f" Nouveau contenu : {temporaire}." if temporaire in gardes else ""))
        nouveau_en_place = None
    if non_supprimes:
        texte += " Temporaire(s) qui n'ont pas pu être supprimés : " + ", ".join(map(str, non_supprimes)) + "."

    if isinstance(erreur, _FichierModifie) or not isinstance(erreur, Exception):
        raison = ""
    elif isinstance(erreur, PermissionError) and remplacement_lance:
        raison = (f"{etape} n'a pas pu être remplacé ({erreur.strerror or erreur}) : il est peut-être ouvert "
                  "dans un autre programme, comme Excel, ou en lecture seule ; corrigez, puis relancez. ")
    else:
        raison = f"Écriture impossible ({type(erreur).__name__} : {erreur}). "
    if raison and not texte.startswith(nom):  # une majuscule après une phrase, jamais sur le nom du fichier
        texte = texte[:1].upper() + texte[1:]
    return raison + texte, nouveau_en_place, gardes + non_supprimes


def reecrire_contexte(chemin, colonnes, lignes, dossier_sauvegarde=DOSSIER_SORTIES, avant=None):
    """Réécrit tout le fichier de contexte : mêmes colonnes dans le même ordre, UTF-8 avec BOM, CRLF.

    Le contenu est préparé en mémoire (une ligne impossible à écrire lève ValueError sans rien
    toucher), puis remplace le fichier par remplacer_fichier, avec la sauvegarde
    dossier_sauvegarde/<nom>.bak. avant : les octets lus par le programme ; sinon, ceux du fichier
    au moment de l'appel.
    """
    chemin = Path(chemin)
    if avant is None:
        avant = chemin.read_bytes()
    sortie = io.StringIO(newline="")
    ecrivain = csv.DictWriter(sortie, fieldnames=colonnes)
    ecrivain.writeheader()
    ecrivain.writerows(lignes)
    contenu = ("\ufeff" + sortie.getvalue()).encode("utf-8")
    remplacer_fichier(chemin, contenu, avant, dossier_sauvegarde, chemin.name + ".bak")


def ecrire_cas_a_verifier(chemin, a_trancher, non_municipaux):
    """Écrit la liste des cas non rattachés : a_traiter vaut « oui » pour a_trancher, « non » sinon."""
    with open(chemin, "w", encoding="utf-8-sig", newline="") as fichier:
        ecrivain = csv.writer(fichier)
        # Les cas à trancher d'abord, puis ceux pour lesquels il n'y a rien à faire.
        ecrivain.writerow(["organisme", "raison", "a_traiter"])
        ecrivain.writerows(cas + ("oui",) for cas in sorted(a_trancher))
        ecrivain.writerows(cas + ("non",) for cas in sorted(non_municipaux))


def lire_codes_postaux_seao(dossier=DOSSIER_SORTIES):
    """Retourne {identifiant d'acheteur : codes postaux du SEAO}, lus dans sorties/*/a_enrichir.csv."""
    codes = {}
    for chemin in sorted(Path(dossier).glob("*/a_enrichir.csv")):
        with chemin.open(encoding="utf-8-sig", newline="") as fichier:
            for ligne in csv.DictReader(fichier):
                for identifiant in (ligne.get("buyer_ids") or "").split("|"):
                    for code in (ligne.get("code_postal_seao") or "").split("|"):
                        if identifiant.strip() and code.strip():
                            codes.setdefault(identifiant.strip(), set()).add(normaliser_code_postal(code))
    return codes


def build_context_rows(summaries, rows):
    """Une ligne de contexte par organisme, tout à « À compléter ».

    merge_context_rows y reporte ensuite la saisie. La localité et le code postal
    du SEAO sont repris : ils servent à départager les homonymes.
    """
    by_org = defaultdict(list)
    for row in rows:
        by_org[row["organisme"]].append(row)

    context = []
    for s in summaries:
        items = by_org[s["organisme"]]
        localites = sorted({r["localite"] for r in items if r["localite"]})
        codes = sorted({r["code_postal"] for r in items if r["code_postal"]})
        context.append({
            "organisme": s["organisme"],
            "type_organisme": s["type_organisme"],
            "buyer_ids": s["buyer_ids"],
            "localite_seao": " | ".join(localites),
            "code_postal_seao": " | ".join(codes),
            "adresse_disponible_seao": "oui" if localites or codes else "non",
            "nb_avis_observes": s["nb_avis"],
            "code_geographique": "À compléter",
            "population": "À compléter",
            "classe_taille": "À compléter",
            "superficie_km2": "À compléter",
            "region_administrative": "À compléter",
            "mrc": "À compléter",
            "type_milieu": "À compléter",
            "particularites_infrastructures": "À compléter",
            "source_contexte": "À compléter",
            # Champ libre : vide, il n'y a rien à signaler.
            "notes": "",
        })
    return context


def merge_context_rows(context_rows, source_rows, absents=None):
    """Reporte le contexte saisi sur les organismes de l'export. Dans le doute, lève ValueError.

    La ligne de contexte d'un organisme se cherche dans cet ordre :
      1. les mêmes identifiants d'acheteur, dans n'importe quel ordre;
      2. un identifiant commun et le même nom, avec un avertissement : la liste de
         Montréal change d'un export à l'autre. Un nom différent, ou plusieurs
         lignes visées, arrête tout;
      3. le même nom, si la ligne de contexte n'a aucun identifiant (sinon, erreur);
      4. sinon l'organisme est nouveau : il reste « À compléter » et va dans
         absents, si la liste est fournie (voir append_context_rows).
    Seules les cases remplies sont reportées.
    """
    def buyer_ids(row):
        return frozenset(part.strip() for part in row.get("buyer_ids", "").split(" | ") if part.strip())

    # Un identifiant dans deux lignes, ou un nom sans identifiant répété, rend
    # le rattachement ambigu : on s'arrête.
    by_ids, by_name, owner_by_id = {}, defaultdict(list), {}
    for source in source_rows:
        name = clean_org_name(source.get("organisme"))
        ids = buyer_ids(source)
        if not name:
            raise ValueError("Le contexte contient une ligne sans nom d'organisme.")
        if ids:
            if ids in by_ids or any(sid in owner_by_id for sid in ids):
                raise ValueError(f"Identifiants d'acheteur ambigus dans le contexte : {name}")
            by_ids[ids] = source
            for sid in ids:
                owner_by_id[sid] = source
        elif any(not buyer_ids(other) for other in by_name[name]):
            raise ValueError(f"Nom sans identifiant répété dans le contexte : {name}")
        by_name[name].append(source)

    merged, used_sources, seen_targets = [], set(), set()
    for row in context_rows:
        result = dict(row)
        ids = buyer_ids(row)
        name = clean_org_name(row.get("organisme"))
        key = ("ids", ids) if ids else ("nom", name)
        if key in seen_targets:
            raise ValueError(f"Organisme ambigu dans la vue de contexte : {name}")
        seen_targets.add(key)
        source = by_ids.get(ids) if ids else None
        if source is None:
            candidates = by_name.get(name, [])
            communs = {sid for sid in ids if sid in owner_by_id}
            if communs:
                # Règle 2 : un identifiant commun et le même nom.
                proprietaires = {id(owner_by_id[sid]): owner_by_id[sid] for sid in communs}
                if len(proprietaires) > 1 or len(candidates) > 1:
                    raise ValueError(f"Correspondance de contexte incertaine pour {name}; "
                                     "plusieurs lignes de contexte visent cet organisme.")
                source = next(iter(proprietaires.values()))
                if clean_org_name(source.get("organisme")) != name:
                    raise ValueError(f"Correspondance de contexte incertaine pour {name} : un identifiant "
                                     f"est commun avec « {source.get('organisme')} », mais le nom diffère.")
                anciens = buyer_ids(source)
                print(f"  contexte : liste d'acheteurs modifiée pour {name} "
                      f"({len(anciens)} identifiants enregistrés, {len(ids)} dans cet export)")
            else:
                if len(candidates) > 1 or any(buyer_ids(c) for c in candidates):
                    raise ValueError(f"Correspondance de contexte incertaine pour {name}; vérifier les identifiants.")
                source = candidates[0] if candidates else None
        if source is not None:
            # Une même ligne de contexte ne doit jamais servir à deux organismes.
            if id(source) in used_sources:
                raise ValueError(f"Une ligne de contexte correspond à plusieurs organismes : {name}")
            used_sources.add(id(source))
            for field in CONTEXT_FIELDS:
                value = source.get(field, "")
                if clean_text(value) and clean_text(value) != "À compléter":
                    result[field] = value
        elif absents is not None:
            absents.append(result)
        merged.append(result)
    return merged


def append_context_rows(source_path, rows, dossier_sauvegarde=DOSSIER_SORTIES):
    """Ajoute à la fin du fichier de contexte les organismes nouveaux; retourne leur nombre.

    Les octets déjà présents sont gardés tels quels, quel que soit leur format : seules les nouvelles
    lignes passent par DictWriter. Le fichier est remplacé par remplacer_fichier, avec la sauvegarde
    dossier_sauvegarde/<nom>.avant_ajout.
    """
    if not rows:
        return 0
    source_path = Path(source_path)
    avant = source_path.read_bytes()
    fields, _ = controler_contexte(avant, source_path)

    nouvelles = [{field: row.get(field, "") if field in ("organisme", "buyer_ids")
                  else ("À compléter" if field in CONTEXT_FIELDS and field != "notes" else "")
                  for field in fields} for row in rows]
    sortie = io.StringIO(newline="")
    csv.DictWriter(sortie, fieldnames=fields).writerows(nouvelles)
    # Pas de BOM dans la partie ajoutée : il se retrouverait au milieu du fichier.
    contenu = avant + (b"\r\n" if avant and not avant.endswith(b"\n") else b"") + sortie.getvalue().encode("utf-8")
    remplacer_fichier(source_path, contenu, avant, dossier_sauvegarde, source_path.name + ".avant_ajout")
    return len(nouvelles)


def load_context_source(source_path, generated_path, context_rows):
    """Retourne les lignes du fichier de contexte, sans jamais le réécrire.

    Leur rattachement aux organismes de l'export est vérifié (merge_context_rows).
    S'il n'existe pas, le fichier est créé une seule fois : à partir de l'ancienne
    vue generated_path si elle existe (lignes et colonnes ajoutées à la main
    comprises), sinon à partir de context_rows.
    """
    def read_rows(path):
        # Les contrôles de controler_contexte ; seules les colonnes organisme et buyer_ids sont exigées.
        fields, rows = lire_contexte(path)
        return rows, fields

    source_path, generated_path = Path(source_path), Path(generated_path)
    if source_path.exists():
        source_rows, _ = read_rows(source_path)
        merge_context_rows(context_rows, source_rows)
        return source_rows

    if generated_path.exists():
        previous_rows, previous_fields = read_rows(generated_path)
    else:
        previous_rows = context_rows
        previous_fields = list(context_rows[0]) if context_rows else []

    fields = ["organisme", "buyer_ids", *CONTEXT_FIELDS]
    generated_fields = {"organisme", "type_organisme", "buyer_ids", "localite_seao",
                        "code_postal_seao", "adresse_disponible_seao", "nb_avis_observes", *CONTEXT_FIELDS}
    fields.extend(field for field in previous_fields if field not in generated_fields)
    source_rows = [{field: row.get(field, "À compléter" if field in CONTEXT_FIELDS else "")
                    for field in fields} for row in previous_rows]
    # Vérifié avant d'écrire : en cas d'ambiguïté, rien n'est créé.
    merge_context_rows(context_rows, source_rows)
    # Le mode « x » refuse d'écraser un fichier apparu entre-temps.
    with source_path.open("x", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(source_rows)
    return source_rows
