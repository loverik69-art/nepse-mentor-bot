import asyncio
from types import SimpleNamespace

import aiosqlite

import database.db as db

import pytest

def test_init_db_creates_stock_price_history_table(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    asyncio.run(db.init_db())

    async def inspect_tables():
        async with aiosqlite.connect(database_path) as connection:
            async with connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ) as cursor:
                return {row[0] for row in await cursor.fetchall()}

    tables = asyncio.run(inspect_tables())

    assert "user_profiles" in tables
    assert "stock_price_history" in tables

def test_save_price_snapshot_inserts_once(tmp_path, monkeypatch):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    stock = {
        "symbol": "NABIL",
        "ltp": 549.0,
        "volume": 1200,
        "turnover": 658800.0,
        "last_updated": "2026-11-10T15:00:00+05:45",
        "source": "YONEPSE community data feed",
    }

    async def run_test():
        await db.init_db()

        first_result = await db.save_price_snapshot(stock)
        second_result = await db.save_price_snapshot(stock)

        async with aiosqlite.connect(database_path) as connection:
            async with connection.execute(
                "SELECT COUNT(*) FROM stock_price_history"
            ) as cursor:
                count = (await cursor.fetchone())[0]

        return first_result, second_result, count

    first, second, count = asyncio.run(run_test())

    assert first is True
    assert second is False
    assert count == 1

def test_get_price_history_returns_newest_first(tmp_path, monkeypatch):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def run_test():
        await db.init_db()

        await db.save_price_snapshot({
            "symbol": "NABIL",
            "ltp": 540.0,
            "volume": 1000,
            "turnover": 540000.0,
            "last_updated": "2026-11-09T15:00:00+05:45",
            "source": "YONEPSE community data feed",
        })

        await db.save_price_snapshot({
            "symbol": "NABIL",
            "ltp": 549.0,
            "volume": 1200,
            "turnover": 658800.0,
            "last_updated": "2026-11-10T15:00:00+05:45",
            "source": "YONEPSE community data feed",
        })

        return await db.get_price_history("NABIL")

    history = asyncio.run(run_test())

    assert len(history) == 2
    assert history[0]["ltp"] == 549.0
    assert history[1]["ltp"] == 540.0
    assert history[0]["symbol"] == "NABIL"

def test_get_indicator_prices_returns_daily_prices_oldest_first(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def run_test():
        await db.init_db()

        snapshots = [
            ("2026-11-09T12:00:00+05:45", 530.0),
            ("2026-11-09T15:00:00+05:45", 540.0),
            ("2026-11-10T12:00:00+05:45", 545.0),
            ("2026-11-10T15:00:00+05:45", 549.0),
            ("2026-11-11T15:00:00+05:45", 555.0),
        ]

        for timestamp, price in snapshots:
            await db.save_price_snapshot({
                "symbol": "NABIL",
                "ltp": price,
                "volume": 1000,
                "turnover": price * 1000,
                "last_updated": timestamp,
                "source": "YONEPSE community data feed",
            })

        return await db.get_indicator_prices("NABIL")

    prices = asyncio.run(run_test())

    assert prices == [540.0, 549.0, 555.0]

def test_get_indicator_prices_respects_limit(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def run_test():
        await db.init_db()

        snapshots = [
            ("2026-11-08T15:00:00+05:45", 520.0),
            ("2026-11-09T15:00:00+05:45", 530.0),
            ("2026-11-10T15:00:00+05:45", 540.0),
        ]

        for timestamp, price in snapshots:
            await db.save_price_snapshot({
                "symbol": "NABIL",
                "ltp": price,
                "volume": 1000,
                "turnover": price * 1000,
                "last_updated": timestamp,
                "source": "YONEPSE community data feed",
            })

        return await db.get_indicator_prices("NABIL", limit=2)

    prices = asyncio.run(run_test())

    assert prices == [530.0, 540.0]

def test_get_indicator_prices_returns_empty_for_unknown_symbol(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def run_test():
        await db.init_db()
        return await db.get_indicator_prices("UNKNOWN")

    prices = asyncio.run(run_test())

    assert prices == []

def test_get_indicator_prices_keeps_symbols_separate(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def run_test():
        await db.init_db()

        snapshots = [
            ("NABIL", "2026-11-09T15:00:00+05:45", 540.0),
            ("NICA", "2026-11-09T15:00:00+05:45", 1200.0),
            ("NABIL", "2026-11-10T15:00:00+05:45", 550.0),
            ("NICA", "2026-11-10T15:00:00+05:45", 1210.0),
        ]

        for symbol, timestamp, price in snapshots:
            await db.save_price_snapshot({
                "symbol": symbol,
                "ltp": price,
                "volume": 1000,
                "turnover": price * 1000,
                "last_updated": timestamp,
                "source": "YONEPSE community data feed",
            })

        nabil = await db.get_indicator_prices("NABIL")
        nica = await db.get_indicator_prices("NICA")

        return nabil, nica

    nabil, nica = asyncio.run(run_test())

    assert nabil == [540.0, 550.0]
    assert nica == [1200.0, 1210.0]

def test_get_indicator_prices_rejects_invalid_limit():
    async def run_test():
        return await db.get_indicator_prices("NABIL", limit=0)

    with pytest.raises(ValueError, match="limit must be at least 1"):
        asyncio.run(run_test())



def test_init_db_creates_stock_price_alert_indexes(tmp_path, monkeypatch):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def inspect_indexes():
        await db.init_db()

        async with aiosqlite.connect(database_path) as connection:
            async with connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                """
            ) as cursor:
                return {row[0] for row in await cursor.fetchall()}

    indexes = asyncio.run(inspect_indexes())

    assert "idx_alerts_user_id" in indexes
    assert "idx_alerts_active_id" in indexes


def test_save_portfolio_daily_snapshot_inserts_and_updates(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def run_test():
        await db.init_db()

        await db.save_portfolio_daily_snapshot(
            12345, "2026-11-10", 100000.0, 105000.0, 3
        )
        await db.save_portfolio_daily_snapshot(
            12345, "2026-11-10", 110000.0, 115000.0, 4
        )

        async with aiosqlite.connect(database_path) as connection:
            async with connection.execute(
                """
                SELECT total_investment, current_value, holdings_count
                FROM portfolio_daily_snapshots
                WHERE telegram_id = ? AND snapshot_date = ?
                """,
                (12345, "2026-11-10"),
            ) as cursor:
                row = await cursor.fetchone()

            async with connection.execute(
                "SELECT COUNT(*) FROM portfolio_daily_snapshots"
            ) as cursor:
                count = (await cursor.fetchone())[0]

        return row, count

    row, count = asyncio.run(run_test())

    assert row == (110000.0, 115000.0, 4)
    assert count == 1


def test_get_portfolio_daily_snapshots_returns_newest_first_and_respects_limit(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def run_test():
        await db.init_db()

        for date, investment, current, holdings in [
            ("2026-11-08", 90000.0, 95000.0, 2),
            ("2026-11-09", 100000.0, 105000.0, 3),
            ("2026-11-10", 110000.0, 115000.0, 4),
        ]:
            await db.save_portfolio_daily_snapshot(
                12345, date, investment, current, holdings
            )

        return await db.get_portfolio_daily_snapshots(
            12345, limit=2
        )

    snapshots = asyncio.run(run_test())

    assert len(snapshots) == 2
    assert snapshots[0]["snapshot_date"] == "2026-11-10"
    assert snapshots[1]["snapshot_date"] == "2026-11-09"


def test_get_portfolio_daily_snapshots_rejects_invalid_limit():
    async def run_test():
        return await db.get_portfolio_daily_snapshots(
            12345, limit=0
        )

    with pytest.raises(ValueError, match="limit must be at least 1"):
        asyncio.run(run_test())


@pytest.mark.parametrize(
    "investment,current",
    [
        (-1.0, 100.0),
        (100.0, -1.0),
        (float("nan"), 100.0),
        (100.0, float("nan")),
        (float("inf"), 100.0),
        (100.0, float("inf")),
    ],
)
def test_save_portfolio_daily_snapshot_rejects_invalid_values(
    investment,
    current,
):
    async def run_test():
        await db.save_portfolio_daily_snapshot(
            12345,
            "2026-11-12",
            investment,
            current,
            2,
        )

    with pytest.raises(ValueError):
        asyncio.run(run_test())


@pytest.mark.parametrize("holdings_count", [-1, 1.5, True])
def test_save_portfolio_daily_snapshot_rejects_invalid_holdings_count(
    holdings_count,
):
    async def run_test():
        await db.save_portfolio_daily_snapshot(
            12345,
            "2026-11-12",
            100000.0,
            105000.0,
            holdings_count,
        )

    with pytest.raises(ValueError, match="holdings_count"):
        asyncio.run(run_test())


def test_get_daily_price_history_returns_latest_daily_snapshots_oldest_first(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test_nepse.db"
    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def run_test():
        await db.init_db()
        snapshots = [
            ("2026-11-09T12:00:00+05:45", 530.0),
            ("2026-11-09T15:00:00+05:45", 540.0),
            ("2026-11-10T15:00:00+05:45", 549.0),
        ]
        for timestamp, price in snapshots:
            await db.save_price_snapshot({
                "symbol": "NABIL",
                "ltp": price,
                "volume": 1000,
                "turnover": price * 1000,
                "last_updated": timestamp,
                "source": "test",
            })
        return await db.get_daily_price_history(" nabil ")

    history = asyncio.run(run_test())

    assert history == [
        {"trading_date": "2026-11-09", "ltp": 540.0},
        {"trading_date": "2026-11-10", "ltp": 549.0},
    ]


def test_get_daily_price_history_respects_limit(tmp_path, monkeypatch):
    database_path = tmp_path / "test_nepse.db"
    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def run_test():
        await db.init_db()
        for date, price in [
            ("2026-11-08T15:00:00+05:45", 520.0),
            ("2026-11-09T15:00:00+05:45", 530.0),
            ("2026-11-10T15:00:00+05:45", 540.0),
        ]:
            await db.save_price_snapshot({
                "symbol": "NABIL",
                "ltp": price,
                "volume": 1000,
                "turnover": price * 1000,
                "last_updated": date,
                "source": "test",
            })
        return await db.get_daily_price_history("NABIL", limit=2)

    history = asyncio.run(run_test())

    assert history == [
        {"trading_date": "2026-11-09", "ltp": 530.0},
        {"trading_date": "2026-11-10", "ltp": 540.0},
    ]


@pytest.mark.parametrize("symbol", ["", "   ", None])
def test_get_daily_price_history_rejects_invalid_symbol(symbol):
    with pytest.raises(ValueError, match="symbol"):
        asyncio.run(db.get_daily_price_history(symbol))


@pytest.mark.parametrize("limit", [0, -1, 1.5, True, "10"])
def test_get_daily_price_history_rejects_invalid_limit(limit):
    with pytest.raises(ValueError, match="limit"):
        asyncio.run(db.get_daily_price_history("NABIL", limit=limit))
