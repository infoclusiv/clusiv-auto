import flet as ft


def construir_tracker_fases(page):
    fases = [
        ("youtube", "📺", "Análisis YouTube"),
        ("chatgpt", "💬", "ChatGPT - Prompts"),
        ("texto", "📄", "Post-proceso texto"),
        ("tts", "🔊", "Síntesis TTS"),
        ("whisperx", "🎙️", "Transcripción"),
        ("aistudio", "🤖", "Prompts de imagen"),
        ("flow", "🖼️", "Generación imágenes"),
    ]
    color_map = {
        "pending": ft.Colors.GREY_400,
        "running": ft.Colors.BLUE_500,
        "done": ft.Colors.GREEN_600,
        "error": ft.Colors.RED_500,
        "skipped": ft.Colors.AMBER_500,
    }
    icon_map = {
        "pending": ft.Icons.RADIO_BUTTON_UNCHECKED,
        "running": ft.Icons.SYNC,
        "done": ft.Icons.CHECK_CIRCLE_OUTLINE,
        "error": ft.Icons.ERROR_OUTLINE,
        "skipped": ft.Icons.SKIP_NEXT,
    }

    controles = {}
    filas = []

    for fase_id, icono, nombre in fases:
        indicador = ft.Icon(
            ft.Icons.RADIO_BUTTON_UNCHECKED,
            color=ft.Colors.GREY_400,
            size=16,
        )
        lbl_detalle = ft.Text("-", size=10, color=ft.Colors.GREY_400, italic=True)
        fila = ft.Container(
            content=ft.Row(
                [
                    indicador,
                    ft.Column(
                        [
                            ft.Text(f"{icono}  {nombre}", size=12, weight="bold"),
                            lbl_detalle,
                        ],
                        spacing=1,
                        tight=True,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=6),
            border_radius=8,
            bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_200),
        )
        controles[fase_id] = {"icono": indicador, "label": lbl_detalle, "row": fila}
        filas.append(fila)

    def set_fase_estado(fase_id, estado, detalle="", refresh=True):
        control = controles.get(fase_id)
        if not control:
            return

        color = color_map.get(estado, ft.Colors.GREY_400)
        control["icono"].name = icon_map.get(estado, ft.Icons.RADIO_BUTTON_UNCHECKED)
        control["icono"].color = color
        control["label"].value = detalle or estado
        control["label"].color = color

        if estado == "running":
            control["row"].bgcolor = "#EBF8FF"
            control["row"].border = ft.border.all(1, ft.Colors.BLUE_300)
        elif estado == "done":
            control["row"].bgcolor = "#F0FFF4"
            control["row"].border = ft.border.all(1, ft.Colors.GREEN_300)
        elif estado == "error":
            control["row"].bgcolor = "#FFF5F5"
            control["row"].border = ft.border.all(1, ft.Colors.RED_200)
        elif estado == "skipped":
            control["row"].bgcolor = "#FFFBEB"
            control["row"].border = ft.border.all(1, ft.Colors.AMBER_200)
        else:
            control["row"].bgcolor = ft.Colors.GREY_50
            control["row"].border = ft.border.all(1, ft.Colors.GREY_200)

        if refresh and page.controls:
            page.update()

    def reset_tracker():
        for fase_id, _, _ in fases:
            set_fase_estado(fase_id, "pending", "-", refresh=False)
        if page.controls:
            page.update()

    return ft.Column(filas, spacing=4), set_fase_estado, reset_tracker
