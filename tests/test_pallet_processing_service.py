import time
import pytest
from src.domain.palet import PaletScanData
from src.services.pallet_processing_service import PalletProcessingService


@pytest.fixture
def service():
    return PalletProcessingService()


def _make_palet(**kwargs) -> PaletScanData:
    return PaletScanData(**kwargs)


class TestProcesarNuevosDatos:
    def test_returns_false_for_none(self, service):
        assert service.procesar_nuevos_datos(None) is False

    def test_returns_true_when_data_added(self, service):
        nuevo = _make_palet(sscc="123456789012345678")
        assert service.procesar_nuevos_datos(nuevo) is True

    def test_accumulated_fields_are_set(self, service):
        service.procesar_nuevos_datos(_make_palet(sscc="SSCC001", ean="EAN001"))
        palet = service.get_palet_actual()
        assert palet.sscc == "SSCC001"
        assert palet.ean == "EAN001"

    def test_does_not_overwrite_existing_field(self, service):
        service.procesar_nuevos_datos(_make_palet(sscc="ORIGINAL"))
        service.procesar_nuevos_datos(_make_palet(sscc="OVERWRITE"))
        assert service.get_palet_actual().sscc == "ORIGINAL"

    def test_fills_missing_field_in_second_scan(self, service):
        service.procesar_nuevos_datos(_make_palet(sscc="SSCC001"))
        service.procesar_nuevos_datos(_make_palet(ean="EAN001"))
        palet = service.get_palet_actual()
        assert palet.sscc == "SSCC001"
        assert palet.ean == "EAN001"

    def test_returns_false_when_no_new_data(self, service):
        service.procesar_nuevos_datos(_make_palet(sscc="SSCC001"))
        assert service.procesar_nuevos_datos(_make_palet(sscc="OVERWRITE")) is False

    def test_empty_palet_returns_false(self, service):
        assert service.procesar_nuevos_datos(_make_palet()) is False


class TestIsFullyCaptured:
    def test_not_fully_captured_with_partial_data(self, service):
        service.procesar_nuevos_datos(_make_palet(sscc="S", ean="E"))
        assert service.get_palet_actual().is_fully_captured() is False

    def test_fully_captured_when_all_fields_set(self, service):
        service.procesar_nuevos_datos(_make_palet(
            sscc="S",
            ean="E",
            batch_number="B",
            product_use_by_date="01/01/2026",
            packaging_date="15/03/2025",
        ))
        assert service.get_palet_actual().is_fully_captured() is True


class TestResetPalet:
    def test_reset_clears_all_fields(self, service):
        service.procesar_nuevos_datos(_make_palet(sscc="S", ean="E"))
        service.reset_palet()
        palet = service.get_palet_actual()
        assert palet.sscc is None
        assert palet.ean is None

    def test_reset_clears_fully_captured_flag(self, service):
        service.procesar_nuevos_datos(_make_palet(
            sscc="S", ean="E", batch_number="B",
            product_use_by_date="01/01/2026", packaging_date="15/03/2025",
        ))
        service.reset_palet()
        assert service.get_palet_actual().is_fully_captured() is False


class TestWatchdog:
    def test_no_timer_returns_false(self, service):
        assert service.evaluar_watchdog(5.0) is False

    def test_within_timeout_returns_false(self, service):
        service.iniciar_temporizador()
        assert service.evaluar_watchdog(10.0) is False

    def test_expired_timeout_returns_true(self, service):
        service.iniciar_temporizador()
        # Force time by backdating scan_start_time
        from datetime import datetime, timedelta
        service.palet_acumulado.scan_start_time = datetime.now() - timedelta(seconds=10)
        assert service.evaluar_watchdog(5.0) is True

    def test_iniciar_temporizador_idempotent(self, service):
        service.iniciar_temporizador()
        first_time = service.palet_acumulado.scan_start_time
        time.sleep(0.01)
        service.iniciar_temporizador()
        assert service.palet_acumulado.scan_start_time == first_time
