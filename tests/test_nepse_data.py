

import math
import pytest

from services.nepse_data import normalize_stock, MarketDataError
from datetime import datetime, timedelta

SAMPLE = {
    "symbol": "NABIL",
    "name": "Nabil Bank Limited",
    "ltp": 549.0,
    "previous_close": 550.0,
    "change": -1.0,
    "percent_change": -0.18,
    "high": 554.0,
    "low": 549.0,
    "volume": 21117,
    "turnover": 11631469.3,
    "trades": 211,
    "market_cap": 155970.07,
    "last_updated": "2026-11-06T14:59:34.613360",
}


def test_normalize_valid_stock():
    stock = normalize_stock(SAMPLE)

    assert stock["symbol"] == "NABIL"
    assert stock["ltp"] == 549.0
    assert stock["name"] == "Nabil Bank Limited"
    assert stock["is_stale"] is True
    assert stock["source"] == "YONEPSE community data feed"


def test_reject_invalid_price():
    bad_stock = SAMPLE.copy()
    bad_stock["ltp"] = -10

    with pytest.raises(MarketDataError):
        normalize_stock(bad_stock)


def test_reject_infinite_price():
    bad_stock = SAMPLE.copy()
    bad_stock["ltp"] = math.inf

    with pytest.raises(MarketDataError):
        normalize_stock(bad_stock)


def test_reject_nan_price():
    bad_stock = SAMPLE.copy()
    bad_stock["ltp"] = math.nan

    with pytest.raises(MarketDataError):
        normalize_stock(bad_stock)


def test_reject_blank_symbol():
    bad_stock = SAMPLE.copy()
    bad_stock["symbol"] = "   "

    with pytest.raises(MarketDataError):
        normalize_stock(bad_stock)


def test_reject_invalid_record():
    with pytest.raises(MarketDataError):
        normalize_stock(None)


import asyncio
import httpx
from services import nepse_data


class FakeResponse:
    def __init__(self, payload=None, json_error=None):
        self.payload = payload
        self.json_error = json_error

    def raise_for_status(self):
        pass

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class FakeClient:
    def __init__(self, response=None, error=None, **kwargs):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, url):
        if self.error:
            raise self.error
        return self.response

def test_fetch_market_data_logs_network_error(monkeypatch, caplog):
    import logging

    def fake_client(*args, **kwargs):
        return FakeClient(
            error=httpx.ConnectError("Network unavailable")
        )

    monkeypatch.setattr(
        nepse_data.httpx,
        "AsyncClient",
        fake_client,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(MarketDataError):
            asyncio.run(nepse_data.fetch_market_data())

    assert "Failed to retrieve NEPSE market data" in caplog.text
    assert "Network unavailable" not in caplog.text

def test_fetch_market_data_logs_invalid_json(monkeypatch, caplog):
    import logging

    response = FakeResponse(
        json_error=ValueError("Invalid JSON")
    )

    def fake_client(*args, **kwargs):
        return FakeClient(response=response)

    monkeypatch.setattr(
        nepse_data.httpx,
        "AsyncClient",
        fake_client,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(MarketDataError):
            asyncio.run(nepse_data.fetch_market_data())

    assert "Failed to retrieve NEPSE market data" in caplog.text
    assert "Invalid JSON" not in caplog.text

def test_fetch_market_data_logs_unexpected_format(monkeypatch, caplog):
    import logging

    response = FakeResponse(payload={"stocks": []})

    def fake_client(*args, **kwargs):
        return FakeClient(response=response)

    monkeypatch.setattr(
        nepse_data.httpx,
        "AsyncClient",
        fake_client,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(MarketDataError):
            asyncio.run(nepse_data.fetch_market_data())

    assert "Unexpected market-data format received" in caplog.text

def test_fetch_market_data_logs_empty_feed(monkeypatch, caplog):
    import logging

    response = FakeResponse(payload=[])

    def fake_client(*args, **kwargs):
        return FakeClient(response=response)

    monkeypatch.setattr(
        nepse_data.httpx,
        "AsyncClient",
        fake_client,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(MarketDataError):
            asyncio.run(nepse_data.fetch_market_data())

    assert "NEPSE market-data feed returned no records" in caplog.text

def test_fetch_market_data_keeps_newest_duplicate(monkeypatch):
    older = SAMPLE.copy()
    older["last_updated"] = "2026-11-06T14:00:00"
    older["ltp"] = 540.0
    older["change"] = -10.0
    older["low"] = 539.0
    older["percent_change"] = -1.82

    newer = SAMPLE.copy()
    newer["last_updated"] = "2026-11-07T14:00:00"
    newer["ltp"] = 550.0
    newer["change"] = 0.0
    newer["percent_change"] = 0.0
    response = FakeResponse(payload=[older, newer])

    def fake_client(*args, **kwargs):
        return FakeClient(response=response)

    monkeypatch.setattr(nepse_data.httpx, "AsyncClient", fake_client)

    stocks = asyncio.run(nepse_data.fetch_market_data())

    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "NABIL"
    assert stocks[0]["ltp"] == 550.0


@pytest.mark.parametrize(
    "field,value",
    [
        ("volume", -100),
        ("turnover", -500),
        ("trades", -10),
        ("market_cap", -100),
        ("previous_close", float("inf")),
        ("high", float("nan")),
        ("low", "invalid"),
        ("percent_change", float("inf")),
    ],
)
def test_reject_invalid_optional_fields(field, value):
    bad_stock = SAMPLE.copy()
    bad_stock[field] = value

    with pytest.raises(MarketDataError):
        normalize_stock(bad_stock)


def test_optional_fields_can_be_missing():
    stock_data = SAMPLE.copy()

    for field in [
        "previous_close",
        "change",
        "percent_change",
        "high",
        "low",
        "volume",
        "turnover",
        "trades",
        "market_cap",
    ]:
        stock_data.pop(field)

    stock = normalize_stock(stock_data)

    assert stock["symbol"] == "NABIL"
    assert stock["volume"] is None
    assert stock["market_cap"] is None


@pytest.mark.parametrize(
    "direction,expected",
    [
        ("gainers", ["AAA", "BBB"]),
        ("losers", ["DDD", "CCC"]),
    ],
)
def test_market_movers_ranking(monkeypatch, direction, expected):
    stocks = [
        {"symbol": "AAA", "percent_change": 5.0},
        {"symbol": "BBB", "percent_change": 2.0},
        {"symbol": "CCC", "percent_change": -2.0},
        {"symbol": "DDD", "percent_change": -5.0},
        {"symbol": "EEE", "percent_change": 0.0},
        {"symbol": "FFF", "percent_change": None},
    ]

    async def fake_fetch():
        return stocks

    monkeypatch.setattr(
        nepse_data, "fetch_market_data", fake_fetch
    )

    result = asyncio.run(
        nepse_data.get_market_movers(direction)
    )

    assert [stock["symbol"] for stock in result] == expected


def test_market_movers_limit(monkeypatch):
    stocks = [
        {"symbol": "AAA", "percent_change": 5.0},
        {"symbol": "BBB", "percent_change": 4.0},
        {"symbol": "CCC", "percent_change": 3.0},
    ]

    async def fake_fetch():
        return stocks

    monkeypatch.setattr(
        nepse_data, "fetch_market_data", fake_fetch
    )

    result = asyncio.run(
        nepse_data.get_market_movers("gainers", limit=2)
    )

    assert len(result) == 2
    assert [stock["symbol"] for stock in result] == ["AAA", "BBB"]


@pytest.mark.parametrize(
    "direction,limit",
    [
        ("unknown", 10),
        ("gainers", 0),
        ("losers", -1),
        ("gainers", 1.5),
        ("gainers", True),
    ],
)
def test_market_movers_reject_invalid_arguments(direction, limit):
    with pytest.raises(ValueError):
        asyncio.run(
            nepse_data.get_market_movers(direction, limit)
        )


@pytest.mark.parametrize(
    "symbol",
    [
        "NABIL BANK",
        "NABIL@",
        "NABIL!",
        "NABIL/ABC",
        "NABIL BANK LIMITED",
    ],
)
def test_reject_invalid_stock_symbols(symbol):
    bad_stock = SAMPLE.copy()
    bad_stock["symbol"] = symbol

    with pytest.raises(MarketDataError):
        normalize_stock(bad_stock)


@pytest.mark.parametrize(
    "symbol",
    ["NABIL", "GBILD86/87", "NIFRAUR85/86", "NABILP", "ACLBSL", "12345"],
)
def test_accept_valid_stock_symbols(symbol):
    stock_data = SAMPLE.copy()
    stock_data["symbol"] = symbol

    stock = normalize_stock(stock_data)

    assert stock["symbol"] == symbol

@pytest.mark.parametrize(
    "field,value",
    [
        ("volume", 100.5),
        ("volume", 10.25),
        ("trades", 5.5),
        ("trades", 2.75),
    ],
)
def test_reject_fractional_count_fields(field, value):
    bad_stock = SAMPLE.copy()
    bad_stock[field] = value

    with pytest.raises(MarketDataError):
        normalize_stock(bad_stock)
@pytest.mark.parametrize(
    "field,value",
    [
        ("high", 540.0),
        ("low", 560.0),
    ],
)
def test_reject_invalid_high_low_relationship(field, value):
    bad_stock = SAMPLE.copy()
    bad_stock[field] = value

    with pytest.raises(MarketDataError):
        normalize_stock(bad_stock)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ltp", 555.0),
        ("ltp", 540.0),
    ],
)
def test_reject_ltp_outside_daily_range(field, value):
    bad_stock = SAMPLE.copy()
    bad_stock[field] = value

    with pytest.raises(MarketDataError):
        normalize_stock(bad_stock)

@pytest.mark.parametrize(
    "field,value",
    [
        ("change", 5.0),
        ("change", -5.0),
        ("percent_change", 2.0),
        ("percent_change", -2.0),
    ],
)
def test_reject_inconsistent_price_change(field, value):
    bad_stock = SAMPLE.copy()
    bad_stock[field] = value

    with pytest.raises(MarketDataError):
        normalize_stock(bad_stock)

def test_fetch_market_data_logs_rejected_records(monkeypatch, caplog):
    import logging

    valid = SAMPLE.copy()

    invalid = SAMPLE.copy()
    invalid["symbol"] = "NABIL@"

    response = FakeResponse(payload=[valid, invalid])

    def fake_client(*args, **kwargs):
        return FakeClient(response=response)

    monkeypatch.setattr(
        nepse_data.httpx,
        "AsyncClient",
        fake_client,
    )

    with caplog.at_level(logging.WARNING):
        stocks = asyncio.run(nepse_data.fetch_market_data())

    assert len(stocks) == 1
    assert "Invalid stock symbol format" in caplog.text
    assert "NABIL@" not in caplog.text

def test_fetch_market_data_logs_summary(monkeypatch, caplog):
    import logging

    valid = SAMPLE.copy()

    invalid = SAMPLE.copy()
    invalid["symbol"] = "NABIL@"

    duplicate = SAMPLE.copy()
    duplicate["last_updated"] = "2026-11-05T14:00:00"

    response = FakeResponse(
        payload=[valid, invalid, duplicate]
    )

    def fake_client(*args, **kwargs):
        return FakeClient(response=response)

    monkeypatch.setattr(
        nepse_data.httpx,
        "AsyncClient",
        fake_client,
    )

    with caplog.at_level(logging.INFO):
        stocks = asyncio.run(nepse_data.fetch_market_data())

    assert len(stocks) == 1
    assert "received=3" in caplog.text
    assert "valid=2" in caplog.text
    assert "rejected=1" in caplog.text
    assert "duplicates_removed=1" in caplog.text
    assert "fresh=" in caplog.text
    assert "stale=" in caplog.text

def test_fetch_market_data_saves_newest_fresh_snapshot(monkeypatch):
    now = datetime.now().astimezone()

    older = SAMPLE.copy()
    older["last_updated"] = (
        now - timedelta(minutes=2)
    ).isoformat()
    older["ltp"] = 540.0
    older["change"] = -10.0
    older["percent_change"] = -1.82

    newer = SAMPLE.copy()
    newer["last_updated"] = now.isoformat()
    newer["ltp"] = 550.0
    newer["change"] = 0.0
    newer["percent_change"] = 0.0

    response = FakeResponse(payload=[older, newer])

    def fake_client(*args, **kwargs):
        return FakeClient(response=response)

    saved = []

    async def fake_save(stock):
        saved.append(stock)
        return True

    monkeypatch.setattr(
        nepse_data.httpx,
        "AsyncClient",
        fake_client,
    )
    monkeypatch.setattr(
        nepse_data,
        "save_price_snapshot",
        fake_save,
        raising=False,
    )

    stocks = asyncio.run(nepse_data.fetch_market_data())

    assert len(stocks) == 1
    assert stocks[0]["ltp"] == 550.0
    assert len(saved) == 1
    assert saved[0]["symbol"] == stocks[0]["symbol"]
    assert saved[0]["ltp"] == 550.0

def test_fetch_market_data_does_not_save_stale_snapshots(monkeypatch):
    old_stock = SAMPLE.copy()

    old_stock["last_updated"] = (
        datetime.now().astimezone() - timedelta(hours=25)
    ).isoformat()

    response = FakeResponse(payload=[old_stock])

    def fake_client(*args, **kwargs):
        return FakeClient(response=response)

    saved = []

    async def fake_save(stock):
        saved.append(stock)
        return True

    monkeypatch.setattr(
        nepse_data.httpx,
        "AsyncClient",
        fake_client,
    )
    monkeypatch.setattr(
        nepse_data,
        "save_price_snapshot",
        fake_save,
        raising=False,
    )

    stocks = asyncio.run(nepse_data.fetch_market_data())

    assert len(stocks) == 1
    assert stocks[0]["is_stale"] is True
    assert len(saved) == 0



def test_fetch_market_data_saves_only_fresh_stocks(monkeypatch):
    now = datetime.now().astimezone()

    stale_stock = SAMPLE.copy()
    stale_stock["symbol"] = "NICA"
    stale_stock["last_updated"] = (
        now - timedelta(hours=25)
    ).isoformat()

    fresh_stock = SAMPLE.copy()
    fresh_stock["symbol"] = "NABIL"
    fresh_stock["last_updated"] = now.isoformat()

    response = FakeResponse(
        payload=[stale_stock, fresh_stock]
    )

    def fake_client(*args, **kwargs):
        return FakeClient(response=response)

    saved = []

    async def fake_save(stock):
        saved.append(stock)
        return True

    monkeypatch.setattr(
        nepse_data.httpx,
        "AsyncClient",
        fake_client,
    )
    monkeypatch.setattr(
        nepse_data,
        "save_price_snapshot",
        fake_save,
        raising=False,
    )

    stocks = asyncio.run(nepse_data.fetch_market_data())

    assert len(stocks) == 2
    assert stocks[0]["is_stale"] is True
    assert stocks[1]["is_stale"] is False
    assert len(saved) == 1
    assert saved[0]["symbol"] == "NABIL"
