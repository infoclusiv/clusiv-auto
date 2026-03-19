# Plan de implementación — Módulo 02: `config.py` + `database.py`

> **Proyecto:** Clusiv Automation  
> **Archivo origen:** `clusiv-auto.py`  
> **Objetivo:** Extraer (a) las constantes globales, defaults y lógica de configuración JSON a `config.py`, y (b) las funciones SQLite de canales a `database.py`. Actualizar `clusiv-auto.py` para importar desde ambos.  
> **Resultado esperado:** Comportamiento **100% idéntico**. Refactor puro de estructura.

---

## Contexto y decisión de diseño

El archivo original mezcla en su primera mitad (líneas 23–514) tres tipos de código que deben separarse:

1. **Constantes y valores por defecto** — API keys, rutas de apps, nombres de archivo, prompts por defecto, y funciones `obtener_*_default()`. Son la "verdad inmutable" del sistema.
2. **Lógica de configuración** — Funciones que leen/escriben `config_automatizacion.json` y normalizan sus valores (`cargar_toda_config`, `guardar_config`, `normalizar_*`). Dependen únicamente de las constantes.
3. **Acceso a base de datos** — Funciones SQLite para gestionar canales (`init_db`, `obtener_canales_db`, `agregar_canal_db`, `eliminar_canal_db`). No dependen de la configuración JSON en absoluto.

**Decisión:** Se crean **dos archivos separados** porque sus motivos de cambio son distintos. `config.py` cambia cuando se añaden nuevas opciones de configuración o se migra el esquema JSON. `database.py` cambia cuando se modifica el esquema de la tabla `channels` o se agrega una nueva tabla. Mezclarlos en un solo archivo crearía acoplamiento innecesario.

**Nota importante sobre las constantes NVIDIA, rutas y prompts:** Aunque constantes como `NVIDIA_API_KEY`, `PATH_CHATGPT`, `NVIDIA_TTS_SERVER`, `PROMPT_DEFAULT`, etc., serán definidas en `config.py`, **también se importan en `clusiv-auto.py`** porque módulos futuros (`tts_nvidia.py`, `chatgpt_automation.py`, `ai_studio.py`) aún no han sido extraídos y actualmente viven dentro de `clusiv-auto.py`. El import de estas constantes en `clusiv-auto.py` se resolverá de forma gradual conforme se extraigan esos módulos en planes futuros.

---

## Estructura de archivos esperada al finalizar

```
proyecto/
├── clusiv-auto.py          ← modificado (bloque de constantes/config/db reemplazado por imports)
├── antibot.py              ← ya existe (plan anterior)
├── config.py               ← nuevo archivo
├── database.py             ← nuevo archivo
└── ... (resto sin cambios)
```

---

## Paso 1 — Crear `config.py`

Crear el archivo `config.py` en la **misma carpeta raíz** del proyecto. Contenido exacto:

```python
"""
config.py
---------
Constantes globales, valores por defecto y gestión del archivo de
configuración JSON (config_automatizacion.json).

Constantes exportadas:
  YOUTUBE_API_KEY, NVIDIA_API_KEY
  PATH_CHATGPT, PATH_AI_STUDIO
  PROMPT_AI_STUDIO_SCRIPT_PLACEHOLDER, AI_STUDIO_OUTPUT_FILENAME_DEFAULT
  AI_STUDIO_WINDOW_TITLES, FLOW_LABS_URL
  CONFIG_FILE, DATABASE_FILE
  NVIDIA_TTS_SERVER, NVIDIA_MAGPIE_TTS_FUNCTION_ID, NVIDIA_GRPC_MAX_MESSAGE_BYTES
  PROMPT_DEFAULT, PROMPT_INVESTIGACION_DEFAULT, PROMPTS_DEFAULT

Funciones de defaults exportadas:
  obtener_tts_config_default()        → dict
  obtener_whisperx_config_default()   → dict
  obtener_ai_studio_config_default()  → dict

Funciones de normalización exportadas:
  normalizar_tts_config(tts_config)                                     → dict
  normalizar_ai_studio_config(ai_studio_config, prompt_ai_studio_legacy) → dict
  normalizar_ejecutar_hasta_prompt(valor, prompts)                       → int
  obtener_cortes_validos_prueba(prompts)                                  → list
  describir_alcance_prompts(prompts, ejecutar_hasta_prompt)               → str

Funciones de persistencia exportadas:
  cargar_toda_config()   → dict
  guardar_config(...)    → None
"""

import os
import json

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Carga de variables de entorno
# ---------------------------------------------------------------------------

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

# ---------------------------------------------------------------------------
# Rutas de aplicaciones externas
# ---------------------------------------------------------------------------

# Ruta de la aplicación ChatGPT (Chrome App)
PATH_CHATGPT = r"C:\Users\carlo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Aplicaciones de Chrome\ChatGPT.lnk"
# Ruta de acceso directo a Google AI Studio (Chrome App)
PATH_AI_STUDIO = r"C:\Users\carlo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Aplicaciones de Chrome\Google AI Studio.lnk"
PROMPT_AI_STUDIO_SCRIPT_PLACEHOLDER = "[PEGAR TU GUION AQUÍ]"
AI_STUDIO_OUTPUT_FILENAME_DEFAULT = "prompts_imagenes.txt"
AI_STUDIO_WINDOW_TITLES = ("Google AI Studio", "AI Studio", "Gemini")
FLOW_LABS_URL = "https://labs.google/fx/tools/flow"

# ---------------------------------------------------------------------------
# Archivos de datos
# ---------------------------------------------------------------------------

CONFIG_FILE = "config_automatizacion.json"
DATABASE_FILE = "channels.db"

# ---------------------------------------------------------------------------
# Constantes NVIDIA TTS
# ---------------------------------------------------------------------------

NVIDIA_TTS_SERVER = "grpc.nvcf.nvidia.com:443"
NVIDIA_MAGPIE_TTS_FUNCTION_ID = "877104f7-e885-42b9-8de8-f6e4c6303969"
NVIDIA_GRPC_MAX_MESSAGE_BYTES = 32 * 1024 * 1024

# ---------------------------------------------------------------------------
# Prompts por defecto
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Funciones de defaults
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Funciones de normalización y lógica de prompts
# ---------------------------------------------------------------------------

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
        sample_rate_hz = int(normalizado.get("sample_rate_hz", defaults["sample_rate_hz"]))
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

# ---------------------------------------------------------------------------
# Persistencia JSON
# ---------------------------------------------------------------------------

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

            # Migración: añadir sección whisperx si no existe
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
```

---

## Paso 2 — Crear `database.py`

Crear el archivo `database.py` en la misma carpeta raíz. Contenido exacto:

```python
"""
database.py
-----------
Gestión de la base de datos SQLite de canales de YouTube.

Funciones exportadas:
  init_db()                          → None
  obtener_canales_db()               → list[tuple]
  agregar_canal_db(ch_id, ch_name)   → tuple[bool, str]
  eliminar_canal_db(ch_id)           → None
"""

import sqlite3

from config import DATABASE_FILE

# ---------------------------------------------------------------------------
# Inicialización
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute("""CREATE TABLE IF NOT EXISTS channels 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      channel_id TEXT UNIQUE NOT NULL, 
                      channel_name TEXT NOT NULL, 
                      category TEXT DEFAULT 'Noticias')""")
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# CRUD de canales
# ---------------------------------------------------------------------------

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
```

---

## Paso 3 — Modificar `clusiv-auto.py`

### 3.1 — Reemplazar el bloque de imports

Localizar el bloque de imports actual al inicio del archivo (líneas 1–21). Reemplazarlo **en su totalidad** por el siguiente bloque. Las líneas de stdlib y terceros se conservan idénticas; solo se añaden los imports de los nuevos módulos al final:

```python
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
import shutil
import websockets
import wave
import pyautogui
import pygetwindow as gw
import webbrowser
import pyperclip
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from dotenv import load_dotenv
from antibot import (
    escribir_humanizado,
    espera_humanizada,
    scroll_simulado,
    sleep_cancelable,
)
from config import (
    YOUTUBE_API_KEY,
    NVIDIA_API_KEY,
    PATH_CHATGPT,
    PATH_AI_STUDIO,
    PROMPT_AI_STUDIO_SCRIPT_PLACEHOLDER,
    AI_STUDIO_OUTPUT_FILENAME_DEFAULT,
    AI_STUDIO_WINDOW_TITLES,
    FLOW_LABS_URL,
    CONFIG_FILE,
    DATABASE_FILE,
    NVIDIA_TTS_SERVER,
    NVIDIA_MAGPIE_TTS_FUNCTION_ID,
    NVIDIA_GRPC_MAX_MESSAGE_BYTES,
    PROMPT_DEFAULT,
    PROMPT_INVESTIGACION_DEFAULT,
    PROMPTS_DEFAULT,
    obtener_tts_config_default,
    obtener_whisperx_config_default,
    obtener_ai_studio_config_default,
    obtener_cortes_validos_prueba,
    normalizar_ejecutar_hasta_prompt,
    describir_alcance_prompts,
    normalizar_tts_config,
    normalizar_ai_studio_config,
    cargar_toda_config,
    guardar_config,
)
from database import (
    init_db,
    obtener_canales_db,
    agregar_canal_db,
    eliminar_canal_db,
)
```

### 3.2 — Eliminar el bloque de constantes, defaults y config/db de `clusiv-auto.py`

Localizar y **eliminar completamente** el bloque que va desde el comentario de sección 1 hasta el final de `eliminar_canal_db` (antes de `validar_texto_para_tts`).

**Inicio exacto del bloque a eliminar** (buscar esta línea):
```
# --- 1. CONFIGURACIÓN Y RUTAS ---
```

**Fin exacto del bloque a eliminar** — la última línea es el cierre de `eliminar_canal_db`, justo antes de la definición de `validar_texto_para_tts`:

```python
def eliminar_canal_db(ch_id):
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute("DELETE FROM channels WHERE channel_id = ?", (ch_id,))
    conn.commit()
    conn.close()
```

El bloque eliminado incluye, en orden:
- El comentario `# --- 1. CONFIGURACIÓN Y RUTAS ---` y `load_dotenv()`
- Todas las constantes (`YOUTUBE_API_KEY` … `NVIDIA_GRPC_MAX_MESSAGE_BYTES`)
- `PROMPT_DEFAULT`, `PROMPT_INVESTIGACION_DEFAULT`, `PROMPTS_DEFAULT`
- `obtener_tts_config_default`, `obtener_whisperx_config_default`, `obtener_ai_studio_config_default`
- `obtener_cortes_validos_prueba`, `normalizar_ejecutar_hasta_prompt`, `describir_alcance_prompts`
- `normalizar_tts_config`, `normalizar_ai_studio_config`
- El comentario `# --- 2. GESTIÓN DE CONFIGURACIÓN Y BASE DE DATOS ---`
- `guardar_config`, `cargar_toda_config`
- `init_db`, `obtener_canales_db`, `agregar_canal_db`, `eliminar_canal_db`

Después de la eliminación, la línea que debe aparecer inmediatamente después del bloque de imports es:

```python
def validar_texto_para_tts(texto):
```

El archivo debe verse así en esa zona:

```python
from database import (
    init_db,
    obtener_canales_db,
    agregar_canal_db,
    eliminar_canal_db,
)


def validar_texto_para_tts(texto):
    texto_limpio = (texto or "").strip()
    ...
```

### 3.3 — Eliminar `load_dotenv()` duplicado (si existe)

Después de la eliminación del bloque anterior, verificar que **no quede ninguna llamada suelta** a `load_dotenv()` en `clusiv-auto.py` fuera del bloque de imports. Si existe alguna, eliminarla. La carga de `.env` ahora ocurre en `config.py` al importarse.

---

## Paso 4 — Verificación

### 4.1 — Verificar que no quedan definiciones duplicadas en `clusiv-auto.py`

Ejecutar y confirmar **salida vacía** en cada caso:

```bash
grep -n "^def guardar_config\|^def cargar_toda_config\|^def init_db\|^def obtener_canales_db\|^def agregar_canal_db\|^def eliminar_canal_db" clusiv-auto.py
```

```bash
grep -n "^def normalizar_tts_config\|^def normalizar_ai_studio_config\|^def normalizar_ejecutar_hasta_prompt\|^def obtener_cortes_validos_prueba\|^def describir_alcance_prompts" clusiv-auto.py
```

```bash
grep -n "^def obtener_tts_config_default\|^def obtener_whisperx_config_default\|^def obtener_ai_studio_config_default" clusiv-auto.py
```

```bash
grep -n "^CONFIG_FILE\|^DATABASE_FILE\|^NVIDIA_API_KEY\|^YOUTUBE_API_KEY\|^PROMPT_DEFAULT\|^PROMPTS_DEFAULT\|^PATH_CHATGPT\|^PATH_AI_STUDIO" clusiv-auto.py
```

### 4.2 — Verificar que los imports existen

```bash
grep -n "from config import\|from database import" clusiv-auto.py
```

Salida esperada: exactamente dos líneas, una por cada import.

### 4.3 — Verificar que los módulos son importables de forma aislada

```bash
python -c "import config; print('config OK')"
python -c "import database; print('database OK')"
```

Salida esperada:
```
config OK
database OK
```

### 4.4 — Verificar que `config.py` exporta correctamente sus símbolos

```bash
python -c "
from config import (
    YOUTUBE_API_KEY, NVIDIA_API_KEY, CONFIG_FILE, DATABASE_FILE,
    PROMPTS_DEFAULT, obtener_tts_config_default, normalizar_tts_config,
    cargar_toda_config, guardar_config, describir_alcance_prompts
)
print('Todos los símbolos de config importados OK')
"
```

### 4.5 — Verificar que `database.py` exporta correctamente

```bash
python -c "
from database import init_db, obtener_canales_db, agregar_canal_db, eliminar_canal_db
print('Todos los símbolos de database importados OK')
"
```

### 4.6 — Verificar que `clusiv-auto.py` arranca sin errores de importación

```bash
python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('m', 'clusiv-auto.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('OK')
"
```

Salida esperada: `OK` (sin `ImportError`, `NameError` ni `ModuleNotFoundError`).

---

## Resumen de cambios

| Acción | Archivo | Descripción |
|--------|---------|-------------|
| Crear | `config.py` | Constantes globales + defaults + normalización + persistencia JSON |
| Crear | `database.py` | CRUD SQLite de canales (depende de `config.DATABASE_FILE`) |
| Reemplazar | `clusiv-auto.py` líneas 1–21 | Bloque de imports ampliado con `from config import (...)` y `from database import (...)` |
| Eliminar | `clusiv-auto.py` líneas 23–514 | Sección 1 completa (constantes + config + db) |

**Líneas netas en `clusiv-auto.py`:** −492 líneas (eliminadas) + ~30 líneas (imports nuevos) = −462 líneas.  
**Líneas en `config.py`:** ~310 líneas.  
**Líneas en `database.py`:** ~55 líneas.

---

## Notas importantes para el agente

1. **No modificar la lógica.** Copiar las funciones y constantes byte a byte desde el archivo original. No renombrar, no reordenar, no cambiar valores por defecto.

2. **`load_dotenv()` debe ejecutarse UNA SOLA VEZ, en `config.py`**, al nivel de módulo (fuera de cualquier función). Eliminar cualquier llamada adicional a `load_dotenv()` que pudiera quedar en `clusiv-auto.py`.

3. **`database.py` importa `DATABASE_FILE` desde `config`**, no lo redefine. Esto es intencional para que haya una única fuente de verdad para el nombre del archivo de base de datos.

4. **No eliminar `import sqlite3` de `clusiv-auto.py`** hasta confirmar que no hay otras referencias a `sqlite3` en el archivo fuera del bloque eliminado. En este caso particular, `sqlite3` solo se usa en las funciones de BD extraídas, por lo que sí se puede eliminar del bloque de imports de `clusiv-auto.py` si se desea — pero es más seguro dejarlo por ahora y limpiarlo en un paso futuro dedicado.

5. **El orden de los imports en `clusiv-auto.py` importa.** `from antibot import (...)` debe aparecer antes de `from config import (...)` y `from database import (...)` para mantener la convención de imports propios al final.

6. **`PROMPTS_DEFAULT` en `config.py`** referencia `PROMPT_DEFAULT` y `PROMPT_INVESTIGACION_DEFAULT` que están definidos en el mismo archivo — esto es correcto ya que Python lee el módulo de arriba hacia abajo y esas constantes están definidas antes.

7. Si el agente usa búsqueda-reemplazo para la eliminación del bloque, la cadena de inicio inequívoca es `\n# --- 1. CONFIGURACIÓN Y RUTAS ---\n` y el fin del bloque es la línea `    conn.close()\n` correspondiente al cierre de `eliminar_canal_db` (la cuarta función que cierra una `conn`). Identificar correctamente el cierre es crítico — contar las definiciones `def` dentro del bloque para no cortar antes de tiempo.
