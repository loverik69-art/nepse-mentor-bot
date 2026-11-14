import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers import ask_mentor


def make_update_and_context(args):
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=12345),
    )
    context = SimpleNamespace(args=args)
    return update, context, message


def test_ask_mentor_prompts_when_question_is_missing():
    update, context, message = make_update_and_context([])

    asyncio.run(ask_mentor(update, context))

    message.reply_text.assert_awaited_once()
    assert "Ask me a NEPSE question" in message.reply_text.await_args.args[0]


def test_ask_mentor_returns_answer():
    update, context, message = make_update_and_context(
        ["Explain", "NABIL", "fundamentals"]
    )

    with patch(
        "bot.handlers.answer_question",
        new=AsyncMock(return_value="NABIL analysis result"),
    ) as mocked:
        asyncio.run(ask_mentor(update, context))

    mocked.assert_awaited_once_with("Explain NABIL fundamentals", 12345)
    message.reply_text.assert_awaited_once_with("NABIL analysis result")


def test_ask_mentor_returns_validation_error():
    update, context, message = make_update_and_context(["invalid"])

    with patch(
        "bot.handlers.answer_question",
        new=AsyncMock(side_effect=ValueError("Invalid stock symbol")),
    ):
        asyncio.run(ask_mentor(update, context))

    message.reply_text.assert_awaited_once_with("Invalid stock symbol")


def test_ask_mentor_handles_unexpected_error():
    update, context, message = make_update_and_context(["NABIL"])

    with patch(
        "bot.handlers.answer_question",
        new=AsyncMock(side_effect=RuntimeError("Internal failure")),
    ):
        asyncio.run(ask_mentor(update, context))

    message.reply_text.assert_awaited_once()
    assert "try again later" in message.reply_text.await_args.args[0]
