import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers as handlers
from services.nepse_data import MarketDataError


def make_stock(stale=False):
    return {
        "symbol": "NABIL",
        "name": "Nabil Bank Limited",
        "ltp": 549.0,
        "last_updated": "2026-11-06T14:59:56+05:45",
        "age_minutes": 4656 if stale else 10,
        "is_stale": stale,
        "source": "YONEPSE community data feed",
    }


def make_update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message)


def test_health_reports_healthy_database_and_fresh_feed(monkeypatch):
    monkeypatch.setattr(
        handlers, "check_db", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        handlers, "fetch_market_data",
        AsyncMock(return_value=[make_stock(stale=False)])
    )

    update = make_update()
    asyncio.run(handlers.health(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "SQLite database: Connected" in response
    assert "NEPSE feed: Reachable and fresh" in response
    assert "Valid stock records: 1" in response


def test_health_reports_stale_feed(monkeypatch):
    monkeypatch.setattr(
        handlers, "check_db", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        handlers, "fetch_market_data",
        AsyncMock(return_value=[make_stock(stale=True)])
    )

    update = make_update()
    asyncio.run(handlers.health(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "NEPSE feed: Reachable, but stale" in response
    assert "Data age: 4656 minutes" in response


def test_health_reports_provider_failure(monkeypatch):
    monkeypatch.setattr(
        handlers, "check_db", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        handlers, "fetch_market_data",
        AsyncMock(side_effect=MarketDataError("Feed unavailable"))
    )

    update = make_update()
    asyncio.run(handlers.health(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "SQLite database: Connected" in response
    assert "NEPSE feed: Unavailable or invalid" in response


def test_health_reports_database_failure(monkeypatch):
    monkeypatch.setattr(
        handlers, "check_db", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        handlers, "fetch_market_data",
        AsyncMock(return_value=[make_stock(stale=False)])
    )

    update = make_update()
    asyncio.run(handlers.health(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "SQLite database: Failed" in response
    assert "NEPSE feed: Reachable and fresh" in response

def test_health_reports_fresh_and_stale_counts(monkeypatch):
    fresh = make_stock(stale=False)
    stale = make_stock(stale=True)
    stale["symbol"] = "NABILP"

    monkeypatch.setattr(
        handlers,
        "check_db",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        handlers,
        "fetch_market_data",
        AsyncMock(return_value=[fresh, stale]),
    )

    update = make_update()
    asyncio.run(handlers.health(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "Fresh stock records: 1" in response
    assert "Stale stock records: 1" in response
    assert "Stale data percentage: 50.0%" in response



def test_health_reports_empty_market_data(monkeypatch):
    monkeypatch.setattr(
        handlers, "check_db", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        handlers, "fetch_market_data",
        AsyncMock(return_value=[])
    )

    update = make_update()
    asyncio.run(handlers.health(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "NEPSE feed: No stock records returned" in response
    assert "Valid stock records: 0" in response
