from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from risk_backend.repositories.auth import AuthRepository
from risk_backend.repositories.database import (
    DATABASE_SCHEMA_VERSION,
    _migrate_database,
)
from risk_backend.security import hash_password, is_password_hash, verify_password


class PasswordSecurityTests(unittest.TestCase):
    def test_password_hash_uses_salt_and_verifies(self) -> None:
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")

        self.assertNotEqual(first, second)
        self.assertTrue(is_password_hash(first))
        self.assertTrue(verify_password("correct horse battery staple", first))
        self.assertFalse(verify_password("wrong password", first))

    def test_repository_upgrades_legacy_password_after_login(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "auth.db"
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "create table db_users (id integer primary key, userName text, password text)"
                )
                connection.execute(
                    "insert into db_users values (1, 'admin', 'legacy-password')"
                )

            def test_connect():
                from contextlib import contextmanager

                @contextmanager
                def manager():
                    connection = sqlite3.connect(database_path)
                    connection.row_factory = sqlite3.Row
                    try:
                        yield connection
                        connection.commit()
                    except Exception:
                        connection.rollback()
                        raise
                    finally:
                        connection.close()

                return manager()

            with patch("risk_backend.repositories.auth.connect", test_connect):
                self.assertTrue(AuthRepository().validate("admin", "legacy-password"))

            with sqlite3.connect(database_path) as connection:
                stored = connection.execute(
                    "select password from db_users where userName = 'admin'"
                ).fetchone()[0]
            self.assertTrue(is_password_hash(stored))
            self.assertNotEqual(stored, "legacy-password")


class DatabaseMigrationTests(unittest.TestCase):
    def test_existing_database_is_backed_up_and_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "risk_app.db"
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "create table db_users (id integer primary key, userName text, password text)"
                )
                connection.execute("insert into db_users values (1, 'admin', 'admin')")

            _migrate_database(database_path, existing_database=True)

            backups = list(database_path.parent.glob("risk_app.backup-*.db"))
            self.assertEqual(len(backups), 1)
            with sqlite3.connect(database_path) as connection:
                version = connection.execute("pragma user_version").fetchone()[0]
                stored = connection.execute("select password from db_users").fetchone()[
                    0
                ]
            with sqlite3.connect(backups[0]) as connection:
                backup_password = connection.execute(
                    "select password from db_users"
                ).fetchone()[0]

            self.assertEqual(version, DATABASE_SCHEMA_VERSION)
            self.assertTrue(is_password_hash(stored))
            self.assertEqual(backup_password, "admin")

    def test_current_database_does_not_create_repeated_backups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "risk_app.db"
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "create table db_users (id integer primary key, userName text, password text)"
                )
                connection.execute(f"pragma user_version = {DATABASE_SCHEMA_VERSION}")

            _migrate_database(database_path, existing_database=True)

            self.assertEqual(list(database_path.parent.glob("*.backup-*.db")), [])

    def test_newer_database_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "risk_app.db"
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "create table db_users (id integer primary key, userName text, password text)"
                )
                connection.execute(
                    f"pragma user_version = {DATABASE_SCHEMA_VERSION + 1}"
                )

            with self.assertRaisesRegex(RuntimeError, "高于软件支持的版本"):
                _migrate_database(database_path, existing_database=True)


if __name__ == "__main__":
    unittest.main()
