import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class MqttConfig:
    """Configuración inmutable para conexión MQTT."""
    
    broker: str
    port: int
    topic: str # Canal MQTT para publicación de datos de palets
    error_topic: str # Canal MQTT para reportar incidencias y lecturas fallidas
    client_id: str
    user: Optional[str] = None
    password: Optional[str] = None
    keepalive: int = 60
    qos: int = 1
    reconnect_on_failure: bool = True

    @staticmethod
    def from_env() -> 'MqttConfig':
        """
        Factory que carga configuración desde variables de entorno.
        
        Variables esperadas:
        - MQTT_BROKER
        - MQTT_PORT
        - MQTT_TOPIC
        - MQTT_CLIENT_ID
        - MQTT_USER (opcional)
        - MQTT_PASSWORD (opcional)
        - MQTT_QOS (opcional, default: 1)
        """
        return MqttConfig(
            broker=os.getenv("MQTT_BROKER", "localhost"),
            port=int(os.getenv("MQTT_PORT", "1883")),
            topic=os.getenv("MQTT_TOPIC", "inventario/palets/escaneados"),
            error_topic=os.getenv("MQTT_TOPIC_ERRORS", "inventario/palets/incidencias"),
            client_id=os.getenv("MQTT_CLIENT_ID", "python_scanner_client"),
            user=os.getenv("MQTT_USER") or None,
            password=os.getenv("MQTT_PASSWORD") or None,
            qos=int(os.getenv("MQTT_QOS", "1"))
        )

    def validate(self) -> None:
        """
        Valida que la configuración sea correcta.
        
        Raises:
            ValueError: Si la configuración es inválida.
        """
        if not self.broker:
            raise ValueError("MQTT_BROKER no puede estar vacío")
        if not (1 <= self.port <= 65535):
            raise ValueError(f"Puerto MQTT inválido: {self.port}")
        if not self.topic:
            raise ValueError("MQTT_TOPIC no puede estar vacío")
        if not (0 <= self.qos <= 2):
            raise ValueError(f"QoS debe estar entre 0 y 2, recibido: {self.qos}")