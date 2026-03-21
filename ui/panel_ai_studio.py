import flet as ft

from config import guardar_config, normalizar_ai_studio_config


def build_panel_ai_studio(page, state):
    ai_studio_config = state.ai_studio_config
    config_actual = state.config_actual

    def show_snack(msg, color=ft.Colors.GREEN):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), bgcolor=color))
        page.overlay[-1].open = True
        page.update()

    txt_prompt_ai_studio = ft.TextField(
        label="Prompt para Google AI Studio (se envía al finalizar WhisperX)",
        value=ai_studio_config.get("prompt", ""),
        multiline=True,
        min_lines=3,
        max_lines=6,
        text_size=12,
        hint_text="Escribe aquí el prompt que se pegará en AI Studio...",
        expand=True,
    )
    txt_ai_studio_wait = ft.TextField(
        label="Espera respuesta AI Studio (segundos)",
        value=str(ai_studio_config.get("espera_respuesta_segundos", 15)),
        dense=True,
        width=220,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    def persistir_ai_studio_desde_ui(mostrar_snack=False):
        ai_studio_config["prompt"] = txt_prompt_ai_studio.value
        ai_studio_config["espera_respuesta_segundos"] = txt_ai_studio_wait.value

        normalizado = normalizar_ai_studio_config(ai_studio_config)
        ai_studio_config.update(normalizado)

        txt_prompt_ai_studio.value = ai_studio_config["prompt"]
        txt_ai_studio_wait.value = str(ai_studio_config["espera_respuesta_segundos"])
        config_actual["ai_studio"] = dict(ai_studio_config)
        config_actual["prompt_ai_studio"] = ai_studio_config["prompt"]

        guardar_config(ai_studio=ai_studio_config)
        if mostrar_snack:
            show_snack("Configuración AI Studio guardada", ft.Colors.GREEN)
        page.update()

    txt_prompt_ai_studio.on_blur = lambda e: persistir_ai_studio_desde_ui()
    txt_ai_studio_wait.on_blur = lambda e: persistir_ai_studio_desde_ui()

    expansion_ai_studio = ft.ExpansionTile(
        title=ft.Text("🤖 Prompts de Imagen - AI Studio", weight="bold", size=13),
        subtitle=ft.Text(
            "Analiza script.txt y genera prompts visuales (Fase 5)",
            size=11,
            color=ft.Colors.GREY_600,
        ),
        expanded=False,
        controls=[
            txt_ai_studio_wait,
            txt_prompt_ai_studio,
            ft.Text(
                "Los prompts extraídos se guardarán en prompts_imagenes.txt.",
                size=11,
                color=ft.Colors.GREY_600,
                italic=True,
            ),
            ft.ElevatedButton(
                "Guardar configuración AI Studio",
                icon=ft.Icons.SAVE,
                on_click=lambda e: persistir_ai_studio_desde_ui(mostrar_snack=True),
                bgcolor=ft.Colors.BLUE_700,
                color="white",
                width=1000,
                height=40,
            ),
        ],
    )

    def get_ai_studio_config():
        return ai_studio_config

    return expansion_ai_studio, get_ai_studio_config