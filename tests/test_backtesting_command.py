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
            horizon: {
                "trades": 30,
                "wins": 18,
                "losses": 12,
                "win_rate_pct": 60.0,
                "average_return_pct": 2.35,
                "buy_trades": 20,
                "sell_trades": 10,
                "buy_execution": {
                    "trades": 20,
                    "wins": 12,
                    "losses": 8,
                    "win_rate_pct": 60.0,
                    "average_return_pct": 1.5,
                    "average_gross_return_pct": 2.35,
                    "total_gross_profit": 40000.0,
                    "total_net_profit": 25000.0,
                    "total_fees": 5000.0,
                    "total_slippage_cost": 2000.0,
                    "investment_budget": 100000,
                    "slippage_pct_per_side": 0.1,
                    "skipped_budget": 2,
                },
                "sell_signal": {
                    "trades": 10,
                    "wins": 5,
                    "losses": 5,
                    "win_rate_pct": 50.0,
                    "average_return_pct": 0.4,
                },
            }
            for horizon in (5, 10, 20)
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
    assert "Skipped (budget insufficient): 2" in response
    assert "Net win rate: 60.00%" in response
    assert "Average net return: +1.50%" in response
    assert "Average gross return: +2.35%" in response
    assert "Total net profit: NPR 25000.00" in response
    assert "Total fees: NPR 5000.00" in response
    assert "Estimated slippage: NPR 2000.00" in response
    assert "SELL signal diagnostic (not short selling)" in response
    assert "Directional win rate: 50.00%" in response
    assert "Combined directional diagnostic (not strategy win rate)" in response
    assert "NPR 100,000 per independent trade" in response
    assert "0.1% per side" in response
    assert "Fees and slippage: Excluded" not in response
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
