from database.db import get_indicator_prices

from services.indicators import (
    calculate_sma,
    calculate_ema,
    calculate_rsi,
    calculate_macd,
)


async def get_technical_analysis(
    symbol: str,
    limit: int = 250,
) -> dict:
    """Calculate technical indicators from daily stock snapshots."""

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Symbol must not be empty")

    symbol = symbol.strip().upper()

    prices = await get_indicator_prices(
        symbol,
        limit=limit,
    )

    return {
        "symbol": symbol,
        "observations": len(prices),
        "data_basis": (
            "Latest daily snapshots, not verified official closing prices"
        ),
        "required_history": {
            "sma_20": 20,
            "sma_50": 50,
            "ema_20": 20,
            "ema_50": 50,
            "rsi_14": 15,
            "macd": 34,
        },
        "indicators": {
            "sma_20": calculate_sma(prices, 20),
            "sma_50": calculate_sma(prices, 50),
            "ema_20": calculate_ema(prices, 20),
            "ema_50": calculate_ema(prices, 50),
            "rsi_14": calculate_rsi(prices, 14),
            "macd": calculate_macd(prices),
        },
    }

