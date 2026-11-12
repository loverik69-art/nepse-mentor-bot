
import math

def calculate_sma(prices: list[float], period: int) -> float | None:
    """Calculate SMA using the most recent prices."""

    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise ValueError("Period must be a positive integer")

    for price in prices:
        if (
            not isinstance(price, (int, float))
            or isinstance(price, bool)
            or not math.isfinite(price)
            or price <= 0
        ):
            raise ValueError(
                "Prices must be finite positive numbers"
            )

    if len(prices) < period:
        return None

    return sum(prices[-period:]) / period

def calculate_ema(prices: list[float], period: int) -> float | None:
    """Calculate Exponential Moving Average.

    Prices must be ordered oldest to newest.
    """

    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise ValueError("Period must be a positive integer")

    for price in prices:
        if (
            not isinstance(price, (int, float))
            or isinstance(price, bool)
            or not math.isfinite(price)
            or price <= 0
        ):
            raise ValueError(
                "Prices must be finite positive numbers"
            )

    if len(prices) < period:
        return None

    ema = sum(prices[:period]) / period
    multiplier = 2 / (period + 1)

    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema

    return ema

def calculate_rsi(prices: list[float], period: int = 14) -> float | None:
    """Calculate RSI using Wilder's smoothing method."""

    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise ValueError("Period must be a positive integer")

    for price in prices:
        if (
            not isinstance(price, (int, float))
            or isinstance(price, bool)
            or not math.isfinite(price)
            or price <= 0
        ):
            raise ValueError(
                "Prices must be finite positive numbers"
            )

    if len(prices) < period + 1:
        return None

    changes = [
        prices[index] - prices[index - 1]
        for index in range(1, len(prices))
    ]

    gains = [max(change, 0) for change in changes]
    losses = [max(-change, 0) for change in changes]

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    for index in range(period, len(changes)):
        average_gain = (
            (average_gain * (period - 1) + gains[index])
            / period
        )
        average_loss = (
            (average_loss * (period - 1) + losses[index])
            / period
        )

    if average_loss == 0:
        if average_gain == 0:
            return 50.0
        return 100.0

    relative_strength = average_gain / average_loss

    return 100 - (100 / (1 + relative_strength))

def calculate_macd(
    prices: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict | None:
    """Calculate MACD, signal line and histogram."""

    periods = (fast_period, slow_period, signal_period)

    if (
        any(
            not isinstance(period, int)
            or isinstance(period, bool)
            or period < 1
            for period in periods
        )
        or fast_period >= slow_period
    ):

        raise ValueError("Invalid MACD periods")

    for price in prices:
        if (
            not isinstance(price, (int, float))
            or isinstance(price, bool)
            or not math.isfinite(price)
            or price <= 0
        ):
            raise ValueError(
                "Prices must be finite positive numbers"
            )

    if len(prices) < slow_period + signal_period - 1:
        return None

    def ema_series(values, period):
        if len(values) < period:
            return []

        ema = sum(values[:period]) / period
        multiplier = 2 / (period + 1)
        result = [ema]

        for value in values[period:]:
            ema = (
                (value - ema) * multiplier
                + ema
            )
            result.append(ema)

        return result

    fast_ema = ema_series(prices, fast_period)
    slow_ema = ema_series(prices, slow_period)

    offset = slow_period - fast_period

    macd_values = [
        fast_ema[index + offset] - slow_ema[index]
        for index in range(len(slow_ema))
    ]

    signal_values = ema_series(
        macd_values,
        signal_period,
    )

    macd_line = macd_values[-1]
    signal_line = signal_values[-1]

    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": macd_line - signal_line,
    }


