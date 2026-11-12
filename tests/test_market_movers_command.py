import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers as handlers


def make_stock(symbol, is_stale):
    return {
        "symbol": symbol,
        "ltp": 500.0,
        "percent_change": 2.5,
        "last_updated": "2026-11-09T14:59:00+05:45",
        "age_minutes": 30 if not is_stale else 3000,
        "is_stale": is_stale,
    }


def make_update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message)


def test_gainers_warn_when_data_is_stale(monkeypatch):
    async def fake_get_market_movers(direction, limit=10):
        return [make_stock("NABIL", True)]

    monkeypatch.setattr(
        handlers, "get_market_movers", fake_get_market_movers
    )

    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(
        handlers.gainers_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]

    assert "TOP GAINERS" in response
    assert "STALE DATA" in response
    assert "may not represent today's market movers" in response
    assert "NABIL" in response
    assert "Educational analysis only" in response


def test_losers_warn_when_data_is_stale(monkeypatch):
    async def fake_get_market_movers(direction, limit=10):
        return [make_stock("NABIL", True)]

    monkeypatch.setattr(
        handlers, "get_market_movers", fake_get_market_movers
    )

    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(
        handlers.losers_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]

    assert "TOP LOSERS" in response
    assert "STALE DATA" in response
    assert "NABIL" in response
    assert "Educational analysis only" in response


def test_gainers_do_not_show_stale_warning_for_fresh_data(monkeypatch):
    async def fake_get_market_movers(direction, limit=10):
        return [make_stock("NABIL", False)]

    monkeypatch.setattr(
        handlers, "get_market_movers", fake_get_market_movers
    )

    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(
        handlers.gainers_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]

    assert "TOP GAINERS" in response
    assert "STALE DATA" not in response
    assert "NABIL" in response
    assert "Educational analysis only" in response


def test_stale_warning_appears_directly_below_heading(monkeypatch):
    async def fake_get_market_movers(direction, limit=10):
        return [make_stock("NABIL", True)]

    monkeypatch.setattr(
        handlers, "get_market_movers", fake_get_market_movers
    )

    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.gainers_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    lines = response.splitlines()

    assert lines[0] == "📈 TOP GAINERS"
    assert "STALE DATA" in lines[1]


def test_market_movers_display_data_age(monkeypatch):
    async def fake_get_market_movers(direction, limit=10):
        return [make_stock("NABIL", False)]

    monkeypatch.setattr(
        handlers, "get_market_movers", fake_get_market_movers
    )

    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.gainers_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "Data age: 30m" in response


def test_gainers_handle_mixed_fresh_and_stale_stocks(monkeypatch):
    async def fake_get_market_movers(direction, limit=10):
        return [
            make_stock("NABIL", False),
            make_stock("NICA", True),
        ]

    monkeypatch.setattr(
        handlers, "get_market_movers", fake_get_market_movers
    )

    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.gainers_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    lines = response.splitlines()

    assert "NABIL" in response
    assert "NICA" in response
    assert "STALE DATA" in response

    nabil_index = next(
        i for i, line in enumerate(lines) if "NABIL" in line
    )
    nica_index = next(
        i for i, line in enumerate(lines) if "NICA" in line
    )

    nabil_details = lines[nabil_index:nabil_index + 5]
    nica_details = lines[nica_index:nica_index + 5]

    assert not any("STALE" in line for line in nabil_details)
    assert any("STALE" in line for line in nica_details)
def test_losers_handle_mixed_fresh_and_stale_stocks(monkeypatch):
    async def fake_get_market_movers(direction, limit=10):
        return [
            make_stock("NABIL", True),
            make_stock("NICA", False),
        ]

    monkeypatch.setattr(
        handlers, "get_market_movers", fake_get_market_movers
    )

    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.losers_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "TOP LOSERS" in response
    assert "NABIL" in response
    assert "NICA" in response
    assert "STALE DATA" in response
    assert "NABIL" in next(
        line for line in response.splitlines() if "NABIL" in line
    )
