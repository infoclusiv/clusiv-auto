import flet as ft

from config import guardar_config
from database import agregar_canal_db, eliminar_canal_db, obtener_canales_db
from youtube_analyzer import obtener_siguiente_num


def build_panel_proyecto(page, state, on_ruta_cambiada=None):
    input_id = ft.TextField(label="ID del Canal", expand=True)
    input_name = ft.TextField(label="Nombre del Canal", expand=True)
    lista_canales_ui = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, height=300)

    def show_snack(msg, color=ft.Colors.GREEN):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), bgcolor=color))
        page.overlay[-1].open = True
        page.update()

    def refrescar_canales():
        lista_canales_ui.controls.clear()
        for ch in obtener_canales_db():
            lista_canales_ui.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.PLAY_CIRCLE_FILL,
                                color=ft.Colors.RED_600,
                                size=20,
                            ),
                            ft.Column(
                                [
                                    ft.Text(ch[1], weight="bold", size=12),
                                    ft.Text(ch[0], size=9),
                                ],
                                expand=True,
                                spacing=0,
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                icon_color=ft.Colors.RED_400,
                                on_click=lambda _, id=ch[0]: borrar_canal(id),
                            ),
                        ]
                    ),
                    padding=8,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=8,
                )
            )
        page.update()

    def borrar_canal(ch_id):
        eliminar_canal_db(ch_id)
        refrescar_canales()
        show_snack("Canal eliminado", ft.Colors.ORANGE)

    def agregar_canal(e):
        if input_id.value and input_name.value:
            res, msg = agregar_canal_db(input_id.value, input_name.value)
            show_snack(msg, ft.Colors.GREEN if res else ft.Colors.RED)
            input_id.value = ""
            input_name.value = ""
            refrescar_canales()

    def on_pick_directory(path):
        if not path:
            return
        state.ruta_base[0] = path
        state.config_actual["ruta_proyectos"] = path
        guardar_config(ruta=path)
        if on_ruta_cambiada:
            on_ruta_cambiada(path)
        else:
            obtener_siguiente_num(state.ruta_base[0])
        page.update()

    picker = ft.FilePicker()

    expansion_proyecto = ft.ExpansionTile(
        title=ft.Text("📁 Proyecto & Canales YouTube", weight="bold", size=13),
        subtitle=ft.Text(
            "Fuente de referencia y carpeta de salida",
            size=11,
            color=ft.Colors.GREY_600,
        ),
        expanded=True,
        controls=[
            ft.ElevatedButton(
                "Ruta de Proyectos",
                icon=ft.Icons.FOLDER_OPEN,
                on_click=lambda _: on_pick_directory(picker.get_directory_path()),
            ),
            ft.Divider(),
            ft.Text(
                "Canales de referencia",
                size=12,
                weight="bold",
                color=ft.Colors.GREY_700,
            ),
            ft.Row([input_id, input_name]),
            ft.ElevatedButton(
                "Agregar Canal",
                icon=ft.Icons.ADD,
                on_click=agregar_canal,
                width=1000,
                bgcolor=ft.Colors.BLUE_800,
                color="white",
            ),
            ft.Divider(),
            lista_canales_ui,
        ],
    )

    return expansion_proyecto, picker, refrescar_canales, on_ruta_cambiada
