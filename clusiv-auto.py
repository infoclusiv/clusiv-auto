import flet as ft
import os
import re
import json
import sqlite3
import time
import random
import threading
import pyautogui
import pygetwindow as gw
import webbrowser
import pyperclip
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from dotenv import load_dotenv

# --- 1. CONFIGURACIÓN Y RUTAS ---
load_dotenv()
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

# Ruta de la aplicación ChatGPT (Chrome App)
PATH_CHATGPT = r"C:\Users\carlo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Aplicaciones de Chrome\ChatGPT.lnk"

CONFIG_FILE = "config_automatizacion.json"
DATABASE_FILE = "channels.db"

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
        "wpm_escritura": 45,
        "post_accion": "extraer_titulo",
        "archivo_salida": "TITULO_FINAL.txt"
    },
    {
        "nombre": "Investigación (5 Key Questions)",
        "texto": PROMPT_INVESTIGACION_DEFAULT,
        "modo": "nueva",
        "espera_segundos": 60,
        "habilitado": True,
        "antibot": True,
        "wpm_escritura": 45,
        "post_accion": "guardar_respuesta",
        "archivo_salida": "RESPUESTA_INVESTIGACION.txt"
    }
]

# --- 2. GESTIÓN DE CONFIGURACIÓN Y BASE DE DATOS ---
def guardar_config(ruta=None, prompts=None):
    config = cargar_toda_config()
    if ruta is not None:
        config["ruta_proyectos"] = ruta
    if prompts is not None:
        config["prompts"] = prompts
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def cargar_toda_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            conf = json.load(f)
            if "ruta_proyectos" not in conf:
                conf["ruta_proyectos"] = ""
            # Migración automática del formato legacy
            if "prompts" not in conf:
                prompts = []
                pt = conf.pop("prompt_template", PROMPT_DEFAULT)
                pi = conf.pop("prompt_investigacion", PROMPT_INVESTIGACION_DEFAULT)
                prompts.append({
                    "nombre": "Generar Título",
                    "texto": pt,
                    "modo": "nueva",
                    "espera_segundos": 30,
                    "habilitado": True,
                    "antibot": True,
                    "wpm_escritura": 45,
                    "post_accion": "extraer_titulo",
                    "archivo_salida": "TITULO_FINAL.txt"
                })
                prompts.append({
                    "nombre": "Investigación (5 Key Questions)",
                    "texto": pi,
                    "modo": "nueva",
                    "espera_segundos": 60,
                    "habilitado": True,
                    "antibot": True,
                    "wpm_escritura": 45,
                    "post_accion": "guardar_respuesta",
                    "archivo_salida": "RESPUESTA_INVESTIGACION.txt"
                })
                conf["prompts"] = prompts
                # Guardar migración
                with open(CONFIG_FILE, "w", encoding="utf-8") as fw:
                    json.dump(conf, fw, indent=4, ensure_ascii=False)
            else:
                # Migración de campos antibot para prompts existentes
                migrado = False
                for p in conf["prompts"]:
                    if "antibot" not in p:
                        p["antibot"] = True
                        migrado = True
                    if "wpm_escritura" not in p:
                        p["wpm_escritura"] = 45
                        migrado = True
                if migrado:
                    with open(CONFIG_FILE, "w", encoding="utf-8") as fw:
                        json.dump(conf, fw, indent=4, ensure_ascii=False)
            return conf
    return {"ruta_proyectos": "", "prompts": list(PROMPTS_DEFAULT)}

def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS channels 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      channel_id TEXT UNIQUE NOT NULL, 
                      channel_name TEXT NOT NULL, 
                      category TEXT DEFAULT 'Noticias')''')
    conn.commit()
    conn.close()

def obtener_canales_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, channel_name, category FROM channels ORDER BY category")
    rows = cursor.fetchall()
    conn.close()
    return rows

def agregar_canal_db(ch_id, ch_name):
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        conn.execute('INSERT INTO channels (channel_id, channel_name) VALUES (?, ?)', 
                     (ch_id.strip(), ch_name.strip()))
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

# --- 2.5 FUNCIONES ANTI-BOT ---
def escribir_humanizado(texto, wpm=45, stop_event=None):
    """Escribe texto carácter por carácter simulando velocidad humana.
    Pausas asimétricas: espacio y Enter tardan más que letras normales.
    Se detiene si stop_event está activado."""
    wpm_real = wpm * random.uniform(0.8, 1.2)
    base_delay = 60.0 / (wpm_real * 5)
    for char in texto:
        if stop_event and stop_event.is_set():
            return False
        if char == ' ':
            time.sleep(random.uniform(base_delay * 1.8, base_delay * 3.5))
            pyautogui.press('space')
        elif char == '\n':
            time.sleep(random.uniform(base_delay * 3.0, base_delay * 5.0))
            pyautogui.press('enter')
        elif char == '\t':
            time.sleep(random.uniform(base_delay * 0.5, base_delay * 1.0))
            pyautogui.press('tab')
        else:
            time.sleep(random.uniform(base_delay * 0.5, base_delay * 1.5))
            pyautogui.typewrite(char, interval=0) if char.isascii() and char.isprintable() else pyautogui.hotkey(char)
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
    if not YOUTUBE_API_KEY: return None
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        fecha_limite = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat().replace('+00:00', 'Z')
        search_res = youtube.search().list(
            part='id', channelId=channel_id, publishedAfter=fecha_limite, 
            type='video', maxResults=50, order='date'
        ).execute()
        video_ids = [item['id']['videoId'] for item in search_res.get('items', [])]
        if not video_ids: return None
        stats_res = youtube.videos().list(part='snippet,statistics', id=','.join(video_ids)).execute()
        videos_data = [{'title': i['snippet']['title'], 'views': int(i['statistics'].get('viewCount', 0))} for i in stats_res.get('items', [])]
        if not videos_data: return None
        avg = sum(v['views'] for v in videos_data) / len(videos_data)
        ganadores = sorted([v for v in videos_data if v['views'] > avg], key=lambda x: x['views'], reverse=True)
        return {"avg": avg, "ganadores": ganadores}
    except: return None

def obtener_siguiente_num(ruta_base):
    if not ruta_base or not os.path.exists(ruta_base): return 1
    carpetas = [d for d in os.listdir(ruta_base) if os.path.isdir(os.path.join(ruta_base, d))]
    nums = [int(m.group(1)) for c in carpetas if (m := re.search(r"video\s*(\d+)", c, re.IGNORECASE))]
    return max(nums) + 1 if nums else 1

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
    
    # Señal de cancelación para detener el flujo
    stop_event = threading.Event()

    # UI Elements
    input_id = ft.TextField(label="ID del Canal", expand=True)
    input_name = ft.TextField(label="Nombre del Canal", expand=True)
    lista_canales_ui = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, height=400)
    log_ui = ft.Column(spacing=5)
    prg = ft.ProgressBar(width=400, visible=False, color=ft.Colors.GREEN_700)
    txt_proximo = ft.Text(size=14, weight="bold", color=ft.Colors.BLUE_GREY_700)

    # Botón de detener flujo y referencia mutable del botón ejecutar
    btn_ejecutar_ref = [None]  # Se asignará más adelante (lista mutable para referencia)
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
        log_ui.controls.append(
            ft.Text("⛔ Solicitud de detención enviada. Esperando que el paso actual finalice...",
                    color=ft.Colors.ORANGE_800, weight="bold", italic=True)
        )
        page.update()

    def set_estado_ejecutando(ejecutando):
        """Alterna visibilidad/estado de los botones ejecutar/detener."""
        if btn_ejecutar_ref[0]:
            btn_ejecutar_ref[0].disabled = ejecutando
            btn_ejecutar_ref[0].bgcolor = ft.Colors.GREY_500 if ejecutando else ft.Colors.GREEN_700
        btn_detener.visible = ejecutando
        btn_detener.disabled = False
        btn_detener.text = "DETENER FLUJO"
        btn_detener.bgcolor = ft.Colors.RED_700
        page.update()

    # Prompt Manager UI container
    prompts_ui = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO)

    def show_snack(msg, color=ft.Colors.GREEN):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), bgcolor=color))
        page.overlay[-1].open = True
        page.update()

    # --- PROMPT MANAGER ---
    def obtener_pipeline_visual(p):
        """Genera el pipeline visual de un prompt."""
        icono_modo = "🆕 Nueva ventana" if p.get("modo") == "nueva" else "📌 Ventana activa"
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

    def guardar_prompts():
        """Guarda la lista de prompts en el config."""
        guardar_config(prompts=prompts_lista)

    def refrescar_prompts():
        """Reconstruye la UI del prompt manager."""
        prompts_ui.controls.clear()
        for idx, p in enumerate(prompts_lista):
            nombre = p.get("nombre", f"Prompt {idx+1}")
            habilitado = p.get("habilitado", True)
            pipeline = obtener_pipeline_visual(p)
            
            # Tarjeta de cada prompt
            card = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Switch(
                            value=habilitado,
                            active_color=ft.Colors.GREEN_600,
                            on_change=lambda e, i=idx: toggle_prompt(i, e.control.value),
                        ),
                        ft.Text(nombre, weight="bold", size=14, expand=True,
                                color=ft.Colors.BLACK if habilitado else ft.Colors.GREY_500),
                        ft.IconButton(
                            ft.Icons.EDIT_NOTE, icon_color=ft.Colors.BLUE_600, tooltip="Editar",
                            on_click=lambda _, i=idx: abrir_editor_prompt(i)
                        ),
                        ft.IconButton(
                            ft.Icons.ARROW_UPWARD, icon_color=ft.Colors.GREY_600, tooltip="Subir",
                            on_click=lambda _, i=idx: mover_prompt(i, -1),
                            disabled=(idx == 0)
                        ),
                        ft.IconButton(
                            ft.Icons.ARROW_DOWNWARD, icon_color=ft.Colors.GREY_600, tooltip="Bajar",
                            on_click=lambda _, i=idx: mover_prompt(i, 1),
                            disabled=(idx == len(prompts_lista) - 1)
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, tooltip="Eliminar",
                            on_click=lambda _, i=idx: eliminar_prompt(i)
                        ),
                    ], alignment=ft.MainAxisAlignment.START),
                    ft.Container(
                        content=ft.Text(pipeline, size=11, color=ft.Colors.BLUE_GREY_600, italic=True),
                        padding=ft.padding.only(left=50)
                    ),
                ], spacing=2),
                padding=12,
                border=ft.border.all(1, ft.Colors.GREEN_300 if habilitado else ft.Colors.GREY_300),
                border_radius=8,
                bgcolor=ft.Colors.WHITE if habilitado else ft.Colors.GREY_100,
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
            prompts_lista[idx], prompts_lista[nuevo_idx] = prompts_lista[nuevo_idx], prompts_lista[idx]
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
            "wpm_escritura": 45,
            "post_accion": "solo_enviar",
            "archivo_salida": ""
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
            multiline=True, min_lines=6, max_lines=12, text_size=12
        )
        f_modo = ft.Dropdown(
            label="Modo de ventana",
            value=p.get("modo", "nueva"),
            options=[
                ft.dropdown.Option("nueva", "🆕 Nueva ventana"),
                ft.dropdown.Option("activa", "📌 Ventana activa"),
            ],
            dense=True, width=250
        )
        f_espera = ft.TextField(
            label="Espera (segundos)",
            value=str(p.get("espera_segundos", 30)),
            width=150, dense=True,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        f_post_accion = ft.Dropdown(
            label="Post-Acción",
            value=p.get("post_accion", "solo_enviar"),
            options=[
                ft.dropdown.Option("extraer_titulo", "📥 Extraer [FINAL_TITLE]"),
                ft.dropdown.Option("guardar_respuesta", "📥 Guardar respuesta completa"),
                ft.dropdown.Option("solo_enviar", "📤 Solo enviar"),
            ],
            dense=True, width=300
        )
        f_archivo = ft.TextField(
            label="Archivo de salida", value=p.get("archivo_salida", ""),
            dense=True, width=300
        )

        # --- Anti-Bot Controls ---
        f_antibot = ft.Switch(
            label="🛡️ Anti-Bot (Escritura humanizada, pausas aleatorias, scroll)",
            value=p.get("antibot", True),
            active_color=ft.Colors.TEAL_600,
        )
        
        wpm_value = p.get("wpm_escritura", 45)
        f_wpm_label = ft.Text(f"{wpm_value} WPM", size=13, weight="bold", color=ft.Colors.TEAL_700)
        
        def on_wpm_change(e):
            val = int(e.control.value)
            f_wpm_label.value = f"{val} WPM"
            page.update()
        
        f_wpm_slider = ft.Slider(
            min=20, max=120, divisions=20,
            value=wpm_value,
            label="{value} WPM",
            active_color=ft.Colors.TEAL_600,
            on_change=on_wpm_change,
            expand=True,
        )

        antibot_section = ft.Container(
            content=ft.Column([
                f_antibot,
                ft.Row([
                    ft.Text("Velocidad de escritura:", size=12, color=ft.Colors.GREY_700),
                    f_wpm_slider,
                    f_wpm_label,
                ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text(
                    "Lento ← 20 WPM ··· 120 WPM → Rápido",
                    size=10, color=ft.Colors.GREY_500, italic=True,
                    text_align=ft.TextAlign.CENTER,
                ),
            ], spacing=4),
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
                content=ft.Column([
                    f_nombre,
                    f_texto,
                    ft.Row([f_modo, f_espera]),
                    ft.Row([f_post_accion, f_archivo]),
                    ft.Divider(),
                    antibot_section,
                ], spacing=10, scroll=ft.ScrollMode.AUTO, height=520),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=cerrar_editor),
                ft.ElevatedButton("Guardar", on_click=guardar_editor, bgcolor=ft.Colors.GREEN_700, color="white"),
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
                    content=ft.Row([
                        ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, color=ft.Colors.RED_600, size=20),
                        ft.Column([ft.Text(ch[1], weight="bold", size=12), ft.Text(ch[0], size=9)], expand=True, spacing=0),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, on_click=lambda _, id=ch[0]: borrar_canal(id))
                    ]),
                    padding=8, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=8
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
            input_id.value = ""; input_name.value = ""
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
                    resultado = escribir_humanizado(prompt_final, wpm=wpm, stop_event=stop_event)
                    if not resultado:
                        return False
                    if not espera_humanizada(0.5, stop_event):
                        return False
                    pyautogui.press('enter')
                else:
                    pyperclip.copy(prompt_final)
                    pyautogui.hotkey('ctrl', 'v')
                    if not sleep_cancelable(0.5, stop_event):
                        return False
                    pyautogui.press('enter')
                return True
            except:
                pass
        return False

    def extraer_solo_el_titulo(texto_completo):
        """Usa Regex para extraer el contenido de [FINAL_TITLE: ...] evitando el prompt"""
        patron = r"\[FINAL_TITLE:\s*(.*?)\]"
        matches = re.findall(patron, texto_completo, re.IGNORECASE | re.DOTALL)
        titulos_reales = [
            m.strip() for m in matches 
            if "Put the generated title here" not in m
        ]
        if titulos_reales:
            return titulos_reales[-1]
        return None

    def extraer_respuesta_automatica(antibot=False):
        try:
            if stop_event.is_set():
                return None
            
            windows = [w for w in gw.getAllWindows() if "ChatGPT" in w.title]
            if not windows: return None
            
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

            pyautogui.hotkey('ctrl', 'a')
            if antibot:
                if not espera_humanizada(0.5, stop_event):
                    return None
            else:
                if not sleep_cancelable(0.5, stop_event):
                    return None
            pyautogui.hotkey('ctrl', 'c')
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
            show_snack("Selecciona una ruta de proyectos", ft.Colors.RED); return
        if not YOUTUBE_API_KEY:
            show_snack("Falta API KEY en .env", ft.Colors.RED); return
        
        habilitados = [p for p in prompts_lista if p.get("habilitado", True)]
        if not habilitados:
            show_snack("No hay prompts habilitados", ft.Colors.RED); return
        
        # Limpiar señal de cancelación y preparar UI
        stop_event.clear()
        log_ui.controls.clear()
        log_ui.controls.append(ft.Text("🚀 Iniciando flujo completo...", italic=True))
        prg.visible = True
        set_estado_ejecutando(True)
        page.update()

        def proceso_hilo():
            detenido = False
            try:
                canales = obtener_canales_db()
                ganadores_totales = []

                for ch_id, ch_name, _ in canales:
                    if stop_event.is_set():
                        detenido = True
                        break
                    log_ui.controls.append(ft.Text(f"Analizando: {ch_name}...", size=12))
                    page.update()
                    data = analizar_rendimiento_canal(ch_id)
                    if data and data['ganadores']:
                        v = data['ganadores'][0]
                        v['ch_name'] = ch_name
                        ganadores_totales.append(v)

                if detenido or stop_event.is_set():
                    log_ui.controls.append(ft.Text("⛔ Flujo detenido por el usuario durante el análisis de canales.", color=ft.Colors.RED_700, weight="bold"))
                    prg.visible = False
                    set_estado_ejecutando(False)
                    page.update()
                    return

                if not ganadores_totales:
                    log_ui.controls.append(ft.Text("❌ No se encontraron videos ganadores.", color=ft.Colors.RED))
                    prg.visible = False
                    set_estado_ejecutando(False)
                    page.update()
                    return

                mejor = max(ganadores_totales, key=lambda x: x['views'])
                titulo_ref = mejor['title']
                
                num = obtener_siguiente_num(ruta_base[0])
                path = os.path.join(ruta_base[0], f"video {num}")
                
                os.makedirs(os.path.join(path, "assets"), exist_ok=True)
                os.makedirs(os.path.join(path, "images"), exist_ok=True)
                open(os.path.join(path, "scenes.txt"), "w", encoding="utf-8").close()
                open(os.path.join(path, "scenes with duration.txt"), "w", encoding="utf-8").close()
                
                titulo_extraido = None

                for idx, p in enumerate(habilitados):
                    if stop_event.is_set():
                        detenido = True
                        break

                    nombre_prompt = p.get("nombre", f"Prompt {idx+1}")
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
                    
                    nombre_archivo_prompt = f"PROMPT_{idx+1}_{nombre_prompt.replace(' ', '_')}.txt"
                    with open(os.path.join(path, nombre_archivo_prompt), "w", encoding="utf-8") as f:
                        f.write(texto_prompt)
                    
                    ab_tag = " 🛡️" if ab else ""
                    log_ui.controls.append(ft.Text(f"🌐 [{idx+1}/{len(habilitados)}] Enviando: {nombre_prompt}{ab_tag}...", color=ft.Colors.BLUE))
                    page.update()
                    
                    if stop_event.is_set():
                        detenido = True
                        break

                    envio_ok = abrir_y_pegar_chatgpt(texto_prompt, modo=modo, antibot=ab, wpm=wpm)
                    
                    if stop_event.is_set():
                        detenido = True
                        break

                    if envio_ok:
                        log_ui.controls.append(ft.Text(f"⏳ Esperando ~{espera}s generación...", italic=True))
                        page.update()
                        
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
                            log_ui.controls.append(ft.Text("📋 Extrayendo título final...", color=ft.Colors.AMBER_800))
                            page.update()
                            texto_copiado = extraer_respuesta_automatica(antibot=ab)
                            
                            if stop_event.is_set():
                                detenido = True
                                break
                            
                            if texto_copiado:
                                titulo_final = extraer_solo_el_titulo(texto_copiado)
                                if titulo_final:
                                    titulo_extraido = titulo_final
                                    if archivo_salida:
                                        with open(os.path.join(path, archivo_salida), "w", encoding="utf-8") as f:
                                            f.write(titulo_final)
                                    log_ui.controls.append(ft.Text(f"🎯 Título detectado: {titulo_final}", color=ft.Colors.GREEN_700, weight="bold"))
                                else:
                                    with open(os.path.join(path, "RESPUESTA_RAW.txt"), "w", encoding="utf-8") as f:
                                        f.write(texto_copiado)
                                    log_ui.controls.append(ft.Text("⚠ No se encontró el título real. Se guardó Raw.", color=ft.Colors.ORANGE))
                            else:
                                log_ui.controls.append(ft.Text("❌ Error: Portapapeles vacío.", color=ft.Colors.RED))
                                
                        elif post_accion == "guardar_respuesta":
                            log_ui.controls.append(ft.Text(f"📋 Extrayendo respuesta para '{nombre_prompt}'...", color=ft.Colors.AMBER_800))
                            page.update()
                            texto_resp = extraer_respuesta_automatica(antibot=ab)
                            
                            if stop_event.is_set():
                                detenido = True
                                break
                            
                            if texto_resp:
                                if archivo_salida:
                                    with open(os.path.join(path, archivo_salida), "w", encoding="utf-8") as f:
                                        f.write(texto_resp)
                                log_ui.controls.append(ft.Text(f"✅ Respuesta guardada: {archivo_salida}", color=ft.Colors.GREEN_700, weight="bold"))
                            else:
                                log_ui.controls.append(ft.Text(f"❌ Error al extraer respuesta de '{nombre_prompt}'.", color=ft.Colors.RED))
                        else:
                            log_ui.controls.append(ft.Text(f"✅ Prompt '{nombre_prompt}' enviado.", color=ft.Colors.GREEN_700))
                    else:
                        if stop_event.is_set():
                            detenido = True
                            break
                        log_ui.controls.append(ft.Text(f"❌ Error: No se pudo enviar '{nombre_prompt}'.", color=ft.Colors.RED))
                    
                    page.update()
                    
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
                log_ui.controls.append(ft.Divider())
                if detenido or stop_event.is_set():
                    log_ui.controls.append(ft.Text(f"⛔ FLUJO DETENIDO por el usuario en video {num}", weight="bold", color=ft.Colors.RED_700))
                else:
                    log_ui.controls.append(ft.Text(f"✅ FINALIZADO: video {num}", weight="bold", color=ft.Colors.GREEN_800))

            except Exception as ex:
                log_ui.controls.append(ft.Text(f"Error: {str(ex)}", color=ft.Colors.RED))
            
            prg.visible = False
            txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(ruta_base[0])}"
            set_estado_ejecutando(False)
            page.update()

        threading.Thread(target=proceso_hilo, daemon=True).start()

    # --- UI LAYOUT ---
    tile_gestion = ft.Card(col={"md": 4}, content=ft.Container(padding=20, content=ft.Column([
        ft.Row([ft.Icon(ft.Icons.PEOPLE_ALT), ft.Text("CANALES", weight="bold")]),
        ft.Row([input_id, input_name]),
        ft.ElevatedButton("Agregar", icon=ft.Icons.ADD, on_click=agregar_canal, width=1000, bgcolor=ft.Colors.BLUE_800, color="white"),
        ft.Divider(),
        lista_canales_ui
    ])))

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

    tile_flujo = ft.Card(col={"md": 4}, content=ft.Container(padding=20, content=ft.Column([
        ft.Row([ft.Icon(ft.Icons.BOLT, color=ft.Colors.AMBER_700), ft.Text("AUTOMATIZACIÓN", weight="bold")]),
        btn_ejecutar_widget,
        btn_detener,
        prg,
        ft.Divider(),
        log_ui
    ])))

    tile_config = ft.Card(col={"md": 4}, content=ft.Container(padding=20, content=ft.Column([
        ft.Row([ft.Icon(ft.Icons.SETTINGS), ft.Text("CONFIGURACIÓN", weight="bold")]),
        txt_proximo,
        ft.ElevatedButton("Ruta de Proyectos", icon=ft.Icons.FOLDER_OPEN, on_click=lambda _: picker.get_directory_path()),
    ])))

    tile_prompts = ft.Card(col={"md": 12}, content=ft.Container(padding=20, content=ft.Column([
        ft.Row([
            ft.Icon(ft.Icons.AUTO_FIX_HIGH, color=ft.Colors.PURPLE_600),
            ft.Text("PROMPT MANAGER", weight="bold", size=16, expand=True),
            ft.ElevatedButton(
                "Agregar Prompt",
                icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                on_click=agregar_prompt_nuevo,
                bgcolor=ft.Colors.PURPLE_600,
                color="white",
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Divider(),
        prompts_ui
    ])))

    picker = ft.FilePicker(on_result=lambda e: (guardar_config(ruta=e.path), page.update()) if e.path else None)
    page.overlay.append(picker)

    page.add(
        ft.Row([ft.Text("Clusiv", size=32, weight="bold", color=ft.Colors.BLUE_800), ft.Text("Automation", size=32)], alignment=ft.MainAxisAlignment.CENTER),
        ft.ResponsiveRow([tile_gestion, tile_flujo, tile_config]),
        ft.ResponsiveRow([tile_prompts]),
    )
    refrescar_canales()
    refrescar_prompts()

if __name__ == "__main__":
    ft.app(target=main)