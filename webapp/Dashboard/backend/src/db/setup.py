"""Create the Flowwatch database and tables, or verify an existing installation."""
import argparse
import re
from getpass import getpass

from mysql.connector import Error

from pathlib import Path
from .mysql_store import MySQLStore, mysql_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--admin-user", help="Use an administrator for setup and prompt for its password.")
    args = parser.parse_args()
    settings = mysql_settings()
    if settings is None:
        parser.error("Set FLOWWATCH_MYSQL_USER and FLOWWATCH_MYSQL_PASSWORD in Dashboard/.env.")
    database = settings["database"]
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", database):
        parser.error("Use a database name containing only letters, numbers and underscores.")
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    statements = [statement.strip() for statement in schema.split(";") if statement.strip()]
    try:
        if not args.check:
            setup = dict(settings)
            setup.pop("database")
            if args.admin_user:
                setup.update(user=args.admin_user, password=getpass("MySQL administrator password: "))
            with MySQLStore(setup).transaction() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4")
                cursor.execute(f"USE `{database}`")
                for statement in statements:
                    cursor.execute(statement)
        with MySQLStore(settings).transaction() as cursor:
            tables = [statement.split()[5] for statement in statements]
            for table in tables:
                cursor.execute(f"SELECT 1 FROM `{table}` LIMIT 1")
                cursor.fetchall()
            print(f"MySQL connection verified. {len(tables)} Flowwatch tables are available.")
    except Error as error:
        parser.exit(1, f"MySQL setup could not finish (error {error.errno}). Check credentials and database permissions.\n")


if __name__ == "__main__":
    main()
