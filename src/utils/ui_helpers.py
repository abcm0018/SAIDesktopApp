import flet as ft
import logging

from src.ui import design_system as ds

logger = logging.getLogger(__name__)


class UiHelper:
    @staticmethod
    def show_alert(page: ft.Page, title: str, message: str):
        dlg = ft.AlertDialog(
            bgcolor=ds.SURFACE_CARD,
            shape=ft.RoundedRectangleBorder(radius=ds.RADIUS_LG),
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.INFO_OUTLINE, color=ds.ACCENT_BLUE, size=20),
                    ft.Text(title, color=ds.TEXT_PRIMARY, weight=ft.FontWeight.BOLD, size=14),
                ],
                spacing=8,
            ),
            content=ft.Text(message, color=ds.TEXT_SECONDARY, size=13),
            actions=[
                ft.ElevatedButton(
                    "Entendido",
                    style=ft.ButtonStyle(
                        bgcolor=ds.ACCENT_BLUE,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=ds.RADIUS_MD),
                    ),
                    on_click=lambda _: UiHelper._cerrar_dialogo(page, dlg),
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            modal=True,
        )

        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    @staticmethod
    def fatal_error(page: ft.Page, mensaje: str):
        def cerrar_app(_):
            logger.info("Cerrando aplicación tras error fatal.")
            page.window.close()

        dlg = ft.AlertDialog(
            bgcolor=ds.SURFACE_CARD,
            shape=ft.RoundedRectangleBorder(radius=ds.RADIUS_LG),
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WARNING_ROUNDED, color=ds.ACCENT_RED, size=20),
                    ft.Text(
                        "Error de Inicialización",
                        color=ds.ACCENT_RED,
                        weight=ft.FontWeight.BOLD,
                        size=14,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Text(
                f"No se pudo iniciar el sistema correctamente:\n\n{mensaje}\n\n"
                "Por favor, contacte con soporte técnico o revise los logs.",
                color=ds.TEXT_SECONDARY,
                size=13,
            ),
            actions=[
                ft.ElevatedButton(
                    "Cerrar Aplicación",
                    style=ft.ButtonStyle(
                        bgcolor=ds.ACCENT_RED,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=ds.RADIUS_MD),
                    ),
                    on_click=cerrar_app,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            modal=True,
        )

        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    @staticmethod
    def _cerrar_dialogo(page, dlg):
        dlg.open = False
        page.update()
