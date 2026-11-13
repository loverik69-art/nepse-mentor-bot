from services.nepse_data import get_stock
from services.technical_analysis import get_technical_analysis

import math


def generate_signal(
    analysis: dict,
    is_stale: bool = False,
) -> dict:
    """Generate an educational signal from technical indicators."""

    if not isinstance(analysis, dict):
        raise ValueError("Analysis must be a dictionary")

    symbol = analysis.get("symbol")
    observations = analysis.get("observations")
    indicators = analysis.get("indicators")

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Analysis must contain a valid symbol")

    if (
        isinstance(observations, bool)
        or not isinstance(observations, int)
        or observations < 0
    ):
        raise ValueError("Invalid observation count")

    if not isinstance(indicators, dict):
        raise ValueError("Analysis must contain indicators")

    numeric_fields = (
        "sma_20",
        "sma_50",
        "ema_20",
        "ema_50",
        "rsi_14",
    )

    for field in numeric_fields:
        value = indicators.get(field)

        if value is None:
            continue

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"Invalid indicator: {field}")

        if field == "rsi_14" and not 0 <= value <= 100:
            raise ValueError("RSI must be between 0 and 100")

        if field != "rsi_14" and value <= 0:
            raise ValueError(f"{field} must be positive")

    macd = indicators.get("macd")

    if macd is not None:
        if not isinstance(macd, dict):
            raise ValueError("Invalid MACD data")

        for field in ("macd", "signal", "histogram"):
            value = macd.get(field)

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"Invalid MACD value: {field}")

    if is_stale:
        return {
            "symbol": symbol,
            "signal": "STALE_DATA",
            "score": 0,
            "strength": "Unavailable",
            "reasons": [
                "Latest market data is stale; no actionable signal generated."
            ],
        }

    if observations < 50:
        return {
            "symbol": symbol,
            "signal": "INSUFFICIENT_DATA",
            "score": 0,
            "strength": "Unavailable",
            "reasons": [
                "At least 50 daily observations are required."
            ],
        }

    score = 0
    reasons = []

    def add_condition(name, bullish, bearish):
        nonlocal score

        if bullish:
            score += 1
            reasons.append(f"Bullish: {name}")
        elif bearish:
            score -= 1
            reasons.append(f"Bearish: {name}")
        else:
            reasons.append(f"Neutral or unavailable: {name}")

    sma_20 = indicators.get("sma_20")
    sma_50 = indicators.get("sma_50")
    ema_20 = indicators.get("ema_20")
    ema_50 = indicators.get("ema_50")
    rsi = indicators.get("rsi_14")
    macd = indicators.get("macd")

    add_condition(
        "SMA 20 vs SMA 50",
        sma_20 is not None and sma_50 is not None and sma_20 > sma_50,
        sma_20 is not None and sma_50 is not None and sma_20 < sma_50,
    )

    add_condition(
        "EMA 20 vs EMA 50",
        ema_20 is not None and ema_50 is not None and ema_20 > ema_50,
        ema_20 is not None and ema_50 is not None and ema_20 < ema_50,
    )

    add_condition(
        "RSI 14 momentum",
        rsi is not None and 50 < rsi < 70,
        rsi is not None and 30 < rsi < 50,
    )

    add_condition(
        "MACD vs signal line",
        (
            isinstance(macd, dict)
            and macd.get("macd") is not None
            and macd.get("signal") is not None
            and macd["macd"] > macd["signal"]
        ),
        (
            isinstance(macd, dict)
            and macd.get("macd") is not None
            and macd.get("signal") is not None
            and macd["macd"] < macd["signal"]
        ),
    )

    if score >= 3:
        signal = "BUY"
    elif score <= -3:
        signal = "SELL"
    else:
        signal = "HOLD"

    strength = (
        "Strong"
        if abs(score) == 4
        else "Moderate"
        if abs(score) == 3
        else "Weak or mixed"
    )

    if rsi is not None:
        if rsi >= 70:
            reasons.append("Caution: RSI is overbought.")
        elif rsi <= 30:
            reasons.append("Caution: RSI is oversold.")

    return {
        "symbol": symbol.strip().upper(),
        "signal": signal,
        "score": score,
        "strength": strength,
        "reasons": reasons,
    }


async def get_stock_signal(symbol: str) -> dict:
    """Combine current market data and technical analysis into a signal."""

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Please provide a valid stock symbol")

    symbol = symbol.strip().upper()
    stock = await get_stock(symbol)

    if stock is None:
        raise ValueError(f"Stock not found: {symbol}")

    analysis = await get_technical_analysis(symbol)

    result = generate_signal(
        analysis,
        is_stale=stock["is_stale"],
    )

    result.update({
        "ltp": stock["ltp"],
        "last_updated": stock["last_updated"],
        "age_minutes": stock["age_minutes"],
        "observations": analysis["observations"],
        "data_basis": analysis["data_basis"],
    })

    return result
