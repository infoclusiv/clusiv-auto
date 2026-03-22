# Plan D — Migración Final (PyQt6)

> **Alcance exacto:** 3 archivos.
> - REEMPLAZAR: `ui/panel_flow.py`
> - REEMPLAZAR: `ui_main.py`
> - REEMPLAZAR: `clusiv-auto.py`
>
> **Al terminar este plan:** la app corre completamente en PyQt6.
> Flet ya no se importa en ningún archivo de `ui/`.
>
> **Prerrequisito:** Planes A, B y C completados y verificados.
>
> **NO tocar:** `ui/state.py`, `ui/compat.py`, `ui/consola.py`, `ui/tracker.py`,
> `ui/header.py`, `ui/panel_proyecto.py`, `ui/panel_prompts.py`,
> `ui/panel_tts.py`, `ui/panel_whisperx.py`, `ui/panel_ai_studio.py`,
> ni ningún archivo fuera de `ui/` excepto `ui_main.py` y `clusiv-auto.py`.

---

## Contrato que debe mantener `panel_flow.py`

`ui_main.py` (actual) llama:
```python
(
    expansion_flow,
    ref_images_picker,
    actualizar_estado_imagen,
    refrescar_journeys_ui,
    lbl_imagen_status_sidebar,
    get_ref_mode,
) = build_panel_flow(page, state, log_msg)
page.services.append(ref_images_picker)
```

El nuevo módulo retorna:
- `widget` — `QGroupBox` (reemplaza `expansion_flow`)
- `None` — reemplaza `ref_images_picker` (QFileDialog es llamada directa)
- `actualizar_estado_imagen` — callable `(texto, color=None)`
- `refrescar_journeys_ui` — callable `()` sin argumentos
- `lbl_imagen_status_sidebar` — `QLabel` para montar en `col_derecha`
- `get_ref_mode` — callable `() → str`

Y acepta `(_page=None, state=None, log_msg=None)`.

---

## Paso D-1 — REEMPLAZAR `ui/panel_flow.py`

```python
# ui/panel_flow.py
import os

from PyQt6.QtCore import QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

import ws_bridge
from config import (
    AI_STUDIO_OUTPUT_FILENAME_DEFAULT,
    guardar_config,
    normalizar_ai_studio_config,
)
from ws_bridge import (
    reset_pending_journey_chain,
    send_image_prompts_to_extension,
    send_ws_msg,
    set_pending_journey_chain,
)
from youtube_analyzer import obtener_ultimo_video


# ---------------------------------------------------------------------------
# Worker para envío de prompts de imagen (no bloquea la UI)
# ---------------------------------------------------------------------------

class _EnvioPromptsWorker(QThread):
    resultado = pyqtSignal(bool, str)   # ok, mensaje
    estado    = pyqtSignal(str, str)    # texto, color_key

    def __init__(self, ruta_txt, modelo, aspect_ratio, count,
                 ref_paths, ref_mode, project_folder):
        super().__init__()
        self._ruta_txt      = ruta_txt
        self._modelo        = modelo
        self._aspect_ratio  = aspect_ratio
        self._count         = count
        self._ref_paths     = ref_paths
        self._ref_mode      = ref_mode
        self._project_folder = project_folder

    def run(self):
        self.estado.emit("Enviando...", "blue800")
        ok, msg, _ = send_image_prompts_to_extension(
            self._ruta_txt,
            modelo=self._modelo,
            aspect_ratio=self._aspect_ratio,
            count=self._count,
            reference_image_paths=self._ref_paths or None,
            reference_mode=self._ref_mode,
            project_folder=self._project_folder,
        )
        if ok:
            self.estado.emit(
                "Prompts enviados. Esperando que Flow genere y descargue imágenes...",
                "teal700",
            )
        else:
            self.estado.emit(msg, "red700")
        self.resultado.emit(ok, msg)


# ---------------------------------------------------------------------------
# Función principal del módulo
# ---------------------------------------------------------------------------

def build_panel_flow(_page=None, state=None, log_msg=None):
    """
    Panel de Generación de Imágenes - Google Flow.
    Incluye configuración de imágenes, referencias y automatización por Journey.

    Parámetros
    ----------
    _page   : ignorado (compatibilidad con firma Flet)
    state   : AppState
    log_msg : callable para escribir en la consola

    Retorna
    -------
    (widget, None, actualizar_estado_imagen, refrescar_journeys_ui,
     lbl_imagen_status_sidebar, get_ref_mode)
    """
    ai_studio_config    = state.ai_studio_config
    config_actual       = state.config_actual
    ref_image_paths_state = state.ref_image_paths_state
    ruta_base           = state.ruta_base

    _worker_ref = [None]   # evita garbage-collection del QThread activo

    # -----------------------------------------------------------------------
    # Colores rápidos para actualizar_estado_imagen
    # -----------------------------------------------------------------------
    _STATUS_COLORS = {
        "blue700":  "#2B6CB0",
        "blue800":  "#2C5282",
        "teal700":  "#2C7A7B",
        "red700":   "#C53030",
        "green700": "#276749",
        "grey500":  "#A0AEC0",
    }

    # -----------------------------------------------------------------------
    # Widget raíz
    # -----------------------------------------------------------------------
    group = QGroupBox("🖼️ Generación de Imágenes - Google Flow")
    group.setCheckable(True)
    group.setChecked(False)
    group.setStyleSheet(
        "QGroupBox { font-weight: bold; font-size: 13px; margin-top: 6px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
    )

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.Shape.NoFrame)
    scroll_area.setMaximumHeight(600)

    inner = QWidget()
    outer = QVBoxLayout(inner)
    outer.setContentsMargins(8, 8, 8, 8)
    outer.setSpacing(10)
    scroll_area.setWidget(inner)

    group_layout = QVBoxLayout(group)
    group_layout.setContentsMargins(0, 8, 0, 0)
    group_layout.addWidget(scroll_area)

    def _sep():
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet("color: #E2E8F0;")
        return s

    def _lbl_section(texto):
        l = QLabel(texto)
        l.setStyleSheet("font-size: 12px; font-weight: bold; color: #4A5568;")
        return l

    def _combo_style():
        return (
            "QComboBox { border: 1px solid #CBD5E0; border-radius: 4px;"
            " padding: 4px 8px; font-size: 12px; }"
        )

    def _btn_style(bg, hover, text_color="white"):
        return (
            f"QPushButton {{ background: {bg}; color: {text_color}; border-radius: 6px;"
            f" padding: 6px 12px; font-size: 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {hover}; }}"
            f"QPushButton:disabled {{ background: #A0AEC0; }}"
        )

    # -----------------------------------------------------------------------
    # Sección A — Configuración de generación
    # -----------------------------------------------------------------------
    outer.addWidget(_lbl_section("Configuración de generación"))

    chk_auto_send = QCheckBox("🔄 Enviar automáticamente al finalizar AI Studio")
    chk_auto_send.setChecked(bool(ai_studio_config.get("auto_send_to_extension", False)))
    chk_auto_send.setStyleSheet("font-size: 12px;")
    outer.addWidget(chk_auto_send)

    row_model_count = QWidget()
    hbox_mc = QHBoxLayout(row_model_count)
    hbox_mc.setContentsMargins(0, 0, 0, 0)
    hbox_mc.setSpacing(6)

    combo_model = QComboBox()
    combo_model.setStyleSheet(_combo_style())
    combo_model.addItem("Imagen 4",  "imagen4")
    combo_model.addItem("NB 2",      "nano_banana2")
    combo_model.addItem("NB Pro",    "nano_banana_pro")
    _set_combo_by_data(combo_model, ai_studio_config.get("imagen_model", "imagen4"))
    hbox_mc.addWidget(combo_model, stretch=1)

    combo_count = QComboBox()
    combo_count.setStyleSheet(_combo_style())
    for v, t in [("1","1x"),("2","2x"),("3","3x"),("4","4x")]:
        combo_count.addItem(t, v)
    _set_combo_by_data(combo_count, str(ai_studio_config.get("imagen_count", 1)))
    hbox_mc.addWidget(combo_count, stretch=1)
    outer.addWidget(row_model_count)

    combo_aspect = QComboBox()
    combo_aspect.setStyleSheet(_combo_style())
    combo_aspect.addItem("16:9 Landscape", "landscape")
    combo_aspect.addItem("9:16 Portrait",  "portrait")
    _set_combo_by_data(combo_aspect, ai_studio_config.get("imagen_aspect_ratio", "landscape"))
    outer.addWidget(combo_aspect)

    def persistir_imagen_config():
        ai_studio_config["auto_send_to_extension"] = chk_auto_send.isChecked()
        ai_studio_config["imagen_model"]       = combo_model.currentData() or "imagen4"
        ai_studio_config["imagen_aspect_ratio"] = combo_aspect.currentData() or "landscape"
        ai_studio_config["imagen_count"]       = combo_count.currentData() or "1"

        normalizado = normalizar_ai_studio_config(ai_studio_config)
        ai_studio_config.update(normalizado)
        config_actual["ai_studio"]        = dict(ai_studio_config)
        config_actual["prompt_ai_studio"] = ai_studio_config["prompt"]
        guardar_config(ai_studio=ai_studio_config)

    chk_auto_send.stateChanged.connect(lambda _: persistir_imagen_config())
    combo_model.currentIndexChanged.connect(lambda _: persistir_imagen_config())
    combo_aspect.currentIndexChanged.connect(lambda _: persistir_imagen_config())
    combo_count.currentIndexChanged.connect(lambda _: persistir_imagen_config())

    # -----------------------------------------------------------------------
    # Sección B — Imágenes de referencia
    # -----------------------------------------------------------------------
    outer.addWidget(_sep())
    outer.addWidget(_lbl_section("🔍 Imágenes de referencia (opcional)"))

    combo_ref_mode = QComboBox()
    combo_ref_mode.setStyleSheet(_combo_style())
    combo_ref_mode.addItem("Ingredients (mezcla libre)", "ingredients")
    combo_ref_mode.addItem("Frames (secuencia ordenada)", "frames")
    outer.addWidget(combo_ref_mode)

    lbl_ref_images = QLabel("Sin imágenes de referencia")
    lbl_ref_images.setStyleSheet("font-size: 11px; color: #A0AEC0; font-style: italic;")
    lbl_ref_images.setWordWrap(True)

    def _actualizar_label_ref_images():
        count = len(ref_image_paths_state)
        if count == 0:
            lbl_ref_images.setText("Sin imágenes de referencia")
            lbl_ref_images.setStyleSheet("font-size: 11px; color: #A0AEC0; font-style: italic;")
        else:
            nombres = ", ".join(os.path.basename(p) for p in ref_image_paths_state)
            lbl_ref_images.setText(f"{count} imagen(es): {nombres}")
            lbl_ref_images.setStyleSheet("font-size: 11px; color: #2C7A7B; font-style: italic;")

    row_ref_btns = QWidget()
    hbox_ref = QHBoxLayout(row_ref_btns)
    hbox_ref.setContentsMargins(0, 0, 0, 0)
    hbox_ref.setSpacing(6)

    btn_sel_imgs = QPushButton("📷  Seleccionar imágenes")
    btn_sel_imgs.setStyleSheet(_btn_style("#E6FFFA", "#B2F5EA", "#285E61"))

    btn_limpiar_imgs = QPushButton("✕")
    btn_limpiar_imgs.setFixedWidth(32)
    btn_limpiar_imgs.setToolTip("Limpiar selección")
    btn_limpiar_imgs.setStyleSheet(_btn_style("#FED7D7", "#FEB2B2", "#C53030"))

    def _seleccionar_ref_images():
        archivos, _ = QFileDialog.getOpenFileNames(
            group,
            "Seleccionar imágenes de referencia",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp)",
        )
        for f in archivos:
            if f not in ref_image_paths_state:
                ref_image_paths_state.append(f)
        _actualizar_label_ref_images()

    def _limpiar_ref_images():
        ref_image_paths_state.clear()
        _actualizar_label_ref_images()

    btn_sel_imgs.clicked.connect(_seleccionar_ref_images)
    btn_limpiar_imgs.clicked.connect(_limpiar_ref_images)
    hbox_ref.addWidget(btn_sel_imgs, stretch=1)
    hbox_ref.addWidget(btn_limpiar_imgs)
    outer.addWidget(row_ref_btns)
    outer.addWidget(lbl_ref_images)

    # -----------------------------------------------------------------------
    # Sección C — Envío manual de prompts
    # -----------------------------------------------------------------------
    outer.addWidget(_sep())

    # Label de estado — se usa también como lbl_imagen_status_sidebar
    lbl_status = QLabel("Estado: esperando...")
    lbl_status.setStyleSheet("font-size: 11px; color: #A0AEC0; font-style: italic;")
    lbl_status.setWordWrap(True)
    outer.addWidget(lbl_status)

    # Label sidebar (referencia independiente al mismo texto)
    lbl_imagen_status_sidebar = QLabel("Estado: esperando...")
    lbl_imagen_status_sidebar.setStyleSheet(
        "font-size: 11px; color: #A0AEC0; font-style: italic;"
    )

    # Actualizar ambos labels — llamable desde cualquier hilo via QTimer
    def actualizar_estado_imagen(texto, color=None):
        color_hex = _STATUS_COLORS.get(str(color).lower().replace("_","").replace(".",""),
                                        "#A0AEC0")
        def _apply():
            css = f"font-size: 11px; color: {color_hex}; font-style: italic;"
            lbl_status.setText(texto)
            lbl_status.setStyleSheet(css)
            lbl_imagen_status_sidebar.setText(texto)
            lbl_imagen_status_sidebar.setStyleSheet(css)
        QTimer.singleShot(0, _apply)

    row_envio = QWidget()
    hbox_envio = QHBoxLayout(row_envio)
    hbox_envio.setContentsMargins(0, 0, 0, 0)
    hbox_envio.setSpacing(6)

    btn_enviar = QPushButton("📤  Enviar Prompts")
    btn_enviar.setStyleSheet(_btn_style("#2C7A7B", "#285E61"))

    btn_cola = QPushButton("ℹ")
    btn_cola.setFixedWidth(32)
    btn_cola.setToolTip("Ver estado de la cola")
    btn_cola.setStyleSheet(_btn_style("#E6FFFA", "#B2F5EA", "#285E61"))

    def _enviar_prompts():
        persistir_imagen_config()
        ultimo_video = obtener_ultimo_video(ruta_base[0])
        if not ultimo_video:
            if log_msg:
                log_msg("❌ No hay proyectos generados todavía.", color="red700")
            return

        ruta_txt = os.path.join(
            ultimo_video,
            ai_studio_config.get("archivo_salida", AI_STUDIO_OUTPUT_FILENAME_DEFAULT),
        )

        btn_enviar.setEnabled(False)

        worker = _EnvioPromptsWorker(
            ruta_txt=ruta_txt,
            modelo=ai_studio_config.get("imagen_model", "imagen4"),
            aspect_ratio=ai_studio_config.get("imagen_aspect_ratio", "landscape"),
            count=ai_studio_config.get("imagen_count", 1),
            ref_paths=list(ref_image_paths_state) if ref_image_paths_state else [],
            ref_mode=combo_ref_mode.currentData() or "ingredients",
            project_folder=ultimo_video,
        )
        _worker_ref[0] = worker

        worker.estado.connect(lambda txt, col: actualizar_estado_imagen(txt, col))
        worker.resultado.connect(
            lambda ok, msg: (
                log_msg(
                    f"{'✅' if ok else '❌'} Imágenes: {msg}",
                    color="green700" if ok else "red700",
                ) if log_msg else None,
                btn_enviar.setEnabled(True),
                _worker_ref.__setitem__(0, None),
            )
        )
        worker.start()

    def _solicitar_estado_cola():
        if not send_ws_msg({"action": "GET_QUEUE_STATUS"}):
            if log_msg:
                log_msg("❌ La extensión no está conectada.", color="red700")
        else:
            actualizar_estado_imagen("Solicitando estado de la cola...", "blue700")

    btn_enviar.clicked.connect(_enviar_prompts)
    btn_cola.clicked.connect(_solicitar_estado_cola)
    hbox_envio.addWidget(btn_enviar, stretch=1)
    hbox_envio.addWidget(btn_cola)
    outer.addWidget(row_envio)

    # -----------------------------------------------------------------------
    # Sección D — Automatización por Journey
    # -----------------------------------------------------------------------
    outer.addWidget(_sep())
    outer.addWidget(_lbl_section("🌐 Automatización por Journey (Chrome)"))

    row_journey_sel = QWidget()
    hbox_js = QHBoxLayout(row_journey_sel)
    hbox_js.setContentsMargins(0, 0, 0, 0)
    hbox_js.setSpacing(4)

    combo_journeys = QComboBox()
    combo_journeys.setStyleSheet(_combo_style())
    combo_journeys.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    hbox_js.addWidget(combo_journeys, stretch=1)

    btn_reload_journeys = QPushButton("🔄")
    btn_reload_journeys.setFixedWidth(32)
    btn_reload_journeys.setToolTip("Recargar lista de Journeys")
    btn_reload_journeys.setStyleSheet(_btn_style("#EBF8FF", "#BEE3F8", "#2B6CB0"))
    hbox_js.addWidget(btn_reload_journeys)
    outer.addWidget(row_journey_sel)

    chk_segundo_journey = QCheckBox("🔁 Ejecutar segunda automatización luego del pegado")
    chk_segundo_journey.setChecked(False)
    chk_segundo_journey.setStyleSheet("font-size: 12px;")
    outer.addWidget(chk_segundo_journey)

    combo_second_journey = QComboBox()
    combo_second_journey.setStyleSheet(_combo_style())
    combo_second_journey.setEnabled(False)
    outer.addWidget(combo_second_journey)

    chk_pegar_script = QCheckBox("📝 Pegar script.txt al finalizar Journey")
    chk_pegar_script.setChecked(True)
    chk_pegar_script.setStyleSheet("font-size: 12px;")
    outer.addWidget(chk_pegar_script)

    def _on_segundo_journey_changed():
        combo_second_journey.setEnabled(chk_segundo_journey.isChecked())
        if not chk_segundo_journey.isChecked():
            combo_second_journey.setCurrentIndex(-1)

    chk_segundo_journey.stateChanged.connect(lambda _: _on_segundo_journey_changed())

    def refrescar_journeys_ui():
        """Llamado por ws_bridge cuando llega la lista de journeys."""
        def _apply():
            prev_primary   = combo_journeys.currentData()
            prev_secondary = combo_second_journey.currentData()
            valid_ids = {j["id"] for j in ws_bridge.available_journeys}

            combo_journeys.blockSignals(True)
            combo_second_journey.blockSignals(True)
            combo_journeys.clear()
            combo_second_journey.clear()

            for j in ws_bridge.available_journeys:
                combo_journeys.addItem(j["name"], j["id"])
                combo_second_journey.addItem(j["name"], j["id"])

            if prev_primary in valid_ids:
                _set_combo_by_data(combo_journeys, prev_primary)
            elif ws_bridge.available_journeys:
                combo_journeys.setCurrentIndex(0)

            if prev_secondary in valid_ids:
                _set_combo_by_data(combo_second_journey, prev_secondary)

            combo_journeys.blockSignals(False)
            combo_second_journey.blockSignals(False)

        QTimer.singleShot(0, _apply)

    def _solicitar_journeys():
        if not send_ws_msg({"action": "GET_JOURNEYS"}):
            if log_msg:
                log_msg("❌ La extensión de Chrome no está conectada", color="red700")

    btn_reload_journeys.clicked.connect(_solicitar_journeys)

    def _obtener_texto_script():
        ultimo_video = obtener_ultimo_video(ruta_base[0])
        if not ultimo_video:
            return None, "No hay proyectos generados aún en la carpeta"
        script_path = os.path.join(ultimo_video, "script.txt")
        if not os.path.exists(script_path):
            return None, "No se encontró script.txt en el último proyecto."
        with open(script_path, "r", encoding="utf-8") as f:
            return f.read(), None

    row_journey_btns = QWidget()
    hbox_jb = QHBoxLayout(row_journey_btns)
    hbox_jb.setContentsMargins(0, 0, 0, 0)
    hbox_jb.setSpacing(6)

    btn_ejecutar_journey = QPushButton("▶  Ejecutar Journey")
    btn_ejecutar_journey.setStyleSheet(_btn_style("#2C5282", "#2A4365"))

    btn_pegar_ahora = QPushButton("📋")
    btn_pegar_ahora.setFixedWidth(32)
    btn_pegar_ahora.setToolTip("Pegar script.txt ahora (Paso Manual)")
    btn_pegar_ahora.setStyleSheet(_btn_style("#EBF8FF", "#BEE3F8", "#2B6CB0"))

    def _ordenar_ejecucion_journey():
        journey_id = combo_journeys.currentData()
        if not journey_id:
            if log_msg:
                log_msg("⚠ Selecciona un Journey primero", color="orange700")
            return

        usar_segundo = chk_segundo_journey.isChecked()
        pegar_script = chk_pegar_script.isChecked()

        if usar_segundo:
            if not pegar_script:
                if log_msg:
                    log_msg(
                        "⚠ Activa el pegado de script.txt para encadenar la segunda automatización",
                        color="orange700",
                    )
                return
            second_id = combo_second_journey.currentData()
            if not second_id:
                if log_msg:
                    log_msg("⚠ Selecciona la segunda automatización", color="orange700")
                return
            if second_id == journey_id:
                if log_msg:
                    log_msg("⚠ El segundo journey debe ser distinto del principal", color="orange700")
                return

        payload = {"action": "RUN_JOURNEY", "journey_id": journey_id}

        if pegar_script:
            script_text, error_msg = _obtener_texto_script()
            if error_msg:
                if log_msg:
                    log_msg(f"❌ {error_msg}", color="red700")
                return
            payload["paste_text_at_end"] = script_text

        if usar_segundo:
            set_pending_journey_chain(journey_id, combo_second_journey.currentData())
        else:
            reset_pending_journey_chain()

        if not send_ws_msg(payload):
            reset_pending_journey_chain()
            if log_msg:
                log_msg("❌ La extensión de Chrome no está conectada", color="red700")
        else:
            if log_msg:
                log_msg("✅ Orden de ejecución enviada", color="green700")
            if usar_segundo and log_msg:
                log_msg(
                    "⏳ Esperando señal de pegado completado para disparar la segunda automatización...",
                    color="blue800",
                )

    def _pegar_script_ahora():
        text, error_msg = _obtener_texto_script()
        if error_msg:
            if log_msg:
                log_msg(f"❌ {error_msg}", color="red700")
            return
        if send_ws_msg({"action": "PASTE_TEXT_NOW", "text": text}):
            if log_msg:
                log_msg("✅ Texto enviado a la extensión", color="green700")
        else:
            if log_msg:
                log_msg("❌ La extensión no está conectada", color="red700")

    btn_ejecutar_journey.clicked.connect(_ordenar_ejecucion_journey)
    btn_pegar_ahora.clicked.connect(_pegar_script_ahora)
    hbox_jb.addWidget(btn_ejecutar_journey, stretch=1)
    hbox_jb.addWidget(btn_pegar_ahora)
    outer.addWidget(row_journey_btns)

    # -----------------------------------------------------------------------
    # Inicialización
    # -----------------------------------------------------------------------
    _actualizar_label_ref_images()

    def get_ref_mode():
        return combo_ref_mode.currentData() or "ingredients"

    return (
        group,
        None,                       # reemplaza ref_images_picker
        actualizar_estado_imagen,
        refrescar_journeys_ui,
        lbl_imagen_status_sidebar,
        get_ref_mode,
    )


# ---------------------------------------------------------------------------
# Helper interno
# ---------------------------------------------------------------------------

def _set_combo_by_data(combo, data_value):
    """Selecciona el item del QComboBox cuyo data() coincida con data_value."""
    idx = combo.findData(data_value)
    if idx >= 0:
        combo.setCurrentIndex(idx)
```

**Verificación:**

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.state import AppState
from ui.panel_flow import build_panel_flow
state = AppState()
def fake_log(txt, **kw): print('LOG:', txt)
w, _, act_img, ref_journeys, lbl_sidebar, get_ref = build_panel_flow(None, state, fake_log)
w.setChecked(True)
w.resize(440, 600)
w.show()
print('panel_flow OK')
print('get_ref_mode:', get_ref())
app.exec()
"
```

**Criterio de éxito:** Imprime `panel_flow OK` y `get_ref_mode: ingredients`.
El panel muestra todas las secciones: configuración, referencias, envío y journeys.

---

## Paso D-2 — REEMPLAZAR `ui_main.py`

Este archivo deja de importar Flet completamente.
Ensambla todos los módulos PyQt6 en una `QMainWindow`.

```python
# ui_main.py
"""ui_main.py - Interfaz principal de Clusiv Automation (PyQt6)."""

import sys

from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import QThread, Qt, pyqtSignal

import ws_bridge
from config import YOUTUBE_API_KEY
from flow_orchestrator import FlowContext, ejecutar_flujo
from youtube_analyzer import obtener_siguiente_num

from ui.compat import DropdownCompat, PageCompat, ProgressBarCompat, TextCompat
from ui.consola import build_consola
from ui.header import build_header
from ui.panel_ai_studio import build_panel_ai_studio
from ui.panel_flow import build_panel_flow
from ui.panel_proyecto import build_panel_proyecto
from ui.panel_prompts import build_panel_prompts
from ui.panel_tts import build_panel_tts
from ui.panel_whisperx import build_panel_whisperx
from ui.state import AppState
from ui.tracker import construir_tracker_fases


# ---------------------------------------------------------------------------
# Worker para ejecutar el flujo sin bloquear la UI
# ---------------------------------------------------------------------------

class _FlowWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx

    def run(self):
        try:
            ejecutar_flujo(self._ctx)
        finally:
            self.finished.emit()


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clusiv Automation Hub")
        self.setMinimumSize(1200, 700)
        self._flow_worker = None

        self.state = AppState()
        self._build_ui()
        self._connect_ws_bridge()
        self._init_estado_inicial()

    # ------------------------------------------------------------------
    # Construcción de la UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        # --- Módulos base ---
        self.log_widget, self.log_msg, self.limpiar_log = build_consola()
        self.tracker_widget, self.set_fase_estado, self.reset_tracker = (
            construir_tracker_fases()
        )
        self.header_widget, self.actualizar_ext_status = build_header()

        # --- Adaptadores para FlowContext (sin Flet) ---
        self.page_compat = PageCompat()
        self.prg_compat  = ProgressBarCompat(
            on_visible_change=self._on_prg_visible
        )
        self.txt_proximo_compat = TextCompat(
            on_value_change=self._on_txt_proximo_change
        )
        self.dropdown_ref_compat = DropdownCompat(default_value="ingredients")

        # --- Paneles de configuración ---
        self.panel_proyecto, _, self.refrescar_canales, _ = build_panel_proyecto(
            None, self.state,
            on_ruta_cambiada=self._actualizar_txt_proximo,
        )
        (
            self.panel_prompts,
            self.obtener_prompts_para_ejecucion,
            self.actualizar_resumen_alcance,
        ) = build_panel_prompts(
            None, self.state,
            on_alcance_cambiado=self._sync_boton_ejecutar,
        )
        self.panel_tts,       _ = build_panel_tts(None, self.state, self.log_msg)
        self.panel_whisperx,  _ = build_panel_whisperx(None, self.state)
        self.panel_ai_studio, _ = build_panel_ai_studio(None, self.state)
        (
            self.panel_flow,
            _,                              # None — picker ya no existe
            self.actualizar_estado_imagen,
            self.refrescar_journeys_ui,
            self.lbl_imagen_status_sidebar,
            self._get_ref_mode,
        ) = build_panel_flow(None, self.state, self.log_msg)

        # Enlazar DropdownCompat con el combo real de panel_flow
        # get_ref_mode() ya lee el combo directamente — DropdownCompat
        # se usa como proxy para FlowContext
        self.dropdown_ref_compat._get_ref_mode_fn = self._get_ref_mode

        # --- Widgets del panel central ---
        self.prg_bar = QProgressBar()
        self.prg_bar.setRange(0, 0)        # indeterminado
        self.prg_bar.setVisible(False)
        self.prg_bar.setFixedHeight(6)
        self.prg_bar.setStyleSheet(
            "QProgressBar { border:none; background:#E2E8F0; border-radius:3px; }"
            "QProgressBar::chunk { background:#276749; border-radius:3px; }"
        )

        self.lbl_proximo = QLabel("")
        self.lbl_proximo.setStyleSheet(
            "font-weight: bold; font-size: 14px; color: #4A5568;"
        )

        self.lbl_alcance = QLabel("")
        self.lbl_alcance.setStyleSheet(
            "font-size: 12px; color: #718096; font-style: italic;"
        )
        self.lbl_alcance.setWordWrap(True)

        self.btn_ejecutar = QPushButton("EJECUTAR FLUJO COMPLETO")
        self.btn_ejecutar.setFixedHeight(50)
        self.btn_ejecutar.setStyleSheet(self._style_btn_ejecutar(ejecutando=False))
        self.btn_ejecutar.clicked.connect(self._ejecutar_flujo_completo)

        self.btn_detener = QPushButton("DETENER FLUJO")
        self.btn_detener.setFixedHeight(50)
        self.btn_detener.setVisible(False)
        self.btn_detener.setStyleSheet(
            "QPushButton { background:#C53030; color:white; font-weight:bold;"
            " font-size:13px; border-radius:6px; }"
            "QPushButton:disabled { background:#A0AEC0; }"
        )
        self.btn_detener.clicked.connect(self._detener_flujo)

        self._ensamblar_layout()

    def _ensamblar_layout(self):
        # Columna izquierda (scrollable)
        col_izq_inner = QWidget()
        vbox_izq = QVBoxLayout(col_izq_inner)
        vbox_izq.setContentsMargins(8, 8, 4, 8)
        vbox_izq.setSpacing(4)

        lbl_config = QLabel("Configuración del Pipeline")
        lbl_config.setStyleSheet(
            "color:#A0AEC0; font-size:11px; font-style:italic; font-weight:bold;"
        )
        vbox_izq.addWidget(lbl_config)
        for panel in [
            self.panel_proyecto, self.panel_prompts, self.panel_tts,
            self.panel_whisperx, self.panel_ai_studio, self.panel_flow,
        ]:
            vbox_izq.addWidget(panel)
        vbox_izq.addStretch()

        scroll_izq = QScrollArea()
        scroll_izq.setWidget(col_izq_inner)
        scroll_izq.setWidgetResizable(True)
        scroll_izq.setFixedWidth(440)
        scroll_izq.setFrameShape(QFrame.Shape.NoFrame)

        # Columna central
        col_central = QWidget()
        col_central.setFixedWidth(330)
        vbox_central = QVBoxLayout(col_central)
        vbox_central.setContentsMargins(8, 16, 8, 16)
        vbox_central.setSpacing(8)

        lbl_pipeline = QLabel("Pipeline de Ejecución")
        lbl_pipeline.setStyleSheet(
            "color:#A0AEC0; font-size:11px; font-style:italic; font-weight:bold;"
        )
        lbl_estado_flujo = QLabel("Estado del flujo")
        lbl_estado_flujo.setStyleSheet(
            "font-weight:bold; font-size:11px; color:#A0AEC0;"
        )

        def _sep():
            s = QFrame()
            s.setFrameShape(QFrame.Shape.HLine)
            s.setStyleSheet("color:#E2E8F0;")
            return s

        for w in [
            lbl_pipeline, _sep(),
            self.lbl_proximo, _sep(),
            self.btn_ejecutar, self.lbl_alcance,
            self.btn_detener, self.prg_bar, _sep(),
            lbl_estado_flujo, self.tracker_widget,
        ]:
            vbox_central.addWidget(w)
        vbox_central.addStretch()

        # Columna derecha (consola + estado imágenes)
        col_derecha = QWidget()
        vbox_derecha = QVBoxLayout(col_derecha)
        vbox_derecha.setContentsMargins(8, 16, 16, 16)
        vbox_derecha.setSpacing(6)

        hdr_consola = QWidget()
        hbox_hdr = QHBoxLayout(hdr_consola)
        hbox_hdr.setContentsMargins(0, 0, 0, 0)
        lbl_consola = QLabel("🖥  Consola de ejecución")
        lbl_consola.setStyleSheet("font-weight:bold; font-size:11px; color:#A0AEC0;")
        btn_limpiar = QPushButton("Limpiar")
        btn_limpiar.setFlat(True)
        btn_limpiar.setStyleSheet("color:#A0AEC0; font-size:11px;")
        btn_limpiar.clicked.connect(self.limpiar_log)
        hbox_hdr.addWidget(lbl_consola)
        hbox_hdr.addStretch()
        hbox_hdr.addWidget(btn_limpiar)

        sep_log = QFrame()
        sep_log.setFrameShape(QFrame.Shape.HLine)
        sep_log.setStyleSheet("color:#E2E8F0;")

        lbl_imgs = QLabel("🖼  Estado de imágenes")
        lbl_imgs.setStyleSheet("font-size:11px; color:#A0AEC0;")

        vbox_derecha.addWidget(hdr_consola)
        vbox_derecha.addWidget(self.log_widget, stretch=1)
        vbox_derecha.addWidget(sep_log)
        vbox_derecha.addWidget(lbl_imgs)
        vbox_derecha.addWidget(self.lbl_imagen_status_sidebar)

        # Separadores verticales
        def _sep_v():
            s = QFrame()
            s.setFrameShape(QFrame.Shape.VLine)
            s.setStyleSheet("color:#E2E8F0;")
            return s

        main_row = QWidget()
        hbox_main = QHBoxLayout(main_row)
        hbox_main.setContentsMargins(0, 0, 0, 0)
        hbox_main.setSpacing(0)
        hbox_main.addWidget(scroll_izq)
        hbox_main.addWidget(_sep_v())
        hbox_main.addWidget(col_central)
        hbox_main.addWidget(_sep_v())
        hbox_main.addWidget(col_derecha, stretch=1)

        central = QWidget()
        vbox_main = QVBoxLayout(central)
        vbox_main.setContentsMargins(0, 0, 0, 0)
        vbox_main.setSpacing(0)
        vbox_main.addWidget(self.header_widget)
        vbox_main.addWidget(main_row, stretch=1)
        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    # Conexión con ws_bridge
    # ------------------------------------------------------------------

    def _connect_ws_bridge(self):
        ws_bridge.ui_log_cb            = self.log_msg
        ws_bridge.ui_ext_status_cb     = self.actualizar_ext_status
        ws_bridge.ui_image_status_cb   = self.actualizar_estado_imagen
        ws_bridge.ui_update_journeys_cb = self.refrescar_journeys_ui

    # ------------------------------------------------------------------
    # Estado inicial
    # ------------------------------------------------------------------

    def _init_estado_inicial(self):
        if self.state.ruta_base[0]:
            self._actualizar_txt_proximo(self.state.ruta_base[0])
        self.actualizar_ext_status(
            bool(ws_bridge.extension_bridge_state.get("connected")),
            ws_bridge.extension_bridge_state.get("version") or "",
        )
        self.reset_tracker()
        self.actualizar_resumen_alcance()
        self.refrescar_journeys_ui()
        self.refrescar_canales()

    # ------------------------------------------------------------------
    # Callbacks internos
    # ------------------------------------------------------------------

    def _actualizar_txt_proximo(self, ruta):
        self.txt_proximo_compat.value = (
            f"Próximo Proyecto: video {obtener_siguiente_num(ruta)}"
        )

    def _on_txt_proximo_change(self, texto):
        self.lbl_proximo.setText(texto)

    def _on_prg_visible(self, visible):
        self.prg_bar.setVisible(visible)

    def _sync_boton_ejecutar(self, texto_boton, descripcion):
        self.btn_ejecutar.setText(texto_boton)
        self.lbl_alcance.setText(f"Alcance actual: {descripcion}")

    @staticmethod
    def _style_btn_ejecutar(ejecutando):
        if ejecutando:
            return (
                "QPushButton { background:#A0AEC0; color:white; font-weight:bold;"
                " font-size:13px; border-radius:6px; }"
            )
        return (
            "QPushButton { background:#276749; color:white; font-weight:bold;"
            " font-size:13px; border-radius:6px; }"
            "QPushButton:hover { background:#22543D; }"
        )

    def _set_estado_ejecutando(self, ejecutando):
        self.btn_ejecutar.setEnabled(not ejecutando)
        self.btn_ejecutar.setStyleSheet(self._style_btn_ejecutar(ejecutando))
        self.btn_detener.setVisible(ejecutando)
        self.btn_detener.setEnabled(True)
        self.btn_detener.setText("DETENER FLUJO")
        self.btn_detener.setStyleSheet(
            "QPushButton { background:#C53030; color:white; font-weight:bold;"
            " font-size:13px; border-radius:6px; }"
        )

    def _detener_flujo(self):
        self.state.stop_event.set()
        self.btn_detener.setEnabled(False)
        self.btn_detener.setText("DETENIENDO...")
        self.btn_detener.setStyleSheet(
            "QPushButton { background:#A0AEC0; color:white; border-radius:6px; }"
        )
        self.log_msg(
            "⛔ Solicitud de detención enviada. Esperando que el paso actual finalice...",
            color="orange800",
            weight="bold",
            italic=True,
        )

    def _ejecutar_flujo_completo(self):
        if not self.state.ruta_base[0]:
            self.statusBar().showMessage("Selecciona una ruta de proyectos", 4000)
            return
        if not YOUTUBE_API_KEY:
            self.statusBar().showMessage("Falta API KEY en .env", 4000)
            return

        prompts_a_ejecutar, _ = self.obtener_prompts_para_ejecucion()
        if not prompts_a_ejecutar:
            self.statusBar().showMessage("No hay prompts configurados", 4000)
            return

        self.limpiar_log()
        self.prg_compat.visible = True
        self._set_estado_ejecutando(True)
        self.reset_tracker()
        self.state.stop_event.clear()

        ctx = FlowContext(
            stop_event                  = self.state.stop_event,
            log_msg                     = self.log_msg,
            ruta_base                   = self.state.ruta_base,
            prompts_lista               = self.state.prompts_lista,
            tts_config                  = self.state.tts_config,
            whisperx_config             = self.state.whisperx_config,
            config_actual               = self.state.config_actual,
            ejecutar_hasta_prompt       = self.state.ejecutar_hasta_prompt,
            ref_image_paths_state       = self.state.ref_image_paths_state,
            dropdown_ref_mode           = self.dropdown_ref_compat,
            prg                         = self.prg_compat,
            txt_proximo                 = self.txt_proximo_compat,
            page                        = self.page_compat,
            set_estado_ejecutando       = self._set_estado_ejecutando,
            obtener_prompts_para_ejecucion = self.obtener_prompts_para_ejecucion,
            set_fase_estado             = self.set_fase_estado,
            reset_tracker               = self.reset_tracker,
        )

        self._flow_worker = _FlowWorker(ctx)
        self._flow_worker.finished.connect(self._on_flujo_terminado)
        self._flow_worker.start()

    def _on_flujo_terminado(self):
        self.prg_compat.visible = False
        self._set_estado_ejecutando(False)
        self._flow_worker = None


# ---------------------------------------------------------------------------
# Punto de entrada (usado por clusiv-auto.py)
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
```

---

## Paso D-3 — REEMPLAZAR `clusiv-auto.py`

```python
# clusiv-auto.py
"""clusiv-auto.py - Punto de entrada de Clusiv Automation."""

from ui_main import main

if __name__ == "__main__":
    main()
```

---

## Verificación del Paso D-1 (`panel_flow.py`)

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.state import AppState
from ui.panel_flow import build_panel_flow
state = AppState()
def fake_log(txt, **kw): print('LOG:', txt)
w, none_val, act_img, ref_j, lbl_sidebar, get_ref = build_panel_flow(None, state, fake_log)
assert none_val is None, 'Segundo retorno debe ser None'
w.setChecked(True)
w.resize(440, 580)
w.show()
print('panel_flow OK — get_ref_mode:', get_ref())
app.exec()
"
```

**Criterio de éxito:** Imprime `panel_flow OK` y `get_ref_mode: ingredients`.

---

## Verificación del Paso D-2 + D-3 (app completa)

```bash
python clusiv-auto.py
```

**Criterio de éxito — checklist completo:**

- [ ] La app abre sin errores en la terminal
- [ ] El header muestra "Clusiv Automation" y el estado de extensión (naranja)
- [ ] Los 6 paneles del lado izquierdo se expanden y colapsan con el checkbox del título
- [ ] Panel Proyecto: botón de ruta abre `QFileDialog`, `lbl_proximo` se actualiza
- [ ] Panel Proyecto: agregar canal → aparece en lista; eliminar → desaparece
- [ ] Panel Prompts: galería muestra una tarjeta por prompt
- [ ] Panel Prompts: clic en ✏️ → se abre el `QDialog` de edición
- [ ] Panel Prompts: guardar en el diálogo → tarjeta se actualiza
- [ ] Panel Prompts: ⬆️ ⬇️ reordenan las tarjetas
- [ ] Panel Prompts: combo de alcance cambia el texto del `btn_ejecutar`
- [ ] Panel TTS: campos guardan al perder foco
- [ ] Panel WhisperX: combo de modelo guarda al cambiar
- [ ] Panel AI Studio: prompt y espera guardan al perder foco o al hacer clic en guardar
- [ ] Panel Flow: botón "Seleccionar imágenes" abre `QFileDialog`
- [ ] Panel Flow: botón 🔄 Recargar Journeys no lanza excepción
- [ ] Botón `EJECUTAR FLUJO COMPLETO` → tracker muestra fases, logs aparecen en consola
- [ ] Botón `DETENER FLUJO` → para la ejecución, se deshabilita mientras detiene
- [ ] `lbl_imagen_status_sidebar` en la columna derecha se actualiza junto con el label interno del panel flow

---

## Verificación de integración completa (sin app)

```bash
python -c "
from ui.compat          import PageCompat, ProgressBarCompat, TextCompat, DropdownCompat
from ui.consola         import build_consola
from ui.tracker         import construir_tracker_fases
from ui.header          import build_header
from ui.panel_proyecto  import build_panel_proyecto
from ui.panel_tts       import build_panel_tts
from ui.panel_whisperx  import build_panel_whisperx
from ui.panel_ai_studio import build_panel_ai_studio
from ui.panel_prompts   import build_panel_prompts
from ui.panel_flow      import build_panel_flow
from ui.state           import AppState
from ui_main            import MainWindow
print('Todos los modulos importan OK — migracion a PyQt6 completa')
"
```

**Criterio de éxito:** Imprime el mensaje sin errores. Flet ya no aparece en ningún traceback.
