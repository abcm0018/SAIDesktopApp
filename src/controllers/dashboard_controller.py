import logging
import queue
import threading
import time
import flet as ft

from src.config.app_config import AppConfig
from src.config.routes import AppRoutes
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
            audit_service,
            image_storage_service,
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
        self.image_storage_service = image_storage_service

        self.pallet_service = PalletProcessingService()

        # Estado del controlador — thread-safe mediante threading.Event
        self._scanning = threading.Event()
        self._blocked = threading.Event()

        # Cola de publicaciones MQTT — procesada en hilo dedicado
        self._mqtt_queue: queue.Queue = queue.Queue(maxsize=8)
        # Evento para el cooldown entre pallets — interruptible al detener el sistema
        self._cooldown_event = threading.Event()

        # Hilos
        self.camera_thread = None
        self.processing_thread = None
        self._mqtt_thread = None

    # -------------------------------------------------------------------------
    # PROPIEDADES THREAD-SAFE
    # -------------------------------------------------------------------------
    @property
    def is_scanning(self) -> bool:
        return self._scanning.is_set()

    @is_scanning.setter
    def is_scanning(self, value: bool) -> None:
        if value:
            self._scanning.set()
        else:
            self._scanning.clear()

    @property
    def lectura_bloqueada(self) -> bool:
        return self._blocked.is_set()

    @lectura_bloqueada.setter
    def lectura_bloqueada(self, value: bool) -> None:
        if value:
            self._blocked.set()
        else:
            self._blocked.clear()

    # -------------------------------------------------------------------------
    # ACCIONES DESDE LA VISTA (Inputs del usuario)
    # -------------------------------------------------------------------------
    def toggle_camera(self, encender: bool):
        """Reacciona al switch de la UI para encender/apagar el sistema."""
        if encender:
            self._start_system()
        else:
            self._stop_system()
            # Para parada normal desde UI: join en background para no bloquear
            threading.Thread(target=self._join_threads, daemon=True, name="sai-shutdown").start()

    def logout(self):
        """Cierre de sesión completo: para el sistema, limpia sesión y navega."""
        self._stop_system()

        # Para logout: join sincrónico para que los hilos terminen antes de limpiar la sesión
        self._join_threads()

        try:
            self.mqtt_service.mqtt_manager.disconnect()
            logger.info("MQTT desconectado al cerrar sesión")
        except Exception as e:
            logger.warning("Error al desconectar MQTT: %s", e)

        user = self.page.session.get("user")
        if user:
            self.auth_service.cerrar_sesion(user)

        try:
            self.page.session.remove("user")
        except KeyError:
            logger.warning("La clave 'user' ya había sido eliminada de la sesión")

        self.page.go(AppRoutes.LOGIN)

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

        self.camera_thread = threading.Thread(
            target=self._camera_capture_loop, daemon=False, name="sai-camera")
        self.processing_thread = threading.Thread(
            target=self._processing_loop_v3, daemon=False, name="sai-processing")
        self._mqtt_thread = threading.Thread(
            target=self._mqtt_sender_loop, daemon=False, name="sai-mqtt")

        self.camera_thread.start()
        self.processing_thread.start()
        self._mqtt_thread.start()

    def _stop_system(self):
        self.is_scanning = False
        self._cooldown_event.set()
        self.view.detener_animacion_escaneo()

    def _join_threads(self):
        # 1. Primero esperamos a los hilos que leen de la cámara (sai-camera,
        #    sai-processing). En macOS (backend AVFoundation) liberar la cámara
        #    mientras otro hilo sigue en cap.read() puede provocar un crash nativo
        #    del proceso ("Python se ha cerrado inesperadamente"); Windows/DirectShow
        #    tolera esa condición de carrera, macOS no.
        camera_pairs = [
            (self.camera_thread, 2.0),
            (self.processing_thread, 2.0),
        ]
        for thread, timeout in camera_pairs:
            if thread and thread.is_alive():
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.warning("El hilo '%s' no terminó en %.1fs", thread.name, timeout)

        # 1.5 _stop_system() ya puso el preview en placeholder, pero si sai-camera
        #     estaba a mitad de mostrar_frame_video() en ese instante, su último
        #     frame real "gana" y se queda pegado en la UI. Con el hilo ya
        #     confirmadamente parado (join arriba), repetimos el reset para que
        #     no quede ningún frame en vuelo pisando el placeholder.
        try:
            self.view.detener_animacion_escaneo()
        except Exception:
            pass

        # 2. Solo ahora, con la certeza de que ningún hilo sigue leyendo frames,
        #    liberamos el hardware de la cámara.
        if self.camera_service:
            self.camera_service.detener_camara()

        # 3. El hilo MQTT no toca la cámara, puede esperar/joinearse en cualquier orden.
        if self._mqtt_thread and self._mqtt_thread.is_alive():
            self._mqtt_thread.join(timeout=10.0)
            if self._mqtt_thread.is_alive():
                logger.warning("El hilo '%s' no terminó en %.1fs", self._mqtt_thread.name, 10.0)

    def _camera_capture_loop(self):
        """Hilo de preview: alimenta el video de la UI. El procesamiento usa capturar_foto_hd()."""
        while self.is_scanning:
            frame = self.camera_service.obtener_frame()
            if frame is not None:
                frame_b64 = self.camera_service.convertir_numpy_a_base64(
                    frame, quality=50, width_resize=AppConfig.VIDEO_PREVIEW_WIDTH
                )
                self.view.mostrar_frame_video(frame_b64)
            else:
                time.sleep(0.01)

    def _processing_loop_v3(self):
        """
        YOLO gate (320px) + procesar_zonas sobre el mismo frame.
        El mismo frame se usa para detección y decodificación — sin desfase temporal.
        CAP_PROP_BUFFERSIZE=1 (Phase 1) garantiza que obtener_frame() ya es fresco.
        Las imágenes solo se persisten a disco en _handle_scan_timeout (diagnóstico).
        """

        ultimo_frame_procesado = -1
        frames_enviados_procesamiento = 0
        frames_omitidos = 0
        inicio_medicion_procesamiento = time.monotonic()


        while self.is_scanning:
            # 1. WATCHDOG
            if self.pallet_service.evaluar_watchdog(AppConfig.READ_TIMEOUT_SEC):
                palet_actual = self.pallet_service.get_palet_actual()
                if palet_actual.sscc:
                    logger.info("Fin parada. Enviando palet SSCC: %s", palet_actual.sscc)
                    self._finalizar_palet()
                else:
                    logger.warning("Fin parada sin SSCC. Etiqueta dañada.")
                    self._handle_scan_timeout()
                continue

            if self.lectura_bloqueada:
                time.sleep(0.05)
                continue

            # 2. OBTENER EL ÚLTIMO FOTOGRAMA DISPONIBLE
            # CameraService ya dispone de un único hilo que realiza cap.read().
            packet = self.camera_service.obtener_ultimo_frame()

            if packet is None:
                time.sleep(0.01)
                continue

            if packet.frame_id == ultimo_frame_procesado:
                time.sleep(0.005)
                continue

            # Si el identificador ha avanzado más de una posición, significa que la
            # cámara produjo fotogramas nuevos mientras el procesamiento estaba ocupado.
            if (
                    ultimo_frame_procesado >= 0
                    and packet.frame_id > ultimo_frame_procesado + 1
            ):
                frames_omitidos += (
                        packet.frame_id - ultimo_frame_procesado - 1
                )

            ultimo_frame_procesado = packet.frame_id
            frame = packet.frame

            frames_enviados_procesamiento += 1

            ahora = time.monotonic()
            tiempo_transcurrido = ahora - inicio_medicion_procesamiento

            if tiempo_transcurrido >= 5.0:
                fps_procesamiento = (
                        frames_enviados_procesamiento / tiempo_transcurrido
                )

                logger.info(
                    "Rendimiento del procesamiento: %.2f FPS; "
                    "fotogramas enviados=%d, omitidos=%d "
                    "en %.2f segundos.",
                    fps_procesamiento,
                    frames_enviados_procesamiento,
                    frames_omitidos,
                    tiempo_transcurrido,
                )

                frames_enviados_procesamiento = 0
                frames_omitidos = 0
                inicio_medicion_procesamiento = ahora

            # 3. YOLO GATE @ 320px — detectar presencia de etiqueta
            # (se ejecuta ANTES del gate de nitidez para no perder la señal de
            # "hay una etiqueta presente" que arranca el watchdog — ver 4)
            rois = self.yolo_service.detectar(frame)
            if not rois:
                time.sleep(0.05)   # sin etiqueta, ceder CPU sin I/O de disco
                continue

            # 4. ETIQUETA DETECTADA — iniciar timer (watchdog cuenta desde aquí,
            # independientemente de si el frame está borroso o no)
            self.pallet_service.iniciar_temporizador()

            # 5. DECODE con el mismo frame (ROIs y píxeles perfectamente alineados)
            try:
                scan_result = self.scanner_service.procesar_zonas(frame, rois)
                hubo_cambios = self.pallet_service.procesar_nuevos_datos(scan_result)

                if hubo_cambios:
                    palet_actual = self.pallet_service.get_palet_actual()
                    self.view.actualizar_datos_palet(palet_actual)

                    if palet_actual.is_fully_captured():
                        self._finalizar_palet()

            except Exception as e:
                logger.error("Error en _processing_loop_v3: %s", e)

    # -------------------------------------------------------------------------
    # RESOLUCIÓN DE LA LECTURA
    # -------------------------------------------------------------------------
    def _finalizar_palet(self):
        """Decisión de negocio: Encolar envío MQTT y preparar siguiente palet."""
        self.lectura_bloqueada = True
        palet = self.pallet_service.get_palet_actual()

        self.view.mostrar_estado_exito()

        # Encolar publicación MQTT con espera de hasta 5s para que el sender drene
        user = self.page.session.get("user")
        empleado = getattr(user, 'employee_number', '0000') if user else '0000'
        try:
            self._mqtt_queue.put({
                "palet_data": palet,
                "employee_number": empleado,
                "station_code": self.page.session.get("station_code"),
                "station_cam_id": self.page.session.get("camera_id"),
            }, block=True, timeout=5.0)
            logger.info("Palet SSCC=%s encolado para envío MQTT", palet.sscc)
        except queue.Full:
            logger.critical(
                "Cola MQTT llena tras 5s de espera; palet SSCC=%s NO enviado. "
                "Revisar conectividad con el broker.", palet.sscc
            )

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

        # Capturar imagen diagnóstica del estado real de la etiqueta al expirar el watchdog
        station_code = self.page.session.get("station_code") or "UNKNOWN"
        gray_diag = self.camera_service.capturar_foto_hd()
        if gray_diag is not None:
            pending_path = self.image_storage_service.guardar_pendiente(gray_diag, station_code)
            self.image_storage_service.marcar_fallido(pending_path)

        palet = self.pallet_service.get_palet_actual()
        user = self.page.session.get("user")
        employee_number = getattr(user, 'employee_number', 'UNKNOWN') if user else 'UNKNOWN'
        threading.Thread(
            target=self.audit_service.registrar_incidencia,
            args=(employee_number, palet, "TIMEOUT_ETIQUETA_DAÑADA"),
            daemon=True,
        ).start()

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