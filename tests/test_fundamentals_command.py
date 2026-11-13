import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bot.handlers as handlers


@pytest.fixture(autouse=True)
def mock_market_price(monkeypatch):
    async def fake_get_stock(symbol):
        return {
            "symbol": symbol,
            "ltp": 500.0,
            "last_updated": "2026-11-13T15:00:00+05:45",
            "age_minutes": 10,
            "is_stale": False,
        }

    monkeypatch.setattr(handlers, "get_stock", fake_get_stock)


def make_update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message)


def sample_report(quarter, eps, status="verified"):
    return {
        "type": "Quarterly Report",
        "fy": "2025-2026",
        "quarter": quarter,
        "pe": 12.5,
        "eps": eps,
        "profit": 1000000.0,
        "paid_up_capital": 50000000.0,
        "net_worth_per_share": 150.0,
        "status": status,
        "documents": [],
    }


def test_fundamentals_show_financial_reports(monkeypatch):
    async def fake_financials(symbol):
        assert symbol == "NABIL"
        return {
            "id": 1,
            "symbol": "NABIL",
            "reports": [
                sample_report("First Quarter", 10.0),
                sample_report("Third Quarter", 30.0),
                sample_report("Second Quarter", 20.0),
            ],
        }

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["nabil"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    update.message.reply_text.assert_awaited_once()
    response = update.message.reply_text.await_args.args[0]

    assert "FUNDAMENTAL REPORTS — NABIL" in response
    assert "Available reports: 3" in response
    assert "P/E: 12.50" in response
    assert "EPS: 30.00" in response
    assert "Profit: 1,000,000.00" in response
    assert "Paid-up capital: 50,000,000.00" in response
    assert "Net worth per share: 150.00" in response
    assert response.index("Third Quarter") < response.index("Second Quarter")
    assert response.index("Second Quarter") < response.index("First Quarter")
    assert "not financial advice" in response


def test_fundamentals_show_missing_values(monkeypatch):
    async def fake_financials(symbol):
        return {
            "id": 1,
            "symbol": symbol,
            "reports": [sample_report("First Quarter", None)],
        }

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]
    assert "EPS: Not reported" in response


def test_fundamentals_warn_about_ambiguous_reports(monkeypatch):
    async def fake_financials(symbol):
        return {
            "id": 1,
            "symbol": symbol,
            "reports": [
                sample_report("Second Quarter", 20.0, "ambiguous")
            ],
        }

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]
    assert "Conflicting source records" in response
    assert "unverified" in response


def test_fundamentals_include_document_links(monkeypatch):
    async def fake_financials(symbol):
        report = sample_report("First Quarter", 10.0)
        report["documents"] = [{
            "submitted_date": "2026-01-15",
            "url": "https://example.com/report.pdf",
        }]
        return {"id": 1, "symbol": symbol, "reports": [report]}

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]
    assert "https://example.com/report.pdf" in response
    assert "2026-01-15" in response


def test_fundamentals_require_one_symbol():
    update = make_update()
    context = SimpleNamespace(args=[])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]
    assert "Usage: /fundamentals SYMBOL" in response


def test_fundamentals_reject_invalid_symbol():
    update = make_update()
    context = SimpleNamespace(args=["NABIL!"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]
    assert "Invalid stock symbol" in response


def test_fundamentals_accept_slash_in_symbol(monkeypatch):
    async def fake_financials(symbol):
        assert symbol == "ABC/DE"
        return {"id": 2, "symbol": symbol, "reports": [
            sample_report("First Quarter", 10.0)
        ]}

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["ABC/DE"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]
    assert "FUNDAMENTAL REPORTS — ABC/DE" in response


def test_fundamentals_handle_unknown_company(monkeypatch):
    async def fake_financials(symbol):
        return None

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["UNKNOWN"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]
    assert "No fundamental financial data found" in response


def test_fundamentals_handle_no_reports(monkeypatch):
    async def fake_financials(symbol):
        return {"id": 1, "symbol": symbol, "reports": []}

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]
    assert "No financial reports are available" in response


def test_fundamentals_handle_service_error(monkeypatch):
    async def fake_financials(symbol):
        raise handlers.FundamentalDataError("Test failure")

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]
    assert "temporarily unavailable" in response


def test_fundamentals_display_year_over_year_comparisons(monkeypatch):
    async def fake_financials(symbol):
        current = sample_report("First Quarter", 30.0)
        current["fy"] = "2026-2027"
        current["profit"] = 2000000.0
        current["net_worth_per_share"] = 160.0

        previous = sample_report("First Quarter", 25.0)
        previous["fy"] = "2025-2026"
        previous["profit"] = 1000000.0
        previous["net_worth_per_share"] = 150.0

        return {
            "id": 1,
            "symbol": symbol,
            "reports": [current, previous],
        }

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]

    assert "YEAR-OVER-YEAR COMPARISON" in response
    assert "EPS: 30.00 vs 25.00 (+20.00%)" in response
    assert "Net worth per share: 160.00 vs 150.00 (+6.67%)" in response
    assert "Profit growth is not calculated" not in response
    assert "growth not calculated" in response


def test_fundamentals_do_not_claim_profit_growth(monkeypatch):
    async def fake_financials(symbol):
        current = sample_report("First Quarter", 30.0)
        current["fy"] = "2026-2027"
        previous = sample_report("First Quarter", 25.0)
        previous["fy"] = "2025-2026"

        return {
            "id": 1,
            "symbol": symbol,
            "reports": [current, previous],
        }

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]

    assert "Profit: 1,000,000.00" in response
    assert "growth not calculated" in response
    assert "Profit: 1,000,000.00 vs 1,000,000.00 (+0.00%)" not in response


def test_fundamentals_explain_insufficient_comparison_history(monkeypatch):
    async def fake_financials(symbol):
        return {
            "id": 1,
            "symbol": symbol,
            "reports": [sample_report("First Quarter", 25.0)],
        }

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(
        handlers.fundamentals_command(update, context)
    )

    response = update.message.reply_text.await_args.args[0]

    assert "YEAR-OVER-YEAR COMPARISON" in response
    assert "EPS: Insufficient comparable history." in response
    assert "Net worth per share: Insufficient comparable history." in response


def test_fundamentals_calculate_indicative_pb_with_fresh_price(monkeypatch):
    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    async def fake_financials(symbol):
        return {
            "id": 1,
            "symbol": symbol,
            "reports": [sample_report("First Quarter", 30.0)],
        }

    async def fake_stock(symbol):
        return {
            "symbol": symbol,
            "ltp": 500.0,
            "last_updated": "2026-11-13T15:00:00+05:45",
            "is_stale": False,
        }

    monkeypatch.setattr(handlers, 'get_company_financials', fake_financials)
    monkeypatch.setattr(handlers, 'get_stock', fake_stock)

    asyncio.run(handlers.fundamentals_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "VALUATION METRICS" in response
    assert "Source-reported P/E: 12.50" in response
    assert "Indicative P/B: 3.33x" in response


def test_fundamentals_withhold_pb_for_stale_market_price(monkeypatch):
    async def fake_financials(symbol):
        return {
            "id": 1,
            "symbol": symbol,
            "reports": [sample_report("First Quarter", 30.0)],
        }

    async def fake_stock(symbol):
        return {
            "symbol": symbol,
            "ltp": 500.0,
            "last_updated": "2026-11-06T15:00:00+05:45",
            "is_stale": True,
        }

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )
    monkeypatch.setattr(handlers, "get_stock", fake_stock)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.fundamentals_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "STALE" in response
    assert "Indicative P/B withheld" in response
    assert "Indicative P/B: 3.33x" not in response


def test_fundamentals_handle_unavailable_market_price(monkeypatch):
    async def fake_financials(symbol):
        return {
            "id": 1,
            "symbol": symbol,
            "reports": [sample_report("First Quarter", 30.0)],
        }

    async def fake_stock(symbol):
        return None

    monkeypatch.setattr(
        handlers, "get_company_financials", fake_financials
    )
    monkeypatch.setattr(handlers, "get_stock", fake_stock)

    update = make_update()
    context = SimpleNamespace(args=["NABIL"])

    asyncio.run(handlers.fundamentals_command(update, context))

    response = update.message.reply_text.await_args.args[0]

    assert "FUNDAMENTAL REPORTS" in response
    assert "Market price unavailable" in response
    assert "indicative P/B not calculated" in response
