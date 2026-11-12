import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers as handlers


def make_stock(is_stale):
    return {
        "symbol": "NABIL",
        "name": "Nabil Bank Limited",
        "ltp": 549.0,
        "previous_close": 550.0,
        "change": -1.0,
        "percent_change": -0.18,
        "high": 555.0,
        "low": 545.0,
        "volume": 1000,
        "turnover": 549000.0,
        "trades": 50,
        "last_updated": "2026-11-09T14:59:00+05:45",
        "age_minutes": 30,
        "is_stale": is_stale,
        "source": "YONEPSE",
    }


def make_update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message)


def test_stock_command_warns_when_data_is_stale(monkeypatch):
    async def fake_get_stock(symbol):
        return make_stock(True)

    monkeypatch.setattr(handlers, "get_stock", fake_get_stock)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.stock_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "STALE DATA" in response
    assert "do not treat this as a current market quote" in response
    assert "YONEPSE" in response
    assert "Educational analysis only" in response


def test_stock_command_reports_freshness_when_data_is_not_stale(monkeypatch):
    async def fake_get_stock(symbol):
        return make_stock(False)

    monkeypatch.setattr(handlers, "get_stock", fake_get_stock)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.stock_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "within the 24-hour freshness threshold" in response
    assert "STALE DATA" not in response
    assert "Educational analysis only" in response

def test_stock_command_shows_stale_warning_before_price(monkeypatch):
    async def fake_get_stock(symbol):
        return make_stock(True)

    monkeypatch.setattr(handlers, "get_stock", fake_get_stock)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.stock_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    warning_position = response.index("STALE DATA")
    price_position = response.index("Last traded price:")

    assert warning_position < price_position

def test_stock_command_missing_symbol_includes_disclaimer():
    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.stock_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Usage: /stock SYMBOL" in response
    assert "Educational analysis only" in response


def test_stock_command_invalid_symbol_includes_disclaimer():
    update = make_update()
    context = SimpleNamespace(args=["NABIL!"])

    asyncio.run(handlers.stock_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Invalid stock symbol" in response
    assert "Educational analysis only" in response


def test_stock_command_market_data_error_includes_disclaimer(monkeypatch):
    async def fake_get_stock(symbol):
        raise handlers.MarketDataError("Feed unavailable")

    monkeypatch.setattr(handlers, "get_stock", fake_get_stock)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.stock_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Market data unavailable" in response
    assert "Educational analysis only" in response


def test_stock_command_unexpected_error_includes_disclaimer(monkeypatch):
    async def fake_get_stock(symbol):
        raise RuntimeError("Unexpected failure")

    monkeypatch.setattr(handlers, "get_stock", fake_get_stock)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.stock_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Something went wrong" in response
    assert "Educational analysis only" in response


def test_stock_command_unknown_symbol_includes_disclaimer(monkeypatch):
    async def fake_get_stock(symbol):
        return None

    monkeypatch.setattr(handlers, "get_stock", fake_get_stock)

    update = make_update()
    context = SimpleNamespace(args=["UNKNOWN"])

    asyncio.run(handlers.stock_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "was not found" in response
    assert "Educational analysis only" in response

def test_history_command_displays_stored_records(monkeypatch):
    async def fake_get_price_history(symbol, limit=10):
        assert symbol == "NABIL"
        return [
            {
                "symbol": "NABIL",
                "ltp": 550.0,
                "volume": 1200,
                "turnover": 660000.0,
                "source_updated_at": "2026-11-10T14:59:00+05:45",
            },
            {
                "symbol": "NABIL",
                "ltp": 549.0,
                "volume": 1000,
                "turnover": 549000.0,
                "source_updated_at": "2026-11-09T14:59:00+05:45",
            },
        ]

    monkeypatch.setattr(
        handlers,
        "get_price_history",
        fake_get_price_history,
        raising=False,
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.history_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "NABIL" in response
    assert "550.00" in response
    assert "549.00" in response
    assert "2026-11-10" in response


def test_history_command_handles_empty_history(monkeypatch):
    async def fake_get_price_history(symbol, limit=10):
        return []

    monkeypatch.setattr(
        handlers,
        "get_price_history",
        fake_get_price_history,
        raising=False,
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.history_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "No historical data" in response


def test_history_command_rejects_invalid_symbol():
    update = make_update()
    context = SimpleNamespace(args=["NABIL!"])

    asyncio.run(handlers.history_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "Invalid stock symbol" in response

