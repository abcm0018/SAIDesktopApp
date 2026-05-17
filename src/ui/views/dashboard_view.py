import logging
import threading
import time
import flet as ft

from src.services.audit_service import AuditService
from src.config.app_config import AppConfig
from src.services.auth_service import AuthService
from src.services.camera_service import CameraService
from src.services.yolo_service import YoloService
from src.services.scanner_service import ScannerService
from src.services.mqtt_service import MqttService
from src.domain.palet import PaletScanData
from src.config.routes import AppRoutes
from src.ui import design_system as ds
from src.controllers.dashboard_controller import DashboardController

logger = logging.getLogger(__name__)

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
        self.mqtt_service = mqtt_service

        # --- Estado UI ---
        self.station_code = self.page.session.get("station_code")
        self.camera_id = self.page.session.get("camera_id")
        self.user = self.page.session.get("user")
        self.animando_linea = False
        self._anim_thread: threading.Thread | None = None

        self.expand = True
        self.spacing = 0

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

        # --- Controlador (se crea después de la UI para poder pasarse como view=self) ---
        self.controller = DashboardController(
            page=page,
            view=self,
            auth_service=auth_service,
            camera_service=camera_service,
            yolo_service=yolo_service,
            scanner_service=scanner_service,
            mqtt_service=mqtt_service,
            audit_service=audit_service,
        )

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

        self.switch_activar = ft.Switch(
            label="Activar puesto",
            label_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            value=False,
            active_color=ds.ACCENT_GREEN,
            on_change=self._toggle_camara
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
                    content=self.switch_activar
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
    # SECCIÓN 2: EVENTOS UI
    # --------------------------------------------------------------------------

    def _toggle_camara(self, e):
        self.controller.toggle_camera(e.control.value)

    def _logout(self, e):
        self.controller.logout()

    # --------------------------------------------------------------------------
    # SECCIÓN 3: INTERFAZ DEL CONTROLADOR
    # Estos métodos son llamados por DashboardController desde sus hilos.
    # Todos los updates de UI usan try/except para tolerar desconexiones de página.
    # --------------------------------------------------------------------------

    def mostrar_error(self, mensaje: str):
        """Muestra un error en el panel de estado."""
        self.txt_estado.value = f"Error: {mensaje}"
        self.txt_estado.color = ds.ACCENT_RED
        try:
            self.txt_estado.update()
        except Exception:
            pass

    def apagar_switch(self):
        """Desactiva el switch de activación del puesto."""
        self.switch_activar.value = False
        try:
            self.switch_activar.update()
        except Exception:
            pass

    def iniciar_animacion_escaneo(self):
        """Transiciona la UI al estado 'escaneando' e inicia la animación de línea."""
        self._conectar_mqtt()

        self.txt_cam_status.value = self.camera_id
        self.txt_cam_status.color = ds.ACCENT_GREEN
        self.status_icon.name = ft.Icons.VIDEOCAM
        self.status_icon.color = ds.ACCENT_GREEN
        self.img_video.src_base64 = PLACEHOLDER_IMG
        self.txt_estado.value = "Buscando códigos GS1..."
        self.txt_estado.color = ds.ACCENT_BLUE
        try:
            self.page.update()
        except Exception:
            pass

        self.animando_linea = True
        self._anim_thread = threading.Thread(
            target=self._thread_animacion, daemon=True, name="sai-anim")
        self._anim_thread.start()

    def detener_animacion_escaneo(self):
        """Transiciona la UI al estado 'pausa' y detiene la animación de línea."""
        self.animando_linea = False

        self.txt_cam_status.value = "PAUSA"
        self.txt_cam_status.color = ds.TEXT_MUTED
        self.status_icon.name = ft.Icons.VIDEOCAM_OFF
        self.status_icon.color = ds.TEXT_MUTED
        self.img_video.src_base64 = PLACEHOLDER_IMG
        self.txt_estado.value = "Cámara en espera"
        try:
            self.page.update()
        except Exception:
            pass

    def mostrar_frame_video(self, frame_b64: str):
        """Actualiza el preview de cámara con el frame codificado en Base64."""
        if frame_b64:
            self.img_video.src_base64 = frame_b64
            try:
                self.img_video.update()
            except Exception:
                pass

    def actualizar_datos_palet(self, palet: PaletScanData):
        """Actualiza el panel derecho con los datos del palé acumulado."""
        if palet.sscc:
            self.txt_sscc.value = palet.sscc
            self.txt_sscc.color = ds.ACCENT_BLUE

        ean_val = getattr(palet, 'ean', None)
        if ean_val:
            self.txt_producto.value = f"EAN: {ean_val}"
            self.txt_producto.weight = ft.FontWeight.BOLD

        if palet.batch_number:
            self.txt_lote.value = f"Lote: {palet.batch_number}"
            self.txt_lote.color = ds.TEXT_PRIMARY

        if palet.product_use_by_date:
            self.txt_fechas.value = f"Caducidad: {palet.product_use_by_date}"

        prod_str = []
        if palet.packaging_date:
            prod_str.append(palet.packaging_date)
        if palet.production_time:
            prod_str.append(palet.production_time)
        if prod_str:
            self.txt_produccion.value = f"Prod: {' '.join(prod_str)}"

        self.info_container.opacity = 1.0
        try:
            self.info_container.update()
        except Exception:
            pass

    def mostrar_estado_exito(self):
        """Muestra el estado visual de palé completado (verde)."""
        self.txt_estado.value = "PALET COMPLETADO"
        self.txt_estado.color = ds.ACCENT_GREEN
        self.animando_linea = False
        self.scan_line.offset = ft.Offset(1.2, 0)
        self.scan_line.bgcolor = ds.ACCENT_GREEN
        try:
            self.txt_estado.update()
            self.scan_line.update()
        except Exception:
            pass

    def mostrar_estado_error_timeout(self):
        """Muestra el estado visual de etiqueta dañada / timeout (rojo)."""
        self.txt_estado.value = "ETIQUETA DAÑADA"
        self.txt_estado.color = ds.ACCENT_RED
        self.scan_line.bgcolor = ds.ACCENT_RED
        try:
            self.txt_estado.update()
            self.scan_line.update()
        except Exception:
            pass

    def limpiar_datos_palet(self):
        """Resetea todos los campos del panel de datos para la siguiente lectura."""
        self.txt_sscc.value = "---"
        self.txt_sscc.color = ds.ACCENT_BLUE
        self.txt_producto.value = "EAN: -"
        self.txt_producto.weight = ft.FontWeight.NORMAL
        self.txt_lote.value = "Lote: -"
        self.txt_lote.color = ds.TEXT_SECONDARY
        self.txt_fechas.value = "Caducidad: -"
        self.txt_produccion.value = "Prod: -"
        self.info_container.opacity = 0.3
        self.txt_estado.value = "Buscando códigos GS1..."
        self.txt_estado.color = ds.ACCENT_BLUE
        self.scan_line.bgcolor = ds.ACCENT_BLUE
        self.scan_line.offset = ft.Offset(-1.2, 0)
        try:
            self.info_container.update()
            self.txt_estado.update()
            self.scan_line.update()
        except Exception:
            pass

        if not self.animando_linea:
            self.animando_linea = True
            self._anim_thread = threading.Thread(
                target=self._thread_animacion, daemon=True, name="sai-anim")
            self._anim_thread.start()

    # --------------------------------------------------------------------------
    # SECCIÓN 4: MQTT STATUS
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

    # --------------------------------------------------------------------------
    # SECCIÓN 5: ANIMACIÓN DE LÍNEA DE ESCANEO (UI pura)
    # --------------------------------------------------------------------------

    def _thread_animacion(self):
        direccion_abajo = True
        while self.animando_linea:
            nuevo_offset = ft.Offset(1.2, 0) if direccion_abajo else ft.Offset(-1.2, 0)
            self.scan_line.offset = nuevo_offset
            try:
                self.scan_line.update()
            except Exception as e:
                logger.debug(f"Animación detenida (página no accesible): {e}")
                break
            direccion_abajo = not direccion_abajo
            time.sleep(1.6)
