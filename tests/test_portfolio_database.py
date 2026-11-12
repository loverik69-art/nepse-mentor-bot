import asyncio
from types import SimpleNamespace

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
