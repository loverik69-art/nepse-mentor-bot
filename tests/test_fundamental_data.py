import asyncio
import math
from datetime import datetime, timedelta

import httpx
import pytest

from services import fundamental_data as fd


def fresh_timestamp():
    return datetime.now(fd.NEPAL_TZ).isoformat()


def sample_report(**overrides):
    report = {
        "type": "Quarterly Report",
        "quarter": "First Quarter",
        "fy": "2025-2026",
        "fy_nepali": "2082-2083",
        "pe": 20.5,
        "eps": 25.0,
        "paid_up_capital": 100000000.0,
        "profit": 25000000.0,
        "net_worth_per_share": 150.0,
        "documents": [
            {
                "submitted_date": "2026-05-12",
                "path": "NABIL/Report Upload/report.pdf",
            }
        ],
    }
    report.update(overrides)
    return report


def sample_company(**overrides):
    company = {
        "id": 1,
        "symbol": "NABIL",
        "reports": [sample_report()],
    }
    company.update(overrides)
    return company


def sample_dataset(companies=None):
    companies = companies or [sample_company()]
    return (
        companies,
        {"count": len(companies), "last_updated": fresh_timestamp()},
        {"financials_last_checked_at": fresh_timestamp()},
    )


@pytest.fixture(autouse=True)
def reset_cache():
    fd.clear_fundamental_cache()
    yield
    fd.clear_fundamental_cache()


def test_normalize_valid_report():
    report = fd._normalize_report(sample_report())

    assert report["type"] == "Quarterly Report"
    assert report["quarter"] == "First Quarter"
    assert report["fy"] == "2025-2026"
    assert report["eps"] == 25.0
    assert report["status"] if "status" in report else True
    assert report["documents"][0]["url"].endswith(
        "NABIL/Report%20Upload/report.pdf"
    )


def test_normalize_annual_report_without_quarter():
    report = fd._normalize_report(
        sample_report(type="Annual Report", quarter=None)
    )

    assert report["type"] == "Annual Report"
    assert report["quarter"] is None


def test_annual_report_unexpected_quarter_is_preserved(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        report = fd._normalize_report(
            sample_report(
                type="Annual Report",
                quarter="First Quarter",
            )
        )

    assert report["type"] == "Annual Report"
    assert report["quarter"] == "First Quarter"
    assert "unexpected quarter value" in caplog.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("pe", math.inf),
        ("eps", math.nan),
        ("profit", "invalid"),
        ("paid_up_capital", True),
    ],
)
def test_reject_invalid_financial_values(field, value):
    with pytest.raises(fd.FundamentalDataError):
        fd._normalize_report(sample_report(**{field: value}))


def test_missing_financial_values_are_allowed():
    report = fd._normalize_report(
        sample_report(profit=None, net_worth_per_share=None)
    )

    assert report["profit"] is None
    assert report["net_worth_per_share"] is None


def test_reject_unknown_report_type():
    with pytest.raises(fd.FundamentalDataError):
        fd._normalize_report(sample_report(type="Other Report"))


def test_reject_quarterly_report_without_valid_quarter():
    with pytest.raises(fd.FundamentalDataError):
        fd._normalize_report(sample_report(quarter=None))


def test_reject_missing_fiscal_year():
    with pytest.raises(fd.FundamentalDataError):
        fd._normalize_report(sample_report(fy="  "))


def test_document_url_encodes_path():
    document = fd._normalize_document(
        {
            "submitted_date": "2026-05-12",
            "path": "Company Name/Annual report.pdf",
        }
    )

    assert "Company%20Name/Annual%20report.pdf" in document["url"]


@pytest.mark.parametrize(
    "path",
    [
        "/absolute/file.pdf",
        "../outside.pdf",
        "folder/../outside.pdf",
        "folder\\file.pdf",
        "file.pdf?download=1",
        "file.pdf#page=1",
    ],
)
def test_reject_unsafe_document_paths(path):
    with pytest.raises(fd.FundamentalDataError):
        fd._normalize_document(
            {"submitted_date": "2026-05-12", "path": path}
        )


def test_identical_duplicate_reports_merge_documents():
    first = sample_report()
    second = sample_report(
        documents=[
            {
                "submitted_date": "2026-06-01",
                "path": "NABIL/second.pdf",
            }
        ]
    )

    reports = [
        fd._normalize_report(first),
        fd._normalize_report(second),
    ]

    result = fd._deduplicate_reports(reports)

    assert len(result) == 1
    assert result[0]["status"] == "verified"
    assert len(result[0]["documents"]) == 2


def test_conflicting_duplicate_reports_are_preserved():
    first = fd._normalize_report(sample_report(eps=25.0))
    second = fd._normalize_report(sample_report(eps=30.0))

    result = fd._deduplicate_reports([first, second])

    assert len(result) == 2
    assert all(report["status"] == "ambiguous" for report in result)
    assert {report["eps"] for report in result} == {25.0, 30.0}


def test_validate_valid_dataset():
    payload, metadata, run_metadata = sample_dataset()

    result = fd._validate_dataset(payload, metadata, run_metadata)

    assert result["company_count"] == 1
    assert result["report_count"] == 1
    assert "NABIL" in result["companies"]
    assert result["source"] == "YONEPSE financial reports"


def test_validate_preserves_sifc_annual_report_quarter():
    report = sample_report(
        type="Annual Report",
        quarter="First Quarter",
    )
    payload, metadata, run_metadata = sample_dataset(
        [sample_company(id=2, symbol="SIFC", reports=[report])]
    )

    result = fd._validate_dataset(payload, metadata, run_metadata)
    stored = result["companies"]["SIFC"]["reports"][0]

    assert stored["type"] == "Annual Report"
    assert stored["quarter"] == "First Quarter"


def test_reject_company_count_mismatch():
    payload, metadata, run_metadata = sample_dataset()
    metadata["count"] = 2

    with pytest.raises(fd.FundamentalDataError):
        fd._validate_dataset(payload, metadata, run_metadata)


def test_reject_duplicate_company_symbols():
    first = sample_company(id=1, symbol="NABIL")
    second = sample_company(id=2, symbol="NABIL")
    payload, metadata, run_metadata = sample_dataset([first, second])

    with pytest.raises(fd.FundamentalDataError):
        fd._validate_dataset(payload, metadata, run_metadata)


def test_reject_duplicate_company_ids():
    first = sample_company(id=1, symbol="NABIL")
    second = sample_company(id=1, symbol="NICA")
    payload, metadata, run_metadata = sample_dataset([first, second])

    with pytest.raises(fd.FundamentalDataError):
        fd._validate_dataset(payload, metadata, run_metadata)


def test_reject_stale_dataset():
    payload, metadata, run_metadata = sample_dataset()
    old_date = datetime.now(fd.NEPAL_TZ) - timedelta(days=8)
    run_metadata["financials_last_checked_at"] = old_date.isoformat()

    with pytest.raises(
        fd.FundamentalDataError,
        match="older than seven days",
    ):
        fd._validate_dataset(payload, metadata, run_metadata)


def test_reject_timestamp_without_timezone():
    with pytest.raises(
        fd.FundamentalDataError,
        match="no timezone",
    ):
        fd._parse_checked_timestamp("2026-11-13T10:00:00")


def test_reject_future_timestamp():
    future = datetime.now(fd.NEPAL_TZ) + timedelta(minutes=10)

    with pytest.raises(
        fd.FundamentalDataError,
        match="future",
    ):
        fd._parse_checked_timestamp(future.isoformat())


def test_reject_invalid_company_id():
    with pytest.raises(fd.FundamentalDataError):
        fd._normalize_company(
            {"id": True, "symbol": "NABIL", "reports": []}
        )


def test_reject_invalid_company_symbol():
    with pytest.raises(fd.FundamentalDataError):
        fd._normalize_company(
            {"id": 1, "symbol": "NABIL BANK", "reports": []}
        )


def test_get_company_financials_normalizes_symbol(monkeypatch):
    expected = {"id": 1, "symbol": "NABIL", "reports": []}

    async def fake_fetch(force_refresh=False):
        return {"companies": {"NABIL": expected}}

    monkeypatch.setattr(fd, "fetch_fundamental_data", fake_fetch)

    result = asyncio.run(fd.get_company_financials(" nabil "))

    assert result is expected


@pytest.mark.parametrize("symbol", ["", "  ", None, 123])
def test_get_company_financials_rejects_invalid_symbol(symbol):
    with pytest.raises(ValueError):
        asyncio.run(fd.get_company_financials(symbol))


def test_fetch_uses_valid_cache():
    cached = {"companies": {}, "company_count": 0}
    fd._cache = cached
    fd._cache_expires_at = float("inf")

    result = asyncio.run(fd.fetch_fundamental_data())

    assert result is cached


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, responses, **kwargs):
        self.responses = responses
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, url):
        self.calls.append(url)
        return self.responses[url]


def test_fetch_fundamental_data_loads_and_caches(monkeypatch):
    payload, metadata, run_metadata = sample_dataset()
    responses = {
        fd.FINANCIALS_URL: FakeResponse(payload),
        fd.METADATA_URL: FakeResponse(metadata),
        fd.RUN_METADATA_URL: FakeResponse(run_metadata),
    }
    clients = []

    def fake_client(*args, **kwargs):
        client = FakeClient(responses, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(fd.httpx, "AsyncClient", fake_client)

    first = asyncio.run(fd.fetch_fundamental_data(force_refresh=True))
    second = asyncio.run(fd.fetch_fundamental_data())

    assert first is second
    assert first["company_count"] == 1
    assert len(clients) == 1
    assert len(clients[0].calls) == 3


def test_fetch_fundamental_data_hides_network_error(monkeypatch):
    def fake_client(*args, **kwargs):
        class BrokenClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url):
                raise httpx.ConnectError("Network unavailable")

        return BrokenClient()

    monkeypatch.setattr(fd.httpx, "AsyncClient", fake_client)

    with pytest.raises(
        fd.FundamentalDataError,
        match="Unable to retrieve NEPSE financial data",
    ):
        asyncio.run(fd.fetch_fundamental_data(force_refresh=True))


def test_fetch_force_refresh_bypasses_cache(monkeypatch):
    payload, metadata, run_metadata = sample_dataset()
    responses = {
        fd.FINANCIALS_URL: FakeResponse(payload),
        fd.METADATA_URL: FakeResponse(metadata),
        fd.RUN_METADATA_URL: FakeResponse(run_metadata),
    }
    calls = []

    def fake_client(*args, **kwargs):
        client = FakeClient(responses, **kwargs)
        calls.append(client)
        return client

    monkeypatch.setattr(fd.httpx, "AsyncClient", fake_client)

    asyncio.run(fd.fetch_fundamental_data(force_refresh=True))
    asyncio.run(fd.fetch_fundamental_data(force_refresh=True))

    assert len(calls) == 2
