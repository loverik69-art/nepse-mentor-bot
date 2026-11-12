import asyncio
import httpx
import aiosqlite

from config import settings
from services.historical_data import (
    import_historical_month,
    HistoricalDataError,
)

MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "Shubhamnpk/yonepse/main/data/ltp/manifest.json"
)

BATCH_SIZE = 48
SOURCE = "YONEPSE historical daily LTP dataset"


async def main():
    print("Fetching historical month list...")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(MANIFEST_URL)
        response.raise_for_status()
        manifest = response.json()

    months = manifest.get("availableMonths")

    if not isinstance(months, list):
        raise ValueError("Invalid historical manifest")

    months = sorted(months, reverse=True)

    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute(
            """
            SELECT DISTINCT substr(source_updated_at, 1, 7)
            FROM stock_price_history
            WHERE source = ?
            """,
            (SOURCE,),
        )
        rows = await cursor.fetchall()

    imported_months = {row[0] for row in rows if row[0]}

    remaining = [
        month for month in months
        if month not in imported_months
    ]

    print(f"Available months: {len(months)}")
    print(f"Already imported: {len(imported_months)}")
    print(f"Remaining months: {len(remaining)}")

    batch = remaining[:BATCH_SIZE]

    if not batch:
        print("All available months have been imported.")
        return

    print(f"\nImporting {len(batch)} months...\n")

    total_inserted = 0
    total_duplicates = 0
    total_rejected = 0

    for month in batch:
        print(f"Importing {month}...")

        try:
            result = await import_historical_month(month)

        except Exception as exc:
            print(f"FAILED: {month}: {exc}")
            print("Stopped. Run the script again to resume.")
            break

        inserted = result["inserted"]
        duplicates = result["duplicates"]
        rejected = result["rejected"]

        total_inserted += inserted
        total_duplicates += duplicates
        total_rejected += rejected

        print(
            f"Completed {month}: "
            f"{inserted} inserted, "
            f"{duplicates} duplicates, "
            f"{rejected} rejected\n"
        )

    print("BATCH SUMMARY")
    print(f"Inserted: {total_inserted}")
    print(f"Duplicates: {total_duplicates}")
    print(f"Rejected: {total_rejected}")


if __name__ == "__main__":
    asyncio.run(main())
