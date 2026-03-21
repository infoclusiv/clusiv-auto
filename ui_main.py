"""ui_main.py - Interfaz principal de Clusiv Automation."""

import flet as ft

from config import YOUTUBE_API_KEY
from flow_orchestrator import FlowContext, ejecutar_flujo
import ws_bridge
from youtube_analyzer import obtener_siguiente_num

from ui.consola import build_consola
from ui.header import build_header
from ui.panel_ai_studio import build_panel_ai_studio
from ui.panel_flow import build_panel_flow
from ui.panel_proyecto import build_panel_proyecto
from ui.panel_prompts import build_panel_prompts
from ui.panel_tts import build_panel_tts
from ui.panel_whisperx import build_panel_whisperx
from ui.state import AppState
from ui.tracker import construir_tracker_fases


def main(page: ft.Page):
    page.title = "Clusiv Automation Hub"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#F0F2F6"
    page.padding = 0
    page.scroll = None

    state = AppState()

    log_container, log_msg, limpiar_log = build_consola(page)
    ws_bridge.ui_log_cb = log_msg

    tracker_widget, set_fase_estado, reset_tracker = construir_tracker_fases(page)

    header_bar, actualizar_ext_status_header = build_header(page)
    ws_bridge.ui_ext_status_cb = actualizar_ext_status_header

    prg = ft.ProgressBar(width=400, visible=False, color=ft.Colors.GREEN_700)
    txt_proximo = ft.Text(size=14, weight="bold", color=ft.Colors.BLUE_GREY_700)
    txt_alcance_flujo = ft.Text(size=12, color=ft.Colors.BLUE_GREY_600, italic=True)
    btn_ejecutar_ref = [None]

    def _show_snack(msg, color=ft.Colors.GREEN):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), bgcolor=color))
        page.overlay[-1].open = True
        page.update()

    def _actualizar_txt_proximo(ruta):
        txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(ruta)}"
        if page.controls:
            page.update()

    def _sync_boton_ejecutar(texto_boton, descripcion):
        if btn_ejecutar_ref[0]:
            btn_ejecutar_ref[0].text = texto_boton
        txt_alcance_flujo.value = f"Alcance actual: {descripcion}"
        if page.controls:
            page.update()

    expansion_proyecto, picker, refrescar_canales, _ = build_panel_proyecto(
        page,
        state,
        on_ruta_cambiada=lambda ruta: _actualizar_txt_proximo(ruta),
    )
    page.services.append(picker)

    expansion_prompts, obtener_prompts_para_ejecucion, actualizar_resumen_alcance = (
        build_panel_prompts(
            page,
            state,
            on_alcance_cambiado=lambda txt, desc: _sync_boton_ejecutar(txt, desc),
        )
    )

    expansion_tts, _ = build_panel_tts(page, state, log_msg)
    expansion_whisperx, _ = build_panel_whisperx(page, state)
    expansion_ai_studio, _ = build_panel_ai_studio(page, state)

    (
        expansion_flow,
        ref_images_picker,
        actualizar_estado_imagen,
        refrescar_journeys_ui,
        lbl_imagen_status_sidebar,
        get_ref_mode,
    ) = build_panel_flow(page, state, log_msg)
    page.services.append(ref_images_picker)
    ws_bridge.ui_image_status_cb = actualizar_estado_imagen
    ws_bridge.ui_update_journeys_cb = refrescar_journeys_ui

    btn_detener = ft.ElevatedButton(
        "DETENER FLUJO",
        icon=ft.Icons.STOP_CIRCLE,
        bgcolor=ft.Colors.RED_700,
        color="white",
        height=50,
        width=1000,
        visible=False,
        on_click=lambda _: _detener_flujo(),
    )

    def _detener_flujo():
        state.stop_event.set()
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

    def _set_estado_ejecutando(ejecutando):
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

    def ejecutar_flujo_completo(e):
        if not state.ruta_base[0]:
            _show_snack("Selecciona una ruta de proyectos", ft.Colors.RED)
            return
        if not YOUTUBE_API_KEY:
            _show_snack("Falta API KEY en .env", ft.Colors.RED)
            return

        prompts_a_ejecutar, _ = obtener_prompts_para_ejecucion()
        if not prompts_a_ejecutar:
            _show_snack("No hay prompts configurados", ft.Colors.RED)
            return

        log_container.content.controls.clear()
        prg.visible = True
        _set_estado_ejecutando(True)
        reset_tracker()
        page.update()

        ctx = FlowContext(
            stop_event=state.stop_event,
            log_msg=log_msg,
            ruta_base=state.ruta_base,
            prompts_lista=state.prompts_lista,
            tts_config=state.tts_config,
            whisperx_config=state.whisperx_config,
            config_actual=state.config_actual,
            ejecutar_hasta_prompt=state.ejecutar_hasta_prompt,
            ref_image_paths_state=state.ref_image_paths_state,
            dropdown_ref_mode=get_ref_mode(),
            prg=prg,
            txt_proximo=txt_proximo,
            page=page,
            set_estado_ejecutando=_set_estado_ejecutando,
            obtener_prompts_para_ejecucion=obtener_prompts_para_ejecucion,
            set_fase_estado=set_fase_estado,
            reset_tracker=reset_tracker,
        )
        ejecutar_flujo(ctx)

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

    btn_limpiar_log = ft.TextButton(
        "Limpiar",
        icon=ft.Icons.DELETE_SWEEP,
        icon_color=ft.Colors.GREY_500,
        on_click=limpiar_log,
        style=ft.ButtonStyle(color=ft.Colors.GREY_500),
    )

    col_izquierda = ft.Container(
        width=420,
        padding=ft.padding.only(left=16, top=16, right=8, bottom=16),
        content=ft.Column(
            [
                ft.Text(
                    "Configuración del Pipeline",
                    size=12,
                    weight="bold",
                    color=ft.Colors.GREY_500,
                    italic=True,
                ),
                expansion_proyecto,
                expansion_prompts,
                expansion_tts,
                expansion_whisperx,
                expansion_ai_studio,
                expansion_flow,
            ],
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    col_central = ft.Container(
        width=320,
        padding=ft.padding.symmetric(horizontal=8, vertical=16),
        content=ft.Column(
            [
                ft.Text(
                    "Pipeline de Ejecución",
                    size=12,
                    weight="bold",
                    color=ft.Colors.GREY_500,
                    italic=True,
                ),
                ft.Divider(),
                txt_proximo,
                ft.Divider(),
                btn_ejecutar_widget,
                txt_alcance_flujo,
                btn_detener,
                prg,
                ft.Divider(),
                ft.Text(
                    "Estado del flujo",
                    size=12,
                    weight="bold",
                    color=ft.Colors.GREY_500,
                ),
                tracker_widget,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    col_derecha = ft.Container(
        expand=True,
        padding=ft.padding.only(left=8, top=16, right=16, bottom=16),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.TERMINAL, color=ft.Colors.GREY_500, size=16),
                                ft.Text(
                                    "Consola de ejecución",
                                    size=12,
                                    weight="bold",
                                    color=ft.Colors.GREY_500,
                                ),
                            ],
                            spacing=6,
                        ),
                        btn_limpiar_log,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                log_container,
                ft.Divider(),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.IMAGE_OUTLINED, color=ft.Colors.GREY_500, size=14),
                        ft.Text("Estado de imágenes", size=11, color=ft.Colors.GREY_500),
                    ],
                    spacing=4,
                ),
                lbl_imagen_status_sidebar,
            ],
            spacing=8,
            expand=True,
        ),
    )

    if state.ruta_base[0]:
        txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(state.ruta_base[0])}"

    actualizar_ext_status_header(
        bool(ws_bridge.extension_bridge_state.get("connected")),
        ws_bridge.extension_bridge_state.get("version") or "",
    )
    reset_tracker()
    actualizar_resumen_alcance()
    refrescar_journeys_ui()

    page.add(
        header_bar,
        ft.Row(
            [
                col_izquierda,
                ft.Container(
                    width=1,
                    bgcolor=ft.Colors.GREY_200,
                    margin=ft.margin.symmetric(vertical=16),
                ),
                col_central,
                ft.Container(
                    width=1,
                    bgcolor=ft.Colors.GREY_200,
                    margin=ft.margin.symmetric(vertical=16),
                ),
                col_derecha,
            ],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
    )
    refrescar_canales()