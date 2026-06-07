import logging
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ImageStorageService:
    """Gestiona el ciclo de vida de las imágenes capturadas durante el escaneo.

    Estructura en disco:
      <base_dir>/pending/  — imagen activa durante un ciclo (se elimina al finalizar)
      <base_dir>/failed/   — imágenes cuyo ciclo terminó sin SSCC (para diagnóstico)
    """

    _CLEANUP_INTERVAL_SEC = 3600  # ejecutar limpiar_failed_antiguos() cada hora

    def __init__(self, base_dir: str, failed_max_age_h: int = 48):
        self._base = Path(base_dir)
        self._pending = self._base / "pending"
        self._failed = self._base / "failed"
        self._failed_max_age_h = failed_max_age_h
        self._cleanup_timer: Optional[threading.Timer] = None

        self._pending.mkdir(parents=True, exist_ok=True)
        self._failed.mkdir(parents=True, exist_ok=True)
        logger.info(
            "ImageStorageService listo — directorio: '%s' | retención failed: %dh",
            self._base,
            self._failed_max_age_h,
        )

    # -------------------------------------------------------------------------
    # OPERACIONES PRINCIPALES
    # -------------------------------------------------------------------------

    def guardar_pendiente(self, gray_img: np.ndarray, station_code: str) -> Optional[Path]:
        """Persiste la imagen en pending/ y devuelve su ruta.

        Args:
            gray_img: imagen numpy (H×W, uint8, grayscale).
            station_code: código de la estación, usado en el nombre del fichero.
        Returns:
            Path del fichero creado, o None si la escritura falla.
        """
        path = self._pending / self._generar_nombre(station_code)
        try:
            cv2.imwrite(str(path), gray_img)
            return path
        except Exception as e:
            logger.error("Error al guardar imagen pendiente '%s': %s", path, e)
            return None

    def eliminar(self, path: Optional[Path]) -> None:
        """Elimina el fichero de disco. Silencioso si no existe o si path es None."""
        if path is None:
            return
        try:
            Path(path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("No se pudo eliminar imagen '%s': %s", path, e)

    def marcar_fallido(self, path: Optional[Path]) -> None:
        """Mueve la imagen de pending/ a failed/.

        Si el fichero ya no existe en pending/ (p. ej. fue eliminado antes),
        el método termina sin error.
        """
        if path is None:
            return
        try:
            src = Path(path)
            if src.exists():
                shutil.move(str(src), str(self._failed / src.name))
        except Exception as e:
            logger.warning("No se pudo mover imagen a failed/ '%s': %s", path, e)

    # -------------------------------------------------------------------------
    # LIMPIEZA
    # -------------------------------------------------------------------------

    def limpiar_al_inicio(self) -> None:
        """Elimina los ficheros huérfanos en pending/ de sesiones anteriores.

        Debe llamarse una vez al arrancar la aplicación, antes de iniciar el
        primer ciclo de escaneo.
        """
        eliminados = 0
        for f in self._pending.glob("*.png"):
            try:
                f.unlink()
                eliminados += 1
            except Exception as e:
                logger.warning("No se pudo eliminar huérfano '%s': %s", f, e)
        if eliminados:
            logger.info(
                "limpiar_al_inicio: %d imagen(es) huérfana(s) eliminada(s) de pending/",
                eliminados,
            )

    def limpiar_failed_antiguos(self) -> None:
        """Elimina de failed/ los ficheros con antigüedad superior a failed_max_age_h."""
        limite = datetime.now() - timedelta(hours=self._failed_max_age_h)
        eliminados = 0
        for f in self._failed.glob("*.png"):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < limite:
                    f.unlink()
                    eliminados += 1
            except Exception as e:
                logger.warning("Error al limpiar failed/ '%s': %s", f, e)
        if eliminados:
            logger.info(
                "limpiar_failed_antiguos: %d imagen(es) eliminada(s) (>%dh)",
                eliminados,
                self._failed_max_age_h,
            )

    def iniciar_limpieza_periodica(self) -> None:
        """Arranca el timer de limpieza periódica de failed/ (cada hora)."""
        self._programar_limpieza()

    def detener_limpieza_periodica(self) -> None:
        """Cancela el timer de limpieza periódica. Llamar al detener el sistema."""
        if self._cleanup_timer and self._cleanup_timer.is_alive():
            self._cleanup_timer.cancel()
            self._cleanup_timer = None

    # -------------------------------------------------------------------------
    # INTERNOS
    # -------------------------------------------------------------------------

    def _programar_limpieza(self) -> None:
        self.limpiar_failed_antiguos()
        self._cleanup_timer = threading.Timer(
            self._CLEANUP_INTERVAL_SEC, self._programar_limpieza
        )
        self._cleanup_timer.daemon = True
        self._cleanup_timer.name = "sai-img-cleanup"
        self._cleanup_timer.start()

    @staticmethod
    def _generar_nombre(station_code: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_code = station_code.replace("/", "-").replace("\\", "-")
        return f"{ts}_{safe_code}.png"
