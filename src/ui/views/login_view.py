import logging
import flet as ft
from src.services.auth_service import AuthService 

# Instancia del logger a nivel de clase/módulo
logger = logging.getLogger(__name__)

class LoginView(ft.Column):
    def __init__(self, page: ft.Page, auth_service: AuthService):
        super().__init__()
        self.page = page
        self.auth_service = auth_service
        
        # Configuración de alineación del propio componente (Columna)
        self.alignment = ft.MainAxisAlignment.CENTER
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.spacing = 20

        # --- Componentes UI ---
        self.txt_user = ft.TextField(
            label="Número de Empleado", 
            width=300, 
            prefix_icon=ft.Icons.PERSON,
            border_radius=10,
            on_submit=self._manejar_login 
        )

        self.txt_pass = ft.TextField(
            label="Contraseña", 
            password=True, 
            can_reveal_password=True, 
            width=300, 
            prefix_icon=ft.Icons.LOCK,
            border_radius=10,
            on_submit=self._manejar_login 
        )

        self.btn_login = ft.ElevatedButton(
            text="INGRESAR",
            width=300,
            height=45,
            on_click=self._manejar_login,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_700,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=8)
            )
        )

        # Agregamos los controles a la vista
        self.controls = [
            ft.Icon(ft.Icons.SECURITY, size=80, color=ft.Colors.BLUE_700),
            ft.Text("Sistema Automatizado de Inventariado", size=24, weight=ft.FontWeight.BOLD),
            self.txt_user,
            self.txt_pass,
            self.btn_login
        ]

    def _mostrar_alerta(self, titulo, mensaje):
        """Función auxiliar para crear y mostrar el diálogo de alerta"""
        
        # Creamos el diálogo
        # Usamos una variable local para poder referenciarla en el evento on_click
        dlg_alerta = ft.AlertDialog(
            modal=True, # Esto obliga al usuario a pulsar el botón para cerrar
            title=ft.Text(titulo),
            content=ft.Text(mensaje),
            actions=[
                ft.TextButton("Entendido", on_click=lambda e: self.page.close(dlg_alerta)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        # Lo abrimos usando el método moderno de Flet
        self.page.open(dlg_alerta)

    def _manejar_login(self, e):
        """Método privado que maneja el evento del click"""
        user_val = self.txt_user.value
        password_val = self.txt_pass.value

        # Validación visual simple
        if not user_val or not password_val:
            self._mostrar_alerta("Campos vacíos", "Por favor, introduce tu usuario y contraseña.")
            return

        # 1. Llamamos al servicio de autenticación
        usuario_logueado = self.auth_service.autenticar_usuario(user_val, password_val)

        if usuario_logueado is not None:
            # Guardamos el usuario en la sesión
            self.page.session.set("usuario_sesion", usuario_logueado)
            logger.debug(f"Redirigiendo al Dashboard al usuario {usuario_logueado.employee_number}.")
            
            # 2. Navegamos al Dashboard
            self.page.go("/dashboard")
        else:
            logger.debug(f"Fallo de autenticación para el usuario {user_val}.")
            
            # --- AQUÍ ESTÁ EL CAMBIO ---
            # En lugar de SnackBar, llamamos a nuestra función de Alerta
            self._mostrar_alerta(
                "Error de Acceso", 
                "El usuario o la contraseña son incorrectos.\nO tal vez tu usuario está bloqueado."
            )