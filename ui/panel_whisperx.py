import flet as ft

from config import guardar_config


def build_panel_whisperx(page, state):
    whisperx_config = state.whisperx_config

    def show_snack(msg, color=ft.Colors.GREEN):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), bgcolor=color))
        page.overlay[-1].open = True
        page.update()

    switch_whisperx_enabled = ft.Switch(
        label="🎙️ Transcribir audio con WhisperX automáticamente",
        value=whisperx_config.get("enabled", False),
        active_color=ft.Colors.PURPLE_600,
    )
    txt_whisperx_model = ft.Dropdown(
        label="Modelo WhisperX",
        value=whisperx_config.get("model", "medium"),
        options=[
            ft.dropdown.Option("tiny"),
            ft.dropdown.Option("base"),
            ft.dropdown.Option("small"),
            ft.dropdown.Option("medium"),
            ft.dropdown.Option("large"),
        ],
        dense=True,
    )
    txt_whisperx_python = ft.TextField(
        label="Ruta Python (whisperx-env)",
        value=whisperx_config.get("python_path", ""),
        dense=True,
        hint_text=r"C:\Users\carlo\miniconda3\envs\whisperx-env\python.exe",
    )

    def persistir_whisperx_desde_ui(mostrar_snack=False):
        whisperx_config["enabled"] = bool(switch_whisperx_enabled.value)
        whisperx_config["model"] = txt_whisperx_model.value or "medium"
        whisperx_config["python_path"] = txt_whisperx_python.value.strip()
        guardar_config(whisperx=whisperx_config)
        if mostrar_snack:
            show_snack("Configuración WhisperX guardada", ft.Colors.GREEN)
        page.update()

    switch_whisperx_enabled.on_change = lambda e: persistir_whisperx_desde_ui()
    txt_whisperx_model.on_change = lambda e: persistir_whisperx_desde_ui()
    txt_whisperx_python.on_blur = lambda e: persistir_whisperx_desde_ui()

    expansion_whisperx = ft.ExpansionTile(
        title=ft.Text("🎙️ Transcripción - WhisperX", weight="bold", size=13),
        subtitle=ft.Text(
            "Timestamps por palabra para sincronización (Fase 4)",
            size=11,
            color=ft.Colors.GREY_600,
        ),
        expanded=False,
        controls=[
            switch_whisperx_enabled,
            txt_whisperx_model,
            txt_whisperx_python,
            ft.ElevatedButton(
                "Guardar config WhisperX",
                icon=ft.Icons.SAVE,
                on_click=lambda e: persistir_whisperx_desde_ui(mostrar_snack=True),
                bgcolor=ft.Colors.PURPLE_600,
                color="white",
            ),
        ],
    )

    def get_whisperx_config():
        return whisperx_config

    return expansion_whisperx, get_whisperx_config
