"""
Orquestador del flujo principal de Clusiv Automation.
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
    escribir_humanizado,
    espera_humanizada,
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
)
from database import obtener_canales_db
from tts_nvidia import sintetizar_script_a_audio_nvidia, transcribir_audio_whisperx
from ws_bridge import (
    abrir_ai_studio_con_prompt,
    construir_prompt_ai_studio,
    send_image_prompts_to_extension,
)
from youtube_analyzer import analizar_rendimiento_canal, obtener_siguiente_num


class FlowContext:
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
        except Exception:
            pass
    return False


def extraer_solo_el_titulo(texto_completo):
    patron = r"\[FINAL_TITLE:\s*(.*?)\]"
    matches = re.findall(patron, texto_completo, re.IGNORECASE | re.DOTALL)
    titulos_reales = [
        match.strip()
        for match in matches
        if "Put the generated title here" not in match
    ]
    if titulos_reales:
        return titulos_reales[-1]
    return None


def limpiar_script_extraido(texto):
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
                    1 for palabra in palabras_muestra if palabra.lower() in texto_anterior_lower
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
    if not texto:
        return texto

    patron_enlace = r"\s*\(\s*(?:https?://)?(?:www\.)?[\w.-]+\.\w{2,}(?:/[^\)]*?)?\s*\)"
    texto_limpio = re.sub(patron_enlace, "", texto)
    texto_limpio = re.sub(r"  +", " ", texto_limpio)

    lineas = texto_limpio.split("\n")
    lineas_limpias = []
    for linea in lineas:
        linea_stripped = linea.strip()
        if linea_stripped or linea == "":
            lineas_limpias.append(linea.rstrip())

    return "\n".join(lineas_limpias).strip()


def extraer_script_de_all_text(carpeta_proyecto):
    ruta_all_text = os.path.join(carpeta_proyecto, "all_text.txt")
    ruta_script = os.path.join(carpeta_proyecto, "script.txt")

    if not os.path.exists(ruta_all_text):
        return False, "all_text.txt no encontrado en la carpeta del proyecto."

    with open(ruta_all_text, "r", encoding="utf-8") as file:
        contenido = file.read()

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

    with open(ruta_script, "w", encoding="utf-8") as file:
        file.write(texto_extraido)

    return (
        True,
        f"script.txt creado exitosamente ({len(bloques_limpios)} bloque(s) extraído(s), limpieza aplicada).",
    )


def obtener_primera_ventana_por_titulos(titulos_objetivo):
    titulos_normalizados = [titulo.lower() for titulo in titulos_objetivo if titulo]
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
    except Exception:
        return None


def extraer_respuesta_automatica(antibot=False, stop_event=None):
    return copiar_texto_desde_ventana(("ChatGPT",), antibot=antibot, stop_event=stop_event)


def extraer_respuesta_ai_studio(antibot=False, stop_event=None):
    return copiar_texto_desde_ventana(
        AI_STUDIO_WINDOW_TITLES, antibot=antibot, stop_event=stop_event
    )


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
    with open(ruta_archivo, "w", encoding="utf-8") as file:
        file.write(contenido)
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

        with open(ruta_fuente, "r", encoding="utf-8") as file:
            contenido = file.read()

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

    with open(ruta_all_text, "w", encoding="utf-8") as file:
        file.write(contenido_all_text)

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
    with open(ruta_archivo, "w", encoding="utf-8") as file:
        file.write("\n\n".join(prompts_extraidos))
    return ruta_archivo


def ejecutar_flujo(ctx: FlowContext):
    if not ctx.ruta_base[0]:
        return
    if not YOUTUBE_API_KEY:
        return

    prompts_a_ejecutar, _ = ctx.obtener_prompts_para_ejecucion()
    if not prompts_a_ejecutar:
        return

    alcance_actual = describir_alcance_prompts(
        ctx.prompts_lista, ctx.ejecutar_hasta_prompt[0]
    )

    ctx.stop_event.clear()
    ctx.log_msg("🚀 Iniciando flujo completo...", italic=True)
    ctx.log_msg(
        f"⚙️ Alcance configurado: {alcance_actual}",
        color=ft.Colors.BLUE_800,
    )

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
                    video = data["ganadores"][0]
                    video["ch_name"] = ch_name
                    ganadores_totales.append(video)

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

            mejor = max(ganadores_totales, key=lambda item: item["views"])
            titulo_ref = mejor["title"]

            num = obtener_siguiente_num(ctx.ruta_base[0])
            path = os.path.join(ctx.ruta_base[0], f"video {num}")

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
                str(prompt.get("archivo_salida", "")).strip().lower() == "all_text.txt"
                for prompt in prompts_a_ejecutar
            )

            for idx, prompt in enumerate(prompts_a_ejecutar):
                if ctx.stop_event.is_set():
                    detenido = True
                    break

                nombre_prompt = prompt.get("nombre", f"Prompt {idx + 1}")
                post_accion = prompt.get("post_accion", "solo_enviar")
                modo = prompt.get("modo", "nueva")
                espera = prompt.get("espera_segundos", 30)
                archivo_salida = prompt.get("archivo_salida", "")
                antibot = prompt.get("antibot", False)
                wpm = prompt.get("wpm_escritura", 45)

                texto_prompt = prompt.get("texto", "")
                texto_prompt = texto_prompt.replace("[REF_TITLE]", titulo_ref)
                if titulo_extraido:
                    texto_prompt = texto_prompt.replace("[TITULO]", titulo_extraido)

                nombre_archivo_prompt = (
                    f"PROMPT_{idx + 1}_{nombre_prompt.replace(' ', '_')}.txt"
                )
                with open(
                    os.path.join(path, nombre_archivo_prompt),
                    "w",
                    encoding="utf-8",
                ) as file:
                    file.write(texto_prompt)

                ab_tag = " 🛡️" if antibot else ""
                ctx.log_msg(
                    f"🌐 [{idx + 1}/{len(prompts_a_ejecutar)}] Enviando: {nombre_prompt}{ab_tag}...",
                    color=ft.Colors.BLUE,
                )

                if ctx.stop_event.is_set():
                    detenido = True
                    break

                envio_ok = abrir_y_pegar_chatgpt(
                    texto_prompt,
                    modo=modo,
                    antibot=antibot,
                    wpm=wpm,
                    stop_event=ctx.stop_event,
                )

                if ctx.stop_event.is_set():
                    detenido = True
                    break

                if envio_ok:
                    ctx.log_msg(f"⏳ Esperando ~{espera}s generación...", italic=True)

                    if antibot:
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

                    if post_accion == "extraer_titulo":
                        ctx.log_msg(
                            "📋 Extrayendo título final...",
                            color=ft.Colors.AMBER_800,
                        )
                        texto_copiado = extraer_respuesta_automatica(
                            antibot=antibot,
                            stop_event=ctx.stop_event,
                        )

                        if ctx.stop_event.is_set():
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
                                    ) as file:
                                        file.write(titulo_final)
                                ctx.log_msg(
                                    f"🎯 Título detectado: {titulo_final}",
                                    color=ft.Colors.GREEN_700,
                                    weight="bold",
                                )
                            else:
                                with open(
                                    os.path.join(path, "RESPUESTA_RAW.txt"),
                                    "w",
                                    encoding="utf-8",
                                ) as file:
                                    file.write(texto_copiado)
                                ctx.log_msg(
                                    "⚠ No se encontró el título real. Se guardó Raw.",
                                    color=ft.Colors.ORANGE,
                                )
                        else:
                            ctx.log_msg(
                                "❌ Error: Portapapeles vacío.",
                                color=ft.Colors.RED,
                            )

                    elif post_accion == "guardar_respuesta":
                        ctx.log_msg(
                            f"📋 Extrayendo respuesta para '{nombre_prompt}'...",
                            color=ft.Colors.AMBER_800,
                        )
                        texto_resp = extraer_respuesta_automatica(
                            antibot=antibot,
                            stop_event=ctx.stop_event,
                        )

                        if ctx.stop_event.is_set():
                            detenido = True
                            break

                        if texto_resp:
                            if archivo_salida:
                                with open(
                                    os.path.join(path, archivo_salida),
                                    "w",
                                    encoding="utf-8",
                                ) as file:
                                    file.write(texto_resp)
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
                        if es_prompt_teleprompter(prompt):
                            ctx.log_msg(
                                f"📋 Capturando snapshot teleprompter para '{nombre_prompt}'...",
                                color=ft.Colors.AMBER_800,
                            )
                            texto_teleprompter = extraer_respuesta_automatica(
                                antibot=antibot,
                                stop_event=ctx.stop_event,
                            )

                            if ctx.stop_event.is_set():
                                detenido = True
                                break

                            if texto_teleprompter:
                                ruta_snapshot = guardar_snapshot_teleprompter(
                                    path,
                                    idx + 1,
                                    prompt,
                                    texto_teleprompter,
                                )
                                bloques_snapshot = extraer_bloques_teleprompter(
                                    texto_teleprompter
                                )
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
                        ctx.log_msg(
                            f"✅ Prompt '{nombre_prompt}' enviado.",
                            color=ft.Colors.GREEN_700,
                        )
                else:
                    if ctx.stop_event.is_set():
                        detenido = True
                        break
                    ctx.log_msg(
                        f"❌ Error: No se pudo enviar '{nombre_prompt}'.",
                        color=ft.Colors.RED,
                    )

                if idx < len(prompts_a_ejecutar) - 1:
                    if antibot:
                        if not espera_humanizada(3, ctx.stop_event):
                            detenido = True
                            break
                    else:
                        if not sleep_cancelable(3, ctx.stop_event):
                            detenido = True
                            break

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
                    if not all_text_esperado:
                        reconstruccion_ok, reconstruccion_msg = reconstruir_all_text_desde_teleprompters(
                            path,
                            prompts_a_ejecutar,
                        )
                        if reconstruccion_ok:
                            ctx.log_msg(
                                f"✅ {reconstruccion_msg}",
                                color=ft.Colors.GREEN_700,
                                weight="bold",
                            )
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
                    ctx.log_msg(
                        "📄 Buscando all_text.txt para extraer script...",
                        color=ft.Colors.BLUE_800,
                        italic=True,
                    )

                    exito, mensaje = extraer_script_de_all_text(path)

                    if exito:
                        ctx.log_msg(
                            f"✅ {mensaje}",
                            color=ft.Colors.GREEN_700,
                            weight="bold",
                        )

                        if ctx.tts_config.get("enabled"):
                            ctx.log_msg(
                                "🔊 Generando audio con NVIDIA Magpie TTS...",
                                color=ft.Colors.BLUE_800,
                                italic=True,
                            )
                            tts_ok, tts_msg, ruta_audio = sintetizar_script_a_audio_nvidia(
                                path,
                                ctx.tts_config,
                            )
                            if tts_ok:
                                ctx.log_msg(
                                    f"✅ {tts_msg}",
                                    color=ft.Colors.GREEN_700,
                                    weight="bold",
                                )
                                if ctx.whisperx_config.get("enabled") and ruta_audio:
                                    ctx.log_msg(
                                        "🎙️ Iniciando transcripción con WhisperX (esto puede tardar varios minutos)...",
                                        color=ft.Colors.BLUE_800,
                                        italic=True,
                                    )
                                    wx_ok, wx_msg, ruta_json = transcribir_audio_whisperx(
                                        ruta_audio,
                                        ctx.whisperx_config,
                                    )
                                    if wx_ok:
                                        ctx.log_msg(
                                            f"✅ WhisperX: {wx_msg}",
                                            color=ft.Colors.GREEN_700,
                                            weight="bold",
                                        )
                                        ai_studio_runtime = normalizar_ai_studio_config(
                                            ctx.config_actual.get("ai_studio"),
                                            ctx.config_actual.get("prompt_ai_studio"),
                                        )
                                        prompt_ai_base = ai_studio_runtime.get("prompt", "").strip()
                                        if prompt_ai_base:
                                            prompt_ai_ok, prompt_ai_msg, prompt_ai = construir_prompt_ai_studio(
                                                prompt_ai_base,
                                                path,
                                            )
                                            if prompt_ai_ok:
                                                ctx.log_msg(
                                                    f"ℹ AI Studio: {prompt_ai_msg}",
                                                    color=ft.Colors.BLUE_800,
                                                    italic=True,
                                                )
                                                ctx.log_msg(
                                                    "🤖 Abriendo Google AI Studio con el prompt configurado...",
                                                    color=ft.Colors.BLUE_800,
                                                    italic=True,
                                                )
                                                ai_ok, ai_msg = abrir_ai_studio_con_prompt(prompt_ai)
                                                if ai_ok:
                                                    ctx.log_msg(
                                                        f"✅ {ai_msg}",
                                                        color=ft.Colors.GREEN_700,
                                                        weight="bold",
                                                    )
                                                    espera_ai = ai_studio_runtime.get(
                                                        "espera_respuesta_segundos",
                                                        15,
                                                    )
                                                    ctx.log_msg(
                                                        f"⏳ Esperando {espera_ai}s para la respuesta de AI Studio...",
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
                                                            antibot=False,
                                                            stop_event=ctx.stop_event,
                                                        )
                                                        if ctx.stop_event.is_set():
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
                                                                    ctx.log_msg(
                                                                        f"✅ AI Studio: {len(prompts_extraidos)} prompt(s) guardados en {os.path.basename(ruta_prompts)}.",
                                                                        color=ft.Colors.GREEN_700,
                                                                        weight="bold",
                                                                    )
                                                                    if (
                                                                        not ctx.stop_event.is_set()
                                                                        and ai_studio_runtime.get(
                                                                            "auto_send_to_extension",
                                                                            False,
                                                                        )
                                                                    ):
                                                                        ctx.log_msg(
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
                                                    ctx.log_msg(
                                                        f"⚠ AI Studio: {ai_msg}",
                                                        color=ft.Colors.ORANGE_700,
                                                    )
                                            else:
                                                ctx.log_msg(
                                                    f"⚠ AI Studio: {prompt_ai_msg}",
                                                    color=ft.Colors.ORANGE_700,
                                                )
                                        else:
                                            ctx.log_msg(
                                                "⚠ No se abrió AI Studio: el prompt está vacío. Configúralo en el tile de Configuración.",
                                                color=ft.Colors.ORANGE_700,
                                            )
                                    else:
                                        ctx.log_msg(
                                            f"⚠ WhisperX: {wx_msg}",
                                            color=ft.Colors.ORANGE_700,
                                        )
                            else:
                                ctx.log_msg(
                                    f"⚠ {tts_msg}",
                                    color=ft.Colors.ORANGE_700,
                                )
                    else:
                        ctx.log_msg(f"⚠ {mensaje}", color=ft.Colors.ORANGE_700)

                if detenido or ctx.stop_event.is_set():
                    ctx.log_msg(
                        f"⛔ FLUJO DETENIDO por el usuario en video {num}",
                        color=ft.Colors.RED_700,
                        weight="bold",
                    )
                else:
                    ctx.log_msg(
                        f"✅ FINALIZADO: video {num}",
                        color=ft.Colors.GREEN_800,
                        weight="bold",
                    )

        except Exception as ex:
            ctx.log_msg(f"❌ Error: {str(ex)}", color=ft.Colors.RED)

        ctx.prg.visible = False
        ctx.txt_proximo.value = (
            f"Próximo Proyecto: video {obtener_siguiente_num(ctx.ruta_base[0])}"
        )
        ctx.set_estado_ejecutando(False)
        ctx.page.update()

    threading.Thread(target=proceso_hilo, daemon=True).start()