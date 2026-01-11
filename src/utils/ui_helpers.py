import flet as ft
import logging

logger = logging.getLogger(__name__)

class UiHelper:
    """
    Clase utilitaria para manejar la visualización de errores en la UI.
    """
    
    @staticmethod
    def show_alert(page: ft.Page, title: str, message: str):
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                ft.TextButton("Entendido", on_click=lambda _: UiHelper._cerrar_dialogo(page, dlg))
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            modal=True
        )
        
        # Uso seguro de overlay para el arranque
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    @staticmethod
    def fatal_error(page: ft.Page, mensaje: str):
        
        def cerrar_app(_):
            logger.info("Cerrando aplicación tras error fatal.")
            # CORRECCIÓN: Sintaxis moderna de Flet para cerrar ventana
            page.window.close()

        dlg = ft.AlertDialog(
            title=ft.Text("Error de Inicialización"),
            content=ft.Text(
                f"No se pudo iniciar el sistema correctamente:\n\n{mensaje}\n\n"
                "Por favor, contacte con soporte técnico o revise los logs."
            ),
            actions=[
                ft.TextButton("Cerrar Aplicación", on_click=cerrar_app)
            ],
            modal=True 
        )

        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    @staticmethod
    def _cerrar_dialogo(page, dlg):
        dlg.open = False
        page.update()