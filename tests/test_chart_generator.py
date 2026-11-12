import struct

import pytest

from services import chart_generator
from services.chart_generator import generate_price_chart


def make_records(count=60):
    return [
        {
            "ltp": 500 + index,
            "volume": 1000 + (index * 100),
            "source_updated_at": f"2026-01-{(index % 28) + 1:02d}T15:00:00",
        }
        for index in range(count)
    ]


def test_chart_generates_valid_png():
    records = make_records(60)

    chart = generate_price_chart(records, "NABIL")
    image = chart.getvalue()

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">I", image[16:20])[0] == 1000
    assert struct.unpack(">I", image[20:24])[0] == 850


def test_chart_rejects_empty_records():
    with pytest.raises(
        ValueError,
        match="No historical records available",
    ):
        generate_price_chart([], "NABIL")


def test_chart_rejects_insufficient_valid_prices():
    records = [
        {
            "ltp": 500,
            "source_updated_at": "2026-01-01T15:00:00",
        },
        {
            "ltp": -10,
            "source_updated_at": "2026-01-02T15:00:00",
        },
        {
            "ltp": "invalid",
            "source_updated_at": "2026-01-03T15:00:00",
        },
    ]

    with pytest.raises(
        ValueError,
        match="Not enough valid prices",
    ):
        generate_price_chart(records, "NABIL")


def test_chart_handles_missing_and_invalid_volume():
    records = [
        {
            "ltp": 500 + index,
            "source_updated_at": f"2026-01-{index + 1:02d}T15:00:00",
            "volume": "invalid" if index == 0 else None,
        }
        for index in range(5)
    ]

    chart = generate_price_chart(records, "NABIL")

    assert chart.getvalue().startswith(b"\x89PNG\r\n\x1a\n")


def test_chart_skips_records_with_invalid_timestamps(monkeypatch):
    records = [
        {
            "ltp": 500 + index,
            "volume": 1000,
            "source_updated_at": (
                "not-a-date" if index == 2
                else f"2026-01-{index + 1:02d}T15:00:00"
            ),
        }
        for index in range(5)
    ]

    captured_text = []
    original_text = chart_generator.Canvas.text

    def capture_text(self, x, y, value, color, scale=1):
        captured_text.append(str(value))
        return original_text(self, x, y, value, color, scale)

    monkeypatch.setattr(chart_generator.Canvas, "text", capture_text)

    chart = generate_price_chart(records, "NABIL")

    assert chart.getvalue().startswith(b"\x89PNG\r\n\x1a\n")
    assert "4 TRADING OBSERVATIONS" in captured_text
