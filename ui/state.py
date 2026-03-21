import threading

from config import (
    cargar_toda_config,
    normalizar_ai_studio_config,
    normalizar_ejecutar_hasta_prompt,
    normalizar_tts_config,
    obtener_whisperx_config_default,
)
from database import init_db


class AppState:
    def __init__(self):
        init_db()
        config_actual = cargar_toda_config()

        self.config_actual = config_actual
        self.ruta_base = [config_actual["ruta_proyectos"]]
        self.prompts_lista = config_actual["prompts"]
        self.ejecutar_hasta_prompt = [
            normalizar_ejecutar_hasta_prompt(
                config_actual.get("ejecutar_hasta_prompt"),
                config_actual["prompts"],
            )
        ]
        self.tts_config = normalizar_tts_config(config_actual.get("tts"))
        self.whisperx_config = config_actual.get(
            "whisperx", obtener_whisperx_config_default()
        )
        self.ai_studio_config = normalizar_ai_studio_config(
            config_actual.get("ai_studio"),
            config_actual.get("prompt_ai_studio"),
        )
        self.config_actual["ejecutar_hasta_prompt"] = self.ejecutar_hasta_prompt[0]
        self.config_actual["ai_studio"] = dict(self.ai_studio_config)
        self.config_actual["prompt_ai_studio"] = self.ai_studio_config["prompt"]

        self.ref_image_paths_state = []
        self.stop_event = threading.Event()
