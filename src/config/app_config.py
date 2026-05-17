import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        logger.warning("Valor inválido para '%s' en .env; usando default %.1f", key, default)
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        logger.warning("Valor inválido para '%s' en .env; usando default %d", key, default)
        return default


class AppConfig:
    """Centraliza la configuración general de la aplicación."""

    APP_TITLE: str = os.getenv("APP_TITLE", "Sistema de Inventariado Automatizado")
    theme_mode: str = os.getenv("THEME_MODE", "light")

    READ_TIMEOUT_SEC = _env_float("READ_TIMEOUT_SEC", 5.0)
    QUEUE_MAX_SIZE = _env_int("QUEUE_MAX_SIZE", 1000)
    POST_SEND_DELAY_SEC = _env_float("POST_SEND_DELAY_SEC", 2.0)
    VIDEO_PREVIEW_WIDTH = _env_int("VIDEO_PREVIEW_WIDTH", 640)