import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers as handlers


def make_update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message)


def sample_backtest():
    return {
        "symbol": "NABIL",
        "observations": 200,
        "first_date": "2025-01-01",
        "last_date": "2026-11-13",
        "signals": {
            "BUY": 20,
            "SELL": 15,
            "HOLD": 100,
        },
        "results": {
            5: {
                "trades": 30,
                "wins": 18,
                "losses": 12,
                "win_rate_pct": 60.0,
                "average_return_pct": 2.35,
                "buy_trades": 20,
                "sell_trades": 10,
            },
            10: {
                "trades": 25,
                "wins": 14,
                "losses": 11,
                "win_rate_pct": 56.0,
                "average_return_pct": 3.15,
                "buy_trades": 15,
                "sell_trades": 10,
            },
            20: {
                "trades": 18,
                "wins": 10,
                "losses": 8,
                "win_rate_pct": 55.56,
                "average_return_pct": 4.25,
                "buy_trades": 10,
                "sell_trades": 8,
            },
        },
    }


def test_backtest_command_displays_report(monkeypatch):
    async def fake_backtest(symbol):
        assert symbol == "NABIL"
        return sample_backtest()

    monkeypatch.setattr(handlers, "backtest_symbol", fake_backtest)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.backtest_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "Historical Backtest — NABIL" in response
    assert "Daily observations: 200" in response
    assert "BUY: 20" in response
    assert "SELL: 15" in response
    assert "HOLD: 100" in response
    assert "5-observation horizon" in response
    assert "10-observation horizon" in response
    assert "20-observation horizon" in response
    assert "Win rate: 60.00%" in response
    assert "Average directional return: +2.35%" in response
    assert "Fees and slippage: Excluded" in response
    assert "not financial advice" in response


def test_backtest_command_requires_one_symbol():
    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.backtest_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Usage: /backtest SYMBOL" in response


def test_backtest_command_rejects_invalid_symbol():
    update = make_update()
    context = SimpleNamespace(args=["NABIL!"])

    asyncio.run(handlers.backtest_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Invalid stock symbol" in response


def test_backtest_command_displays_insufficient_data(monkeypatch):
    async def fake_backtest(symbol):
        return {
            "symbol": symbol,
            "observations": 30,
            "message": "At least 51 daily observations are required.",
        }

    monkeypatch.setattr(handlers, "backtest_symbol", fake_backtest)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.backtest_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Daily observations: 30" in response
    assert "At least 51 daily observations are required." in response


def test_backtest_command_handles_value_error(monkeypatch):
    async def fake_backtest(symbol):
        raise ValueError("Invalid historical data")

    monkeypatch.setattr(handlers, "backtest_symbol", fake_backtest)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.backtest_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Invalid historical data" in response


def test_backtest_command_handles_service_error(monkeypatch):
    async def fake_backtest(symbol):
        raise RuntimeError("Test error")

    monkeypatch.setattr(handlers, "backtest_symbol", fake_backtest)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.backtest_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Unable to run historical backtesting" in response
