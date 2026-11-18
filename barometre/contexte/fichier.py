"""Le fichier de contexte (contexte_municipalites.csv) vu par l'analyse : la vue à enrichir, le
rattachement de la saisie aux organismes de l'export, et l'ajout des organismes nouveaux à la fin."""

import csv
import shutil
from collections import defaultdict
from pathlib import Path

from barometre.chemins import DOSSIER_SORTIES
from utilitaires import clean_org_name, clean_text


# Les colonnes que le SEAO ne donne pas : completer_contexte.py ou une saisie à la main les remplit.
CONTEXT_FIELDS = (
    "code_geographique", "population", "classe_taille", "superficie_km2",
    "region_administrative", "mrc", "type_milieu",
    "particularites_infrastructures", "source_contexte", "notes",
)


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

    Le fichier est d'abord copié. Si son début change d'un seul octet, la copie
    est remise en place et ValueError est levée.
    """
    if not rows:
        return 0
    source_path = Path(source_path)
    avant = source_path.read_bytes()
    with source_path.open("r", encoding="utf-8-sig", newline="") as file:
        fields = csv.DictReader(file).fieldnames
    Path(dossier_sauvegarde).mkdir(exist_ok=True)
    sauvegarde = Path(dossier_sauvegarde) / (source_path.name + ".avant_ajout")
    shutil.copy2(source_path, sauvegarde)

    nouvelles = [{field: row.get(field, "") if field in ("organisme", "buyer_ids")
                  else ("À compléter" if field in CONTEXT_FIELDS and field != "notes" else "")
                  for field in fields} for row in rows]
    # Pas « utf-8-sig » en ajout : le BOM se retrouverait au milieu du fichier.
    with source_path.open("a", encoding="utf-8", newline="") as file:
        if avant and not avant.endswith(b"\n"):
            file.write("\r\n")
        csv.DictWriter(file, fieldnames=fields).writerows(nouvelles)

    if not source_path.read_bytes().startswith(avant):
        shutil.copy2(sauvegarde, source_path)
        raise ValueError("Le début du fichier de contexte a changé : ajout annulé, ancien fichier restauré.")
    return len(nouvelles)


def load_context_source(source_path, generated_path, context_rows):
    """Retourne les lignes du fichier de contexte, sans jamais le réécrire.

    Leur rattachement aux organismes de l'export est vérifié (merge_context_rows).
    S'il n'existe pas, le fichier est créé une seule fois : à partir de l'ancienne
    vue generated_path si elle existe (lignes et colonnes ajoutées à la main
    comprises), sinon à partir de context_rows.
    """
    def read_rows(path):
        with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fields = reader.fieldnames or []
            if not {"organisme", "buyer_ids"}.issubset(fields):
                raise ValueError(f"Colonnes organisme et buyer_ids requises dans {path}")
            rows = list(reader)
            # Trop ou trop peu de cellules : une virgule de trop dans une saisie, par exemple.
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError(f"Ligne CSV incomplète ou mal délimitée dans {path}")
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
