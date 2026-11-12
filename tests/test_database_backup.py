import sqlite3

import pytest

from database.backup import create_database_backup


def test_create_database_backup_preserves_data(tmp_path):
    source = tmp_path / "nepse.db"
    backup_dir = tmp_path / "backups"

    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE portfolio (symbol TEXT, quantity REAL)"
        )
        connection.execute(
            "INSERT INTO portfolio VALUES ('NABIL', 10)"
        )

    backup = create_database_backup(source, backup_dir)

    assert backup.exists()

    with sqlite3.connect(backup) as connection:
        result = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        holding = connection.execute(
            "SELECT symbol, quantity FROM portfolio"
        ).fetchone()

    assert result == "ok"
    assert holding == ("NABIL", 10.0)


def test_create_database_backup_rejects_missing_source(tmp_path):
    source = tmp_path / "missing.db"
    backup_dir = tmp_path / "backups"

    with pytest.raises(FileNotFoundError):
        create_database_backup(source, backup_dir)

    assert not backup_dir.exists()
