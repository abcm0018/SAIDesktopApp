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

        # Conteo temporal de los SSCC detectados durante la pasada actual.
        self._candidatos_sscc = {}

    def _confirmar_sscc(self, sscc: str):
        """
        Confirma el SSCC mediante varias lecturas.

        Se acepta cuando:
        - se ha leído al menos tres veces;
        - tiene al menos dos lecturas de ventaja sobre el segundo candidato.
        """
        sscc = str(sscc).strip()

        if not sscc:
            return None

        self._candidatos_sscc[sscc] = (
                self._candidatos_sscc.get(sscc, 0) + 1
        )

        candidatos_ordenados = sorted(
            self._candidatos_sscc.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        mejor_sscc, mejores_votos = candidatos_ordenados[0]

        segundos_votos = (
            candidatos_ordenados[1][1]
            if len(candidatos_ordenados) > 1
            else 0
        )

        if mejores_votos >= 3 and mejores_votos - segundos_votos >= 2:
            logger.info(
                "SSCC confirmado: %s (%d lecturas)",
                mejor_sscc,
                mejores_votos,
            )
            return mejor_sscc

        return None

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
            sscc_confirmado = self._confirmar_sscc(
                nuevo_dato.sscc
            )

            if sscc_confirmado:
                acc.sscc = sscc_confirmado
                self._candidatos_sscc.clear()
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
        """Limpia el estado para prepararse para la siguiente lectura."""
        self.palet_acumulado = PaletScanData()
        self._candidatos_sscc.clear()

        logger.debug(
            "Estado del palet reseteado para nueva lectura."
        )

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
