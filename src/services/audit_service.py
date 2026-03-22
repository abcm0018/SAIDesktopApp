import logging
from datetime import datetime, timedelta

from core.database_manager import DatabaseManager
from domain.audit_scan_incidents import AuditScanIncidents
from domain.palet import PaletScanData

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def registrar_incidencia(self, employee_number: str, palet_data: PaletScanData, motivo: str = "ETIQUETA DAÑADA"):
        """
        Registra una incidencia de auditoría en la base de datos.

        Args:
            employee_number (str): Número de empleado que registró la incidencia.
            palet_data (PaletScanData): Datos del palet que generaron la incidencia.
            motivo (str, optional): Motivo de la incidencia. Por defecto es "ETIQUETA DAÑADA".
        """

        sscc = palet_data.sscc

        if not sscc:
            logger.warning("Incidencia descartada: No se ha identificado el SSCC (dato obligatorio para auditoria")
            return False

        try:
            with self.db.session() as session:

                tiempo_limite = datetime.now() - timedelta(minutes=10)

                existe_reciente = session.query(AuditScanIncidents).filter(
                    AuditScanIncidents.sscc_attempt == sscc,
                    AuditScanIncidents.timestamp >= tiempo_limite,
                    AuditScanIncidents.incident_type == motivo
                ).first()

                if existe_reciente:
                    logger.info(f"Incidencia para SSCC {sscc} ignorada (ya reportada hace menos de 10 min).")
                    return False

                logger.info(f"Registrando incidencia de auditoría para empleado {employee_number} con motivo '{motivo}'")

                incidencia = AuditScanIncidents(
                    employee_number=employee_number,
                    sscc_attempt=palet_data.sscc,
                    ean_attempt=palet_data.ean,
                    batch_attempt=palet_data.batch_number,
                    incident_type=motivo,
                    details=f"Lectura incompleta. Fechas leídas: {palet_data.packaging_date or 'N/A'}"
                )
                session.add(incidencia)
                session.commit()
                logger.info(f"Incidencia registrada con éxito para empleado {employee_number}")

                return True
        except Exception as e:
            logger.error(f"Error al registrar incidencia de auditoría: {e}")
            return False