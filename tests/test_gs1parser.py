import pytest
from src.utils.date_time_formatter import DateTimeFormatter
from src.utils.gs1parser import GS1Parser


@pytest.fixture(autouse=True)
def clear_lru_cache():
    DateTimeFormatter.gs1_to_ui_date.cache_clear()
    DateTimeFormatter.gs1_to_ui_time.cache_clear()
    yield


FULL_GS1 = "(00) 123456789012345678 (01) 04012345678901 (10) LOTE123 (15) 260101 (8008) 2504101200"


class TestGS1ParserParse:
    def test_full_label_all_fields(self):
        result = GS1Parser.parse(FULL_GS1)
        assert result["sscc"] == "123456789012345678"
        assert result["gtin"] == "04012345678901"
        assert result["batch"] == "LOTE123"
        assert result["best_before_date"] == "01/01/2026"
        assert result["production_date"] == "10/04/2025"
        assert result["production_time"] == "12:00"

    def test_sscc_only(self):
        result = GS1Parser.parse("(00) 000000000000000001")
        assert result["sscc"] == "000000000000000001"
        assert "gtin" not in result
        assert "batch" not in result

    def test_empty_string(self):
        assert GS1Parser.parse("") == {}

    def test_no_valid_ais(self):
        assert GS1Parser.parse("just random text without AIs") == {}

    def test_ai_15_converts_to_ui_date(self):
        result = GS1Parser.parse("(15) 251231")
        assert result["best_before_date"] == "31/12/2025"

    def test_ai_8008_short_value_ignored(self):
        # Less than 10 chars — no production data expected
        result = GS1Parser.parse("(8008) 250410")
        assert "production_date" not in result
        assert "production_time" not in result

    def test_ai_8008_exact_10_chars(self):
        result = GS1Parser.parse("(8008) 2504101430")
        assert result["production_date"] == "10/04/2025"
        assert result["production_time"] == "14:30"

    def test_whitespace_trimmed_from_values(self):
        result = GS1Parser.parse("(10)  LOTE 456 ")
        assert result["batch"] == "LOTE 456"

    def test_multiple_ais_partial(self):
        result = GS1Parser.parse("(00) 987654321098765432 (10) BATCHX")
        assert result["sscc"] == "987654321098765432"
        assert result["batch"] == "BATCHX"
        assert "gtin" not in result
