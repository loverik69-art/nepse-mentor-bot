"""Offline historical backtesting for NEPSE technical signals."""

import math

from database.db import get_daily_price_history
from services.indicators import (
    calculate_sma,
    calculate_ema,
    calculate_rsi,
    calculate_macd,
)
from services.signals import generate_signal


def _validate_backtest_inputs(
    symbol: str,
    horizons: tuple[int, ...],
    limit: int,
) -> tuple[str, tuple[int, ...]]:
    """Validate and normalize backtesting inputs."""

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")

    if not isinstance(horizons, (tuple, list)) or not horizons:
        raise ValueError("horizons must be a non-empty tuple or list")

    normalized_horizons = []

    for horizon in horizons:
        if isinstance(horizon, bool) or not isinstance(horizon, int):
            raise ValueError("each horizon must be a positive integer")
        if horizon < 1:
            raise ValueError("each horizon must be a positive integer")
        if horizon in normalized_horizons:
            raise ValueError("horizons must not contain duplicates")
        normalized_horizons.append(horizon)

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    return symbol.strip().upper(), tuple(normalized_horizons)


async def _load_historical_prices(
    symbol: str,
    limit: int,
) -> list[dict]:
    """Load and validate dated historical price observations."""

    rows = await get_daily_price_history(symbol, limit=limit)

    if not isinstance(rows, list):
        raise ValueError("historical data must be a list")

    validated = []

    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid historical price record")

        trading_date = row.get("trading_date")
        price = row.get("ltp")

        if not isinstance(trading_date, str) or not trading_date.strip():
            raise ValueError("historical record has an invalid trading date")

        if (
            isinstance(price, bool)
            or not isinstance(price, (int, float))
            or not math.isfinite(price)
            or price <= 0
        ):
            raise ValueError("historical record has an invalid LTP")

        validated.append({
            "trading_date": trading_date,
            "ltp": float(price),
        })

    return validated


def _build_historical_analysis(symbol: str, prices: list[float]) -> dict:
    """Build signal inputs using only prices available through that date."""

    return {
        "symbol": symbol,
        "observations": len(prices),
        "indicators": {
            "sma_20": calculate_sma(prices, 20),
            "sma_50": calculate_sma(prices, 50),
            "ema_20": calculate_ema(prices, 20),
            "ema_50": calculate_ema(prices, 50),
            "rsi_14": calculate_rsi(prices, 14),
            "macd": calculate_macd(prices),
        },
    }


def _calculate_forward_return(
    entry_price: float,
    exit_price: float,
    action: str,
) -> float:
    """Calculate directional return as a percentage."""

    if action == "BUY":
        return (exit_price - entry_price) / entry_price * 100

    if action == "SELL":
        return (entry_price - exit_price) / entry_price * 100

    raise ValueError("action must be BUY or SELL")


def _summarize_horizon(trades: list[dict]) -> dict:
    """Summarize completed directional trades for one horizon."""

    if not trades:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": None,
            "average_return_pct": None,
        }

    returns = [trade["return_pct"] for trade in trades]
    wins = sum(value > 0 for value in returns)

    return {
        "trades": len(returns),
        "wins": wins,
        "losses": sum(value < 0 for value in returns),
        "win_rate_pct": round(wins / len(returns) * 100, 2),
        "average_return_pct": round(sum(returns) / len(returns), 2),
    }


async def backtest_symbol(
    symbol: str,
    horizons: tuple[int, ...] = (5, 10, 20),
    limit: int = 5000,
) -> dict:
    """Backtest historical signals without using future data for signals.

    A signal is generated using prices through date T. Entry occurs at the
    next available observation. Each horizon measures subsequent available
    trading observations from that entry.

    Fees and slippage are excluded. Historical prices are daily LTP snapshots,
    not independently verified official closing prices.
    """

    symbol, horizons = _validate_backtest_inputs(
        symbol,
        horizons,
        limit,
    )

    rows = await _load_historical_prices(symbol, limit)

    if len(rows) < 51:
        return {
            "symbol": symbol,
            "observations": len(rows),
            "signals": {"BUY": 0, "SELL": 0, "HOLD": 0},
            "results": {
                horizon: {
                    **_summarize_horizon([]),
                    "buy_trades": 0,
                    "sell_trades": 0,
                }
                for horizon in horizons
            },
            "message": "At least 51 daily observations are required.",
        }

    prices = [row["ltp"] for row in rows]
    signal_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
    horizon_trades = {horizon: [] for horizon in horizons}
    directional_counts = {
        horizon: {"BUY": 0, "SELL": 0}
        for horizon in horizons
    }


    # i is the signal date. Entry is i+1, and exit is
    # horizon additional observations after entry.
    for i in range(49, len(rows) - 1):
        historical_prices = prices[: i + 1]

        analysis = _build_historical_analysis(
            symbol,
            historical_prices,
        )
        signal = generate_signal(analysis)
        action = signal["signal"]

        if action not in signal_counts:
            raise ValueError("signal engine returned an unknown action")

        signal_counts[action] += 1

        if action == "HOLD":
            continue

        entry_index = i + 1
        entry_price = prices[entry_index]

        for horizon in horizons:
            exit_index = entry_index + horizon

            if exit_index >= len(prices):
                continue

            exit_price = prices[exit_index]
            return_pct = _calculate_forward_return(
                entry_price,
                exit_price,
                action,
            )

            horizon_trades[horizon].append({
                "action": action,
                "return_pct": return_pct,
            })
            directional_counts[horizon][action] += 1

    results = {}

    for horizon in horizons:
        summary = _summarize_horizon(horizon_trades[horizon])
        summary["buy_trades"] = directional_counts[horizon]["BUY"]
        summary["sell_trades"] = directional_counts[horizon]["SELL"]
        results[horizon] = summary

    return {
        "symbol": symbol,
        "observations": len(rows),
        "first_date": rows[0]["trading_date"],
        "last_date": rows[-1]["trading_date"],
        "signals": signal_counts,
        "results": results,
        "methodology": {
            "entry": "Next available daily observation after signal",
            "horizons": "Subsequent available trading observations after entry",
            "fees_and_slippage": "Excluded",
            "price_source": "Daily LTP snapshots; not verified official closes",
            "look_ahead_bias": "Signal indicators use only observations available on the signal date",
        },
    }
