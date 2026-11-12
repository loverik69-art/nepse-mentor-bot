import asyncio
from types import SimpleNamespace
import aiosqlite

import pytest

import database.db as db


@pytest.fixture
def portfolio_db(tmp_path, monkeypatch):
    database_path = tmp_path / "test_portfolio.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    asyncio.run(db.init_db())

    return database_path


def test_add_portfolio_holding(portfolio_db):
    async def run_test():
        await db.add_portfolio_holding(
            1001, "NABIL", 10, 500
        )
        return await db.get_portfolio(1001)

    holdings = asyncio.run(run_test())

    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "NABIL"
    assert holdings[0]["quantity"] == 10
    assert holdings[0]["average_buy_price"] == 500


def test_add_portfolio_holding_normalizes_symbol(portfolio_db):
    async def run_test():
        await db.add_portfolio_holding(
            1001, " nabil ", 5, 600
        )
        return await db.get_portfolio(1001)

    holdings = asyncio.run(run_test())

    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "NABIL"


def test_add_existing_holding_replaces_values(portfolio_db):
    async def run_test():
        await db.add_portfolio_holding(
            1001, "NABIL", 10, 500
        )

        await db.add_portfolio_holding(
            1001, "NABIL", 5, 600
        )

        return await db.get_portfolio(1001)

    holdings = asyncio.run(run_test())

    assert len(holdings) == 1
    assert holdings[0]["quantity"] == 5
    assert holdings[0]["average_buy_price"] == 600


def test_portfolios_are_isolated_between_users(portfolio_db):
    async def run_test():
        await db.add_portfolio_holding(
            1001, "NABIL", 10, 500
        )

        await db.add_portfolio_holding(
            1002, "NABIL", 20, 600
        )

        return (
            await db.get_portfolio(1001),
            await db.get_portfolio(1002),
        )

    user_one, user_two = asyncio.run(run_test())

    assert user_one[0]["quantity"] == 10
    assert user_two[0]["quantity"] == 20
    assert user_one[0]["average_buy_price"] == 500
    assert user_two[0]["average_buy_price"] == 600


def test_get_portfolio_returns_empty_for_unknown_user(portfolio_db):
    holdings = asyncio.run(db.get_portfolio(9999))

    assert holdings == []


def test_remove_portfolio_holding(portfolio_db):
    async def run_test():
        await db.add_portfolio_holding(
            1001, "NABIL", 10, 500
        )

        removed = await db.remove_portfolio_holding(
            1001, "NABIL"
        )

        remaining = await db.get_portfolio(1001)

        return removed, remaining

    removed, remaining = asyncio.run(run_test())

    assert removed is True
    assert remaining == []


def test_remove_nonexistent_holding_returns_false(portfolio_db):
    removed = asyncio.run(
        db.remove_portfolio_holding(1001, "NABIL")
    )

    assert removed is False


def test_remove_holding_does_not_affect_another_user(portfolio_db):
    async def run_test():
        await db.add_portfolio_holding(
            1001, "NABIL", 10, 500
        )

        await db.add_portfolio_holding(
            1002, "NABIL", 20, 600
        )

        removed = await db.remove_portfolio_holding(
            1001, "NABIL"
        )

        remaining = await db.get_portfolio(1002)

        return removed, remaining

    removed, remaining = asyncio.run(run_test())

    assert removed is True
    assert len(remaining) == 1
    assert remaining[0]["quantity"] == 20


@pytest.mark.parametrize("symbol", ["", "   ", None, 123])
def test_add_portfolio_holding_rejects_invalid_symbol(
    portfolio_db,
    symbol,
):
    with pytest.raises(ValueError, match="symbol"):
        asyncio.run(
            db.add_portfolio_holding(1001, symbol, 10, 500)
        )


@pytest.mark.parametrize(
    "quantity",
    [0, -1, float("nan"), float("inf"), True, "10"],
)
def test_add_portfolio_holding_rejects_invalid_quantity(
    portfolio_db,
    quantity,
):
    with pytest.raises(ValueError, match="quantity"):
        asyncio.run(
            db.add_portfolio_holding(1001, "NABIL", quantity, 500)
        )


@pytest.mark.parametrize(
    "average_buy_price",
    [0, -1, float("nan"), float("inf"), True, "500"],
)
def test_add_portfolio_holding_rejects_invalid_average_buy_price(
    portfolio_db,
    average_buy_price,
):
    with pytest.raises(ValueError, match="average_buy_price"):
        asyncio.run(
            db.add_portfolio_holding(
                1001, "NABIL", 10, average_buy_price
            )
        )


def test_buy_transaction_creates_holding_with_fees(portfolio_db):
    async def run_test():
        await db.record_portfolio_transaction(
            telegram_id=1001,
            symbol="NABIL",
            transaction_type="buy",
            quantity=10,
            price=500,
            fees=100,
        )
        return await db.get_portfolio(1001)

    holdings = asyncio.run(run_test())

    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "NABIL"
    assert holdings[0]["quantity"] == 10
    assert holdings[0]["average_buy_price"] == 510


def test_additional_buy_uses_weighted_average(portfolio_db):
    async def run_test():
        await db.record_portfolio_transaction(1001, "NABIL", "buy", 10, 500, 100)
        await db.record_portfolio_transaction(1001, "NABIL", "buy", 10, 600, 0)
        return await db.get_portfolio(1001)

    holdings = asyncio.run(run_test())

    assert len(holdings) == 1
    assert holdings[0]["quantity"] == 20
    assert holdings[0]["average_buy_price"] == 555


def test_sell_calculates_realized_profit_loss(portfolio_db):
    async def run_test():
        await db.record_portfolio_transaction(1001, "NABIL", "buy", 10, 500, 100)
        result = await db.record_portfolio_transaction(1001, "NABIL", "sell", 4, 600, 40)
        holdings = await db.get_portfolio(1001)
        return result, holdings

    result, holdings = asyncio.run(run_test())

    assert result["realized_profit_loss"] == 320
    assert len(holdings) == 1
    assert holdings[0]["quantity"] == 6
    assert holdings[0]["average_buy_price"] == 510


def test_sell_rejects_quantity_above_holding(portfolio_db):
    async def run_test():
        await db.record_portfolio_transaction(1001, "NABIL", "buy", 5, 500)

        with pytest.raises(ValueError, match="cannot sell more"):
            await db.record_portfolio_transaction(1001, "NABIL", "sell", 6, 600)

        holdings = await db.get_portfolio(1001)
        async with aiosqlite.connect(portfolio_db) as connection:
            cursor = await connection.execute(
                "SELECT COUNT(*) FROM portfolio_transactions"
            )
            transaction_count = (await cursor.fetchone())[0]

        return holdings, transaction_count

    holdings, transaction_count = asyncio.run(run_test())

    assert holdings[0]["quantity"] == 5
    assert transaction_count == 1


def test_transaction_history_is_isolated_and_newest_first(portfolio_db):
    async def run_test():
        await db.record_portfolio_transaction(1001, "NABIL", "buy", 5, 500)
        await db.record_portfolio_transaction(1001, "NABIL", "buy", 2, 550)
        await db.record_portfolio_transaction(2002, "NICA", "buy", 3, 700)

        history = await db.get_portfolio_transactions(1001)
        limited = await db.get_portfolio_transactions(1001, limit=1)
        other_user = await db.get_portfolio_transactions(2002)

        return history, limited, other_user

    history, limited, other_user = asyncio.run(run_test())

    assert len(history) == 2
    assert history[0]["quantity"] == 2
    assert history[1]["quantity"] == 5
    assert len(limited) == 1
    assert len(other_user) == 1
    assert other_user[0]["symbol"] == "NICA"


def test_automatic_buy_fee_calculation():
    fees = db.calculate_equity_transaction_fees(10, 500, "buy")

    assert fees["trade_value"] == 5000
    assert fees["broker_commission"] == 18
    assert fees["sebon_fee"] == 0.75
    assert fees["dp_charge"] == 0
    assert fees["total_fees"] == 18.75


def test_automatic_sell_fee_calculation():
    fees = db.calculate_equity_transaction_fees(4, 600, "sell")

    assert fees["trade_value"] == 2400
    assert fees["broker_commission"] == 10
    assert fees["sebon_fee"] == 0.36
    assert fees["dp_charge"] == 25
    assert fees["total_fees"] == 35.36


def test_automatic_fees_are_included_in_buy_cost(portfolio_db):
    async def run_test():
        result = await db.record_portfolio_transaction(
            1001, "NABIL", "buy", 10, 500
        )
        holdings = await db.get_portfolio(1001)
        return result, holdings

    result, holdings = asyncio.run(run_test())

    assert result["fees"] == 18.75
    assert result["fee_breakdown"]["total_fees"] == 18.75
    assert holdings[0]["average_buy_price"] == 501.875


def test_automatic_fees_reduce_sell_profit(portfolio_db):
    async def run_test():
        await db.record_portfolio_transaction(
            1001, "NABIL", "buy", 10, 500, 100
        )
        result = await db.record_portfolio_transaction(
            1001, "NABIL", "sell", 4, 600
        )
        return result

    result = asyncio.run(run_test())

    assert result["fees"] == 35.36
    assert result["realized_profit_loss"] == pytest.approx(324.64)


def test_transaction_saves_individual_fee_components(portfolio_db):
    async def run_test():
        await db.record_portfolio_transaction(
            1001, "NABIL", "buy", 10, 500, 100
        )
        await db.record_portfolio_transaction(
            1001, "NABIL", "sell", 4, 600
        )

        async with aiosqlite.connect(portfolio_db) as connection:
            cursor = await connection.execute(
                """
                SELECT fees, broker_commission, sebon_fee, dp_charge
                FROM portfolio_transactions
                WHERE telegram_id = ? AND transaction_type = 'sell'
                """,
                (1001,),
            )
            return await cursor.fetchone()

    fees = asyncio.run(run_test())

    assert fees[0] == 35.36
    assert fees[1] == 10.00
    assert fees[2] == 0.36
    assert fees[3] == 25.00
