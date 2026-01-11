import zxingcpp
import cv2
import numpy as np
from typing import Any, List
from src.domain.palet import PaletScanData
from utils.gs1parser import GS1Parser

class ZXingBarcodeReader:
    """
    Fachada para la librería zxing-cpp.
    Responsabilidad: Obtener strings desde imágenes y orquestar la creación del DTO.
    """

    def scan_palet_image(self, image_source: Any) -> PaletScanData:
        """
        Procesa una imagen, lee TODOS los códigos de barras y agrega
        la información en un único objeto PaletScanData.
        """
        # 1. Lectura de imagen (soporta path o array numpy)
        if isinstance(image_source, str):
            img = cv2.imread(image_source)
        elif isinstance(image_source, np.ndarray):
            img = image_source
        else:
            raise ValueError("Fuente de imagen no soportada")

        if img is None:
            raise ValueError("No se pudo cargar la imagen")

        # 2. Detección con zxing-cpp
        results = zxingcpp.read_barcodes(img)
        
        # 3. Instanciamos el DTO vacío
        palet_data = PaletScanData()

        if not results:
            print("Warning: No se detectaron códigos.")
            return palet_data

        # 4. Agregación de datos
        # Un palet puede tener la info repartida en varios códigos (o repetida)
        print(f"--- Detectados {len(results)} códigos ---")
        
        for result in results:
            raw_text = result.text
            print(f"Procesando raw: {raw_text}")
            
            # Delegamos la lógica de parsing a la clase especializada
            parsed_dict = GS1Parser.parse(raw_text)
            
            # Actualizamos el DTO con lo que hayamos encontrado en este código específico
            palet_data.actualizar_datos(parsed_dict)

        return palet_data

# --- ZONA DE EJECUCIÓN (MAIN) ---
if __name__ == "__main__":
    # Simulación de uso real
    reader = ZXingBarcodeReader()
    
    # Asegúrate de poner la ruta correcta a tu imagen
    try:
        palet_result = reader.scan_palet_image("etiqueta_palet.jpeg")
        
        print("\n=== RESULTADO FINAL DEL DTO ===")
        print(palet_result.to_dict())
        
        if palet_result.is_complete():
            print("El palet está completamente identificado.")
        else:
            print("Faltan datos obligatorios del palet.")
            
    except Exception as e:
        print(f"Error: {e}")