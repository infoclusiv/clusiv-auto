import os
import threading

import flet as ft

import ws_bridge
from config import (
    AI_STUDIO_OUTPUT_FILENAME_DEFAULT,
    guardar_config,
    normalizar_ai_studio_config,
)
from ws_bridge import (
    reset_pending_journey_chain,
    send_image_prompts_to_extension,
    send_ws_msg,
    set_pending_journey_chain,
)
from youtube_analyzer import obtener_ultimo_video


def build_panel_flow(page, state, log_msg):
    ai_studio_config = state.ai_studio_config
    config_actual = state.config_actual
    ref_image_paths_state = state.ref_image_paths_state
    ruta_base = state.ruta_base

    image_status_refs = []

    def show_snack(msg, color=ft.Colors.GREEN):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), bgcolor=color))
        page.overlay[-1].open = True
        page.update()

    def actualizar_estado_imagen(texto, color=ft.Colors.GREY_500):
        if not image_status_refs:
            return
        for status_control in image_status_refs:
            status_control.value = texto
            status_control.color = color
        if page.controls:
            page.update()

    imagen_model_inicial = ai_studio_config.get("imagen_model", "imagen4")
    imagen_aspect_inicial = ai_studio_config.get("imagen_aspect_ratio", "landscape")
    imagen_count_inicial = str(ai_studio_config.get("imagen_count", 1))
    auto_send_inicial = ai_studio_config.get("auto_send_to_extension", False)

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

    def crear_lbl_imagen_status():
        control = ft.Text(
            "Estado: esperando...",
            size=11,
            color=ft.Colors.GREY_500,
            italic=True,
        )
        image_status_refs.append(control)
        return control

    lbl_imagen_status = crear_lbl_imagen_status()

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

    def on_ref_images_picked(files):
        if not files:
            return

        for selected_file in files:
            if selected_file.path and selected_file.path not in ref_image_paths_state:
                ref_image_paths_state.append(selected_file.path)

        _actualizar_label_ref_images()
        page.update()

    def limpiar_ref_images(e=None):
        ref_image_paths_state.clear()
        _actualizar_label_ref_images()
        page.update()

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

    dropdown_journeys = ft.Dropdown(label="Journey principal", expand=True)
    dropdown_second_journey = ft.Dropdown(
        label="Segunda automatización",
        expand=True,
        disabled=True,
    )

    chk_pegar_script = ft.Switch(
        label="📝 Pegar script.txt al finalizar Journey",
        value=True,
        active_color=ft.Colors.BLUE_600,
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
            "journey_id": dropdown_journeys.value,
        }

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

    def pegar_script_ahora(e):
        text, error_msg = obtener_texto_script_ultimo_video()
        if error_msg:
            show_snack(error_msg, ft.Colors.RED)
            return

        if send_ws_msg({"action": "PASTE_TEXT_NOW", "text": text}):
            show_snack("Texto enviado a la extensión", ft.Colors.GREEN)
        else:
            show_snack("La extensión no está conectada", ft.Colors.RED)

    ref_images_picker = ft.FilePicker()
    lbl_imagen_status_sidebar = crear_lbl_imagen_status()

    expansion_flow = ft.ExpansionTile(
        title=ft.Text("🖼️ Generación de Imágenes - Google Flow", weight="bold", size=13),
        subtitle=ft.Text(
            "Extensión Chrome + Flow Automator (Fase 6)",
            size=11,
            color=ft.Colors.GREY_600,
        ),
        expanded=False,
        controls=[
            ft.Text(
                "Configuración de generación",
                size=12,
                weight="bold",
                color=ft.Colors.GREY_700,
            ),
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
                        on_click=lambda _: on_ref_images_picked(
                            ref_images_picker.pick_files(
                                allow_multiple=True,
                                allowed_extensions=["png", "jpg", "jpeg", "webp"],
                            )
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
            ft.Divider(),
            ft.Row(
                [
                    ft.Icon(ft.Icons.LANGUAGE, color=ft.Colors.BLUE_500, size=16),
                    ft.Text("Automatización por Journey (Chrome)", size=12, weight="bold"),
                ]
            ),
            ft.Row(
                [
                    dropdown_journeys,
                    ft.IconButton(
                        ft.Icons.REFRESH,
                        on_click=solicitar_journeys,
                        tooltip="Recargar lista de Journeys",
                        icon_color=ft.Colors.BLUE_700,
                    ),
                ]
            ),
            chk_segundo_journey,
            dropdown_second_journey,
            chk_pegar_script,
            ft.Row(
                [
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
                        bgcolor=ft.Colors.BLUE_50,
                    ),
                ]
            ),
        ],
    )

    _actualizar_label_ref_images()

    def get_ref_mode():
        return dropdown_ref_mode.value or "ingredients"

    return (
        expansion_flow,
        ref_images_picker,
        actualizar_estado_imagen,
        refrescar_journeys_ui,
        lbl_imagen_status_sidebar,
        get_ref_mode,
    )