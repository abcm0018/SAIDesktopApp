import json
from datetime import datetime
import logging
from typing import Any, Dict

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

    def enviar_datos_palet(self, palet_data: PaletScanData, employee_number: str, station_code: str, station_cam_id: str) -> bool:
        """
        Envía los datos de un palet escaneado al sistema backend.
        
        Args:
            palet_data: Datos del palet escaneado.
            employee_number: Número de empleado.
            station_code: Código del puesto de trabajo.
            station_cam_id: Identificador de la cámara del puesto de trabajo.
        Returns:
            True si el envío fue exitoso, False en caso contrario.
        """
        # Validación de employee_number
        if not employee_number or not isinstance(employee_number, str):
            logger.error(f"Número de empleado inválido: {employee_number}")
            return False

        try:
            # Construir payload
            payload = self._build_payload(palet_data, employee_number, station_code, station_cam_id)
            
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
        
        
    def send_scan_incident(self, partial_data: PaletScanData) -> bool:
        """
        Sends a report about a damaged or incomplete label scan.
        Ensures all fields are present, filling missing ones with 'NO DATA'.
        """
        try:
            # Helper local para limpiar nulos/vacíos
            def _sanitize(value: Any) -> str:
                if value is None:
                    return "NO DATA"
                str_val = str(value).strip()
                return str_val if str_val else "NO DATA"

            # Construimos el payload completo, sin huecos
            payload = {
                "event_type": "DAMAGED_LABEL_TIMEOUT",
                "timestamp": datetime.now().isoformat(),
                "device_id": "CAMERA_01", # Opcional: si tienes config de ID
                "captured_data": {
                    "sscc": _sanitize(partial_data.sscc),
                    "ean": _sanitize(partial_data.ean),
                    "batch_number": _sanitize(partial_data.batch_number),
                    "expiration_date": _sanitize(partial_data.product_use_by_date),
                    "packaging_date": _sanitize(partial_data.packaging_date),
                    "production_time": _sanitize(partial_data.production_time)
                }
            }

            logger.warning(f"Reporting incident to MQTT: {json.dumps(payload)}")
            
            target_topic = self.mqtt_manager.config.error_topic
            return self.mqtt_manager.publish(target_topic, payload)

        except Exception as e:
            logger.error(f"Failed to send incident report: {e}")
            return False
        

    @staticmethod
    def _build_payload(palet_data: PaletScanData, employee_number: str, station_code: str, station_cam_id: str) -> Dict:
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
            "employeeNumber": employee_number,
            "scanDate": scan_timestamp,
            "stationId": station_code,
            "cameraId": station_cam_id
        }