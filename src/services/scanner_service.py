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

        # Evita repetir continuamente en el log la misma lectura.
        # Se utiliza temporalmente para diagnosticar ZXing y el parser GS1.
        self._lecturas_diagnosticadas = set()

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
                    # ---------------------------------------------------------
                    # INTENTO 1: ROI habitual con margen proporcional
                    # ---------------------------------------------------------

                    pad_x = max(20, int(w * 0.10))
                    pad_y = max(20, int(h * 0.10))

                    x1 = max(0, x - pad_x)
                    y1 = max(0, y - pad_y)
                    x2 = min(w_img, x + w + pad_x)
                    y2 = min(h_img, y + h + pad_y)

                    roi_crop = gray_img[y1:y2, x1:x2]

                    res = self._decodificar_recorte(
                        roi_crop,
                        try_rotate=False,
                    )

                    # ---------------------------------------------------------
                    # INTENTO 2: ROI ampliada
                    # ---------------------------------------------------------

                    if not res:
                        pad_x_ampliado = max(40, int(w * 0.25))
                        pad_y_ampliado = max(30, int(h * 0.25))

                        x1_ampliado = max(0, x - pad_x_ampliado)
                        y1_ampliado = max(0, y - pad_y_ampliado)
                        x2_ampliado = min(w_img, x + w + pad_x_ampliado)
                        y2_ampliado = min(h_img, y + h + pad_y_ampliado)

                        roi_ampliada = gray_img[
                            y1_ampliado:y2_ampliado,
                            x1_ampliado:x2_ampliado,
                        ]

                        res = self._decodificar_recorte(
                            roi_ampliada,
                            try_rotate=False,
                        )

                    # ---------------------------------------------------------
                    # INTENTO 3: ROI ampliada con CLAHE y rotación
                    # ---------------------------------------------------------

                    if not res:
                        roi_enhanced = self.clahe.apply(
                            roi_ampliada
                        )

                        res = self._decodificar_recorte(
                            roi_enhanced,
                            try_rotate=True,
                        )

                    # Intento 4: corregir inclinaciones pequeñas en ambos sentidos.
                    # Solo se ejecuta cuando las estrategias anteriores han fallado.
                    if not res:
                        for angulo in (-15, 15):
                            roi_rotada = self._rotar_roi(
                                roi_enhanced,
                                angulo,
                            )

                            res = self._decodificar_recorte(
                                roi_rotada,
                                try_rotate=False,
                            )

                            if res:
                                logger.debug(
                                    "Código recuperado corrigiendo una inclinación de %d grados.",
                                    angulo,
                                )
                                break

                    codigos_leidos.extend(res)

            # --- ESTRATEGIA B: FALLBACK CUANDO LAS ROI NO DAN RESULTADO ---
            if not codigos_leidos:
                if rois:
                    # YOLO encontró una posible etiqueta, pero ninguna ROI pudo
                    # decodificarse. Se realiza un intento directo sobre el fotograma
                    # completo para recuperar códigos que hayan quedado fuera del recorte.
                    resultados_frame = self._decodificar_recorte(
                        gray_img,
                        try_rotate=False,
                    )

                    if resultados_frame:
                        logger.debug(
                            "Fallback de fotograma completo: %d código(s) recuperado(s).",
                            len(resultados_frame),
                        )

                    codigos_leidos.extend(resultados_frame)

                else:
                    # Si YOLO no encontró ninguna región, se conserva el intento
                    # sobre la zona central, que es más rápido que procesar toda
                    # la imagen con transformaciones adicionales.
                    h, w = gray_img.shape
                    cy, cx = h // 2, w // 2

                    roi_center = gray_img[
                        int(cy - h * 0.25):int(cy + h * 0.25),
                        int(cx - w * 0.4):int(cx + w * 0.4),
                    ]

                    codigos_leidos.extend(
                        self._decodificar_recorte(
                            roi_center,
                            try_rotate=False,
                        )
                    )

            # --- PROCESAMIENTO Y PARSEO ---
            procesados = set()

            for result in codigos_leidos:
                raw_text = result.text or ""

                # Asegurar que siempre trabajamos con texto.
                if not isinstance(raw_text, str):
                    raw_text = str(raw_text)

                if raw_text in procesados or len(raw_text) < 5:
                    continue

                procesados.add(raw_text)

                # Interpretar la cadena obtenida mediante la estructura GS1.
                datos_parsed = GS1Parser.parse(raw_text)

                # Diagnóstico temporal. %r permite visualizar caracteres especiales
                # como el separador GS: '\x1d'.
                clave_diagnostico = (str(result.format), raw_text)

                if clave_diagnostico not in self._lecturas_diagnosticadas:
                    self._lecturas_diagnosticadas.add(clave_diagnostico)

                    logger.info(
                        "DIAGNÓSTICO ZXing: formato=%s, texto_bruto=%r",
                        result.format,
                        raw_text,
                    )

                    logger.info(
                        "DIAGNÓSTICO GS1Parser: campos_extraídos=%s",
                        datos_parsed or {},
                    )

                if datos_parsed:
                    palet_result.actualizar_datos(datos_parsed)

                    logger.debug(
                        "Lectura exitosa (%s): %s",
                        result.format,
                        raw_text,
                    )

        except Exception as e:
            logger.error(f"Error scanner: {e}")

        return palet_result

    def _calcular_nitidez(self, imagen) -> float:
        """
        Calcula la nitidez mediante la varianza del Laplaciano.

        Un valor mayor indica, en general, que la imagen contiene
        más bordes definidos. No se utiliza todavía para descartar
        regiones; únicamente para diagnóstico.
        """
        if imagen is None or imagen.size == 0:
            return 0.0

        if len(imagen.shape) == 3:
            imagen_gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        else:
            imagen_gris = imagen

        return float(
            cv2.Laplacian(
                imagen_gris,
                cv2.CV_64F,
            ).var()
        )

    def es_frame_nitido(self, frame) -> bool:
        """
        Comprueba si el fotograma completo supera el umbral
        mínimo de nitidez configurado.
        """
        if frame is None or frame.size == 0:
            return False

        variance = self._calcular_nitidez(frame)

        return variance >= YoloConfig.BLUR_VAR_THRESHOLD

    def escanear_imagen_completa(self, gray_img: np.ndarray) -> PaletScanData:
        """
        Escanea el frame completo en escala de grises sin ROIs previas de YOLO.

        Estrategia de dos intentos:
          1. Decodificación directa sin rotación (rápido, ~15-30 ms).
          2. CLAHE + rotación si el primero falla (robusto, ~30-60 ms adicionales).

        Args:
            gray_img: imagen numpy (H×W, uint8, grayscale).
        Returns:
            PaletScanData con los campos decodificados (puede estar parcialmente relleno).
        """
        palet_result = PaletScanData()

        if gray_img is None or gray_img.size == 0:
            return palet_result

        try:
            resultados = self._decodificar_recorte(gray_img, try_rotate=False)

            if not resultados:
                img_enhanced = self.clahe.apply(gray_img)
                resultados = self._decodificar_recorte(img_enhanced, try_rotate=True)

            procesados = set()
            for result in resultados:
                raw_text = result.text
                if raw_text in procesados or len(raw_text) < 5:
                    continue
                procesados.add(raw_text)
                datos_parsed = GS1Parser.parse(raw_text)
                if datos_parsed:
                    palet_result.actualizar_datos(datos_parsed)
                    logger.debug("Full-frame decode (%s): %s", result.format, raw_text)

        except Exception as e:
            logger.error("Error en escaneo full-frame: %s", e)

        return palet_result

    def _rotar_roi(
            self,
            imagen: np.ndarray,
            angulo: float,
    ) -> np.ndarray:
        """
        Rota una ROI sin recortar sus esquinas.
        """

        if imagen is None or imagen.size == 0:
            return imagen

        alto, ancho = imagen.shape[:2]
        centro = (ancho / 2.0, alto / 2.0)

        matriz = cv2.getRotationMatrix2D(
            centro,
            angulo,
            1.0,
        )

        coseno = abs(matriz[0, 0])
        seno = abs(matriz[0, 1])

        nuevo_ancho = int(
            alto * seno + ancho * coseno
        )
        nuevo_alto = int(
            alto * coseno + ancho * seno
        )

        matriz[0, 2] += nuevo_ancho / 2.0 - centro[0]
        matriz[1, 2] += nuevo_alto / 2.0 - centro[1]

        return cv2.warpAffine(
            imagen,
            matriz,
            (nuevo_ancho, nuevo_alto),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )

    def _decodificar_recorte(self, imagen_gris: np.ndarray, try_rotate: bool = False):
        """Wrapper para llamar a zxing-cpp con los parámetros óptimos"""
        if imagen_gris.size == 0:
            return []

        return zxingcpp.read_barcodes(
            imagen_gris,
            formats=self.formatos_validos,
            try_rotate=try_rotate,
            binarizer=zxingcpp.Binarizer.LocalAverage
        )