import math
from statistics import median

from database.db import get_daily_price_history, get_profile
from services.nepse_data import get_stock


STYLE_LOOKBACKS = {
    "Swing": 30,
    "Positional": 90,
    "Long-Term": 180,
}

RISK_ENTRY_FACTORS = {
    "Low": 0.25,
    "Medium": 0.40,
    "High": 0.50,
}


def _valid_number(value, name, *, allow_zero=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (value < 0 if allow_zero else value <= 0)
    ):
        raise ValueError(f"{name} must be a valid number")


def _validate_prices(prices):
    if not isinstance(prices, list):
        raise ValueError("Price history must be a list")

    for price in prices:
        _valid_number(price, "Historical price")

    return prices


def _validate_profile(profile):
    if not isinstance(profile, dict):
        raise ValueError("A valid user profile is required")

    style = profile.get("trading_style")
    risk_tolerance = profile.get("risk_tolerance")
    capital = profile.get("capital_npr")
    max_risk = profile.get("max_risk_pct")

    if style not in STYLE_LOOKBACKS:
        raise ValueError("Unsupported trading style in profile")

    if risk_tolerance not in RISK_ENTRY_FACTORS:
        raise ValueError("Invalid risk tolerance")

    _valid_number(capital, "Capital", allow_zero=True)
    _valid_number(max_risk, "Maximum risk percentage")

    if capital <= 0:
        raise ValueError("Capital must be greater than zero")

    if not 0 < max_risk <= 5:
        raise ValueError(
            "Maximum risk percentage must be above 0 and at most 5"
        )

    return (
        style,
        risk_tolerance,
        float(capital),
        float(max_risk),
    )


def _price_volatility(prices):
    returns = [
        abs((prices[index] - prices[index - 1]) / prices[index - 1])
        for index in range(1, len(prices))
    ]
    return median(returns) if returns else 0.0


def generate_trade_plan(
    symbol,
    current_price,
    price_history,
    profile,
    *,
    is_stale=False,
):
    """Build an educational plan from historical daily LTP snapshots."""

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("A valid stock symbol is required")

    _valid_number(current_price, "Current price")

    style, risk_tolerance, capital, max_risk_pct = (
        _validate_profile(profile)
    )

    normalized_symbol = symbol.strip().upper()

    if is_stale:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": "Latest market data is stale. No trade plan generated.",
        }

    prices = _validate_prices(price_history)
    lookback = STYLE_LOOKBACKS[style]

    if len(prices) < lookback:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": (
                f"{style} planning requires at least "
                f"{lookback} daily observations."
            ),
        }

    prices = [float(price) for price in prices[-lookback:]]

    recent_low = min(prices)
    recent_high = max(prices)
    price_range = recent_high - recent_low

    if price_range <= 0:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": "Historical prices do not show a usable trading range.",
        }

    # These are historical price clusters, not confirmed technical
    # support or resistance. Daily LTP data does not contain OHLC candles.
    lower_boundary = recent_low + price_range * 0.25
    upper_boundary = recent_high - price_range * 0.25

    support_candidates = [
        price for price in prices if price <= lower_boundary
    ]
    resistance_candidates = [
        price for price in prices if price >= upper_boundary
    ]

    if not support_candidates or not resistance_candidates:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": "Unable to identify historical price clusters.",
        }

    support = median(support_candidates)
    resistance = median(resistance_candidates)

    if not support < current_price < resistance:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": (
                "Current price is outside the historical price clusters. "
                "A fresh entry is not supported by this method."
            ),
        }

    volatility = _price_volatility(prices)

    if not math.isfinite(volatility) or volatility <= 0:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": "Price movement is insufficient to estimate a stop loss.",
        }

    # Risk tolerance changes how close the entry reference is to current
    # price. It does not change the user's maximum portfolio risk setting.
    entry_factor = RISK_ENTRY_FACTORS[risk_tolerance]
    entry_low = round(support, 2)
    entry_high = round(
        support + (current_price - support) * entry_factor,
        2,
    )
    entry = round((entry_low + entry_high) / 2, 2)

    # Median absolute daily return provides a data-derived stop buffer.
    stop_loss = round(support * (1 - volatility), 2)

    if stop_loss <= 0 or stop_loss >= entry:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": "A defensible stop-loss level could not be calculated.",
        }

    risk_per_share = round(entry - stop_loss, 2)

    if risk_per_share <= 0:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": "A defensible stop-loss level could not be calculated.",
        }

    # Targets are limited by the observed upper price cluster.
    target_1 = round(min(resistance, entry + risk_per_share * 1.5), 2)
    target_2 = round(min(resistance, entry + risk_per_share * 2.0), 2)

    if target_1 <= entry or target_2 <= target_1:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": (
                "Historical price structure does not support "
                "two distinct upside targets."
            ),
        }

    risk_budget = capital * max_risk_pct / 100
    risk_based_quantity = math.floor(risk_budget / risk_per_share)
    capital_based_quantity = math.floor(capital / entry)
    quantity = min(risk_based_quantity, capital_based_quantity)

    if quantity < 1:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": (
                "Available capital and risk limit do not support even one share."
            ),
        }

    return {
        "symbol": normalized_symbol,
        "status": "AVAILABLE",
        "trading_style": style,
        "risk_tolerance": risk_tolerance,
        "lookback_observations": len(prices),
        "current_price": round(float(current_price), 2),
        "support_zone": round(support, 2),
        "resistance_zone": round(resistance, 2),
        "buying_range": {
            "low": round(entry_low, 2),
            "high": round(entry_high, 2),
        },
        "selling_range": {
            "low": round(target_1, 2),
            "high": round(target_2, 2),
        },
        "entry_reference": round(entry, 2),
        "stop_loss": round(stop_loss, 2),
        "target_1": round(target_1, 2),
        "target_2": round(target_2, 2),
        "risk_reward": {
            "target_1": round((target_1 - entry) / risk_per_share, 2),
            "target_2": round((target_2 - entry) / risk_per_share, 2),
        },
        "risk_budget_npr": round(risk_budget, 2),
        "risk_per_share_npr": round(risk_per_share, 2),
        "suggested_quantity": quantity,
        "estimated_investment_npr": round(quantity * entry, 2),
        "estimated_max_loss_npr": round(quantity * risk_per_share, 2),
        "methodology": (
            "Historical price clusters use the lower and upper 25% price bands "
            "of daily LTP observations. The stop buffer uses median absolute "
            "daily returns. Targets use 1.5R and 2R, capped at the upper "
            "historical price cluster. Risk tolerance adjusts entry "
            "conservatism; the saved maximum risk percentage controls sizing."
        ),
        "data_basis": (
            "Historical daily snapshots, not verified official closing "
            "prices or OHLC candles. Price clusters are estimates, not "
            "confirmed support/resistance or guaranteed execution prices."
        ),
    }



async def get_trade_plan(symbol, telegram_id):
    """Load saved profile and market data, then generate a trade plan."""

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("A valid stock symbol is required.")

    if (
        isinstance(telegram_id, bool)
        or not isinstance(telegram_id, int)
        or telegram_id <= 0
    ):
        raise ValueError("A valid Telegram user ID is required.")

    normalized_symbol = symbol.strip().upper()

    if not normalized_symbol.isalnum():
        raise ValueError("Invalid stock symbol.")

    profile = await get_profile(telegram_id)

    if profile is None:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": "Please create your profile first using /start.",
        }

    stock = await get_stock(normalized_symbol)

    if stock is None:
        return {
            "symbol": normalized_symbol,
            "status": "UNAVAILABLE",
            "reason": f"No current market quote found for {normalized_symbol}.",
        }

    current_price = stock.get("ltp")

    if stock.get("is_stale"):
        return generate_trade_plan(
            normalized_symbol,
            current_price,
            [],
            profile,
            is_stale=True,
        )

    history = await get_daily_price_history(
        normalized_symbol,
        limit=5000,
    )

    if not isinstance(history, list):
        raise ValueError("Historical price data has an unexpected format.")

    prices = []

    for row in history:
        if not isinstance(row, dict) or "ltp" not in row:
            raise ValueError("Historical price data has an unexpected format.")
        prices.append(row["ltp"])

    return generate_trade_plan(
        normalized_symbol,
        current_price,
        prices,
        profile,
        is_stale=False,
    )
