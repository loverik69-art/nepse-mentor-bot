
import pytest

from services.indicators import calculate_sma
from services.indicators import calculate_ema
from services.indicators import calculate_rsi
from services.indicators import calculate_macd

def test_sma_calculates_average():
    assert calculate_sma([10, 20, 30], 3) == 20


def test_sma_uses_requested_period():
    assert calculate_sma([10, 20, 30], 2) == 25


def test_sma_returns_none_when_history_is_insufficient():
    assert calculate_sma([10, 20], 3) is None


def test_sma_rejects_invalid_period():
    with pytest.raises(ValueError):
        calculate_sma([10, 20], 0)


@pytest.mark.parametrize(
    "prices",
    [
        [0, 20],
        [-10, 20],
        [float("nan"), 20],
        [float("inf"), 20],
        ["invalid", 20],
    ],
)
def test_sma_rejects_invalid_prices(prices):
    with pytest.raises(ValueError):
        calculate_sma(prices, 2)

def test_ema_calculates_average():
    assert calculate_ema([10, 20, 30], 2) == 25


def test_ema_uses_sma_as_initial_value():
    assert calculate_ema([10, 20, 30], 3) == 20


def test_ema_returns_none_when_history_is_insufficient():
    assert calculate_ema([10, 20], 3) is None


def test_ema_rejects_invalid_period():
    with pytest.raises(ValueError):
        calculate_ema([10, 20], 0)


@pytest.mark.parametrize(
    "prices",
    [
        [0, 20],
        [-10, 20],
        [float("nan"), 20],
        [float("inf"), 20],
        ["invalid", 20],
    ],
)
def test_ema_rejects_invalid_prices(prices):
    with pytest.raises(ValueError):
        calculate_ema(prices, 2)

def test_rsi_returns_100_for_only_gains():
    assert calculate_rsi(
        [10, 11, 12, 13, 14, 15], 5
    ) == 100.0


def test_rsi_returns_zero_for_only_losses():
    assert calculate_rsi(
        [15, 14, 13, 12, 11, 10], 5
    ) == 0.0


def test_rsi_returns_50_for_no_price_movement():
    assert calculate_rsi(
        [10, 10, 10, 10, 10, 10], 5
    ) == 50.0


def test_rsi_returns_none_when_history_is_insufficient():
    assert calculate_rsi([10, 11, 12], 3) is None


def test_rsi_rejects_invalid_period():
    with pytest.raises(ValueError):
        calculate_rsi([10, 11], 0)


@pytest.mark.parametrize(
    "prices",
    [
        [0, 11],
        [-10, 11],
        [float("nan"), 11],
        [float("inf"), 11],
        ["invalid", 11],
    ],
)
def test_rsi_rejects_invalid_prices(prices):
    with pytest.raises(ValueError):
        calculate_rsi(prices, 1)

def test_macd_returns_expected_values():
    result = calculate_macd(
        list(range(1, 36))
    )

    assert result is not None
    assert set(result) == {"macd", "signal", "histogram"}
    assert result["macd"] > 0
    assert result["signal"] > 0


def test_macd_histogram_equals_macd_minus_signal():
    result = calculate_macd(list(range(1, 36)))

    assert result is not None
    assert result["histogram"] == pytest.approx(
        result["macd"] - result["signal"]
    )


def test_macd_returns_none_when_history_is_insufficient():
    assert calculate_macd(list(range(1, 34))) is None

@pytest.mark.parametrize(
    "fast, slow, signal",
    [
        (26, 12, 9),
        (0, 26, 9),
        (12, 26, 0),
        (12.5, 26, 9),
        (12, True, 9),
        (12, 26, 9.5),
    ],
)
def test_macd_rejects_invalid_periods(fast, slow, signal):
    with pytest.raises(ValueError):
        calculate_macd(
            list(range(1, 36)),
            fast_period=fast,
            slow_period=slow,
            signal_period=signal,
        )

def test_macd_rejects_invalid_prices():
    with pytest.raises(ValueError):
        calculate_macd(
            [10, 11, 12, float("nan")]
        )
