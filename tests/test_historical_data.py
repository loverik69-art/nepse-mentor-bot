import asyncio
import pytest

import services.historical_data as historical


SAMPLE_DATA = {
    "version": 1,
    "market": "NEPSE",
    "currency": "NPR",
    "month": "2026-11",
    "updatedAt": "2026-11-06",
    "dates": ["2026-11-02", "2026-11-03"],
    "columns": [
        "dateIndex",
        "ltp",
        "volume",
        "turnover",
        "trades",
    ],
    "series": {
        "NABIL": [
            [0, 551, 98981, 54721809.5, 557],
            [1, 552, 42360, 23333426.4, 309],
        ],
    },
}


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return SAMPLE_DATA


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, url):
        return FakeResponse()


def test_fetch_historical_month_validates_data(monkeypatch):
    monkeypatch.setattr(
        historical.httpx,
        "AsyncClient",
        FakeClient,
    )

    result = asyncio.run(
        historical.fetch_historical_month("2026-11")
    )

    assert result["market"] == "NEPSE"
    assert result["dates"] == SAMPLE_DATA["dates"]


def test_fetch_historical_month_rejects_invalid_month():
    with pytest.raises(historical.HistoricalDataError):
        asyncio.run(
            historical.fetch_historical_month("2026-13")
        )


def test_import_historical_month_saves_records(monkeypatch):
    monkeypatch.setattr(
        historical.httpx,
        "AsyncClient",
        FakeClient,
    )

    saved_records = []

    async def fake_save(stocks):
        saved_records.extend(stocks)
        return len(stocks), 0

    monkeypatch.setattr(
        historical,
        "save_price_snapshots",
        fake_save,
    )

    result = asyncio.run(
        historical.import_historical_month("2026-11")
    )

    assert result["inserted"] == 2
    assert result["duplicates"] == 0
    assert result["rejected"] == 0
    assert len(saved_records) == 2
    assert saved_records[0]["symbol"] == "NABIL"
    assert saved_records[0]["ltp"] == 551.0
    assert saved_records[0]["source"] == historical.SOURCE


def test_import_historical_month_counts_duplicates(monkeypatch):
    monkeypatch.setattr(
        historical.httpx,
        "AsyncClient",
        FakeClient,
    )

    async def fake_save(stocks):
        return 0, len(stocks)

    monkeypatch.setattr(
        historical,
        "save_price_snapshots",
        fake_save,
    )

    result = asyncio.run(
        historical.import_historical_month("2026-11")
    )

    assert result["inserted"] == 0
    assert result["duplicates"] == 2
    assert result["rejected"] == 0
