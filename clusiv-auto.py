import flet as ft
import os
import re
import threading
import pyautogui
import pygetwindow as gw
import webbrowser
import pyperclip
from datetime import datetime
from antibot import (
    escribir_humanizado,
    espera_humanizada,
    scroll_simulado,
    sleep_cancelable,
)
from config import (
    AI_STUDIO_OUTPUT_FILENAME_DEFAULT,
    AI_STUDIO_WINDOW_TITLES,
    NVIDIA_API_KEY,
    PATH_CHATGPT,
    YOUTUBE_API_KEY,
    cargar_toda_config,
    describir_alcance_prompts,
    guardar_config,
    normalizar_ai_studio_config,
    normalizar_ejecutar_hasta_prompt,
    normalizar_tts_config,
    obtener_cortes_validos_prueba,
    obtener_whisperx_config_default,
)
from database import (
    agregar_canal_db,
    eliminar_canal_db,
    init_db,
    obtener_canales_db,
)
from youtube_analyzer import (
    analizar_rendimiento_canal,
    obtener_siguiente_num,
    obtener_ultimo_video,
)
from tts_nvidia import (
    sintetizar_script_a_audio_nvidia,
    transcribir_audio_whisperx,
)
import ws_bridge
from ws_bridge import (
    abrir_ai_studio_con_prompt,
    construir_prompt_ai_studio,
    reset_pending_journey_chain,
    send_image_prompts_to_extension,
    send_ws_msg,
    set_pending_journey_chain,
)


# --- 4. INTERFAZ FLET ---
def main(page: ft.Page):
    page.title = "Clusiv Automation Hub"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#F0F2F6"
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    init_db()
    config_actual = cargar_toda_config()
    ruta_base = [config_actual["ruta_proyectos"]]
    prompts_lista = config_actual["prompts"]
    ejecutar_hasta_prompt = [
        normalizar_ejecutar_hasta_prompt(
            config_actual.get("ejecutar_hasta_prompt"),
            prompts_lista,
        )
    ]
    tts_config = normalizar_tts_config(config_actual.get("tts"))
    whisperx_config = config_actual.get("whisperx", obtener_whisperx_config_default())
    ai_studio_config = normalizar_ai_studio_config(
        config_actual.get("ai_studio"),
        config_actual.get("prompt_ai_studio"),
    )
    config_actual["ejecutar_hasta_prompt"] = ejecutar_hasta_prompt[0]
    config_actual["ai_studio"] = dict(ai_studio_config)
    config_actual["prompt_ai_studio"] = ai_studio_config["prompt"]

    ref_image_paths_state = []

    # Señal de cancelación para detener el flujo
    stop_event = threading.Event()

    # UI Elements
    input_id = ft.TextField(label="ID del Canal", expand=True)
    input_name = ft.TextField(label="Nombre del Canal", expand=True)
    lista_canales_ui = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, height=400)
    log_ui = ft.Column(
        spacing=6,
        scroll=ft.ScrollMode.AUTO,
        auto_scroll=True,
    )
    log_container = ft.Container(
        content=log_ui,
        height=350,
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

        # Determinar color de fondo del bubble según tipo de mensaje
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

        # Limitar mensajes para rendimiento (los más antiguos se eliminan)
        MAX_LOG_MESSAGES = 150
        if len(log_ui.controls) > MAX_LOG_MESSAGES:
            log_ui.controls = log_ui.controls[-MAX_LOG_MESSAGES:]

        page.update()

    ws_bridge.ui_log_cb = log_msg

    image_status_ref = [None]

    def actualizar_estado_imagen(texto, color=ft.Colors.GREY_500):
        status_control = image_status_ref[0]
        if status_control is None:
            return
        status_control.value = texto
        status_control.color = color
        page.update()

    ws_bridge.ui_image_status_cb = actualizar_estado_imagen

    prg = ft.ProgressBar(width=400, visible=False, color=ft.Colors.GREEN_700)
    txt_proximo = ft.Text(size=14, weight="bold", color=ft.Colors.BLUE_GREY_700)

    # Botón de detener flujo y referencia mutable del botón ejecutar
    btn_ejecutar_ref = [
        None
    ]  # Se asignará más adelante (lista mutable para referencia)
    btn_detener = ft.ElevatedButton(
        "DETENER FLUJO",
        icon=ft.Icons.STOP_CIRCLE,
        bgcolor=ft.Colors.RED_700,
        color="white",
        height=50,
        width=1000,
        visible=False,
        on_click=lambda _: detener_flujo(),
    )

    def detener_flujo():
        stop_event.set()
        btn_detener.disabled = True
        btn_detener.text = "DETENIENDO..."
        btn_detener.bgcolor = ft.Colors.GREY_500
        log_msg(
            "⛔ Solicitud de detención enviada. Esperando que el paso actual finalice...",
            color=ft.Colors.ORANGE_800,
            weight="bold",
            italic=True,
        )
        page.update()

    def set_estado_ejecutando(ejecutando):
        """Alterna visibilidad/estado de los botones ejecutar/detener."""
        if btn_ejecutar_ref[0]:
            btn_ejecutar_ref[0].disabled = ejecutando
            btn_ejecutar_ref[0].bgcolor = (
                ft.Colors.GREY_500 if ejecutando else ft.Colors.GREEN_700
            )
        btn_detener.visible = ejecutando
        btn_detener.disabled = False
        btn_detener.text = "DETENER FLUJO"
        btn_detener.bgcolor = ft.Colors.RED_700
        page.update()

    # Prompt Manager UI container — Gallery grid
    prompts_ui = ft.ResponsiveRow(spacing=10, run_spacing=10)
    txt_alcance_flujo = ft.Text(size=12, color=ft.Colors.BLUE_GREY_600, italic=True)
    txt_alcance_selector = ft.Text(
        size=11,
        color=ft.Colors.GREY_600,
        italic=True,
    )

    def show_snack(msg, color=ft.Colors.GREEN):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), bgcolor=color))
        page.overlay[-1].open = True
        page.update()

    # --- PROMPT MANAGER ---
    def obtener_pipeline_visual(p):
        """Genera el pipeline visual de un prompt."""
        icono_modo = (
            "🆕 Nueva ventana" if p.get("modo") == "nueva" else "📌 Ventana activa"
        )
        espera = p.get("espera_segundos", 30)
        accion = p.get("post_accion", "solo_enviar")
        archivo = p.get("archivo_salida", "")
        antibot = p.get("antibot", False)
        wpm = p.get("wpm_escritura", 45)

        partes = []
        if antibot:
            partes.append(f"🛡️ Anti-Bot ({wpm} WPM)")
        partes.extend([f"📤 Enviar ({icono_modo})", f"⏳ {espera}s"])

        if accion == "extraer_titulo":
            partes.append("📥 Extraer [FINAL_TITLE]")
            if archivo:
                partes.append(f"💾 {archivo}")
        elif accion == "guardar_respuesta":
            partes.append("📥 Extraer respuesta")
            if archivo:
                partes.append(f"💾 {archivo}")
        else:
            partes.append("(solo enviar)")

        return " → ".join(partes)

    def crear_badge(texto, color_texto, color_fondo, color_borde):
        """Crea un badge/chip compacto para las tarjetas de galería."""
        return ft.Container(
            content=ft.Text(
                texto, size=10, color=color_texto, weight=ft.FontWeight.W_500
            ),
            bgcolor=color_fondo,
            border=ft.border.all(1, color_borde),
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=8, vertical=3),
        )

    def guardar_prompts():
        """Guarda la lista de prompts en el config."""
        ejecutar_hasta_prompt[0] = normalizar_ejecutar_hasta_prompt(
            ejecutar_hasta_prompt[0],
            prompts_lista,
        )
        config_actual["ejecutar_hasta_prompt"] = ejecutar_hasta_prompt[0]
        guardar_config(
            prompts=prompts_lista,
            ejecutar_hasta_prompt=ejecutar_hasta_prompt[0],
        )
        actualizar_selector_ejecucion()
        actualizar_resumen_alcance()

    def guardar_tts():
        guardar_config(tts=tts_config)

    def obtener_prompts_para_ejecucion():
        limite = normalizar_ejecutar_hasta_prompt(ejecutar_hasta_prompt[0], prompts_lista)
        ejecutar_hasta_prompt[0] = limite
        config_actual["ejecutar_hasta_prompt"] = limite
        if limite == 0:
            return list(prompts_lista), len(prompts_lista)
        return list(prompts_lista[:limite]), limite

    def actualizar_resumen_alcance():
        descripcion = describir_alcance_prompts(prompts_lista, ejecutar_hasta_prompt[0])
        txt_alcance_flujo.value = f"Alcance actual: {descripcion}"
        txt_alcance_selector.value = (
            "La prueba siempre corre desde el prompt 1 y solo permite cortes en prompts de teleprompter."
        )
        if btn_ejecutar_ref[0]:
            limite = normalizar_ejecutar_hasta_prompt(ejecutar_hasta_prompt[0], prompts_lista)
            if limite == 0:
                btn_ejecutar_ref[0].text = "EJECUTAR FLUJO COMPLETO"
            else:
                btn_ejecutar_ref[0].text = f"EJECUTAR FLUJO 1-{limite}"

    def actualizar_selector_ejecucion():
        total = len(prompts_lista)
        valor_actual = normalizar_ejecutar_hasta_prompt(
            ejecutar_hasta_prompt[0],
            prompts_lista,
        )
        ejecutar_hasta_prompt[0] = valor_actual
        config_actual["ejecutar_hasta_prompt"] = valor_actual

        opciones = [
            ft.dropdown.Option(
                "0",
                f"Flujo completo (1-{total})" if total else "Flujo completo",
            )
        ]
        for corte in obtener_cortes_validos_prueba(prompts_lista):
            if corte >= total:
                continue
            nombre = prompts_lista[corte - 1].get("nombre", f"Prompt {corte}")
            opciones.append(
                ft.dropdown.Option(str(corte), f"Prueba 1-{corte} · {nombre}")
            )

        dropdown_ejecutar_hasta.options = opciones
        dropdown_ejecutar_hasta.value = str(valor_actual)

    def persistir_alcance_ejecucion(mostrar_snack=False):
        ejecutar_hasta_prompt[0] = normalizar_ejecutar_hasta_prompt(
            dropdown_ejecutar_hasta.value,
            prompts_lista,
        )
        config_actual["ejecutar_hasta_prompt"] = ejecutar_hasta_prompt[0]
        guardar_config(ejecutar_hasta_prompt=ejecutar_hasta_prompt[0])
        actualizar_selector_ejecucion()
        actualizar_resumen_alcance()
        if mostrar_snack:
            show_snack("Alcance de prueba guardado", ft.Colors.GREEN)
        page.update()

    def refrescar_prompts():
        """Reconstruye la UI del prompt manager en formato galería."""
        prompts_ui.controls.clear()
        txt_prompt_count.value = f"{len(prompts_lista)} prompts"
        for idx, p in enumerate(prompts_lista):
            nombre = p.get("nombre", f"Prompt {idx + 1}")
            habilitado = p.get("habilitado", True)
            antibot = p.get("antibot", False)
            wpm = p.get("wpm_escritura", 45)
            modo = p.get("modo", "nueva")
            espera = p.get("espera_segundos", 30)
            accion = p.get("post_accion", "solo_enviar")
            archivo = p.get("archivo_salida", "")

            # — Construir badges del pipeline —
            badges = []
            if antibot:
                if wpm >= 301:
                    tier_icon = "⚡"
                elif wpm >= 121:
                    tier_icon = "🏃"
                elif wpm >= 51:
                    tier_icon = "🚶"
                else:
                    tier_icon = "🐢"
                badges.append(
                    crear_badge(
                        f"🛡️ {wpm} WPM {tier_icon}",
                        ft.Colors.TEAL_800,
                        ft.Colors.TEAL_50,
                        ft.Colors.TEAL_200,
                    )
                )

            modo_txt = "🆕 Nueva" if modo == "nueva" else "📌 Activa"
            badges.append(
                crear_badge(
                    modo_txt, ft.Colors.BLUE_800, ft.Colors.BLUE_50, ft.Colors.BLUE_200
                )
            )
            badges.append(
                crear_badge(
                    f"⏳ {espera}s",
                    ft.Colors.ORANGE_800,
                    ft.Colors.ORANGE_50,
                    ft.Colors.ORANGE_200,
                )
            )

            if accion == "extraer_titulo":
                badges.append(
                    crear_badge(
                        "📥 Título",
                        ft.Colors.PURPLE_800,
                        ft.Colors.PURPLE_50,
                        ft.Colors.PURPLE_200,
                    )
                )
            elif accion == "guardar_respuesta":
                badges.append(
                    crear_badge(
                        "📥 Respuesta",
                        ft.Colors.PURPLE_800,
                        ft.Colors.PURPLE_50,
                        ft.Colors.PURPLE_200,
                    )
                )

            # — Fila de archivo de salida (condicional) —
            archivo_row = []
            if archivo:
                archivo_row.append(
                    ft.Text(
                        f"💾 {archivo}",
                        size=10,
                        color=ft.Colors.GREY_600,
                        italic=True,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    )
                )

            # — Número de orden —
            orden_badge = ft.Container(
                content=ft.Text(
                    f"#{idx + 1}",
                    size=10,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.WHITE,
                ),
                bgcolor=ft.Colors.BLUE_GREY_400 if habilitado else ft.Colors.GREY_400,
                border_radius=12,
                width=26,
                height=26,
                alignment=ft.alignment.center,
            )

            # — Colores según estado —
            borde_color = ft.Colors.GREEN_400 if habilitado else ft.Colors.GREY_300
            fondo_color = ft.Colors.WHITE if habilitado else ft.Colors.GREY_100
            nombre_color = ft.Colors.BLACK if habilitado else ft.Colors.GREY_500

            # — Tarjeta compacta de galería —
            card = ft.Container(
                col={"xs": 12, "sm": 6, "md": 4},
                content=ft.Column(
                    [
                        # Fila 1: Orden + Switch + Nombre
                        ft.Row(
                            [
                                orden_badge,
                                ft.Switch(
                                    value=habilitado,
                                    active_color=ft.Colors.GREEN_600,
                                    on_change=lambda e, i=idx: toggle_prompt(
                                        i, e.control.value
                                    ),
                                    scale=0.8,
                                ),
                                ft.Text(
                                    nombre,
                                    weight=ft.FontWeight.BOLD,
                                    size=13,
                                    expand=True,
                                    color=nombre_color,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        # Fila 2: Badges del pipeline
                        ft.Row(badges, wrap=True, spacing=4, run_spacing=4),
                        # Fila 3: Archivo de salida (si existe)
                        *archivo_row,
                        # Fila 4: Botones de acción
                        ft.Row(
                            [
                                ft.IconButton(
                                    ft.Icons.EDIT_NOTE,
                                    icon_color=ft.Colors.BLUE_600,
                                    tooltip="Editar",
                                    icon_size=18,
                                    on_click=lambda _, i=idx: abrir_editor_prompt(i),
                                    style=ft.ButtonStyle(padding=ft.padding.all(4)),
                                ),
                                ft.IconButton(
                                    ft.Icons.ARROW_UPWARD,
                                    icon_color=ft.Colors.GREY_600,
                                    tooltip="Subir",
                                    icon_size=18,
                                    on_click=lambda _, i=idx: mover_prompt(i, -1),
                                    disabled=(idx == 0),
                                    style=ft.ButtonStyle(padding=ft.padding.all(4)),
                                ),
                                ft.IconButton(
                                    ft.Icons.ARROW_DOWNWARD,
                                    icon_color=ft.Colors.GREY_600,
                                    tooltip="Bajar",
                                    icon_size=18,
                                    on_click=lambda _, i=idx: mover_prompt(i, 1),
                                    disabled=(idx == len(prompts_lista) - 1),
                                    style=ft.ButtonStyle(padding=ft.padding.all(4)),
                                ),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE,
                                    icon_color=ft.Colors.RED_400,
                                    tooltip="Eliminar",
                                    icon_size=18,
                                    on_click=lambda _, i=idx: eliminar_prompt(i),
                                    style=ft.ButtonStyle(padding=ft.padding.all(4)),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.END,
                            spacing=0,
                        ),
                    ],
                    spacing=8,
                    tight=True,
                ),
                padding=14,
                border_radius=10,
                border=ft.border.all(1.5, borde_color),
                bgcolor=fondo_color,
                shadow=ft.BoxShadow(
                    spread_radius=0,
                    blur_radius=4,
                    color=ft.Colors.with_opacity(0.06, ft.Colors.BLACK),
                    offset=ft.Offset(0, 2),
                ),
            )
            prompts_ui.controls.append(card)
        page.update()

    def toggle_prompt(idx, valor):
        prompts_lista[idx]["habilitado"] = valor
        guardar_prompts()
        refrescar_prompts()

    def deshabilitar_todos_prompts(e=None):
        for prompt in prompts_lista:
            prompt["habilitado"] = False
        guardar_prompts()
        refrescar_prompts()
        show_snack("Todos los prompts fueron desactivados", ft.Colors.ORANGE)

    def habilitar_todos_prompts(e=None):
        for prompt in prompts_lista:
            prompt["habilitado"] = True
        guardar_prompts()
        refrescar_prompts()
        show_snack("Todos los prompts fueron activados", ft.Colors.GREEN)

    def mover_prompt(idx, direccion):
        nuevo_idx = idx + direccion
        if 0 <= nuevo_idx < len(prompts_lista):
            prompts_lista[idx], prompts_lista[nuevo_idx] = (
                prompts_lista[nuevo_idx],
                prompts_lista[idx],
            )
            guardar_prompts()
            refrescar_prompts()

    def eliminar_prompt(idx):
        prompts_lista.pop(idx)
        guardar_prompts()
        refrescar_prompts()
        show_snack("Prompt eliminado", ft.Colors.ORANGE)

    def agregar_prompt_nuevo(e):
        """Agrega un nuevo prompt vacío y abre el editor."""
        nuevo = {
            "nombre": f"Nuevo Prompt {len(prompts_lista) + 1}",
            "texto": "",
            "modo": "nueva",
            "espera_segundos": 30,
            "habilitado": True,
            "antibot": True,
            "wpm_escritura": 200,
            "post_accion": "solo_enviar",
            "archivo_salida": "",
        }
        prompts_lista.append(nuevo)
        guardar_prompts()
        refrescar_prompts()
        show_snack("Prompt agregado ✅", ft.Colors.GREEN)
        # Abrir editor del nuevo prompt
        abrir_editor_prompt(len(prompts_lista) - 1)

    def abrir_editor_prompt(idx):
        """Abre un diálogo para editar un prompt."""
        p = prompts_lista[idx]

        f_nombre = ft.TextField(label="Nombre", value=p.get("nombre", ""), dense=True)
        f_texto = ft.TextField(
            label="Texto del prompt (usa [REF_TITLE] o [TITULO])",
            value=p.get("texto", ""),
            multiline=True,
            min_lines=6,
            max_lines=12,
            text_size=12,
        )
        f_modo = ft.Dropdown(
            label="Modo de ventana",
            value=p.get("modo", "nueva"),
            options=[
                ft.dropdown.Option("nueva", "🆕 Nueva ventana"),
                ft.dropdown.Option("activa", "📌 Ventana activa"),
            ],
            dense=True,
            width=250,
        )
        f_espera = ft.TextField(
            label="Espera (segundos)",
            value=str(p.get("espera_segundos", 30)),
            width=150,
            dense=True,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        f_post_accion = ft.Dropdown(
            label="Post-Acción",
            value=p.get("post_accion", "solo_enviar"),
            options=[
                ft.dropdown.Option("extraer_titulo", "📥 Extraer [FINAL_TITLE]"),
                ft.dropdown.Option(
                    "guardar_respuesta", "📥 Guardar respuesta completa"
                ),
                ft.dropdown.Option("solo_enviar", "📤 Solo enviar"),
            ],
            dense=True,
            width=300,
        )
        f_archivo = ft.TextField(
            label="Archivo de salida",
            value=p.get("archivo_salida", ""),
            dense=True,
            width=300,
        )

        # --- Anti-Bot Controls ---
        f_antibot = ft.Switch(
            label="🛡️ Anti-Bot (Escritura humanizada, pausas aleatorias, scroll)",
            value=p.get("antibot", True),
            active_color=ft.Colors.TEAL_600,
        )

        wpm_value = p.get("wpm_escritura", 200)

        def get_tier_label(val):
            if val >= 301:
                return f"{val} WPM ⚡ Turbo"
            elif val >= 121:
                return f"{val} WPM 🏃 Rápido"
            elif val >= 51:
                return f"{val} WPM 🚶 Palabra"
            else:
                return f"{val} WPM 🐢 Stealth"

        f_wpm_label = ft.Text(
            get_tier_label(wpm_value), size=13, weight="bold", color=ft.Colors.TEAL_700
        )

        def on_wpm_change(e):
            val = int(e.control.value)
            f_wpm_label.value = get_tier_label(val)
            page.update()

        f_wpm_slider = ft.Slider(
            min=20,
            max=500,
            divisions=48,
            value=wpm_value,
            label="{value} WPM",
            active_color=ft.Colors.TEAL_600,
            on_change=on_wpm_change,
            expand=True,
        )

        antibot_section = ft.Container(
            content=ft.Column(
                [
                    f_antibot,
                    ft.Row(
                        [
                            ft.Text(
                                "Velocidad de escritura:",
                                size=12,
                                color=ft.Colors.GREY_700,
                            ),
                            f_wpm_slider,
                            f_wpm_label,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        "🐢 20 ← Stealth | 51 → Palabra 🚶 | 121 → Rápido 🏃 | 301 → Turbo ⚡ → 500",
                        size=10,
                        color=ft.Colors.GREY_500,
                        italic=True,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                spacing=4,
            ),
            padding=ft.padding.all(10),
            border=ft.border.all(1, ft.Colors.TEAL_200),
            border_radius=8,
            bgcolor=ft.Colors.TEAL_50,
        )

        def cerrar_editor(e):
            dlg.open = False
            page.update()

        def guardar_editor(e):
            prompts_lista[idx]["nombre"] = f_nombre.value
            prompts_lista[idx]["texto"] = f_texto.value
            prompts_lista[idx]["modo"] = f_modo.value
            try:
                prompts_lista[idx]["espera_segundos"] = int(f_espera.value)
            except ValueError:
                prompts_lista[idx]["espera_segundos"] = 30
            prompts_lista[idx]["post_accion"] = f_post_accion.value
            prompts_lista[idx]["archivo_salida"] = f_archivo.value
            prompts_lista[idx]["antibot"] = f_antibot.value
            prompts_lista[idx]["wpm_escritura"] = int(f_wpm_slider.value)
            guardar_prompts()
            refrescar_prompts()
            dlg.open = False
            page.update()
            show_snack(f"Prompt '{f_nombre.value}' guardado ✅")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Editar Prompt: {p.get('nombre', '')}"),
            content=ft.Container(
                width=550,
                content=ft.Column(
                    [
                        f_nombre,
                        f_texto,
                        ft.Row([f_modo, f_espera]),
                        ft.Row([f_post_accion, f_archivo]),
                        ft.Divider(),
                        antibot_section,
                    ],
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                    height=520,
                ),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=cerrar_editor),
                ft.ElevatedButton(
                    "Guardar",
                    on_click=guardar_editor,
                    bgcolor=ft.Colors.GREEN_700,
                    color="white",
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    # --- CANALES ---
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

    # --- AUTOMATIZACIÓN DE CHATGPT ---
    def abrir_y_pegar_chatgpt(prompt_final, modo="nueva", antibot=False, wpm=45):
        if stop_event.is_set():
            return False

        if modo == "nueva":
            if os.path.exists(PATH_CHATGPT):
                os.startfile(PATH_CHATGPT)
            else:
                webbrowser.open("https://chatgpt.com")

        ventana_encontrada = None
        for _ in range(15):
            if stop_event.is_set():
                return False
            if antibot:
                if not espera_humanizada(1, stop_event):
                    return False
            else:
                if not sleep_cancelable(1, stop_event):
                    return False
            windows = [w for w in gw.getAllWindows() if "ChatGPT" in w.title]
            if windows:
                ventana_encontrada = windows[0]
                break

        if ventana_encontrada:
            try:
                if stop_event.is_set():
                    return False
                ventana_encontrada.activate()
                if antibot:
                    if not espera_humanizada(2, stop_event):
                        return False
                else:
                    if not sleep_cancelable(2, stop_event):
                        return False

                if stop_event.is_set():
                    return False

                if antibot:
                    resultado = escribir_humanizado(
                        prompt_final, wpm=wpm, stop_event=stop_event
                    )
                    if not resultado:
                        return False
                    if not espera_humanizada(0.5, stop_event):
                        return False
                    pyautogui.press("enter")
                else:
                    pyperclip.copy(prompt_final)
                    pyautogui.hotkey("ctrl", "v")
                    if not sleep_cancelable(0.5, stop_event):
                        return False
                    pyautogui.press("enter")
                return True
            except:
                pass
        return False

    def extraer_solo_el_titulo(texto_completo):
        """Usa Regex para extraer el contenido de [FINAL_TITLE: ...] evitando el prompt"""
        patron = r"\[FINAL_TITLE:\s*(.*?)\]"
        matches = re.findall(patron, texto_completo, re.IGNORECASE | re.DOTALL)
        titulos_reales = [
            m.strip() for m in matches if "Put the generated title here" not in m
        ]
        if titulos_reales:
            return titulos_reales[-1]
        return None

    def limpiar_script_extraido(texto):
        """Limpia artefactos del script extraído de all_text.txt.

        Corrige dos problemas:
        1. Elimina líneas de instrucción del prompt al inicio del bloque
           (ej: 'Your full script here', 'Do not write anything after').
        2. Detecta y elimina bloques duplicados concatenados al final
           (generados por Ctrl+A en ChatGPT que captura DOM duplicado).
        """
        if not texto:
            return texto

        # === FIX BUG 1: Eliminar frases de instrucción al inicio ===
        frases_instruccion = [
            "your full script here",
            "do not write anything after",
            "do not write anything before",
            "put your full script here",
            "insert your script here",
            "write your script here",
            "paste your script here",
        ]

        lineas = texto.split("\n")

        # Recorrer desde el inicio y eliminar líneas vacías o que coincidan
        while lineas:
            linea_limpia = lineas[0].strip()
            # Saltar líneas vacías al inicio
            if not linea_limpia:
                lineas.pop(0)
                continue
            # Verificar si la línea contiene alguna frase de instrucción
            linea_lower = linea_limpia.lower()
            es_instruccion = any(frase in linea_lower for frase in frases_instruccion)
            if es_instruccion:
                lineas.pop(0)
                continue
            # Si no es vacía ni instrucción, dejar de recortar
            break

        texto = "\n".join(lineas).strip()

        # === FIX BUG 2: Eliminar bloque duplicado al final ===
        # Estrategia: detectar si la última "línea" es anormalmente larga
        # y contiene palabras que ya aparecieron en el texto anterior,
        # lo que indica que es una repetición concatenada sin saltos de línea.
        lineas = texto.split("\n")

        if len(lineas) >= 3:
            ultima_linea = lineas[-1].strip()
            texto_sin_ultima = "\n".join(lineas[:-1])

            # Solo actuar si la última línea es sospechosamente larga
            if len(ultima_linea) > 300:
                # Tomar una muestra de palabras del bloque sospechoso
                palabras_muestra = ultima_linea.split()[:50]
                if len(palabras_muestra) >= 10:
                    # Contar cuántas de esas palabras aparecen en el texto anterior
                    texto_anterior_lower = texto_sin_ultima.lower()
                    coincidencias = sum(
                        1 for p in palabras_muestra if p.lower() in texto_anterior_lower
                    )
                    ratio = coincidencias / len(palabras_muestra)

                    # Si más del 60% de las palabras coinciden, es duplicado
                    if ratio > 0.6:
                        texto = texto_sin_ultima.strip()

        # === FALLBACK: Detección por substring directo ===
        # Si el final del texto (últimos N chars) aparece textualmente
        # antes en el texto, es un duplicado pegado.
        longitud = len(texto)
        if longitud > 600:
            # Probar con un fragmento del final
            tamano_prueba = min(200, longitud // 4)
            cola = texto[-tamano_prueba:]
            # Buscar si ese fragmento exacto aparece antes en el texto
            pos_primera = texto.find(cola)
            pos_ultima = longitud - tamano_prueba
            if pos_primera != -1 and pos_primera < pos_ultima - tamano_prueba:
                # El fragmento aparece antes → truncar en donde termina
                # la primera aparición del contenido duplicado
                # Buscar el punto de corte: dónde empieza la repetición
                # Recorremos hacia atrás desde pos_ultima para encontrar
                # el inicio real del bloque duplicado
                for corte in range(pos_ultima, max(pos_ultima - 500, 0), -1):
                    fragmento = texto[corte : corte + 100]
                    buscar_en = texto[:corte]
                    if fragmento in buscar_en:
                        texto = texto[:corte].rstrip()
                        break

        return texto.strip()

    def remover_enlaces_parentesis(texto):
        """Remueve del texto todos los enlaces web entre paréntesis.

        Detecta patrones como:
          (reuters.com)
          (https://www.nytimes.com/article/something)
          (bbc.com)
          ( ft.com )

        Y los elimina del texto, limpiando también espacios dobles residuales.
        """
        if not texto:
            return texto

        # Patrón: paréntesis conteniendo un dominio web (con o sin protocolo/path)
        patron_enlace = (
            r'\s*\(\s*(?:https?://)?(?:www\.)?[\w.-]+\.\w{2,}(?:/[^\)]*?)?\s*\)'
        )

        texto_limpio = re.sub(patron_enlace, '', texto)

        # Limpiar espacios dobles residuales que puedan quedar
        texto_limpio = re.sub(r'  +', ' ', texto_limpio)

        # Limpiar líneas que quedaron vacías o solo con espacios
        lineas = texto_limpio.split('\n')
        lineas_limpias = []
        for linea in lineas:
            linea_stripped = linea.strip()
            # Mantener líneas vacías intencionales (separadores de párrafo)
            # pero eliminar líneas que solo tenían un enlace
            if linea_stripped or linea == '':
                lineas_limpias.append(linea.rstrip())

        return '\n'.join(lineas_limpias).strip()

    def extraer_script_de_all_text(carpeta_proyecto):
        """Lee all_text.txt, extrae el contenido entre las etiquetas
        <<<START_TELEPROMPTER_SCRIPT>>> y <<<END_TELEPROMPTER_SCRIPT>>>,
        limpia artefactos (instrucciones del prompt y duplicados),
        y lo guarda en script.txt en la misma carpeta.
        El archivo all_text.txt permanece intacto."""

        ruta_all_text = os.path.join(carpeta_proyecto, "all_text.txt")
        ruta_script = os.path.join(carpeta_proyecto, "script.txt")

        if not os.path.exists(ruta_all_text):
            return False, "all_text.txt no encontrado en la carpeta del proyecto."

        with open(ruta_all_text, "r", encoding="utf-8") as f:
            contenido = f.read()

        patron = r"<<<START_TELEPROMPTER_SCRIPT>>>(.*?)<<<END_TELEPROMPTER_SCRIPT>>>"
        matches = re.findall(patron, contenido, re.DOTALL)

        if not matches:
            return (
                False,
                "No se encontraron etiquetas <<<START_TELEPROMPTER_SCRIPT>>> en all_text.txt.",
            )

        # Limpiar cada bloque individualmente antes de unirlos
        bloques_limpios = []
        for bloque in matches:
            bloque_limpio = limpiar_script_extraido(bloque.strip())
            if bloque_limpio:  # Solo agregar bloques que tengan contenido después de limpiar
                bloques_limpios.append(bloque_limpio)

        if not bloques_limpios:
            return (
                False,
                "Los bloques extraídos quedaron vacíos después de la limpieza.",
            )

        texto_extraido = "\n\n".join(bloques_limpios)

        # Limpieza adicional: remover enlaces web entre paréntesis ej: (reuters.com)
        texto_extraido = remover_enlaces_parentesis(texto_extraido)

        with open(ruta_script, "w", encoding="utf-8") as f:
            f.write(texto_extraido)

        return (
            True,
            f"script.txt creado exitosamente ({len(bloques_limpios)} bloque(s) extraído(s), limpieza aplicada).",
        )

    def obtener_primera_ventana_por_titulos(titulos_objetivo):
        titulos_normalizados = [t.lower() for t in titulos_objetivo if t]
        for ventana in gw.getAllWindows():
            titulo = (ventana.title or "").strip().lower()
            if titulo and any(objetivo in titulo for objetivo in titulos_normalizados):
                return ventana
        return None

    def copiar_texto_desde_ventana(titulos_objetivo, antibot=False):
        try:
            if stop_event.is_set():
                return None

            ventana = obtener_primera_ventana_por_titulos(titulos_objetivo)
            if not ventana:
                return None

            if hasattr(ventana, "isMinimized") and ventana.isMinimized:
                ventana.restore()
            ventana.activate()
            if antibot:
                if not espera_humanizada(1.5, stop_event):
                    return None
            else:
                if not sleep_cancelable(1.5, stop_event):
                    return None

            if stop_event.is_set():
                return None

            if antibot:
                scroll_simulado(stop_event)

            if stop_event.is_set():
                return None

            ancho, alto = ventana.size
            centro_x = ventana.left + (ancho // 2)
            centro_y = ventana.top + (alto // 2)
            pyautogui.click(centro_x, centro_y)
            if antibot:
                if not espera_humanizada(0.5, stop_event):
                    return None
            else:
                if not sleep_cancelable(0.5, stop_event):
                    return None

            pyautogui.hotkey("ctrl", "a")
            if antibot:
                if not espera_humanizada(0.5, stop_event):
                    return None
            else:
                if not sleep_cancelable(0.5, stop_event):
                    return None
            pyautogui.hotkey("ctrl", "c")
            if antibot:
                if not espera_humanizada(1.5, stop_event):
                    return None
            else:
                if not sleep_cancelable(1.5, stop_event):
                    return None

            return pyperclip.paste()
        except:
            return None

    def extraer_respuesta_automatica(antibot=False):
        return copiar_texto_desde_ventana(("ChatGPT",), antibot=antibot)

    def extraer_respuesta_ai_studio(antibot=False):
        return copiar_texto_desde_ventana(AI_STUDIO_WINDOW_TITLES, antibot=antibot)

    def es_prompt_teleprompter(prompt):
        nombre = str(prompt.get("nombre", "")).strip().lower()
        return "teleprompter" in nombre

    def construir_nombre_snapshot_teleprompter(indice_prompt, prompt):
        nombre = str(prompt.get("nombre", f"prompt_{indice_prompt}")).strip().lower()
        nombre = re.sub(r"[^a-z0-9]+", "_", nombre).strip("_")
        if not nombre:
            nombre = f"prompt_{indice_prompt}"
        return f"teleprompter_snapshot_{indice_prompt:02d}_{nombre}.txt"

    def guardar_snapshot_teleprompter(carpeta_proyecto, indice_prompt, prompt, contenido):
        nombre_archivo = construir_nombre_snapshot_teleprompter(indice_prompt, prompt)
        ruta_archivo = os.path.join(carpeta_proyecto, nombre_archivo)
        with open(ruta_archivo, "w", encoding="utf-8") as f:
            f.write(contenido)
        return ruta_archivo

    def extraer_bloques_teleprompter(texto):
        if not texto:
            return []

        patron = r"<<<START_TELEPROMPTER_SCRIPT>>>(.*?)<<<END_TELEPROMPTER_SCRIPT>>>"
        return [
            bloque.strip()
            for bloque in re.findall(patron, texto, re.DOTALL)
            if bloque and bloque.strip()
        ]

    def reconstruir_all_text_desde_teleprompters(carpeta_proyecto, prompts_ejecutados):
        rutas_fuente = []
        for indice_prompt, prompt in enumerate(prompts_ejecutados, start=1):
            if not es_prompt_teleprompter(prompt):
                continue

            archivo_salida = str(prompt.get("archivo_salida", "")).strip()
            if archivo_salida:
                rutas_fuente.append(os.path.join(carpeta_proyecto, archivo_salida))
                continue

            rutas_fuente.append(
                os.path.join(
                    carpeta_proyecto,
                    construir_nombre_snapshot_teleprompter(indice_prompt, prompt),
                )
            )

        if not rutas_fuente:
            return False, "No hay prompts teleprompter disponibles para reconstruir all_text.txt."

        bloques = []
        bloques_vistos = set()
        archivos_usados = 0

        for ruta_fuente in rutas_fuente:
            if not os.path.exists(ruta_fuente):
                continue

            with open(ruta_fuente, "r", encoding="utf-8") as f:
                contenido = f.read()

            bloques_archivo = extraer_bloques_teleprompter(contenido)
            if not bloques_archivo:
                continue

            archivos_usados += 1
            for bloque in bloques_archivo:
                if bloque in bloques_vistos:
                    continue
                bloques_vistos.add(bloque)
                bloques.append(bloque)

        if not bloques:
            return (
                False,
                "No se encontraron bloques teleprompter reutilizables para reconstruir all_text.txt.",
            )

        ruta_all_text = os.path.join(carpeta_proyecto, "all_text.txt")
        contenido_all_text = "\n\n".join(
            f"<<<START_TELEPROMPTER_SCRIPT>>>\n{bloque}\n<<<END_TELEPROMPTER_SCRIPT>>>"
            for bloque in bloques
        )

        with open(ruta_all_text, "w", encoding="utf-8") as f:
            f.write(contenido_all_text)

        return (
            True,
            f"all_text.txt reconstruido con {len(bloques)} bloque(s) desde {archivos_usados} archivo(s) teleprompter.",
        )

    def extraer_prompts_ai_studio(texto_completo):
        if not texto_completo:
            return []

        matches = re.findall(
            r"<prompt>\s*(.*?)\s*</prompt>",
            texto_completo,
            re.IGNORECASE | re.DOTALL,
        )
        return [match.strip() for match in matches if match and match.strip()]

    def guardar_prompts_ai_studio(carpeta_proyecto, prompts_extraidos, archivo_salida=None):
        nombre_archivo = str(archivo_salida or AI_STUDIO_OUTPUT_FILENAME_DEFAULT).strip()
        if not nombre_archivo:
            nombre_archivo = AI_STUDIO_OUTPUT_FILENAME_DEFAULT
        if not nombre_archivo.lower().endswith(".txt"):
            nombre_archivo = f"{nombre_archivo}.txt"

        ruta_archivo = os.path.join(carpeta_proyecto, nombre_archivo)
        with open(ruta_archivo, "w", encoding="utf-8") as f:
            f.write("\n\n".join(prompts_extraidos))
        return ruta_archivo

    # --- FLUJO PRINCIPAL (basado en lista de prompts) ---
    def ejecutar_flujo_completo(e):
        if not ruta_base[0]:
            show_snack("Selecciona una ruta de proyectos", ft.Colors.RED)
            return
        if not YOUTUBE_API_KEY:
            show_snack("Falta API KEY en .env", ft.Colors.RED)
            return

        prompts_a_ejecutar, _ = obtener_prompts_para_ejecucion()
        if not prompts_a_ejecutar:
            show_snack("No hay prompts configurados", ft.Colors.RED)
            return

        alcance_actual = describir_alcance_prompts(prompts_lista, ejecutar_hasta_prompt[0])

        # Limpiar señal de cancelación y preparar UI
        stop_event.clear()
        log_ui.controls.clear()
        prg.visible = True
        set_estado_ejecutando(True)
        page.update()
        log_msg("🚀 Iniciando flujo completo...", italic=True)
        log_msg(f"⚙️ Alcance configurado: {alcance_actual}", color=ft.Colors.BLUE_800)

        def proceso_hilo():
            detenido = False
            try:
                canales = obtener_canales_db()
                ganadores_totales = []

                for ch_id, ch_name, _ in canales:
                    if stop_event.is_set():
                        detenido = True
                        break
                    log_msg(f"🔍 Analizando: {ch_name}...")
                    data = analizar_rendimiento_canal(ch_id)
                    if data and data["ganadores"]:
                        v = data["ganadores"][0]
                        v["ch_name"] = ch_name
                        ganadores_totales.append(v)

                if detenido or stop_event.is_set():
                    log_msg(
                        "⛔ Flujo detenido por el usuario durante el análisis de canales.",
                        color=ft.Colors.RED_700,
                        weight="bold",
                    )
                    prg.visible = False
                    set_estado_ejecutando(False)
                    page.update()
                    return

                if not ganadores_totales:
                    log_msg(
                        "❌ No se encontraron videos ganadores.",
                        color=ft.Colors.RED,
                    )
                    prg.visible = False
                    set_estado_ejecutando(False)
                    page.update()
                    return

                mejor = max(ganadores_totales, key=lambda x: x["views"])
                titulo_ref = mejor["title"]

                num = obtener_siguiente_num(ruta_base[0])
                path = os.path.join(ruta_base[0], f"video {num}")

                os.makedirs(os.path.join(path, "assets"), exist_ok=True)
                os.makedirs(os.path.join(path, "images"), exist_ok=True)
                open(os.path.join(path, "scenes.txt"), "w", encoding="utf-8").close()
                open(
                    os.path.join(path, "scenes with duration.txt"),
                    "w",
                    encoding="utf-8",
                ).close()

                titulo_extraido = None
                all_text_esperado = any(
                    str(p.get("archivo_salida", "")).strip().lower() == "all_text.txt"
                    for p in prompts_a_ejecutar
                )

                for idx, p in enumerate(prompts_a_ejecutar):
                    if stop_event.is_set():
                        detenido = True
                        break

                    nombre_prompt = p.get("nombre", f"Prompt {idx + 1}")
                    post_accion = p.get("post_accion", "solo_enviar")
                    modo = p.get("modo", "nueva")
                    espera = p.get("espera_segundos", 30)
                    archivo_salida = p.get("archivo_salida", "")
                    ab = p.get("antibot", False)
                    wpm = p.get("wpm_escritura", 45)

                    texto_prompt = p.get("texto", "")
                    texto_prompt = texto_prompt.replace("[REF_TITLE]", titulo_ref)
                    if titulo_extraido:
                        texto_prompt = texto_prompt.replace("[TITULO]", titulo_extraido)

                    nombre_archivo_prompt = (
                        f"PROMPT_{idx + 1}_{nombre_prompt.replace(' ', '_')}.txt"
                    )
                    with open(
                        os.path.join(path, nombre_archivo_prompt), "w", encoding="utf-8"
                    ) as f:
                        f.write(texto_prompt)

                    ab_tag = " 🛡️" if ab else ""
                    log_msg(
                        f"🌐 [{idx + 1}/{len(prompts_a_ejecutar)}] Enviando: {nombre_prompt}{ab_tag}...",
                        color=ft.Colors.BLUE,
                    )

                    if stop_event.is_set():
                        detenido = True
                        break

                    envio_ok = abrir_y_pegar_chatgpt(
                        texto_prompt, modo=modo, antibot=ab, wpm=wpm
                    )

                    if stop_event.is_set():
                        detenido = True
                        break

                    if envio_ok:
                        log_msg(f"⏳ Esperando ~{espera}s generación...", italic=True)

                        if ab:
                            if not espera_humanizada(espera * 0.5, stop_event):
                                detenido = True
                                break
                            scroll_simulado(stop_event)
                            if stop_event.is_set():
                                detenido = True
                                break
                            if not espera_humanizada(espera * 0.5, stop_event):
                                detenido = True
                                break
                        else:
                            if not sleep_cancelable(espera, stop_event):
                                detenido = True
                                break

                        if stop_event.is_set():
                            detenido = True
                            break

                        # Post-acción
                        if post_accion == "extraer_titulo":
                            log_msg(
                                "📋 Extrayendo título final...",
                                color=ft.Colors.AMBER_800,
                            )
                            texto_copiado = extraer_respuesta_automatica(antibot=ab)

                            if stop_event.is_set():
                                detenido = True
                                break

                            if texto_copiado:
                                titulo_final = extraer_solo_el_titulo(texto_copiado)
                                if titulo_final:
                                    titulo_extraido = titulo_final
                                    if archivo_salida:
                                        with open(
                                            os.path.join(path, archivo_salida),
                                            "w",
                                            encoding="utf-8",
                                        ) as f:
                                            f.write(titulo_final)
                                    log_msg(
                                        f"🎯 Título detectado: {titulo_final}",
                                        color=ft.Colors.GREEN_700,
                                        weight="bold",
                                    )
                                else:
                                    with open(
                                        os.path.join(path, "RESPUESTA_RAW.txt"),
                                        "w",
                                        encoding="utf-8",
                                    ) as f:
                                        f.write(texto_copiado)
                                    log_msg(
                                        "⚠ No se encontró el título real. Se guardó Raw.",
                                        color=ft.Colors.ORANGE,
                                    )
                            else:
                                log_msg(
                                    "❌ Error: Portapapeles vacío.",
                                    color=ft.Colors.RED,
                                )

                        elif post_accion == "guardar_respuesta":
                            log_msg(
                                f"📋 Extrayendo respuesta para '{nombre_prompt}'...",
                                color=ft.Colors.AMBER_800,
                            )
                            texto_resp = extraer_respuesta_automatica(antibot=ab)

                            if stop_event.is_set():
                                detenido = True
                                break

                            if texto_resp:
                                if archivo_salida:
                                    with open(
                                        os.path.join(path, archivo_salida),
                                        "w",
                                        encoding="utf-8",
                                    ) as f:
                                        f.write(texto_resp)
                                log_msg(
                                    f"✅ Respuesta guardada: {archivo_salida}",
                                    color=ft.Colors.GREEN_700,
                                    weight="bold",
                                )
                            else:
                                log_msg(
                                    f"❌ Error al extraer respuesta de '{nombre_prompt}'.",
                                    color=ft.Colors.RED,
                                )
                        else:
                            if es_prompt_teleprompter(p):
                                log_msg(
                                    f"📋 Capturando snapshot teleprompter para '{nombre_prompt}'...",
                                    color=ft.Colors.AMBER_800,
                                )
                                texto_teleprompter = extraer_respuesta_automatica(antibot=ab)

                                if stop_event.is_set():
                                    detenido = True
                                    break

                                if texto_teleprompter:
                                    ruta_snapshot = guardar_snapshot_teleprompter(
                                        path,
                                        idx + 1,
                                        p,
                                        texto_teleprompter,
                                    )
                                    bloques_snapshot = extraer_bloques_teleprompter(
                                        texto_teleprompter
                                    )
                                    if bloques_snapshot:
                                        log_msg(
                                            f"✅ Snapshot teleprompter guardado ({len(bloques_snapshot)} bloque(s)): {os.path.basename(ruta_snapshot)}",
                                            color=ft.Colors.GREEN_700,
                                            weight="bold",
                                        )
                                    else:
                                        log_msg(
                                            f"⚠ Se guardó el snapshot teleprompter, pero no se detectaron bloques válidos todavía: {os.path.basename(ruta_snapshot)}",
                                            color=ft.Colors.ORANGE_700,
                                        )
                                else:
                                    log_msg(
                                        f"⚠ No se pudo capturar el snapshot teleprompter de '{nombre_prompt}'.",
                                        color=ft.Colors.ORANGE_700,
                                    )
                            log_msg(
                                f"✅ Prompt '{nombre_prompt}' enviado.",
                                color=ft.Colors.GREEN_700,
                            )
                    else:
                        if stop_event.is_set():
                            detenido = True
                            break
                        log_msg(
                            f"❌ Error: No se pudo enviar '{nombre_prompt}'.",
                            color=ft.Colors.RED,
                        )

                    # Pausa entre prompts
                    if idx < len(prompts_a_ejecutar) - 1:
                        if ab:
                            if not espera_humanizada(3, stop_event):
                                detenido = True
                                break
                        else:
                            if not sleep_cancelable(3, stop_event):
                                detenido = True
                                break

                # Mensaje final
                log_msg("", is_divider=True)
                if detenido or stop_event.is_set():
                    log_msg(
                        f"⛔ FLUJO DETENIDO por el usuario en video {num}",
                        color=ft.Colors.RED_700,
                        weight="bold",
                    )
                else:
                    ruta_all_text = os.path.join(path, "all_text.txt")
                    if not os.path.exists(ruta_all_text):
                        reconstruccion_ok = False
                        if not all_text_esperado:
                            reconstruccion_ok, reconstruccion_msg = reconstruir_all_text_desde_teleprompters(
                                path,
                                prompts_a_ejecutar,
                            )
                            if reconstruccion_ok:
                                log_msg(
                                    f"✅ {reconstruccion_msg}",
                                    color=ft.Colors.GREEN_700,
                                    weight="bold",
                                )
                            else:
                                log_msg(
                                    f"ℹ No se pudo reconstruir all_text.txt para el alcance parcial: {reconstruccion_msg}",
                                    color=ft.Colors.BLUE_800,
                                    italic=True,
                                )

                        if not os.path.exists(ruta_all_text) and all_text_esperado:
                            log_msg(
                                "⚠ Se omitió el postproceso final porque no se generó all_text.txt en esta corrida.",
                                color=ft.Colors.ORANGE_700,
                            )
                        elif not os.path.exists(ruta_all_text):
                            log_msg(
                                f"ℹ Se omite el postproceso final porque el alcance '{alcance_actual}' no dejó bloques teleprompter reutilizables.",
                                color=ft.Colors.BLUE_800,
                                italic=True,
                            )

                    if os.path.exists(ruta_all_text):
                        log_msg(
                            "📄 Buscando all_text.txt para extraer script...",
                            color=ft.Colors.BLUE_800,
                            italic=True,
                        )

                        exito, mensaje = extraer_script_de_all_text(path)

                        if exito:
                            log_msg(
                                f"✅ {mensaje}",
                                color=ft.Colors.GREEN_700,
                                weight="bold",
                            )

                            if tts_config.get("enabled"):
                                log_msg(
                                    "🔊 Generando audio con NVIDIA Magpie TTS...",
                                    color=ft.Colors.BLUE_800,
                                    italic=True,
                                )
                                tts_ok, tts_msg, ruta_audio = sintetizar_script_a_audio_nvidia(
                                    path,
                                    tts_config,
                                )
                                if tts_ok:
                                    log_msg(
                                        f"✅ {tts_msg}",
                                        color=ft.Colors.GREEN_700,
                                        weight="bold",
                                    )
                                    # --- WhisperX: transcripción automática ---
                                    if whisperx_config.get("enabled") and ruta_audio:
                                        log_msg(
                                            "🎙️ Iniciando transcripción con WhisperX (esto puede tardar varios minutos)...",
                                            color=ft.Colors.BLUE_800,
                                            italic=True,
                                        )
                                        wx_ok, wx_msg, ruta_json = transcribir_audio_whisperx(
                                            ruta_audio, whisperx_config
                                        )
                                        if wx_ok:
                                            log_msg(
                                                f"✅ WhisperX: {wx_msg}",
                                                color=ft.Colors.GREEN_700,
                                                weight="bold",
                                            )
                                            ai_studio_runtime = normalizar_ai_studio_config(
                                                config_actual.get("ai_studio"),
                                                config_actual.get("prompt_ai_studio"),
                                            )
                                            prompt_ai_base = ai_studio_runtime.get("prompt", "").strip()
                                            if prompt_ai_base:
                                                prompt_ai_ok, prompt_ai_msg, prompt_ai = construir_prompt_ai_studio(
                                                    prompt_ai_base,
                                                    path,
                                                )
                                                if prompt_ai_ok:
                                                    log_msg(
                                                        f"ℹ AI Studio: {prompt_ai_msg}",
                                                        color=ft.Colors.BLUE_800,
                                                        italic=True,
                                                    )
                                                    log_msg(
                                                        "🤖 Abriendo Google AI Studio con el prompt configurado...",
                                                        color=ft.Colors.BLUE_800,
                                                        italic=True,
                                                    )
                                                    ai_ok, ai_msg = abrir_ai_studio_con_prompt(prompt_ai)
                                                    if ai_ok:
                                                        log_msg(
                                                            f"✅ {ai_msg}",
                                                            color=ft.Colors.GREEN_700,
                                                            weight="bold",
                                                        )
                                                        espera_ai = ai_studio_runtime.get(
                                                            "espera_respuesta_segundos",
                                                            15,
                                                        )
                                                        log_msg(
                                                            f"⏳ Esperando {espera_ai}s para la respuesta de AI Studio...",
                                                            color=ft.Colors.BLUE_800,
                                                            italic=True,
                                                        )
                                                        if not sleep_cancelable(espera_ai, stop_event):
                                                            detenido = True
                                                        else:
                                                            log_msg(
                                                                "📋 Copiando respuesta completa desde AI Studio...",
                                                                color=ft.Colors.AMBER_800,
                                                            )
                                                            texto_ai_studio = extraer_respuesta_ai_studio(
                                                                antibot=False
                                                            )
                                                            if stop_event.is_set():
                                                                detenido = True
                                                            else:
                                                                if texto_ai_studio:
                                                                    prompts_extraidos = extraer_prompts_ai_studio(
                                                                        texto_ai_studio
                                                                    )
                                                                    if prompts_extraidos:
                                                                        ruta_prompts = guardar_prompts_ai_studio(
                                                                            path,
                                                                            prompts_extraidos,
                                                                            ai_studio_runtime.get(
                                                                                "archivo_salida"
                                                                            ),
                                                                        )
                                                                        log_msg(
                                                                            f"✅ AI Studio: {len(prompts_extraidos)} prompt(s) guardados en {os.path.basename(ruta_prompts)}.",
                                                                            color=ft.Colors.GREEN_700,
                                                                            weight="bold",
                                                                        )
                                                                        if (
                                                                            not stop_event.is_set()
                                                                            and ai_studio_runtime.get(
                                                                                "auto_send_to_extension",
                                                                                False,
                                                                            )
                                                                        ):
                                                                            log_msg(
                                                                                "🖼️ Enviando prompts de imagen a la extensión Chrome...",
                                                                                color=ft.Colors.TEAL_700,
                                                                                italic=True,
                                                                            )
                                                                            img_ok, img_msg, _ = send_image_prompts_to_extension(
                                                                                ruta_prompts,
                                                                                modelo=ai_studio_runtime.get(
                                                                                    "imagen_model",
                                                                                    "imagen4",
                                                                                ),
                                                                                aspect_ratio=ai_studio_runtime.get(
                                                                                    "imagen_aspect_ratio",
                                                                                    "landscape",
                                                                                ),
                                                                                count=ai_studio_runtime.get(
                                                                                    "imagen_count",
                                                                                    1,
                                                                                ),
                                                                                reference_image_paths=list(ref_image_paths_state) if ref_image_paths_state else None,
                                                                                reference_mode=dropdown_ref_mode.value or "ingredients",
                                                                                project_folder=path,
                                                                            )
                                                                            log_msg(
                                                                                f"{'✅' if img_ok else '⚠'} {img_msg}",
                                                                                color=ft.Colors.GREEN_700 if img_ok else ft.Colors.ORANGE_700,
                                                                                weight="bold" if img_ok else None,
                                                                            )
                                                                    else:
                                                                        log_msg(
                                                                            "⚠ AI Studio: no se encontraron etiquetas <prompt></prompt> en la respuesta copiada.",
                                                                            color=ft.Colors.ORANGE_700,
                                                                        )
                                                                else:
                                                                    log_msg(
                                                                        "⚠ AI Studio: no se pudo copiar la respuesta completa desde la ventana.",
                                                                        color=ft.Colors.ORANGE_700,
                                                                    )
                                                    else:
                                                        log_msg(
                                                            f"⚠ AI Studio: {ai_msg}",
                                                            color=ft.Colors.ORANGE_700,
                                                        )
                                                else:
                                                    log_msg(
                                                        f"⚠ AI Studio: {prompt_ai_msg}",
                                                        color=ft.Colors.ORANGE_700,
                                                    )
                                            else:
                                                log_msg(
                                                    "⚠ No se abrió AI Studio: el prompt está vacío. Configúralo en el tile de Configuración.",
                                                    color=ft.Colors.ORANGE_700,
                                                )
                                        else:
                                            log_msg(
                                                f"⚠ WhisperX: {wx_msg}",
                                                color=ft.Colors.ORANGE_700,
                                            )
                                    # --- FIN WhisperX ---
                                else:
                                    log_msg(f"⚠ {tts_msg}", color=ft.Colors.ORANGE_700)
                        else:
                            log_msg(f"⚠ {mensaje}", color=ft.Colors.ORANGE_700)

                    if detenido or stop_event.is_set():
                        log_msg(
                            f"⛔ FLUJO DETENIDO por el usuario en video {num}",
                            color=ft.Colors.RED_700,
                            weight="bold",
                        )
                    else:
                        log_msg(
                            f"✅ FINALIZADO: video {num}",
                            color=ft.Colors.GREEN_800,
                            weight="bold",
                        )

            except Exception as ex:
                log_msg(f"❌ Error: {str(ex)}", color=ft.Colors.RED)

            prg.visible = False
            txt_proximo.value = (
                f"Próximo Proyecto: video {obtener_siguiente_num(ruta_base[0])}"
            )
            set_estado_ejecutando(False)
            page.update()

        threading.Thread(target=proceso_hilo, daemon=True).start()

    # --- UI LAYOUT ---
    tile_gestion = ft.Card(
        col={"md": 4},
        content=ft.Container(
            padding=20,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.PEOPLE_ALT),
                            ft.Text("CANALES", weight="bold"),
                        ]
                    ),
                    ft.Row([input_id, input_name]),
                    ft.ElevatedButton(
                        "Agregar",
                        icon=ft.Icons.ADD,
                        on_click=agregar_canal,
                        width=1000,
                        bgcolor=ft.Colors.BLUE_800,
                        color="white",
                    ),
                    ft.Divider(),
                    lista_canales_ui,
                ]
            ),
        ),
    )

    btn_ejecutar_widget = ft.ElevatedButton(
        "EJECUTAR FLUJO COMPLETO",
        icon=ft.Icons.AUTO_AWESOME,
        on_click=ejecutar_flujo_completo,
        bgcolor=ft.Colors.GREEN_700,
        color="white",
        height=50,
        width=1000,
    )
    btn_ejecutar_ref[0] = btn_ejecutar_widget

    tile_flujo = ft.Card(
        col={"md": 4},
        content=ft.Container(
            padding=20,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.BOLT, color=ft.Colors.AMBER_700),
                            ft.Text("AUTOMATIZACIÓN", weight="bold"),
                        ]
                    ),
                    btn_ejecutar_widget,
                    txt_alcance_flujo,
                    btn_detener,
                    prg,
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.TERMINAL,
                                size=16,
                                color=ft.Colors.GREY_500,
                            ),
                            ft.Text(
                                "Consola de ejecución",
                                size=12,
                                color=ft.Colors.GREY_500,
                                italic=True,
                            ),
                        ],
                        spacing=6,
                    ),
                    log_container,
                ]
            ),
        ),
    )

    txt_nvidia_status = ft.Text(
        "NVIDIA API: detectada" if NVIDIA_API_KEY else "NVIDIA API: no configurada",
        size=12,
        color=ft.Colors.GREEN_700 if NVIDIA_API_KEY else ft.Colors.ORANGE_700,
        italic=True,
    )

    switch_tts_enabled = ft.Switch(
        label="🔊 Generar audio automáticamente al crear script.txt",
        value=tts_config.get("enabled", False),
        active_color=ft.Colors.BLUE_600,
    )
    txt_tts_language = ft.TextField(
        label="Language Code",
        value=tts_config.get("language_code", "en-US"),
        dense=True,
    )
    txt_tts_voice = ft.TextField(
        label="Voice",
        value=tts_config.get("voice", ""),
        dense=True,
    )
    txt_tts_output = ft.TextField(
        label="Archivo WAV",
        value=tts_config.get("output_filename", "audio.wav"),
        dense=True,
    )
    txt_tts_sample_rate = ft.TextField(
        label="Sample Rate (Hz)",
        value=str(tts_config.get("sample_rate_hz", 44100)),
        dense=True,
        width=180,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    def persistir_tts_desde_ui(mostrar_snack=False):
        tts_config["enabled"] = bool(switch_tts_enabled.value)
        tts_config["language_code"] = txt_tts_language.value
        tts_config["voice"] = txt_tts_voice.value
        tts_config["output_filename"] = txt_tts_output.value
        tts_config["sample_rate_hz"] = txt_tts_sample_rate.value

        normalizado = normalizar_tts_config(tts_config)
        tts_config.update(normalizado)

        txt_tts_language.value = tts_config["language_code"]
        txt_tts_voice.value = tts_config["voice"]
        txt_tts_output.value = tts_config["output_filename"]
        txt_tts_sample_rate.value = str(tts_config["sample_rate_hz"])

        guardar_tts()
        if mostrar_snack:
            show_snack("Configuración TTS guardada", ft.Colors.GREEN)
        page.update()

    switch_tts_enabled.on_change = lambda e: persistir_tts_desde_ui()
    txt_tts_language.on_blur = lambda e: persistir_tts_desde_ui()
    txt_tts_voice.on_blur = lambda e: persistir_tts_desde_ui()
    txt_tts_output.on_blur = lambda e: persistir_tts_desde_ui()
    txt_tts_sample_rate.on_blur = lambda e: persistir_tts_desde_ui()

    def probar_tts_ultimo_proyecto(e=None):
        persistir_tts_desde_ui()

        ultimo_video = obtener_ultimo_video(ruta_base[0])
        if not ultimo_video:
            show_snack("No hay proyectos generados para probar TTS", ft.Colors.RED)
            return

        def ejecutar_prueba_tts():
            try:
                log_msg(
                    f"🔊 Probando NVIDIA TTS en {os.path.basename(ultimo_video)}...",
                    color=ft.Colors.BLUE_800,
                    italic=True,
                )
                tts_ok, tts_msg, ruta_audio = sintetizar_script_a_audio_nvidia(
                    ultimo_video,
                    tts_config,
                )
                if tts_ok:
                    log_msg(
                        f"✅ {tts_msg}",
                        color=ft.Colors.GREEN_700,
                        weight="bold",
                    )
                    show_snack("TTS completado", ft.Colors.GREEN)
                else:
                    log_msg(f"⚠ {tts_msg}", color=ft.Colors.ORANGE_700)
                    show_snack("TTS devolvió un warning", ft.Colors.ORANGE)
            except Exception as ex:
                log_msg(f"❌ Error TTS manual: {str(ex)}", color=ft.Colors.RED)
                show_snack("Falló la prueba TTS", ft.Colors.RED)

        threading.Thread(target=ejecutar_prueba_tts, daemon=True).start()

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
    dropdown_ejecutar_hasta = ft.Dropdown(
        label="Ejecutar hasta prompt",
        dense=True,
        width=320,
        options=[],
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
    dropdown_ejecutar_hasta.on_change = lambda e: persistir_alcance_ejecucion()

    imagen_model_inicial = ai_studio_config.get("imagen_model", "imagen4")
    imagen_aspect_inicial = ai_studio_config.get("imagen_aspect_ratio", "landscape")
    imagen_count_inicial = str(ai_studio_config.get("imagen_count", 1))
    auto_send_inicial = ai_studio_config.get("auto_send_to_extension", False)

    tile_config = ft.Card(
        col={"md": 4},
        content=ft.Container(
            padding=20,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SETTINGS),
                            ft.Text("CONFIGURACIÓN", weight="bold"),
                        ]
                    ),
                    txt_proximo,
                    ft.ElevatedButton(
                        "Ruta de Proyectos",
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=lambda _: picker.get_directory_path(),
                    ),
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.RECORD_VOICE_OVER, color=ft.Colors.BLUE_600),
                            ft.Text("NVIDIA TTS", weight="bold"),
                        ]
                    ),
                    txt_nvidia_status,
                    switch_tts_enabled,
                    txt_tts_language,
                    txt_tts_voice,
                    ft.Row([txt_tts_output, txt_tts_sample_rate]),
                    ft.ElevatedButton(
                        "Probar TTS en último script",
                        icon=ft.Icons.GRAPHIC_EQ,
                        on_click=probar_tts_ultimo_proyecto,
                        bgcolor=ft.Colors.BLUE_700,
                        color="white",
                    ),
                    ft.Text(
                        "Usa una voz válida de Magpie Multilingual, por ejemplo Magpie-Multilingual.EN-US.Aria.",
                        size=11,
                        color=ft.Colors.GREY_600,
                        italic=True,
                    ),
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.TRANSCRIBE, color=ft.Colors.PURPLE_500),
                            ft.Text("WHISPERX", weight="bold"),
                        ]
                    ),
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
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.FAST_FORWARD, color=ft.Colors.ORANGE_700),
                            ft.Text("ALCANCE DE PRUEBA", weight="bold"),
                        ]
                    ),
                    dropdown_ejecutar_hasta,
                    txt_alcance_selector,
                    ft.ElevatedButton(
                        "Guardar alcance de prueba",
                        icon=ft.Icons.SAVE,
                        on_click=lambda e: persistir_alcance_ejecucion(mostrar_snack=True),
                        bgcolor=ft.Colors.ORANGE_700,
                        color="white",
                    ),
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SMART_TOY, color=ft.Colors.BLUE_700),
                            ft.Text("Google AI Studio (Post-WhisperX)", weight="bold"),
                        ]
                    ),
                    txt_ai_studio_wait,
                    txt_prompt_ai_studio,
                    ft.Text(
                        "Los prompts extraídos se guardarán en prompts_imagenes.txt, separados por una línea en blanco.",
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
                ]
            ),
        ),
    )

    txt_prompt_count = ft.Text(
        f"{len(prompts_lista)} prompts",
        size=12,
        color=ft.Colors.GREY_600,
        italic=True,
    )

    prompts_gallery_scroll = ft.Container(
        content=ft.Column(
            controls=[prompts_ui],
            scroll=ft.ScrollMode.AUTO,
        ),
        height=450,
        border_radius=8,
    )

    tile_prompts = ft.Card(
        col={"md": 12},
        content=ft.Container(
            padding=20,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.AUTO_FIX_HIGH, color=ft.Colors.PURPLE_600),
                            ft.Text(
                                "PROMPT MANAGER", weight="bold", size=16, expand=True
                            ),
                            txt_prompt_count,
                            ft.OutlinedButton(
                                "Desactivar todos",
                                icon=ft.Icons.TOGGLE_OFF,
                                on_click=deshabilitar_todos_prompts,
                            ),
                            ft.OutlinedButton(
                                "Activar todos",
                                icon=ft.Icons.TOGGLE_ON,
                                on_click=habilitar_todos_prompts,
                            ),
                            ft.ElevatedButton(
                                "Agregar Prompt",
                                icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                                on_click=agregar_prompt_nuevo,
                                bgcolor=ft.Colors.PURPLE_600,
                                color="white",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(),
                    prompts_gallery_scroll,
                ]
            ),
        ),
    )

    actualizar_selector_ejecucion()
    actualizar_resumen_alcance()

    # ==========================================
    # --- UI: GENERACIÓN DE IMÁGENES (FLOW AUTOMATOR) ---
    # ==========================================
    switch_auto_send = ft.Switch(
        label="🔄 Enviar automáticamente al finalizar AI Studio",
        value=auto_send_inicial,
        active_color=ft.Colors.TEAL_600,
    )

    dropdown_imagen_model = ft.Dropdown(
        label="Modelo de imagen",
        value=imagen_model_inicial,
        options=[
            ft.dropdown.Option("imagen4", "Imagen 4"),
            ft.dropdown.Option("nano_banana2", "NB 2"),
            ft.dropdown.Option("nano_banana_pro", "NB Pro"),
        ],
        dense=True,
        expand=True,
    )

    dropdown_imagen_aspect = ft.Dropdown(
        label="Aspect Ratio",
        value=imagen_aspect_inicial,
        options=[
            ft.dropdown.Option("landscape", "16:9 Landscape"),
            ft.dropdown.Option("portrait", "9:16 Portrait"),
        ],
        dense=True,
        expand=True,
    )

    dropdown_imagen_count = ft.Dropdown(
        label="Imágenes por prompt",
        value=imagen_count_inicial,
        options=[
            ft.dropdown.Option("1", "1x"),
            ft.dropdown.Option("2", "2x"),
            ft.dropdown.Option("3", "3x"),
            ft.dropdown.Option("4", "4x"),
        ],
        dense=True,
        expand=True,
    )

    lbl_imagen_status = ft.Text(
        "Estado: esperando...",
        size=11,
        color=ft.Colors.GREY_500,
        italic=True,
    )
    image_status_ref[0] = lbl_imagen_status

    def persistir_imagen_config(e=None, mostrar_snack=False):
        ai_studio_config["auto_send_to_extension"] = bool(switch_auto_send.value)
        ai_studio_config["imagen_model"] = dropdown_imagen_model.value or "imagen4"
        ai_studio_config["imagen_aspect_ratio"] = (
            dropdown_imagen_aspect.value or "landscape"
        )
        ai_studio_config["imagen_count"] = dropdown_imagen_count.value or "1"

        normalizado = normalizar_ai_studio_config(ai_studio_config)
        ai_studio_config.update(normalizado)

        switch_auto_send.value = ai_studio_config["auto_send_to_extension"]
        dropdown_imagen_model.value = ai_studio_config["imagen_model"]
        dropdown_imagen_aspect.value = ai_studio_config["imagen_aspect_ratio"]
        dropdown_imagen_count.value = str(ai_studio_config["imagen_count"])
        config_actual["ai_studio"] = dict(ai_studio_config)
        config_actual["prompt_ai_studio"] = ai_studio_config["prompt"]

        guardar_config(ai_studio=ai_studio_config)
        if mostrar_snack:
            show_snack("Configuración de imágenes guardada", ft.Colors.GREEN)
        page.update()

    switch_auto_send.on_change = persistir_imagen_config
    dropdown_imagen_model.on_change = persistir_imagen_config
    dropdown_imagen_aspect.on_change = persistir_imagen_config
    dropdown_imagen_count.on_change = persistir_imagen_config

    def enviar_prompts_manualmente(e):
        persistir_imagen_config()

        ultimo_video = obtener_ultimo_video(ruta_base[0])
        if not ultimo_video:
            show_snack("No hay proyectos generados todavía.", ft.Colors.RED)
            return

        ruta_txt = os.path.join(
            ultimo_video,
            ai_studio_config.get("archivo_salida", AI_STUDIO_OUTPUT_FILENAME_DEFAULT),
        )

        def hilo_envio():
            actualizar_estado_imagen("Enviando...", ft.Colors.BLUE_700)
            ok, msg, _ = send_image_prompts_to_extension(
                ruta_txt,
                modelo=ai_studio_config.get("imagen_model", "imagen4"),
                aspect_ratio=ai_studio_config.get("imagen_aspect_ratio", "landscape"),
                count=ai_studio_config.get("imagen_count", 1),
                reference_image_paths=list(ref_image_paths_state) if ref_image_paths_state else None,
                reference_mode=dropdown_ref_mode.value or "ingredients",
                project_folder=ultimo_video,
            )
            if ok:
                actualizar_estado_imagen(
                    "Prompts enviados. Esperando que Flow genere y descargue imágenes...",
                    ft.Colors.TEAL_700,
                )
            else:
                actualizar_estado_imagen(msg, ft.Colors.RED_700)
            log_msg(
                f"{'✅' if ok else '❌'} Imágenes: {msg}",
                color=ft.Colors.GREEN_700 if ok else ft.Colors.RED,
            )

        threading.Thread(target=hilo_envio, daemon=True).start()

    def solicitar_estado_cola(e):
        if not send_ws_msg({"action": "GET_QUEUE_STATUS"}):
            show_snack("La extensión no está conectada.", ft.Colors.RED)
        else:
            actualizar_estado_imagen(
                "Solicitando estado de la cola...",
                ft.Colors.BLUE_700,
            )

    dropdown_ref_mode = ft.Dropdown(
        label="Modo de referencia",
        value="ingredients",
        options=[
            ft.dropdown.Option("ingredients", "Ingredients (mezcla libre)"),
            ft.dropdown.Option("frames", "Frames (secuencia ordenada)"),
        ],
        dense=True,
        expand=True,
    )

    lbl_ref_images = ft.Text(
        "Sin imágenes de referencia",
        size=11,
        color=ft.Colors.GREY_500,
        italic=True,
    )

    def _actualizar_label_ref_images():
        count = len(ref_image_paths_state)
        if count == 0:
            lbl_ref_images.value = "Sin imágenes de referencia"
            lbl_ref_images.color = ft.Colors.GREY_500
            return

        nombres = ", ".join(os.path.basename(path) for path in ref_image_paths_state)
        lbl_ref_images.value = f"{count} imagen(es): {nombres}"
        lbl_ref_images.color = ft.Colors.TEAL_700

    def on_ref_images_picked(e: ft.FilePickerResultEvent):
        if not e.files:
            return

        for selected_file in e.files:
            if selected_file.path and selected_file.path not in ref_image_paths_state:
                ref_image_paths_state.append(selected_file.path)

        _actualizar_label_ref_images()
        page.update()

    def limpiar_ref_images(e=None):
        ref_image_paths_state.clear()
        _actualizar_label_ref_images()
        page.update()

    tile_imagen = ft.Card(
        col={"md": 4},
        content=ft.Container(
            padding=20,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.IMAGE, color=ft.Colors.TEAL_600),
                            ft.Text("GENERACIÓN DE IMÁGENES", weight="bold"),
                        ]
                    ),
                    ft.Divider(),
                    switch_auto_send,
                    ft.Row([dropdown_imagen_model, dropdown_imagen_count]),
                    dropdown_imagen_aspect,
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.IMAGE_SEARCH, color=ft.Colors.TEAL_600, size=16),
                            ft.Text("Imágenes de referencia (opcional)", size=12, weight="bold"),
                        ]
                    ),
                    dropdown_ref_mode,
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "Seleccionar imágenes",
                                icon=ft.Icons.ADD_PHOTO_ALTERNATE,
                                on_click=lambda _: ref_images_picker.pick_files(
                                    allow_multiple=True,
                                    allowed_extensions=["png", "jpg", "jpeg", "webp"],
                                ),
                                expand=True,
                                bgcolor=ft.Colors.TEAL_50,
                                color=ft.Colors.TEAL_800,
                            ),
                            ft.IconButton(
                                ft.Icons.CLEAR,
                                on_click=limpiar_ref_images,
                                tooltip="Limpiar selección",
                                icon_color=ft.Colors.RED_400,
                            ),
                        ]
                    ),
                    lbl_ref_images,
                    ft.Divider(),
                    lbl_imagen_status,
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "Enviar Prompts",
                                icon=ft.Icons.SEND,
                                on_click=enviar_prompts_manualmente,
                                expand=True,
                                bgcolor=ft.Colors.TEAL_700,
                                color="white",
                            ),
                            ft.IconButton(
                                ft.Icons.INFO_OUTLINE,
                                on_click=solicitar_estado_cola,
                                tooltip="Ver estado de la cola",
                                icon_color=ft.Colors.TEAL_700,
                                bgcolor=ft.Colors.TEAL_50,
                            ),
                        ]
                    ),
                ]
            ),
        ),
    )

    # ==========================================
    # --- UI: CONTROL DE EXTENSIÓN WEB ---
    # ==========================================
    dropdown_journeys = ft.Dropdown(label="Journey principal", expand=True)
    dropdown_second_journey = ft.Dropdown(
        label="Segunda automatización",
        expand=True,
        disabled=True,
    )
    
    # Nuevo switch para decirle al bot que pegue el texto al final
    chk_pegar_script = ft.Switch(
        label="📝 Pegar script.txt al finalizar Journey",
        value=True,
        active_color=ft.Colors.BLUE_600
    )
    chk_segundo_journey = ft.Switch(
        label="🔁 Ejecutar segunda automatización luego del pegado",
        value=False,
        active_color=ft.Colors.BLUE_600,
    )

    def actualizar_estado_segundo_journey(e=None):
        dropdown_second_journey.disabled = not chk_segundo_journey.value
        if not chk_segundo_journey.value:
            dropdown_second_journey.value = None
        page.update()

    chk_segundo_journey.on_change = actualizar_estado_segundo_journey

    def obtener_texto_script_ultimo_video():
        ultimo_video = obtener_ultimo_video(ruta_base[0])
        if not ultimo_video:
            return None, "No hay proyectos generados aún en la carpeta"

        script_path = os.path.join(ultimo_video, "script.txt")
        if not os.path.exists(script_path):
            return None, "No se encontró script.txt en el último proyecto."

        with open(script_path, "r", encoding="utf-8") as f:
            return f.read(), None

    def refrescar_journeys_ui():
        """Se llama automáticamente cuando el navegador envía la lista"""
        current_primary = dropdown_journeys.value
        current_secondary = dropdown_second_journey.value
        primary_options = [
            ft.dropdown.Option(key=j["id"], text=j["name"])
            for j in ws_bridge.available_journeys
        ]
        secondary_options = [
            ft.dropdown.Option(key=j["id"], text=j["name"])
            for j in ws_bridge.available_journeys
        ]
        valid_ids = {j["id"] for j in ws_bridge.available_journeys}
        dropdown_journeys.options = primary_options
        dropdown_second_journey.options = secondary_options

        if current_primary in valid_ids:
            dropdown_journeys.value = current_primary
        elif ws_bridge.available_journeys:
            dropdown_journeys.value = ws_bridge.available_journeys[0]["id"]

        if current_secondary in valid_ids:
            dropdown_second_journey.value = current_secondary
        elif current_secondary:
            dropdown_second_journey.value = None

        page.update()
        
    ws_bridge.ui_update_journeys_cb = refrescar_journeys_ui

    def solicitar_journeys(e):
        if not send_ws_msg({"action": "GET_JOURNEYS"}):
            show_snack("La extensión de Chrome no está conectada", ft.Colors.RED)

    def ordenar_ejecucion_journey(e):
        if not dropdown_journeys.value:
            show_snack("Selecciona un Journey primero", ft.Colors.RED)
            return

        if chk_segundo_journey.value:
            if not chk_pegar_script.value:
                show_snack("Activa el pegado de script.txt para encadenar la segunda automatización", ft.Colors.RED)
                return
            if not dropdown_second_journey.value:
                show_snack("Selecciona la segunda automatización", ft.Colors.RED)
                return
            if dropdown_second_journey.value == dropdown_journeys.value:
                show_snack("El segundo journey debe ser distinto del principal", ft.Colors.RED)
                return

        payload = {
            "action": "RUN_JOURNEY",
            "journey_id": dropdown_journeys.value
        }

        # Lógica para leer el archivo local y adjuntarlo al comando del navegador
        if chk_pegar_script.value:
            script_text, error_msg = obtener_texto_script_ultimo_video()
            if error_msg:
                show_snack(error_msg, ft.Colors.RED)
                return
            payload["paste_text_at_end"] = script_text

        if chk_segundo_journey.value:
            set_pending_journey_chain(
                dropdown_journeys.value,
                dropdown_second_journey.value,
            )
        else:
            reset_pending_journey_chain()

        if not send_ws_msg(payload):
             reset_pending_journey_chain()
             show_snack("La extensión de Chrome no está conectada", ft.Colors.RED)
        else:
             show_snack("Orden de ejecución enviada", ft.Colors.GREEN)
             if chk_segundo_journey.value:
                 log_msg(
                     "⏳ Esperando señal de pegado completado para disparar la segunda automatización...",
                     color=ft.Colors.BLUE_800,
                 )

    # Botón de rescate: Permite pegar el script independientemente si no se quiere usar el "Journey"
    def pegar_script_ahora(e):
        text, error_msg = obtener_texto_script_ultimo_video()
        if error_msg:
            show_snack(error_msg, ft.Colors.RED)
            return

        if send_ws_msg({"action": "PASTE_TEXT_NOW", "text": text}):
            show_snack("Texto enviado a la extensión", ft.Colors.GREEN)
        else:
            show_snack("La extensión no está conectada", ft.Colors.RED)

    tile_web_extension = ft.Card(
        col={"md": 4},
        content=ft.Container(
            padding=20,
            content=ft.Column([
                    ft.Row([
                            ft.Icon(ft.Icons.LANGUAGE, color=ft.Colors.BLUE_500),
                            ft.Text("EXTENSIÓN WEB (CHROME)", weight="bold"),
                        ]
                    ),
                    ft.Row([
                        dropdown_journeys,
                        ft.IconButton(
                            ft.Icons.REFRESH,
                            on_click=solicitar_journeys,
                            tooltip="Recargar lista de Journeys",
                            icon_color=ft.Colors.BLUE_700
                        )
                    ]),
                    chk_segundo_journey,
                    dropdown_second_journey,
                    chk_pegar_script,
                    ft.Row([
                        ft.ElevatedButton(
                            "Ejecutar Journey",
                            icon=ft.Icons.PLAY_ARROW,
                            on_click=ordenar_ejecucion_journey,
                            expand=True,
                            bgcolor=ft.Colors.BLUE_800,
                            color="white",
                        ),
                        ft.IconButton(
                            ft.Icons.PASTE,
                            tooltip="Pegar script.txt ahora (Paso Manual)",
                            on_click=pegar_script_ahora,
                            icon_color=ft.Colors.BLUE_800,
                            bgcolor=ft.Colors.BLUE_50
                        )
                    ])
                ]
            ),
        ),
    )

    def on_pick_directory(e):
        if not e.path:
            return
        ruta_base[0] = e.path
        guardar_config(ruta=e.path)
        txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(ruta_base[0])}"
        page.update()

    picker = ft.FilePicker(on_result=on_pick_directory)
    ref_images_picker = ft.FilePicker(on_result=on_ref_images_picked)
    page.overlay.append(picker)
    page.overlay.append(ref_images_picker)

    page.add(
        ft.Row([
                ft.Text("Clusiv", size=32, weight="bold", color=ft.Colors.BLUE_800),
                ft.Text("Automation", size=32),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        ft.ResponsiveRow([tile_gestion, tile_flujo, tile_config, tile_web_extension, tile_imagen]),
        ft.ResponsiveRow([tile_prompts]),
    )
    refrescar_canales()
    refrescar_prompts()


if __name__ == "__main__":
    ft.app(target=main)