import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers as handlers


def make_update():
    message = SimpleNamespace(
        reply_text=AsyncMock(),
        reply_photo=AsyncMock(),
    )
    return SimpleNamespace(message=message)


def test_chart_sends_generated_photo(monkeypatch):
    async def fake_get_price_history(symbol, limit=30):
        assert symbol == "NABIL"
        assert limit == 30
        return [{"ltp": 500}, {"ltp": 510}]

    def fake_generate_chart(records, symbol):
        assert len(records) == 2
        assert symbol == "NABIL"
        return BytesIO(b"test chart")

    monkeypatch.setattr(
        handlers, "get_price_history", fake_get_price_history
    )
    monkeypatch.setattr(
        handlers, "generate_price_chart", fake_generate_chart
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.chart_command(update, context))

    update.message.reply_photo.assert_awaited_once()
    update.message.reply_text.assert_not_awaited()

    kwargs = update.message.reply_photo.await_args.kwargs
    assert kwargs["caption"].startswith(
        "📈 NABIL — Historical LTP"
    )
    assert "not a live quote" in kwargs["caption"]


def test_chart_handles_missing_history(monkeypatch):
    async def fake_get_price_history(symbol, limit=30):
        return []

    monkeypatch.setattr(
        handlers, "get_price_history", fake_get_price_history
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.chart_command(update, context))

    update.message.reply_text.assert_awaited_once()
    response = update.message.reply_text.await_args.args[0]

    assert "No historical data found for NABIL" in response
    update.message.reply_photo.assert_not_awaited()


def test_chart_requires_symbol():
    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(handlers.chart_command(update, context))

    update.message.reply_text.assert_awaited_once()
    response = update.message.reply_text.await_args.args[0]

    assert "Usage: /chart SYMBOL [LIMIT]" in response


def test_chart_rejects_invalid_symbol():
    update = make_update()
    context = SimpleNamespace(args=["NABIL!"])

    asyncio.run(handlers.chart_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Invalid stock symbol" in response


def test_chart_rejects_invalid_limit():
    update = make_update()
    context = SimpleNamespace(args=["NABIL", "abc"])

    asyncio.run(handlers.chart_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "Invalid limit" in response


def test_chart_rejects_limit_out_of_range():
    update = make_update()
    context = SimpleNamespace(args=["NABIL", "300"])

    asyncio.run(handlers.chart_command(update, context))

    response = update.message.reply_text.await_args.args[0]
    assert "between 1 and 250" in response


def test_chart_handles_generation_error(monkeypatch):
    async def fake_get_price_history(symbol, limit=30):
        return [{"ltp": 500}, {"ltp": 510}]

    def fake_generate_chart(records, symbol):
        raise RuntimeError("Test chart error")

    monkeypatch.setattr(
        handlers, "get_price_history", fake_get_price_history
    )
    monkeypatch.setattr(
        handlers, "generate_price_chart", fake_generate_chart
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.chart_command(update, context))

    update.message.reply_text.assert_awaited_once()
    response = update.message.reply_text.await_args.args[0]

    assert "Unable to generate the historical chart" in response
    update.message.reply_photo.assert_not_awaited()
