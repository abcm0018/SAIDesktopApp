import os
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

load_dotenv()

# 1. Configuración del protocolo MQTT desde .env
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883)) # Por defecto 1883 si no existe
MQTT_TOPIC = os.getenv("MQTT_TOPIC")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID") # Opcional, pero recomendado
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

# 2. Funciones de callback (Opcional: para saber si conectó bien)
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Conectado al broker MQTT: {MQTT_BROKER}")
    else:
        print(f"Fallo en la conexión MQTT. Código: {rc}")

# 3. Generamos la instancia del cliente (Similar a 'engine' en database.py)
mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)

# Configuración de autenticación si existe usuario/pass
if MQTT_USER and MQTT_PASSWORD:
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

# Asignamos los callbacks
mqtt_client.on_connect = on_connect
