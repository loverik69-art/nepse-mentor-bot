"""Offline historical backtesting for NEPSE technical signals."""

import math

from database.db import (
    calculate_equity_transaction_fees,
    get_daily_price_history,
)
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


def _calculate_buy_trade_performance(
    entry_price: float,
    exit_price: float,
    budget: float = 100_000,
    slippage_pct: float = 0.1,
) -> dict:
    """Estimate long-only BUY performance after NEPSE fees and slippage."""

    for name, value in (
        ("entry_price", entry_price),
        ("exit_price", exit_price),
        ("budget", budget),
        ("slippage_pct", slippage_pct),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be a finite number")

    if entry_price <= 0 or exit_price <= 0 or budget <= 0:
        raise ValueError("Prices and budget must be positive")
    if not 0 <= slippage_pct < 100:
        raise ValueError("slippage_pct must be between 0 and 100")

    slippage_rate = slippage_pct / 100
    effective_entry = entry_price * (1 + slippage_rate)
    effective_exit = exit_price * (1 - slippage_rate)
    quantity = math.floor(budget / effective_entry)

    while quantity > 0:
        buy_fees = calculate_equity_transaction_fees(
            quantity, effective_entry, "buy"
        )["total_fees"]
        if quantity * effective_entry + buy_fees <= budget:
            break
        quantity -= 1

    if quantity < 1:
        raise ValueError("Budget is insufficient to buy one share")

    sell_fees = calculate_equity_transaction_fees(
        quantity, effective_exit, "sell"
    )["total_fees"]

    gross_profit = (exit_price - entry_price) * quantity
    slippage_cost = (
        (effective_entry - entry_price)
        + (exit_price - effective_exit)
    ) * quantity
    total_fees = buy_fees + sell_fees
    net_profit = gross_profit - slippage_cost - total_fees
    invested_capital = quantity * effective_entry + buy_fees

    return {
        "quantity": quantity,
        "gross_profit": round(gross_profit, 2),
        "gross_return_pct": round(
            gross_profit / (quantity * entry_price) * 100, 2
        ),
        "buy_fees": round(buy_fees, 2),
        "sell_fees": round(sell_fees, 2),
        "total_fees": round(total_fees, 2),
        "slippage_cost": round(slippage_cost, 2),
        "net_profit": round(net_profit, 2),
        "net_return_pct": round(
            net_profit / invested_capital * 100, 2
        ),
        "net_return_pct_exact": (
            net_profit / invested_capital * 100
        ),
    }


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

    BUY trades include estimated NEPSE fees and configurable slippage.
    SELL signals are bearish diagnostics, not executable short trades.
    Historical prices are daily LTP snapshots, not verified official closes.
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
    buy_execution_trades = {horizon: [] for horizon in horizons}
    buy_skipped_budget = {horizon: 0 for horizon in horizons}
    sell_signal_trades = {horizon: [] for horizon in horizons}
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

            if action == "BUY":
                try:
                    performance = _calculate_buy_trade_performance(
                        entry_price,
                        exit_price,
                    )
                except ValueError as exc:
                    if str(exc) != "Budget is insufficient to buy one share":
                        raise
                    buy_skipped_budget[horizon] += 1
                else:
                    buy_execution_trades[horizon].append(performance)
            else:
                sell_signal_trades[horizon].append({
                    "return_pct": return_pct,
                })

    results = {}

    for horizon in horizons:
        summary = _summarize_horizon(horizon_trades[horizon])
        summary["buy_trades"] = directional_counts[horizon]["BUY"]
        summary["sell_trades"] = directional_counts[horizon]["SELL"]

        buy_trades = buy_execution_trades[horizon]
        buy_summary = _summarize_horizon([
            {"return_pct": trade["net_return_pct_exact"]}
            for trade in buy_trades
        ])
        buy_summary["average_return_pct"] = (
            round(
                sum(t["net_return_pct"] for t in buy_trades)
                / len(buy_trades),
                2,
            )
            if buy_trades else None
        )
        buy_summary.update({
            "average_gross_return_pct": (
                round(
                    sum(t["gross_return_pct"] for t in buy_trades)
                    / len(buy_trades),
                    2,
                )
                if buy_trades else None
            ),
            "total_gross_profit": round(
                sum(t["gross_profit"] for t in buy_trades), 2
            ),
            "total_net_profit": round(
                sum(t["net_profit"] for t in buy_trades), 2
            ),
            "total_fees": round(
                sum(t["total_fees"] for t in buy_trades), 2
            ),
            "total_slippage_cost": round(
                sum(t["slippage_cost"] for t in buy_trades), 2
            ),
            "investment_budget": 100_000,
            "slippage_pct_per_side": 0.1,
            "skipped_budget": buy_skipped_budget[horizon],
        })

        summary["buy_execution"] = buy_summary
        summary["sell_signal"] = _summarize_horizon(
            sell_signal_trades[horizon]
        )
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
            "buy_execution": (
                "Long-only BUY simulation; NPR 100,000 budget per trade, "
                "whole shares, NEPSE fees, and 0.1% slippage per side"
            ),
            "sell_signals": (
                "Bearish directional evaluation only; not executable short sales"
            ),
            "price_source": "Daily LTP snapshots; not verified official closes",
            "look_ahead_bias": "Signal indicators use only observations available on the signal date",
        },
    }
