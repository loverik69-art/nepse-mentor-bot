import asyncio
from unittest.mock import AsyncMock

import pytest
import services.trade_planner as trade_planner

from services.trade_planner import (
    STYLE_LOOKBACKS,
    generate_trade_plan,
)


def sample_profile(
    style="Swing",
    risk_tolerance="Medium",
    capital=100000,
    max_risk_pct=2,
):
    return {
        "trading_style": style,
        "risk_tolerance": risk_tolerance,
        "capital_npr": capital,
        "max_risk_pct": max_risk_pct,
    }


def sample_prices(count=30):
    pattern = [100, 105, 110, 115, 120, 125, 130, 135, 140, 145]
    return (pattern * ((count + len(pattern) - 1) // len(pattern)))[:count]


def make_plan(
    *,
    style="Swing",
    risk_tolerance="Medium",
    capital=100000,
    max_risk_pct=2,
    current_price=120,
    prices=None,
    is_stale=False,
):
    if prices is None:
        prices = sample_prices(STYLE_LOOKBACKS[style])

    return generate_trade_plan(
        "nabil",
        current_price,
        prices,
        sample_profile(
            style=style,
            risk_tolerance=risk_tolerance,
            capital=capital,
            max_risk_pct=max_risk_pct,
        ),
        is_stale=is_stale,
    )


@pytest.mark.parametrize(
    "style,count",
    [
        ("Swing", 30),
        ("Positional", 90),
        ("Long-Term", 180),
    ],
)
def test_generates_plan_for_each_trading_style(style, count):
    result = make_plan(style=style)

    assert result["status"] == "AVAILABLE"
    assert result["symbol"] == "NABIL"
    assert result["trading_style"] == style
    assert result["lookback_observations"] == count


def test_plan_contains_required_price_levels():
    result = make_plan()

    assert result["status"] == "AVAILABLE"
    assert result["buying_range"]["low"] < result["buying_range"]["high"]
    assert result["stop_loss"] < result["entry_reference"]
    assert result["entry_reference"] < result["target_1"]
    assert result["target_1"] < result["target_2"]
    assert result["selling_range"]["low"] == result["target_1"]
    assert result["selling_range"]["high"] == result["target_2"]


def test_plan_contains_risk_and_position_sizing():
    result = make_plan()

    assert result["risk_budget_npr"] == 2000
    assert result["suggested_quantity"] > 0
    assert result["estimated_investment_npr"] <= 100000
    assert result["estimated_max_loss_npr"] <= 2000


def test_risk_tolerance_changes_entry_conservatism():
    low = make_plan(risk_tolerance="Low")
    medium = make_plan(risk_tolerance="Medium")
    high = make_plan(risk_tolerance="High")

    assert low["entry_reference"] < medium["entry_reference"]
    assert medium["entry_reference"] < high["entry_reference"]


def test_maximum_risk_percentage_controls_risk_budget():
    result = make_plan(max_risk_pct=1)

    assert result["risk_budget_npr"] == 1000
    assert result["estimated_max_loss_npr"] <= 1000


def test_stale_data_returns_unavailable():
    result = make_plan(is_stale=True)

    assert result["status"] == "UNAVAILABLE"
    assert "stale" in result["reason"].lower()


@pytest.mark.parametrize(
    "style,count",
    [
        ("Swing", 29),
        ("Positional", 89),
        ("Long-Term", 179),
    ],
)
def test_insufficient_history_returns_unavailable(style, count):
    result = make_plan(
        style=style,
        prices=sample_prices(count),
    )

    assert result["status"] == "UNAVAILABLE"
    assert "observations" in result["reason"]


def test_current_price_outside_historical_clusters_returns_unavailable():
    result = make_plan(current_price=200)

    assert result["status"] == "UNAVAILABLE"


def test_flat_history_returns_unavailable():
    result = make_plan(prices=[100] * 30)

    assert result["status"] == "UNAVAILABLE"


@pytest.mark.parametrize(
    "prices",
    [
        [100] * 29 + [0],
        [100] * 29 + [-1],
        [100] * 29 + [float("nan")],
        [100] * 29 + [float("inf")],
        [100] * 29 + ["invalid"],
    ],
)
def test_invalid_historical_prices_are_rejected(prices):
    with pytest.raises(ValueError):
        make_plan(prices=prices)


@pytest.mark.parametrize(
    "current_price",
    [0, -1, float("nan"), float("inf"), True, "120"],
)
def test_invalid_current_price_is_rejected(current_price):
    with pytest.raises(ValueError):
        make_plan(current_price=current_price)


@pytest.mark.parametrize(
    "profile",
    [
        None,
        {},
        sample_profile(style="Unknown"),
        sample_profile(risk_tolerance="Extreme"),
        sample_profile(capital=0),
        sample_profile(capital=-100),
        sample_profile(capital=float("nan")),
        sample_profile(max_risk_pct=0),
        sample_profile(max_risk_pct=5.1),
        sample_profile(max_risk_pct=float("inf")),
    ],
)
def test_invalid_profiles_are_rejected(profile):
    with pytest.raises(ValueError):
        generate_trade_plan(
            "NABIL",
            120,
            sample_prices(),
            profile,
        )


def test_empty_symbol_is_rejected():
    with pytest.raises(ValueError):
        generate_trade_plan(
            "",
            120,
            sample_prices(),
            sample_profile(),
        )


def test_price_history_must_be_a_list():
    with pytest.raises(ValueError):
        make_plan(prices=(100, 105, 110))


def test_methodology_discloses_historical_data_limitations():
    result = make_plan()

    assert "historical" in result["methodology"].lower()
    assert "not verified official closing prices" in result["data_basis"].lower()
    assert "not" in result["data_basis"].lower()


def integration_profile():
    return sample_profile()


def integration_stock(stale=False):
    return {"symbol": "NABIL", "ltp": 120, "is_stale": stale}


def integration_history():
    return [
        {"trading_date": f"2026-01-{i:02d}", "ltp": price}
        for i, price in enumerate(sample_prices(30), 1)
    ]


def mock_trade_plan_dependencies(monkeypatch):
    monkeypatch.setattr(
        trade_planner, "get_profile",
        AsyncMock(return_value=integration_profile()),
    )
    monkeypatch.setattr(
        trade_planner, "get_stock",
        AsyncMock(return_value=integration_stock()),
    )
    monkeypatch.setattr(
        trade_planner, "get_daily_price_history",
        AsyncMock(return_value=integration_history()),
    )


def test_get_trade_plan_requires_profile(monkeypatch):
    monkeypatch.setattr(
        trade_planner, "get_profile",
        AsyncMock(return_value=None),
    )
    result = asyncio.run(trade_planner.get_trade_plan("nabil", 12345))
    assert result["status"] == "UNAVAILABLE"
    assert "create your profile" in result["reason"].lower()


def test_get_trade_plan_requires_market_quote(monkeypatch):
    mock_trade_plan_dependencies(monkeypatch)
    monkeypatch.setattr(
        trade_planner, "get_stock",
        AsyncMock(return_value=None),
    )
    result = asyncio.run(trade_planner.get_trade_plan("nabil", 12345))
    assert result["status"] == "UNAVAILABLE"
    assert "no current market quote" in result["reason"].lower()


def test_get_trade_plan_generates_successfully(monkeypatch):
    mock_trade_plan_dependencies(monkeypatch)
    result = asyncio.run(trade_planner.get_trade_plan("nabil", 12345))
    assert result["status"] == "AVAILABLE"
    assert result["symbol"] == "NABIL"
    assert result["suggested_quantity"] > 0
    trade_planner.get_daily_price_history.assert_awaited_once()


def test_get_trade_plan_rejects_stale_market_quote(monkeypatch):
    mock_trade_plan_dependencies(monkeypatch)
    monkeypatch.setattr(
        trade_planner,
        "get_stock",
        AsyncMock(return_value=integration_stock(stale=True)),
    )

    result = asyncio.run(trade_planner.get_trade_plan("nabil", 12345))

    assert result["status"] == "UNAVAILABLE"
    assert "stale" in result["reason"].lower()
    trade_planner.get_daily_price_history.assert_not_awaited()


def test_get_trade_plan_rejects_insufficient_history(monkeypatch):
    mock_trade_plan_dependencies(monkeypatch)
    monkeypatch.setattr(
        trade_planner,
        "get_daily_price_history",
        AsyncMock(return_value=integration_history()[:10]),
    )

    result = asyncio.run(trade_planner.get_trade_plan("nabil", 12345))

    assert result["status"] == "UNAVAILABLE"
    assert "30 daily observations" in result["reason"].lower()


def test_get_trade_plan_rejects_malformed_history(monkeypatch):
    mock_trade_plan_dependencies(monkeypatch)
    monkeypatch.setattr(
        trade_planner,
        "get_daily_price_history",
        AsyncMock(return_value=[{"trading_date": "2026-01-01"}]),
    )

    with pytest.raises(ValueError, match="unexpected format"):
        asyncio.run(trade_planner.get_trade_plan("nabil", 12345))


@pytest.mark.parametrize("telegram_id", [0, -1, True, "12345", None])
def test_get_trade_plan_rejects_invalid_telegram_id(
    monkeypatch,
    telegram_id,
):
    profile_mock = AsyncMock()
    monkeypatch.setattr(trade_planner, "get_profile", profile_mock)

    with pytest.raises(ValueError, match="Telegram user ID"):
        asyncio.run(
            trade_planner.get_trade_plan("NABIL", telegram_id)
        )

    profile_mock.assert_not_awaited()
