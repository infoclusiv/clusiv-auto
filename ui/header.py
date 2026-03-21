import flet as ft


def build_header(page):
    icono_ext_status = ft.Icon(ft.Icons.CIRCLE, size=10, color=ft.Colors.ORANGE_400)
    lbl_ext_status = ft.Text(
        "Extensión: desconectada",
        size=11,
        color=ft.Colors.ORANGE_700,
    )

    def actualizar_ext_status_header(conectada, version=""):
        version_label = f" v{version}" if version else ""
        if conectada:
            lbl_ext_status.value = f"Extensión: conectada{version_label}"
            lbl_ext_status.color = ft.Colors.GREEN_700
            icono_ext_status.color = ft.Colors.GREEN_500
        else:
            lbl_ext_status.value = "Extensión: desconectada"
            lbl_ext_status.color = ft.Colors.ORANGE_700
            icono_ext_status.color = ft.Colors.ORANGE_400
        if page.controls:
            page.update()

    header_bar = ft.Container(
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.AUTO_AWESOME, color=ft.Colors.BLUE_700, size=22),
                        ft.Text("Clusiv", size=20, weight="bold", color=ft.Colors.BLUE_800),
                        ft.Text("Automation", size=20),
                    ],
                    spacing=6,
                ),
                ft.Row([icono_ext_status, lbl_ext_status], spacing=4),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        padding=ft.padding.symmetric(horizontal=20, vertical=10),
        bgcolor=ft.Colors.WHITE,
        border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_200)),
        shadow=ft.BoxShadow(
            blur_radius=4,
            color=ft.Colors.with_opacity(0.06, ft.Colors.BLACK),
            offset=ft.Offset(0, 2),
        ),
    )

    return header_bar, actualizar_ext_status_header