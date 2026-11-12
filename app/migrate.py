"""Database migration script for mywebapp."""
import argparse
import sys

import pymysql

MIGRATIONS = [
    (1, [
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        "CREATE INDEX idx_notes_created_at ON notes (created_at)",
    ]),
]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="mywebapp DB migration")
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-password", default="")
    p.add_argument("--db-name", required=True)
    return p.parse_args(argv)


def main():
    a = parse_args()
    conn = pymysql.connect(
        host=a.db_host, port=a.db_port, user=a.db_user,
        password=a.db_password, database=a.db_name, autocommit=True,
    )
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INT NOT NULL PRIMARY KEY, "
            "applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        cur.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
        current = cur.fetchone()[0]
        print(f"Current schema version: {current}")

        for version, statements in MIGRATIONS:
            if version <= current:
                continue
            print(f"Applying migration {version}...")
            for sql in statements:
                cur.execute(sql)
            cur.execute("INSERT INTO schema_version (version) VALUES (%s)", (version,))
    conn.close()
    print("Migration finished.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)