import math

import pytest

from services import fundamental_analysis as fa


def test_calculate_eps():
    assert fa.calculate_eps(100_000_000, 10_000_000) == 10.0


def test_calculate_eps_allows_loss():
    assert fa.calculate_eps(-20_000_000, 10_000_000) == -2.0


def test_calculate_eps_returns_none_for_missing_data():
    assert fa.calculate_eps(None, 100) is None
    assert fa.calculate_eps(100, None) is None


def test_calculate_pe_ratio():
    assert fa.calculate_pe_ratio(500, 25) == 20.0


@pytest.mark.parametrize("eps", [0, -1, None])
def test_calculate_pe_ratio_unavailable_for_nonpositive_eps(eps):
    assert fa.calculate_pe_ratio(500, eps) is None


def test_calculate_book_value_per_share():
    assert fa.calculate_book_value_per_share(500_000_000, 10_000_000) == 50.0


def test_calculate_pb_ratio():
    assert fa.calculate_pb_ratio(500, 50) == 10.0


@pytest.mark.parametrize("book_value", [0, -10, None])
def test_calculate_pb_ratio_unavailable_for_nonpositive_book_value(book_value):
    assert fa.calculate_pb_ratio(500, book_value) is None


def test_calculate_roe_uses_average_equity():
    assert fa.calculate_roe(20_000_000, 100_000_000, 100_000_000) == 20.0


def test_calculate_roe_returns_none_for_missing_or_nonpositive_equity():
    assert fa.calculate_roe(20, None, 100) is None
    assert fa.calculate_roe(20, 0, 0) is None
    assert fa.calculate_roe(20, -100, -100) is None


def test_calculate_dividend_yield():
    assert fa.calculate_dividend_yield(15, 500) == 3.0


def test_zero_dividend_is_valid():
    assert fa.calculate_dividend_yield(0, 500) == 0.0


def test_dividend_yield_returns_none_for_missing_data():
    assert fa.calculate_dividend_yield(None, 500) is None
    assert fa.calculate_dividend_yield(15, None) is None


def test_analyze_fundamentals_returns_all_metrics():
    result = fa.analyze_fundamentals(
        market_price=500,
        net_profit=100_000_000,
        weighted_average_shares=10_000_000,
        shareholders_equity=500_000_000,
        outstanding_shares=10_000_000,
        opening_equity=400_000_000,
        closing_equity=500_000_000,
        annual_dividend_per_share=15,
    )

    assert result == {
        "eps": 10.0,
        "pe_ratio": 50.0,
        "book_value_per_share": 50.0,
        "pb_ratio": 10.0,
        "roe": pytest.approx(22.2222222222),
        "dividend_yield": 3.0,
    }


def test_analyze_fundamentals_preserves_missing_values():
    result = fa.analyze_fundamentals()

    assert set(result) == {
        "eps",
        "pe_ratio",
        "book_value_per_share",
        "pb_ratio",
        "roe",
        "dividend_yield",
    }
    assert all(value is None for value in result.values())


@pytest.mark.parametrize(
    "function,args",
    [
        (fa.calculate_eps, ("100", 10)),
        (fa.calculate_eps, (100, True)),
        (fa.calculate_eps, (math.nan, 10)),
        (fa.calculate_eps, (math.inf, 10)),
        (fa.calculate_pe_ratio, (-1, 10)),
        (fa.calculate_pe_ratio, (500, math.nan)),
        (fa.calculate_book_value_per_share, (100, 0)),
        (fa.calculate_pb_ratio, (500, math.inf)),
        (fa.calculate_roe, (100, 100, math.nan)),
        (fa.calculate_dividend_yield, (-1, 500)),
        (fa.calculate_dividend_yield, (10, 0)),
    ],
)
def test_calculations_reject_invalid_inputs(function, args):
    with pytest.raises(ValueError):
        function(*args)
