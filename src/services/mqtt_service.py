import logging
import json
import time
from datetime import datetime
import paho.mqtt.client as mqtt

# 1. Importamos la configuración y el cliente desde tu nuevo fichero
# Asegúrate de que 'mqtt' sea el nombre correcto del fichero o ajusta la ruta (ej: from infrastructure.mqtt import ...)
from mqtt import mqtt_client, MQTT_BROKER, MQTT_PORT, MQTT_TOPIC

from src.model.palet import PaletScanData
# Suponiendo que User está definido en algún lugar, si no, impórtalo o ajusta el type hinting
# from src.model.user import User 

from src.utils.formatters import (
    formatear_fecha_gs1_a_java, 
    formatear_hora_gs1_a_java
)

# Instancia del logger a nivel de clase/módulo
logger = logging.getLogger(__name__)

class MqttService:

    def __init__(self):
        # 2. Usamos la instancia pre-configurada (Singleton pattern)
        self.client = mqtt_client
        
        # Guardamos las constantes importadas
        self.broker_host = MQTT_BROKER
        self.broker_port = MQTT_PORT
        self.topic = MQTT_TOPIC
        
        # 3. Sobrescribimos los callbacks del cliente importado.
        # Esto es necesario para que los eventos (connect/disconnect) modifiquen
        # el estado 'self.is_connected' de ESTA clase y usen tu logging específico.
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        
        self.is_connected = False
        
        # Nota: El client_id ya viene configurado desde mqtt.py
        logging.info(f"Servicio MQTT inicializado usando configuración de mqtt.py")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info(f"✅ Conectado exitosamente al broker MQTT en {self.broker_host}")
            self.is_connected = True
        else:
            logging.error(f"❌ Fallo al conectar con MQTT, código: {rc}")
            self.is_connected = False

    def _on_disconnect(self, client, userdata, rc):
        self.is_connected = False
        if rc != 0:
            logging.warning(f"Desconexión inesperada de MQTT. Código: {rc}.")
        else:
            logging.info("Desconectado de MQTT limpiamente.")

    def _on_publish(self, client, userdata, mid):
        logging.info(f"Mensaje MQTT (mid: {mid}) publicado exitosamente.")

    # --- Implementación de la Interfaz ---

    def connect(self):
        if self.is_connected:
            return
        try:
            # Usamos los parámetros importados para conectar
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start() # Inicia el bucle en un hilo separado
            
            # Esperar a que la conexión se establezca
            timeout = 5
            while not self.is_connected and timeout > 0:
                time.sleep(0.1)
                timeout -= 0.1
            
            if not self.is_connected:
                logging.error("Fallo de timeout al conectar con MQTT.")
                self.client.loop_stop()

        except Exception as e:
            logging.error(f"Error al iniciar conexión MQTT: {e}")

    def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

    def notify_palet_scanned(self, palet_data: PaletScanData, supervisor) -> bool:
        """
        Publica los datos de un palet en el topic configurado.
        """
        if not self.is_connected:
            logging.error("❌ No se puede publicar: Cliente MQTT no conectado.")
            return False
        
        hora_actual = datetime.now().time()
        fecha_simulada = datetime.combine(
            datetime(2025, 11, 27).date(), 
            hora_actual
        )
        
        try:
            # Preparamos el payload JSON
            message_body = {
                "ean": palet_data.ean,
                "batchNumber": palet_data.batch_number,
                "productUseByDate": formatear_fecha_gs1_a_java(palet_data.product_use_by_date),
                "packagingDate": formatear_fecha_gs1_a_java(palet_data.packaging_date),
                "productionTime": formatear_hora_gs1_a_java(palet_data.production_time),
                "sscc": palet_data.sscc,
                "employeeNumber": supervisor.employee_number,
                "scanDate": fecha_simulada.isoformat(timespec='seconds')
            }
            
            message = json.dumps(message_body, ensure_ascii=False)
            
            result = self.client.publish(
                self.topic, # Usamos el topic importado
                payload=message,
                qos=1
            )

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logging.info(f"Mensaje para SSCC {palet_data.sscc} enviado a la cola MQTT.")
                return True
            else:
                logging.warning(f"Error al poner en cola el mensaje (código: {result.rc}).")
                return False

        except Exception as e:
            logging.error(f"Error durante la publicación MQTT: {e}")
            return False