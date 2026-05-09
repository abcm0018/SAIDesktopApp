import functools
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class DateTimeFormatter:
    """
    Utilidad centralizada para conversión de fechas.
    Fuente de la verdad para transformaciones GS1 <-> UI <-> ISO (MQTT/DB).
    """

    # --- FORMATOS ---
    _FMT_GS1_DATE = "%y%m%d"  # Ej: 250315
    _FMT_GS1_TIME = "%H%M"    # Ej: 1430
    _FMT_UI_DATE = "%d/%m/%Y" # Ej: 15/03/2025
    _FMT_UI_TIME = "%H:%M"    # Ej: 14:30
    _FMT_ISO_DATE = "%Y-%m-%d"# Ej: 2025-03-15
    _FMT_ISO_TIME = "%H:%M:%S"# Ej: 14:30:00

    @staticmethod
    @functools.lru_cache(maxsize=256)
    def gs1_to_ui_date(gs1_date: str) -> Optional[str]:
        """Convierte 'YYMMDD' -> 'DD/MM/YYYY' (Para visualización)"""
        if not gs1_date or len(gs1_date) != 6:
            return None
        try:
            dt = datetime.strptime(gs1_date, DateTimeFormatter._FMT_GS1_DATE)
            return dt.strftime(DateTimeFormatter._FMT_UI_DATE)
        except ValueError:
            return None

    @staticmethod
    @functools.lru_cache(maxsize=256)
    def gs1_to_ui_time(gs1_time: str) -> Optional[str]:
        """Convierte 'HHMM' -> 'HH:MM' (Para visualización)"""
        if not gs1_time or len(gs1_time) != 4:
            return None
        try:
            dt = datetime.strptime(gs1_time, DateTimeFormatter._FMT_GS1_TIME)
            return dt.strftime(DateTimeFormatter._FMT_UI_TIME)
        except ValueError:
            return None

    @staticmethod
    @functools.lru_cache(maxsize=256)
    def ui_date_to_iso(ui_date: str) -> Optional[str]:
        """Convierte 'DD/MM/YYYY' -> 'YYYY-MM-DD'. Vital para MQTT/Backend."""
        if not ui_date:
            return None
        try:
            dt = datetime.strptime(ui_date, DateTimeFormatter._FMT_UI_DATE)
            return dt.strftime(DateTimeFormatter._FMT_ISO_DATE)
        except ValueError:
            logger.error(f"Error convirtiendo fecha UI a ISO: {ui_date}")
            return None

    @staticmethod
    @functools.lru_cache(maxsize=256)
    def ui_time_to_iso(ui_time: str) -> Optional[str]:
        """Convierte 'HH:MM' -> 'HH:MM:SS' (añade :00 por defecto)"""
        if not ui_time:
            return None
        try:
            dt = datetime.strptime(ui_time, DateTimeFormatter._FMT_UI_TIME)
            return dt.strftime(DateTimeFormatter._FMT_ISO_TIME)
        except ValueError:
            return None