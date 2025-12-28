import logging
import threading
import time
import flet as ft
from src.services.auth_service import AuthService
from src.services.camera_service import CameraService

logger = logging.getLogger(__name__)

# Un pixel gris en Base64 para inicializar la imagen sin errores
PLACEHOLDER_IMG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="

class DashboardView(ft.Column):
    def __init__(self, page: ft.Page, auth_service: AuthService, camera_service: CameraService):
        super().__init__()
        self.page = page
        self.auth_service = auth_service
        self.camera_service = camera_service
        
        self.expand = True 
        self.escaneando = False 
        self.animando_linea = False # Bandera para el bucle de animación

        # --- 1. DATOS DEL USUARIO Y HEADER ---
        self.user = self.page.session.get("usuario_sesion")
        nombre_mostrar = "Usuario"
        if self.user:
            nombre = getattr(self.user, 'name', '') or ''
            apellido = getattr(self.user, 'surname', '') or ''
            full_name = f"{nombre} {apellido}".strip()
            nombre_mostrar = full_name if full_name else self.user.employee_number

        self.header = ft.Container(
            padding=ft.padding.symmetric(horizontal=20, vertical=15),
            content=ft.Row(
                controls=[
                    ft.Text(f"Hola, {nombre_mostrar}", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_800),
                    ft.IconButton(icon=ft.Icons.LOGOUT_ROUNDED, tooltip="Cerrar Sesión", icon_size=26, icon_color=ft.Colors.RED_400, on_click=self._logout)
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER 
            )
        )

        # --- 2. COMPONENTES DEL ESCÁNER ---
        
        # A. La imagen del video
        self.img_video = ft.Image(
            src_base64=PLACEHOLDER_IMG, 
            width=640, 
            height=480,
            fit=ft.ImageFit.COVER,
            border_radius=12,
            gapless_playback=True 
        )

        # B. La línea de escaneo roja
        self.scan_line = ft.Container(
            width=280,
            height=2,
            bgcolor=ft.Colors.RED_ACCENT_400,
            shadow=ft.BoxShadow(blur_radius=5, color=ft.Colors.RED_ACCENT_400),
            
            # --- CORRECCIÓN 1: ft.Offset en lugar de ft.transform.Offset ---
            offset=ft.Offset(0, -1.2), 
            
            # --- CORRECCIÓN 2: ft.Animation en lugar de ft.animation.Animation ---
            animate_offset=ft.Animation(duration=1500, curve=ft.AnimationCurve.EASE_IN_OUT)
        )

        # C. Construcción del Stack
        self.scanner_stack = ft.Stack(
            width=640,
            height=480,
            controls=[
                self.img_video,
                # Overlay oscuro
                ft.Container(
                    alignment=ft.alignment.center,
                    content=ft.Container(
                        width=250, 
                        height=250,
                        border=ft.border.all(2, ft.Colors.WHITE54),
                        border_radius=12,
                        shadow=ft.BoxShadow(
                            spread_radius=1000, 
                            color=ft.Colors.with_opacity(0.5, ft.Colors.BLACK), 
                            offset=ft.Offset(0,0),
                            blur_style=ft.ShadowBlurStyle.SOLID
                        )
                    )
                ),
                # Línea animada
                ft.Container(
                    alignment=ft.alignment.center,
                    content=self.scan_line
                )
            ]
        )

        # D. Header diálogo
        header_dialogo = ft.Row(
            controls=[
                ft.IconButton(ft.Icons.CLOSE, on_click=self._cerrar_modal_camara, icon_color=ft.Colors.GREY_600),
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    bgcolor=ft.Colors.GREEN_50,
                    border_radius=20,
                    content=ft.Row([
                        ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, color=ft.Colors.GREEN, size=14),
                        ft.Text("Cámara Activa", color=ft.Colors.GREEN_800, size=12, weight=ft.FontWeight.BOLD)
                    ], spacing=5)
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )

        # E. Footer diálogo
        footer_dialogo = ft.Column(
            controls=[
                ft.Text("Escanea el código QR del palet", weight=ft.FontWeight.BOLD, size=16, text_align=ft.TextAlign.CENTER),
                ft.Text("Sitúa el código dentro del marco cuadrado para procesarlo.", color=ft.Colors.GREY_600, size=12, text_align=ft.TextAlign.CENTER)
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=5
        )

        # F. Diálogo final
        self.dlg_escaner = ft.AlertDialog(
            modal=True,
            title_padding=0,
            content_padding=ft.padding.all(20),
            actions_padding=0,
            shape=ft.RoundedRectangleBorder(radius=16),
            content=ft.Container(
                width=650,
                content=ft.Column(
                    controls=[
                        header_dialogo,
                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                        self.scanner_stack,
                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                        footer_dialogo
                    ],
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                )
            ),
            on_dismiss=lambda e: self._cerrar_modal_camara(None) 
        )

        # --- 3. BOTÓN PRINCIPAL ---
        try:
            tiene_camara = self.camera_service.verificar_disponibilidad()
        except Exception as e:
            logger.error(f"Error checking camera: {e}")
            tiene_camara = False
            
        color_fondo = ft.Colors.BLUE_600 if tiene_camara else ft.Colors.GREY_400
        
        self.scan_button = ft.Container(
            width=280, height=280,
            bgcolor=color_fondo, border_radius=30, disabled=not tiene_camara,
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color=ft.Colors.BLUE_200 if tiene_camara else ft.Colors.GREY_300, offset=ft.Offset(0, 5)),
            on_click=self._abrir_modal_camara,
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.QR_CODE_SCANNER if tiene_camara else ft.Icons.NO_PHOTOGRAPHY, size=80, color=ft.Colors.WHITE),
                    ft.Text("ESCANEAR PALET", size=20, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    ft.Text("Toca para iniciar" if tiene_camara else "Cámara no detectada", size=12, color=ft.Colors.BLUE_100)
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            )
        )

        self.controls = [
            self.header,
            ft.Divider(height=1, color=ft.Colors.GREY_200),
            ft.Container(expand=True, content=self.scan_button, alignment=ft.alignment.center)
        ]

    # --- MÉTODOS DE LÓGICA ---

    def _abrir_modal_camara(self, e):
        self.page.open(self.dlg_escaner)
        self.camera_service.iniciar_camara()
        
        self.escaneando = True
        self.animando_linea = True
        
        threading.Thread(target=self._bucle_captura, daemon=True).start()
        threading.Thread(target=self._animar_linea_bucle, daemon=True).start()

    def _cerrar_modal_camara(self, e):
        self.escaneando = False
        self.animando_linea = False
        self.camera_service.detener_camara()
        self.page.close(self.dlg_escaner)

    def _animar_linea_bucle(self):
        """Bucle infinito que mueve la línea de arriba a abajo"""
        time.sleep(0.5)
        direccion_abajo = True
        while self.animando_linea:
            # --- CORRECCIÓN 3: Eliminado 'ft.transform.' aquí también ---
            nuevo_offset = ft.Offset(0, 1.2) if direccion_abajo else ft.Offset(0, -1.2)
            
            self.scan_line.offset = nuevo_offset
            try:
                self.scan_line.update()
            except: pass
            
            direccion_abajo = not direccion_abajo
            time.sleep(1.6)

    def _bucle_captura(self):
        time.sleep(0.5) 
        while self.escaneando:
            try:
                frame_b64 = self.camera_service.obtener_frame_base64()
                if frame_b64:
                    self.img_video.src_base64 = frame_b64
                    try:
                        self.img_video.update()
                    except Exception as e:
                        logger.warning(f"Error actualizando frame: {e}")
            except Exception as e:
                logger.error(f"Error en bucle de cámara: {e}")
            time.sleep(0.03)
            
    def _logout(self, e):
        self.auth_service.cerrar_sesion(self.user)
        self.page.session.clear()
        self.page.go("/login")