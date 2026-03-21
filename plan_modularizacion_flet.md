# Plan de Modularización: `ui_main.py` (Flet)

> **Para agente de IA:** Este plan modulariza `ui_main.py` manteniéndolo en Flet.
> Al finalizar, la app debe funcionar **exactamente igual** que antes.
> No se cambia ninguna funcionalidad. No se migra de framework.
> Ejecutar los pasos en orden estricto. Verificar cada paso antes de continuar.

---

## Contexto

- **Archivo a modularizar:** `ui_main.py` (1986 líneas, Flet)
- **Punto de entrada:** `clusiv-auto.py` → `ft.app(target=main)` — **no se toca**
- **Archivos de lógica que nunca se modifican:**
  `config.py`, `database.py`, `flow_orchestrator.py`, `ws_bridge.py`,
  `youtube_analyzer.py`, `tts_nvidia.py`, `whisperx_runner.py`, `antibot.py`

---

## Estado inicial del archivo

`ui_main.py` contiene una sola función `main(page)` con todo dentro:
estado compartido, funciones de lógica UI, construcción de widgets y ensamblaje final.
Las secciones identificadas y sus líneas aproximadas son:

| Sección | Líneas aprox. | Descripción |
|---|---|---|
| Estado compartido | 42–91 | `config_actual`, `ruta_base`, `prompts_lista`, `stop_event`, etc. |
| Consola de logs | 92–176 | `log_msg()`, `log_ui`, `log_container` |
| Panel de ejecución | 177–244 | `prg`, `btn_ejecutar`, `btn_detener`, `set_estado_ejecutando()` |
| Helpers de prompts | 245–370 | `obtener_pipeline_visual()`, `crear_badge()`, `guardar_prompts()`, selectores |
| Panel prompts (galería) | 371–795 | `refrescar_prompts()`, `abrir_editor_prompt()`, CRUD de prompts |
| Panel canales | 796–841 | `refrescar_canales()`, `agregar_canal()`, `borrar_canal()` |
| Tracker de fases | 843–940 | `construir_tracker_fases()` |
| Flujo principal | 941–991 | `ejecutar_flujo_completo()`, `btn_ejecutar_widget` |
| Panel TTS | 993–1088 | Widgets + `persistir_tts_desde_ui()`, `probar_tts_ultimo_proyecto()` |
| Panel WhisperX | 1089–1124 | Widgets + `persistir_whisperx_desde_ui()` |
| Panel AI Studio | 1126–1193 | Widgets + `persistir_ai_studio_desde_ui()` |
| Panel Flow/Imágenes | 1194–1371 | Widgets config imágenes + `enviar_prompts_manualmente()` |
| Panel Extension/Journeys | 1373–1520 | Widgets journeys + `ordenar_ejecucion_journey()`, `pegar_script_ahora()` |
| Header bar | 1547–1570 | `header_bar`, `actualizar_ext_status_header()` |
| Ensamblaje ExpansionTiles | 1572–1863 | `expansion_*`, `col_izquierda`, `col_central`, `col_derecha` |
| Inicialización y `page.add()` | 1960–1986 | Estado inicial y montaje final |

---

## Estructura objetivo

```
clusiv-auto/
├── clusiv-auto.py          ← NO SE TOCA
├── ui_main.py              ← se reemplaza (solo ensamblaje, ~120 líneas)
├── ui/
│   ├── __init__.py         ← crear (vacío)
│   ├── state.py            ← crear (estado compartido)
│   ├── consola.py          ← crear
│   ├── tracker.py          ← crear
│   ├── header.py           ← crear
│   ├── panel_proyecto.py   ← crear
│   ├── panel_prompts.py    ← crear
│   ├── panel_tts.py        ← crear
│   ├── panel_whisperx.py   ← crear
│   ← panel_ai_studio.py   ← crear
│   └── panel_flow.py       ← crear (Flow + Journeys juntos)
└── [resto de archivos sin cambios]
```

**Tamaño esperado de cada archivo:**

| Archivo | Líneas aprox. |
|---|---|
| `ui/state.py` | ~40 |
| `ui/consola.py` | ~100 |
| `ui/tracker.py` | ~110 |
| `ui/header.py` | ~60 |
| `ui/panel_proyecto.py` | ~130 |
| `ui/panel_prompts.py` | ~480 |
| `ui/panel_tts.py` | ~130 |
| `ui/panel_whisperx.py` | ~70 |
| `ui/panel_ai_studio.py` | ~100 |
| `ui/panel_flow.py` | ~380 |
| `ui_main.py` (nuevo) | ~120 |

---

## Reglas que el agente debe respetar en todos los pasos

1. **Cero cambios funcionales.** Mover código, no reescribirlo.
2. **Cero renombrado de variables.** Si en el original se llama `txt_tts_voice`, en el módulo también.
3. **Las funciones que usan `page` deben recibirla como parámetro** si la necesitan, o accederla a través del estado compartido.
4. **Las funciones que modifican estado compartido** (`ruta_base`, `prompts_lista`, `tts_config`, etc.) deben recibir ese estado como parámetro — nunca leer variables de otro módulo directamente.
5. **`ws_bridge`** se sigue importando directamente donde se necesite — no se abstrae.
6. **Cada módulo nuevo debe poder importarse sin errores** antes de integrarse en `ui_main.py`.

---

## PASO 1 — Crear la carpeta `ui/` y el archivo `__init__.py`

**Acción:**
1. Crear carpeta `ui/` en la raíz del proyecto (mismo nivel que `ui_main.py`)
2. Crear archivo `ui/__init__.py` con contenido vacío

**Verificación:**
```bash
python -c "import ui; print('OK')"
```

**Criterio de éxito:** El comando imprime `OK` sin errores.

---

## PASO 2 — Crear `ui/state.py` (estado compartido)

**Por qué existe este archivo:**
El estado que hoy vive dentro de `main()` necesita ser accesible por todos los módulos.
En lugar de pasarlo como argumento a cada función, se centraliza en un objeto `AppState`.

**Extraer de `ui_main.py` (líneas 49–73) las siguientes variables:**
- `config_actual`
- `ruta_base`
- `prompts_lista`
- `ejecutar_hasta_prompt`
- `tts_config`
- `whisperx_config`
- `ai_studio_config`
- `ref_image_paths_state`
- `stop_event`

**Contenido de `ui/state.py`:**

```python
# ui/state.py
import threading
from config import (
    cargar_toda_config,
    normalizar_tts_config,
    normalizar_ai_studio_config,
    normalizar_ejecutar_hasta_prompt,
    obtener_whisperx_config_default,
)
from database import init_db


class AppState:
    """Estado compartido de la aplicación. Se instancia una sola vez en ui_main.py."""

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
```

**Verificación:**
```python
from ui.state import AppState
s = AppState()
print(s.prompts_lista)
print(s.tts_config)
print("state OK")
```

**Criterio de éxito:** Se instancia sin errores y los valores reflejan el config actual.

---

## PASO 3 — Crear `ui/consola.py`

**Extraer de `ui_main.py`:**
- Variables: `log_ui` (línea 78), `log_container` (línea 83)
- Función: `log_msg()` completa (líneas 92–173)
- Constante: `MAX_LOG_MESSAGES = 150` (línea 169)
- La asignación `ws_bridge.ui_log_cb = log_msg` **no** va aquí — va en `ui_main.py`

**Firma de la función pública que debe exportar:**
```python
def build_consola(page) -> tuple:
    """
    Retorna (log_container, log_msg, limpiar_log)
    - log_container: ft.Container listo para montar en la UI
    - log_msg: función para agregar mensajes
    - limpiar_log: función para vaciar la consola
    """
```

**El código interno de `log_msg` no cambia ni una línea.**

**Verificación:**
```python
from ui.consola import build_consola
# No se puede testear sin ft.Page, pero debe importarse sin errores
print("consola OK")
```

**Criterio de éxito:** `from ui.consola import build_consola` no lanza excepciones.

---

## PASO 4 — Crear `ui/tracker.py`

**Extraer de `ui_main.py`:**
- Función completa `construir_tracker_fases(page)` (líneas 843–940)

**No cambiar nada internamente.** Solo moverla a su propio archivo.

**Contenido de `ui/tracker.py`:**
```python
# ui/tracker.py
import flet as ft


def construir_tracker_fases(page):
    # ... pegar aquí el cuerpo exacto de la función desde ui_main.py ...
    # Retorna: (ft.Column, set_fase_estado, reset_tracker)
```

**Verificación:**
```python
from ui.tracker import construir_tracker_fases
print("tracker OK")
```

**Criterio de éxito:** Importa sin errores.

---

## PASO 5 — Crear `ui/header.py`

**Extraer de `ui_main.py`:**
- Variables: `icono_ext_status` (línea 1524), `lbl_ext_status` (línea 1527)
- Función: `actualizar_ext_status_header(conectada, version="")` (líneas 1532–1544)
- Widget: `header_bar` (líneas 1547–1570)

**Firma de la función pública:**
```python
def build_header(page) -> tuple:
    """
    Retorna (header_bar, actualizar_ext_status_header)
    - header_bar: ft.Container listo para montar
    - actualizar_ext_status_header: función para cambiar el estado de la extensión
    """
```

**Verificación:**
```python
from ui.header import build_header
print("header OK")
```

**Criterio de éxito:** Importa sin errores.

---

## PASO 6 — Crear `ui/panel_proyecto.py`

**Extraer de `ui_main.py`:**
- Variables: `input_id` (línea 75), `input_name` (línea 76), `lista_canales_ui` (línea 77)
- Funciones: `refrescar_canales()`, `borrar_canal()`, `agregar_canal()` (líneas 796–841)
- Función: `on_pick_directory(e)` (líneas 1509–1515)
- Variables: `picker` (línea 1517), registro en `page.overlay` (línea 1519)
- Widget: `expansion_proyecto` (líneas 1572–1606)

**Firma de la función pública:**
```python
def build_panel_proyecto(page, state) -> tuple:
    """
    Retorna (expansion_tile, picker, refrescar_canales, txt_proximo_ref)
    - expansion_tile: ft.ExpansionTile listo para montar
    - picker: ft.FilePicker (debe agregarse a page.overlay en ui_main.py)
    - refrescar_canales: función para recargar la lista
    - on_ruta_cambiada: callback que recibe la nueva ruta (para actualizar txt_proximo)
    """
```

**Parámetros que recibe `state`:**
- `state.ruta_base` — para leer y escribir la ruta actual
- `state.config_actual` — para guardar

**Nota:** `txt_proximo` vive en el panel central (paso 10), no aquí.
`on_pick_directory` debe llamar un callback externo para actualizar `txt_proximo`.
Usar un parámetro `on_ruta_cambiada: callable` para esto.

**Verificación:**
```python
from ui.panel_proyecto import build_panel_proyecto
print("panel_proyecto OK")
```

**Criterio de éxito:** Importa sin errores.

---

## PASO 7 — Crear `ui/panel_prompts.py`

> Este es el módulo más grande. Tomar el tiempo necesario.

**Extraer de `ui_main.py`:**
- Variable: `txt_prompt_count` (línea ~1196)
- Variable: `prompts_ui` (línea 233), `txt_alcance_flujo` (línea 236), `txt_alcance_selector` (línea 237)
- Variable: `dropdown_ejecutar_hasta` (líneas 1143–1149)
- Variable: `prompts_gallery_scroll` (líneas ~1195–1200)
- Funciones helpers: `obtener_pipeline_visual()`, `crear_badge()` (líneas 249–288)
- Funciones CRUD: `guardar_prompts()`, `obtener_prompts_para_ejecucion()`,
  `actualizar_resumen_alcance()`, `actualizar_selector_ejecucion()`,
  `persistir_alcance_ejecucion()`, `refrescar_prompts()` (líneas 290–369, 367–565)
- Funciones de acciones: `toggle_prompt()`, `deshabilitar_todos_prompts()`,
  `habilitar_todos_prompts()`, `mover_prompt()`, `eliminar_prompt()`,
  `agregar_prompt_nuevo()` (líneas 562–615)
- Diálogo: `abrir_editor_prompt()` completo (líneas 617–795)
- Widget: `expansion_prompts` (líneas 1607–1659)

**Firma de la función pública:**
```python
def build_panel_prompts(page, state) -> tuple:
    """
    Retorna (expansion_tile, obtener_prompts_para_ejecucion, actualizar_resumen_alcance,
             btn_ejecutar_text_updater)
    """
```

**Parámetros que recibe `state`:**
- `state.prompts_lista`
- `state.ejecutar_hasta_prompt`
- `state.config_actual`

**Dependencia cruzada crítica:** `actualizar_resumen_alcance()` necesita actualizar
el texto del botón ejecutar que vive en el panel central.
Resolver con un parámetro callback `on_alcance_cambiado: callable` que recibe `(texto_boton, descripcion)`.

**Verificación:**
```python
from ui.panel_prompts import build_panel_prompts
print("panel_prompts OK")
```

**Criterio de éxito:** Importa sin errores.

---

## PASO 8 — Crear `ui/panel_tts.py`

**Extraer de `ui_main.py`:**
- Variable: `txt_nvidia_status` (líneas 993–999)
- Variables widgets: `switch_tts_enabled`, `txt_tts_language`, `txt_tts_voice`,
  `txt_tts_output`, `txt_tts_sample_rate` (líneas 1000–1027)
- Funciones: `persistir_tts_desde_ui()`, `guardar_tts()`, `probar_tts_ultimo_proyecto()` (líneas 304–307, 1028–1088)
- Asignaciones `on_blur` / `on_change` (líneas 1048–1052)
- Widget: `expansion_tts` (líneas 1660–1689)

**Firma de la función pública:**
```python
def build_panel_tts(page, state, log_msg) -> tuple:
    """
    Retorna (expansion_tile, get_tts_config)
    - log_msg: función de la consola para reportar resultados del test TTS
    """
```

**Parámetros que recibe `state`:**
- `state.tts_config`
- `state.ruta_base`

**Verificación:**
```python
from ui.panel_tts import build_panel_tts
print("panel_tts OK")
```

**Criterio de éxito:** Importa sin errores.

---

## PASO 9 — Crear `ui/panel_whisperx.py`

**Extraer de `ui_main.py`:**
- Variables widgets: `switch_whisperx_enabled`, `txt_whisperx_model`, `txt_whisperx_python` (líneas 1089–1112)
- Funciones: `persistir_whisperx_desde_ui()` (líneas 1113–1121)
- Asignaciones `on_change` / `on_blur` (líneas 1122–1124)
- Widget: `expansion_whisperx` (líneas 1690–1711)

**Firma de la función pública:**
```python
def build_panel_whisperx(page, state) -> tuple:
    """
    Retorna (expansion_tile, get_whisperx_config)
    """
```

**Parámetros que recibe `state`:**
- `state.whisperx_config`

**Verificación:**
```python
from ui.panel_whisperx import build_panel_whisperx
print("panel_whisperx OK")
```

**Criterio de éxito:** Importa sin errores.

---

## PASO 10 — Crear `ui/panel_ai_studio.py`

**Extraer de `ui_main.py`:**
- Variables widgets: `txt_prompt_ai_studio`, `txt_ai_studio_wait` (líneas 1126–1142)
- Función: `persistir_ai_studio_desde_ui()` (líneas 1150–1172)
- Asignaciones `on_blur` (líneas 1173–1174)
- Widget: `expansion_ai_studio` (líneas 1712–1740)

**Firma de la función pública:**
```python
def build_panel_ai_studio(page, state) -> tuple:
    """
    Retorna (expansion_tile, get_ai_studio_config)
    """
```

**Parámetros que recibe `state`:**
- `state.ai_studio_config`
- `state.config_actual`

**Verificación:**
```python
from ui.panel_ai_studio import build_panel_ai_studio
print("panel_ai_studio OK")
```

**Criterio de éxito:** Importa sin errores.

---

## PASO 11 — Crear `ui/panel_flow.py`

> Agrupa "Generación de Imágenes" y "Control de Extensión/Journeys" porque comparten
> `ws_bridge`, `ref_image_paths_state` y `ai_studio_config`. Son dos secciones del mismo
> `expansion_flow` en el original.

**Extraer de `ui_main.py`:**

*Sección imágenes (líneas 1194–1371):*
- Variables: `switch_auto_send`, `dropdown_imagen_model`, `dropdown_imagen_aspect`,
  `dropdown_imagen_count`, `lbl_imagen_status`, `lbl_ref_images`, `dropdown_ref_mode`
- Funciones: `crear_lbl_imagen_status()`, `persistir_imagen_config()`,
  `enviar_prompts_manualmente()`, `solicitar_estado_cola()`,
  `_actualizar_label_ref_images()`, `on_ref_images_picked()`, `limpiar_ref_images()`
- Variable: `ref_images_picker` (línea 1518), registro en `page.overlay` (línea 1520)
- Callback: `actualizar_estado_imagen()` (líneas 179–187)
- Asignación: `ws_bridge.ui_image_status_cb = actualizar_estado_imagen` — **va en `ui_main.py`**

*Sección journeys (líneas 1373–1498):*
- Variables: `dropdown_journeys`, `dropdown_second_journey`, `chk_pegar_script`, `chk_segundo_journey`
- Funciones: `actualizar_estado_segundo_journey()`, `obtener_texto_script_ultimo_video()`,
  `refrescar_journeys_ui()`, `solicitar_journeys()`, `ordenar_ejecucion_journey()`, `pegar_script_ahora()`
- Asignación: `ws_bridge.ui_update_journeys_cb = refrescar_journeys_ui` — **va en `ui_main.py`**

*Widget final:*
- `expansion_flow` completo (líneas 1741–1851)
- `lbl_imagen_status_sidebar` (línea 1530) — también se construye aquí

**Firma de la función pública:**
```python
def build_panel_flow(page, state, log_msg) -> tuple:
    """
    Retorna (expansion_tile, ref_images_picker, actualizar_estado_imagen,
             refrescar_journeys_ui, lbl_imagen_status_sidebar)
    - ref_images_picker: ft.FilePicker (debe agregarse a page.overlay en ui_main.py)
    - actualizar_estado_imagen: para asignar a ws_bridge.ui_image_status_cb
    - refrescar_journeys_ui: para asignar a ws_bridge.ui_update_journeys_cb
    """
```

**Parámetros que recibe `state`:**
- `state.ai_studio_config`
- `state.config_actual`
- `state.ref_image_paths_state`
- `state.ruta_base`

**Verificación:**
```python
from ui.panel_flow import build_panel_flow
print("panel_flow OK")
```

**Criterio de éxito:** Importa sin errores.

---

## PASO 12 — Reescribir `ui_main.py` como ensamblador

**Este es el único paso donde se modifica `ui_main.py`.**
El archivo nuevo solo importa los módulos y los conecta. Cero lógica de UI aquí.

**Estructura del nuevo `ui_main.py`:**

```python
# ui_main.py
import flet as ft
import ws_bridge
from config import AI_STUDIO_OUTPUT_FILENAME_DEFAULT
from youtube_analyzer import obtener_siguiente_num
from flow_orchestrator import FlowContext, ejecutar_flujo
import threading

from ui.state import AppState
from ui.consola import build_consola
from ui.tracker import construir_tracker_fases
from ui.header import build_header
from ui.panel_proyecto import build_panel_proyecto
from ui.panel_prompts import build_panel_prompts
from ui.panel_tts import build_panel_tts
from ui.panel_whisperx import build_panel_whisperx
from ui.panel_ai_studio import build_panel_ai_studio
from ui.panel_flow import build_panel_flow


def main(page: ft.Page):
    page.title = "Clusiv Automation Hub"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#F0F2F6"
    page.padding = 0
    page.scroll = None

    # 1. Estado compartido
    state = AppState()

    # 2. Consola
    log_container, log_msg, limpiar_log = build_consola(page)
    ws_bridge.ui_log_cb = log_msg

    # 3. Tracker
    tracker_widget, set_fase_estado, reset_tracker = construir_tracker_fases(page)

    # 4. Header
    header_bar, actualizar_ext_status_header = build_header(page)
    ws_bridge.ui_ext_status_cb = actualizar_ext_status_header

    # 5. Panel proyecto
    expansion_proyecto, picker, refrescar_canales, on_ruta_cambiada = build_panel_proyecto(
        page, state, on_ruta_cambiada=lambda ruta: _actualizar_txt_proximo(ruta)
    )
    page.overlay.append(picker)

    # 6. Panel prompts
    expansion_prompts, obtener_prompts_para_ejecucion, actualizar_resumen_alcance = (
        build_panel_prompts(page, state, on_alcance_cambiado=lambda txt, desc: _sync_boton_ejecutar(txt, desc))
    )

    # 7. Panel TTS
    expansion_tts, _ = build_panel_tts(page, state, log_msg)

    # 8. Panel WhisperX
    expansion_whisperx, _ = build_panel_whisperx(page, state)

    # 9. Panel AI Studio
    expansion_ai_studio, _ = build_panel_ai_studio(page, state)

    # 10. Panel Flow + Journeys
    (
        expansion_flow,
        ref_images_picker,
        actualizar_estado_imagen,
        refrescar_journeys_ui,
        lbl_imagen_status_sidebar,
    ) = build_panel_flow(page, state, log_msg)
    page.overlay.append(ref_images_picker)
    ws_bridge.ui_image_status_cb = actualizar_estado_imagen
    ws_bridge.ui_update_journeys_cb = refrescar_journeys_ui

    # 11. Panel central: progreso + botones de ejecución
    prg = ft.ProgressBar(width=400, visible=False, color=ft.Colors.GREEN_700)
    txt_proximo = ft.Text(size=14, weight="bold", color=ft.Colors.BLUE_GREY_700)

    def _actualizar_txt_proximo(ruta):
        txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(ruta)}"
        page.update()

    txt_alcance_flujo = ft.Text(size=12, color=ft.Colors.BLUE_GREY_600, italic=True)

    btn_ejecutar_ref = [None]

    btn_detener = ft.ElevatedButton(
        "DETENER FLUJO",
        icon=ft.Icons.STOP_CIRCLE,
        bgcolor=ft.Colors.RED_700,
        color="white",
        height=50,
        width=1000,
        visible=False,
        on_click=lambda _: _detener_flujo(),
    )

    def _detener_flujo():
        state.stop_event.set()
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

    def _set_estado_ejecutando(ejecutando):
        if btn_ejecutar_ref[0]:
            btn_ejecutar_ref[0].disabled = ejecutando
            btn_ejecutar_ref[0].bgcolor = ft.Colors.GREY_500 if ejecutando else ft.Colors.GREEN_700
        btn_detener.visible = ejecutando
        btn_detener.disabled = False
        btn_detener.text = "DETENER FLUJO"
        btn_detener.bgcolor = ft.Colors.RED_700
        page.update()

    def _sync_boton_ejecutar(texto_boton, descripcion):
        if btn_ejecutar_ref[0]:
            btn_ejecutar_ref[0].text = texto_boton
        txt_alcance_flujo.value = f"Alcance actual: {descripcion}"

    def ejecutar_flujo_completo(e):
        if not state.ruta_base[0]:
            _show_snack("Selecciona una ruta de proyectos", ft.Colors.RED)
            return
        from config import YOUTUBE_API_KEY
        if not YOUTUBE_API_KEY:
            _show_snack("Falta API KEY en .env", ft.Colors.RED)
            return

        prompts_a_ejecutar, _ = obtener_prompts_para_ejecucion()
        if not prompts_a_ejecutar:
            _show_snack("No hay prompts configurados", ft.Colors.RED)
            return

        log_container.content.controls.clear()
        prg.visible = True
        _set_estado_ejecutando(True)
        reset_tracker()
        page.update()

        ctx = FlowContext(
            stop_event=state.stop_event,
            log_msg=log_msg,
            ruta_base=state.ruta_base,
            prompts_lista=state.prompts_lista,
            tts_config=state.tts_config,
            whisperx_config=state.whisperx_config,
            config_actual=state.config_actual,
            ejecutar_hasta_prompt=state.ejecutar_hasta_prompt,
            ref_image_paths_state=state.ref_image_paths_state,
            dropdown_ref_mode=_get_dropdown_ref_mode(),
            prg=prg,
            txt_proximo=txt_proximo,
            page=page,
            set_estado_ejecutando=_set_estado_ejecutando,
            obtener_prompts_para_ejecucion=obtener_prompts_para_ejecucion,
            set_fase_estado=set_fase_estado,
            reset_tracker=reset_tracker,
        )
        ejecutar_flujo(ctx)

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

    # Nota: _get_dropdown_ref_mode() debe obtenerse del panel_flow
    # (ver sección de "Dependencias cruzadas" al final de este plan)

    def _show_snack(msg, color=ft.Colors.GREEN):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), bgcolor=color))
        page.overlay[-1].open = True
        page.update()

    # 12. Columnas de layout
    col_izquierda = ft.Container(
        width=420,
        padding=ft.padding.only(left=16, top=16, right=8, bottom=16),
        content=ft.Column(
            [
                ft.Text("Configuración del Pipeline", size=12, weight="bold",
                        color=ft.Colors.GREY_500, italic=True),
                expansion_proyecto,
                expansion_prompts,
                expansion_tts,
                expansion_whisperx,
                expansion_ai_studio,
                expansion_flow,
            ],
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    col_central = ft.Container(
        width=320,
        padding=ft.padding.symmetric(horizontal=8, vertical=16),
        content=ft.Column(
            [
                ft.Text("Pipeline de Ejecución", size=12, weight="bold",
                        color=ft.Colors.GREY_500, italic=True),
                ft.Divider(),
                txt_proximo,
                ft.Divider(),
                btn_ejecutar_widget,
                txt_alcance_flujo,
                btn_detener,
                prg,
                ft.Divider(),
                ft.Text("Estado del flujo", size=12, weight="bold", color=ft.Colors.GREY_500),
                tracker_widget,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    btn_limpiar_log = ft.TextButton(
        "Limpiar",
        icon=ft.Icons.DELETE_SWEEP,
        icon_color=ft.Colors.GREY_500,
        on_click=limpiar_log,
        style=ft.ButtonStyle(color=ft.Colors.GREY_500),
    )

    col_derecha = ft.Container(
        expand=True,
        padding=ft.padding.only(left=8, top=16, right=16, bottom=16),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Row([ft.Icon(ft.Icons.TERMINAL, color=ft.Colors.GREY_500, size=16),
                                ft.Text("Consola de ejecución", size=12, weight="bold",
                                        color=ft.Colors.GREY_500)], spacing=6),
                        btn_limpiar_log,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                log_container,
                ft.Divider(),
                ft.Row([ft.Icon(ft.Icons.IMAGE_OUTLINED, color=ft.Colors.GREY_500, size=14),
                        ft.Text("Estado de imágenes", size=11, color=ft.Colors.GREY_500)], spacing=4),
                lbl_imagen_status_sidebar,
            ],
            spacing=8,
            expand=True,
        ),
    )

    # 13. Estado inicial
    if state.ruta_base[0]:
        txt_proximo.value = f"Próximo Proyecto: video {obtener_siguiente_num(state.ruta_base[0])}"

    actualizar_ext_status_header(
        bool(ws_bridge.extension_bridge_state.get("connected")),
        ws_bridge.extension_bridge_state.get("version") or "",
    )
    reset_tracker()
    actualizar_resumen_alcance()

    page.add(
        header_bar,
        ft.Row(
            [
                col_izquierda,
                ft.Container(width=1, bgcolor=ft.Colors.GREY_200,
                             margin=ft.margin.symmetric(vertical=16)),
                col_central,
                ft.Container(width=1, bgcolor=ft.Colors.GREY_200,
                             margin=ft.margin.symmetric(vertical=16)),
                col_derecha,
            ],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
    )
    refrescar_canales()
```

**Verificación:**
```bash
python clusiv-auto.py
```

**Criterio de éxito:** La app abre, se ve igual que antes, todos los paneles funcionan.

---

## PASO 13 — Verificación funcional completa

Ejecutar este checklist con la app corriendo:

- [ ] La app abre sin errores en consola/terminal
- [ ] Los 6 paneles del lado izquierdo se expanden y colapsan
- [ ] Seleccionar ruta de proyectos → `txt_proximo` se actualiza
- [ ] Agregar canal → aparece en la lista
- [ ] Eliminar canal → desaparece de la lista
- [ ] Abrir editor de prompt → el diálogo modal aparece correctamente
- [ ] Guardar cambios en prompt → la tarjeta en la galería se actualiza
- [ ] Mover prompt arriba/abajo → el orden cambia
- [ ] Switch de prompt → habilita/deshabilita y cambia el color de la tarjeta
- [ ] Dropdown alcance → cambia el texto del botón ejecutar
- [ ] Campos TTS → se guardan al perder foco
- [ ] Campos WhisperX → se guardan al cambiar
- [ ] Campos AI Studio → se guardan al perder foco
- [ ] Selector imágenes de referencia → abre el file picker
- [ ] Botón recargar Journeys → no lanza excepción
- [ ] Botón EJECUTAR FLUJO → el tracker muestra fases y los logs aparecen en la consola
- [ ] Botón DETENER FLUJO → detiene la ejecución correctamente
- [ ] Estado extensión Chrome en el header → se actualiza al conectar/desconectar

**Criterio de éxito:** Todos los ítems marcados sin diferencias de comportamiento respecto al original.

---

## Dependencias cruzadas a resolver

Durante la implementación pueden surgir estas dependencias entre módulos:

### 1. `dropdown_ref_mode` en `panel_flow.py` → necesario en `ejecutar_flujo_completo`

`ejecutar_flujo_completo` en `ui_main.py` necesita leer `dropdown_ref_mode.value`.
Este widget vive ahora en `panel_flow.py`.

**Solución:** `build_panel_flow()` retorna también una función `get_ref_mode() -> str`.
```python
# En build_panel_flow:
def get_ref_mode():
    return dropdown_ref_mode.value or "ingredients"
# Se retorna junto con los demás valores
```

### 2. `actualizar_resumen_alcance` necesita actualizar `btn_ejecutar_widget.text`

`actualizar_resumen_alcance` vive en `panel_prompts.py` pero necesita modificar
el texto del botón ejecutar que vive en `ui_main.py`.

**Solución:** `build_panel_prompts()` recibe un callback `on_alcance_cambiado(texto_boton, descripcion)`.
`ui_main.py` pasa ese callback en el momento de construir el panel.

### 3. `show_snack` se usa en múltiples paneles

Cada panel que necesite mostrar snackbars recibe `page` como parámetro y
define su propio `show_snack` local, o recibe un callable `show_snack` desde `ui_main.py`.

**Solución recomendada:** Cada `build_panel_*` recibe `page` y define su propio
`show_snack` internamente — es una función de 3 líneas, no vale la pena centralizar.

### 4. `image_status_refs` — lista de labels a actualizar

En el original hay dos labels de estado de imágenes: `lbl_imagen_status` (dentro del
panel flow) y `lbl_imagen_status_sidebar` (en `col_derecha`).
`actualizar_estado_imagen` los actualiza a ambos.

**Solución:** `build_panel_flow()` retorna `lbl_imagen_status_sidebar` como widget separado
(ya está incluido en la firma del paso 11). `actualizar_estado_imagen` maneja ambos
internamente usando la lista `image_status_refs` igual que en el original.
`ui_main.py` monta `lbl_imagen_status_sidebar` en `col_derecha`.

---

## Notas finales para el agente

- **Si un import falla**, revisar que el archivo `ui/__init__.py` existe y está vacío.
- **Si hay `NameError` de variable no encontrada**, verificar que `state.nombre_variable`
  se está pasando correctamente al `build_panel_*` correspondiente.
- **No eliminar `ui_main.py` original** hasta que el paso 13 esté 100% verificado.
  Mantenerlo como `ui_main_original.py` durante la migración.
- **El orden de los pasos 3–11 es flexible** — cada módulo puede crearse y verificarse
  de forma independiente. El paso 12 requiere que todos los anteriores estén completos.
