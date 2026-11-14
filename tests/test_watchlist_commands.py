import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers as handlers


def make_update(user_id=12345):
    message = SimpleNamespace(reply_text=AsyncMock())
    user = SimpleNamespace(id=user_id)
    return SimpleNamespace(message=message, effective_user=user)


def response_text(update):
    return update.message.reply_text.await_args.args[0]


def test_watchadd_command_adds_stock(monkeypatch):
    async def fake_add(user_id, symbol):
        assert user_id == 12345
        assert symbol == "NABIL"
        return True

    monkeypatch.setattr(handlers, "add_watchlist_stock", fake_add)

    update = make_update()
    context = SimpleNamespace(args=["nabil"])

    asyncio.run(handlers.watchadd_command(update, context))

    response = response_text(update)
    assert "NABIL added to your watchlist" in response
    assert "does not add it to your portfolio" in response


def test_watchadd_command_reports_duplicate(monkeypatch):
    async def fake_add(user_id, symbol):
        return False

    monkeypatch.setattr(handlers, "add_watchlist_stock", fake_add)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.watchadd_command(update, context))

    assert "already in your watchlist" in response_text(update)


def test_watchadd_command_requires_one_symbol():
    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.watchadd_command(update, context))

    assert "Usage: /watchadd SYMBOL" in response_text(update)


def test_watchadd_command_rejects_invalid_symbol():
    update = make_update()
    context = SimpleNamespace(args=["NABIL!"])

    asyncio.run(handlers.watchadd_command(update, context))

    assert "Invalid stock symbol" in response_text(update)


def test_watchadd_command_handles_database_error(monkeypatch):
    async def fake_add(user_id, symbol):
        raise RuntimeError("Database error")

    monkeypatch.setattr(handlers, "add_watchlist_stock", fake_add)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.watchadd_command(update, context))

    assert "Unable to update your watchlist" in response_text(update)


def test_watchlist_command_displays_stocks(monkeypatch):
    async def fake_get(user_id):
        assert user_id == 12345
        return [
            {"symbol": "NABIL", "created_at": "2026-11-14"},
            {"symbol": "NICA", "created_at": "2026-11-14"},
        ]

    monkeypatch.setattr(handlers, "get_watchlist", fake_get)

    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.watchlist_command(update, context))

    response = response_text(update)
    assert "YOUR NEPSE WATCHLIST" in response
    assert "1. NABIL" in response
    assert "2. NICA" in response
    assert "/watchremove SYMBOL" in response


def test_watchlist_command_displays_empty_message(monkeypatch):
    async def fake_get(user_id):
        return []

    monkeypatch.setattr(handlers, "get_watchlist", fake_get)

    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.watchlist_command(update, context))

    response = response_text(update)
    assert "Your watchlist is empty" in response
    assert "/watchadd SYMBOL" in response


def test_watchlist_command_handles_database_error(monkeypatch):
    async def fake_get(user_id):
        raise RuntimeError("Database error")

    monkeypatch.setattr(handlers, "get_watchlist", fake_get)

    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.watchlist_command(update, context))

    assert "Unable to retrieve your watchlist" in response_text(update)


def test_watchremove_command_removes_stock(monkeypatch):
    async def fake_remove(user_id, symbol):
        assert user_id == 12345
        assert symbol == "NABIL"
        return True

    monkeypatch.setattr(handlers, "remove_watchlist_stock", fake_remove)

    update = make_update()
    context = SimpleNamespace(args=["nabil"])

    asyncio.run(handlers.watchremove_command(update, context))

    assert "NABIL removed from your watchlist" in response_text(update)


def test_watchremove_command_reports_missing_stock(monkeypatch):
    async def fake_remove(user_id, symbol):
        return False

    monkeypatch.setattr(handlers, "remove_watchlist_stock", fake_remove)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.watchremove_command(update, context))

    assert "was not found in your watchlist" in response_text(update)


def test_watchremove_command_requires_one_symbol():
    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.watchremove_command(update, context))

    assert "Usage: /watchremove SYMBOL" in response_text(update)


def test_watchremove_command_rejects_invalid_symbol():
    update = make_update()
    context = SimpleNamespace(args=["NABIL!"])

    asyncio.run(handlers.watchremove_command(update, context))

    assert "Invalid stock symbol" in response_text(update)


def test_watchremove_command_handles_database_error(monkeypatch):
    async def fake_remove(user_id, symbol):
        raise RuntimeError("Database error")

    monkeypatch.setattr(handlers, "remove_watchlist_stock", fake_remove)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.watchremove_command(update, context))

    assert "Unable to update your watchlist" in response_text(update)
