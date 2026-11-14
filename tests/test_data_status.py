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


def test_data_status_reports_fresh_data(monkeypatch):
    monkeypatch.setattr(
        handlers,
        "fetch_market_data",
        AsyncMock(return_value=[make_stock(stale=False)]),
    )

    update = make_update()
    asyncio.run(handlers.data_status_command(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "Status: ✅ FRESH" in response
    assert "Valid stock records: 1" in response
    assert "10 minutes" in response
    assert "Educational analysis only" in response


def test_data_status_reports_stale_data(monkeypatch):
    monkeypatch.setattr(
        handlers,
        "fetch_market_data",
        AsyncMock(return_value=[make_stock(stale=True)]),
    )

    update = make_update()
    asyncio.run(handlers.data_status_command(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "Status: ⚠️ STALE" in response
    assert "Data age: 77 hours, 36 minutes" in response
    assert "Do not treat these prices as live" in response
    assert "Educational analysis only" in response


def test_data_status_reports_provider_failure(monkeypatch):
    monkeypatch.setattr(
        handlers,
        "fetch_market_data",
        AsyncMock(
            side_effect=MarketDataError("Feed unavailable")
        ),
    )

    update = make_update()
    asyncio.run(handlers.data_status_command(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "Unavailable or invalid data" in response
    assert "Feed unavailable" in response
    assert "Educational analysis only" in response

def test_data_status_reports_fresh_and_stale_counts(monkeypatch):
    fresh = make_stock(stale=False)
    stale = make_stock(stale=True)
    stale["symbol"] = "NABILP"

    monkeypatch.setattr(
        handlers,
        "fetch_market_data",
        AsyncMock(return_value=[fresh, stale]),
    )

    update = make_update()
    asyncio.run(handlers.data_status_command(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "Fresh stock records: 1" in response
    assert "Stale stock records: 1" in response
    assert "Stale data percentage: 50.0%" in response
    assert "Status: ⚠️ PARTIALLY STALE" in response
    assert "Do not treat the entire feed as live" in response


def test_data_status_reports_empty_feed(monkeypatch):
    monkeypatch.setattr(
        handlers,
        "fetch_market_data",
        AsyncMock(return_value=[]),
    )

    update = make_update()
    asyncio.run(handlers.data_status_command(update, None))

    response = update.message.reply_text.await_args.args[0]

    assert "No stock records returned" in response
    assert "Educational analysis only" in response

