import sqlite3

import pytest

from database.backup import create_database_backup, restore_database_backup


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


def test_restore_database_backup_preserves_current_database(
    tmp_path,
):
    target = tmp_path / "nepse.db"
    backup_dir = tmp_path / "backups"
    safety_dir = tmp_path / "safety"

    with sqlite3.connect(target) as connection:
        connection.execute(
            "CREATE TABLE portfolio (symbol TEXT, quantity REAL)"
        )
        connection.execute(
            "INSERT INTO portfolio VALUES ('NABIL', 10)"
        )

    backup = create_database_backup(target, backup_dir)

    with sqlite3.connect(target) as connection:
        connection.execute(
            "UPDATE portfolio SET quantity = 20"
        )

    safety_backup = restore_database_backup(
        backup, target, safety_dir
    )

    with sqlite3.connect(target) as connection:
        restored = connection.execute(
            "SELECT quantity FROM portfolio"
        ).fetchone()[0]

    with sqlite3.connect(safety_backup) as connection:
        previous = connection.execute(
            "SELECT quantity FROM portfolio"
        ).fetchone()[0]

    assert restored == 10
    assert previous == 20
    assert safety_backup.exists()


def test_restore_rejects_invalid_backup_without_changing_target(
    tmp_path,
):
    target = tmp_path / "nepse.db"
    invalid_backup = tmp_path / "invalid.db"
    safety_dir = tmp_path / "safety"

    with sqlite3.connect(target) as connection:
        connection.execute("CREATE TABLE test (value INTEGER)")
        connection.execute("INSERT INTO test VALUES (123)")

    invalid_backup.write_text("not a valid SQLite database")

    with pytest.raises(sqlite3.DatabaseError):
        restore_database_backup(
            invalid_backup, target, safety_dir
        )

    with sqlite3.connect(target) as connection:
        value = connection.execute(
            "SELECT value FROM test"
        ).fetchone()[0]

    assert value == 123
    assert not safety_dir.exists()
