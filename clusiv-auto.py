import flet as ft
import os
import re
import json
import sqlite3
import time
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

# PROMPT CON ESTRUCTURA DE EXTRACCIÓN
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

# Prompts iniciales por defecto cuando no hay config
PROMPTS_DEFAULT = [
    {
        "nombre": "Generar Título",
        "texto": PROMPT_DEFAULT,
        "modo": "nueva",
        "espera_segundos": 30,
        "habilitado": True,
        "post_accion": "extraer_titulo",
        "archivo_salida": "TITULO_FINAL.txt"
    },
    {
        "nombre": "Investigación (5 Key Questions)",
        "texto": PROMPT_INVESTIGACION_DEFAULT,
        "modo": "nueva",
        "espera_segundos": 60,
        "habilitado": True,
        "post_accion": "guardar_respuesta",
        "archivo_salida": "RESPUESTA_INVESTIGACION.txt"
    }
]

# --- 2. GESTIÓN DE CONFIGURACIÓN Y BASE DE DATOS ---
def guardar_config(ruta=None, prompts=None):
    config = cargar_toda_config()
    if ruta is not None: config["ruta_proyectos"] = ruta
    if prompts is not None: config["prompts"] = prompts
    # Limpiar claves legacy al guardar
    config.pop("prompt_template", None)
    config.pop("prompt_investigacion", None)
    config.pop("prompts_adicionales", None)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def cargar_toda_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            conf = json.load(f)
            if "ruta_proyectos" not in conf: conf["ruta_proyectos"] = ""
            # Migración automática de formato legacy
            if "prompts" not in conf:
                prompts_migrados = []
                # Migrar prompt de título
                texto_titulo = conf.get("prompt_template", PROMPT_DEFAULT)
                prompts_migrados.append({
                    "nombre": "Generar Título",
                    "texto": texto_titulo,
                    "modo": "nueva",
                    "espera_segundos": 30,
                    "habilitado": True,
                    "post_accion": "extraer_titulo",
                    "archivo_salida": "TITULO_FINAL.txt"
                })
                # Migrar prompt de investigación
                texto_invest = conf.get("prompt_investigacion", PROMPT_INVESTIGACION_DEFAULT)
                prompts_migrados.append({
                    "nombre": "Investigación (5 Key Questions)",
                    "texto": texto_invest,
                    "modo": "nueva",
                    "espera_segundos": 60,
                    "habilitado": True,
                    "post_accion": "guardar_respuesta",
                    "archivo_salida": "RESPUESTA_INVESTIGACION.txt"
                })
                # Migrar prompts adicionales
                for p in conf.get("prompts_adicionales", []):
                    p.setdefault("post_accion", "solo_enviar")
                    p.setdefault("archivo_salida", "")
                    prompts_migrados.append(p)
                conf["prompts"] = prompts_migrados
                # Limpiar claves legacy
                conf.pop("prompt_template", None)
                conf.pop("prompt_investigacion", None)
                conf.pop("prompts_adicionales", None)
                # Guardar migración
                with open(CONFIG_FILE, "w") as fw:
                    json.dump(conf, fw, indent=4)
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

# --- Helpers de post-acción ---
POST_ACCION_LABELS = {
    "extraer_titulo": "📥 Extraer [FINAL_TITLE] → 💾",
    "guardar_respuesta": "📥 Extraer respuesta → 💾",
    "solo_enviar": "📤 Solo enviar"
}

def describir_pipeline(prompt_item):
    """Genera una descripción visual del pipeline de un prompt."""
    modo = "🆕 Nueva ventana" if prompt_item.get("modo") == "nueva" else "📌 Ventana activa"
    espera = prompt_item.get("espera_segundos", 60)
    post = prompt_item.get("post_accion", "solo_enviar")
    archivo = prompt_item.get("archivo_salida", "")
    
    partes = [f"📤 Enviar ({modo})", f"⏳ {espera}s"]
    if post == "extraer_titulo":
        partes.append(f"📥 Extraer [FINAL_TITLE]")
        if archivo: partes.append(f"💾 {archivo}")
    elif post == "guardar_respuesta":
        partes.append(f"📥 Extraer respuesta")
        if archivo: partes.append(f"💾 {archivo}")
    else:
        partes.append("(solo enviar)")
    
    return " → ".join(partes)


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

    # UI Elements
    input_id = ft.TextField(label="ID del Canal", expand=True)
    input_name = ft.TextField(label="Nombre del Canal", expand=True)
    lista_canales_ui = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, height=400)
    log_ui = ft.Column(spacing=5)
    prg = ft.ProgressBar(width=400, visible=False, color=ft.Colors.GREEN_700)
    txt_proximo = ft.Text(size=14, weight="bold", color=ft.Colors.BLUE_GREY_700)

    def show_snack(msg, color=ft.Colors.GREEN):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), bgcolor=color))
        page.overlay[-1].open = True
        page.update()

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
    def abrir_y_pegar_chatgpt(prompt_final):
        """Abre una NUEVA ventana de ChatGPT y pega el prompt."""
        pyperclip.copy(prompt_final)
        if os.path.exists(PATH_CHATGPT):
            os.startfile(PATH_CHATGPT)
        else:
            webbrowser.open("https://chatgpt.com")
        
        ventana_encontrada = None
        for _ in range(15):
            time.sleep(1)
            windows = [w for w in gw.getAllWindows() if "ChatGPT" in w.title]
            if windows:
                ventana_encontrada = windows[0]
                break
        
        if ventana_encontrada:
            try:
                ventana_encontrada.activate()
                time.sleep(2) 
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.5)
                pyautogui.press('enter')
                return True
            except: pass
        return False

    def enviar_en_ventana_activa(prompt_final):
        """Envía un prompt en la ventana de ChatGPT ya abierta (sin abrir una nueva)."""
        pyperclip.copy(prompt_final)
        windows = [w for w in gw.getAllWindows() if "ChatGPT" in w.title]
        if not windows:
            return False
        ventana = windows[0]
        try:
            ventana.activate()
            time.sleep(2)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.5)
            pyautogui.press('enter')
            return True
        except:
            return False

    def extraer_solo_el_titulo(texto_completo):
        """Usa Regex para extraer el contenido de [FINAL_TITLE: ...] evitando el prompt"""
        patron = r"\[FINAL_TITLE:\s*(.*?)\]"
        # Buscamos TODOS los matches
        matches = re.findall(patron, texto_completo, re.IGNORECASE | re.DOTALL)
        
        # Filtramos los que sean exactamente el placeholder del prompt
        titulos_reales = [
            m.strip() for m in matches 
            if "Put the generated title here" not in m
        ]
        
        if titulos_reales:
            # Retornamos el ÚLTIMO encontrado (el más reciente en el chat)
            return titulos_reales[-1]
        return None

    def extraer_respuesta_automatica():
        try:
            windows = [w for w in gw.getAllWindows() if "ChatGPT" in w.title]
            if not windows: return None
            
            ventana = windows[0]
            ventana.activate()
            time.sleep(1.5)

            # Clic en el centro para asegurar foco
            ancho, alto = ventana.size
            centro_x = ventana.left + (ancho // 2)
            centro_y = ventana.top + (alto // 2)
            pyautogui.click(centro_x, centro_y)
            time.sleep(0.5)

            # Seleccionar todo y Copiar
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(1.5)

            return pyperclip.paste()
        except:
            return None

    # --- FLUJO PRINCIPAL (motor basado en la lista de prompts) ---
    def ejecutar_flujo_completo(e):
        if not ruta_base[0]:
            show_snack("Selecciona una ruta de proyectos", ft.Colors.RED); return
        if not YOUTUBE_API_KEY:
            show_snack("Falta API KEY en .env", ft.Colors.RED); return
            
        log_ui.controls.clear()
        log_ui.controls.append(ft.Text("🚀 Iniciando flujo completo...", italic=True))
        prg.visible = True
        page.update()

        def proceso_hilo():
            canales = obtener_canales_db()
            ganadores_totales = []

            for ch_id, ch_name, _ in canales:
                log_ui.controls.append(ft.Text(f"Analizando: {ch_name}...", size=12))
                page.update()
                data = analizar_rendimiento_canal(ch_id)
                if data and data['ganadores']:
                    v = data['ganadores'][0]
                    v['ch_name'] = ch_name
                    ganadores_totales.append(v)

            if not ganadores_totales:
                log_ui.controls.append(ft.Text("❌ No se encontraron videos ganadores.", color=ft.Colors.RED))
                prg.visible = False
                page.update()
                return

            mejor = max(ganadores_totales, key=lambda x: x['views'])
            titulo_ref = mejor['title']
            
            num = obtener_siguiente_num(ruta_base[0])
            path = os.path.join(ruta_base[0], f"video {num}")
            
            try:
                os.makedirs(os.path.join(path, "assets"), exist_ok=True)
                os.makedirs(os.path.join(path, "images"), exist_ok=True)
                open(os.path.join(path, "scenes.txt"), "w", encoding="utf-8").close()
                open(os.path.join(path, "scenes with duration.txt"), "w", encoding="utf-8").close()
                
                # Variables de contexto disponibles para placeholders
                titulo_final = ""  # Se rellena si algún prompt hace "extraer_titulo"
                
                # Cargar lista unificada de prompts
                todos_prompts = cargar_toda_config().get("prompts", [])
                prompts_activos = [p for p in todos_prompts if p.get("habilitado", True)]
                
                log_ui.controls.append(ft.Text(f"📋 {len(prompts_activos)} prompt(s) habilitado(s) en la cola", color=ft.Colors.PURPLE, weight="bold"))
                page.update()
                
                for idx, p_item in enumerate(prompts_activos):
                    nombre = p_item.get("nombre", f"Prompt {idx+1}")
                    texto = p_item.get("texto", "")
                    modo = p_item.get("modo", "nueva")
                    espera = p_item.get("espera_segundos", 60)
                    post_accion = p_item.get("post_accion", "solo_enviar")
                    archivo = p_item.get("archivo_salida", "")
                    
                    # Reemplazar placeholders
                    texto = texto.replace("[REF_TITLE]", titulo_ref)
                    if titulo_final:
                        texto = texto.replace("[TITULO]", titulo_final)
                    
                    # Guardar prompt enviado
                    nombre_archivo_prompt = f"PROMPT_{idx+1}_{nombre.replace(' ', '_')}.txt"
                    with open(os.path.join(path, nombre_archivo_prompt), "w", encoding="utf-8") as f:
                        f.write(texto)
                    
                    modo_label = "nueva ventana" if modo == "nueva" else "ventana activa"
                    log_ui.controls.append(ft.Text(f"🌐 [{idx+1}/{len(prompts_activos)}] Enviando: {nombre} ({modo_label})...", color=ft.Colors.BLUE))
                    page.update()
                    time.sleep(3)
                    
                    # Enviar según modo
                    if modo == "nueva":
                        exito = abrir_y_pegar_chatgpt(texto)
                    else:
                        exito = enviar_en_ventana_activa(texto)
                    
                    if not exito:
                        log_ui.controls.append(ft.Text(f"❌ Error al enviar '{nombre}'.", color=ft.Colors.RED))
                        page.update()
                        continue
                    
                    # Esperar generación
                    log_ui.controls.append(ft.Text(f"⏳ Esperando {espera}s para '{nombre}'...", italic=True))
                    page.update()
                    time.sleep(espera)
                    
                    # Ejecutar post-acción
                    if post_accion == "extraer_titulo":
                        log_ui.controls.append(ft.Text("📋 Extrayendo título final...", color=ft.Colors.AMBER_800))
                        page.update()
                        
                        texto_copiado = extraer_respuesta_automatica()
                        if texto_copiado:
                            titulo_extraido = extraer_solo_el_titulo(texto_copiado)
                            if titulo_extraido:
                                titulo_final = titulo_extraido
                                if archivo:
                                    with open(os.path.join(path, archivo), "w", encoding="utf-8") as f:
                                        f.write(titulo_final)
                                log_ui.controls.append(ft.Text(f"🎯 Título detectado: {titulo_final}", color=ft.Colors.GREEN_700, weight="bold"))
                                if archivo:
                                    log_ui.controls.append(ft.Text(f"💾 Guardado en {archivo}", color=ft.Colors.GREEN_700))
                            else:
                                with open(os.path.join(path, "RESPUESTA_RAW.txt"), "w", encoding="utf-8") as f:
                                    f.write(texto_copiado)
                                log_ui.controls.append(ft.Text("⚠ No se encontró el título real. Se guardó Raw.", color=ft.Colors.ORANGE))
                        else:
                            log_ui.controls.append(ft.Text("❌ Error: Portapapeles vacío.", color=ft.Colors.RED))
                    
                    elif post_accion == "guardar_respuesta":
                        log_ui.controls.append(ft.Text(f"📋 Extrayendo respuesta para '{nombre}'...", color=ft.Colors.AMBER_800))
                        page.update()
                        
                        texto_copiado = extraer_respuesta_automatica()
                        if texto_copiado:
                            nombre_salida = archivo or f"RESPUESTA_{idx+1}.txt"
                            with open(os.path.join(path, nombre_salida), "w", encoding="utf-8") as f:
                                f.write(texto_copiado)
                            log_ui.controls.append(ft.Text(f"✅ Respuesta guardada en {nombre_salida}", color=ft.Colors.GREEN_700, weight="bold"))
                        else:
                            log_ui.controls.append(ft.Text("❌ Error: No se pudo extraer la respuesta.", color=ft.Colors.RED))
                    
                    else:  # solo_enviar
                        log_ui.controls.append(ft.Text(f"✅ '{nombre}' enviado correctamente.", color=ft.Colors.GREEN_700))
                    
                    page.update()

                log_ui.controls.append(ft.Divider())
                log_ui.controls.append(ft.Text(f"✅ FINALIZADO: video {num}", weight="bold", color=ft.Colors.GREEN_800))

            except Exception as ex:
                log_ui.controls.append(ft.Text(f"Error: {str(ex)}", color=ft.Colors.RED))
            
            prg.visible = False
            txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(ruta_base[0])}"
            page.update()

        threading.Thread(target=proceso_hilo).start()

    # --- PROMPT MANAGER DIALOG ---
    prompts_lista_ui = ft.Column(spacing=5, scroll=ft.ScrollMode.AUTO, height=400)

    def refrescar_prompts_lista():
        prompts_lista_ui.controls.clear()
        prompts = cargar_toda_config().get("prompts", [])
        for i, p in enumerate(prompts):
            habilitado = p.get("habilitado", True)
            pipeline_text = describir_pipeline(p)
            
            prompts_lista_ui.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Checkbox(
                                value=habilitado,
                                on_change=lambda e, idx=i: toggle_prompt_habilitado(idx, e.control.value)
                            ),
                            ft.Container(
                                content=ft.Text(f"{i+1}", size=11, weight="bold", color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER),
                                width=24, height=24, border_radius=12,
                                bgcolor=ft.Colors.BLUE_800 if habilitado else ft.Colors.GREY_400,
                                alignment=ft.alignment.center
                            ),
                            ft.Column([
                                ft.Text(p.get("nombre", f"Prompt {i+1}"), weight="bold", size=13),
                                ft.Text(p.get("texto", "")[:70] + ("..." if len(p.get("texto", "")) > 70 else ""), size=10, color=ft.Colors.GREY_500),
                            ], expand=True, spacing=2),
                            ft.IconButton(ft.Icons.ARROW_UPWARD, icon_size=18, on_click=lambda _, idx=i: mover_prompt(idx, -1), tooltip="Subir"),
                            ft.IconButton(ft.Icons.ARROW_DOWNWARD, icon_size=18, on_click=lambda _, idx=i: mover_prompt(idx, 1), tooltip="Bajar"),
                            ft.IconButton(ft.Icons.EDIT, icon_size=18, icon_color=ft.Colors.BLUE_600, on_click=lambda _, idx=i: abrir_editor_prompt(idx), tooltip="Editar"),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18, icon_color=ft.Colors.RED_400, on_click=lambda _, idx=i: eliminar_prompt(idx), tooltip="Eliminar"),
                        ]),
                        # Pipeline visual
                        ft.Container(
                            content=ft.Text(pipeline_text, size=11, color=ft.Colors.BLUE_GREY_600, italic=True),
                            padding=ft.padding.only(left=50, bottom=4),
                        ),
                    ], spacing=0),
                    padding=8, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=8,
                    bgcolor=ft.Colors.WHITE if habilitado else ft.Colors.GREY_200
                )
            )
        if not prompts:
            prompts_lista_ui.controls.append(
                ft.Text("No hay prompts. Agrega uno con el botón de abajo.", italic=True, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER)
            )
        page.update()

    def toggle_prompt_habilitado(idx, valor):
        config = cargar_toda_config()
        prompts = config.get("prompts", [])
        if idx < len(prompts):
            prompts[idx]["habilitado"] = valor
            guardar_config(prompts=prompts)
            refrescar_prompts_lista()

    def mover_prompt(idx, direction):
        config = cargar_toda_config()
        prompts = config.get("prompts", [])
        new_idx = idx + direction
        if 0 <= new_idx < len(prompts):
            prompts[idx], prompts[new_idx] = prompts[new_idx], prompts[idx]
            guardar_config(prompts=prompts)
            refrescar_prompts_lista()

    def eliminar_prompt(idx):
        config = cargar_toda_config()
        prompts = config.get("prompts", [])
        if idx < len(prompts):
            prompts.pop(idx)
            guardar_config(prompts=prompts)
            refrescar_prompts_lista()
            show_snack("Prompt eliminado", ft.Colors.ORANGE)

    # --- Editor de prompt (agregar / editar) ---
    editor_nombre = ft.TextField(label="Nombre del prompt", expand=True)
    editor_texto = ft.TextField(label="Texto del prompt (placeholders: [REF_TITLE], [TITULO])", multiline=True, min_lines=6, max_lines=10, expand=True)
    editor_modo = ft.Dropdown(
        label="Modo de envío",
        options=[ft.dropdown.Option("activa", "📌 Ventana Activa"), ft.dropdown.Option("nueva", "🆕 Nueva Ventana")],
        value="activa", width=220
    )
    editor_espera = ft.TextField(label="Espera (seg)", value="60", width=120, keyboard_type=ft.KeyboardType.NUMBER)
    editor_post_accion = ft.Dropdown(
        label="Post-acción",
        options=[
            ft.dropdown.Option("extraer_titulo", "📥 Extraer título [FINAL_TITLE]"),
            ft.dropdown.Option("guardar_respuesta", "📥 Guardar respuesta completa"),
            ft.dropdown.Option("solo_enviar", "📤 Solo enviar (sin extraer)"),
        ],
        value="solo_enviar", width=280
    )
    editor_archivo = ft.TextField(label="Archivo de salida (ej: RESULTADO.txt)", value="", expand=True)
    editor_idx_actual = [None]  # None = agregar nuevo, int = editar existente

    def abrir_editor_prompt(idx=None):
        # Cerrar Prompt Manager primero (Flet no soporta 2 dialogs abiertos)
        dlg_prompt_manager.open = False
        page.update()
        if idx is not None:
            config = cargar_toda_config()
            prompts = config.get("prompts", [])
            if idx < len(prompts):
                p = prompts[idx]
                editor_nombre.value = p.get("nombre", "")
                editor_texto.value = p.get("texto", "")
                editor_modo.value = p.get("modo", "activa")
                editor_espera.value = str(p.get("espera_segundos", 60))
                editor_post_accion.value = p.get("post_accion", "solo_enviar")
                editor_archivo.value = p.get("archivo_salida", "")
                editor_idx_actual[0] = idx
        else:
            editor_nombre.value = ""
            editor_texto.value = ""
            editor_modo.value = "activa"
            editor_espera.value = "60"
            editor_post_accion.value = "solo_enviar"
            editor_archivo.value = ""
            editor_idx_actual[0] = None
        dlg_editor.open = True
        page.update()

    def guardar_prompt_editor(e):
        config = cargar_toda_config()
        prompts = config.get("prompts", [])
        nuevo = {
            "nombre": editor_nombre.value.strip() or "Sin nombre",
            "texto": editor_texto.value.strip(),
            "modo": editor_modo.value,
            "espera_segundos": int(editor_espera.value) if editor_espera.value.isdigit() else 60,
            "habilitado": True,
            "post_accion": editor_post_accion.value,
            "archivo_salida": editor_archivo.value.strip()
        }
        if editor_idx_actual[0] is not None and editor_idx_actual[0] < len(prompts):
            nuevo["habilitado"] = prompts[editor_idx_actual[0]].get("habilitado", True)
            prompts[editor_idx_actual[0]] = nuevo
        else:
            prompts.append(nuevo)
        guardar_config(prompts=prompts)
        dlg_editor.open = False
        page.update()
        show_snack("Prompt guardado ✅")
        # Reabrir Prompt Manager
        refrescar_prompts_lista()
        dlg_prompt_manager.open = True
        page.update()

    def cerrar_editor_y_reabrir_manager():
        dlg_editor.open = False
        page.update()
        refrescar_prompts_lista()
        dlg_prompt_manager.open = True
        page.update()

    dlg_editor = ft.AlertDialog(
        modal=True,
        title=ft.Text("Editar Prompt"),
        content=ft.Container(
            width=550,
            content=ft.Column([
                editor_nombre,
                editor_texto,
                ft.Row([editor_modo, editor_espera]),
                ft.Divider(),
                ft.Text("¿Qué sucede después de enviar?", weight="bold", size=12, color=ft.Colors.BLUE_GREY_700),
                editor_post_accion,
                editor_archivo,
            ], spacing=10, tight=True)
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda _: cerrar_editor_y_reabrir_manager()),
            ft.ElevatedButton("Guardar", on_click=guardar_prompt_editor, bgcolor=ft.Colors.GREEN_700, color="white"),
        ]
    )
    page.overlay.append(dlg_editor)

    dlg_prompt_manager = ft.AlertDialog(
        modal=False,
        title=ft.Row([ft.Icon(ft.Icons.LIST_ALT, color=ft.Colors.BLUE_800), ft.Text("Prompt Manager", weight="bold")]),
        content=ft.Container(
            width=700,
            height=530,
            content=ft.Column([
                ft.Text("Gestiona todos los prompts del flujo. Se ejecutan en orden de arriba a abajo.", size=12, color=ft.Colors.GREY_600),
                ft.Text("Placeholders: [REF_TITLE] = título de YouTube, [TITULO] = título extraído por el primer prompt", size=11, color=ft.Colors.BLUE_GREY_400, italic=True),
                ft.Divider(),
                prompts_lista_ui,
                ft.Divider(),
                ft.ElevatedButton("➕ Agregar Prompt", on_click=lambda _: abrir_editor_prompt(None), bgcolor=ft.Colors.BLUE_800, color="white", width=1000),
            ], spacing=8)
        ),
        actions=[
            ft.TextButton("Cerrar", on_click=lambda _: setattr(dlg_prompt_manager, 'open', False) or page.update()),
        ]
    )
    page.overlay.append(dlg_prompt_manager)

    def abrir_prompt_manager(e):
        refrescar_prompts_lista()
        dlg_prompt_manager.open = True
        page.update()

    # --- UI LAYOUT ---
    tile_gestion = ft.Card(col={"md": 4}, content=ft.Container(padding=20, content=ft.Column([
        ft.Row([ft.Icon(ft.Icons.PEOPLE_ALT), ft.Text("CANALES", weight="bold")]),
        ft.Row([input_id, input_name]),
        ft.ElevatedButton("Agregar", icon=ft.Icons.ADD, on_click=agregar_canal, width=1000, bgcolor=ft.Colors.BLUE_800, color="white"),
        ft.Divider(),
        lista_canales_ui
    ])))

    tile_flujo = ft.Card(col={"md": 4}, content=ft.Container(padding=20, content=ft.Column([
        ft.Row([ft.Icon(ft.Icons.BOLT, color=ft.Colors.AMBER_700), ft.Text("AUTOMATIZACIÓN", weight="bold")]),
        ft.ElevatedButton("EJECUTAR FLUJO COMPLETO", icon=ft.Icons.AUTO_AWESOME, on_click=ejecutar_flujo_completo, bgcolor=ft.Colors.GREEN_700, color="white", height=50, width=1000),
        ft.ElevatedButton("📋 Prompt Manager", icon=ft.Icons.LIST_ALT, on_click=abrir_prompt_manager, bgcolor=ft.Colors.BLUE_600, color="white", height=40, width=1000),
        prg,
        ft.Divider(),
        log_ui
    ])))

    tile_config = ft.Card(col={"md": 4}, content=ft.Container(padding=20, content=ft.Column([
        ft.Row([ft.Icon(ft.Icons.SETTINGS), ft.Text("CONFIGURACIÓN", weight="bold")]),
        txt_proximo,
        ft.ElevatedButton("Ruta de Proyectos", icon=ft.Icons.FOLDER_OPEN, on_click=lambda _: picker.get_directory_path()),
    ])))

    picker = ft.FilePicker(on_result=lambda e: (guardar_config(ruta=e.path), page.update()) if e.path else None)
    page.overlay.append(picker)

    page.add(
        ft.Row([ft.Text("Clusiv", size=32, weight="bold", color=ft.Colors.BLUE_800), ft.Text("Automation", size=32)], alignment=ft.MainAxisAlignment.CENTER),
        ft.ResponsiveRow([tile_gestion, tile_flujo, tile_config])
    )
    refrescar_canales()

if __name__ == "__main__":
    ft.app(target=main)