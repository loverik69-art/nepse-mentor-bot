import asyncio
from types import SimpleNamespace

import pytest
import database.db as db


@pytest.fixture
def watchlist_db(tmp_path, monkeypatch):
    database_path = tmp_path / "test_watchlist.db"
    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )
    asyncio.run(db.init_db())
    return database_path


def test_add_watchlist_stock(watchlist_db):
    result = asyncio.run(db.add_watchlist_stock(123, "NABIL"))

    assert result is True
    assert [item["symbol"] for item in asyncio.run(db.get_watchlist(123))] == [
        "NABIL"
    ]


def test_watchlist_normalizes_symbol(watchlist_db):
    asyncio.run(db.add_watchlist_stock(123, "  nabil  "))

    stocks = asyncio.run(db.get_watchlist(123))

    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "NABIL"


def test_duplicate_watchlist_stock_is_ignored(watchlist_db):
    first = asyncio.run(db.add_watchlist_stock(123, "NABIL"))
    second = asyncio.run(db.add_watchlist_stock(123, "nabil"))

    assert first is True
    assert second is False
    assert len(asyncio.run(db.get_watchlist(123))) == 1


def test_watchlist_is_isolated_between_users(watchlist_db):
    asyncio.run(db.add_watchlist_stock(123, "NABIL"))
    asyncio.run(db.add_watchlist_stock(456, "NICA"))

    assert [item["symbol"] for item in asyncio.run(db.get_watchlist(123))] == [
        "NABIL"
    ]
    assert [item["symbol"] for item in asyncio.run(db.get_watchlist(456))] == [
        "NICA"
    ]


def test_unknown_user_has_empty_watchlist(watchlist_db):
    assert asyncio.run(db.get_watchlist(999)) == []


def test_watchlist_is_sorted_by_symbol(watchlist_db):
    for symbol in ("NICA", "NABIL", "SHIVM"):
        asyncio.run(db.add_watchlist_stock(123, symbol))

    symbols = [
        item["symbol"] for item in asyncio.run(db.get_watchlist(123))
    ]

    assert symbols == ["NABIL", "NICA", "SHIVM"]


def test_remove_watchlist_stock(watchlist_db):
    asyncio.run(db.add_watchlist_stock(123, "NABIL"))

    result = asyncio.run(db.remove_watchlist_stock(123, "NABIL"))

    assert result is True
    assert asyncio.run(db.get_watchlist(123)) == []


def test_remove_nonexistent_watchlist_stock(watchlist_db):
    assert asyncio.run(db.remove_watchlist_stock(123, "NABIL")) is False


def test_remove_does_not_affect_another_user(watchlist_db):
    asyncio.run(db.add_watchlist_stock(123, "NABIL"))
    asyncio.run(db.add_watchlist_stock(456, "NABIL"))

    asyncio.run(db.remove_watchlist_stock(123, "NABIL"))

    assert asyncio.run(db.get_watchlist(123)) == []
    assert len(asyncio.run(db.get_watchlist(456))) == 1


def test_watchlist_does_not_create_portfolio_holding(watchlist_db):
    asyncio.run(db.add_watchlist_stock(123, "NABIL"))

    assert asyncio.run(db.get_portfolio(123)) == []


@pytest.mark.parametrize("telegram_id", [0, -1, True, 1.5, "123", None])
def test_add_watchlist_rejects_invalid_telegram_id(watchlist_db, telegram_id):
    with pytest.raises(ValueError):
        asyncio.run(db.add_watchlist_stock(telegram_id, "NABIL"))


@pytest.mark.parametrize("symbol", ["", "   ", None, 123, "NABIL LTD"])
def test_add_watchlist_rejects_invalid_symbol(watchlist_db, symbol):
    with pytest.raises(ValueError):
        asyncio.run(db.add_watchlist_stock(123, symbol))


@pytest.mark.parametrize("telegram_id", [0, -1, True, 1.5, "123", None])
def test_get_watchlist_rejects_invalid_telegram_id(watchlist_db, telegram_id):
    with pytest.raises(ValueError):
        asyncio.run(db.get_watchlist(telegram_id))


@pytest.mark.parametrize("telegram_id", [0, -1, True, 1.5, "123", None])
def test_remove_watchlist_rejects_invalid_telegram_id(watchlist_db, telegram_id):
    with pytest.raises(ValueError):
        asyncio.run(db.remove_watchlist_stock(telegram_id, "NABIL"))


@pytest.mark.parametrize("symbol", ["", "   ", None, 123, "NABIL LTD"])
def test_remove_watchlist_rejects_invalid_symbol(watchlist_db, symbol):
    with pytest.raises(ValueError):
        asyncio.run(db.remove_watchlist_stock(123, symbol))
