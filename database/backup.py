import os
import tempfile
import sqlite3
from datetime import datetime
from pathlib import Path


def create_database_backup(
    source_path: str | Path,
    backup_dir: str | Path,
) -> Path:
    """Create and verify a timestamped SQLite database backup."""
    source_path = Path(source_path)
    backup_dir = Path(backup_dir)

    if not source_path.is_file():
        raise FileNotFoundError(
            f"Database not found: {source_path}"
        )

    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = backup_dir / f"nepse-{timestamp}.db"

    try:
        with sqlite3.connect(source_path) as source:
            with sqlite3.connect(backup_path) as destination:
                source.backup(destination)

                result = destination.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]

                if result != "ok":
                    raise sqlite3.DatabaseError(
                        f"Backup integrity check failed: {result}"
                    )

        backup_path.chmod(0o600)
        return backup_path

    except Exception:
        backup_path.unlink(missing_ok=True)
        raise


def restore_database_backup(
    backup_path: str | Path,
    target_path: str | Path,
    safety_backup_dir: str | Path,
) -> Path:
    """Safely restore a verified SQLite backup."""
    backup_path = Path(backup_path)
    target_path = Path(target_path)

    if not backup_path.is_file():
        raise FileNotFoundError(
            f"Backup not found: {backup_path}"
        )

    if not target_path.is_file():
        raise FileNotFoundError(
            f"Target database not found: {target_path}"
        )

    if backup_path.resolve() == target_path.resolve():
        raise ValueError("Backup and target must be different files")

    backup_uri = backup_path.resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(backup_uri, uri=True) as source:
        result = source.execute(
            "PRAGMA integrity_check"
        ).fetchone()

        if result is None or result[0] != "ok":
            raise sqlite3.DatabaseError(
                f"Invalid backup integrity: {result}"
            )

        safety_backup = create_database_backup(
            target_path, safety_backup_dir
        )

        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{target_path.name}.restore-",
            suffix=".tmp",
            dir=target_path.parent,
        )
        os.close(fd)
        temporary_path = Path(temporary_name)

        try:
            with sqlite3.connect(temporary_path) as destination:
                source.backup(destination)

                result = destination.execute(
                    "PRAGMA integrity_check"
                ).fetchone()

                if result is None or result[0] != "ok":
                    raise sqlite3.DatabaseError(
                        f"Restored database integrity failed: {result}"
                    )

            temporary_path.chmod(0o600)
            os.replace(temporary_path, target_path)

        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    return safety_backup
