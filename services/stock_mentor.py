"""Rule-based NEPSE stock mentor question classification."""

import re


STOCK_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+$")

TOPIC_KEYWORDS = {
    "technical": (
        "technical", "indicator", "sma", "ema", "rsi", "macd",
        "moving average", "momentum",
    ),
    "fundamental": (
        "fundamental", "eps", "p/e", "pe ratio", "p/b", "pb ratio",
        "roe", "dividend", "book value", "financial report",
    ),
    "signal": (
        "signal", "buy or sell", "should i buy", "should i sell",
        "buy sell hold",
    ),
    "tradeplan": (
        "tradeplan", "trade plan", "buying range", "selling range",
        "target", "stop loss", "entry", "risk reward",
    ),
}


def classify_question(question: str) -> dict:
    """Identify a stock symbol and the topic of a mentor question."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Please enter a question.")

    normalized = question.strip()
    lowered = normalized.lower()

    if lowered in {"portfolio", "my portfolio"}:
        return {
            "topic": "portfolio",
            "symbol": None,
            "question": normalized,
        }

    if len(normalized) > 300:
        raise ValueError("Please keep your question within 300 characters.")

    words = re.findall(r"\b[A-Za-z][A-Za-z0-9]*\b", normalized)
    symbol = None

    for word in words:
        candidate = word.upper()

        if (
            STOCK_SYMBOL_PATTERN.fullmatch(candidate)
            and candidate not in {
                "WHAT", "WHY", "HOW", "WHEN", "WHERE", "WHICH",
                "SHOULD", "CAN", "COULD", "WOULD", "IS", "THE",
                "MY", "ME", "I", "A", "AN", "AND", "OR", "FOR",
                "OF", "TO", "IN", "ON", "DOES", "MEAN", "EXPLAIN",
                "RSI", "MACD", "SMA", "EMA", "EPS", "ROE",
                "NPR", "LTP", "PE", "PB", "BUY", "SELL", "HOLD",
                "TECHNICAL", "FUNDAMENTAL", "ANALYSIS",
                "TRADEPLAN", "PLAN", "TARGET", "STOP", "LOSS",
                "CREATE", "INDICATOR", "INDICATORS", "STOCK",
                "RISK", "REWARD", "DIVIDEND", "YIELD", "PORTFOLIO",
            }
            and len(candidate) >= 2
        ):
            symbol = candidate
            break

    topic = "overview"

    for candidate_topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            topic = candidate_topic
            break

    if any(
        phrase in lowered
        for phrase in ("my portfolio", "my holdings", "portfolio performance")
    ):
        topic = "portfolio"
        symbol = None

    return {
        "topic": topic,
        "symbol": symbol,
        "question": normalized,
    }


def _format_npr(value):
    """Format a finite numeric value as NPR, or disclose missing data."""
    import math

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        return "Not available"

    return f"NPR {value:,.2f}"


def _format_number(value, suffix=""):
    """Format a finite numeric metric without inventing missing values."""
    import math

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        return "Not available"

    return f"{value:,.2f}{suffix}"


def explain_indicator(name, value):
    """Explain a technical indicator using its supplied value."""
    explanations = {
        "sma_20": (
            "20-day Simple Moving Average",
            "The average price over the latest 20 observations. "
            "It helps describe short-term price direction.",
        ),
        "sma_50": (
            "50-day Simple Moving Average",
            "The average price over the latest 50 observations. "
            "It helps describe the medium-term trend.",
        ),
        "ema_20": (
            "20-day Exponential Moving Average",
            "A 20-observation moving average that gives more weight "
            "to recent prices.",
        ),
        "ema_50": (
            "50-day Exponential Moving Average",
            "A 50-observation moving average that gives more weight "
            "to recent prices.",
        ),
        "rsi_14": (
            "14-period Relative Strength Index",
            "A momentum indicator ranging from 0 to 100. "
            "Above 70 is commonly considered overbought and below "
            "30 oversold; neither level guarantees a reversal.",
        ),
    }

    if name == "macd":
        if not isinstance(value, dict):
            return "MACD: Not available."

        return (
            "MACD: "
            f"{_format_number(value.get('macd'))}; "
            f"signal: {_format_number(value.get('signal'))}; "
            f"histogram: {_format_number(value.get('histogram'))}. "
            "MACD compares two exponential moving averages to describe "
            "momentum and possible trend changes."
        )

    if name not in explanations:
        raise ValueError(f"Unsupported indicator: {name}")

    title, description = explanations[name]

    return (
        f"{title}: {_format_npr(value)}.\n"
        f"{description}"
    )


def explain_general_question(question):
    """Answer supported general investing and indicator questions."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Please enter a question.")

    lowered = question.lower()

    explanations = (
        (
            ("rsi", "relative strength index"),
            "The Relative Strength Index (RSI) measures the speed and magnitude of recent price "
            "movements on a 0–100 scale. Readings above 70 are commonly "
            "called overbought and below 30 oversold. These are warnings, "
            "not automatic buy or sell signals.",
        ),
        (
            ("macd",),
            "MACD compares shorter- and longer-term exponential moving "
            "averages. Traders often compare the MACD line with its signal "
            "line to assess momentum. It can lag price movements and may "
            "give false signals in sideways markets.",
        ),
        (
            ("sma", "simple moving average"),
            "SMA is the arithmetic average of prices over a selected "
            "number of observations. A shorter SMA reacts faster; a "
            "longer SMA describes a broader trend.",
        ),
        (
            ("ema", "exponential moving average"),
            "EMA is a moving average that gives greater weight to recent "
            "prices, so it generally reacts faster than an SMA.",
        ),
        (
            ("eps", "earnings per share"),
            "EPS is company earnings attributable to each share. Compare "
            "it across compatible reporting periods and check whether "
            "figures are quarterly or annual. EPS alone does not establish "
            "whether a share is fairly valued.",
        ),
        (
            ("p/e", "pe ratio", "price to earnings"),
            "P/E compares a share's market price with earnings per share. "
            "A high or low P/E is not automatically good or bad; compare "
            "similar companies and consider earnings quality and growth.",
        ),
        (
            ("dividend yield",),
            "Dividend yield compares annual dividend per share with the "
            "market price. A high yield is not guaranteed to continue, "
            "and past dividends do not guarantee future payments.",
        ),
        (
            ("stop loss",),
            "A stop-loss is a planned exit level intended to limit a "
            "trade's loss. Execution price can differ from the stop level "
            "because of gaps, liquidity, or market conditions.",
        ),
        (
            ("diversification",),
            "Diversification spreads investments across different "
            "companies or sectors to reduce concentration risk. It "
            "cannot eliminate market-wide risk.",
        ),
    )

    for keywords, explanation in explanations:
        if any(keyword in lowered for keyword in keywords):
            return explanation

    return (
        "I can explain NEPSE indicators, valuation metrics, dividends, "
        "risk management, and trading concepts. Try asking: "
        "'What does RSI mean?' or 'Explain P/E ratio'. "
        "For stock-specific analysis, include a symbol such as "
        "'NABIL technical'."
    )


def explain_technical_analysis(analysis, is_stale=False):
    """Turn existing technical-analysis results into a cautious explanation."""
    if not isinstance(analysis, dict):
        raise ValueError("Technical analysis must be a dictionary.")

    symbol = analysis.get("symbol", "Unknown")
    observations = analysis.get("observations", 0)
    indicators = analysis.get("indicators", {})

    if not isinstance(indicators, dict):
        indicators = {}

    lines = [
        f"Technical analysis for {symbol}",
        f"Historical observations: {observations}",
    ]

    if is_stale:
        lines.append(
            "WARNING: Available price data is stale. "
            "Do not rely on these readings for a current trading decision."
        )

    if observations < 50:
        lines.append(
            "History is insufficient for a reliable medium-term trend "
            "assessment. At least 50 observations are needed."
        )

    sma20 = indicators.get("sma_20")
    sma50 = indicators.get("sma_50")

    if (
        isinstance(sma20, (int, float))
        and not isinstance(sma20, bool)
        and isinstance(sma50, (int, float))
        and not isinstance(sma50, bool)
    ):
        if sma20 > sma50:
            lines.append("SMA trend: SMA20 is above SMA50, indicating a stronger shorter-term trend.")
        elif sma20 < sma50:
            lines.append("SMA trend: SMA20 is below SMA50, indicating a weaker shorter-term trend.")
        else:
            lines.append("SMA trend: SMA20 and SMA50 are equal.")

    ema20 = indicators.get("ema_20")
    ema50 = indicators.get("ema_50")

    if (
        isinstance(ema20, (int, float))
        and not isinstance(ema20, bool)
        and isinstance(ema50, (int, float))
        and not isinstance(ema50, bool)
    ):
        if ema20 > ema50:
            lines.append("EMA trend: EMA20 is above EMA50, suggesting stronger recent momentum.")
        elif ema20 < ema50:
            lines.append("EMA trend: EMA20 is below EMA50, suggesting weaker recent momentum.")
        else:
            lines.append("EMA trend: EMA20 and EMA50 are equal.")

    rsi = indicators.get("rsi_14")
    if isinstance(rsi, (int, float)) and not isinstance(rsi, bool):
        lines.append(explain_indicator("rsi_14", rsi))

    macd = indicators.get("macd")
    if isinstance(macd, dict):
        lines.append(explain_indicator("macd", macd))
        histogram = macd.get("histogram")

        if isinstance(histogram, (int, float)) and not isinstance(histogram, bool):
            if histogram > 0:
                lines.append("MACD momentum: Positive histogram.")
            elif histogram < 0:
                lines.append("MACD momentum: Negative histogram.")
            else:
                lines.append("MACD momentum: Histogram is neutral.")

    lines.append(
        "These indicators describe historical price behavior. "
        "They are not guaranteed buy or sell signals."
    )

    data_basis = analysis.get("data_basis")
    if isinstance(data_basis, str) and data_basis.strip():
        lines.append(f"Data basis: {data_basis}")

    return "\n".join(lines)


async def answer_technical_question(symbol):
    """Retrieve and explain existing technical analysis for one stock."""
    from services.nepse_data import get_stock
    from services.technical_analysis import get_technical_analysis

    symbol = symbol.strip().upper()

    if not symbol.isalnum():
        raise ValueError("Please provide a valid stock symbol.")

    stock = await get_stock(symbol)

    if stock is None:
        return f"No market data is available for {symbol}."

    analysis = await get_technical_analysis(symbol)

    if not isinstance(analysis, dict):
        return f"Technical analysis is unavailable for {symbol}."

    return explain_technical_analysis(
        analysis,
        is_stale=bool(stock.get("is_stale")),
    )


async def answer_signal_question(symbol):
    """Retrieve and explain the existing stock signal."""
    from services.signals import get_stock_signal

    symbol = symbol.strip().upper()

    if not symbol.isalnum():
        raise ValueError("Please provide a valid stock symbol.")

    result = await get_stock_signal(symbol)

    if not isinstance(result, dict):
        return f"Signal analysis is unavailable for {symbol}."

    signal = result.get("signal", "UNAVAILABLE")
    lines = [
        f"📊 {symbol} Signal Analysis",
        f"Signal: {signal}",
        f"Strength: {result.get('strength', 'Unavailable')}",
        f"Score: {result.get('score', 'Unavailable')}",
    ]

    price = _format_npr(result.get("ltp"))
    if price != "N/A":
        lines.append(f"Latest LTP snapshot: NPR {price}")

    age = result.get("age_minutes")
    if isinstance(age, (int, float)) and not isinstance(age, bool):
        lines.append(f"Data age: {age:.1f} minutes")

    reasons = result.get("reasons", [])
    if isinstance(reasons, list) and reasons:
        lines.append("\nWhy:")
        lines.extend(f"• {reason}" for reason in reasons)

    lines.extend([
        "",
        "This is educational technical analysis, not a guaranteed prediction.",
        "Market data may be historical snapshots rather than verified live quotes.",
    ])

    return "\n".join(lines)


async def answer_tradeplan_question(symbol, telegram_id):
    """Retrieve and explain the existing risk-aware trade plan."""
    from services.trade_planner import get_trade_plan

    symbol = symbol.strip().upper()

    if not symbol.isalnum():
        raise ValueError("Please provide a valid stock symbol.")

    plan = await get_trade_plan(symbol, telegram_id)

    if not isinstance(plan, dict):
        return f"Trade planning is unavailable for {symbol}."

    if plan.get("status") != "AVAILABLE":
        reason = plan.get("reason", "Insufficient information.")
        return (
            f"📋 {symbol} Trade Plan\n\n"
            f"Plan unavailable: {reason}"
        )

    buying = plan.get("buying_range", {})
    selling = plan.get("selling_range", {})
    risk_reward = plan.get("risk_reward", {})

    lines = [
        f"📋 {symbol} Educational Trade Plan",
        f"Trading style: {plan.get('trading_style', 'N/A')}",
        f"Risk tolerance: {plan.get('risk_tolerance', 'N/A')}",
        f"Current LTP snapshot: NPR {_format_number(plan.get('current_price'))}",
        "",
        f"Buying range: NPR {_format_number(buying.get('low'))} – {_format_number(buying.get('high'))}",
        f"Entry reference: NPR {_format_number(plan.get('entry_reference'))}",
        f"Stop-loss: NPR {_format_number(plan.get('stop_loss'))}",
        f"Target 1: NPR {_format_number(plan.get('target_1'))}",
        f"Target 2: NPR {_format_number(plan.get('target_2'))}",
        "",
        f"Risk/reward at Target 1: {_format_number(risk_reward.get('target_1'))}:1",
        f"Risk/reward at Target 2: {_format_number(risk_reward.get('target_2'))}:1",
        f"Suggested quantity: {_format_number(plan.get('suggested_quantity'))} shares",
        f"Estimated investment: NPR {_format_number(plan.get('estimated_investment_npr'))}",
        f"Estimated maximum loss: NPR {_format_number(plan.get('estimated_max_loss_npr'))}",
    ]

    if selling:
        lines.append(
            f"Selling range: NPR {_format_number(selling.get('low'))} – "
            f"{_format_number(selling.get('high'))}"
        )

    lines.extend([
        "",
        plan.get("data_basis", ""),
        "These are estimates, not guaranteed execution prices or profit.",
        "Educational analysis only — not financial advice.",
    ])

    return "\n".join(line for line in lines if line is not None)


async def answer_fundamental_question(symbol):
    """Retrieve and explain existing company financial reports."""
    from services.fundamental_data import get_company_financials
    from services.fundamental_analysis import analyze_company_reports

    symbol = symbol.strip().upper()

    if not symbol.isalnum():
        raise ValueError("Please provide a valid stock symbol.")

    company = await get_company_financials(symbol)

    if not isinstance(company, dict):
        return f"No fundamental financial data is available for {symbol}."

    analysis = analyze_company_reports(company)
    report = analysis.get("latest_report")

    if not isinstance(report, dict):
        return f"No usable financial reports are available for {symbol}."

    lines = [
        f"📊 {symbol} Fundamental Analysis",
        "",
        f"Report type: {report.get('type') or 'Not available'}",
        f"Fiscal year: {report.get('fy') or 'Not available'}",
        f"Quarter: {report.get('quarter') or 'Not specified'}",
        "",
        f"Reported EPS: NPR {_format_number(report.get('eps'))}",
        f"Reported P/E: {_format_number(report.get('pe'))}",
        f"Reported profit: {_format_number(report.get('profit'))}",
        f"Net worth per share: NPR {_format_number(report.get('net_worth_per_share'))}",
        "",
        "Year-on-year comparisons:",
    ]

    comparisons = analysis.get("comparisons", {})

    for field, label in (
        ("eps", "EPS"),
        ("net_worth_per_share", "Net worth per share"),
        ("profit", "Profit"),
    ):
        comparison = comparisons.get(field, {})
        status = comparison.get("status")

        if status == "compared":
            change = comparison.get("change_percent")
            lines.append(
                f"• {label}: {_format_number(change, '%')} change"
            )
        elif status == "comparison_unverified":
            lines.append(
                f"• {label}: comparison unverified; no growth conclusion."
            )
        elif status == "ambiguous_period":
            lines.append(
                f"• {label}: reporting period is ambiguous."
            )
        elif status == "missing_values":
            lines.append(
                f"• {label}: comparison values are incomplete."
            )
        else:
            lines.append(
                f"• {label}: insufficient comparable data."
            )

    warnings = analysis.get("warnings", [])
    if warnings:
        lines.extend(["", "Important limitations:"])
        lines.extend(f"• {warning}" for warning in warnings)

    lines.extend([
        "",
        f"Usable reports analyzed: {analysis.get('reports_analyzed', 0)}",
        f"Ambiguous reports excluded: {analysis.get('ambiguous_reports_excluded', 0)}",
        "",
        "Figures are source-reported and not independently verified.",
        "Quarterly EPS is not annualized. This is educational analysis, not financial advice.",
    ])

    return "\n".join(lines)


async def answer_portfolio_question(telegram_id):
    """Explain the requesting user's portfolio without modifying it."""
    from database.db import get_portfolio, get_profile

    if (
        isinstance(telegram_id, bool)
        or not isinstance(telegram_id, int)
        or telegram_id <= 0
    ):
        raise ValueError("A valid Telegram user ID is required.")

    holdings = await get_portfolio(telegram_id)
    profile = await get_profile(telegram_id)

    if not holdings:
        return (
            "📁 Your Portfolio\n\n"
            "No stock holdings were found in your portfolio.\n"
            "You can add holdings using the portfolio commands."
        )

    lines = ["📁 Your Portfolio", ""]
    total_investment = 0.0

    for holding in holdings:
        symbol = holding.get("symbol", "Unknown")
        quantity = holding.get("quantity")
        average_price = holding.get("average_buy_price")

        lines.append(f"**{symbol}**")
        lines.append(f"Quantity: {_format_number(quantity)} shares")
        lines.append(f"Average buy price: NPR {_format_number(average_price)}")

        if (
            isinstance(quantity, (int, float))
            and not isinstance(quantity, bool)
            and isinstance(average_price, (int, float))
            and not isinstance(average_price, bool)
            and quantity >= 0
            and average_price >= 0
        ):
            investment = quantity * average_price
            total_investment += investment
            lines.append(f"Estimated investment: NPR {_format_number(investment)}")
        else:
            lines.append("Estimated investment: Not available")

        lines.append("")

    lines.extend([
        f"Number of holdings: {len(holdings)}",
        f"Estimated total investment: NPR {_format_number(total_investment)}",
    ])

    if isinstance(profile, dict):
        lines.extend([
            "",
            "Investor profile:",
            f"Trading style: {profile.get('trading_style') or 'Not set'}",
            f"Risk tolerance: {profile.get('risk_tolerance') or 'Not set'}",
        ])

    lines.extend([
        "",
        "Investment figures use recorded average buy prices.",
        "They do not represent current market value or verified live prices.",
        "Educational information only — not financial advice.",
    ])

    return "\n".join(lines)


async def answer_question(question, telegram_id):
    """Route a user's question to the appropriate mentor service."""
    classified = classify_question(question)
    topic = classified["topic"]
    symbol = classified["symbol"]

    if topic == "portfolio":
        return await answer_portfolio_question(telegram_id)

    if topic == "technical":
        if not symbol:
            lowered = question.lower()
            if any(
                term in lowered
                for term in ("rsi", "macd", "sma", "ema")
            ):
                return explain_general_question(question)
            return (
                "Please include a stock symbol.\n"
                "Example: Explain NABIL technical indicators."
            )
        return await answer_technical_question(symbol)

    if topic == "fundamental":
        if not symbol:
            return (
                "Please include a stock symbol.\n"
                "Example: Explain NABIL fundamentals."
            )
        return await answer_fundamental_question(symbol)

    if topic == "signal":
        if not symbol:
            return (
                "Please include a stock symbol.\n"
                "Example: Is NICA a buy or sell?"
            )
        return await answer_signal_question(symbol)

    if topic == "tradeplan":
        if not symbol:
            return (
                "Please include a stock symbol.\n"
                "Example: Create a NABIL trade plan."
            )
        return await answer_tradeplan_question(symbol, telegram_id)

    if symbol:
        return await answer_signal_question(symbol)

    return explain_general_question(question)
