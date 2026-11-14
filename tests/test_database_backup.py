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


def test_prune_database_backups_keeps_newest(tmp_path):
    from database.backup import prune_database_backups

    backup_dir = tmp_path / "automatic"
    backup_dir.mkdir()

    for day in range(1, 5):
        (backup_dir / f"nepse-202611{day:02d}.db").touch()

    removed = prune_database_backups(backup_dir, keep=2)

    remaining = sorted(path.name for path in backup_dir.glob("*.db"))

    assert remaining == [
        "nepse-20261103.db",
        "nepse-20261104.db",
    ]
    assert len(removed) == 2


def test_prune_database_backups_rejects_zero_retention(tmp_path):
    from database.backup import prune_database_backups

    with pytest.raises(ValueError):
        prune_database_backups(tmp_path, keep=0)


def test_restore_preserves_multiple_tables_and_records(tmp_path):
    target = tmp_path / "nepse.db"
    backup_dir = tmp_path / "backups"
    safety_dir = tmp_path / "safety"

    with sqlite3.connect(target) as connection:
        connection.execute(
            "CREATE TABLE portfolio (symbol TEXT, quantity REAL)"
        )
        connection.execute(
            "CREATE TABLE transactions (symbol TEXT, action TEXT)"
        )
        connection.executemany(
            "INSERT INTO portfolio VALUES (?, ?)",
            [("NABIL", 10), ("NICA", 5)],
        )
        connection.executemany(
            "INSERT INTO transactions VALUES (?, ?)",
            [("NABIL", "buy"), ("NICA", "sell")],
        )

    backup = create_database_backup(target, backup_dir)

    with sqlite3.connect(target) as connection:
        connection.execute("DELETE FROM portfolio")
        connection.execute("DELETE FROM transactions")

    restore_database_backup(backup, target, safety_dir)

    with sqlite3.connect(target) as connection:
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        holdings = connection.execute(
            "SELECT symbol, quantity FROM portfolio ORDER BY symbol"
        ).fetchall()
        transactions = connection.execute(
            "SELECT symbol, action FROM transactions ORDER BY symbol"
        ).fetchall()

    assert integrity == "ok"
    assert holdings == [("NABIL", 10.0), ("NICA", 5.0)]
    assert transactions == [("NABIL", "buy"), ("NICA", "sell")]


def test_restore_failure_during_final_swap_preserves_target(
    tmp_path, monkeypatch
):
    import database.backup as backup_module

    target = tmp_path / "nepse.db"
    backup_dir = tmp_path / "backups"
    safety_dir = tmp_path / "safety"

    with sqlite3.connect(target) as connection:
        connection.execute("CREATE TABLE test (value INTEGER)")
        connection.execute("INSERT INTO test VALUES (123)")

    backup = create_database_backup(target, backup_dir)

    with sqlite3.connect(target) as connection:
        connection.execute("UPDATE test SET value = 456")

    def fail_replace(source, destination):
        raise OSError("Simulated final swap failure")

    monkeypatch.setattr(backup_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="Simulated final swap failure"):
        restore_database_backup(backup, target, safety_dir)

    with sqlite3.connect(target) as connection:
        value = connection.execute(
            "SELECT value FROM test"
        ).fetchone()[0]

    assert value == 456
    assert list(target.parent.glob(".nepse.db.restore-*.tmp")) == []
    assert list(safety_dir.glob("nepse-*.db"))


def test_prune_preserves_unrelated_files(tmp_path):
    from database.backup import prune_database_backups

    backup_dir = tmp_path / "automatic"
    backup_dir.mkdir()

    old_backup = backup_dir / "nepse-20261101.db"
    new_backup = backup_dir / "nepse-20261102.db"
    unrelated = backup_dir / "important.txt"

    old_backup.touch()
    new_backup.touch()
    unrelated.write_text("Keep this file")

    removed = prune_database_backups(backup_dir, keep=1)

    assert removed == [old_backup]
    assert not old_backup.exists()
    assert new_backup.exists()
    assert unrelated.read_text() == "Keep this file"


def test_prune_missing_directory_returns_empty_list(tmp_path):
    from database.backup import prune_database_backups

    backup_dir = tmp_path / "missing"

    assert prune_database_backups(backup_dir) == []
    assert not backup_dir.exists()
