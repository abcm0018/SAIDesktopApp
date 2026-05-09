import logging
import queue
import threading
import time
import flet as ft

from services.audit_service import AuditService
from src.config.app_config import AppConfig
from src.services.auth_service import AuthService
from src.services.camera_service import CameraService
from src.services.yolo_service import YoloService
from src.services.scanner_service import ScannerService
from src.services.mqtt_service import MqttService
from src.domain.palet import PaletScanData
from src.config.routes import AppRoutes
from src.ui import design_system as ds

logger = logging.getLogger(__name__)

# Imagen vacía (pixel transparente) para cuando la cámara está apagada
PLACEHOLDER_IMG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


class DashboardView(ft.Column):
    def __init__(
            self,
            page: ft.Page,
            auth_service: AuthService,
            camera_service: CameraService,
            yolo_service: YoloService,
            scanner_service: ScannerService,
            mqtt_service: MqttService,
            audit_service: AuditService
    ):
        super().__init__()
        self.page = page
        self.auth_service = auth_service
        self.camera_service = camera_service
        self.yolo_service = yolo_service
        self.scanner_service = scanner_service
        self.mqtt_service = mqtt_service
        self.audit_service = audit_service

        # --- Estado interno ---
        self.station_code = self.page.session.get("station_code")
        self.camera_id = self.page.session.get("camera_id")
        self.user = self.page.session.get("user")

        self.en_periodo_gracia = False
        self.tiempo_inicio_gracia = 0
        self.segundos_gracia = 5

        self.expand = True
        self.spacing = 0
        self.is_scanning = True
        self.animando_linea = False
        self.lectura_bloqueada = False

        self.palet_acumulado = PaletScanData()
        self.frame_queue = queue.Queue(maxsize=1)

        # --- Construcción de UI ---
        self.header = self._build_header()
        self.left_panel = self._build_camera_panel()
        self.right_panel = self._build_info_panel()

        self.controls = [
            self.header,
            ft.Row(
                controls=[self.left_panel, self.right_panel],
                expand=True,
                spacing=0
            )
        ]

    # --------------------------------------------------------------------------
    # SECCIÓN 1: BUILDERS
    # --------------------------------------------------------------------------

    def _build_header(self) -> ft.Container:
        nombre_mostrar = "Operador"
        if self.user:
            nombre = getattr(self.user, 'name', '') or ''
            apellido = getattr(self.user, 'surname', '') or ''
            nombre_mostrar = f"{nombre} {apellido}".strip() or self.user.employee_number

        self.txt_subtitle = ft.Text(
            f"Puesto: {self.station_code} | Cámara: {self.camera_id}",
            size=14,
            color=ds.TEXT_SECONDARY,
        )

        self.mqtt_status_icon = ft.Icon(
            ft.Icons.CLOUD_OFF,
            color=ds.TEXT_MUTED,
            size=20,
            tooltip="MQTT desconectado"
        )

        return ft.Column(
            controls=[
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=20, vertical=14),
                    bgcolor=ds.SURFACE_ELEVATED,
                    content=ft.Row(
                        controls=[
                            ft.Column([
                                ft.Text(
                                    f"Operador: {nombre_mostrar}",
                                    size=14,
                                    weight=ft.FontWeight.BOLD,
                                    color=ds.TEXT_PRIMARY,
                                ),
                                self.txt_subtitle,
                            ], spacing=2),
                            ft.Row([
                                self.mqtt_status_icon,
                                ft.IconButton(
                                    icon=ft.Icons.LOGOUT_ROUNDED,
                                    tooltip="Cerrar Sesión",
                                    icon_color=ds.ACCENT_RED,
                                    on_click=self._logout
                                )
                            ], spacing=5)
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    )
                ),
                ft.Container(height=1, bgcolor=ds.BORDER_ACCENT),
            ],
            spacing=0,
        )

    def _build_camera_panel(self) -> ft.Container:
        self.img_video = ft.Image(
            src_base64=PLACEHOLDER_IMG,
            fit=ft.ImageFit.COVER,
            border_radius=12,
            gapless_playback=True,
            expand=True
        )

        self.scan_line = ft.Container(
            width=3,
            height=450,
            bgcolor=ds.ACCENT_BLUE,
            shadow=ft.BoxShadow(blur_radius=10, color=ds.ACCENT_BLUE),
            offset=ft.Offset(-1.2, 0),
            animate_offset=ft.Animation(duration=1500, curve=ft.AnimationCurve.EASE_IN_OUT),
        )

        stack = ft.Stack(
            expand=True,
            alignment=ft.alignment.center,
            controls=[
                ft.Container(
                    content=self.img_video,
                    expand=True,
                    alignment=ft.alignment.center
                ),
                ft.Container(
                    width=450,
                    height=450,
                    border=ft.border.all(2, ft.Colors.WHITE60),
                    border_radius=12,
                    alignment=ft.alignment.center
                ),
                ft.Container(
                    alignment=ft.alignment.center,
                    content=self.scan_line,
                    expand=True
                ),
                ft.Container(content=self._build_camera_status(), alignment=ft.alignment.top_right, padding=20),
                ft.Container(
                    alignment=ft.alignment.bottom_center,
                    padding=20,
                    content=ft.Switch(
                        label="Activar puesto",
                        label_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                        value=False,
                        active_color=ds.ACCENT_GREEN,
                        on_change=self._toggle_camara
                    )
                )
            ]
        )

        return ft.Container(
            expand=1,
            margin=5,
            border_radius=15,
            bgcolor=ds.SURFACE_BASE,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=stack
        )

    def _build_info_panel(self) -> ft.Container:
        self.txt_estado = ft.Text(
            "Cámara apagada",
            color=ds.TEXT_MUTED,
            weight=ft.FontWeight.BOLD,
        )

        self.txt_sscc = ft.Text(
            "---",
            size=ds.SIZE_DATA_XL,
            weight=ft.FontWeight.BOLD,
            color=ds.ACCENT_BLUE,
            text_align=ft.TextAlign.CENTER,
        )

        self.txt_producto = ft.Text("EAN: -", size=ds.SIZE_DATA_LG, color=ds.TEXT_PRIMARY)
        self.txt_lote = ft.Text("Lote: -", size=ds.SIZE_LABEL, color=ds.TEXT_SECONDARY)
        self.txt_fechas = ft.Text("Caducidad: -", size=ds.SIZE_LABEL, color=ds.TEXT_SECONDARY)
        self.txt_produccion = ft.Text("Prod: -", size=ds.SIZE_LABEL, color=ds.TEXT_SECONDARY)

        self.txt_envio_msg = ft.Text("Enviando datos...", color=ds.TEXT_SECONDARY)

        self.info_container = ft.Column(
            opacity=0.3,
            animate_opacity=300,
            controls=[
                ft.Text("SSCC (Matrícula):", size=10, color=ds.TEXT_MUTED),
                self.txt_sscc,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                self.txt_producto,
                self.txt_lote,
                self.txt_fechas,
                self.txt_produccion
            ]
        )

        self.envio_status = ft.Container(
            visible=False,
            animate_opacity=300,
            padding=15,
            border_radius=ds.RADIUS_MD,
            bgcolor=ds.SURFACE_ELEVATED,
            content=ft.Row(
                controls=[
                    ft.ProgressRing(width=20, height=20, stroke_width=2, color=ds.ACCENT_BLUE),
                    self.txt_envio_msg
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER
            )
        )

        content = ft.Column(
            controls=[
                ft.Row([
                    ft.Icon(ft.Icons.QR_CODE_SCANNER, size=30, color=ds.ACCENT_BLUE),
                    ft.Text("Recepción", size=20, weight=ft.FontWeight.BOLD, color=ds.TEXT_PRIMARY)
                ], spacing=10),
                ft.Divider(color=ds.SURFACE_ELEVATED),
                ft.Container(
                    padding=10,
                    bgcolor=ds.SURFACE_ELEVATED,
                    border_radius=ds.RADIUS_SM,
                    content=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, color=ds.ACCENT_BLUE),
                        self.txt_estado
                    ])
                ),
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                self.info_container,
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                self.envio_status
            ],
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )

        return ft.Container(
            expand=1,
            margin=10,
            padding=30,
            bgcolor=ds.SURFACE_CARD,
            border_radius=15,
            shadow=ds.card_shadow(0.30),
            content=content
        )

    def _build_camera_status(self):
        self.txt_cam_status = ft.Text("En Pausa", weight=ft.FontWeight.BOLD, color=ds.ACCENT_BLUE)
        self.status_icon = ft.Icon(ft.Icons.PAUSE_CIRCLE_OUTLINE, color=ds.ACCENT_BLUE)

        return ft.Container(
            content=ft.Row(
                controls=[self.status_icon, self.txt_cam_status],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=5,
                tight=True
            ),
            bgcolor=ds.SURFACE_OVERLAY,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=ds.RADIUS_SM,
        )

    # --------------------------------------------------------------------------
    # SECCIÓN 2: CONTROL DE FLUJO Y EVENTOS
    # --------------------------------------------------------------------------

    def _toggle_camara(self, e):
        activar = e.control.value
        if activar:
            self._iniciar_flujo_camara()
        else:
            self._detener_flujo_camara()

    def _logout(self, e):
        logger.debug(f"Evento de cierre de sessión: {e}")
        self._detener_flujo_camara()

        try:
            self.mqtt_service.mqtt_manager.disconnect()
            logger.info("MQTT desconectado al cerrar sesión")
        except Exception as ex:
            logger.warning(f"Error al desconectar MQTT: {ex}")

        if self.user:
            self.auth_service.cerrar_sesion(self.user)
        self.page.session.remove('user')
        self.page.go(AppRoutes.LOGIN)

    def _iniciar_flujo_camara(self):
        self._conectar_mqtt()

        self.camera_service.iniciar_camara()
        self.escaneando = True
        self.animando_linea = True
        self.lectura_bloqueada = False
        self.txt_cam_status.value = self.camera_id
        self.txt_cam_status.color = ds.ACCENT_GREEN
        self.status_icon.name = ft.Icons.VIDEOCAM
        self.status_icon.color = ds.ACCENT_GREEN

        self.page.update()

        with self.frame_queue.mutex:
            self.frame_queue.queue.clear()

        self.txt_estado.value = "Buscando códigos GS1..."
        self.txt_estado.color = ds.ACCENT_BLUE
        self.txt_estado.update()

        threading.Thread(target=self._thread_camera_loop, daemon=True).start()
        threading.Thread(target=self._thread_processing_loop, daemon=True).start()
        threading.Thread(target=self._thread_animacion, daemon=True).start()

    def _detener_flujo_camara(self):
        self.escaneando = False
        self.animando_linea = False
        self.camera_service.detener_camara()

        self.txt_cam_status.value = "PAUSA"
        self.txt_cam_status.color = ds.TEXT_MUTED
        self.status_icon.name = ft.Icons.VIDEOCAM_OFF
        self.status_icon.color = ds.TEXT_MUTED

        self.img_video.src_base64 = PLACEHOLDER_IMG
        self.txt_estado.value = "Cámara en espera"
        self.page.update()

    def _limpiar_datos(self):
        self.lectura_bloqueada = False

        with self.frame_queue.mutex:
            self.frame_queue.queue.clear()

        self.palet_acumulado = PaletScanData()

        self.txt_sscc.value = "---"
        self.txt_sscc.color = ds.ACCENT_BLUE
        self.txt_producto.value = "EAN: -"
        self.txt_producto.weight = ft.FontWeight.NORMAL
        self.txt_lote.value = "Lote: -"
        self.txt_lote.color = ds.TEXT_SECONDARY
        self.txt_fechas.value = "Caducidad: -"
        self.txt_produccion.value = "Prod: -"

        self.info_container.opacity = 0.3
        self.info_container.update()

        self.txt_estado.value = "Buscando códigos GS1..."
        self.txt_estado.color = ds.ACCENT_BLUE
        self.txt_estado.update()

        self.scan_line.bgcolor = ds.ACCENT_BLUE
        self.scan_line.update()

        self.envio_status.visible = False
        self.envio_status.update()

        if self.escaneando and not self.animando_linea:
            self.animando_linea = True
            threading.Thread(target=self._thread_animacion, daemon=True).start()

    # --------------------------------------------------------------------------
    # SECCIÓN: GESTIÓN MQTT
    # --------------------------------------------------------------------------

    def _conectar_mqtt(self):
        def _conectar_async():
            try:
                if self.mqtt_service.mqtt_manager.connect(timeout=5.0):
                    logger.info("Conexión MQTT establecida")
                    self._actualizar_mqtt_status(conectado=True)
                else:
                    logger.warning("No se pudo conectar a MQTT")
                    self._actualizar_mqtt_status(conectado=False)
            except Exception as e:
                logger.error(f"Error al conectar MQTT: {e}")
                self._actualizar_mqtt_status(conectado=False)

        threading.Thread(target=_conectar_async, daemon=True).start()

    def _actualizar_mqtt_status(self, conectado: bool):
        if conectado:
            self.mqtt_status_icon.name = ft.Icons.CLOUD_DONE
            self.mqtt_status_icon.color = ds.ACCENT_GREEN
            self.mqtt_status_icon.tooltip = "MQTT conectado"
        else:
            self.mqtt_status_icon.name = ft.Icons.CLOUD_OFF
            self.mqtt_status_icon.color = ds.ACCENT_RED
            self.mqtt_status_icon.tooltip = "MQTT desconectado"

        try:
            self.mqtt_status_icon.update()
        except Exception as e:
            logger.warning(f"Error actualizando icono MQTT: {e}")

    def _enviar_palet_mqtt(self):
        def _enviar_async():
            try:
                self.envio_status.visible = True
                self.txt_envio_msg.value = "Enviando datos..."
                self.envio_status.update()

                employee_number = getattr(self.user, 'employee_number', 'UNKNOWN')

                enviado = self.mqtt_service.enviar_datos_palet(
                    palet_data=self.palet_acumulado,
                    employee_number=employee_number,
                    station_code=self.station_code,
                    station_cam_id=self.camera_id,
                )

                if enviado:
                    logger.info(f"Palet acumulado {self.palet_acumulado.sscc} enviado exitosamente")
                    self._mostrar_resultado_envio(exito=True)
                else:
                    logger.error(f"Error al enviar palet {self.palet_acumulado.sscc}")
                    self._mostrar_resultado_envio(exito=False)

            except Exception as e:
                logger.exception(f"Error crítico enviando palet: {e}")
                self._mostrar_resultado_envio(exito=False)

        threading.Thread(target=_enviar_async, daemon=True).start()

    def _mostrar_resultado_envio(self, exito: bool):
        if exito:
            self.envio_status.bgcolor = ft.Colors.with_opacity(0.12, ft.Colors.GREEN)
            self.envio_status.content = ft.Column(
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=ds.ACCENT_GREEN, size=40),
                    ft.Text(
                        "Datos enviados correctamente",
                        color=ds.ACCENT_GREEN,
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER
                    ),
                    ft.Text(
                        "Escanee el siguiente palet",
                        color=ds.TEXT_SECONDARY,
                        size=12,
                        text_align=ft.TextAlign.CENTER
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5
            )
        else:
            self.envio_status.bgcolor = ft.Colors.with_opacity(0.12, ft.Colors.RED)
            self.envio_status.content = ft.Column(
                controls=[
                    ft.Icon(ft.Icons.ERROR, color=ds.ACCENT_RED, size=40),
                    ft.Text(
                        "Error al enviar datos",
                        color=ds.ACCENT_RED,
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER
                    ),
                    ft.Text(
                        "Verifique la conexión MQTT",
                        color=ds.TEXT_SECONDARY,
                        size=12,
                        text_align=ft.TextAlign.CENTER
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5
            )

        self.envio_status.update()

        if exito:
            def _auto_limpiar():
                time.sleep(3)
                if self.escaneando:
                    self._limpiar_datos()

            threading.Thread(target=_auto_limpiar, daemon=True).start()

    def _handle_scan_timeout(self):
        logger.warning(f"Scan Timeout ({AppConfig.READ_TIMEOUT_SEC}s). Reporting damaged label.")

        self.palet_acumulado.station_id = self.station_code
        self.palet_acumulado.camera_id = self.camera_id

        if self.palet_acumulado.sscc is None:
            employee_number = getattr(self.user, 'employee_number', 'UNKNOWN')

            threading.Thread(
                target=self.audit_service.registrar_incidencia,
                args=(employee_number, self.palet_acumulado, "TIMEOUT_ETIQUETA_DAÑADA"),
                daemon=True
            ).start()

            self.txt_estado.value = "❌ ETIQUETA DAÑADA"
            self.txt_estado.color = ds.ACCENT_RED
            self.scan_line.bgcolor = ds.ACCENT_RED
            self.update()

            time.sleep(2.0)

        else:
            logger.info(
                f"Scan Timeout alcanzado. Palet con SSCC ({self.palet_acumulado.sscc}) omitido de auditoría de daños.")

        self._limpiar_datos()

        self.txt_estado.value = "ESPERANDO NUEVA ETIQUETA"
        self.txt_estado.color = ds.TEXT_PRIMARY
        self.scan_line.bgcolor = ds.ACCENT_BLUE
        self.update()

    # --------------------------------------------------------------------------
    # SECCIÓN 3: LÓGICA DE HILOS
    # --------------------------------------------------------------------------

    def _thread_camera_loop(self):
        time.sleep(0.5)

        while self.escaneando:
            frame_hd = self.camera_service.obtener_frame()

            if frame_hd is None:
                time.sleep(0.02)
                continue

            frame_b64 = self.camera_service.convertir_numpy_a_base64(
                frame_hd, quality=50, width_resize=800
            )

            if frame_b64:
                self.img_video.src_base64 = frame_b64
                self.page.update()

            if not self.lectura_bloqueada:
                try:
                    self.frame_queue.put_nowait(frame_hd)
                except queue.Full:
                    pass

            time.sleep(0.025)

    def _thread_processing_loop(self):
        while self.is_scanning:

            if (self.palet_acumulado.scan_start_time is not None
                    and self.palet_acumulado.has_timed_out(AppConfig.READ_TIMEOUT_SEC)):

                if self.palet_acumulado.sscc:
                    logger.info(f"Fin de los 5s de parada. Enviando palet SSCC: {self.palet_acumulado.sscc}")
                    self._finalizar_palet()
                else:
                    logger.warning("Fin de los 5s de parada sin detectar SSCC. Marcando como ETIQUETA DAÑADA.")
                    self._handle_scan_timeout()

                with self.frame_queue.mutex:
                    self.frame_queue.queue.clear()

                continue

            try:
                frame = self.frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self.lectura_bloqueada:
                self.frame_queue.task_done()
                continue

            try:
                rois_detectados = self.yolo_service.detectar(frame)

                if rois_detectados is None or len(rois_detectados) > 0:
                    self.palet_acumulado.init_timeout()

                scan_result_dto = self.scanner_service.procesar_zonas(frame, rois_detectados)

                if self._fusionar_datos(scan_result_dto):
                    self._actualizar_ui_progreso()

                    if hasattr(self.palet_acumulado, 'is_fully_captured') and self.palet_acumulado.is_fully_captured():
                        logger.info("Lectura al 100% completada antes de 5s. Finalizando anticipadamente.")
                        self._finalizar_palet()
                        with self.frame_queue.mutex:
                            self.frame_queue.queue.clear()

            except Exception as e:
                logger.error(f"Error en hilo de procesamiento IA: {e}")
            finally:
                self.frame_queue.task_done()

    def _fusionar_datos(self, nuevo_dato: PaletScanData) -> bool:
        hubo_cambios = False
        attrs = ['sscc', 'ean', 'batch_number', 'product_use_by_date', 'packaging_date', 'production_time']

        for attr in attrs:
            nuevo_valor = getattr(nuevo_dato, attr, None)
            valor_actual = getattr(self.palet_acumulado, attr, None)

            if nuevo_valor:
                if not valor_actual or valor_actual != nuevo_valor:
                    setattr(self.palet_acumulado, attr, nuevo_valor)
                    hubo_cambios = True

        return hubo_cambios

    def _actualizar_ui_progreso(self):
        p = self.palet_acumulado

        if p.sscc:
            self.txt_sscc.value = p.sscc
            self.txt_sscc.color = ds.ACCENT_BLUE

        ean_val = getattr(p, 'ean', None) or getattr(p, 'gtin', None)
        if ean_val:
            self.txt_producto.value = f"EAN: {ean_val}"
            self.txt_producto.weight = ft.FontWeight.BOLD

        if p.batch_number:
            self.txt_lote.value = f"Lote: {p.batch_number}"
            self.txt_lote.color = ds.TEXT_PRIMARY

        if p.product_use_by_date:
            self.txt_fechas.value = f"Caducidad: {p.product_use_by_date}"

        prod_str = []
        if p.packaging_date: prod_str.append(p.packaging_date)
        if p.production_time: prod_str.append(p.production_time)
        if prod_str:
            self.txt_produccion.value = f"Prod: {' '.join(prod_str)}"

        self.info_container.opacity = 1.0
        self.info_container.update()

    def _finalizar_palet(self):
        self.lectura_bloqueada = True

        self.txt_estado.value = "✅ PALET COMPLETADO"
        self.txt_estado.color = ds.ACCENT_GREEN

        self.animando_linea = False
        self.scan_line.offset = ft.Offset(1.2, 0)
        self.scan_line.bgcolor = ds.ACCENT_GREEN

        self.update()

        logger.info(f"Palet SSCC: {self.palet_acumulado.sscc} completado")

        self._enviar_palet_mqtt()

    def _thread_animacion(self):
        direccion_abajo = True
        while self.animando_linea and self.escaneando:
            nuevo_offset = ft.Offset(1.2, 0) if direccion_abajo else ft.Offset(-1.2, 0)
            self.scan_line.offset = nuevo_offset
            try:
                self.scan_line.update()
            except Exception as e:
                logger.debug(f"Animación detenida (UI no accesible): {e}")
                break

            direccion_abajo = not direccion_abajo
            time.sleep(1.6)
