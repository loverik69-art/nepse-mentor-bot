import asyncio
import logging
from types import SimpleNamespace

import pytest

from services import price_alerts


class FakeBot:
    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    async def send_message(self, chat_id, text):
        if self.fail:
            raise RuntimeError("Telegram unavailable")

        self.messages.append({
            "chat_id": chat_id,
            "text": text,
        })


def make_alert(condition="above", target=600):
    return {
        "id": 10,
        "telegram_id": 12345,
        "symbol": "NABIL",
        "condition": condition,
        "target_price": target,
    }


@pytest.mark.parametrize(
    "condition,price,target",
    [
        ("above", 600, 600),
        ("above", 610, 600),
        ("below", 500, 500),
        ("below", 490, 500),
    ],
)
def test_price_alert_triggers_at_target(
    monkeypatch, condition, price, target
):
    alert = make_alert(condition, target)
    bot = FakeBot()
    triggered_ids = []

    async def fake_fetch():
        return [{
            "symbol": "NABIL",
            "ltp": price,
            "is_stale": False,
        }]

    async def fake_alerts():
        return [alert]

    async def fake_trigger(alert_id):
        triggered_ids.append(alert_id)
        return True

    monkeypatch.setattr(
        price_alerts, "fetch_market_data", fake_fetch
    )
    monkeypatch.setattr(
        price_alerts, "get_all_active_stock_price_alerts",
        fake_alerts,
    )
    monkeypatch.setattr(
        price_alerts, "trigger_stock_price_alert",
        fake_trigger,
    )

    context = SimpleNamespace(bot=bot)

    asyncio.run(price_alerts.check_price_alerts_job(context))

    assert triggered_ids == [10]
    assert len(bot.messages) == 1
    assert bot.messages[0]["chat_id"] == 12345
    assert "NABIL" in bot.messages[0]["text"]


def test_stale_price_does_not_trigger_alert(monkeypatch):
    bot = FakeBot()
    triggered_ids = []

    async def fake_fetch():
        return [{
            "symbol": "NABIL",
            "ltp": 700,
            "is_stale": True,
        }]

    async def fake_alerts():
        return [make_alert()]

    async def fake_trigger(alert_id):
        triggered_ids.append(alert_id)
        return True

    monkeypatch.setattr(
        price_alerts, "fetch_market_data", fake_fetch
    )
    monkeypatch.setattr(
        price_alerts, "get_all_active_stock_price_alerts",
        fake_alerts,
    )
    monkeypatch.setattr(
        price_alerts, "trigger_stock_price_alert",
        fake_trigger,
    )

    asyncio.run(
        price_alerts.check_price_alerts_job(
            SimpleNamespace(bot=bot)
        )
    )

    assert triggered_ids == []
    assert bot.messages == []


def test_unrelated_stock_does_not_trigger_alert(monkeypatch):
    bot = FakeBot()
    triggered_ids = []

    async def fake_fetch():
        return [{
            "symbol": "NICA",
            "ltp": 700,
            "is_stale": False,
        }]

    async def fake_alerts():
        return [make_alert()]

    async def fake_trigger(alert_id):
        triggered_ids.append(alert_id)
        return True

    monkeypatch.setattr(
        price_alerts, "fetch_market_data", fake_fetch
    )
    monkeypatch.setattr(
        price_alerts, "get_all_active_stock_price_alerts",
        fake_alerts,
    )
    monkeypatch.setattr(
        price_alerts, "trigger_stock_price_alert",
        fake_trigger,
    )

    asyncio.run(
        price_alerts.check_price_alerts_job(
            SimpleNamespace(bot=bot)
        )
    )

    assert triggered_ids == []
    assert bot.messages == []


def test_failed_database_trigger_logs_after_delivery(monkeypatch):
    bot = FakeBot()

    async def fake_fetch():
        return [{
            "symbol": "NABIL",
            "ltp": 650,
            "is_stale": False,
        }]

    async def fake_alerts():
        return [make_alert()]

    async def fake_trigger(alert_id):
        return False

    monkeypatch.setattr(
        price_alerts, "fetch_market_data", fake_fetch
    )
    monkeypatch.setattr(
        price_alerts, "get_all_active_stock_price_alerts",
        fake_alerts,
    )
    monkeypatch.setattr(
        price_alerts, "trigger_stock_price_alert",
        fake_trigger,
    )

    asyncio.run(
        price_alerts.check_price_alerts_job(
            SimpleNamespace(bot=bot)
        )
    )

    assert len(bot.messages) == 1
    assert bot.messages[0]["chat_id"] == 12345


def test_telegram_delivery_failure_is_logged(monkeypatch, caplog):
    bot = FakeBot(fail=True)
    trigger_calls = []

    async def fake_fetch():
        return [{
            "symbol": "NABIL",
            "ltp": 650,
            "is_stale": False,
        }]

    async def fake_alerts():
        return [make_alert()]

    async def fake_trigger(alert_id):
        trigger_calls.append(alert_id)
        return True

    monkeypatch.setattr(
        price_alerts, "fetch_market_data", fake_fetch
    )
    monkeypatch.setattr(
        price_alerts, "get_all_active_stock_price_alerts",
        fake_alerts,
    )
    monkeypatch.setattr(
        price_alerts, "trigger_stock_price_alert",
        fake_trigger,
    )

    with caplog.at_level(logging.ERROR):
        asyncio.run(
            price_alerts.check_price_alerts_job(
                SimpleNamespace(bot=bot)
            )
        )

    assert "Failed to send price alert 10" in caplog.text
    assert trigger_calls == []
