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

        # Candidatos temporales para los campos que requieren confirmación
        # antes de incorporarse al palet acumulado.
        self._candidatos_ean = {}
        self._candidatos_batch = {}
        self._candidatos_best_before = {}
        self._candidatos_produccion = {}

    @staticmethod
    def _validar_digito_control_gs1(valor: str, longitud: int) -> bool:
        """
        Valida el dígito de control de un identificador GS1
        mediante el algoritmo módulo 10.
        """
        valor = str(valor).strip()

        if len(valor) != longitud or not valor.isdigit():
            return False

        cuerpo = valor[:-1]
        digito_control = int(valor[-1])

        suma = 0
        for indice, digito in enumerate(reversed(cuerpo)):
            peso = 3 if indice % 2 == 0 else 1
            suma += int(digito) * peso

        esperado = (10 - (suma % 10)) % 10

        return esperado == digito_control

    @classmethod
    def _validar_gtin(cls, gtin: str) -> bool:
        """Valida un GTIN-14 mediante su dígito de control GS1."""
        return cls._validar_digito_control_gs1(gtin, 14)

    @classmethod
    def _validar_sscc(cls, sscc: str) -> bool:
        """Valida un SSCC de 18 dígitos mediante su dígito de control GS1."""
        return cls._validar_digito_control_gs1(sscc, 18)

    @staticmethod
    def _confirmar_candidato(
            candidatos: dict,
            valor,
            min_lecturas: int = 2,
            ventaja_minima: int = 1,
    ):
        """
        Confirma un valor cuando aparece repetidamente y mantiene una ventaja
        mínima frente al segundo candidato más frecuente.
        """
        if valor is None:
            return None, 0

        if isinstance(valor, str):
            valor = valor.strip()
            if not valor:
                return None, 0

        candidatos[valor] = candidatos.get(valor, 0) + 1

        ordenados = sorted(
            candidatos.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        mejor_valor, mejores_votos = ordenados[0]
        segundos_votos = ordenados[1][1] if len(ordenados) > 1 else 0

        if (
                mejores_votos >= min_lecturas
                and mejores_votos - segundos_votos >= ventaja_minima
        ):
            return mejor_valor, mejores_votos

        return None, mejores_votos

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
        Fusiona los datos obtenidos en fotogramas sucesivos y confirma los
        campos mediante consistencia temporal antes de fijarlos en el palet.
        """
        if not nuevo_dato:
            return False

        acc = self.palet_acumulado
        hubo_cambios = False

        # SSCC: primero se valida el dígito de control y después
        # se aplica la confirmación temporal reforzada de 3 lecturas.
        if nuevo_dato.sscc and not acc.sscc:
            if self._validar_sscc(nuevo_dato.sscc):
                sscc_confirmado = self._confirmar_sscc(nuevo_dato.sscc)

                if sscc_confirmado:
                    acc.sscc = sscc_confirmado
                    self._candidatos_sscc.clear()
                    hubo_cambios = True
            else:
                logger.debug(
                    "SSCC descartado por dígito de control no válido: %s",
                    nuevo_dato.sscc,
                )

        # GTIN/EAN: primero se valida el dígito de control y después se exigen
        # dos lecturas coincidentes antes de incorporarlo al palet.
        if nuevo_dato.ean and not acc.ean:
            if self._validar_gtin(nuevo_dato.ean):
                ean_confirmado, votos = self._confirmar_candidato(
                    self._candidatos_ean,
                    str(nuevo_dato.ean).strip(),
                )

                if ean_confirmado:
                    acc.ean = ean_confirmado
                    self._candidatos_ean.clear()
                    hubo_cambios = True
                    logger.info(
                        "GTIN confirmado: %s (%d lecturas)",
                        ean_confirmado,
                        votos,
                    )
            else:
                logger.debug(
                    "GTIN descartado por dígito de control no válido: %s",
                    nuevo_dato.ean,
                )

        # Lote: al no disponer de dígito de control, se confirma por repetición.
        if nuevo_dato.batch_number and not acc.batch_number:
            batch_confirmado, votos = self._confirmar_candidato(
                self._candidatos_batch,
                str(nuevo_dato.batch_number).strip(),
            )

            if batch_confirmado:
                acc.batch_number = batch_confirmado
                self._candidatos_batch.clear()
                hubo_cambios = True
                logger.info(
                    "Lote confirmado: %s (%d lecturas)",
                    batch_confirmado,
                    votos,
                )

        # Fecha de consumo preferente/caducidad: el parser ya descarta fechas
        # imposibles; aquí se exige además consistencia entre fotogramas.
        if nuevo_dato.product_use_by_date and not acc.product_use_by_date:
            fecha_confirmada, votos = self._confirmar_candidato(
                self._candidatos_best_before,
                str(nuevo_dato.product_use_by_date).strip(),
            )

            if fecha_confirmada:
                acc.product_use_by_date = fecha_confirmada
                self._candidatos_best_before.clear()
                hubo_cambios = True
                logger.info(
                    "Fecha de consumo preferente confirmada: %s (%d lecturas)",
                    fecha_confirmada,
                    votos,
                )

        # El AI 8008 aporta conjuntamente fecha y hora de producción. Se vota
        # la pareja completa para evitar combinar valores de lecturas distintas.
        if (
            nuevo_dato.packaging_date
            and nuevo_dato.production_time
            and (not acc.packaging_date or not acc.production_time)
        ):
            candidato_produccion = (
                str(nuevo_dato.packaging_date).strip(),
                str(nuevo_dato.production_time).strip(),
            )

            produccion_confirmada, votos = self._confirmar_candidato(
                self._candidatos_produccion,
                candidato_produccion,
            )

            if produccion_confirmada:
                fecha_produccion, hora_produccion = produccion_confirmada

                if not acc.packaging_date:
                    acc.packaging_date = fecha_produccion
                    hubo_cambios = True

                if not acc.production_time:
                    acc.production_time = hora_produccion
                    hubo_cambios = True

                self._candidatos_produccion.clear()

                logger.info(
                    "Fecha/hora de producción confirmada: %s %s (%d lecturas)",
                    fecha_produccion,
                    hora_produccion,
                    votos,
                )

        # Actualizar flag cacheado una sola vez cuando hay cambios y aún no está completo.
        if hubo_cambios and not acc._fully_captured:
            acc._fully_captured = bool(
                acc.sscc
                and acc.ean
                and acc.batch_number
                and acc.product_use_by_date
                and acc.packaging_date
                and acc.production_time
            )

        return hubo_cambios

    def get_palet_actual(self) -> PaletScanData:
        """Devuelve el estado actual del palet en memoria."""
        return self.palet_acumulado

    def reset_palet(self):
        """Limpia el estado para prepararse para la siguiente lectura."""
        self.palet_acumulado = PaletScanData()
        self._candidatos_sscc.clear()
        self._candidatos_ean.clear()
        self._candidatos_batch.clear()
        self._candidatos_best_before.clear()
        self._candidatos_produccion.clear()

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
