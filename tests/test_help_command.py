import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers import help_command


def test_help_command_includes_all_trading_commands():
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(message=message)
    context = SimpleNamespace()

    asyncio.run(help_command(update, context))

    message.reply_text.assert_awaited_once()
    help_text = message.reply_text.await_args.args[0]

    assert "/signal SYMBOL" in help_text
    assert "/backtest SYMBOL" in help_text
    assert "/fundamentals SYMBOL" in help_text
    assert "/portfolio" in help_text
    assert "/health" in help_text
    assert "not financial advice" in help_text
