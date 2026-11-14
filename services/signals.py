import math

from services.nepse_data import get_stock
from services.technical_analysis import get_technical_analysis


def generate_signal(
    analysis: dict,
    is_stale: bool = False,
) -> dict:
    """Generate a balanced educational signal from technical indicators."""

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
        "sma_20", "sma_50", "ema_20", "ema_50", "rsi_14",
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
            "symbol": symbol.strip().upper(),
            "signal": "STALE_DATA",
            "score": 0,
            "strength": "Unavailable",
            "confidence": None,
            "quality": "Unavailable",
            "data_coverage": 0.0,
            "available_factors": 0,
            "supporting_factors": 0,
            "reasons": [
                "Latest market data is stale; no actionable signal generated."
            ],
        }

    if observations < 50:
        return {
            "symbol": symbol.strip().upper(),
            "signal": "INSUFFICIENT_DATA",
            "score": 0,
            "strength": "Unavailable",
            "confidence": None,
            "quality": "Unavailable",
            "data_coverage": 0.0,
            "available_factors": 0,
            "supporting_factors": 0,
            "reasons": [
                "At least 50 daily observations are required."
            ],
        }

    score = 0
    available_factors = 0
    factor_directions = []
    reasons = []

    def add_factor(name, direction):
        nonlocal score, available_factors

        if direction is None:
            reasons.append(f"Neutral or unavailable: {name}")
            return

        available_factors += 1
        factor_directions.append(direction)

        if direction > 0:
            score += 1
            reasons.append(f"Bullish: {name}")
        elif direction < 0:
            score -= 1
            reasons.append(f"Bearish: {name}")
        else:
            reasons.append(f"Neutral: {name}")

    sma_20 = indicators.get("sma_20")
    sma_50 = indicators.get("sma_50")
    ema_20 = indicators.get("ema_20")
    ema_50 = indicators.get("ema_50")
    rsi = indicators.get("rsi_14")

    # Factor 1: SMA and EMA must agree on the trend.
    if all(
        value is not None
        for value in (sma_20, sma_50, ema_20, ema_50)
    ):
        sma_bullish = sma_20 > sma_50
        sma_bearish = sma_20 < sma_50
        ema_bullish = ema_20 > ema_50
        ema_bearish = ema_20 < ema_50

        if sma_bullish and ema_bullish:
            add_factor("SMA and EMA trend agreement", 1)
        elif sma_bearish and ema_bearish:
            add_factor("SMA and EMA trend agreement", -1)
        else:
            add_factor("SMA and EMA trend agreement", 0)
    else:
        add_factor("SMA and EMA trend agreement", None)

    # Factor 2: RSI momentum. Extreme readings are cautions, not signals.
    if rsi is None:
        add_factor("RSI 14 momentum", None)
    elif 50 < rsi < 70:
        add_factor("RSI 14 momentum", 1)
    elif 30 < rsi < 50:
        add_factor("RSI 14 momentum", -1)
    else:
        add_factor("RSI 14 momentum", 0)

    if rsi is not None:
        if rsi >= 70:
            reasons.append("Caution: RSI is overbought.")
        elif rsi <= 30:
            reasons.append("Caution: RSI is oversold.")

    # Factor 3: MACD confirmation.
    if macd is None:
        add_factor("MACD vs signal line", None)
    elif macd["macd"] > macd["signal"]:
        add_factor("MACD vs signal line", 1)
    elif macd["macd"] < macd["signal"]:
        add_factor("MACD vs signal line", -1)
    else:
        add_factor("MACD vs signal line", 0)

    if score >= 2:
        signal = "BUY"
    elif score <= -2:
        signal = "SELL"
    else:
        signal = "HOLD"

    if available_factors == 3 and abs(score) == 3:
        strength = "Strong"
    elif available_factors >= 2 and abs(score) >= 2:
        strength = "Moderate"
    else:
        strength = "Weak or mixed"

    supporting_factors = (
        sum(1 for direction in factor_directions if direction > 0)
        if signal == "BUY"
        else sum(1 for direction in factor_directions if direction < 0)
        if signal == "SELL"
        else 0
    )

    confidence = (
        round(supporting_factors / available_factors * 100, 1)
        if signal in ("BUY", "SELL") and available_factors
        else None
    )

    data_coverage = round(available_factors / 3 * 100, 1)

    if signal == "HOLD":
        quality = "Neutral / mixed"
    elif available_factors == 3 and supporting_factors == 3:
        quality = "High"
    elif available_factors >= 2 and confidence >= 66.7:
        quality = "Moderate"
    else:
        quality = "Low"

    return {
        "symbol": symbol.strip().upper(),
        "signal": signal,
        "score": score,
        "strength": strength,
        "confidence": confidence,
        "quality": quality,
        "data_coverage": data_coverage,
        "available_factors": available_factors,
        "supporting_factors": supporting_factors,
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
