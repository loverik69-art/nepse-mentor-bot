import pytest

from services import backtesting as bt


@pytest.mark.parametrize(
    ("symbol", "horizons", "limit", "expected"),
    [
        (" nabil ", (5, 10, 20), 5000, ("NABIL", (5, 10, 20))),
        ("ebl", [5, 10], 100, ("EBL", (5, 10))),
    ],
)
def test_validate_backtest_inputs_valid(
    symbol,
    horizons,
    limit,
    expected,
):
    assert bt._validate_backtest_inputs(
        symbol,
        horizons,
        limit,
    ) == expected


@pytest.mark.parametrize(
    ("symbol", "horizons", "limit"),
    [
        ("", (5,), 100),
        ("   ", (5,), 100),
        (None, (5,), 100),
        ("NABIL", (), 100),
        ("NABIL", "5", 100),
        ("NABIL", (0,), 100),
        ("NABIL", (-1,), 100),
        ("NABIL", (True,), 100),
        ("NABIL", (1.5,), 100),
        ("NABIL", (5, 5), 100),
        ("NABIL", (5,), 0),
        ("NABIL", (5,), True),
    ],
)
def test_validate_backtest_inputs_invalid(
    symbol,
    horizons,
    limit,
):
    with pytest.raises(ValueError):
        bt._validate_backtest_inputs(
            symbol,
            horizons,
            limit,
        )


@pytest.mark.parametrize(
    ("entry", "exit_price", "action", "expected"),
    [
        (100, 110, "BUY", 10),
        (100, 90, "BUY", -10),
        (100, 90, "SELL", 10),
        (100, 110, "SELL", -10),
    ],
)
def test_calculate_forward_return(
    entry,
    exit_price,
    action,
    expected,
):
    assert bt._calculate_forward_return(
        entry,
        exit_price,
        action,
    ) == pytest.approx(expected)


def test_calculate_forward_return_rejects_hold():
    with pytest.raises(ValueError):
        bt._calculate_forward_return(100, 110, "HOLD")


def test_summarize_horizon_with_wins_and_losses():
    result = bt._summarize_horizon([
        {"return_pct": 10.0},
        {"return_pct": -5.0},
        {"return_pct": 5.0},
        {"return_pct": 0.0},
    ])

    assert result == {
        "trades": 4,
        "wins": 2,
        "losses": 1,
        "win_rate_pct": 50.0,
        "average_return_pct": 2.5,
    }


def test_summarize_horizon_empty():
    assert bt._summarize_horizon([]) == {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_pct": None,
        "average_return_pct": None,
    }


def test_backtest_uses_next_observation_and_no_future_data(
    monkeypatch,
):
    import asyncio

    rows = [
        {
            "trading_date": f"2026-01-{i + 1:02d}",
            "ltp": 100.0 + i,
        }
        for i in range(60)
    ]

    async def fake_history(symbol, limit):
        assert symbol == "NABIL"
        return rows[:limit]

    observed_lengths = []

    def fake_analysis(symbol, prices):
        observed_lengths.append(len(prices))
        return {"observations": len(prices)}

    def fake_signal(analysis):
        count = analysis["observations"]

        if count == 50:
            return {"signal": "BUY"}
        if count == 51:
            return {"signal": "SELL"}
        return {"signal": "HOLD"}

    monkeypatch.setattr(bt, "get_daily_price_history", fake_history)
    monkeypatch.setattr(bt, "_build_historical_analysis", fake_analysis)
    monkeypatch.setattr(bt, "generate_signal", fake_signal)

    result = asyncio.run(
        bt.backtest_symbol(" nabil ", horizons=(1, 2), limit=60)
    )

    assert observed_lengths == list(range(50, 60))
    assert result["signals"] == {
        "BUY": 1,
        "SELL": 1,
        "HOLD": 8,
    }

    one_day = result["results"][1]
    assert one_day["trades"] == 2
    assert one_day["buy_trades"] == 1
    assert one_day["sell_trades"] == 1

    expected_buy = (151 - 150) / 150 * 100
    expected_sell = (151 - 152) / 151 * 100

    assert one_day["average_return_pct"] == pytest.approx(
        round((expected_buy + expected_sell) / 2, 2)
    )


def test_backtest_handles_insufficient_history(monkeypatch):
    import asyncio

    async def fake_history(symbol, limit):
        return [
            {"trading_date": f"2026-01-{i + 1:02d}", "ltp": 100 + i}
            for i in range(50)
        ]

    monkeypatch.setattr(bt, "get_daily_price_history", fake_history)

    result = asyncio.run(
        bt.backtest_symbol("NABIL", horizons=(5,), limit=100)
    )

    assert result["observations"] == 50
    assert result["signals"] == {"BUY": 0, "SELL": 0, "HOLD": 0}
    assert result["results"][5]["trades"] == 0
    assert "51 daily observations" in result["message"]
