import logging

from src.domain.palet import PaletScanData

logger = logging.getLogger(__name__)

class PalletProcessingService:
    """
    Servicio encargado de mantener el estado de la lectura actual y aplicar
    las reglas de negocio para la fusión y validación de datos del palet
    """
    def __init__(self):
        self.palet_acumulado = PaletScanData()

    def procesar_nuevos_datos(self, nuevo_dato: PaletScanData) -> bool:
        """
        Algoritmo de fusión: Rellena los huecos del palet acumulado con los nuevos datos leídos.
        Retorna True si hubo algún cambio/actualización en el estado.
        """
        if not nuevo_dato:
            return False

        acc = self.palet_acumulado
        hubo_cambios = False

        # Acceso directo por atributo — evita getattr/setattr en el hot path (~30 fps)
        if nuevo_dato.sscc and not acc.sscc:
            acc.sscc = nuevo_dato.sscc
            hubo_cambios = True
        if nuevo_dato.ean and not acc.ean:
            acc.ean = nuevo_dato.ean
            hubo_cambios = True
        if nuevo_dato.batch_number and not acc.batch_number:
            acc.batch_number = nuevo_dato.batch_number
            hubo_cambios = True
        if nuevo_dato.product_use_by_date and not acc.product_use_by_date:
            acc.product_use_by_date = nuevo_dato.product_use_by_date
            hubo_cambios = True
        if nuevo_dato.packaging_date and not acc.packaging_date:
            acc.packaging_date = nuevo_dato.packaging_date
            hubo_cambios = True
        if nuevo_dato.production_time and not acc.production_time:
            acc.production_time = nuevo_dato.production_time
            hubo_cambios = True

        # Actualizar flag cacheado una sola vez cuando hay cambios y aún no está completo
        if hubo_cambios and not acc._fully_captured:
            acc._fully_captured = bool(
                acc.sscc and acc.ean and acc.batch_number
                and acc.product_use_by_date and acc.packaging_date
            )

        return hubo_cambios

    def get_palet_actual(self) -> PaletScanData:
        """Devuelve el estado actual del palet en memoria."""
        return self.palet_acumulado

    def reset_palet(self):
        """Limpia el estado en memoria para prepararse para la siguiente caja."""
        self.palet_acumulado = PaletScanData()
        logger.debug("Estado del palet reseteado para nueva lectura.")

    def evaluar_watchdog(self, timeout_sec: float) -> bool:
        """
        Evalúa si el tiempo de lectura (los 5 segundos físicos) se ha agotado.
        """
        if self.palet_acumulado.scan_start_time is None:
            return False

        return self.palet_acumulado.has_timed_out(timeout_sec)

    def iniciar_temporizador(self):
        """Inicia el cronómetro de lectura si no estaba iniciado."""
        self.palet_acumulado.init_timeout()
