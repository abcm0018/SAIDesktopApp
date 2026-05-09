import logging
import queue
import threading
import time
import flet as ft

from src.config.app_config import AppConfig
from src.services.pallet_processing_service import PalletProcessingService

logger = logging.getLogger(__name__)


class DashboardController:
    def __init__(
            self,
            page: ft.Page,
            view,  # Recibirá la instancia de DashboardView
            auth_service,
            camera_service,
            yolo_service,
            scanner_service,
            mqtt_service,
            audit_service
    ):
        self.page = page
        self.view = view

        # Servicios
        self.auth_service = auth_service
        self.camera_service = camera_service
        self.yolo_service = yolo_service
        self.scanner_service = scanner_service
        self.mqtt_service = mqtt_service
        self.audit_service = audit_service

        self.pallet_service = PalletProcessingService()

        # Estado del controlador
        self.is_scanning = False
        self.lectura_bloqueada = False
        self.frame_queue = queue.Queue(maxsize=AppConfig.QUEUE_MAX_SIZE)

        # Cola de publicaciones MQTT — procesada en hilo dedicado
        self._mqtt_queue: queue.Queue = queue.Queue(maxsize=8)
        # Evento para el cooldown entre pallets — interruptible al detener el sistema
        self._cooldown_event = threading.Event()

        # Hilos
        self.camera_thread = None
        self.processing_thread = None
        self._mqtt_thread = None

    # -------------------------------------------------------------------------
    # ACCIONES DESDE LA VISTA (Inputs del usuario)
    # -------------------------------------------------------------------------
    def toggle_camera(self, encender: bool):
        """Reacciona al switch de la UI para encender/apagar el sistema."""
        if encender:
            self._start_system()
        else:
            self._stop_system()

    def logout(self):
        """Maneja el cierre de sesión."""
        self._stop_system()
        self.auth_service.logout()
        # Aquí le dirías al enrutador principal que cambie a la pantalla de login
        self.page.go("/login")

        # -------------------------------------------------------------------------

    # CONTROL DE HILOS Y FLUJO PRINCIPAL
    # -------------------------------------------------------------------------
    def _start_system(self):
        if not self.camera_service.iniciar_camara():
            self.view.mostrar_error("No se pudo conectar a la cámara.")
            self.view.apagar_switch()
            return

        self.is_scanning = True
        self.lectura_bloqueada = False
        self._cooldown_event.clear()
        self.pallet_service.reset_palet()

        self.view.iniciar_animacion_escaneo()

        self.camera_thread = threading.Thread(target=self._camera_capture_loop, daemon=True)
        self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self._mqtt_thread = threading.Thread(target=self._mqtt_sender_loop, daemon=True)

        self.camera_thread.start()
        self.processing_thread.start()
        self._mqtt_thread.start()

    def _stop_system(self):
        self.is_scanning = False
        self._cooldown_event.set()  # Desbloquea cualquier cooldown en curso

        if self.camera_service:
            self.camera_service.detener_camara()

        with self.frame_queue.mutex:
            self.frame_queue.queue.clear()

        self.view.detener_animacion_escaneo()

    def _camera_capture_loop(self):
        """Hilo Productor: Lee la cámara y mete frames en la cola."""
        while self.is_scanning:
            frame = self.camera_service.obtener_frame()
            if frame is not None:
                frame_b64 = self.camera_service.convertir_numpy_a_base64(
                    frame, quality=50, width_resize=AppConfig.VIDEO_PREVIEW_WIDTH
                )
                self.view.mostrar_frame_video(frame_b64)

                if not self.lectura_bloqueada:
                    try:
                        self.frame_queue.put_nowait(frame)
                    except queue.Full:
                        pass  # Frame descartado — el procesamiento no puede seguir el ritmo
            else:
                time.sleep(0.01)

    def _processing_loop(self):
        """
        Hilo Consumidor: Orquesta la IA y la Lógica de Negocio.
        Es la versión limpia del método que reparamos anteriormente.
        """
        while self.is_scanning:
            # 1. EVALUAR WATCHDOG (5 Segundos de parada)
            if self.pallet_service.evaluar_watchdog(AppConfig.READ_TIMEOUT_SEC):
                palet_actual = self.pallet_service.get_palet_actual()

                if palet_actual.sscc:
                    logger.info(f"Fin parada. Enviando palet SSCC: {palet_actual.sscc}")
                    self._finalizar_palet()
                else:
                    logger.warning("Fin parada sin SSCC. Etiqueta Dañada.")
                    self._handle_scan_timeout()

                with self.frame_queue.mutex:
                    self.frame_queue.queue.clear()
                continue

            # 2. OBTENER FRAME
            try:
                frame = self.frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self.lectura_bloqueada:
                self.frame_queue.task_done()
                continue

            # 3. PROCESAMIENTO IA Y FUSIÓN
            try:
                rois_detectados = self.yolo_service.detectar(frame)

                if rois_detectados is None or len(rois_detectados) > 0:
                    self.pallet_service.iniciar_temporizador()

                scan_result_dto = self.scanner_service.procesar_zonas(frame, rois_detectados)

                # Delega la lógica de negocio al servicio
                hubo_cambios = self.pallet_service.procesar_nuevos_datos(scan_result_dto)

                if hubo_cambios:
                    palet_actual = self.pallet_service.get_palet_actual()
                    self.view.actualizar_datos_palet(palet_actual)

                    if palet_actual.is_fully_captured():
                        self._finalizar_palet()
                        with self.frame_queue.mutex:
                            self.frame_queue.queue.clear()

            except Exception as e:
                logger.error(f"Error en hilo de procesamiento: {e}")
            finally:
                self.frame_queue.task_done()

    # -------------------------------------------------------------------------
    # RESOLUCIÓN DE LA LECTURA
    # -------------------------------------------------------------------------
    def _finalizar_palet(self):
        """Decisión de negocio: Encolar envío MQTT y preparar siguiente palet."""
        self.lectura_bloqueada = True
        palet = self.pallet_service.get_palet_actual()

        self.view.mostrar_estado_exito()

        # Encolar publicación MQTT — el hilo dedicado la procesa sin bloquear aquí
        empleado = self.auth_service.get_current_user() or "0000"
        try:
            self._mqtt_queue.put_nowait({
                "palet_data": palet,
                "employee_number": empleado,
                "station_code": self.page.session.get("station_code"),
                "station_cam_id": self.page.session.get("camera_id"),
            })
        except queue.Full:
            logger.error("Cola MQTT llena; palet SSCC=%s no enviado", palet.sscc)

        self.audit_service.log_scan_success(palet.sscc)

        # Cooldown interruptible: se desbloquea si el sistema se detiene
        self._cooldown_event.clear()
        self._cooldown_event.wait(timeout=AppConfig.POST_SEND_DELAY_SEC)

        self.pallet_service.reset_palet()
        self.view.limpiar_datos_palet()
        self.lectura_bloqueada = False

    def _handle_scan_timeout(self):
        """Decisión de negocio: Etiqueta dañada / Timeout."""
        self.lectura_bloqueada = True

        self.view.mostrar_estado_error_timeout()
        self.audit_service.log_scan_timeout("NO_SSCC_DETECTED")

        self._cooldown_event.clear()
        self._cooldown_event.wait(timeout=AppConfig.POST_SEND_DELAY_SEC)

        self.pallet_service.reset_palet()
        self.view.limpiar_datos_palet()
        self.lectura_bloqueada = False

    def _mqtt_sender_loop(self):
        """Hilo dedicado: consume la cola MQTT y publica sin bloquear el hilo de procesamiento."""
        while self.is_scanning or not self._mqtt_queue.empty():
            try:
                payload = self._mqtt_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                exito = self.mqtt_service.enviar_datos_palet(**payload)
                if not exito:
                    sscc = getattr(payload.get("palet_data"), "sscc", "?")
                    logger.error("Fallo MQTT para SSCC=%s", sscc)
            except Exception as e:
                logger.error("Error en envío MQTT: %s", e)
            finally:
                self._mqtt_queue.task_done()