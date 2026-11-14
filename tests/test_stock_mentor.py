import pytest

from services.stock_mentor import classify_question


@pytest.mark.parametrize(
    ("question", "topic", "symbol"),
    [
        ("NABIL fundamental analysis", "fundamental", "NABIL"),
        ("NICA buy or sell signal", "signal", "NICA"),
        ("SHIVM trade plan", "tradeplan", "SHIVM"),
        ("What does RSI mean?", "technical", None),
        ("Explain MACD", "technical", None),
        ("my portfolio performance", "portfolio", None),
    ],
)
def test_classify_question(question, topic, symbol):
    result = classify_question(question)

    assert result["topic"] == topic
    assert result["symbol"] == symbol
    assert result["question"] == question


@pytest.mark.parametrize("question", ["", "   ", None])
def test_reject_empty_question(question):
    with pytest.raises(ValueError):
        classify_question(question)


def test_reject_question_over_300_characters():
    with pytest.raises(ValueError):
        classify_question("A" * 301)


def test_general_question_has_no_stock_symbol():
    result = classify_question("What does dividend yield mean?")

    assert result["symbol"] is None


from services.stock_mentor import explain_indicator, explain_general_question


def test_explain_rsi_indicator():
    result = explain_indicator("rsi_14", 72.5)
    assert "72.50" in result
    assert "overbought" in result.lower()
    assert "reversal" in result.lower()


def test_explain_missing_indicator():
    result = explain_indicator("sma_20", None)
    assert "Not available" in result


def test_explain_macd_values():
    result = explain_indicator(
        "macd",
        {"macd": 2.5, "signal": 1.5, "histogram": 1.0},
    )
    assert "2.50" in result
    assert "1.50" in result
    assert "1.00" in result


def test_general_question_explains_pe_ratio():
    result = explain_general_question("What does P/E ratio mean?")
    assert "market price" in result.lower()
    assert "earnings per share" in result.lower()


def test_general_question_explains_dividend_yield():
    result = explain_general_question("Explain dividend yield")
    assert "annual dividend" in result.lower()
    assert "not guaranteed" in result.lower()


def test_general_question_has_safe_fallback():
    result = explain_general_question("Tell me something")
    assert "NEPSE" in result
    assert "NABIL" in result


from services.stock_mentor import explain_technical_analysis


def test_technical_analysis_explains_bullish_trend():
    analysis = {
        "symbol": "NABIL",
        "observations": 100,
        "data_basis": "Historical daily snapshots",
        "indicators": {
            "sma_20": 550.0,
            "sma_50": 530.0,
            "ema_20": 552.0,
            "ema_50": 535.0,
            "rsi_14": 60.0,
            "macd": {
                "macd": 3.0,
                "signal": 2.0,
                "histogram": 1.0,
            },
        },
    }

    result = explain_technical_analysis(analysis)

    assert "NABIL" in result
    assert "above SMA50" in result
    assert "above EMA50" in result
    assert "Positive histogram" in result


def test_technical_analysis_warns_about_stale_data():
    analysis = {
        "symbol": "NABIL",
        "observations": 100,
        "indicators": {},
    }

    result = explain_technical_analysis(analysis, is_stale=True)

    assert "stale" in result.lower()


def test_technical_analysis_warns_about_insufficient_history():
    analysis = {
        "symbol": "NABIL",
        "observations": 10,
        "indicators": {},
    }

    result = explain_technical_analysis(analysis)

    assert "insufficient" in result.lower()


import asyncio
from unittest.mock import AsyncMock, patch


def test_answer_technical_question_with_fresh_data():
    from services.stock_mentor import answer_technical_question

    analysis = {
        "symbol": "NABIL",
        "observations": 100,
        "indicators": {
            "sma_20": 550.0,
            "sma_50": 530.0,
        },
    }

    with (
        patch(
            "services.nepse_data.get_stock",
            new=AsyncMock(return_value={"is_stale": False}),
        ),
        patch(
            "services.technical_analysis.get_technical_analysis",
            new=AsyncMock(return_value=analysis),
        ),
    ):
        result = asyncio.run(answer_technical_question("NABIL"))

    assert "NABIL" in result
    assert "above SMA50" in result


def test_answer_technical_question_warns_about_stale_data():
    from services.stock_mentor import answer_technical_question

    analysis = {
        "symbol": "NABIL",
        "observations": 100,
        "indicators": {},
    }

    with (
        patch(
            "services.nepse_data.get_stock",
            new=AsyncMock(return_value={"is_stale": True}),
        ),
        patch(
            "services.technical_analysis.get_technical_analysis",
            new=AsyncMock(return_value=analysis),
        ),
    ):
        result = asyncio.run(answer_technical_question("NABIL"))

    assert "stale" in result.lower()


def test_answer_technical_question_when_stock_is_missing():
    from services.stock_mentor import answer_technical_question

    with patch(
        "services.nepse_data.get_stock",
        new=AsyncMock(return_value=None),
    ):
        result = asyncio.run(answer_technical_question("NABIL"))

    assert "No market data" in result


def test_answer_technical_question_rejects_invalid_symbol():
    from services.stock_mentor import answer_technical_question

    with pytest.raises(ValueError):
        asyncio.run(answer_technical_question("NABIL!"))


def test_answer_signal_question_formats_buy_signal():
    from services.stock_mentor import answer_signal_question

    with patch(
        "services.signals.get_stock_signal",
        new=AsyncMock(return_value={
            "signal": "BUY",
            "score": 3,
            "strength": "Moderate",
            "ltp": 600,
            "age_minutes": 10,
            "reasons": ["Bullish: SMA 20 vs SMA 50"],
        }),
    ):
        result = asyncio.run(answer_signal_question("NABIL"))

    assert "BUY" in result
    assert "NPR 600.00" in result
    assert "Bullish" in result


def test_answer_signal_question_handles_stale_data():
    from services.stock_mentor import answer_signal_question

    with patch(
        "services.signals.get_stock_signal",
        new=AsyncMock(return_value={
            "signal": "STALE_DATA",
            "score": 0,
            "strength": "Unavailable",
            "reasons": ["Latest market data is stale."],
        }),
    ):
        result = asyncio.run(answer_signal_question("NABIL"))

    assert "STALE_DATA" in result
    assert "stale" in result.lower()


def test_answer_signal_question_handles_hold_signal():
    from services.stock_mentor import answer_signal_question

    with patch(
        "services.signals.get_stock_signal",
        new=AsyncMock(return_value={
            "signal": "HOLD",
            "score": 0,
            "strength": "Weak or mixed",
            "reasons": ["Neutral or unavailable: RSI 14 momentum"],
        }),
    ):
        result = asyncio.run(answer_signal_question("NABIL"))

    assert "HOLD" in result


def test_answer_signal_question_rejects_invalid_symbol():
    from services.stock_mentor import answer_signal_question

    with pytest.raises(ValueError):
        asyncio.run(answer_signal_question("NABIL!"))


def test_answer_tradeplan_question_formats_available_plan():
    from services.stock_mentor import answer_tradeplan_question

    plan = {
        "status": "AVAILABLE",
        "trading_style": "Positional",
        "risk_tolerance": "Medium",
        "current_price": 550,
        "buying_range": {"low": 530, "high": 540},
        "selling_range": {"low": 570, "high": 590},
        "entry_reference": 535,
        "stop_loss": 520,
        "target_1": 570,
        "target_2": 590,
        "risk_reward": {"target_1": 2.33, "target_2": 3.67},
        "suggested_quantity": 100,
        "estimated_investment_npr": 53500,
        "estimated_max_loss_npr": 1500,
        "data_basis": "Historical daily LTP snapshots.",
    }

    with patch(
        "services.trade_planner.get_trade_plan",
        new=AsyncMock(return_value=plan),
    ):
        result = asyncio.run(answer_tradeplan_question("NABIL", 12345))

    assert "Positional" in result
    assert "NPR 530.00" in result
    assert "Stop-loss" in result
    assert "Target 1" in result
    assert "Estimated maximum loss" in result


def test_answer_tradeplan_question_handles_unavailable_plan():
    from services.stock_mentor import answer_tradeplan_question

    with patch(
        "services.trade_planner.get_trade_plan",
        new=AsyncMock(return_value={
            "status": "UNAVAILABLE",
            "reason": "Latest market data is stale.",
        }),
    ):
        result = asyncio.run(answer_tradeplan_question("NABIL", 12345))

    assert "unavailable" in result.lower()
    assert "stale" in result.lower()


def test_answer_tradeplan_question_handles_missing_plan():
    from services.stock_mentor import answer_tradeplan_question

    with patch(
        "services.trade_planner.get_trade_plan",
        new=AsyncMock(return_value=None),
    ):
        result = asyncio.run(answer_tradeplan_question("NABIL", 12345))

    assert "unavailable" in result.lower()


def test_answer_tradeplan_question_rejects_invalid_symbol():
    from services.stock_mentor import answer_tradeplan_question

    with pytest.raises(ValueError):
        asyncio.run(answer_tradeplan_question("NABIL!", 12345))


def test_answer_fundamental_question_formats_report():
    from services.stock_mentor import answer_fundamental_question

    company = {"symbol": "NABIL", "reports": [{"type": "Annual"}]}
    analysis = {
        "latest_report": {
            "type": "Annual",
            "fy": "2082/83",
            "quarter": None,
            "eps": 35.5,
            "pe": 18.2,
            "profit": 350000000,
            "net_worth_per_share": 210,
        },
        "comparisons": {
            "eps": {"status": "compared", "change_percent": 12.5},
            "net_worth_per_share": {"status": "insufficient_data"},
            "profit": {"status": "comparison_unverified"},
        },
        "warnings": ["EPS is not annualized."],
        "reports_analyzed": 1,
        "ambiguous_reports_excluded": 0,
    }

    with (
        patch(
            "services.fundamental_data.get_company_financials",
            new=AsyncMock(return_value=company),
        ),
        patch(
            "services.fundamental_analysis.analyze_company_reports",
            return_value=analysis,
        ),
    ):
        result = asyncio.run(answer_fundamental_question("NABIL"))

    assert "NABIL Fundamental Analysis" in result
    assert "NPR 35.50" in result
    assert "12.50%" in result
    assert "comparison unverified" in result.lower()
    assert "not annualized" in result.lower()


def test_answer_fundamental_question_handles_missing_company():
    from services.stock_mentor import answer_fundamental_question

    with patch(
        "services.fundamental_data.get_company_financials",
        new=AsyncMock(return_value=None),
    ):
        result = asyncio.run(answer_fundamental_question("NABIL"))

    assert "No fundamental financial data" in result


def test_answer_fundamental_question_handles_no_usable_reports():
    from services.stock_mentor import answer_fundamental_question

    with (
        patch(
            "services.fundamental_data.get_company_financials",
            new=AsyncMock(return_value={"symbol": "NABIL", "reports": []}),
        ),
        patch(
            "services.fundamental_analysis.analyze_company_reports",
            return_value={"latest_report": None},
        ),
    ):
        result = asyncio.run(answer_fundamental_question("NABIL"))

    assert "No usable financial reports" in result


def test_answer_fundamental_question_rejects_invalid_symbol():
    from services.stock_mentor import answer_fundamental_question

    with pytest.raises(ValueError):
        asyncio.run(answer_fundamental_question("NABIL!"))


def test_answer_portfolio_question_formats_holdings():
    from services.stock_mentor import answer_portfolio_question

    holdings = [
        {
            "symbol": "NABIL",
            "quantity": 10,
            "average_buy_price": 500,
        },
        {
            "symbol": "NICA",
            "quantity": 5,
            "average_buy_price": 600,
        },
    ]
    profile = {
        "trading_style": "Positional",
        "risk_tolerance": "Medium",
    }

    with (
        patch(
            "database.db.get_portfolio",
            new=AsyncMock(return_value=holdings),
        ),
        patch(
            "database.db.get_profile",
            new=AsyncMock(return_value=profile),
        ),
    ):
        result = asyncio.run(answer_portfolio_question(12345))

    assert "NABIL" in result
    assert "NICA" in result
    assert "10.00 shares" in result
    assert "NPR 5,000.00" in result
    assert "NPR 8,000.00" in result
    assert "Positional" in result
    assert "Medium" in result
    assert "not represent current market value" in result


def test_answer_portfolio_question_handles_empty_portfolio():
    from services.stock_mentor import answer_portfolio_question

    with (
        patch(
            "database.db.get_portfolio",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "database.db.get_profile",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = asyncio.run(answer_portfolio_question(12345))

    assert "No stock holdings" in result


def test_answer_portfolio_question_handles_missing_profile():
    from services.stock_mentor import answer_portfolio_question

    with (
        patch(
            "database.db.get_portfolio",
            new=AsyncMock(return_value=[
                {
                    "symbol": "NABIL",
                    "quantity": 2,
                    "average_buy_price": 500,
                }
            ]),
        ),
        patch(
            "database.db.get_profile",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = asyncio.run(answer_portfolio_question(12345))

    assert "NABIL" in result
    assert "Investor profile" not in result


def test_answer_portfolio_question_rejects_invalid_user_id():
    from services.stock_mentor import answer_portfolio_question

    with pytest.raises(ValueError):
        asyncio.run(answer_portfolio_question(0))


def test_answer_question_routes_technical():
    from services.stock_mentor import answer_question

    with patch(
        "services.stock_mentor.answer_technical_question",
        new=AsyncMock(return_value="Technical result"),
    ) as mocked:
        result = asyncio.run(
            answer_question("Explain NABIL technical indicators", 12345)
        )

    assert result == "Technical result"
    mocked.assert_awaited_once_with("NABIL")


def test_answer_question_routes_fundamental():
    from services.stock_mentor import answer_question

    with patch(
        "services.stock_mentor.answer_fundamental_question",
        new=AsyncMock(return_value="Fundamental result"),
    ) as mocked:
        result = asyncio.run(
            answer_question("NABIL fundamental analysis", 12345)
        )

    assert result == "Fundamental result"
    mocked.assert_awaited_once_with("NABIL")


def test_answer_question_routes_signal():
    from services.stock_mentor import answer_question

    with patch(
        "services.stock_mentor.answer_signal_question",
        new=AsyncMock(return_value="Signal result"),
    ) as mocked:
        result = asyncio.run(
            answer_question("NICA buy or sell signal", 12345)
        )

    assert result == "Signal result"
    mocked.assert_awaited_once_with("NICA")


def test_answer_question_routes_tradeplan():
    from services.stock_mentor import answer_question

    with patch(
        "services.stock_mentor.answer_tradeplan_question",
        new=AsyncMock(return_value="Trade plan result"),
    ) as mocked:
        result = asyncio.run(
            answer_question("Create a SHIVM trade plan", 12345)
        )

    assert result == "Trade plan result"
    mocked.assert_awaited_once_with("SHIVM", 12345)


def test_answer_question_routes_portfolio():
    from services.stock_mentor import answer_question

    with patch(
        "services.stock_mentor.answer_portfolio_question",
        new=AsyncMock(return_value="Portfolio result"),
    ) as mocked:
        result = asyncio.run(
            answer_question("my portfolio", 12345)
        )

    assert result == "Portfolio result"
    mocked.assert_awaited_once_with(12345)


def test_answer_question_explains_general_question():
    from services.stock_mentor import answer_question

    result = asyncio.run(
        answer_question("What does RSI mean?", 12345)
    )

    assert "Relative Strength Index" in result


def test_answer_question_requests_symbol_for_technical():
    from services.stock_mentor import answer_question

    result = asyncio.run(
        answer_question("Explain technical indicators", 12345)
    )

    assert "include a stock symbol" in result.lower()
