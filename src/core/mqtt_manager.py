import logging
import threading
import time
from typing import Optional
import paho.mqtt.client as mqtt

from src.config.mqtt_config import MqttConfig

logger = logging.getLogger(__name__)


class MqttConnectionError(Exception):
    """Excepción lanzada cuando falla la conexión MQTT."""
    pass


class MqttManager:
    """
    Gestor de infraestructura MQTT.
    
    Responsabilidades:
    - Mantener conexión con el broker
    - Publicar mensajes crudos (bytes/string)
    - Manejar reconexiones automáticas
    """

    def __init__(self, config: MqttConfig):
        """
        Inicializa el gestor MQTT.
        
        Args:
            config: Configuración del broker MQTT.
        """
        config.validate()  # Validar antes de usar
        
        self.config = config
        self.client = mqtt.Client(client_id=self.config.client_id)
        self._is_connected = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        self._connect_event = threading.Event()

        # Configurar autenticación si existe
        if self.config.user and self.config.password:
            self.client.username_pw_set(self.config.user, self.config.password)

        # Registrar callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish

        logger.info(f"MqttManager inicializado: {self.config.broker}:{self.config.port}")

    @property
    def is_connected(self) -> bool:
        """Retorna el estado de conexión actual."""
        return self._is_connected

    def connect(self, timeout: float = 5.0) -> bool:
        """
        Establece conexión con el broker MQTT.
        
        Args:
            timeout: Tiempo máximo de espera en segundos.
            
        Returns:
            True si la conexión fue exitosa, False en caso contrario.
            
        Raises:
            MqttConnectionError: Si falla la conexión después de varios intentos.
        """
        try:
            logger.info(f"Conectando a {self.config.broker}:{self.config.port}...")
            self._connect_event.clear()
            self.client.connect(
                self.config.broker,
                self.config.port,
                self.config.keepalive
            )
            self.client.loop_start()

            connected = self._connect_event.wait(timeout=timeout)
            if not connected:
                logger.error("Timeout esperando conexión MQTT")
                return False

            self._reconnect_attempts = 0
            return True

        except ConnectionRefusedError:
            logger.error(f"Conexión rechazada por {self.config.broker}")
            return False
        except OSError as e:
            logger.error(f"Error de red al conectar: {e}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado al conectar: {e}", exc_info=True)
            return False

    def disconnect(self) -> None:
        """Cierra la conexión MQTT de forma limpia."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self._is_connected = False
            logger.info("Cliente MQTT desconectado")

    def publish_message(self, topic: Optional[str] = None, payload: str = "", qos: Optional[int] = None) -> bool:
        """
        Publica un mensaje en el topic especificado.
        
        Args:
            topic: Topic MQTT. Si es None, usa el topic por defecto.
            payload: Contenido del mensaje (string o JSON).
            qos: Quality of Service. Si es None, usa el QoS de config.
            
        Returns:
            True si el mensaje fue encolado exitosamente, False en caso contrario.
        """
        topic = topic or self.config.topic
        qos = qos if qos is not None else self.config.qos

        # Intentar reconectar si no está conectado
        if not self._is_connected:
            logger.warning("No conectado a MQTT, intentando reconectar...")
            if self.config.reconnect_on_failure:
                if not self._attempt_reconnect():
                    return False
            else:
                logger.error("Publicación fallida: sin conexión")
                return False

        try:
            result = self.client.publish(topic, payload, qos=qos)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Mensaje encolado en topic '{topic}' (mid: {result.mid})")
                return True
            else:
                logger.error(f"Error al publicar mensaje, código: {result.rc}")
                return False

        except ValueError as e:
            logger.error(f"Payload inválido: {e}")
            return False
        except Exception as e:
            logger.error(f"Error al publicar: {e}", exc_info=True)
            return False

    def _attempt_reconnect(self) -> bool:
        """Intenta reconectar con backoff exponencial (1s → 2s → 4s … 32s máx)."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(
                "Máximo de intentos de reconexión alcanzado (%d). Broker inaccesible.",
                self._max_reconnect_attempts
            )
            return False

        delay = min(2 ** self._reconnect_attempts, 32)
        self._reconnect_attempts += 1
        logger.info(
            "Reconexión %d/%d en %ds...",
            self._reconnect_attempts, self._max_reconnect_attempts, delay
        )
        time.sleep(delay)
        return self.connect()

    def _on_connect(self, client, userdata, flags, rc):
        """Callback ejecutado al conectar."""
        if rc == 0:
            self._is_connected = True
            self._connect_event.set()
            logger.info(f"Conectado a MQTT: {self.config.broker}")
        else:
            self._is_connected = False
            error_messages = {
                1: "Protocolo incorrecto",
                2: "Client ID inválido",
                3: "Servidor no disponible",
                4: "Usuario/contraseña incorrectos",
                5: "No autorizado"
            }
            error_msg = error_messages.get(rc, f"Error desconocido ({rc})")
            logger.error(f"Error de conexión MQTT: {error_msg}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback ejecutado al desconectar."""
        self._is_connected = False
        if rc != 0:
            logger.warning(f"Desconexión inesperada (código: {rc})")
            if self.config.reconnect_on_failure:
                logger.info("Intentando reconexión automática...")
        else:
            logger.info("Desconexión limpia de MQTT")

    def _on_publish(self, client, userdata, mid):
        """Callback ejecutado cuando un mensaje es publicado."""
        logger.debug(f"Mensaje publicado exitosamente (mid: {mid})")