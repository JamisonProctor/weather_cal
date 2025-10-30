from src.models.forecast import Forecast
from src.services.forecast_formatting import format_detailed_forecast


def test_format_detailed_forecast_emits_warnings():
    forecast = Forecast(
        date="2025-01-01",
        location="Munich",
        high=8,
        low=-2,
        times=[
            "2025-01-01T06:00",
            "2025-01-01T07:00",
            "2025-01-01T09:00",
            "2025-01-01T10:00",
            "2025-01-01T12:00",
            "2025-01-01T13:00",
            "2025-01-01T15:00",
            "2025-01-01T16:00",
        ],
        temps=[5, 4, 6, 5, 2, 1, -1, -2],
        codes=[61, 61, 1, 1, 1, 1, 71, 71],
        rain=[60, 45, 0, 0, 0, 0, 20, 20],
        winds=[12, 10, 35, 32, 8, 7, 12, 10],
    )

    lines = format_detailed_forecast(forecast).splitlines()

    assert any("06:00" in line and "⚠️" in line and "☂️" in line for line in lines)
    assert any("09:00" in line and "⚠️" in line and "🌬️" in line for line in lines)
    assert any("12:00" in line and "⚠️" in line and "🥶" in line for line in lines)
    assert any("15:00" in line and "⚠️" in line and "☃️" in line and "🥶" in line for line in lines)


def test_format_detailed_forecast_no_warnings():
    forecast = Forecast(
        date="2025-06-01",
        location="Munich",
        high=22,
        low=12,
        times=[
            "2025-06-01T06:00",
            "2025-06-01T07:00",
            "2025-06-01T09:00",
            "2025-06-01T10:00",
        ],
        temps=[18, 17, 20, 21],
        codes=[1, 1, 2, 2],
        rain=[5, 5, 0, 0],
        winds=[10, 12, 8, 6],
    )

    description = format_detailed_forecast(forecast)
    assert "⚠️" not in description
