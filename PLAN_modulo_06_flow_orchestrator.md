# Plan de implementación — Módulo 06: `flow_orchestrator.py`

> **Proyecto:** Clusiv Automation  
> **Archivo origen:** `clusiv-auto.py`  
> **Prerequisitos:** Planes 01–05 aplicados.  
> **Objetivo:** Extraer las funciones de automatización de ChatGPT, extracción de texto y el orquestador del flujo principal a `flow_orchestrator.py`, usando inyección de dependencias para desacoplarlas de la UI sin cambiar su lógica.  
> **Resultado esperado:** Comportamiento **100% idéntico**. Refactor de estructura con un patrón de inyección explícito.

---

## Contexto y decisión de diseño central

Este módulo presenta un desafío diferente a todos los anteriores: las funciones que lo componen **no son funciones de módulo** — son **closures anidados dentro de `main()`**. Capturan directamente variables del scope de `main()`:

| Variable capturada | Tipo | Propósito |
|---|---|---|
| `stop_event` | `threading.Event` | Señal de cancelación del flujo |
| `log_msg` | `callable` | Escribe en la consola de log de la UI |
| `ruta_base` | `list[str]` | Ruta de proyectos (mutable via lista) |
| `prompts_lista` | `list[dict]` | Prompts configurados |
| `tts_config` | `dict` | Configuración TTS activa |
| `whisperx_config` | `dict` | Configuración WhisperX activa |
| `config_actual` | `dict` | Config completa cargada al inicio |
| `ejecutar_hasta_prompt` | `list[int]` | Límite de ejecución (mutable) |
| `ref_image_paths_state` | `list` | Imágenes de referencia seleccionadas |
| `dropdown_ref_mode` | `ft.Dropdown` | Widget de selección de modo de referencia |
| `prg` | `ft.ProgressBar` | Barra de progreso |
| `txt_proximo` | `ft.Text` | Texto "Próximo proyecto: video N" |
| `page` | `ft.Page` | Página Flet para forzar `page.update()` |
| `set_estado_ejecutando` | `callable` | Alterna estado botones ejecutar/detener |
| `obtener_prompts_para_ejecucion` | `callable` | Calcula los prompts a ejecutar |

### Estrategia: inyección de dependencias por parámetro

En lugar de mover las funciones como closures (que requeriría mantenerlas dentro de `main()`), se extraen a nivel de módulo y sus dependencias de UI se pasan como parámetros explícitos. El punto de entrada del orquestador pasa a ser `ejecutar_flujo(ctx)`, donde `ctx` es un dataclass que agrupa todas las dependencias.

**Este patrón no modifica ninguna lógica** — solo hace explícito lo que antes era implícito a través de la captura de closures.

---

## Inventario de funciones a extraer

Todas son actualmente `def` anidados dentro de `main()`:

### Funciones de automatización de ChatGPT (interacción con ventana)
| Función | Línea aprox. | Propósito |
|---|---|---|
| `abrir_y_pegar_chatgpt` | 2955 | Abre ChatGPT, espera ventana, pega y envía el prompt |
| `obtener_primera_ventana_por_titulos` | 3208 | Busca ventana activa por título |
| `copiar_texto_desde_ventana` | 3216 | Ctrl+A, Ctrl+C en una ventana y devuelve portapapeles |
| `extraer_respuesta_automatica` | 3274 | Alias: copia texto de ventana ChatGPT |
| `extraer_respuesta_ai_studio` | 3277 | Alias: copia texto de ventana AI Studio |

### Funciones de extracción y limpieza de texto
| Función | Línea aprox. | Propósito |
|---|---|---|
| `extraer_solo_el_titulo` | 3015 | Extrae `[FINAL_TITLE: ...]` con regex |
| `limpiar_script_extraido` | 3026 | Limpia artefactos y duplicados del script |
| `remover_enlaces_parentesis` | 3121 | Elimina `(dominio.com)` del texto |
| `extraer_script_de_all_text` | 3157 | Lee `all_text.txt`, extrae bloques teleprompter → `script.txt` |

### Funciones de gestión de snapshots teleprompter
| Función | Línea aprox. | Propósito |
|---|---|---|
| `es_prompt_teleprompter` | 3280 | Detecta si un prompt tiene "teleprompter" en su nombre |
| `construir_nombre_snapshot_teleprompter` | 3284 | Genera nombre de archivo para el snapshot |
| `guardar_snapshot_teleprompter` | 3291 | Escribe el snapshot a disco |
| `extraer_bloques_teleprompter` | 3298 | Extrae bloques entre etiquetas `<<<...>>>` |
| `reconstruir_all_text_desde_teleprompters` | 3309 | Reconstruye `all_text.txt` desde snapshots previos |

### Funciones de extracción de prompts de AI Studio
| Función | Línea aprox. | Propósito |
|---|---|---|
| `extraer_prompts_ai_studio` | 3372 | Extrae etiquetas `<prompt>...</prompt>` |
| `guardar_prompts_ai_studio` | 3383 | Guarda los prompts de imagen en `.txt` |

### Orquestador principal
| Función | Línea aprox. | Propósito |
|---|---|---|
| `ejecutar_flujo_completo` | 3396 | Handler del botón; prepara UI y lanza `proceso_hilo` en thread |
| `proceso_hilo` | 3420 | Lógica completa del flujo: YouTube → ChatGPT × N prompts → TTS → WhisperX → AI Studio |

---

## Paso 1 — Crear `flow_orchestrator.py`

Crear el archivo `flow_orchestrator.py` en la carpeta raíz del proyecto. Contenido exacto:

```python
"""
flow_orchestrator.py
--------------------
Orquestador del flujo de producción de video de Clusiv Automation.

Secuencia del flujo principal:
  1. Analizar canales YouTube → obtener título de referencia del video ganador
  2. Crear carpeta del proyecto (video N)
  3. Para cada prompt configurado:
     a. Construir texto final (reemplazar placeholders)
     b. Abrir ChatGPT y pegar prompt (con antibot opcional)
     c. Esperar generación
     d. Post-acción: extraer título / guardar respuesta / snapshot teleprompter
  4. Extraer script.txt desde all_text.txt
  5. Sintetizar audio con NVIDIA TTS (opcional)
  6. Transcribir con WhisperX (opcional)
  7. Generar prompts de imagen con AI Studio (opcional)
  8. Enviar prompts de imagen a extensión Chrome (opcional)

Punto de entrada:
  ejecutar_flujo(ctx: FlowContext) → None
    Lanza el flujo en un thread daemon. ctx agrupa todas las dependencias
    de UI necesarias para que el orquestador interactúe con Flet.
"""

import os
import re
import threading
import webbrowser

import flet as ft
import pyautogui
import pygetwindow as gw
import pyperclip

from antibot import (
    espera_humanizada,
    escribir_humanizado,
    scroll_simulado,
    sleep_cancelable,
)
from config import (
    AI_STUDIO_OUTPUT_FILENAME_DEFAULT,
    AI_STUDIO_WINDOW_TITLES,
    PATH_CHATGPT,
    YOUTUBE_API_KEY,
    describir_alcance_prompts,
    normalizar_ai_studio_config,
    normalizar_ejecutar_hasta_prompt,
)
from database import obtener_canales_db
from tts_nvidia import sintetizar_script_a_audio_nvidia, transcribir_audio_whisperx
from ws_bridge import (
    construir_prompt_ai_studio,
    abrir_ai_studio_con_prompt,
    extraer_prompts_ai_studio as _ws_extraer_prompts,
    send_image_prompts_to_extension,
)
from youtube_analyzer import analizar_rendimiento_canal, obtener_siguiente_num


# ---------------------------------------------------------------------------
# Contexto de ejecución — agrupa todas las dependencias de UI
# ---------------------------------------------------------------------------

class FlowContext:
    """
    Agrupa todas las dependencias que el orquestador necesita de la UI.
    Se instancia en ui_main.py y se pasa a ejecutar_flujo().
    """
    def __init__(
        self,
        stop_event,
        log_msg,
        ruta_base,
        prompts_lista,
        tts_config,
        whisperx_config,
        config_actual,
        ejecutar_hasta_prompt,
        ref_image_paths_state,
        dropdown_ref_mode,
        prg,
        txt_proximo,
        page,
        set_estado_ejecutando,
        obtener_prompts_para_ejecucion,
    ):
        self.stop_event = stop_event
        self.log_msg = log_msg
        self.ruta_base = ruta_base
        self.prompts_lista = prompts_lista
        self.tts_config = tts_config
        self.whisperx_config = whisperx_config
        self.config_actual = config_actual
        self.ejecutar_hasta_prompt = ejecutar_hasta_prompt
        self.ref_image_paths_state = ref_image_paths_state
        self.dropdown_ref_mode = dropdown_ref_mode
        self.prg = prg
        self.txt_proximo = txt_proximo
        self.page = page
        self.set_estado_ejecutando = set_estado_ejecutando
        self.obtener_prompts_para_ejecucion = obtener_prompts_para_ejecucion


# ---------------------------------------------------------------------------
# Automatización de ChatGPT — interacción con ventana
# ---------------------------------------------------------------------------

def abrir_y_pegar_chatgpt(prompt_final, modo="nueva", antibot=False, wpm=45, stop_event=None):
    if stop_event and stop_event.is_set():
        return False

    if modo == "nueva":
        if os.path.exists(PATH_CHATGPT):
            os.startfile(PATH_CHATGPT)
        else:
            webbrowser.open("https://chatgpt.com")

    ventana_encontrada = None
    for _ in range(15):
        if stop_event and stop_event.is_set():
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
            if stop_event and stop_event.is_set():
                return False
            ventana_encontrada.activate()
            if antibot:
                if not espera_humanizada(2, stop_event):
                    return False
            else:
                if not sleep_cancelable(2, stop_event):
                    return False

            if stop_event and stop_event.is_set():
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


def obtener_primera_ventana_por_titulos(titulos_objetivo):
    titulos_normalizados = [t.lower() for t in titulos_objetivo if t]
    for ventana in gw.getAllWindows():
        titulo = (ventana.title or "").strip().lower()
        if titulo and any(objetivo in titulo for objetivo in titulos_normalizados):
            return ventana
    return None


def copiar_texto_desde_ventana(titulos_objetivo, antibot=False, stop_event=None):
    try:
        if stop_event and stop_event.is_set():
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

        if stop_event and stop_event.is_set():
            return None

        if antibot:
            scroll_simulado(stop_event)

        if stop_event and stop_event.is_set():
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


def extraer_respuesta_automatica(antibot=False, stop_event=None):
    return copiar_texto_desde_ventana(("ChatGPT",), antibot=antibot, stop_event=stop_event)


def extraer_respuesta_ai_studio(antibot=False, stop_event=None):
    return copiar_texto_desde_ventana(AI_STUDIO_WINDOW_TITLES, antibot=antibot, stop_event=stop_event)


# ---------------------------------------------------------------------------
# Extracción y limpieza de texto
# ---------------------------------------------------------------------------

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
    """Limpia artefactos del script extraído de all_text.txt."""
    if not texto:
        return texto

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

    while lineas:
        linea_limpia = lineas[0].strip()
        if not linea_limpia:
            lineas.pop(0)
            continue
        linea_lower = linea_limpia.lower()
        es_instruccion = any(frase in linea_lower for frase in frases_instruccion)
        if es_instruccion:
            lineas.pop(0)
            continue
        break

    texto = "\n".join(lineas).strip()

    lineas = texto.split("\n")

    if len(lineas) >= 3:
        ultima_linea = lineas[-1].strip()
        texto_sin_ultima = "\n".join(lineas[:-1])

        if len(ultima_linea) > 300:
            palabras_muestra = ultima_linea.split()[:50]
            if len(palabras_muestra) >= 10:
                texto_anterior_lower = texto_sin_ultima.lower()
                coincidencias = sum(
                    1 for p in palabras_muestra if p.lower() in texto_anterior_lower
                )
                ratio = coincidencias / len(palabras_muestra)

                if ratio > 0.6:
                    texto = texto_sin_ultima.strip()

    longitud = len(texto)
    if longitud > 600:
        tamano_prueba = min(200, longitud // 4)
        cola = texto[-tamano_prueba:]
        pos_primera = texto.find(cola)
        pos_ultima = longitud - tamano_prueba
        if pos_primera != -1 and pos_primera < pos_ultima - tamano_prueba:
            for corte in range(pos_ultima, max(pos_ultima - 500, 0), -1):
                fragmento = texto[corte : corte + 100]
                buscar_en = texto[:corte]
                if fragmento in buscar_en:
                    texto = texto[:corte].rstrip()
                    break

    return texto.strip()


def remover_enlaces_parentesis(texto):
    """Remueve del texto todos los enlaces web entre paréntesis."""
    if not texto:
        return texto

    patron_enlace = (
        r'\s*\(\s*(?:https?://)?(?:www\.)?[\w.-]+\.\w{2,}(?:/[^\)]*?)?\s*\)'
    )

    texto_limpio = re.sub(patron_enlace, '', texto)
    texto_limpio = re.sub(r'  +', ' ', texto_limpio)

    lineas = texto_limpio.split('\n')
    lineas_limpias = []
    for linea in lineas:
        linea_stripped = linea.strip()
        if linea_stripped or linea == '':
            lineas_limpias.append(linea.rstrip())

    return '\n'.join(lineas_limpias).strip()


def extraer_script_de_all_text(carpeta_proyecto):
    """Lee all_text.txt, extrae bloques teleprompter y guarda script.txt."""
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

    bloques_limpios = []
    for bloque in matches:
        bloque_limpio = limpiar_script_extraido(bloque.strip())
        if bloque_limpio:
            bloques_limpios.append(bloque_limpio)

    if not bloques_limpios:
        return (
            False,
            "Los bloques extraídos quedaron vacíos después de la limpieza.",
        )

    texto_extraido = "\n\n".join(bloques_limpios)
    texto_extraido = remover_enlaces_parentesis(texto_extraido)

    with open(ruta_script, "w", encoding="utf-8") as f:
        f.write(texto_extraido)

    return (
        True,
        f"script.txt creado exitosamente ({len(bloques_limpios)} bloque(s) extraído(s), limpieza aplicada).",
    )


# ---------------------------------------------------------------------------
# Gestión de snapshots teleprompter
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Extracción de prompts de AI Studio
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def ejecutar_flujo(ctx: FlowContext):
    """
    Punto de entrada del orquestador. Valida condiciones y lanza proceso_hilo.
    Equivale a ejecutar_flujo_completo() en el original.
    """
    from flet import Colors  # evitar import circular si ft ya está importado

    if not ctx.ruta_base[0]:
        return  # La UI valida esto antes de llamar

    if not YOUTUBE_API_KEY:
        return  # La UI valida esto antes de llamar

    prompts_a_ejecutar, _ = ctx.obtener_prompts_para_ejecucion()
    if not prompts_a_ejecutar:
        return

    alcance_actual = describir_alcance_prompts(ctx.prompts_lista, ctx.ejecutar_hasta_prompt[0])

    ctx.stop_event.clear()
    ctx.log_msg("🚀 Iniciando flujo completo...", italic=True)
    ctx.log_msg(f"⚙️ Alcance configurado: {alcance_actual}", color=ft.Colors.BLUE_800)

    def proceso_hilo():
        detenido = False
        try:
            canales = obtener_canales_db()
            ganadores_totales = []

            for ch_id, ch_name, _ in canales:
                if ctx.stop_event.is_set():
                    detenido = True
                    break
                ctx.log_msg(f"🔍 Analizando: {ch_name}...")
                data = analizar_rendimiento_canal(ch_id)
                if data and data["ganadores"]:
                    v = data["ganadores"][0]
                    v["ch_name"] = ch_name
                    ganadores_totales.append(v)

            if detenido or ctx.stop_event.is_set():
                ctx.log_msg(
                    "⛔ Flujo detenido por el usuario durante el análisis de canales.",
                    color=ft.Colors.RED_700,
                    weight="bold",
                )
                ctx.prg.visible = False
                ctx.set_estado_ejecutando(False)
                ctx.page.update()
                return

            if not ganadores_totales:
                ctx.log_msg(
                    "❌ No se encontraron videos ganadores.",
                    color=ft.Colors.RED,
                )
                ctx.prg.visible = False
                ctx.set_estado_ejecutando(False)
                ctx.page.update()
                return

            mejor = max(ganadores_totales, key=lambda x: x["views"])
            titulo_ref = mejor["title"]

            num = obtener_siguiente_num(ctx.ruta_base[0])
            path = os.path.join(ctx.ruta_base[0], f"video {num}")

            os.makedirs(os.path.join(path, "assets"), exist_ok=True)
            os.makedirs(os.path.join(path, "images"), exist_ok=True)
            open(os.path.join(path, "scenes.txt"), "w", encoding="utf-8").close()
            open(os.path.join(path, "scenes with duration.txt"), "w", encoding="utf-8").close()

            titulo_extraido = None
            all_text_esperado = any(
                str(p.get("archivo_salida", "")).strip().lower() == "all_text.txt"
                for p in prompts_a_ejecutar
            )

            for idx, p in enumerate(prompts_a_ejecutar):
                if ctx.stop_event.is_set():
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
                with open(os.path.join(path, nombre_archivo_prompt), "w", encoding="utf-8") as f:
                    f.write(texto_prompt)

                ab_tag = " 🛡️" if ab else ""
                ctx.log_msg(
                    f"🌐 [{idx + 1}/{len(prompts_a_ejecutar)}] Enviando: {nombre_prompt}{ab_tag}...",
                    color=ft.Colors.BLUE,
                )

                if ctx.stop_event.is_set():
                    detenido = True
                    break

                envio_ok = abrir_y_pegar_chatgpt(
                    texto_prompt, modo=modo, antibot=ab, wpm=wpm, stop_event=ctx.stop_event
                )

                if ctx.stop_event.is_set():
                    detenido = True
                    break

                if envio_ok:
                    ctx.log_msg(f"⏳ Esperando ~{espera}s generación...", italic=True)

                    if ab:
                        if not espera_humanizada(espera * 0.5, ctx.stop_event):
                            detenido = True
                            break
                        scroll_simulado(ctx.stop_event)
                        if ctx.stop_event.is_set():
                            detenido = True
                            break
                        if not espera_humanizada(espera * 0.5, ctx.stop_event):
                            detenido = True
                            break
                    else:
                        if not sleep_cancelable(espera, ctx.stop_event):
                            detenido = True
                            break

                    if ctx.stop_event.is_set():
                        detenido = True
                        break

                    # Post-acción
                    if post_accion == "extraer_titulo":
                        ctx.log_msg("📋 Extrayendo título final...", color=ft.Colors.AMBER_800)
                        texto_copiado = extraer_respuesta_automatica(antibot=ab, stop_event=ctx.stop_event)

                        if ctx.stop_event.is_set():
                            detenido = True
                            break

                        if texto_copiado:
                            titulo_final = extraer_solo_el_titulo(texto_copiado)
                            if titulo_final:
                                titulo_extraido = titulo_final
                                if archivo_salida:
                                    with open(os.path.join(path, archivo_salida), "w", encoding="utf-8") as f:
                                        f.write(titulo_final)
                                ctx.log_msg(
                                    f"🎯 Título detectado: {titulo_final}",
                                    color=ft.Colors.GREEN_700,
                                    weight="bold",
                                )
                            else:
                                with open(os.path.join(path, "RESPUESTA_RAW.txt"), "w", encoding="utf-8") as f:
                                    f.write(texto_copiado)
                                ctx.log_msg("⚠ No se encontró el título real. Se guardó Raw.", color=ft.Colors.ORANGE)
                        else:
                            ctx.log_msg("❌ Error: Portapapeles vacío.", color=ft.Colors.RED)

                    elif post_accion == "guardar_respuesta":
                        ctx.log_msg(
                            f"📋 Extrayendo respuesta para '{nombre_prompt}'...",
                            color=ft.Colors.AMBER_800,
                        )
                        texto_resp = extraer_respuesta_automatica(antibot=ab, stop_event=ctx.stop_event)

                        if ctx.stop_event.is_set():
                            detenido = True
                            break

                        if texto_resp:
                            if archivo_salida:
                                with open(os.path.join(path, archivo_salida), "w", encoding="utf-8") as f:
                                    f.write(texto_resp)
                            ctx.log_msg(
                                f"✅ Respuesta guardada: {archivo_salida}",
                                color=ft.Colors.GREEN_700,
                                weight="bold",
                            )
                        else:
                            ctx.log_msg(
                                f"❌ Error al extraer respuesta de '{nombre_prompt}'.",
                                color=ft.Colors.RED,
                            )
                    else:
                        if es_prompt_teleprompter(p):
                            ctx.log_msg(
                                f"📋 Capturando snapshot teleprompter para '{nombre_prompt}'...",
                                color=ft.Colors.AMBER_800,
                            )
                            texto_teleprompter = extraer_respuesta_automatica(antibot=ab, stop_event=ctx.stop_event)

                            if ctx.stop_event.is_set():
                                detenido = True
                                break

                            if texto_teleprompter:
                                ruta_snapshot = guardar_snapshot_teleprompter(
                                    path, idx + 1, p, texto_teleprompter
                                )
                                bloques_snapshot = extraer_bloques_teleprompter(texto_teleprompter)
                                if bloques_snapshot:
                                    ctx.log_msg(
                                        f"✅ Snapshot teleprompter guardado ({len(bloques_snapshot)} bloque(s)): {os.path.basename(ruta_snapshot)}",
                                        color=ft.Colors.GREEN_700,
                                        weight="bold",
                                    )
                                else:
                                    ctx.log_msg(
                                        f"⚠ Se guardó el snapshot teleprompter, pero no se detectaron bloques válidos todavía: {os.path.basename(ruta_snapshot)}",
                                        color=ft.Colors.ORANGE_700,
                                    )
                            else:
                                ctx.log_msg(
                                    f"⚠ No se pudo capturar el snapshot teleprompter de '{nombre_prompt}'.",
                                    color=ft.Colors.ORANGE_700,
                                )
                        ctx.log_msg(f"✅ Prompt '{nombre_prompt}' enviado.", color=ft.Colors.GREEN_700)
                else:
                    if ctx.stop_event.is_set():
                        detenido = True
                        break
                    ctx.log_msg(
                        f"❌ Error: No se pudo enviar '{nombre_prompt}'.",
                        color=ft.Colors.RED,
                    )

                # Pausa entre prompts
                if idx < len(prompts_a_ejecutar) - 1:
                    if ab:
                        if not espera_humanizada(3, ctx.stop_event):
                            detenido = True
                            break
                    else:
                        if not sleep_cancelable(3, ctx.stop_event):
                            detenido = True
                            break

            # Mensaje final y postproceso
            ctx.log_msg("", is_divider=True)
            if detenido or ctx.stop_event.is_set():
                ctx.log_msg(
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
                            path, prompts_a_ejecutar
                        )
                        if reconstruccion_ok:
                            ctx.log_msg(f"✅ {reconstruccion_msg}", color=ft.Colors.GREEN_700, weight="bold")
                        else:
                            ctx.log_msg(
                                f"ℹ No se pudo reconstruir all_text.txt para el alcance parcial: {reconstruccion_msg}",
                                color=ft.Colors.BLUE_800,
                                italic=True,
                            )

                    if not os.path.exists(ruta_all_text) and all_text_esperado:
                        ctx.log_msg(
                            "⚠ Se omitió el postproceso final porque no se generó all_text.txt en esta corrida.",
                            color=ft.Colors.ORANGE_700,
                        )
                    elif not os.path.exists(ruta_all_text):
                        ctx.log_msg(
                            f"ℹ Se omite el postproceso final porque el alcance '{alcance_actual}' no dejó bloques teleprompter reutilizables.",
                            color=ft.Colors.BLUE_800,
                            italic=True,
                        )

                if os.path.exists(ruta_all_text):
                    ctx.log_msg("📄 Buscando all_text.txt para extraer script...", color=ft.Colors.BLUE_800, italic=True)
                    exito, mensaje = extraer_script_de_all_text(path)

                    if exito:
                        ctx.log_msg(f"✅ {mensaje}", color=ft.Colors.GREEN_700, weight="bold")

                        if ctx.tts_config.get("enabled"):
                            ctx.log_msg("🔊 Generando audio con NVIDIA Magpie TTS...", color=ft.Colors.BLUE_800, italic=True)
                            tts_ok, tts_msg, ruta_audio = sintetizar_script_a_audio_nvidia(path, ctx.tts_config)
                            if tts_ok:
                                ctx.log_msg(f"✅ {tts_msg}", color=ft.Colors.GREEN_700, weight="bold")
                                if ctx.whisperx_config.get("enabled") and ruta_audio:
                                    ctx.log_msg(
                                        "🎙️ Iniciando transcripción con WhisperX (esto puede tardar varios minutos)...",
                                        color=ft.Colors.BLUE_800,
                                        italic=True,
                                    )
                                    wx_ok, wx_msg, ruta_json = transcribir_audio_whisperx(ruta_audio, ctx.whisperx_config)
                                    if wx_ok:
                                        ctx.log_msg(f"✅ WhisperX: {wx_msg}", color=ft.Colors.GREEN_700, weight="bold")
                                        ai_studio_runtime = normalizar_ai_studio_config(
                                            ctx.config_actual.get("ai_studio"),
                                            ctx.config_actual.get("prompt_ai_studio"),
                                        )
                                        prompt_ai_base = ai_studio_runtime.get("prompt", "").strip()
                                        if prompt_ai_base:
                                            prompt_ai_ok, prompt_ai_msg, prompt_ai = construir_prompt_ai_studio(
                                                prompt_ai_base, path
                                            )
                                            if prompt_ai_ok:
                                                espera_ai = ai_studio_runtime.get("espera_respuesta_segundos", 15)
                                                ai_ok, ai_msg = abrir_ai_studio_con_prompt(prompt_ai)
                                                if ai_ok:
                                                    ctx.log_msg(f"✅ {ai_msg}", color=ft.Colors.TEAL_700, weight="bold")
                                                    ctx.log_msg(
                                                        f"⏳ Esperando ~{espera_ai}s respuesta de AI Studio...",
                                                        color=ft.Colors.BLUE_800,
                                                        italic=True,
                                                    )
                                                    if not sleep_cancelable(espera_ai, ctx.stop_event):
                                                        detenido = True
                                                    else:
                                                        ctx.log_msg(
                                                            "📋 Copiando respuesta completa desde AI Studio...",
                                                            color=ft.Colors.AMBER_800,
                                                        )
                                                        texto_ai_studio = extraer_respuesta_ai_studio(
                                                            antibot=False, stop_event=ctx.stop_event
                                                        )
                                                        if not ctx.stop_event.is_set() and texto_ai_studio:
                                                            prompts_extraidos = extraer_prompts_ai_studio(texto_ai_studio)
                                                            if prompts_extraidos:
                                                                ruta_prompts = guardar_prompts_ai_studio(
                                                                    path,
                                                                    prompts_extraidos,
                                                                    ai_studio_runtime.get("archivo_salida"),
                                                                )
                                                                ctx.log_msg(
                                                                    f"✅ AI Studio: {len(prompts_extraidos)} prompt(s) guardados en {os.path.basename(ruta_prompts)}.",
                                                                    color=ft.Colors.GREEN_700,
                                                                    weight="bold",
                                                                )
                                                                if (
                                                                    not ctx.stop_event.is_set()
                                                                    and ai_studio_runtime.get("auto_send_to_extension", False)
                                                                ):
                                                                    ctx.log_msg(
                                                                        "🖼️ Enviando prompts de imagen a la extensión Chrome...",
                                                                        color=ft.Colors.TEAL_700,
                                                                        italic=True,
                                                                    )
                                                                    img_ok, img_msg, _ = send_image_prompts_to_extension(
                                                                        ruta_prompts,
                                                                        modelo=ai_studio_runtime.get("imagen_model", "imagen4"),
                                                                        aspect_ratio=ai_studio_runtime.get("imagen_aspect_ratio", "landscape"),
                                                                        count=ai_studio_runtime.get("imagen_count", 1),
                                                                        reference_image_paths=list(ctx.ref_image_paths_state) if ctx.ref_image_paths_state else None,
                                                                        reference_mode=ctx.dropdown_ref_mode.value or "ingredients",
                                                                        project_folder=path,
                                                                    )
                                                                    ctx.log_msg(
                                                                        f"{'✅' if img_ok else '⚠'} {img_msg}",
                                                                        color=ft.Colors.GREEN_700 if img_ok else ft.Colors.ORANGE_700,
                                                                        weight="bold" if img_ok else None,
                                                                    )
                                                            else:
                                                                ctx.log_msg(
                                                                    "⚠ AI Studio: no se encontraron etiquetas <prompt></prompt> en la respuesta copiada.",
                                                                    color=ft.Colors.ORANGE_700,
                                                                )
                                                        else:
                                                            ctx.log_msg(
                                                                "⚠ AI Studio: no se pudo copiar la respuesta completa desde la ventana.",
                                                                color=ft.Colors.ORANGE_700,
                                                            )
                                                else:
                                                    ctx.log_msg(f"⚠ AI Studio: {ai_msg}", color=ft.Colors.ORANGE_700)
                                            else:
                                                ctx.log_msg(f"⚠ AI Studio: {prompt_ai_msg}", color=ft.Colors.ORANGE_700)
                                        else:
                                            ctx.log_msg(
                                                "⚠ No se abrió AI Studio: el prompt está vacío. Configúralo en el tile de Configuración.",
                                                color=ft.Colors.ORANGE_700,
                                            )
                                    else:
                                        ctx.log_msg(f"⚠ WhisperX: {wx_msg}", color=ft.Colors.ORANGE_700)
                            else:
                                ctx.log_msg(f"⚠ {tts_msg}", color=ft.Colors.ORANGE_700)
                    else:
                        ctx.log_msg(f"⚠ {mensaje}", color=ft.Colors.ORANGE_700)

                if detenido or ctx.stop_event.is_set():
                    ctx.log_msg(f"⛔ FLUJO DETENIDO por el usuario en video {num}", color=ft.Colors.RED_700, weight="bold")
                else:
                    ctx.log_msg(f"✅ FINALIZADO: video {num}", color=ft.Colors.GREEN_800, weight="bold")

        except Exception as ex:
            ctx.log_msg(f"❌ Error: {str(ex)}", color=ft.Colors.RED)

        ctx.prg.visible = False
        ctx.txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(ctx.ruta_base[0])}"
        ctx.set_estado_ejecutando(False)
        ctx.page.update()

    threading.Thread(target=proceso_hilo, daemon=True).start()
```

---

## Paso 2 — Corregir el import circular con `ws_bridge`

`flow_orchestrator.py` importa `extraer_prompts_ai_studio` desde `ws_bridge`. Sin embargo, esta función **no existe en `ws_bridge.py`** — existe en el original como closure dentro de `main()`, y en este plan la definimos directamente en `flow_orchestrator.py`. El import de `ws_bridge` en la cabecera del módulo debe corregirse:

**Eliminar esta línea** del bloque de imports de `flow_orchestrator.py`:
```python
from ws_bridge import (
    construir_prompt_ai_studio,
    abrir_ai_studio_con_prompt,
    extraer_prompts_ai_studio as _ws_extraer_prompts,
    send_image_prompts_to_extension,
)
```

**Reemplazarla con:**
```python
from ws_bridge import (
    construir_prompt_ai_studio,
    abrir_ai_studio_con_prompt,
    send_image_prompts_to_extension,
)
```

La función `extraer_prompts_ai_studio` se usa directamente desde el mismo módulo (`flow_orchestrator.py`), donde está definida.

---

## Paso 3 — Modificar `clusiv-auto.py`

### 3.1 — Agregar el import de `flow_orchestrator`

Añadir al final del bloque de imports propios:

```python
from flow_orchestrator import FlowContext, ejecutar_flujo
```

### 3.2 — Reemplazar `ejecutar_flujo_completo` en `clusiv-auto.py`

Localizar la definición actual de `ejecutar_flujo_completo` dentro de `main()` (comienza en la línea con el comentario `# --- FLUJO PRINCIPAL`). Reemplazar **toda la función** `ejecutar_flujo_completo` — incluyendo la función anidada `proceso_hilo` y el `threading.Thread` final — por esta versión compacta:

```python
    # --- FLUJO PRINCIPAL ---
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

        log_ui.controls.clear()
        prg.visible = True
        set_estado_ejecutando(True)
        page.update()

        ctx = FlowContext(
            stop_event=stop_event,
            log_msg=log_msg,
            ruta_base=ruta_base,
            prompts_lista=prompts_lista,
            tts_config=tts_config,
            whisperx_config=whisperx_config,
            config_actual=config_actual,
            ejecutar_hasta_prompt=ejecutar_hasta_prompt,
            ref_image_paths_state=ref_image_paths_state,
            dropdown_ref_mode=dropdown_ref_mode,
            prg=prg,
            txt_proximo=txt_proximo,
            page=page,
            set_estado_ejecutando=set_estado_ejecutando,
            obtener_prompts_para_ejecucion=obtener_prompts_para_ejecucion,
        )
        ejecutar_flujo(ctx)
```

### 3.3 — Eliminar las funciones de ChatGPT y extracción de `clusiv-auto.py`

Localizar y eliminar los siguientes bloques de funciones nested dentro de `main()`. Todos están entre el comentario `# --- AUTOMATIZACIÓN DE CHATGPT ---` y el comentario `# --- FLUJO PRINCIPAL`.

Funciones a eliminar:
- `abrir_y_pegar_chatgpt`
- `extraer_solo_el_titulo`
- `limpiar_script_extraido`
- `remover_enlaces_parentesis`
- `extraer_script_de_all_text`
- `obtener_primera_ventana_por_titulos`
- `copiar_texto_desde_ventana`
- `extraer_respuesta_automatica`
- `extraer_respuesta_ai_studio`
- `es_prompt_teleprompter`
- `construir_nombre_snapshot_teleprompter`
- `guardar_snapshot_teleprompter`
- `extraer_bloques_teleprompter`
- `reconstruir_all_text_desde_teleprompters`
- `extraer_prompts_ai_studio`
- `guardar_prompts_ai_studio`

**Inicio del bloque a eliminar:**
```python
    # --- AUTOMATIZACIÓN DE CHATGPT ---
    def abrir_y_pegar_chatgpt(prompt_final, modo="nueva", antibot=False, wpm=45):
```

**Fin del bloque a eliminar** (última línea, justo antes del comentario del flujo principal):
```python
        return ruta_archivo

    # --- FLUJO PRINCIPAL (basado en lista de prompts) ---
```

---

## Paso 4 — Verificación

### 4.1 — Verificar que no quedan definiciones duplicadas

```bash
grep -n "def abrir_y_pegar_chatgpt\|def extraer_solo_el_titulo\|def limpiar_script_extraido\|def extraer_script_de_all_text" clusiv-auto.py
grep -n "def copiar_texto_desde_ventana\|def extraer_respuesta_automatica\|def es_prompt_teleprompter\|def extraer_bloques_teleprompter" clusiv-auto.py
grep -n "def reconstruir_all_text\|def extraer_prompts_ai_studio\|def guardar_prompts_ai_studio\|def proceso_hilo" clusiv-auto.py
```

Salida esperada: vacía en todos los casos.

### 4.2 — Verificar que `flow_orchestrator.py` es importable

```bash
python -c "from flow_orchestrator import FlowContext, ejecutar_flujo; print('flow_orchestrator OK')"
```

### 4.3 — Verificar que el nuevo `ejecutar_flujo_completo` en `clusiv-auto.py` no tiene `proceso_hilo`

```bash
grep -n "proceso_hilo\|threading.Thread.*proceso" clusiv-auto.py
```

Salida esperada: vacía (el thread ahora lo lanza `ejecutar_flujo` en `flow_orchestrator.py`).

### 4.4 — Verificar que `clusiv-auto.py` arranca sin errores

```bash
python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('m', 'clusiv-auto.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('OK')
"
```

---

## Resumen de cambios

| Acción | Archivo | Descripción |
|--------|---------|-------------|
| Crear | `flow_orchestrator.py` | `FlowContext` + 17 funciones extraídas + `ejecutar_flujo` (~380 líneas) |
| Agregar | `clusiv-auto.py` | `from flow_orchestrator import FlowContext, ejecutar_flujo` |
| Reemplazar | `clusiv-auto.py` | `ejecutar_flujo_completo` + `proceso_hilo` → versión compacta con `FlowContext` |
| Eliminar | `clusiv-auto.py` | 16 funciones nested (~440 líneas) entre `# AUTOMATIZACIÓN DE CHATGPT` y `# FLUJO PRINCIPAL` |

**Líneas netas en `clusiv-auto.py`:** −440 (funciones) −~500 (proceso_hilo) +~30 (nueva ejecutar_flujo_completo + import) = **~−910 líneas**.

---

## Notas importantes para el agente

1. **`FlowContext` no es un dataclass** — es una clase plana con `__init__`. No añadir `@dataclass` ni cambiar la firma.

2. **`stop_event` se pasa explícitamente a cada función** que antes lo capturaba como closure. Las firmas cambian: `abrir_y_pegar_chatgpt(prompt_final, modo, antibot, wpm, stop_event=None)`, `copiar_texto_desde_ventana(titulos, antibot, stop_event=None)`, etc. La lógica interna es idéntica — solo se reemplaza el `stop_event` implícito por el `stop_event` del parámetro.

3. **`import flet as ft` va en `flow_orchestrator.py`** — `ft.Colors.*` se usa extensamente en los mensajes de log dentro de `proceso_hilo`. No es un error.

4. **`log_ui.controls.clear()` se mantiene en `ejecutar_flujo_completo` en `clusiv-auto.py`** — es una operación sobre un widget de Flet que no tiene sentido en el orquestador. El nuevo `ejecutar_flujo_completo` la ejecuta antes de llamar a `ejecutar_flujo(ctx)`.

5. **`import pygetwindow as gw`** ya está importado en `clusiv-auto.py`. Debe también importarse en `flow_orchestrator.py` con `import pygetwindow as gw`.

6. **El import circular potencial**: `flow_orchestrator` importa de `ws_bridge`, y `ws_bridge` no importa de `flow_orchestrator`. No hay ciclo.
