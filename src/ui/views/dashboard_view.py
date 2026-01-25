import logging
import queue
import threading
import time
import flet as ft

from src.config.app_config import AppConfig
from src.services.auth_service import AuthService
from src.services.camera_service import CameraService
from src.services.yolo_service import YoloService
from src.services.scanner_service import ScannerService
from src.services.mqtt_service import MqttService
from src.domain.palet import PaletScanData 
from src.config.routes import AppRoutes

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
        mqtt_service: MqttService
    ):
        super().__init__()
        self.page = page
        self.auth_service = auth_service
        self.camera_service = camera_service
        self.yolo_service = yolo_service
        self.scanner_service = scanner_service
        self.mqtt_service = mqtt_service 
        
        # --- Estado interno ---
        self.expand = True 
        self.is_scanning = True 
        self.animando_linea = False
        self.lectura_bloqueada = False # Se activa al completar un palet
        self.user = self.page.session.get("user")

        # ESTADO DEL NEGOCIO: Acumulador de datos del palet actual
        self.palet_acumulado = PaletScanData(sscc="")
        
        # COLA (OPTIMIZACIÓN DE RENDIMIENTO)
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
    # SECCIÓN 1: BUILDERS (Construcción visual)
    # --------------------------------------------------------------------------

    def _build_header(self) -> ft.Container:
        nombre_mostrar = "Operador"
        if self.user:
            nombre = getattr(self.user, 'name', '') or ''
            apellido = getattr(self.user, 'surname', '') or ''
            nombre_mostrar = f"{nombre} {apellido}".strip() or self.user.employee_number

        self.mqtt_status_icon = ft.Icon(
            ft.Icons.CLOUD_OFF,
            color=ft.Colors.GREY_400,
            size=20,
            tooltip="MQTT desconectado"
        )

        return ft.Container(
            padding=ft.padding.symmetric(horizontal=20, vertical=15),
            bgcolor=ft.Colors.WHITE,
            shadow=ft.BoxShadow(blur_radius=5, color=ft.Colors.GREY_200, offset=ft.Offset(0,2)),
            content=ft.Row(
                controls=[
                    ft.Column([
                        ft.Text(f"Operador: {nombre_mostrar}", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_800),
                        ft.Text("Sistema de Recepción GS1-128", size=12, color=ft.Colors.BLUE_GREY),
                    ], spacing=2),
                    ft.Row([
                        self.mqtt_status_icon,
                        ft.IconButton(
                            icon=ft.Icons.LOGOUT_ROUNDED, 
                            tooltip="Cerrar Sesión", 
                            icon_color=ft.Colors.RED_400, 
                            on_click=self._logout
                        )
                    ], spacing=5)
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            )
        )

    def _build_camera_panel(self) -> ft.Container:
        self.img_video = ft.Image(
            src_base64=PLACEHOLDER_IMG, 
            # CAMBIO 1: COVER hace que la imagen llene todo el contenedor.
            # (Recortará un poco los laterales, pero elimina el hueco negro)
            fit=ft.ImageFit.COVER,   
            border_radius=12, 
            gapless_playback=True, 
            expand=True
        )

        self.scan_line = ft.Container(
            height=3,
            bgcolor=ft.Colors.RED_ACCENT_400,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.RED_ACCENT_400),
            offset=ft.Offset(0, -0.8), 
            animate_offset=ft.Animation(duration=1500, curve=ft.AnimationCurve.EASE_IN_OUT),
            expand=True
        )

        stack = ft.Stack(
            expand=True,
            # CAMBIO 2: Alineación central forzada para que video, 
            # recuadro y línea de escaneo compartan el mismo centro.
            alignment=ft.alignment.center, 
            controls=[
                # Capa 1: Video
                ft.Container(
                    content=self.img_video,
                    # Aseguramos que el contenedor del video también busque expandirse
                    expand=True, 
                    alignment=ft.alignment.center
                ),
                
                # Capa 2: Recuadro ROI (El cuadrado blanco)
                ft.Container(
                    width=450, 
                    height=450,
                    border=ft.border.all(2, ft.Colors.WHITE60), 
                    border_radius=12,
                    alignment=ft.alignment.center # Asegura centrado interno
                ),
                
                # Capa 3: Línea de escaneo
                ft.Container(
                    alignment=ft.alignment.center, 
                    content=self.scan_line,
                    expand=True
                ),

                # Indicador de tipo de cámara
                ft.Container(content=self._build_camera_status(), alignment=ft.alignment.top_right, padding=20),
                
                # Capa 4: Switch (Este lo mantenemos abajo)
                ft.Container(
                    alignment=ft.alignment.bottom_center, 
                    padding=20,
                    content=ft.Switch(
                        label="Cámara Activa", 
                        label_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), 
                        value=False, 
                        active_color=ft.Colors.GREEN_400, 
                        on_change=self._toggle_camara
                    )
                )
            ]
        )

        return ft.Container(
            expand=1, 
            margin=5,
            border_radius=15, 
            bgcolor=ft.Colors.BLACK,  
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=stack
        )

    def _build_info_panel(self) -> ft.Container:
        self.txt_estado = ft.Text(
            "Cámara apagada", 
            color=ft.Colors.GREY_500, 
            weight=ft.FontWeight.BOLD
        )
        
        self.txt_sscc = ft.Text(
            "---", 
            size=24, 
            weight=ft.FontWeight.BOLD, 
            color=ft.Colors.BLUE_800, 
            text_align=ft.TextAlign.CENTER
        )
        
        self.txt_producto = ft.Text("EAN: -", size=16)
        self.txt_lote = ft.Text("Lote: -", size=14, color=ft.Colors.GREY_700)
        self.txt_fechas = ft.Text("Caducidad: -", size=12, color=ft.Colors.GREY_600)
        self.txt_produccion = ft.Text("Prod: -", size=12, color=ft.Colors.GREY_600)

        self.txt_envio_msg = ft.Text("Enviando datos...", color=ft.Colors.BLUE_700)

        self.info_container = ft.Column(
            opacity=0.3,
            animate_opacity=300,
            controls=[
                ft.Text("SSCC (Matrícula):", size=10, color=ft.Colors.GREY_400),
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
            border_radius=10,
            bgcolor=ft.Colors.BLUE_50,
            content=ft.Row(
                controls=[
                    ft.ProgressRing(width=20, height=20, stroke_width=2),
                    self.txt_envio_msg
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER
            )
        )

        content = ft.Column(
            controls=[
                ft.Row([
                    ft.Icon(ft.Icons.QR_CODE_SCANNER, size=30, color=ft.Colors.BLUE_600), 
                    ft.Text("Recepción", size=20, weight=ft.FontWeight.BOLD)
                ], spacing=10),
                ft.Divider(),
                ft.Container(
                    padding=10, 
                    bgcolor=ft.Colors.BLUE_50, 
                    border_radius=8, 
                    content=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.BLUE), 
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
            expand=1, margin=10, padding=30, 
            bgcolor=ft.Colors.WHITE, border_radius=15,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.GREY_200),
            content=content
        )

    def _build_camera_status(self):
        """
        Construye el indicador de estado de la cámara (Master/Slave)
        Define los controles con atributos de clase para poder actualizarlos
        """
        self.icon_cam_status = ft.Icon(name=ft.Icons.VIDEOCAM_OFF, color=ft.Colors.GREY_500)
        self.txt_cam_status = ft.Text(
            value="PAUSA",
            color=ft.Colors.GREY_500,
            weight=ft.FontWeight.BOLD,
            size=12
        )

        return ft.Container(
            content=ft.Row(
                controls=[self.icon_cam_status, self.txt_cam_status],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=5,
                tight=True
            ),
            bgcolor=ft.Colors.BLACK54,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=5,
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
        self.page.session.clear()
        self.page.go(AppRoutes.LOGIN)

    def _iniciar_flujo_camara(self):
        """Arranca la cámara y LOS DOS HILOS (Visualización + Procesamiento)."""
        
        self._conectar_mqtt()
        
        self.camera_service.iniciar_camara()
        self.escaneando = True
        self.animando_linea = True
        self.lectura_bloqueada = False

        if self.camera_service.using_backup:
            # Estado: SLAVE (Naranja)
            self.txt_cam_status.value = "SLAVE (BACKUP)"
            self.txt_cam_status.color = ft.Colors.ORANGE
            self.icon_cam_status.name = ft.Icons.WARNING_AMBER_ROUNDED
            self.icon_cam_status.color = ft.Colors.ORANGE
        else:
            # Estado: MASTER (verde)
            self.txt_cam_status.value = "MASTER"
            self.txt_cam_status.color = ft.Colors.GREEN
            self.icon_cam_status.name = ft.Icons.VIDEOCAM
            self.icon_cam_status.color = ft.Colors.GREEN

        self.txt_cam_status.update()
        self.icon_cam_status.update()

        # Limpiar la cola por si había basura
        with self.frame_queue.mutex:
            self.frame_queue.queue.clear()

        # Feedback UI
        self.txt_estado.value = "Buscando códigos GS1..."
        self.txt_estado.color = ft.Colors.BLUE
        self.txt_estado.update()
        
        # --- HILOS ---
        threading.Thread(target=self._thread_camera_loop, daemon=True).start()
        threading.Thread(target=self._thread_processing_loop, daemon=True).start()
        threading.Thread(target=self._thread_animacion, daemon=True).start()

    def _detener_flujo_camara(self):
        self.escaneando = False
        self.animando_linea = False
        self.camera_service.detener_camara()

        # Actualización icono estado cámara
        self.txt_cam_status.value = "PAUSA"
        self.txt_cam_status.color = ft.Colors.GREY_500
        self.icon_cam_status.name = ft.Icons.VIDEOCAM_OFF
        self.icon_cam_status.color = ft.Colors.GREY_500
        self.txt_cam_status.update()
        self.icon_cam_status.update()
        # Limpiamos imagen
        self.img_video.src_base64 = PLACEHOLDER_IMG
        self.img_video.update()
        self.txt_estado.value = "Cámara en espera"
        self.txt_estado.update()

    def _limpiar_datos(self):
        """Resetea el acumulador para empezar un nuevo palet."""
        self.lectura_bloqueada = False
        
        # Vaciamos la cola para evitar procesar frames viejos del palet anterior
        with self.frame_queue.mutex:
            self.frame_queue.queue.clear()

        # Reiniciamos el DTO
        self.palet_acumulado = PaletScanData()
        
        # Reset visual
        self.txt_sscc.value = "---"
        self.txt_sscc.color = ft.Colors.BLUE_800
        self.txt_producto.value = "EAN: -"
        self.txt_producto.weight = ft.FontWeight.NORMAL
        self.txt_lote.value = "Lote: -"
        self.txt_lote.color = ft.Colors.GREY_700
        self.txt_fechas.value = "Caducidad: -"
        self.txt_produccion.value = "Prod: -"
        
        self.info_container.opacity = 0.3
        self.info_container.update()

        self.txt_estado.value = "Buscando códigos GS1..."
        self.txt_estado.color = ft.Colors.BLUE
        self.txt_estado.update()
        
        self.scan_line.bgcolor = ft.Colors.RED_ACCENT_400
        self.scan_line.update()

        self.envio_status.visible = False
        self.envio_status.update()

        # Reactivamos animación
        if self.escaneando and not self.animando_linea:
            self.animando_linea = True
            threading.Thread(target=self._thread_animacion, daemon=True).start()

    # --------------------------------------------------------------------------
    # SECCIÓN NUEVA: GESTIÓN MQTT
    # --------------------------------------------------------------------------

    def _conectar_mqtt(self):
        """Establece conexión con el broker MQTT."""
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
        
        # Conectar en thread para no bloquear UI
        threading.Thread(target=_conectar_async, daemon=True).start()

    def _actualizar_mqtt_status(self, conectado: bool):
        """Actualiza el icono de estado MQTT en el header."""
        if conectado:
            self.mqtt_status_icon.name = ft.Icons.CLOUD_DONE
            self.mqtt_status_icon.color = ft.Colors.GREEN_600
            self.mqtt_status_icon.tooltip = "MQTT conectado"
        else:
            self.mqtt_status_icon.name = ft.Icons.CLOUD_OFF
            self.mqtt_status_icon.color = ft.Colors.RED_400
            self.mqtt_status_icon.tooltip = "MQTT desconectado"
        
        try:
            self.mqtt_status_icon.update()
        except Exception as e:
            logger.warning(f"Error actualizando icono MQTT: {e}")

    def _enviar_palet_mqtt(self):
        """
        Envía el palet completo a través de MQTT.
        Ejecutado en thread separado para no bloquear UI.
        """
        def _enviar_async():
            try:
                # Mostrar indicador de envío
                self.envio_status.visible = True
                self.txt_envio_msg.value = "Enviando datos..."
                self.envio_status.update()

                # Obtener employee_number del usuario
                employee_number = getattr(self.user, 'employee_number', 'UNKNOWN')

                # Enviar datos
                enviado = self.mqtt_service.enviar_datos_palet(palet_data=self.palet_acumulado, employee_number=employee_number)

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
        """Muestra el resultado del envío y programa limpieza automática."""
        if exito:
            self.envio_status.bgcolor = ft.Colors.GREEN_50
            self.envio_status.content = ft.Column(
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_600, size=40),
                    ft.Text(
                        "✅ Datos enviados correctamente", 
                        color=ft.Colors.GREEN_700,
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER
                    ),
                    ft.Text(
                        "Escanee el siguiente palet", 
                        color=ft.Colors.GREY_700,
                        size=12,
                        text_align=ft.TextAlign.CENTER
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5
            )
        else:
            self.envio_status.bgcolor = ft.Colors.RED_50
            self.envio_status.content = ft.Column(
                controls=[
                    ft.Icon(ft.Icons.ERROR, color=ft.Colors.RED_600, size=40),
                    ft.Text(
                        "❌ Error al enviar datos", 
                        color=ft.Colors.RED_700,
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER
                    ),
                    ft.Text(
                        "Verifique la conexión MQTT", 
                        color=ft.Colors.GREY_700,
                        size=12,
                        text_align=ft.TextAlign.CENTER
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5
            )

        self.envio_status.update()

        # Limpiar automáticamente después de 3 segundos (solo si éxito)
        if exito:
            def _auto_limpiar():
                time.sleep(3)
                if self.escaneando:  # Solo si seguimos escaneando
                    self._limpiar_datos()
            
            threading.Thread(target=_auto_limpiar, daemon=True).start()
    
    def _handle_scan_timeout(self):
        """
        Handles the timeout event when a label cannot be fully read.
        Renamed from '_procesar_etiqueta_daniada' to English.
        """
        logger.warning(f"Scan Timeout ({AppConfig.READ_TIMEOUT_SEC}s). Reporting damaged label.")

        # Send Incident Report (Async)
        threading.Thread(
            target=self.mqtt_service.send_scan_incident,
            args=(self.palet_acumulado,),
            daemon=True
        ).start()

        # Visual Feedback
        self.txt_estado.value = "❌ ETIQUETA DAÑADA"
        self.txt_estado.color = ft.Colors.RED_ACCENT_400
        self.scan_line.bgcolor = ft.Colors.RED_ACCENT_400
        self.update()

        # Short delay and reset
        time.sleep(2.0)
        self._limpiar_datos()
        
        # Restore UI
        self.txt_estado.value = "ESPERANDO NUEVA ETIQUETA"
        self.txt_estado.color = ft.Colors.WHITE
        self.scan_line.bgcolor = ft.Colors.BLUE_ACCENT
        self.update()
        
    # --------------------------------------------------------------------------
    # SECCIÓN 3: LOGICA DE HILOS
    # --------------------------------------------------------------------------

    def _thread_camera_loop(self):
        """
        HILO PRODUCTOR: Prioridad Máxima -> Fluidez de Video.
        Captura frames y actualiza la UI a máxima velocidad.
        """
        time.sleep(0.5) # Warmup cámara
        
        while self.escaneando:
            frame_hd = self.camera_service.obtener_frame()
            
            if frame_hd is None:
                time.sleep(0.02)
                continue

            # Renderizado Rápido (UI)
            frame_b64 = self.camera_service.convertir_numpy_a_base64(
                frame_hd, quality=50, width_resize=800
            )
            
            if frame_b64:
                self.img_video.src_base64 = frame_b64
                self.img_video.update()

            # Enviar a Cola de IA (Strategy: Drop Frame)
            if not self.lectura_bloqueada:
                try:
                    self.frame_queue.put_nowait(frame_hd)
                except queue.Full:
                    pass 
            
            time.sleep(0.025)

    def _thread_processing_loop(self):
        """
        HILO CONSUMIDOR: Velocidad Variable.
        Recibe frames de la cola y ejecuta la IA pesada (YOLO + Scanner).
        """
        while self.is_scanning:
            try:
                frame = self.frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                # WATCHDOG DE TIMEOUT (FAIL FAST)
                if (self.palet_acumulado.scan_start_time is not None
                    and self.palet_acumulado.has_timed_out(AppConfig.READ_TIMEOUT_SEC)):
                    
                    logger.warning(f"Tiempo de lectura agotado para palet SSCC: {self.palet_acumulado.sscc}")
                    
                    # Ejecutamos la lógica de error (UI roja + MQTT reporte)
                    self._handle_scan_timeout()
                    
                    # Clear the queue to skip pending frames
                    with self.frame_queue.mutex:
                        self.frame_queue.queue.clear()
                        
                    continue
                
                # A. Detection (YOLO)
                rois_detectados = self.yolo_service.detectar(frame)
                
                if rois_detectados is None or len(rois_detectados) > 0:
                    self.palet_acumulado.init_timeout()
                
                # B. Decodificación (Zxing + GS1)
                scan_result_dto = self.scanner_service.procesar_zonas(frame, rois_detectados)
                
                # C. Lógica de Negocio (Fusión)
                if self._fusionar_datos(scan_result_dto):
                    self._actualizar_ui_progreso()
                    
                    if self.palet_acumulado.is_complete():
                        self._finalizar_palet()
                        # Vaciamos la cola para no seguir procesando frames pendientes
                        with self.frame_queue.mutex:
                            self.frame_queue.queue.clear()

            except Exception as e:
                logger.error(f"Error en hilo de procesamiento IA: {e}")
            finally:
                self.frame_queue.task_done()

    def _fusionar_datos(self, nuevo_dato: PaletScanData) -> bool:
        """Algoritmo de fusión: Rellena los huecos del palet acumulado."""
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
        """Refresca los textos de la UI con los datos acumulados."""
        p = self.palet_acumulado
        
        # SSCC
        if p.sscc: 
            self.txt_sscc.value = p.sscc
            self.txt_sscc.color = ft.Colors.BLUE_800 
        
        # EAN
        ean_val = getattr(p, 'ean', None) or getattr(p, 'gtin', None)
        if ean_val: 
            self.txt_producto.value = f"EAN: {ean_val}"
            self.txt_producto.weight = ft.FontWeight.BOLD

        # Lote
        if p.batch_number: 
            self.txt_lote.value = f"Lote: {p.batch_number}"
            self.txt_lote.color = ft.Colors.BLACK87

        # Fechas
        if p.product_use_by_date: 
            self.txt_fechas.value = f"Caducidad: {p.product_use_by_date}"
        
        # Producción
        prod_str = []
        if p.packaging_date: prod_str.append(p.packaging_date)
        if p.production_time: prod_str.append(p.production_time)
        if prod_str: 
            self.txt_produccion.value = f"Prod: {' '.join(prod_str)}"

        self.info_container.opacity = 1.0
        self.info_container.update()

    def _finalizar_palet(self):
        """
        MODIFICADO: Cuando el palet tiene todos los campos obligatorios,
        ahora se envía automáticamente por MQTT.
        """
        self.lectura_bloqueada = True
        
        self.txt_estado.value = "✅ PALET COMPLETADO"
        self.txt_estado.color = ft.Colors.GREEN_700
        
        self.animando_linea = False 
        self.scan_line.offset = ft.Offset(0, 0) 
        self.scan_line.bgcolor = ft.Colors.GREEN 
        
        self.update()
        
        logger.info(f"✅ Palet SSCC: {self.palet_acumulado.sscc} completado")
        
        self._enviar_palet_mqtt()

    def _thread_animacion(self):
        """Efecto visual de 'cylon'."""
        direccion_abajo = True
        while self.animando_linea and self.escaneando:
            nuevo_offset = ft.Offset(0, 1.2) if direccion_abajo else ft.Offset(0, -1.2)
            self.scan_line.offset = nuevo_offset
            try:
                self.scan_line.update()
            except Exception as e:
                logger.debug(f"Animación detenida (UI no accesible): {e}")
                break 
            
            direccion_abajo = not direccion_abajo
            time.sleep(1.6)