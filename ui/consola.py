from datetime import datetime

import flet as ft


def build_consola(page):
    log_ui = ft.Column(
        spacing=6,
        scroll=ft.ScrollMode.AUTO,
        auto_scroll=True,
    )
    log_container = ft.Container(
        content=log_ui,
        expand=True,
        border_radius=10,
        bgcolor="#F8F9FA",
        border=ft.border.all(1, ft.Colors.GREY_300),
        padding=ft.padding.all(10),
    )

    def log_msg(texto, color=None, weight=None, italic=False, is_divider=False):
        """Agrega un mensaje estilo chat-bubble al log con timestamp y auto-scroll."""
        if is_divider:
            log_ui.controls.append(
                ft.Container(
                    content=ft.Divider(height=1, color=ft.Colors.GREY_300),
                    padding=ft.padding.symmetric(vertical=4),
                )
            )
            page.update()
            return

        timestamp = datetime.now().strftime("%H:%M:%S")

        if color == ft.Colors.RED or color == ft.Colors.RED_700:
            bubble_bg = "#FFF5F5"
            border_color = ft.Colors.RED_200
        elif color == ft.Colors.GREEN_700 or color == ft.Colors.GREEN_800:
            bubble_bg = "#F0FFF4"
            border_color = ft.Colors.GREEN_200
        elif (
            color == ft.Colors.ORANGE
            or color == ft.Colors.ORANGE_700
            or color == ft.Colors.ORANGE_800
        ):
            bubble_bg = "#FFFAF0"
            border_color = ft.Colors.ORANGE_200
        elif color == ft.Colors.BLUE or color == ft.Colors.BLUE_800:
            bubble_bg = "#EBF8FF"
            border_color = ft.Colors.BLUE_200
        elif color == ft.Colors.AMBER_800:
            bubble_bg = "#FFFBEB"
            border_color = ft.Colors.AMBER_200
        else:
            bubble_bg = ft.Colors.WHITE
            border_color = ft.Colors.GREY_200

        bubble = ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        timestamp,
                        size=9,
                        color=ft.Colors.GREY_400,
                        italic=True,
                        no_wrap=True,
                    ),
                    ft.Text(
                        texto,
                        size=12,
                        color=color,
                        weight=weight,
                        italic=italic,
                        expand=True,
                        selectable=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=10,
            bgcolor=bubble_bg,
            border=ft.border.all(1, border_color),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=2,
                color=ft.Colors.with_opacity(0.04, ft.Colors.BLACK),
                offset=ft.Offset(0, 1),
            ),
            animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_IN),
        )

        log_ui.controls.append(bubble)

        MAX_LOG_MESSAGES = 150
        if len(log_ui.controls) > MAX_LOG_MESSAGES:
            log_ui.controls = log_ui.controls[-MAX_LOG_MESSAGES:]

        page.update()

    def limpiar_log(e=None):
        log_ui.controls.clear()
        page.update()

    return log_container, log_msg, limpiar_log
