import math


def _validate_number(name, value, allow_negative=False):
    """Validate an optional finite financial number."""

    if value is None:
        return None

    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number or None")

    if not allow_negative and value < 0:
        raise ValueError(f"{name} must not be negative")

    return float(value)


def _validate_positive(name, value):
    value = _validate_number(name, value)

    if value is not None and value <= 0:
        raise ValueError(f"{name} must be positive")

    return value


def calculate_eps(net_profit, weighted_average_shares):
    """Calculate earnings per share."""

    profit = _validate_number(
        "Net profit", net_profit, allow_negative=True
    )
    shares = _validate_positive(
        "Weighted average shares", weighted_average_shares
    )

    if profit is None or shares is None:
        return None

    return profit / shares


def calculate_pe_ratio(market_price, eps):
    """Calculate price-to-earnings ratio."""

    price = _validate_positive("Market price", market_price)
    earnings = _validate_number("EPS", eps, allow_negative=True)

    if price is None or earnings is None or earnings <= 0:
        return None

    return price / earnings


def calculate_book_value_per_share(
    shareholders_equity,
    outstanding_shares,
):
    """Calculate book value per share."""

    equity = _validate_number(
        "Shareholders' equity",
        shareholders_equity,
        allow_negative=True,
    )
    shares = _validate_positive(
        "Outstanding shares", outstanding_shares
    )

    if equity is None or shares is None:
        return None

    return equity / shares


def calculate_pb_ratio(market_price, book_value_per_share):
    """Calculate price-to-book ratio."""

    price = _validate_positive("Market price", market_price)
    book_value = _validate_number(
        "Book value per share",
        book_value_per_share,
        allow_negative=True,
    )

    if price is None or book_value is None or book_value <= 0:
        return None

    return price / book_value


def calculate_roe(net_profit, opening_equity, closing_equity):
    """Calculate return on average shareholders' equity."""

    profit = _validate_number(
        "Net profit", net_profit, allow_negative=True
    )
    opening = _validate_number(
        "Opening equity", opening_equity, allow_negative=True
    )
    closing = _validate_number(
        "Closing equity", closing_equity, allow_negative=True
    )

    if profit is None or opening is None or closing is None:
        return None

    average_equity = (opening + closing) / 2

    if average_equity <= 0:
        return None

    return (profit / average_equity) * 100


def calculate_dividend_yield(
    annual_dividend_per_share,
    market_price,
):
    """Calculate annual dividend yield as a percentage."""

    dividend = _validate_number(
        "Annual dividend per share",
        annual_dividend_per_share,
    )
    price = _validate_positive("Market price", market_price)

    if dividend is None or price is None:
        return None

    return (dividend / price) * 100


def analyze_fundamentals(
    market_price=None,
    net_profit=None,
    weighted_average_shares=None,
    shareholders_equity=None,
    outstanding_shares=None,
    opening_equity=None,
    closing_equity=None,
    annual_dividend_per_share=None,
):
    """Calculate fundamental metrics from supplied financial data.

    The caller is responsible for supplying figures from compatible
    reporting periods and share bases. Quarterly figures are not
    automatically annualized.
    """

    eps = calculate_eps(
        net_profit,
        weighted_average_shares,
    )

    book_value = calculate_book_value_per_share(
        shareholders_equity,
        outstanding_shares,
    )

    return {
        "eps": eps,
        "pe_ratio": calculate_pe_ratio(market_price, eps),
        "book_value_per_share": book_value,
        "pb_ratio": calculate_pb_ratio(market_price, book_value),
        "roe": calculate_roe(
            net_profit,
            opening_equity,
            closing_equity,
        ),
        "dividend_yield": calculate_dividend_yield(
            annual_dividend_per_share,
            market_price,
        ),
    }
