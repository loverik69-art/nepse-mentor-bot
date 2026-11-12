
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers as handlers


def make_update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message)


def test_indicators_show_all_calculated_values(monkeypatch):
    async def fake_analysis(symbol):
        return {
            "symbol": symbol,
            "observations": 60,
            "indicators": {
                "sma_20": 500.0,
                "sma_50": 480.0,
                "ema_20": 510.0,
                "ema_50": 490.0,
                "rsi_14": 62.5,
                "macd": {
                    "macd": 12.5,
                    "signal": 10.0,
                    "histogram": 2.5,
                },
            },
        }

    monkeypatch.setattr(
        handlers, "get_technical_analysis", fake_analysis
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.indicators_command(update, context)
    )

    update.message.reply_text.assert_awaited_once()
    response = update.message.reply_text.await_args.args[0]

    assert "Technical Indicators — NABIL" in response
    assert "Daily observations: 60" in response
    assert "SMA 20: 500.00" in response
    assert "SMA 50: 480.00" in response
    assert "EMA 20: 510.00" in response
    assert "EMA 50: 490.00" in response
    assert "RSI 14: 62.50" in response
    assert "MACD: 12.50" in response
    assert "Signal: 10.00" in response
    assert "Histogram: 2.50" in response
    assert "not verified" in response


def test_indicators_handle_insufficient_history(monkeypatch):
    async def fake_analysis(symbol):
        return {
            "symbol": symbol,
            "observations": 5,
            "indicators": {
                "sma_20": None,
                "sma_50": None,
                "ema_20": None,
                "ema_50": None,
                "rsi_14": None,
                "macd": None,
            },
        }

    monkeypatch.setattr(
        handlers, "get_technical_analysis", fake_analysis
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.indicators_command(update, context)
    )

    update.message.reply_text.assert_awaited_once()
    response = update.message.reply_text.await_args.args[0]

    assert "Insufficient history" in response
    assert "Daily observations: 5" in response


def test_indicators_require_symbol():
    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(
        handlers.indicators_command(update, context)
    )

    update.message.reply_text.assert_awaited_once()
    response = update.message.reply_text.await_args.args[0]

    assert "Usage: /indicators SYMBOL" in response


def test_indicators_reject_invalid_symbol():
    update = make_update()
    context = SimpleNamespace(args=["NABIL!"])

    asyncio.run(
        handlers.indicators_command(update, context)
    )

    update.message.reply_text.assert_awaited_once()
    response = update.message.reply_text.await_args.args[0]

    assert "Invalid stock symbol" in response


def test_indicators_handle_service_error(monkeypatch):
    async def fake_analysis(symbol):
        raise RuntimeError("Test error")

    monkeypatch.setattr(
        handlers, "get_technical_analysis", fake_analysis
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.indicators_command(update, context)
    )

    update.message.reply_text.assert_awaited_once()
    response = update.message.reply_text.await_args.args[0]

    assert "Unable to calculate technical indicators" in response
