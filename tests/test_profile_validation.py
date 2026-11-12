def test_max_risk_bounds():
    assert 0 < 1.0 <= 5
    assert not (0 < 0 <= 5)
    assert not (0 < 5.1 <= 5)

def test_position_size_formula_reference():
    capital = 200_000
    risk_pct = 1
    entry = 500
    stop = 475
    risk_amount = capital * risk_pct / 100
    quantity = int(risk_amount / (entry - stop))
    assert quantity == 80
