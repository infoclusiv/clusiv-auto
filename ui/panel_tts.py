import os
import threading

import flet as ft

from config import NVIDIA_API_KEY, guardar_config, normalizar_tts_config
from tts_nvidia import sintetizar_script_a_audio_nvidia
from youtube_analyzer import obtener_ultimo_video


def build_panel_tts(page, state, log_msg):
    tts_config = state.tts_config
    ruta_base = state.ruta_base

    def show_snack(msg, color=ft.Colors.GREEN):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), bgcolor=color))
        page.overlay[-1].open = True
        page.update()

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

    def guardar_tts():
        guardar_config(tts=tts_config)

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

    expansion_tts = ft.ExpansionTile(
        title=ft.Text("🔊 Síntesis de Voz - NVIDIA TTS", weight="bold", size=13),
        subtitle=ft.Text(
            "Genera audio.wav desde script.txt (Fase 3)",
            size=11,
            color=ft.Colors.GREY_600,
        ),
        expanded=False,
        controls=[
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
                "Voz válida: Magpie-Multilingual.EN-US.Aria",
                size=11,
                color=ft.Colors.GREY_600,
                italic=True,
            ),
        ],
    )

    def get_tts_config():
        return tts_config

    return expansion_tts, get_tts_config
