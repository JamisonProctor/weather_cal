"""Tests for _make_check factory in forecast_formatting.py."""
from src.services.forecast_formatting import _make_check
from src.constants import (
    COLD_TEMP_THRESHOLD,
    HOT_TEMP_THRESHOLD,
    RAIN_MM_THRESHOLD,
    WARM_TEMP_THRESHOLD,
    WIND_GUST_THRESHOLD,
    WIND_SPEED_THRESHOLD,
)


def test_rain_check_uses_constant():
    check = _make_check("rain")
    assert check(10, 0, 50, 5, RAIN_MM_THRESHOLD, 0) is True
    assert check(10, 0, 50, 5, RAIN_MM_THRESHOLD - 0.1, 0) is False


def test_wind_check_uses_constant():
    check = _make_check("wind")
    assert check(10, 0, 50, WIND_SPEED_THRESHOLD, 0, 0) is True
    assert check(10, 0, 50, WIND_SPEED_THRESHOLD - 1, 0, 0) is False


def test_wind_check_triggers_on_gusts():
    """Sustained below threshold but gusts at threshold → triggers."""
    check = _make_check("wind")
    assert check(10, 0, 50, 20, 0, WIND_GUST_THRESHOLD) is True
    assert check(10, 0, 50, 20, 0, WIND_GUST_THRESHOLD - 1) is False


def test_cold_check_default_threshold():
    check = _make_check("cold")
    assert check(COLD_TEMP_THRESHOLD - 1, 0, 0, 0, 0, 0) is True
    assert check(COLD_TEMP_THRESHOLD, 0, 0, 0, 0, 0) is False


def test_cold_check_custom_threshold():
    check = _make_check("cold", prefs={"cold_threshold": 10.0})
    assert check(9.0, 0, 0, 0, 0, 0) is True
    assert check(10.0, 0, 0, 0, 0, 0) is False


def test_hot_check_default_threshold():
    check = _make_check("hot")
    assert check(HOT_TEMP_THRESHOLD + 1, 0, 0, 0, 0, 0) is True
    assert check(HOT_TEMP_THRESHOLD, 0, 0, 0, 0, 0) is False


def test_hot_check_custom_threshold():
    check = _make_check("hot", prefs={"hot_threshold": 35.0})
    assert check(36.0, 0, 0, 0, 0, 0) is True
    assert check(35.0, 0, 0, 0, 0, 0) is False


def test_sunny_check_default_threshold():
    check = _make_check("sunny")
    # Clear sky (code 0), warm enough, no rain, no wind, no gusts
    assert check(WARM_TEMP_THRESHOLD, 0, 0, 0, 0, 0) is True
    # Too cold
    assert check(WARM_TEMP_THRESHOLD - 1, 0, 0, 0, 0, 0) is False
    # Cloudy (code 3)
    assert check(WARM_TEMP_THRESHOLD, 3, 0, 0, 0, 0) is False


def test_sunny_check_blocked_by_gusts():
    """Nice weather conditions but gusts >= threshold → not sunny."""
    check = _make_check("sunny")
    assert check(WARM_TEMP_THRESHOLD, 0, 0, 0, 0, WIND_GUST_THRESHOLD) is False
    assert check(WARM_TEMP_THRESHOLD, 0, 0, 0, 0, WIND_GUST_THRESHOLD - 1) is True


def test_sunny_check_custom_warm_threshold():
    check = _make_check("sunny", prefs={"warm_threshold": 20.0})
    assert check(20.0, 0, 0, 0, 0, 0) is True
    assert check(19.0, 0, 0, 0, 0, 0) is False


def test_snow_check():
    check = _make_check("snow")
    assert check(0, 71, 0, 0, 0, 0) is True  # snow code
    assert check(0, 0, 0, 0, 0, 0) is False   # clear code


def test_unknown_type_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown warning type"):
        _make_check("tornado")
