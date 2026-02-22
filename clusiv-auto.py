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
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from dotenv import load_dotenv

# --- 1. CONFIGURACIÓN Y PERSISTENCIA ---
load_dotenv()
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

CONFIG_FILE = "config_automatizacion.json"
DATABASE_FILE = "channels.db"

PROMPT_DEFAULT = """**Act as a senior YouTube Growth Strategist and expert Copywriter.**

I have a specific video title that performed exceptionally well on my channel. I need you to reverse-engineer its success and use those insights to create better, high-CTR variations in English.

**The successful title (in Spanish) was:**
[REF_TITLE]

**Please complete the following two steps:**

**STEP 1: The Analysis**
Briefly analyze **why** this title worked effectively. Identify the psychological triggers (e.g., fear, urgency, curiosity, high stakes) and the power keywords used. Explain the "hook" mechanism behind it.

**STEP 2: The Proposal**
Based on your analysis, generate **5 new high-performing title variations in ENGLISH**.

**Guidelines for the new titles:**
1.  **Language:** All titles must be in **English**.
2.  **Psychology:** Leverage the "Curiosity Gap" or "Urgency" triggers.
3.  **Structure:** Use "Front-loading" (put the most impactful words at the beginning).
4.  **Length:** Keep them concise (optimized for mobile).
5.  **Variety:** Provide different angles (e.g., a warning, a question, a scenario)."""

def guardar_config(ruta=None, prompt=None):
    config = cargar_toda_config()
    if ruta is not None: config["ruta_proyectos"] = ruta
    if prompt is not None: config["prompt_template"] = prompt
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def cargar_toda_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            conf = json.load(f)
            if "ruta_proyectos" not in conf: conf["ruta_proyectos"] = ""
            if "prompt_template" not in conf: conf["prompt_template"] = PROMPT_DEFAULT
            return conf
    return {"ruta_proyectos": "", "prompt_template": PROMPT_DEFAULT}

# --- 2. LÓGICA DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS channels 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      channel_id TEXT UNIQUE NOT NULL, 
                      channel_name TEXT NOT NULL, 
                      category TEXT DEFAULT 'Noticias')''')
    conn.commit()
    conn.close()

def agregar_canal_db(ch_id, ch_name, ch_cat):
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        conn.execute('INSERT INTO channels (channel_id, channel_name, category) VALUES (?, ?, ?)', 
                     (ch_id.strip(), ch_name.strip(), ch_cat.strip()))
        conn.commit()
        return True, f"Canal '{ch_name}' guardado."
    except sqlite3.IntegrityError:
        return False, "Ese ID de canal ya existe."
    finally:
        conn.close()

def obtener_canales_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, channel_name, category FROM channels ORDER BY category")
    rows = cursor.fetchall()
    conn.close()
    return rows

def eliminar_canal_db(ch_id):
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute("DELETE FROM channels WHERE channel_id = ?", (ch_id,))
    conn.commit()
    conn.close()

# --- 3. LÓGICA DE YOUTUBE ---
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

# --- 4. LÓGICA DE CARPETAS ---
def obtener_siguiente_num(ruta_base):
    if not ruta_base or not os.path.exists(ruta_base): return 1
    carpetas = [d for d in os.listdir(ruta_base) if os.path.isdir(os.path.join(ruta_base, d))]
    nums = [int(m.group(1)) for c in carpetas if (m := re.search(r"video\s*(\d+)", c, re.IGNORECASE))]
    return max(nums) + 1 if nums else 1

# --- 5. INTERFAZ FLET ---
def main(page: ft.Page):
    page.title = "Clusiv Automation Hub"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#F0F2F6"
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    
    init_db()
    config_actual = cargar_toda_config()
    ruta_base = [config_actual["ruta_proyectos"]]

    # --- ELEMENTOS DE UI ---
    input_id = ft.TextField(label="ID del Canal", expand=True)
    input_name = ft.TextField(label="Nombre del Canal", expand=True)
    
    lista_canales_ui = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, height=400)
    log_ui = ft.Column(spacing=5)
    prg = ft.ProgressBar(width=400, visible=False, color=ft.Colors.GREEN_700)
    txt_proximo = ft.Text(size=14, weight="bold", color=ft.Colors.BLUE_GREY_700)

    field_prompt = ft.TextField(
        label="Prompt Template (usa [REF_TITLE])",
        multiline=True,
        min_lines=8,
        max_lines=10,
        value=config_actual["prompt_template"],
        text_size=12,
        bgcolor=ft.Colors.WHITE
    )

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
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, icon_size=18, on_click=lambda _, id=ch[0]: borrar_canal(id))
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
            res, msg = agregar_canal_db(input_id.value, input_name.value, "General")
            show_snack(msg, ft.Colors.GREEN if res else ft.Colors.RED)
            input_id.value = ""; input_name.value = ""
            refrescar_canales()

    def guardar_prompt_event(e):
        guardar_config(prompt=field_prompt.value)
        show_snack("Prompt guardado", ft.Colors.BLUE)

    # --- AUTOMATIZACIÓN DE CHAGPT (LÓGICA EXTRAÍDA) ---
    def automatizar_chatgpt(prompt_final):
        # 1. Copiar al portapapeles
        page.set_clipboard(prompt_final)
        
        # 2. Buscar ventana de ChatGPT
        windows = [w for w in gw.getAllWindows() if "ChatGPT" in w.title]
        
        if not windows:
            # Si no está abierta, intentamos abrir el navegador
            webbrowser.open("https://chatgpt.com")
            time.sleep(6) # Esperar a que cargue la web
            windows = [w for w in gw.getAllWindows() if "ChatGPT" in w.title]

        if windows:
            try:
                w = windows[0]
                w.activate()
                time.sleep(1) # Pequeña pausa para asegurar foco
                pyautogui.hotkey('ctrl', 'v') # Pegar
                time.sleep(0.5)
                pyautogui.press('enter') # Enviar
            except Exception as e:
                print(f"Error en automatización: {e}")

    # --- FLUJO AUTOMÁTICO ---
    def ejecutar_flujo_completo(e):
        if not ruta_base[0]:
            show_snack("Primero selecciona una ruta base", ft.Colors.RED); return
        if not YOUTUBE_API_KEY:
            show_snack("Falta API KEY en el archivo .env", ft.Colors.RED); return
            
        log_ui.controls.clear()
        log_ui.controls.append(ft.Text("🚀 Iniciando flujo automático...", italic=True))
        prg.visible = True
        page.update()

        # Usamos threading para no congelar la UI de Flet
        def proceso():
            canales = obtener_canales_db()
            todos_los_ganadores = []

            for ch_id, ch_name, _ in canales:
                log_ui.controls.append(ft.Text(f"Analizando: {ch_name}...", size=12))
                page.update()
                
                data = analizar_rendimiento_canal(ch_id)
                if data and data['ganadores']:
                    mejor_del_canal = data['ganadores'][0]
                    mejor_del_canal['channel_name'] = ch_name
                    todos_los_ganadores.append(mejor_del_canal)

            if not todos_los_ganadores:
                log_ui.controls.append(ft.Text("❌ Sin videos virales nuevos.", color=ft.Colors.RED))
                prg.visible = False
                page.update()
                return

            ganador_supremo = max(todos_los_ganadores, key=lambda x: x['views'])
            titulo = ganador_supremo['title']
            
            num = obtener_siguiente_num(ruta_base[0])
            path = os.path.join(ruta_base[0], f"video {num}")
            
            try:
                os.makedirs(path, exist_ok=True)
                os.makedirs(os.path.join(path, "assets"), exist_ok=True)
                os.makedirs(os.path.join(path, "images"), exist_ok=True)
                
                with open(os.path.join(path, "scenes.txt"), "w", encoding="utf-8") as f: pass
                with open(os.path.join(path, "scenes with duration.txt"), "w", encoding="utf-8") as f: pass
                
                prompt_final = field_prompt.value.replace("[REF_TITLE]", titulo)
                with open(os.path.join(path, "PROMPT_IA.txt"), "w", encoding="utf-8") as f:
                    f.write(prompt_final)
                
                # --- NUEVA ACCIÓN: AUTOMATIZAR CHATGPT ---
                log_ui.controls.append(ft.Text("🤖 Enviando a ChatGPT...", color=ft.Colors.BLUE))
                page.update()
                automatizar_chatgpt(prompt_final)

                log_ui.controls.append(ft.Divider())
                log_ui.controls.append(ft.Text(f"✅ ¡ÉXITO! Proyecto: video {num}", weight="bold", color=ft.Colors.GREEN_700))
                log_ui.controls.append(ft.Text(f"Título: {titulo}", size=12))
                
            except Exception as ex:
                log_ui.controls.append(ft.Text(f"Error: {str(ex)}", color=ft.Colors.RED))
            
            prg.visible = False
            txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(ruta_base[0])}"
            page.update()

        threading.Thread(target=proceso).start()

    # --- DISEÑO UI ---
    tile_gestion = ft.Card(
        col={"md": 4},
        content=ft.Container(padding=20, content=ft.Column([
            ft.Row([ft.Icon(ft.Icons.PEOPLE_ALT), ft.Text("CANALES", weight="bold")]),
            ft.Row([input_id, input_name]),
            ft.ElevatedButton("Agregar", icon=ft.Icons.ADD, on_click=agregar_canal, width=1000, bgcolor=ft.Colors.BLUE_800, color="white"),
            ft.Divider(),
            lista_canales_ui
        ]))
    )

    tile_flujo = ft.Card(
        col={"md": 4},
        content=ft.Container(padding=20, content=ft.Column([
            ft.Row([ft.Icon(ft.Icons.BOLT, color=ft.Colors.AMBER_700), ft.Text("AUTOMATIZACIÓN", weight="bold")]),
            ft.Text("Analiza canales, crea carpetas y envía el prompt a ChatGPT con un clic.", size=12, color=ft.Colors.GREY_700),
            ft.ElevatedButton(
                "EJECUTAR FLUJO COMPLETO", 
                icon=ft.Icons.AUTO_AWESOME, 
                on_click=ejecutar_flujo_completo, 
                bgcolor=ft.Colors.GREEN_700, 
                color="white", 
                height=50,
                width=1000
            ),
            prg,
            ft.Divider(),
            ft.Text("LOG DE ACTIVIDAD:", size=10, weight="bold"),
            log_ui
        ]))
    )

    tile_config = ft.Card(
        col={"md": 4},
        content=ft.Container(padding=20, content=ft.Column([
            ft.Row([ft.Icon(ft.Icons.SETTINGS), ft.Text("CONFIGURACIÓN", weight="bold")]),
            txt_proximo,
            ft.ElevatedButton("Ruta de Proyectos", icon=ft.Icons.FOLDER_OPEN, on_click=lambda _: picker.get_directory_path()),
            ft.Divider(),
            field_prompt,
            ft.ElevatedButton("Guardar Prompt Template", icon=ft.Icons.SAVE, on_click=guardar_prompt_event, width=1000)
        ]))
    )

    def on_folder(e: ft.FilePickerResultEvent):
        if e.path:
            ruta_base[0] = e.path
            guardar_config(ruta=e.path)
            txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(e.path)}"
            show_snack("Ruta guardada"); page.update()

    picker = ft.FilePicker(on_result=on_folder); page.overlay.append(picker)

    page.add(
        ft.Row([
            ft.Text("Clusiv", size=32, weight="bold", color=ft.Colors.BLUE_800),
            ft.Text("Automation Hub", size=32, weight="light")
        ], alignment=ft.MainAxisAlignment.CENTER),
        ft.ResponsiveRow([tile_gestion, tile_flujo, tile_config], run_spacing=20)
    )
    
    txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(ruta_base[0])}"
    refrescar_canales()

if __name__ == "__main__":
    ft.app(target=main)