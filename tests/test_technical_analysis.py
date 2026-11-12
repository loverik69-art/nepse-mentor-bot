
import asyncio
import pytest

from services import technical_analysis as ta

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import database.db as db

def test_analysis_returns_indicators_with_sufficient_history(
    monkeypatch,
):
    prices = [float(price) for price in range(100, 160)]

    async def fake_get_indicator_prices(symbol, limit=250):
        assert symbol == "NABIL"
        assert limit == 250
        return prices

    monkeypatch.setattr(
        ta,
        "get_indicator_prices",
        fake_get_indicator_prices,
    )

    result = asyncio.run(
        ta.get_technical_analysis("nabil")
    )

    assert result["symbol"] == "NABIL"
    assert result["observations"] == 60
    assert result["indicators"]["sma_20"] is not None
    assert result["indicators"]["sma_50"] is not None
    assert result["indicators"]["ema_20"] is not None
    assert result["indicators"]["ema_50"] is not None
    assert result["indicators"]["rsi_14"] is not None
    assert result["indicators"]["macd"] is not None


def test_analysis_reports_insufficient_history(monkeypatch):

    async def fake_get_indicator_prices(symbol, limit=250):
        return [500.0, 510.0, 520.0]

    monkeypatch.setattr(
        ta,
        "get_indicator_prices",
        fake_get_indicator_prices,
    )

    result = asyncio.run(
        ta.get_technical_analysis("NABIL")
    )

    assert result["observations"] == 3

    for value in result["indicators"].values():
        assert value is None


def test_analysis_rejects_empty_symbol():

    with pytest.raises(
        ValueError,
        match="Symbol must not be empty",
    ):
        asyncio.run(
            ta.get_technical_analysis("   ")
        )

def test_analysis_works_with_real_database(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "test_nepse.db"

    monkeypatch.setattr(
        db,
        "settings",
        SimpleNamespace(database_path=str(database_path)),
    )

    async def run_test():
        await db.init_db()

        start = datetime(
            2026, 1, 1,
            15, 0,
            tzinfo=timezone(timedelta(hours=5, minutes=45)),
        )

        for index in range(60):
            timestamp = (
                start + timedelta(days=index)
            ).isoformat()

            await db.save_price_snapshot({
                "symbol": "NABIL",
                "ltp": 500.0 + index,
                "volume": 1000,
                "turnover": (500.0 + index) * 1000,
                "last_updated": timestamp,
                "source": "TEST FIXTURE",
            })

        return await ta.get_technical_analysis("NABIL")

    result = asyncio.run(run_test())

    assert result["observations"] == 60

    for value in result["indicators"].values():
        assert value is not None

