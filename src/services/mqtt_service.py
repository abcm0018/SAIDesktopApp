import json
from datetime import datetime
import logging
from typing import Dict

from src.core.mqtt_manager import MqttManager
from src.domain.palet import PaletScanData
from src.utils.date_time_formatter import DateTimeFormatter

logger = logging.getLogger(__name__)


class MqttService:
    """
    Servicio de aplicación para publicación de datos de palets.
    
    Responsabilidades:
    - Transformar objetos de dominio a formato JSON
    - Validar datos antes de enviar
    - Coordinar el envío a través del MqttManager
    """

    def __init__(self, mqtt_manager: MqttManager):
        """
        Inicializa el servicio MQTT.
        
        Args:
            mqtt_manager: Instancia del gestor de infraestructura MQTT.
        """
        self.mqtt_manager = mqtt_manager

    def enviar_datos_palet(self, palet_data: PaletScanData, employee_number: str) -> bool:
        """
        Envía los datos de un palet escaneado al sistema backend.
        
        Args:
            palet_data: Datos del palet escaneado.
            employee_number: Número de empleado.
            
        Returns:
            True si el envío fue exitoso, False en caso contrario.
        """
        # Validación de completitud
        if not palet_data.is_complete():
            logger.warning(f"Intento de envío de palet incompleto (SSCC: {palet_data.sscc or 'N/A'})")
            return False

        # Validación de employee_number
        if not employee_number or not isinstance(employee_number, str):
            logger.error(f"Número de empleado inválido: {employee_number}")
            return False

        try:
            # Construir payload
            payload = self._build_payload(palet_data, employee_number)
            
            # Serializar a JSON
            json_payload = json.dumps(payload, ensure_ascii=False, indent=None)
            
            # Enviar a través del gestor MQTT
            enviado = self.mqtt_manager.publish_message(payload=json_payload)

            if enviado:
                logger.info(f"Palet {palet_data.sscc} enviado correctamente")
                return True
            else:
                logger.error(f"Fallo al enviar palet {palet_data.sscc}")
                return False

        except (ValueError, TypeError) as e:
            logger.error(f"Error de datos al construir payload: {e}")
            return False
        except Exception as e:
            logger.exception(f"Error crítico enviando datos de palet: {e}")
            return False

    def _build_payload(self, palet_data: PaletScanData, employee_number: str) -> Dict:
        """
        Construye el payload JSON para enviar al backend.
        
        NOTA: Asume que palet_data tiene fechas en formato UI (DD/MM/YYYY).
        Las transforma a formato ISO (YYYY-MM-DD) para el backend Java.
        
        Args:
            palet_data: Datos del palet.
            employee_number: Número de empleado.
            
        Returns:
            Diccionario con el payload formateado.
        """
        # Transformar fechas de formato UI a ISO
        iso_use_by_date = DateTimeFormatter.ui_date_to_iso(palet_data.product_use_by_date)
        iso_packaging_date = DateTimeFormatter.ui_date_to_iso(palet_data.packaging_date)
        iso_production_time = DateTimeFormatter.ui_time_to_iso(palet_data.production_time)
        
        # Timestamp actual del escaneo
        scan_timestamp = datetime.now().isoformat(timespec='seconds')
        
        return {
            "sscc": palet_data.sscc,
            "ean": palet_data.ean,
            "batchNumber": palet_data.batch_number,
            "productUseByDate": iso_use_by_date,
            "packagingDate": iso_packaging_date,
            "productionTime": iso_production_time,
            "sscc": palet_data.sscc,
            "employeeNumber": employee_number,
            "scanDate": scan_timestamp
        }