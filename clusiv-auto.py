import flet as ft
import os
import re
import json
import sqlite3
import time
import random
import threading
import asyncio
import subprocess
import sys
import websockets
import wave
import pyautogui
import pygetwindow as gw
import webbrowser
import pyperclip
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from dotenv import load_dotenv

# --- 1. CONFIGURACIÓN Y RUTAS ---
load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

# Ruta de la aplicación ChatGPT (Chrome App)
PATH_CHATGPT = r"C:\Users\carlo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Aplicaciones de Chrome\ChatGPT.lnk"

CONFIG_FILE = "config_automatizacion.json"
DATABASE_FILE = "channels.db"
NVIDIA_TTS_SERVER = "grpc.nvcf.nvidia.com:443"
NVIDIA_MAGPIE_TTS_FUNCTION_ID = "877104f7-e885-42b9-8de8-f6e4c6303969"
NVIDIA_GRPC_MAX_MESSAGE_BYTES = 32 * 1024 * 1024

# PROMPTS POR DEFECTO
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
        sample_rate_hz = int(normalizado.get("sample_rate_hz", defaults["sample_rate_hz"]))
    except (TypeError, ValueError):
        sample_rate_hz = defaults["sample_rate_hz"]
    if sample_rate_hz <= 0:
        sample_rate_hz = defaults["sample_rate_hz"]
    normalizado["sample_rate_hz"] = sample_rate_hz

    return normalizado


# --- 2. GESTIÓN DE CONFIGURACIÓN Y BASE DE DATOS ---
def guardar_config(ruta=None, prompts=None, tts=None):
    config = cargar_toda_config()
    if ruta is not None:
        config["ruta_proyectos"] = ruta
    if prompts is not None:
        config["prompts"] = prompts
    if tts is not None:
        config["tts"] = normalizar_tts_config(tts)
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
            # Migración automática del formato legacy
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
                # Migración de campos antibot para prompts existentes
                for p in conf["prompts"]:
                    if "antibot" not in p:
                        p["antibot"] = True
                        migrado = True
                    if "wpm_escritura" not in p:
                        p["wpm_escritura"] = 200
                        migrado = True

            tts_normalizado = normalizar_tts_config(conf.get("tts"))
            if conf.get("tts") != tts_normalizado:
                conf["tts"] = tts_normalizado
                migrado = True

            if migrado:
                with open(CONFIG_FILE, "w", encoding="utf-8") as fw:
                    json.dump(conf, fw, indent=4, ensure_ascii=False)
            return conf
    return {
        "ruta_proyectos": "",
        "prompts": list(PROMPTS_DEFAULT),
        "tts": obtener_tts_config_default(),
    }


def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute("""CREATE TABLE IF NOT EXISTS channels 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      channel_id TEXT UNIQUE NOT NULL, 
                      channel_name TEXT NOT NULL, 
                      category TEXT DEFAULT 'Noticias')""")
    conn.commit()
    conn.close()


def obtener_canales_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_id, channel_name, category FROM channels ORDER BY category"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def agregar_canal_db(ch_id, ch_name):
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        conn.execute(
            "INSERT INTO channels (channel_id, channel_name) VALUES (?, ?)",
            (ch_id.strip(), ch_name.strip()),
        )
        conn.commit()
        return True, f"Canal '{ch_name}' guardado."
    except sqlite3.IntegrityError:
        return False, "El ID del canal ya existe."
    finally:
        conn.close()


def eliminar_canal_db(ch_id):
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute("DELETE FROM channels WHERE channel_id = ?", (ch_id,))
    conn.commit()
    conn.close()


def validar_texto_para_tts(texto):
    texto_limpio = (texto or "").strip()
    if not texto_limpio:
        return False, "script.txt está vacío."
    if len(texto_limpio) < 40:
        return False, "script.txt es demasiado corto para sintetizar audio útil."

    artefactos = [
        "your full script here",
        "do not write anything after",
        "do not write anything before",
        "<<<start_teleprompter_script>>>",
        "<<<end_teleprompter_script>>>",
    ]
    texto_lower = texto_limpio.lower()
    for artefacto in artefactos:
        if artefacto in texto_lower:
            return False, "script.txt todavía contiene artefactos del prompt."

    return True, None


def dividir_texto_para_tts(texto, max_chars=1400):
    bloques = []
    actual = ""

    def agregar_bloque(segmento):
        nonlocal actual
        segmento = segmento.strip()
        if not segmento:
            return
        separador = "\n\n" if actual else ""
        if len(actual) + len(separador) + len(segmento) <= max_chars:
            actual = f"{actual}{separador}{segmento}"
        else:
            if actual:
                bloques.append(actual.strip())
            actual = segmento

    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]

    for parrafo in parrafos:
        if len(parrafo) <= max_chars:
            agregar_bloque(parrafo)
            continue

        frases = re.split(r"(?<=[.!?])\s+", parrafo)
        frase_actual = ""
        for frase in frases:
            frase = frase.strip()
            if not frase:
                continue
            separador = " " if frase_actual else ""
            if len(frase_actual) + len(separador) + len(frase) <= max_chars:
                frase_actual = f"{frase_actual}{separador}{frase}"
                continue

            if frase_actual:
                agregar_bloque(frase_actual)
                frase_actual = ""

            if len(frase) <= max_chars:
                frase_actual = frase
                continue

            palabras = frase.split()
            segmento = ""
            for palabra in palabras:
                separador_palabra = " " if segmento else ""
                if len(segmento) + len(separador_palabra) + len(palabra) <= max_chars:
                    segmento = f"{segmento}{separador_palabra}{palabra}"
                else:
                    agregar_bloque(segmento)
                    segmento = palabra
            if segmento:
                agregar_bloque(segmento)

        if frase_actual:
            agregar_bloque(frase_actual)

    if actual:
        bloques.append(actual.strip())

    return bloques or [texto.strip()]


def guardar_audio_pcm_como_wav(ruta_salida, audio_pcm, sample_rate_hz, silencio_ms=250):
    silencio_frames = int(sample_rate_hz * (silencio_ms / 1000.0))
    silencio = b"\x00\x00" * silencio_frames

    with wave.open(ruta_salida, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)

        total = len(audio_pcm)
        for idx, chunk in enumerate(audio_pcm):
            wav_file.writeframes(chunk)
            if idx < total - 1 and silencio:
                wav_file.writeframes(silencio)


def resolver_python_para_tts():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidatos = [
        os.path.join(base_dir, ".venv", "Scripts", "python.exe"),
        os.path.join(base_dir, ".venv", "bin", "python"),
        sys.executable,
    ]

    for candidato in candidatos:
        if candidato and os.path.exists(candidato):
            return candidato

    return sys.executable


def sintetizar_script_a_audio_nvidia_via_standalone(carpeta_proyecto, tts_config):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    python_tts = resolver_python_para_tts()
    script_tts = os.path.join(base_dir, "test_nvidia_tts.py")

    if not os.path.exists(script_tts):
        return False, "No se encontró test_nvidia_tts.py para el fallback TTS.", None

    cmd = [
        python_tts,
        script_tts,
        "--project-dir",
        carpeta_proyecto,
        "--voice",
        tts_config["voice"],
        "--language-code",
        tts_config["language_code"],
        "--output",
        tts_config["output_filename"],
        "--sample-rate-hz",
        str(tts_config["sample_rate_hz"]),
        "--json-output",
    ]

    try:
        resultado = subprocess.run(
            cmd,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as ex:
        return False, f"No se pudo lanzar el fallback TTS: {str(ex)}", None

    salida = (resultado.stdout or "").strip()
    error = (resultado.stderr or "").strip()
    payload = None

    if salida:
        ultima_linea = salida.splitlines()[-1].strip()
        try:
            payload = json.loads(ultima_linea)
        except json.JSONDecodeError:
            payload = None

    if payload:
        return payload.get("ok", False), payload.get("msg", "Sin mensaje"), payload.get("path")

    if resultado.returncode == 0:
        ruta_audio = os.path.join(carpeta_proyecto, tts_config["output_filename"])
        return True, "Audio generado por fallback TTS.", ruta_audio

    detalle = error or salida or "Error desconocido en fallback TTS."
    return False, f"Fallback TTS falló: {detalle}", None


def sintetizar_script_a_audio_nvidia(carpeta_proyecto, tts_config):
    tts_config = normalizar_tts_config(tts_config)

    if tts_config.get("provider") != "nvidia":
        return False, "Proveedor TTS no soportado actualmente.", None

    if not NVIDIA_API_KEY:
        return False, "Falta NVIDIA_API_KEY en .env.", None

    ruta_script = os.path.join(carpeta_proyecto, "script.txt")
    if not os.path.exists(ruta_script):
        return False, "No se encontró script.txt para sintetizar.", None

    with open(ruta_script, "r", encoding="utf-8") as f:
        texto = f.read()

    valido, error_validacion = validar_texto_para_tts(texto)
    if not valido:
        return False, error_validacion, None

    try:
        import riva.client
    except ImportError:
        return sintetizar_script_a_audio_nvidia_via_standalone(
            carpeta_proyecto,
            tts_config,
        )

    chunks = dividir_texto_para_tts(texto)
    if not chunks:
        return False, "No se pudo dividir el texto para síntesis.", None

    try:
        auth = riva.client.Auth(
            uri=NVIDIA_TTS_SERVER,
            use_ssl=True,
            metadata_args=[
                ["function-id", NVIDIA_MAGPIE_TTS_FUNCTION_ID],
                ["authorization", f"Bearer {NVIDIA_API_KEY}"],
            ],
            options=[
                ("grpc.max_receive_message_length", NVIDIA_GRPC_MAX_MESSAGE_BYTES),
                ("grpc.max_send_message_length", NVIDIA_GRPC_MAX_MESSAGE_BYTES),
            ],
        )
        service = riva.client.SpeechSynthesisService(auth)

        audios_pcm = []
        for chunk in chunks:
            response = service.synthesize(
                text=chunk,
                voice_name=tts_config["voice"],
                language_code=tts_config["language_code"],
                sample_rate_hz=tts_config["sample_rate_hz"],
                encoding=riva.client.AudioEncoding.LINEAR_PCM,
            )
            if not getattr(response, "audio", None):
                return False, "NVIDIA devolvió audio vacío.", None
            audios_pcm.append(response.audio)

        ruta_audio = os.path.join(carpeta_proyecto, tts_config["output_filename"])
        guardar_audio_pcm_como_wav(
            ruta_audio,
            audios_pcm,
            tts_config["sample_rate_hz"],
        )
        return (
            True,
            f"Audio generado correctamente en {tts_config['output_filename']} ({len(chunks)} fragmento(s)).",
            ruta_audio,
        )
    except Exception as ex:
        return False, f"Error NVIDIA TTS: {str(ex)}", None


# --- 2.5 FUNCIONES ANTI-BOT ---
def escribir_humanizado(texto, wpm=45, stop_event=None):
    """Router principal de escritura. Selecciona estrategia según WPM.

    Tiers:
      20-50  WPM → Carácter por carácter (máximo stealth)
      51-120 WPM → Palabra por palabra via clipboard
      121-300 WPM → Chunks de líneas via clipboard
      301-500 WPM → Paste directo con micro-pausa
    """
    if wpm >= 301:
        return _escribir_paste_directo(texto, stop_event)
    elif wpm >= 121:
        return _escribir_por_chunks_linea(texto, wpm, stop_event)
    elif wpm >= 51:
        return _escribir_por_palabras(texto, wpm, stop_event)
    else:
        return _escribir_caracter(texto, wpm, stop_event)


def _escribir_caracter(texto, wpm=45, stop_event=None):
    """Tier 🐢 Stealth (20-50 WPM): Carácter por carácter.
    Multiplicadores REDUCIDOS vs la versión original para que sea más fiel al WPM real."""
    wpm_real = wpm * random.uniform(0.9, 1.1)
    base_delay = 60.0 / (wpm_real * 5)
    for char in texto:
        if stop_event and stop_event.is_set():
            return False
        if char == " ":
            time.sleep(random.uniform(base_delay * 1.0, base_delay * 1.5))
            pyautogui.press("space")
        elif char == "\n":
            time.sleep(random.uniform(base_delay * 1.2, base_delay * 2.0))
            pyautogui.press("enter")
        elif char == "\t":
            time.sleep(random.uniform(base_delay * 0.3, base_delay * 0.6))
            pyautogui.press("tab")
        else:
            time.sleep(random.uniform(base_delay * 0.6, base_delay * 1.1))
            if char.isascii() and char.isprintable():
                pyautogui.typewrite(char, interval=0)
            else:
                try:
                    pyperclip.copy(char)
                    pyautogui.hotkey("ctrl", "v")
                except Exception:
                    pass
    return True


def _escribir_por_palabras(texto, wpm=80, stop_event=None):
    """Tier 🚶 Normal (51-120 WPM): Palabra por palabra via clipboard.
    Cada palabra se pega con Ctrl+V, luego espacio/newline se teclea manual.
    Mucho más rápido que char-by-char porque clipboard es instantáneo."""

    tokens = re.split(r"(\s)", texto)
    palabra_delay = 60.0 / wpm

    for token in tokens:
        if stop_event and stop_event.is_set():
            return False

        if token == "":
            continue
        elif token == " ":
            time.sleep(random.uniform(palabra_delay * 0.1, palabra_delay * 0.3))
            pyautogui.press("space")
        elif token == "\n":
            time.sleep(random.uniform(palabra_delay * 0.2, palabra_delay * 0.5))
            pyautogui.press("enter")
        elif token == "\t":
            time.sleep(random.uniform(palabra_delay * 0.05, palabra_delay * 0.15))
            pyautogui.press("tab")
        elif token.strip() == "":
            for ch in token:
                if stop_event and stop_event.is_set():
                    return False
                pyautogui.press("space")
                time.sleep(random.uniform(0.01, 0.05))
        else:
            time.sleep(random.uniform(palabra_delay * 0.3, palabra_delay * 0.8))
            pyperclip.copy(token)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(random.uniform(0.02, 0.06))

    return True


def _escribir_por_chunks_linea(texto, wpm=200, stop_event=None):
    """Tier 🏃 Rápido (121-300 WPM): Chunks de líneas/frases via clipboard.
    Pega líneas completas con pausas breves entre ellas."""

    lineas = texto.split("\n")
    line_delay = max(0.05, 60.0 / wpm)

    for i, linea in enumerate(lineas):
        if stop_event and stop_event.is_set():
            return False

        if linea:
            pyperclip.copy(linea)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(random.uniform(0.02, 0.08))

        if i < len(lineas) - 1:
            time.sleep(random.uniform(line_delay * 0.5, line_delay * 1.2))
            pyautogui.press("enter")

    return True


def _escribir_paste_directo(texto, stop_event=None):
    """Tier ⚡ Turbo (301-500 WPM): Paste directo completo.
    Pega todo el texto de una vez. Máxima velocidad, mínimo stealth."""
    if stop_event and stop_event.is_set():
        return False

    pyperclip.copy(texto)
    time.sleep(random.uniform(0.1, 0.3))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(random.uniform(0.1, 0.3))

    return True


def espera_humanizada(segundos, stop_event=None):
    """Espera con variación aleatoria ±20% y decimales.
    Fragmenta la espera en intervalos de 0.5s para permitir cancelación."""
    total = random.uniform(segundos * 0.8, segundos * 1.2)
    elapsed = 0.0
    while elapsed < total:
        if stop_event and stop_event.is_set():
            return False
        chunk = min(0.5, total - elapsed)
        time.sleep(chunk)
        elapsed += chunk
    return True


def scroll_simulado(stop_event=None):
    """Simula scroll aleatorio de lectura/atención.
    Se detiene si stop_event está activado."""
    veces = random.randint(1, 3)
    for _ in range(veces):
        if stop_event and stop_event.is_set():
            return False
        pyautogui.scroll(random.choice([-3, -2, -1, 1, 2, 3]))
        time.sleep(random.uniform(0.3, 0.8))
    return True


def sleep_cancelable(segundos, stop_event=None):
    """time.sleep fragmentado que permite cancelación."""
    elapsed = 0.0
    while elapsed < segundos:
        if stop_event and stop_event.is_set():
            return False
        chunk = min(0.5, segundos - elapsed)
        time.sleep(chunk)
        elapsed += chunk
    return True


# --- 3. LÓGICA DE YOUTUBE Y CARPETAS ---
def analizar_rendimiento_canal(channel_id):
    if not YOUTUBE_API_KEY:
        return None
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        fecha_limite = (
            (datetime.now(timezone.utc) - timedelta(days=15))
            .isoformat()
            .replace("+00:00", "Z")
        )
        search_res = (
            youtube.search()
            .list(
                part="id",
                channelId=channel_id,
                publishedAfter=fecha_limite,
                type="video",
                maxResults=50,
                order="date",
            )
            .execute()
        )
        video_ids = [item["id"]["videoId"] for item in search_res.get("items", [])]
        if not video_ids:
            return None
        stats_res = (
            youtube.videos()
            .list(part="snippet,statistics", id=",".join(video_ids))
            .execute()
        )
        videos_data = [
            {
                "title": i["snippet"]["title"],
                "views": int(i["statistics"].get("viewCount", 0)),
            }
            for i in stats_res.get("items", [])
        ]
        if not videos_data:
            return None
        avg = sum(v["views"] for v in videos_data) / len(videos_data)
        ganadores = sorted(
            [v for v in videos_data if v["views"] > avg],
            key=lambda x: x["views"],
            reverse=True,
        )
        return {"avg": avg, "ganadores": ganadores}
    except:
        return None


def obtener_siguiente_num(ruta_base):
    if not ruta_base or not os.path.exists(ruta_base):
        return 1
    carpetas = [
        d for d in os.listdir(ruta_base) if os.path.isdir(os.path.join(ruta_base, d))
    ]
    nums = [
        int(m.group(1))
        for c in carpetas
        if (m := re.search(r"video\s*(\d+)", c, re.IGNORECASE))
    ]
    return max(nums) + 1 if nums else 1


def obtener_ultimo_video(ruta_base):
    """Busca y retorna la ruta de la carpeta del último video generado."""
    if not ruta_base or not os.path.exists(ruta_base):
        return None
    carpetas = [d for d in os.listdir(ruta_base) if os.path.isdir(os.path.join(ruta_base, d))]
    nums = [int(m.group(1)) for c in carpetas if (m := re.search(r"video\s*(\d+)", c, re.IGNORECASE))]
    if not nums:
        return None
    return os.path.join(ruta_base, f"video {max(nums)}")


# ==========================================
# --- SERVIDOR WEBSOCKET PARA LA EXTENSIÓN ---
# ==========================================
active_ws_connection = None
ws_loop = None
available_journeys = []
pending_journey_chain = {
    "active": False,
    "first_journey_id": None,
    "second_journey_id": None,
    "second_sent": False,
}

# Callbacks globales para interactuar con la UI de Flet desde el hilo asíncrono
ui_update_journeys_cb = None
ui_log_cb = None


def reset_pending_journey_chain():
    pending_journey_chain["active"] = False
    pending_journey_chain["first_journey_id"] = None
    pending_journey_chain["second_journey_id"] = None
    pending_journey_chain["second_sent"] = False


def set_pending_journey_chain(first_journey_id, second_journey_id):
    pending_journey_chain["active"] = True
    pending_journey_chain["first_journey_id"] = first_journey_id
    pending_journey_chain["second_journey_id"] = second_journey_id
    pending_journey_chain["second_sent"] = False


def journey_chain_matches_first(journey_id):
    first_journey_id = pending_journey_chain["first_journey_id"]
    return not journey_id or journey_id == first_journey_id


def is_paste_completion_signal(data):
    status = (data.get("status") or "").lower()
    event = (data.get("event") or "").lower()
    phase = (data.get("phase") or "").lower()
    msg = (data.get("message") or "").lower()

    explicit_signals = {"paste_completed", "paste_done", "pasted"}
    if status in explicit_signals or event in explicit_signals or phase in explicit_signals:
        return True

    return "paste" in msg and any(token in msg for token in ("completed", "done", "finished", "pegado"))


def dispatch_second_journey(trigger_label):
    if not pending_journey_chain["active"] or pending_journey_chain["second_sent"]:
        return False

    second_journey_id = pending_journey_chain["second_journey_id"]
    if not second_journey_id:
        reset_pending_journey_chain()
        return False

    payload = {
        "action": "RUN_JOURNEY",
        "journey_id": second_journey_id,
        "triggered_by": trigger_label,
    }

    if not send_ws_msg(payload):
        if ui_log_cb:
            ui_log_cb(
                "❌ No se pudo disparar la segunda automatización porque la extensión no está conectada.",
                color=ft.Colors.RED,
            )
        reset_pending_journey_chain()
        return False

    pending_journey_chain["second_sent"] = True
    if ui_log_cb:
        ui_log_cb(
            "🔁 Segunda automatización enviada a la extensión.",
            color=ft.Colors.BLUE_800,
            weight="bold",
        )
    reset_pending_journey_chain()
    return True

async def ws_handler(websocket):
    global active_ws_connection, available_journeys
    active_ws_connection = websocket

    if ui_log_cb:
        ui_log_cb("🟢 Extensión web conectada al orquestador", color=ft.Colors.GREEN_700, weight="bold")

    try:
        async for message in websocket:
            data = json.loads(message)
            accion = data.get("action")

            if accion == "JOURNEYS_LIST":
                available_journeys = data.get("data", [])
                if ui_update_journeys_cb:
                    ui_update_journeys_cb()

            elif accion == "JOURNEY_STATUS":
                status = data.get("status")
                msg = data.get("message", "")
                if status == "completed":
                    if ui_log_cb: ui_log_cb(f"✅ {msg}", color=ft.Colors.GREEN_700, weight="bold")
                elif status == "error":
                    if ui_log_cb: ui_log_cb(f"❌ Extensión: {msg}", color=ft.Colors.RED)
                elif status == "started":
                    if ui_log_cb: ui_log_cb(f"🚀 {msg}", color=ft.Colors.PURPLE_700, weight="bold")
                else:
                    if ui_log_cb: ui_log_cb(f"▶ {msg}", color=ft.Colors.BLUE_700)

                if pending_journey_chain["active"] and not pending_journey_chain["second_sent"]:
                    if status == "error" and journey_chain_matches_first(data.get("journey_id")):
                        reset_pending_journey_chain()
                    elif journey_chain_matches_first(data.get("journey_id")) and is_paste_completion_signal(data):
                        dispatch_second_journey("paste_completed")
                    elif status == "completed" and journey_chain_matches_first(data.get("journey_id")):
                        if ui_log_cb:
                            ui_log_cb(
                                "⚠ El primer journey terminó, pero la extensión no envió una señal explícita de pegado completado. La segunda automatización queda cancelada hasta que la extensión emita 'paste_completed'.",
                                color=ft.Colors.ORANGE_700,
                            )
                        reset_pending_journey_chain()
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        active_ws_connection = None
        reset_pending_journey_chain()
        if ui_log_cb:
            ui_log_cb("🔴 Extensión web desconectada. Esperando reconexión...", color=ft.Colors.ORANGE_700, weight="bold")

def start_ws_server():
    """Inicia el servidor WS en un hilo separado con su propio event loop"""
    global ws_loop
    
    async def runner():
        async with websockets.serve(ws_handler, "localhost", 8765):
            await asyncio.Future()  # Mantiene el loop corriendo indefinidamente
            
    ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(ws_loop)
    ws_loop.run_until_complete(runner())

def send_ws_msg(msg_dict):
    """Envía comandos a la extensión de forma segura desde otros hilos"""
    if active_ws_connection and ws_loop:
        asyncio.run_coroutine_threadsafe(
            active_ws_connection.send(json.dumps(msg_dict)), ws_loop
        )
        return True
    return False

# Iniciar servidor WebSocket en un hilo daemon al cargar el módulo
threading.Thread(target=start_ws_server, daemon=True).start()


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
    tts_config = normalizar_tts_config(config_actual.get("tts"))

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

    global ui_log_cb
    ui_log_cb = log_msg

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
        guardar_config(prompts=prompts_lista)

    def guardar_tts():
        guardar_config(tts=tts_config)

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

    def extraer_respuesta_automatica(antibot=False):
        try:
            if stop_event.is_set():
                return None

            windows = [w for w in gw.getAllWindows() if "ChatGPT" in w.title]
            if not windows:
                return None

            ventana = windows[0]
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

    # --- FLUJO PRINCIPAL (basado en lista de prompts) ---
    def ejecutar_flujo_completo(e):
        if not ruta_base[0]:
            show_snack("Selecciona una ruta de proyectos", ft.Colors.RED)
            return
        if not YOUTUBE_API_KEY:
            show_snack("Falta API KEY en .env", ft.Colors.RED)
            return

        habilitados = [p for p in prompts_lista if p.get("habilitado", True)]
        if not habilitados:
            show_snack("No hay prompts habilitados", ft.Colors.RED)
            return

        # Limpiar señal de cancelación y preparar UI
        stop_event.clear()
        log_ui.controls.clear()
        prg.visible = True
        set_estado_ejecutando(True)
        page.update()
        log_msg("🚀 Iniciando flujo completo...", italic=True)

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

                for idx, p in enumerate(habilitados):
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
                        f"🌐 [{idx + 1}/{len(habilitados)}] Enviando: {nombre_prompt}{ab_tag}...",
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
                    if idx < len(habilitados) - 1:
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
                            else:
                                log_msg(f"⚠ {tts_msg}", color=ft.Colors.ORANGE_700)
                    else:
                        log_msg(f"⚠ {mensaje}", color=ft.Colors.ORANGE_700)

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
            for j in available_journeys
        ]
        secondary_options = [
            ft.dropdown.Option(key=j["id"], text=j["name"])
            for j in available_journeys
        ]
        valid_ids = {j["id"] for j in available_journeys}
        dropdown_journeys.options = primary_options
        dropdown_second_journey.options = secondary_options

        if current_primary in valid_ids:
            dropdown_journeys.value = current_primary
        elif available_journeys:
            dropdown_journeys.value = available_journeys[0]["id"]

        if current_secondary in valid_ids:
            dropdown_second_journey.value = current_secondary
        elif current_secondary:
            dropdown_second_journey.value = None

        page.update()
        
    global ui_update_journeys_cb
    ui_update_journeys_cb = refrescar_journeys_ui

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
    page.overlay.append(picker)

    page.add(
        ft.Row([
                ft.Text("Clusiv", size=32, weight="bold", color=ft.Colors.BLUE_800),
                ft.Text("Automation", size=32),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        ft.ResponsiveRow([tile_gestion, tile_flujo, tile_config, tile_web_extension]),
        ft.ResponsiveRow([tile_prompts]),
    )
    refrescar_canales()
    refrescar_prompts()


if __name__ == "__main__":
    ft.app(target=main)