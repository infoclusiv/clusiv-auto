import json
import os

from dotenv import load_dotenv


load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

PATH_CHATGPT = r"C:\Users\carlo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Aplicaciones de Chrome\ChatGPT.lnk"
PATH_AI_STUDIO = r"C:\Users\carlo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Aplicaciones de Chrome\Google AI Studio.lnk"
PROMPT_AI_STUDIO_SCRIPT_PLACEHOLDER = "[PEGAR TU GUION AQUÍ]"
AI_STUDIO_OUTPUT_FILENAME_DEFAULT = "prompts_imagenes.txt"
AI_STUDIO_WINDOW_TITLES = ("Google AI Studio", "AI Studio", "Gemini")
FLOW_LABS_URL = "https://labs.google/fx/tools/flow"

CONFIG_FILE = "config_automatizacion.json"
DATABASE_FILE = "channels.db"
NVIDIA_TTS_SERVER = "grpc.nvcf.nvidia.com:443"
NVIDIA_MAGPIE_TTS_FUNCTION_ID = "877104f7-e885-42b9-8de8-f6e4c6303969"
NVIDIA_GRPC_MAX_MESSAGE_BYTES = 32 * 1024 * 1024

PROMPT_DEFAULT = """**Act as a senior YouTube Growth Strategist and expert Copywriter.**

I have a specific video title that performed exceptionally well on my channel. I need you to reverse-engineer its success and use those insights to create better, high-CTR variations in English.

**The successful title (in Spanish) was:**
[REF_TITLE]

**Please complete the following two steps:**

**STEP 1: The Analysis**
Briefly analyze **why** this title worked effectively. Identify the psychological triggers (e.g., fear, urgency, curiosity, high stakes) and the power keywords used. Explain the "hook" mechanism behind it.

**STEP 2: The Proposal**
Based on your analysis, generate **1 new high-performing title variation in ENGLISH**.

**CRITICAL INSTRUCTION FOR STEP 2:**
You must provide the title strictly inside this structure so I can parse it:
[FINAL_TITLE: Put the generated title here]

**Guidelines for the new title:**
1.  **Language:** All titles must be in **English**.
2.  **Psychology:** Leverage the "Curiosity Gap" or "Urgency" triggers.
3.  **Structure:** Use "Front-loading" (put the most impactful words at the beginning).
4.  **Length:** Keep them concise (optimized for mobile)."""

PROMPT_INVESTIGACION_DEFAULT = """I want you to follow these steps.
Step 1:
Based on the following title for a youtube video, generate an outline with 5 key questions that explore its central theme. The outline and questions should be structured in a way that keeps people's attention, as it will be used to create a video script. For this reason, it is necessary to begin with the most important and pressing question for the audience, followed by questions that help dive deeper into the content.
For each of these questions, conduct research using reputable web sources that provide verified information, such as:

nytimes.com

washingtonpost.com

npr.org

bbc.com

axios.com

apnews.com

bloomberg.com

foxnews.com

news.yahoo.com

nbc.com

reuters.com

cnbc.com

wsj.com

foxbusiness.com

ft.com

economist.com

marketwatch.com

investing.com

edition.cnn.com

politico.com

usnews.com

propublica.org
You can also include scientific papers, indexed journals, or official U.S. government websites. Avoid social media, youtube, unverified blogs, and low-credibility content. Cross-check at least three reliable sources to confirm each relevant fact.

Title for a YouTube video:
[TITULO]"""

PROMPTS_DEFAULT = [
    {
        "nombre": "Generar Título",
        "texto": PROMPT_DEFAULT,
        "modo": "nueva",
        "espera_segundos": 30,
        "habilitado": True,
        "antibot": True,
        "wpm_escritura": 200,
        "post_accion": "extraer_titulo",
        "archivo_salida": "TITULO_FINAL.txt",
    },
    {
        "nombre": "Investigación (5 Key Questions)",
        "texto": PROMPT_INVESTIGACION_DEFAULT,
        "modo": "nueva",
        "espera_segundos": 60,
        "habilitado": True,
        "antibot": True,
        "wpm_escritura": 200,
        "post_accion": "guardar_respuesta",
        "archivo_salida": "RESPUESTA_INVESTIGACION.txt",
    },
]


def obtener_tts_config_default():
    return {
        "enabled": False,
        "provider": "nvidia",
        "language_code": "en-US",
        "voice": "Magpie-Multilingual.EN-US.Aria",
        "output_filename": "audio.wav",
        "sample_rate_hz": 44100,
    }


def obtener_whisperx_config_default():
    return {
        "enabled": False,
        "model": "medium",
        "python_path": r"C:\Users\carlo\miniconda3\envs\whisperx-env\python.exe",
        "runner_script": "whisperx_runner.py",
    }


def obtener_ai_studio_config_default():
    return {
        "prompt": "",
        "espera_respuesta_segundos": 15,
        "archivo_salida": AI_STUDIO_OUTPUT_FILENAME_DEFAULT,
        "auto_send_to_extension": False,
        "imagen_model": "imagen4",
        "imagen_aspect_ratio": "landscape",
        "imagen_count": 1,
    }


def obtener_cortes_validos_prueba(prompts):
    cortes = []
    for idx, prompt in enumerate(prompts, start=1):
        nombre = str(prompt.get("nombre", "")).strip().lower()
        if "teleprompter" in nombre:
            cortes.append(idx)

    total = len(prompts)
    if total and total not in cortes:
        cortes.append(total)

    return cortes


def normalizar_ejecutar_hasta_prompt(valor, prompts):
    total = len(prompts)
    if total <= 0:
        return 0

    try:
        valor_normalizado = int(valor or 0)
    except (TypeError, ValueError):
        valor_normalizado = 0

    if valor_normalizado <= 0 or valor_normalizado >= total:
        return 0

    cortes_validos = obtener_cortes_validos_prueba(prompts)
    if valor_normalizado in cortes_validos:
        return valor_normalizado

    cortes_menores = [corte for corte in cortes_validos if corte <= valor_normalizado]
    if cortes_menores:
        return max(cortes_menores)

    return cortes_validos[0] if cortes_validos else 0


def describir_alcance_prompts(prompts, ejecutar_hasta_prompt):
    total = len(prompts)
    if total <= 0:
        return "Sin prompts configurados"

    limite = normalizar_ejecutar_hasta_prompt(ejecutar_hasta_prompt, prompts)
    if limite == 0:
        return f"Flujo completo (1-{total})"

    return f"Prueba rápida (1-{limite} de {total})"


def normalizar_tts_config(tts_config):
    defaults = obtener_tts_config_default()
    normalizado = dict(defaults)

    if isinstance(tts_config, dict):
        for key, value in tts_config.items():
            if value is not None:
                normalizado[key] = value

    normalizado["enabled"] = bool(normalizado.get("enabled", defaults["enabled"]))

    provider = str(normalizado.get("provider", defaults["provider"])).strip().lower()
    normalizado["provider"] = provider or defaults["provider"]

    language_code = str(
        normalizado.get("language_code", defaults["language_code"])
    ).strip()
    normalizado["language_code"] = language_code or defaults["language_code"]

    voice = str(normalizado.get("voice", defaults["voice"])).strip()
    normalizado["voice"] = voice or defaults["voice"]

    output_filename = str(
        normalizado.get("output_filename", defaults["output_filename"])
    ).strip()
    if not output_filename:
        output_filename = defaults["output_filename"]
    if not output_filename.lower().endswith(".wav"):
        output_filename = f"{output_filename}.wav"
    normalizado["output_filename"] = output_filename

    try:
        sample_rate_hz = int(
            normalizado.get("sample_rate_hz", defaults["sample_rate_hz"])
        )
    except (TypeError, ValueError):
        sample_rate_hz = defaults["sample_rate_hz"]
    if sample_rate_hz <= 0:
        sample_rate_hz = defaults["sample_rate_hz"]
    normalizado["sample_rate_hz"] = sample_rate_hz

    return normalizado


def normalizar_ai_studio_config(ai_studio_config, prompt_ai_studio_legacy=None):
    defaults = obtener_ai_studio_config_default()
    normalizado = dict(defaults)

    if isinstance(ai_studio_config, dict):
        for key, value in ai_studio_config.items():
            if value is not None:
                normalizado[key] = value

    prompt_legacy = str(prompt_ai_studio_legacy or "").strip()

    prompt = str(normalizado.get("prompt", defaults["prompt"])).strip()
    if not prompt and prompt_legacy:
        prompt = prompt_legacy
    normalizado["prompt"] = prompt

    try:
        espera = int(
            normalizado.get(
                "espera_respuesta_segundos",
                defaults["espera_respuesta_segundos"],
            )
        )
    except (TypeError, ValueError):
        espera = defaults["espera_respuesta_segundos"]
    espera = max(1, min(300, espera))
    normalizado["espera_respuesta_segundos"] = espera

    archivo_salida = str(
        normalizado.get("archivo_salida", defaults["archivo_salida"])
    ).strip()
    if not archivo_salida:
        archivo_salida = defaults["archivo_salida"]
    if not archivo_salida.lower().endswith(".txt"):
        archivo_salida = f"{archivo_salida}.txt"
    normalizado["archivo_salida"] = archivo_salida

    normalizado["auto_send_to_extension"] = bool(
        normalizado.get("auto_send_to_extension", defaults["auto_send_to_extension"])
    )

    imagen_model = str(normalizado.get("imagen_model", defaults["imagen_model"])).strip()
    normalizado["imagen_model"] = imagen_model or defaults["imagen_model"]

    imagen_aspect_ratio = str(
        normalizado.get("imagen_aspect_ratio", defaults["imagen_aspect_ratio"])
    ).strip()
    normalizado["imagen_aspect_ratio"] = (
        imagen_aspect_ratio or defaults["imagen_aspect_ratio"]
    )

    try:
        imagen_count = int(normalizado.get("imagen_count", defaults["imagen_count"]))
    except (TypeError, ValueError):
        imagen_count = defaults["imagen_count"]
    imagen_count = max(1, min(4, imagen_count))
    normalizado["imagen_count"] = imagen_count

    return normalizado


def guardar_config(
    ruta=None,
    prompts=None,
    tts=None,
    whisperx=None,
    prompt_ai_studio=None,
    ai_studio=None,
    ejecutar_hasta_prompt=None,
):
    config = cargar_toda_config()
    if ruta is not None:
        config["ruta_proyectos"] = ruta
    if prompts is not None:
        config["prompts"] = prompts
    if tts is not None:
        config["tts"] = normalizar_tts_config(tts)
    if whisperx is not None:
        config["whisperx"] = whisperx
    if ai_studio is not None:
        config["ai_studio"] = normalizar_ai_studio_config(
            ai_studio,
            prompt_ai_studio_legacy=config.get("prompt_ai_studio"),
        )
        config["prompt_ai_studio"] = config["ai_studio"]["prompt"]
    if prompt_ai_studio is not None:
        config["prompt_ai_studio"] = str(prompt_ai_studio).strip()
        ai_studio_actual = normalizar_ai_studio_config(
            config.get("ai_studio"),
            prompt_ai_studio_legacy=config["prompt_ai_studio"],
        )
        ai_studio_actual["prompt"] = config["prompt_ai_studio"]
        config["ai_studio"] = ai_studio_actual
    if ejecutar_hasta_prompt is not None:
        config["ejecutar_hasta_prompt"] = ejecutar_hasta_prompt
    config["ejecutar_hasta_prompt"] = normalizar_ejecutar_hasta_prompt(
        config.get("ejecutar_hasta_prompt"),
        config.get("prompts", []),
    )
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def cargar_toda_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            conf = json.load(f)
            migrado = False
            if "ruta_proyectos" not in conf:
                conf["ruta_proyectos"] = ""
                migrado = True
            if "prompts" not in conf:
                prompts = []
                pt = conf.pop("prompt_template", PROMPT_DEFAULT)
                pi = conf.pop("prompt_investigacion", PROMPT_INVESTIGACION_DEFAULT)
                prompts.append(
                    {
                        "nombre": "Generar Título",
                        "texto": pt,
                        "modo": "nueva",
                        "espera_segundos": 30,
                        "habilitado": True,
                        "antibot": True,
                        "wpm_escritura": 200,
                        "post_accion": "extraer_titulo",
                        "archivo_salida": "TITULO_FINAL.txt",
                    }
                )
                prompts.append(
                    {
                        "nombre": "Investigación (5 Key Questions)",
                        "texto": pi,
                        "modo": "nueva",
                        "espera_segundos": 60,
                        "habilitado": True,
                        "antibot": True,
                        "wpm_escritura": 200,
                        "post_accion": "guardar_respuesta",
                        "archivo_salida": "RESPUESTA_INVESTIGACION.txt",
                    }
                )
                conf["prompts"] = prompts
                migrado = True
            else:
                for prompt in conf["prompts"]:
                    if "antibot" not in prompt:
                        prompt["antibot"] = True
                        migrado = True
                    if "wpm_escritura" not in prompt:
                        prompt["wpm_escritura"] = 200
                        migrado = True

            tts_normalizado = normalizar_tts_config(conf.get("tts"))
            if conf.get("tts") != tts_normalizado:
                conf["tts"] = tts_normalizado
                migrado = True

            if "whisperx" not in conf:
                conf["whisperx"] = obtener_whisperx_config_default()
                migrado = True

            ai_studio_normalizado = normalizar_ai_studio_config(
                conf.get("ai_studio"),
                prompt_ai_studio_legacy=conf.get("prompt_ai_studio"),
            )
            if conf.get("ai_studio") != ai_studio_normalizado:
                conf["ai_studio"] = ai_studio_normalizado
                migrado = True

            if conf.get("prompt_ai_studio") != ai_studio_normalizado["prompt"]:
                conf["prompt_ai_studio"] = ai_studio_normalizado["prompt"]
                migrado = True

            ejecutar_hasta_prompt = normalizar_ejecutar_hasta_prompt(
                conf.get("ejecutar_hasta_prompt"),
                conf.get("prompts", []),
            )
            if conf.get("ejecutar_hasta_prompt") != ejecutar_hasta_prompt:
                conf["ejecutar_hasta_prompt"] = ejecutar_hasta_prompt
                migrado = True

            if migrado:
                with open(CONFIG_FILE, "w", encoding="utf-8") as fw:
                    json.dump(conf, fw, indent=4, ensure_ascii=False)
            return conf
    return {
        "ruta_proyectos": "",
        "prompts": list(PROMPTS_DEFAULT),
        "tts": obtener_tts_config_default(),
        "whisperx": obtener_whisperx_config_default(),
        "ai_studio": obtener_ai_studio_config_default(),
        "prompt_ai_studio": "",
        "ejecutar_hasta_prompt": 0,
    }