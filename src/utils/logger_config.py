import logging.config
import yaml
import os

def setup_logging(path='logging_config.yaml'):
    """Carga la configuración de logs desde un archivo YAML."""
    if os.path.exists(path):
        with open(path, 'rt') as f:
            try:
                config = yaml.safe_load(f.read())
                logging.config.dictConfig(config)
                print(f"Logs configurados desde {path}")
            except Exception as e:
                print(f"Error cargando configuración de logs: {e}")
                # Fallback básico por si falla el YAML
                logging.basicConfig(level=logging.INFO)
    else:
        print(f"No se encontró {path}. Usando configuración por defecto.")
        logging.basicConfig(level=logging.INFO)