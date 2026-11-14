import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers as handlers


def make_update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message)


def sample_signal(signal="BUY"):
    return {
        "symbol": "NABIL",
        "signal": signal,
        "score": 3 if signal == "BUY" else 0,
        "strength": "Strong" if signal == "BUY" else "Unavailable",
        "ltp": 550.0,
        "last_updated": "2026-11-13T14:59:00+05:45",
        "age_minutes": 5,
        "observations": 60,
        "reasons": ["Bullish: SMA 20 vs SMA 50"],
    }


def test_signal_command_displays_buy_signal(monkeypatch):
    async def fake_signal(symbol):
        assert symbol == "NABIL"
        return sample_signal()

    monkeypatch.setattr(handlers, "get_stock_signal", fake_signal)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.signal_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "Trading Signal — NABIL" in response
    assert "BUY" in response
    assert "Score: +3/3" in response
    assert "Strength: Strong" in response
    assert "NPR 550.00" in response
    assert "Daily observations: 60" in response
    assert "Bullish:" in response
    assert "not financial advice" in response


def test_signal_command_requires_one_symbol():
    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.signal_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Usage: /signal SYMBOL" in response


def test_signal_command_rejects_invalid_symbol():
    update = make_update()
    context = SimpleNamespace(args=["NABIL!"])

    asyncio.run(handlers.signal_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Invalid stock symbol" in response


def test_signal_command_displays_stale_data(monkeypatch):
    async def fake_signal(symbol):
        result = sample_signal("STALE_DATA")
        result["reasons"] = ["Latest market data is stale."]
        result["age_minutes"] = 4000
        return result

    monkeypatch.setattr(handlers, "get_stock_signal", fake_signal)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.signal_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "STALE DATA" in response
    assert "NO ACTIONABLE SIGNAL" in response


def test_signal_command_handles_service_error(monkeypatch):
    async def fake_signal(symbol):
        raise RuntimeError("Test error")

    monkeypatch.setattr(handlers, "get_stock_signal", fake_signal)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.signal_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Unable to generate a trading signal" in response
