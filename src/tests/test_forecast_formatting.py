from src.models.forecast import Forecast
from src.services.forecast_formatting import (
    MergedWarningWindow,
    WarningWindow,
    c_to_f,
    format_detailed_forecast,
    format_summary,
    get_warning_windows,
    map_code_to_emoji,
    merge_overlapping_windows,
)


def test_format_summary_with_warnings():
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
        temps=[7, 7, 7, 1, 13, 13, 13, 13],
        codes=[61, 61, 1, 1, 1, 1, 1, 1],
        rain=[60, 45, 0, 0, 0, 0, 0, 0],
        winds=[12, 10, 35, 32, 8, 7, 12, 10],
    )

    summary = format_summary(forecast)

    assert summary == "⚠️☂️🌬️🥶 AM6° / 13°"


def test_format_summary_without_warnings():
    forecast = Forecast(
        date="2025-06-01",
        location="Munich",
        high=22,
        low=12,
        times=[
            "2025-06-01T06:00",
            "2025-06-01T09:00",
            "2025-06-01T12:00",
            "2025-06-01T15:00",
        ],
        temps=[6, 6, 13, 13],
        codes=[1, 1, 2, 2],
        rain=[5, 5, 0, 0],
        winds=[10, 12, 8, 6],
    )

    summary = format_summary(forecast)

    assert summary == "AM🌤️6° / PM⛅13°"


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


def _make_forecast(times, temps, codes, rain, winds):
    return Forecast(
        date="2025-08-01",
        location="Munich",
        high=max(temps),
        low=min(temps),
        times=times,
        temps=temps,
        codes=codes,
        rain=rain,
        winds=winds,
    )


def test_get_warning_windows_single_rain_window():
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00", "2025-08-01T12:00", "2025-08-01T13:00"],
        temps=[15, 15, 15, 15],
        codes=[61, 61, 1, 1],
        rain=[60, 55, 5, 5],
        winds=[10, 10, 10, 10],
    )
    windows = get_warning_windows(forecast)
    rain = [w for w in windows if w.warning_type == "rain"]
    assert len(rain) == 1
    assert rain[0].start_time == "2025-08-01T10:00"
    assert rain[0].end_time == "2025-08-01T12:00"
    assert rain[0].emoji == "☂️"
    assert rain[0].label == "Rain Warning"


def test_get_warning_windows_two_separate_rain_windows():
    forecast = _make_forecast(
        times=[
            "2025-08-01T06:00", "2025-08-01T07:00",
            "2025-08-01T10:00",
            "2025-08-01T14:00", "2025-08-01T15:00",
        ],
        temps=[15, 15, 15, 15, 15],
        codes=[61, 61, 1, 63, 63],
        rain=[60, 60, 5, 70, 70],
        winds=[10, 10, 10, 10, 10],
    )
    windows = get_warning_windows(forecast)
    rain = [w for w in windows if w.warning_type == "rain"]
    assert len(rain) == 2
    assert rain[0].start_time == "2025-08-01T06:00"
    assert rain[0].end_time == "2025-08-01T08:00"
    assert rain[1].start_time == "2025-08-01T14:00"
    assert rain[1].end_time == "2025-08-01T16:00"


def test_get_warning_windows_wind_and_cold_independent():
    forecast = _make_forecast(
        times=["2025-08-01T06:00", "2025-08-01T07:00", "2025-08-01T08:00"],
        temps=[1, 2, 10],
        codes=[1, 1, 1],
        rain=[0, 0, 0],
        winds=[35, 35, 10],
    )
    windows = get_warning_windows(forecast)
    wind = [w for w in windows if w.warning_type == "wind"]
    cold = [w for w in windows if w.warning_type == "cold"]
    assert len(wind) == 1
    assert wind[0].start_time == "2025-08-01T06:00"
    assert wind[0].end_time == "2025-08-01T08:00"
    assert len(cold) == 1
    assert cold[0].start_time == "2025-08-01T06:00"
    assert cold[0].end_time == "2025-08-01T08:00"


def test_get_warning_windows_no_warnings():
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00"],
        temps=[20, 21],
        codes=[1, 2],
        rain=[5, 0],
        winds=[10, 8],
    )
    assert get_warning_windows(forecast) == []


def test_format_summary_fahrenheit():
    forecast = Forecast(
        date="2025-06-01",
        location="New York",
        high=30,
        low=20,
        times=["2025-06-01T06:00", "2025-06-01T12:00"],
        temps=[20, 28],
        codes=[1, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {"temp_unit": "F", "warn_in_allday": 1, "allday_rain": 1, "allday_wind": 1,
             "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0, "allday_hot": 0,
             "cold_threshold": 3.0, "hot_threshold": 28.0}
    summary = format_summary(forecast, prefs)
    # 20°C = 68°F, 28°C = 82°F — values should be in F range
    assert "68" in summary or "82" in summary


def test_format_detailed_forecast_fahrenheit():
    forecast = Forecast(
        date="2025-06-01",
        location="New York",
        high=30,
        low=20,
        times=["2025-06-01T06:00", "2025-06-01T12:00"],
        temps=[20, 28],
        codes=[1, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {"temp_unit": "F"}
    description = format_detailed_forecast(forecast, prefs)
    assert "°F" in description
    # 20°C = 68°F, 28°C = 82°F
    assert "68" in description
    assert "82" in description


def test_get_warning_windows_snow_all_day():
    forecast = _make_forecast(
        times=["2025-01-01T06:00", "2025-01-01T09:00", "2025-01-01T12:00"],
        temps=[-2, -3, -1],
        codes=[71, 73, 75],
        rain=[0, 0, 0],
        winds=[10, 10, 10],
    )
    windows = get_warning_windows(forecast)
    snow = [w for w in windows if w.warning_type == "snow"]
    assert len(snow) == 1
    assert snow[0].start_time == "2025-01-01T06:00"
    assert snow[0].end_time == "2025-01-01T13:00"


_SUNNY_PREFS = {"warn_sunny": 1, "warn_rain": 1, "warn_wind": 1, "warn_cold": 1, "warn_snow": 1}


def test_sunny_window_includes_partly_cloudy():
    """Partly cloudy (code 2) + warm + dry + calm → included in sunny window."""
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00", "2025-08-01T12:00"],
        temps=[20, 22, 21],
        codes=[2, 2, 2],
        rain=[0, 0, 0],
        winds=[5, 5, 5],
    )
    windows = get_warning_windows(forecast, prefs=_SUNNY_PREFS)
    sunny = [w for w in windows if w.warning_type == "sunny"]
    assert len(sunny) == 1
    assert sunny[0].start_time == "2025-08-01T10:00"
    assert sunny[0].end_time == "2025-08-01T13:00"


def test_sunny_window_excludes_partly_cloudy_with_rain():
    """Partly cloudy (code 2) + warm + rainy → NOT a nice weather window."""
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00", "2025-08-01T12:00"],
        temps=[20, 22, 21],
        codes=[2, 2, 2],
        rain=[50, 55, 60],
        winds=[5, 5, 5],
    )
    windows = get_warning_windows(forecast, prefs=_SUNNY_PREFS)
    sunny = [w for w in windows if w.warning_type == "sunny"]
    assert len(sunny) == 0


def test_sunny_window_excludes_partly_cloudy_with_wind():
    """Partly cloudy (code 2) + warm + windy → NOT a nice weather window."""
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00", "2025-08-01T12:00"],
        temps=[20, 22, 21],
        codes=[2, 2, 2],
        rain=[0, 0, 0],
        winds=[35, 35, 35],
    )
    windows = get_warning_windows(forecast, prefs=_SUNNY_PREFS)
    sunny = [w for w in windows if w.warning_type == "sunny"]
    assert len(sunny) == 0


def test_map_code_to_emoji_unknown_code():
    assert map_code_to_emoji(9999) == "❓"


def test_c_to_f_basic_conversions():
    assert c_to_f(0) == 32
    assert c_to_f(100) == 212


def test_collect_warnings_allday_hot_enabled():
    forecast = _make_forecast(
        times=["2025-08-01T12:00", "2025-08-01T13:00"],
        temps=[30, 32],
        codes=[0, 0],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {"allday_hot": 1, "allday_rain": 1, "allday_wind": 1, "allday_cold": 1,
             "allday_snow": 1, "allday_sunny": 0, "warn_in_allday": 1, "hot_threshold": 28.0}
    summary = format_summary(forecast, prefs)
    assert "🥵" in summary


def test_collect_warnings_allday_hot_disabled():
    forecast = _make_forecast(
        times=["2025-08-01T12:00", "2025-08-01T13:00"],
        temps=[30, 32],
        codes=[0, 0],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {"allday_hot": 0, "allday_rain": 1, "allday_wind": 1, "allday_cold": 1,
             "allday_snow": 1, "allday_sunny": 0, "warn_in_allday": 1, "hot_threshold": 28.0}
    summary = format_summary(forecast, prefs)
    assert "🥵" not in summary


def test_collect_warnings_allday_sunny_enabled():
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00", "2025-08-01T12:00"],
        temps=[20, 22, 21],
        codes=[0, 1, 0],
        rain=[0, 0, 0],
        winds=[5, 5, 5],
    )
    prefs = {"allday_sunny": 1, "allday_rain": 1, "allday_wind": 1, "allday_cold": 1,
             "allday_snow": 1, "allday_hot": 0, "warn_in_allday": 1}
    summary = format_summary(forecast, prefs)
    assert "☀️" in summary


def test_format_summary_with_prefs_none_uses_defaults():
    forecast = _make_forecast(
        times=["2025-08-01T06:00", "2025-08-01T12:00"],
        temps=[15, 20],
        codes=[1, 2],
        rain=[0, 0],
        winds=[5, 5],
    )
    summary = format_summary(forecast, None)
    assert "°" in summary


def test_get_warning_windows_hot_custom_threshold():
    forecast = _make_forecast(
        times=["2025-08-01T12:00", "2025-08-01T13:00"],
        temps=[25, 26],
        codes=[0, 0],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {"warn_hot": 1, "warn_rain": 1, "warn_wind": 1, "warn_cold": 1, "warn_snow": 1,
             "hot_threshold": 24.0}
    windows = get_warning_windows(forecast, prefs)
    hot = [w for w in windows if w.warning_type == "hot"]
    assert len(hot) == 1


def test_sunny_to_partly_cloudy_merges_into_one_window():
    """Sunny → partly cloudy → sunny merges into one continuous nice weather window."""
    forecast = _make_forecast(
        times=[
            "2025-08-01T10:00", "2025-08-01T11:00",
            "2025-08-01T12:00", "2025-08-01T13:00",
            "2025-08-01T14:00", "2025-08-01T15:00",
        ],
        temps=[20, 21, 22, 23, 22, 21],
        codes=[0, 0, 2, 2, 1, 0],
        rain=[0, 0, 0, 0, 0, 0],
        winds=[5, 5, 8, 8, 5, 5],
    )
    windows = get_warning_windows(forecast, prefs=_SUNNY_PREFS)
    sunny = [w for w in windows if w.warning_type == "sunny"]
    assert len(sunny) == 1
    assert sunny[0].start_time == "2025-08-01T10:00"
    assert sunny[0].end_time == "2025-08-01T16:00"


# --- merge_overlapping_windows tests ---


def test_merge_overlapping_windows_two_overlap():
    """Two overlapping windows merge into one with combined types."""
    windows = [
        WarningWindow("rain", "☂️", "Rain Warning", "2025-08-01T17:00", "2025-08-01T23:00"),
        WarningWindow("cold", "🥶", "Cold Warning", "2025-08-01T18:00", "2025-08-01T23:00"),
    ]
    merged = merge_overlapping_windows(windows)
    assert len(merged) == 1
    assert merged[0].warning_types == ["rain", "cold"]
    assert merged[0].emojis == ["☂️", "🥶"]
    assert merged[0].start_time == "2025-08-01T17:00"
    assert merged[0].end_time == "2025-08-01T23:00"


def test_merge_overlapping_windows_non_overlapping_stay_separate():
    """Non-overlapping windows remain as separate merged windows."""
    windows = [
        WarningWindow("rain", "☂️", "Rain Warning", "2025-08-01T06:00", "2025-08-01T08:00"),
        WarningWindow("wind", "🌬️", "Wind Warning", "2025-08-01T14:00", "2025-08-01T16:00"),
    ]
    merged = merge_overlapping_windows(windows)
    assert len(merged) == 2
    assert merged[0].warning_types == ["rain"]
    assert merged[1].warning_types == ["wind"]


def test_merge_overlapping_windows_single_passthrough():
    """A single window passes through as a single MergedWarningWindow."""
    windows = [
        WarningWindow("rain", "☂️", "Rain Warning", "2025-08-01T10:00", "2025-08-01T14:00"),
    ]
    merged = merge_overlapping_windows(windows)
    assert len(merged) == 1
    assert merged[0].warning_types == ["rain"]
    assert merged[0].start_time == "2025-08-01T10:00"
    assert merged[0].end_time == "2025-08-01T14:00"


def test_merge_overlapping_windows_empty():
    """Empty input returns empty output."""
    assert merge_overlapping_windows([]) == []


def test_merge_overlapping_windows_emoji_ordering():
    """Types/emojis are ordered by _WARNING_CHECKS order, not input order."""
    windows = [
        WarningWindow("cold", "🥶", "Cold Warning", "2025-08-01T10:00", "2025-08-01T14:00"),
        WarningWindow("rain", "☂️", "Rain Warning", "2025-08-01T11:00", "2025-08-01T15:00"),
    ]
    merged = merge_overlapping_windows(windows)
    assert len(merged) == 1
    # rain comes before cold in _WARNING_CHECKS
    assert merged[0].warning_types == ["rain", "cold"]
    assert merged[0].emojis == ["☂️", "🥶"]


def test_merge_overlapping_windows_adjacent_not_merged():
    """Adjacent windows (end == start) are NOT merged — only strict overlap."""
    windows = [
        WarningWindow("rain", "☂️", "Rain Warning", "2025-08-01T10:00", "2025-08-01T12:00"),
        WarningWindow("wind", "🌬️", "Wind Warning", "2025-08-01T12:00", "2025-08-01T14:00"),
    ]
    merged = merge_overlapping_windows(windows)
    assert len(merged) == 2
