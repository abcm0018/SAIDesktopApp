import zxingcpp
import numpy as np
import cv2
import logging
from typing import List, Tuple
from src.config.yolo_config import YoloConfig
from src.domain.palet import PaletScanData
from src.utils.gs1parser import GS1Parser

logger = logging.getLogger(__name__)

class ScannerService:
    """
    Servicio de Dominio encargado de la lectura (decodificación) de códigos de barras.
    OPTIMIZADO: Filtro de formatos, mejora de contraste y estrategias de reintento.
    """

    def __init__(self):
        # 1. DEFINIR FORMATOS ESPERADOS
        self.formatos_validos = (
            zxingcpp.BarcodeFormat.Code128 | 
            zxingcpp.BarcodeFormat.ITF | 
            zxingcpp.BarcodeFormat.DataMatrix
        )
        
        # 2. Configurar CLAHE (Contrast Limited Adaptive Histogram Equalization)
        # Esto ayuda mucho con códigos bajo film plástico brillante.
        self.clahe = cv2.createCLAHE(
            clipLimit=YoloConfig.CLAHE_CLIP_LIMIT, 
            tileGridSize=YoloConfig.CLAHE_GRID_SIZE
        )

    def procesar_zonas(self, frame: np.ndarray, rois: List[Tuple[int, int, int, int]]) -> PaletScanData:
        palet_result = PaletScanData()

        if frame is None:
            return palet_result

        try:
            # Convertimos a gris una sola vez para eficiencia
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                gray_img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray_img = frame

            codigos_leidos = []
            
            # --- ESTRATEGIA A: Zonas YOLO (Con reintentos de mejora) ---
            if rois:
                h_img, w_img = gray_img.shape
                
                for (x, y, w, h) in rois:
                    # Padding generoso para asegurar la "Quiet Zone" blanca alrededor del código
                    pad = 20 
                    x1 = max(0, x - pad)
                    y1 = max(0, y - pad)
                    x2 = min(w_img, x + w + pad)
                    y2 = min(h_img, y + h + pad)
                    
                    roi_crop = gray_img[y1:y2, x1:x2]
                    
                    # Intento 1: Lectura directa (Rápida)
                    res = self._decodificar_recorte(roi_crop)
                    
                    # Intento 2: Si falla, aplicamos mejora de contraste (Lento pero robusto)
                    if not res:
                        roi_enhanced = self.clahe.apply(roi_crop)
                        res = self._decodificar_recorte(roi_enhanced)
                    
                    # Intento 3 (Opcional): Invertir color (útil para etiquetas negras con letras blancas)
                    # if not res:
                    #     res = self._decodificar_recorte(cv2.bitwise_not(roi_crop))

                    codigos_leidos.extend(res)

            # --- ESTRATEGIA B: Fallback Central ---
            if not rois and not codigos_leidos:
                h, w = gray_img.shape
                cy, cx = h // 2, w // 2
                # Recorte central
                roi_center = gray_img[int(cy - h*0.25):int(cy + h*0.25), 
                                      int(cx - w*0.4):int(cx + w*0.4)]
                
                codigos_leidos.extend(self._decodificar_recorte(roi_center))

            # --- PROCESAMIENTO Y PARSEO ---
            procesados = set()
            for result in codigos_leidos:
                raw_text = result.text
                
                if raw_text in procesados or len(raw_text) < 5:
                    continue

                procesados.add(raw_text)
                
                # Parseo GS1
                datos_parsed = GS1Parser.parse(raw_text)
                if datos_parsed:
                    palet_result.actualizar_datos(datos_parsed)
                    logger.debug(f"Lectura exitosa ({result.format}): {raw_text}")

        except Exception as e:
            logger.error(f"Error scanner: {e}")

        return palet_result

    def _decodificar_recorte(self, imagen_gris: np.ndarray):
        """Wrapper para llamar a zxing-cpp con los parámetros óptimos"""
        if imagen_gris.size == 0:
            return []
            
        return zxingcpp.read_barcodes(
            imagen_gris,
            formats=self.formatos_validos,
            try_rotate=True,
            binarizer=zxingcpp.Binarizer.LocalAverage # LocalAverage es mejor para sombras que GlobalHistogram
        )