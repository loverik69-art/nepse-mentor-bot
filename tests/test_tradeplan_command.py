import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers as handlers


def make_update():
    message = SimpleNamespace(reply_text=AsyncMock())
    user = SimpleNamespace(id=12345)
    return SimpleNamespace(message=message, effective_user=user)


def sample_trade_plan():
    return {
        "status": "AVAILABLE",
        "symbol": "NABIL",
        "trading_style": "Swing",
        "risk_tolerance": "Medium",
        "current_price": 120.00,
        "lookback_observations": 30,
        "buying_range": {"low": 110.00, "high": 115.00},
        "entry_reference": 113.00,
        "selling_range": {"low": 130.00, "high": 140.00},
        "target_1": 130.00,
        "target_2": 140.00,
        "stop_loss": 105.00,
        "risk_reward": {"target_1": 1.5, "target_2": 2.0},
        "risk_budget_npr": 20000.00,
        "suggested_quantity": 100,
        "estimated_investment_npr": 11300.00,
        "estimated_max_loss_npr": 800.00,
        "methodology": "Historical price-cluster analysis.",
    }


def test_tradeplan_command_displays_plan(monkeypatch):
    mock_plan = AsyncMock(return_value=sample_trade_plan())
    monkeypatch.setattr(handlers, "get_trade_plan", mock_plan)

    update = make_update()
    context = SimpleNamespace(args=["nabil"])

    asyncio.run(handlers.tradeplan_command(update, context))

    mock_plan.assert_awaited_once_with("NABIL", 12345)
    response = update.message.reply_text.await_args.args[0]

    assert "Trade Plan — NABIL" in response
    assert "Trading style: Swing" in response
    assert "Risk tolerance: Medium" in response
    assert "Buying range: NPR 110.00 – 115.00" in response
    assert "Selling range: NPR 130.00 – 140.00" in response
    assert "Target 1: NPR 130.00" in response
    assert "Target 2: NPR 140.00" in response
    assert "Stop loss: NPR 105.00" in response
    assert "Suggested quantity: 100 shares" in response
    assert "not financial advice" in response


def test_tradeplan_command_requires_one_symbol():
    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.tradeplan_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Usage: /tradeplan SYMBOL" in response


def test_tradeplan_command_rejects_invalid_symbol(monkeypatch):
    mock_plan = AsyncMock()
    monkeypatch.setattr(handlers, "get_trade_plan", mock_plan)

    update = make_update()
    context = SimpleNamespace(args=["NABIL!"])

    asyncio.run(handlers.tradeplan_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Invalid stock symbol" in response
    mock_plan.assert_not_awaited()


def test_tradeplan_command_displays_unavailable_plan(monkeypatch):
    mock_plan = AsyncMock(return_value={
        "status": "UNAVAILABLE",
        "symbol": "NABIL",
        "reason": "Market data is stale.",
    })
    monkeypatch.setattr(handlers, "get_trade_plan", mock_plan)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.tradeplan_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Plan unavailable" in response
    assert "Market data is stale." in response


def test_tradeplan_command_handles_value_error(monkeypatch):
    mock_plan = AsyncMock(side_effect=ValueError("Invalid user profile"))
    monkeypatch.setattr(handlers, "get_trade_plan", mock_plan)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.tradeplan_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Invalid user profile" in response


def test_tradeplan_command_handles_service_error(monkeypatch):
    mock_plan = AsyncMock(side_effect=RuntimeError("Test error"))
    monkeypatch.setattr(handlers, "get_trade_plan", mock_plan)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.tradeplan_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Unable to generate a trade plan" in response
