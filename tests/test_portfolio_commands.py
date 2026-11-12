import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers as handlers


def make_update(args=None):
    message = SimpleNamespace(reply_text=AsyncMock())
    user = SimpleNamespace(id=1001)

    return (
        SimpleNamespace(message=message, effective_user=user),
        SimpleNamespace(args=args or []),
    )


def test_addstock_command_saves_holding(monkeypatch):
    save = AsyncMock()
    monkeypatch.setattr(handlers, "add_portfolio_holding", save)

    update, context = make_update(["nabil", "10", "500"])

    asyncio.run(handlers.addstock_command(update, context))

    save.assert_awaited_once_with(1001, "NABIL", 10.0, 500.0)

    response = update.message.reply_text.await_args.args[0]
    assert "Portfolio holding saved" in response
    assert "NABIL" in response
    assert "5,000.00" in response


def test_addstock_command_rejects_invalid_quantity(monkeypatch):
    save = AsyncMock()
    monkeypatch.setattr(handlers, "add_portfolio_holding", save)

    update, context = make_update(["NABIL", "0", "500"])

    asyncio.run(handlers.addstock_command(update, context))

    save.assert_not_awaited()

    response = update.message.reply_text.await_args.args[0]
    assert "positive numbers" in response


def test_addstock_command_rejects_non_finite_values(monkeypatch):
    save = AsyncMock()
    monkeypatch.setattr(handlers, "add_portfolio_holding", save)

    update, context = make_update(["NABIL", "nan", "500"])

    asyncio.run(handlers.addstock_command(update, context))

    save.assert_not_awaited()

    response = update.message.reply_text.await_args.args[0]
    assert "positive numbers" in response


def test_portfolio_command_reports_empty_portfolio(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return []

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)

    update, context = make_update()

    asyncio.run(handlers.portfolio_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "portfolio is empty" in response
    assert "/addstock" in response


def test_portfolio_command_calculates_profit(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return [
            {
                "symbol": "NABIL",
                "quantity": 10,
                "average_buy_price": 500,
            }
        ]

    async def fake_get_price_history(symbol, limit=1):
        assert symbol == "NABIL"
        return [{"ltp": 550}]

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(handlers, "get_price_history", fake_get_price_history)

    update, context = make_update()

    asyncio.run(handlers.portfolio_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "NABIL" in response
    assert "Current value: NPR 5,500.00" in response
    assert "Portfolio P/L: NPR +500.00 (+10.00%)" in response
    assert "not verified live quotes" in response


def test_portfolio_command_handles_missing_price_history(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return [
            {
                "symbol": "NABIL",
                "quantity": 10,
                "average_buy_price": 500,
            }
        ]

    async def fake_get_price_history(symbol, limit=1):
        return []

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(handlers, "get_price_history", fake_get_price_history)

    update, context = make_update()

    asyncio.run(handlers.portfolio_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Latest LTP: Unavailable" in response
    assert "Total investment: NPR 5,000.00" in response


def test_removestock_command_removes_holding(monkeypatch):
    remove = AsyncMock(return_value=True)
    monkeypatch.setattr(handlers, "remove_portfolio_holding", remove)

    update, context = make_update(["nabil"])

    asyncio.run(handlers.removestock_command(update, context))

    remove.assert_awaited_once_with(1001, "NABIL")

    response = update.message.reply_text.await_args.args[0]
    assert "NABIL removed from your portfolio" in response


def test_removestock_command_reports_missing_holding(monkeypatch):
    remove = AsyncMock(return_value=False)
    monkeypatch.setattr(handlers, "remove_portfolio_holding", remove)

    update, context = make_update(["NABIL"])

    asyncio.run(handlers.removestock_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "NABIL was not found" in response


def test_allocation_command_calculates_percentages(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return [
            {"symbol": "NABIL", "quantity": 10, "average_buy_price": 500},
            {"symbol": "NICA", "quantity": 10, "average_buy_price": 500},
        ]

    async def fake_get_price_history(symbol, limit=1):
        prices = {"NABIL": 600, "NICA": 400}
        return [{"ltp": prices[symbol]}]

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(handlers, "get_price_history", fake_get_price_history)

    update, context = make_update()

    asyncio.run(handlers.allocation_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "NABIL" in response
    assert "NICA" in response
    assert "60.00%" in response
    assert "40.00%" in response
    assert response.index("NABIL") < response.index("NICA")


def test_allocation_command_reports_empty_portfolio(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return []

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)

    update, context = make_update()

    asyncio.run(handlers.allocation_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "portfolio is empty" in response


def test_allocation_command_handles_unavailable_prices(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return [
            {"symbol": "NABIL", "quantity": 10, "average_buy_price": 500}
        ]

    async def fake_get_price_history(symbol, limit=1):
        return []

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(handlers, "get_price_history", fake_get_price_history)

    update, context = make_update()

    asyncio.run(handlers.allocation_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "No usable historical prices" in response


def test_diversification_command_warns_about_concentration(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return [
            {"symbol": "NABIL", "quantity": 10, "average_buy_price": 500},
            {"symbol": "NICA", "quantity": 2, "average_buy_price": 500},
        ]

    async def fake_get_price_history(symbol, limit=1):
        prices = {"NABIL": 600, "NICA": 500}
        return [{"ltp": prices[symbol]}]

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(handlers, "get_price_history", fake_get_price_history)

    update, context = make_update()

    asyncio.run(handlers.diversification_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "Largest holding: NABIL" in response
    assert "High concentration" in response
    assert "more than 50%" in response


def test_diversification_command_handles_no_prices(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return [
            {"symbol": "NABIL", "quantity": 10, "average_buy_price": 500}
        ]

    async def fake_get_price_history(symbol, limit=1):
        return []

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(handlers, "get_price_history", fake_get_price_history)

    update, context = make_update()

    asyncio.run(handlers.diversification_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "No usable historical prices" in response


def test_performance_command_calculates_and_saves_snapshot(monkeypatch):
    from datetime import datetime

    async def fake_get_portfolio(telegram_id):
        return [
            {"symbol": "NABIL", "quantity": 10, "average_buy_price": 500}
        ]

    async def fake_get_price_history(symbol, limit=1):
        return [{"ltp": 550}]

    async def fake_get_snapshots(telegram_id, limit=30):
        return []

    save_snapshot = AsyncMock()

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 12, 12, 0, tzinfo=tz)

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(handlers, "get_price_history", fake_get_price_history)
    monkeypatch.setattr(
        handlers, "get_portfolio_daily_snapshots", fake_get_snapshots
    )
    monkeypatch.setattr(
        handlers, "save_portfolio_daily_snapshot", save_snapshot
    )
    monkeypatch.setattr(handlers, "datetime", FixedDateTime)

    update, context = make_update()

    asyncio.run(handlers.performance_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "Portfolio P/L: NPR +500.00 (+10.00%)" in response
    assert "First daily snapshot saved" in response
    save_snapshot.assert_awaited_once_with(
        1001, "2026-11-12", 5000.0, 5500.0, 1
    )


def test_performance_command_compares_previous_snapshot(monkeypatch):
    from datetime import datetime

    async def fake_get_portfolio(telegram_id):
        return [
            {"symbol": "NABIL", "quantity": 10, "average_buy_price": 500}
        ]

    async def fake_get_price_history(symbol, limit=1):
        return [{"ltp": 550}]

    async def fake_get_snapshots(telegram_id, limit=30):
        return [
            {
                "snapshot_date": "2026-11-11",
                "current_value": 5000.0,
            }
        ]

    save_snapshot = AsyncMock()

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 12, 12, 0, tzinfo=tz)

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(handlers, "get_price_history", fake_get_price_history)
    monkeypatch.setattr(
        handlers, "get_portfolio_daily_snapshots", fake_get_snapshots
    )
    monkeypatch.setattr(
        handlers, "save_portfolio_daily_snapshot", save_snapshot
    )
    monkeypatch.setattr(handlers, "datetime", FixedDateTime)

    update, context = make_update()

    asyncio.run(handlers.performance_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "Change since 2026-11-11" in response
    assert "NPR +500.00 (+10.00%)" in response
    save_snapshot.assert_awaited_once()


def test_performance_command_reports_empty_portfolio(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return []

    save_snapshot = AsyncMock()

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(
        handlers, "save_portfolio_daily_snapshot", save_snapshot
    )

    update, context = make_update()

    asyncio.run(handlers.performance_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "Your portfolio is empty" in response
    save_snapshot.assert_not_awaited()


def test_performance_command_handles_unavailable_prices(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return [
            {"symbol": "NABIL", "quantity": 10, "average_buy_price": 500}
        ]

    async def fake_get_price_history(symbol, limit=1):
        return []

    save_snapshot = AsyncMock()

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(handlers, "get_price_history", fake_get_price_history)
    monkeypatch.setattr(
        handlers, "save_portfolio_daily_snapshot", save_snapshot
    )

    update, context = make_update()

    asyncio.run(handlers.performance_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "No usable historical prices" in response
    save_snapshot.assert_not_awaited()


def test_performance_command_handles_portfolio_database_error(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)

    update, context = make_update()

    asyncio.run(handlers.performance_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "Unable to calculate portfolio performance" in response


def test_performance_command_handles_snapshot_save_error(monkeypatch):
    async def fake_get_portfolio(telegram_id):
        return [
            {"symbol": "NABIL", "quantity": 10, "average_buy_price": 500}
        ]

    async def fake_get_price_history(symbol, limit=1):
        return [{"ltp": 550}]

    async def fake_get_snapshots(telegram_id, limit=30):
        return []

    save_snapshot = AsyncMock(
        side_effect=RuntimeError("Snapshot database error")
    )

    monkeypatch.setattr(handlers, "get_portfolio", fake_get_portfolio)
    monkeypatch.setattr(handlers, "get_price_history", fake_get_price_history)
    monkeypatch.setattr(
        handlers, "get_portfolio_daily_snapshots", fake_get_snapshots
    )
    monkeypatch.setattr(
        handlers, "save_portfolio_daily_snapshot", save_snapshot
    )

    update, context = make_update()

    asyncio.run(handlers.performance_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "Unable to calculate portfolio performance" in response
    save_snapshot.assert_awaited_once()
