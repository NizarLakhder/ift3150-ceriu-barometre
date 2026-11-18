"""La connexion à PostgreSQL, et la création des schémas et des tables (schema.sql) dans une base déjà créée.

Rien n'est validé ici : charger_base.py décide des commits.
"""

import os

import psycopg

from barometre.chemins import SCHEMA_SQL


def connecter():
    """Ouvre la connexion. Le mot de passe vient du fichier pgpass.conf de PostgreSQL."""
    return psycopg.connect(
        host=os.environ.get("BAROMETRE_HOTE", "localhost"), port=int(os.environ.get("BAROMETRE_PORT", "5433")),
        dbname=os.environ.get("BAROMETRE_BASE", "barometre"), user=os.environ.get("BAROMETRE_COMPTE", "barometre"),
        connect_timeout=10)


def preparer_schemas(connexion, reinitialiser):
    """Efface les quatre schémas si on le demande, puis crée les schémas et les tables s'ils manquent.

    La base elle-même existe déjà. Rien n'est validé ici : executer_chargement fait le commit.
    """
    if reinitialiser:
        connexion.execute("DROP SCHEMA IF EXISTS analyses, seao, organismes, territoire CASCADE")
        print("Base effacée.")
    if connexion.execute("SELECT to_regnamespace('seao')").fetchone()[0] is None:
        connexion.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        print("Base créée à partir de schema.sql.")
