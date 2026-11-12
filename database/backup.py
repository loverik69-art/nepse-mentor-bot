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
