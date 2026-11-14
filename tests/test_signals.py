import asyncio
import pytest

from services.signals import generate_signal, get_stock_signal


def make_analysis(
    sma_20=110,
    sma_50=100,
    ema_20=110,
    ema_50=100,
    rsi_14=60,
    macd_value=2,
    macd_signal=1,
    observations=60,
):
    return {
        "symbol": "NABIL",
        "observations": observations,
        "indicators": {
            "sma_20": sma_20,
            "sma_50": sma_50,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "rsi_14": rsi_14,
            "macd": (
                None
                if macd_value is None or macd_signal is None
                else {
                    "macd": macd_value,
                    "signal": macd_signal,
                    "histogram": macd_value - macd_signal,
                }
            ),
        },
    }


def test_bullish_conditions_generate_buy():
    result = generate_signal(make_analysis())

    assert result["signal"] == "BUY"
    assert result["score"] == 3


def test_bearish_conditions_generate_sell():
    analysis = make_analysis(
        sma_20=90,
        sma_50=100,
        ema_20=90,
        ema_50=100,
        rsi_14=40,
        macd_value=-2,
        macd_signal=-1,
    )

    result = generate_signal(analysis)

    assert result["signal"] == "SELL"
    assert result["score"] == -3


def test_disagreeing_trends_do_not_double_count():
    analysis = make_analysis(
        sma_20=110,
        sma_50=100,
        ema_20=90,
        ema_50=100,
        rsi_14=40,
        macd_value=2,
        macd_signal=1,
    )

    result = generate_signal(analysis)

    assert result["signal"] == "HOLD"
    assert result["score"] == 0
    assert any("Neutral: SMA and EMA" in reason for reason in result["reasons"])


@pytest.mark.parametrize("rsi", [30, 70])
def test_extreme_rsi_is_neutral_with_caution(rsi):
    result = generate_signal(make_analysis(rsi_14=rsi))

    assert result["signal"] == "BUY"
    assert result["score"] == 2
    assert any("Caution:" in reason for reason in result["reasons"])


def test_missing_indicators_do_not_add_score():
    analysis = make_analysis(
        sma_20=None,
        sma_50=None,
        ema_20=None,
        ema_50=None,
        rsi_14=None,
        macd_value=None,
        macd_signal=None,
    )

    result = generate_signal(analysis)

    assert result["signal"] == "HOLD"
    assert result["score"] == 0


def test_insufficient_history_withholds_signal():
    result = generate_signal(
        make_analysis(observations=10)
    )

    assert result["signal"] == "INSUFFICIENT_DATA"
    assert result["score"] == 0


def test_stale_data_withholds_signal():
    result = generate_signal(
        make_analysis(),
        is_stale=True,
    )

    assert result["signal"] == "STALE_DATA"
    assert result["score"] == 0


def test_invalid_analysis_is_rejected():
    with pytest.raises(ValueError):
        generate_signal({})


@pytest.mark.parametrize(
    "field,value",
    [
        ("sma_20", float("nan")),
        ("ema_20", float("inf")),
        ("rsi_14", "invalid"),
        ("sma_50", True),
    ],
)
def test_invalid_indicator_values_are_rejected(field, value):
    analysis = make_analysis()
    analysis["indicators"][field] = value

    with pytest.raises(ValueError):
        generate_signal(analysis)


def test_rsi_outside_valid_range_is_rejected():
    analysis = make_analysis(rsi_14=101)

    with pytest.raises(ValueError):
        generate_signal(analysis)


@pytest.mark.parametrize(
    "macd_value",
    [
        {"macd": float("nan"), "signal": 1, "histogram": 1},
        {"macd": 2, "signal": float("inf"), "histogram": 1},
        {"macd": 2, "signal": 1, "histogram": "bad"},
    ],
)
def test_invalid_macd_values_are_rejected(macd_value):
    analysis = make_analysis()
    analysis["indicators"]["macd"] = macd_value

    with pytest.raises(ValueError):
        generate_signal(analysis)


def test_get_stock_signal_combines_fresh_market_and_technical_data(monkeypatch):
    import services.signals as signals

    async def fake_get_stock(symbol):
        assert symbol == "NABIL"
        return {
            "symbol": "NABIL",
            "ltp": 550.0,
            "is_stale": False,
            "last_updated": "2026-11-13T14:59:00+05:45",
            "age_minutes": 5,
        }

    async def fake_analysis(symbol):
        return {
            **make_analysis(),
            "data_basis": "Daily stored snapshots",
        }

    monkeypatch.setattr(signals, "get_stock", fake_get_stock)
    monkeypatch.setattr(
        signals,
        "get_technical_analysis",
        fake_analysis,
    )

    result = asyncio.run(get_stock_signal("nabil"))

    assert result["symbol"] == "NABIL"
    assert result["signal"] == "BUY"
    assert result["ltp"] == 550.0
    assert result["age_minutes"] == 5
    assert result["observations"] == 60


def test_get_stock_signal_marks_stale_market_data(monkeypatch):
    import services.signals as signals

    async def fake_get_stock(symbol):
        return {
            "symbol": "NABIL",
            "ltp": 550.0,
            "is_stale": True,
            "last_updated": "2026-11-10T14:59:00+05:45",
            "age_minutes": 4000,
        }

    async def fake_analysis(symbol):
        return {
            **make_analysis(),
            "data_basis": "Daily stored snapshots",
        }

    monkeypatch.setattr(signals, "get_stock", fake_get_stock)
    monkeypatch.setattr(
        signals,
        "get_technical_analysis",
        fake_analysis,
    )

    result = asyncio.run(get_stock_signal("NABIL"))

    assert result["signal"] == "STALE_DATA"
    assert result["score"] == 0


def test_get_stock_signal_rejects_unknown_symbol(monkeypatch):
    import services.signals as signals

    async def fake_get_stock(symbol):
        return None

    monkeypatch.setattr(signals, "get_stock", fake_get_stock)

    with pytest.raises(ValueError, match="Stock not found"):
        asyncio.run(get_stock_signal("UNKNOWN"))
