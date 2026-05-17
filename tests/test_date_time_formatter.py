import pytest
from src.utils.date_time_formatter import DateTimeFormatter


@pytest.fixture(autouse=True)
def clear_lru_cache():
    DateTimeFormatter.gs1_to_ui_date.cache_clear()
    DateTimeFormatter.gs1_to_ui_time.cache_clear()
    DateTimeFormatter.ui_date_to_iso.cache_clear()
    DateTimeFormatter.ui_time_to_iso.cache_clear()
    yield


class TestGs1ToUiDate:
    def test_valid_date(self):
        assert DateTimeFormatter.gs1_to_ui_date("250315") == "15/03/2025"

    def test_century_boundary(self):
        # Python strptime maps %y 69-99 → 1969-1999 (standard ISO 8601 two-digit year rule)
        assert DateTimeFormatter.gs1_to_ui_date("991231") == "31/12/1999"
        assert DateTimeFormatter.gs1_to_ui_date("250101") == "01/01/2025"

    def test_empty_string_returns_none(self):
        assert DateTimeFormatter.gs1_to_ui_date("") is None

    def test_wrong_length_returns_none(self):
        assert DateTimeFormatter.gs1_to_ui_date("2503") is None
        assert DateTimeFormatter.gs1_to_ui_date("2503150") is None

    def test_non_numeric_returns_none(self):
        assert DateTimeFormatter.gs1_to_ui_date("AB0315") is None

    def test_invalid_date_values_return_none(self):
        assert DateTimeFormatter.gs1_to_ui_date("251340") is None  # month 13


class TestGs1ToUiTime:
    def test_valid_time(self):
        assert DateTimeFormatter.gs1_to_ui_time("1430") == "14:30"

    def test_midnight(self):
        assert DateTimeFormatter.gs1_to_ui_time("0000") == "00:00"

    def test_empty_returns_none(self):
        assert DateTimeFormatter.gs1_to_ui_time("") is None

    def test_wrong_length_returns_none(self):
        assert DateTimeFormatter.gs1_to_ui_time("143") is None
        assert DateTimeFormatter.gs1_to_ui_time("14300") is None

    def test_invalid_time_returns_none(self):
        assert DateTimeFormatter.gs1_to_ui_time("2560") is None  # hour 25


class TestUiDateToIso:
    def test_valid_date(self):
        assert DateTimeFormatter.ui_date_to_iso("15/03/2025") == "2025-03-15"

    def test_first_of_jan(self):
        assert DateTimeFormatter.ui_date_to_iso("01/01/2000") == "2000-01-01"

    def test_none_returns_none(self):
        assert DateTimeFormatter.ui_date_to_iso(None) is None

    def test_empty_returns_none(self):
        assert DateTimeFormatter.ui_date_to_iso("") is None

    def test_wrong_format_returns_none(self):
        assert DateTimeFormatter.ui_date_to_iso("2025-03-15") is None
        assert DateTimeFormatter.ui_date_to_iso("15-03-2025") is None


class TestUiTimeToIso:
    def test_valid_time(self):
        assert DateTimeFormatter.ui_time_to_iso("14:30") == "14:30:00"

    def test_midnight(self):
        assert DateTimeFormatter.ui_time_to_iso("00:00") == "00:00:00"

    def test_none_returns_none(self):
        assert DateTimeFormatter.ui_time_to_iso(None) is None

    def test_empty_returns_none(self):
        assert DateTimeFormatter.ui_time_to_iso("") is None

    def test_wrong_format_returns_none(self):
        assert DateTimeFormatter.ui_time_to_iso("14:30:00") is None
        assert DateTimeFormatter.ui_time_to_iso("1430") is None
