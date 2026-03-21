# Plan B — Paneles Simples (PyQt6)

> **Alcance exacto:** 4 archivos solamente.
> - REEMPLAZAR: `ui/panel_proyecto.py`
> - REEMPLAZAR: `ui/panel_tts.py`
> - REEMPLAZAR: `ui/panel_whisperx.py`
> - REEMPLAZAR: `ui/panel_ai_studio.py`
>
> **Al terminar este plan:** `ui_main.py` y `clusiv-auto.py` siguen sin cambios.
> La app Flet todavía no corre (ya que consola/tracker/header son PyQt6),
> pero todos estos módulos importan sin errores.
>
> **Prerrequisito:** Plan A completado y verificado.
>
> **NO tocar:** `ui/state.py`, `ui/compat.py`, `ui/consola.py`, `ui/tracker.py`,
> `ui/header.py`, `ui/panel_prompts.py`, `ui/panel_flow.py`,
> `ui_main.py`, `clusiv-auto.py`, ni ningún archivo fuera de `ui/`.

---

## Patrón común a todos los paneles

Cada panel Flet era un `ft.ExpansionTile` (sección colapsable).
En PyQt6 se reemplaza con un `QGroupBox` que tiene un botón de colapso
integrado mediante `setCheckable(True)`.

```python
group = QGroupBox("🔊 Título del panel")
group.setCheckable(True)   # permite colapsar/expandir con el checkbox del título
group.setChecked(False)    # empieza colapsado (igual que expanded=False en Flet)
```

Todos los paneles mantienen la misma firma de retorno que espera `ui_main.py`,
pero con `_page=None` en lugar de `page` para ignorar el argumento Flet
mientras `ui_main.py` no se actualice.

---

## Paso B-1 — REEMPLAZAR `ui/panel_proyecto.py`

**Contrato que debe mantener** (lo que `ui_main.py` espera):
```python
expansion_proyecto, picker, refrescar_canales, _ = build_panel_proyecto(
    page, state, on_ruta_cambiada=lambda ruta: ...
)
page.services.append(picker)
```

En PyQt6 el `picker` (ft.FilePicker) desaparece — `QFileDialog` es una llamada
directa. Para mantener compatibilidad con `ui_main.py` sin modificarlo,
retornar `None` en lugar del picker. `page.services.append(None)` no hace nada dañino en Flet,
y en el Plan D se limpiará.

**Retorno nuevo:**
```python
# panel_widget: QGroupBox
# None: reemplaza al picker (ya no se necesita)
# refrescar_canales: callable() sin argumentos
# None: cuarto valor ignorado por ui_main.py con _
return panel_widget, None, refrescar_canales, None
```

**Contenido completo:**

```python
# ui/panel_proyecto.py
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QLineEdit, QPushButton, QScrollArea,
    QFrame, QFileDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt

from config import guardar_config
from database import agregar_canal_db, eliminar_canal_db, obtener_canales_db


def build_panel_proyecto(_page=None, state=None, on_ruta_cambiada=None):
    """
    Panel de Proyecto & Canales YouTube.

    Retorna
    -------
    (widget: QGroupBox, None, refrescar_canales: callable, None)
    El segundo valor era ft.FilePicker — ya no aplica en PyQt6.
    """

    group = QGroupBox("📁 Proyecto & Canales YouTube")
    group.setCheckable(True)
    group.setChecked(True)   # empieza expandido (mismo comportamiento que Flet)
    group.setStyleSheet(
        "QGroupBox { font-weight: bold; font-size: 13px; margin-top: 6px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
    )

    outer = QVBoxLayout(group)
    outer.setContentsMargins(8, 12, 8, 8)
    outer.setSpacing(8)

    # --- Ruta de proyectos ---
    btn_ruta = QPushButton("📂  Ruta de Proyectos")
    btn_ruta.setStyleSheet(
        "QPushButton { background: #EBF8FF; color: #2B6CB0; border: 1px solid #90CDF4;"
        " border-radius: 6px; padding: 6px 12px; font-size: 12px; }"
        "QPushButton:hover { background: #BEE3F8; }"
    )

    def _on_elegir_ruta():
        ruta = QFileDialog.getExistingDirectory(group, "Seleccionar carpeta de proyectos")
        if ruta:
            state.ruta_base[0] = ruta
            guardar_config(ruta=ruta)
            if on_ruta_cambiada:
                on_ruta_cambiada(ruta)

    btn_ruta.clicked.connect(_on_elegir_ruta)
    outer.addWidget(btn_ruta)

    # --- Separador ---
    sep1 = QFrame()
    sep1.setFrameShape(QFrame.Shape.HLine)
    sep1.setStyleSheet("color: #E2E8F0;")
    outer.addWidget(sep1)

    # --- Agregar canal ---
    lbl_canales = QLabel("Canales de referencia")
    lbl_canales.setStyleSheet("font-size: 12px; font-weight: bold; color: #4A5568;")
    outer.addWidget(lbl_canales)

    row_inputs = QWidget()
    hbox_inputs = QHBoxLayout(row_inputs)
    hbox_inputs.setContentsMargins(0, 0, 0, 0)
    hbox_inputs.setSpacing(6)

    input_id = QLineEdit()
    input_id.setPlaceholderText("ID del Canal")
    input_id.setStyleSheet(
        "QLineEdit { border: 1px solid #CBD5E0; border-radius: 4px;"
        " padding: 4px 8px; font-size: 12px; }"
    )
    input_name = QLineEdit()
    input_name.setPlaceholderText("Nombre del Canal")
    input_name.setStyleSheet(
        "QLineEdit { border: 1px solid #CBD5E0; border-radius: 4px;"
        " padding: 4px 8px; font-size: 12px; }"
    )
    hbox_inputs.addWidget(input_id)
    hbox_inputs.addWidget(input_name)
    outer.addWidget(row_inputs)

    btn_agregar = QPushButton("➕  Agregar Canal")
    btn_agregar.setStyleSheet(
        "QPushButton { background: #2C5282; color: white; border-radius: 6px;"
        " padding: 6px 12px; font-size: 12px; font-weight: bold; }"
        "QPushButton:hover { background: #2A4365; }"
    )

    # --- Separador ---
    sep2 = QFrame()
    sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setStyleSheet("color: #E2E8F0;")

    # --- Lista de canales (scroll) ---
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setMaximumHeight(250)
    scroll.setFrameShape(QFrame.Shape.NoFrame)

    lista_container = QWidget()
    lista_layout = QVBoxLayout(lista_container)
    lista_layout.setContentsMargins(0, 0, 0, 0)
    lista_layout.setSpacing(6)
    lista_layout.addStretch()

    scroll.setWidget(lista_container)

    def refrescar_canales():
        # Eliminar filas anteriores (todo excepto el stretch al final)
        while lista_layout.count() > 1:
            item = lista_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for ch in obtener_canales_db():
            ch_id, ch_name = ch[0], ch[1]

            fila = QFrame()
            fila.setStyleSheet(
                "QFrame { border: 1px solid #E2E8F0; border-radius: 6px; background: white; }"
            )
            hbox = QHBoxLayout(fila)
            hbox.setContentsMargins(8, 6, 8, 6)
            hbox.setSpacing(8)

            lbl_play = QLabel("▶")
            lbl_play.setStyleSheet("color: #C53030; font-size: 16px;")
            lbl_play.setFixedWidth(20)

            col = QWidget()
            vcol = QVBoxLayout(col)
            vcol.setContentsMargins(0, 0, 0, 0)
            vcol.setSpacing(0)
            lbl_nombre = QLabel(ch_name)
            lbl_nombre.setStyleSheet("font-weight: bold; font-size: 12px; color: #2D3748;")
            lbl_id = QLabel(ch_id)
            lbl_id.setStyleSheet("font-size: 9px; color: #A0AEC0;")
            vcol.addWidget(lbl_nombre)
            vcol.addWidget(lbl_id)

            btn_del = QPushButton("🗑")
            btn_del.setFixedWidth(30)
            btn_del.setStyleSheet(
                "QPushButton { border: none; color: #FC8181; font-size: 14px; background: transparent; }"
                "QPushButton:hover { color: #C53030; }"
            )
            btn_del.clicked.connect(lambda _, cid=ch_id: _borrar_canal(cid))

            hbox.addWidget(lbl_play)
            hbox.addWidget(col, stretch=1)
            hbox.addWidget(btn_del)

            lista_layout.insertWidget(lista_layout.count() - 1, fila)

    def _borrar_canal(ch_id):
        eliminar_canal_db(ch_id)
        refrescar_canales()

    def _agregar_canal():
        ch_id = input_id.text().strip()
        ch_name = input_name.text().strip()
        if ch_id and ch_name:
            ok, msg = agregar_canal_db(ch_id, ch_name)
            if ok:
                input_id.clear()
                input_name.clear()
                refrescar_canales()

    btn_agregar.clicked.connect(_agregar_canal)

    outer.addWidget(btn_agregar)
    outer.addWidget(sep2)
    outer.addWidget(scroll)

    refrescar_canales()

    return group, None, refrescar_canales, None
```

**Verificación:**

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.state import AppState
from ui.panel_proyecto import build_panel_proyecto
state = AppState()
w, _, refrescar, _ = build_panel_proyecto(None, state, on_ruta_cambiada=lambda r: print('ruta:', r))
w.resize(400, 400)
w.show()
print('panel_proyecto OK')
app.exec()
"
```

**Criterio de éxito:** Imprime `panel_proyecto OK`. El panel muestra la lista de canales
y el botón de ruta abre un diálogo de selección de carpeta.

---

## Paso B-2 — REEMPLAZAR `ui/panel_tts.py`

**Contrato que debe mantener:**
```python
expansion_tts, _ = build_panel_tts(page, state, log_msg)
```

**Importante:** el botón "Probar TTS" lanza trabajo en background.
Usar `QThread` para no bloquear la UI.

**Contenido completo:**

```python
# ui/panel_tts.py
import threading

from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFrame,
)
from PyQt6.QtCore import QThread, pyqtSignal

from config import NVIDIA_API_KEY, guardar_config, normalizar_tts_config
from youtube_analyzer import obtener_ultimo_video


class _TtsWorker(QThread):
    resultado = pyqtSignal(bool, str)

    def __init__(self, carpeta, tts_config):
        super().__init__()
        self._carpeta = carpeta
        self._config = tts_config

    def run(self):
        try:
            from tts_nvidia import sintetizar_script_a_audio_nvidia
            ok, msg, _ = sintetizar_script_a_audio_nvidia(self._carpeta, self._config)
            self.resultado.emit(ok, msg)
        except Exception as ex:
            self.resultado.emit(False, f"Error TTS: {ex}")


def _make_line_edit(placeholder="", value=""):
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setText(str(value))
    w.setStyleSheet(
        "QLineEdit { border: 1px solid #CBD5E0; border-radius: 4px;"
        " padding: 4px 8px; font-size: 12px; }"
    )
    return w


def build_panel_tts(_page=None, state=None, log_msg=None):
    """
    Panel de Síntesis de Voz - NVIDIA TTS.

    Retorna
    -------
    (widget: QGroupBox, get_tts_config: callable)
    """
    tts_config = state.tts_config
    _worker_ref = [None]   # evitar que el QThread se garbage-collecte

    group = QGroupBox("🔊 Síntesis de Voz - NVIDIA TTS")
    group.setCheckable(True)
    group.setChecked(False)
    group.setStyleSheet(
        "QGroupBox { font-weight: bold; font-size: 13px; margin-top: 6px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
    )

    outer = QVBoxLayout(group)
    outer.setContentsMargins(8, 12, 8, 8)
    outer.setSpacing(8)

    # --- Estado NVIDIA API ---
    if NVIDIA_API_KEY:
        lbl_nvidia = QLabel("✅ NVIDIA API: detectada")
        lbl_nvidia.setStyleSheet("font-size: 12px; color: #276749; font-style: italic;")
    else:
        lbl_nvidia = QLabel("⚠️ NVIDIA API: no configurada")
        lbl_nvidia.setStyleSheet("font-size: 12px; color: #C05621; font-style: italic;")
    outer.addWidget(lbl_nvidia)

    # --- Switch habilitado ---
    chk_enabled = QCheckBox("🔊 Generar audio automáticamente al crear script.txt")
    chk_enabled.setChecked(bool(tts_config.get("enabled", False)))
    chk_enabled.setStyleSheet("font-size: 12px;")
    outer.addWidget(chk_enabled)

    # --- Campos de configuración ---
    txt_language = _make_line_edit("Language Code", tts_config.get("language_code", "en-US"))
    txt_voice    = _make_line_edit("Voice",          tts_config.get("voice", ""))
    txt_output   = _make_line_edit("Archivo WAV",    tts_config.get("output_filename", "audio.wav"))

    row_rate = QWidget()
    hbox_rate = QHBoxLayout(row_rate)
    hbox_rate.setContentsMargins(0, 0, 0, 0)
    hbox_rate.setSpacing(6)
    txt_sample_rate = _make_line_edit("Sample Rate (Hz)", str(tts_config.get("sample_rate_hz", 44100)))
    hbox_rate.addWidget(txt_output)
    hbox_rate.addWidget(txt_sample_rate)

    for lbl_txt, widget in [
        ("Language Code:", txt_language),
        ("Voice:",         txt_voice),
        ("Archivo WAV / Sample Rate:", row_rate),
    ]:
        lbl = QLabel(lbl_txt)
        lbl.setStyleSheet("font-size: 11px; color: #718096;")
        outer.addWidget(lbl)
        outer.addWidget(widget)

    # --- Nota de voz válida ---
    lbl_nota = QLabel("Voz válida: Magpie-Multilingual.EN-US.Aria")
    lbl_nota.setStyleSheet("font-size: 11px; color: #A0AEC0; font-style: italic;")
    outer.addWidget(lbl_nota)

    def persistir_tts(mostrar_snack=False):
        tts_config["enabled"]         = chk_enabled.isChecked()
        tts_config["language_code"]   = txt_language.text().strip()
        tts_config["voice"]           = txt_voice.text().strip()
        tts_config["output_filename"] = txt_output.text().strip()
        tts_config["sample_rate_hz"]  = txt_sample_rate.text().strip()

        normalizado = normalizar_tts_config(tts_config)
        tts_config.update(normalizado)

        txt_language.setText(tts_config["language_code"])
        txt_voice.setText(tts_config["voice"])
        txt_output.setText(tts_config["output_filename"])
        txt_sample_rate.setText(str(tts_config["sample_rate_hz"]))

        guardar_config(tts=tts_config)

    # Guardar al perder foco
    chk_enabled.stateChanged.connect(lambda _: persistir_tts())
    txt_language.editingFinished.connect(persistir_tts)
    txt_voice.editingFinished.connect(persistir_tts)
    txt_output.editingFinished.connect(persistir_tts)
    txt_sample_rate.editingFinished.connect(persistir_tts)

    # --- Botón probar TTS ---
    btn_probar = QPushButton("🎛  Probar TTS en último script")
    btn_probar.setStyleSheet(
        "QPushButton { background: #2B6CB0; color: white; border-radius: 6px;"
        " padding: 6px 12px; font-size: 12px; font-weight: bold; }"
        "QPushButton:hover { background: #2C5282; }"
        "QPushButton:disabled { background: #A0AEC0; }"
    )

    def _on_probar_tts():
        persistir_tts()
        ultimo = obtener_ultimo_video(state.ruta_base[0])
        if not ultimo:
            if log_msg:
                log_msg("⚠ No hay proyectos generados para probar TTS", color="orange700")
            return

        btn_probar.setEnabled(False)
        if log_msg:
            log_msg("🔊 Iniciando prueba TTS...", color="blue800")

        worker = _TtsWorker(ultimo, dict(tts_config))
        _worker_ref[0] = worker

        def _on_result(ok, msg):
            if log_msg:
                log_msg(
                    f"{'✅' if ok else '❌'} {msg}",
                    color="green700" if ok else "red700",
                    weight="bold" if ok else None,
                )
            btn_probar.setEnabled(True)
            _worker_ref[0] = None

        worker.resultado.connect(_on_result)
        worker.start()

    btn_probar.clicked.connect(_on_probar_tts)
    outer.addWidget(btn_probar)

    def get_tts_config():
        return tts_config

    return group, get_tts_config
```

**Verificación:**

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.state import AppState
from ui.panel_tts import build_panel_tts
state = AppState()
def fake_log(txt, **kw): print('LOG:', txt)
w, get_cfg = build_panel_tts(None, state, fake_log)
w.resize(400, 350)
w.show()
print('panel_tts OK')
app.exec()
"
```

**Criterio de éxito:** Imprime `panel_tts OK`. El panel muestra los campos de configuración TTS.

---

## Paso B-3 — REEMPLAZAR `ui/panel_whisperx.py`

**Contrato que debe mantener:**
```python
expansion_whisperx, _ = build_panel_whisperx(page, state)
```

**Contenido completo:**

```python
# ui/panel_whisperx.py
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QWidget, QLabel,
    QLineEdit, QPushButton, QCheckBox, QComboBox,
)

from config import guardar_config


def build_panel_whisperx(_page=None, state=None):
    """
    Panel de Transcripción - WhisperX.

    Retorna
    -------
    (widget: QGroupBox, get_whisperx_config: callable)
    """
    whisperx_config = state.whisperx_config

    group = QGroupBox("🎙️ Transcripción - WhisperX")
    group.setCheckable(True)
    group.setChecked(False)
    group.setStyleSheet(
        "QGroupBox { font-weight: bold; font-size: 13px; margin-top: 6px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
    )

    outer = QVBoxLayout(group)
    outer.setContentsMargins(8, 12, 8, 8)
    outer.setSpacing(8)

    # --- Switch habilitado ---
    chk_enabled = QCheckBox("🎙️ Transcribir audio con WhisperX automáticamente")
    chk_enabled.setChecked(bool(whisperx_config.get("enabled", False)))
    chk_enabled.setStyleSheet("font-size: 12px;")
    outer.addWidget(chk_enabled)

    # --- Dropdown modelo ---
    lbl_modelo = QLabel("Modelo WhisperX:")
    lbl_modelo.setStyleSheet("font-size: 11px; color: #718096;")
    outer.addWidget(lbl_modelo)

    combo_model = QComboBox()
    combo_model.setStyleSheet(
        "QComboBox { border: 1px solid #CBD5E0; border-radius: 4px;"
        " padding: 4px 8px; font-size: 12px; }"
    )
    for opcion in ["tiny", "base", "small", "medium", "large"]:
        combo_model.addItem(opcion, opcion)
    modelo_actual = whisperx_config.get("model", "medium")
    idx = combo_model.findData(modelo_actual)
    if idx >= 0:
        combo_model.setCurrentIndex(idx)
    outer.addWidget(combo_model)

    # --- Ruta Python ---
    lbl_python = QLabel("Ruta Python (whisperx-env):")
    lbl_python.setStyleSheet("font-size: 11px; color: #718096;")
    outer.addWidget(lbl_python)

    txt_python = QLineEdit()
    txt_python.setText(whisperx_config.get("python_path", ""))
    txt_python.setPlaceholderText(
        r"C:\Users\carlo\miniconda3\envs\whisperx-env\python.exe"
    )
    txt_python.setStyleSheet(
        "QLineEdit { border: 1px solid #CBD5E0; border-radius: 4px;"
        " padding: 4px 8px; font-size: 12px; }"
    )
    outer.addWidget(txt_python)

    def persistir_whisperx(mostrar_snack=False):
        whisperx_config["enabled"]     = chk_enabled.isChecked()
        whisperx_config["model"]       = combo_model.currentData() or "medium"
        whisperx_config["python_path"] = txt_python.text().strip()
        guardar_config(whisperx=whisperx_config)

    # Guardar al cambiar
    chk_enabled.stateChanged.connect(lambda _: persistir_whisperx())
    combo_model.currentIndexChanged.connect(lambda _: persistir_whisperx())
    txt_python.editingFinished.connect(persistir_whisperx)

    # --- Botón guardar ---
    btn_guardar = QPushButton("💾  Guardar config WhisperX")
    btn_guardar.setStyleSheet(
        "QPushButton { background: #6B46C1; color: white; border-radius: 6px;"
        " padding: 6px 12px; font-size: 12px; font-weight: bold; }"
        "QPushButton:hover { background: #553C9A; }"
    )
    btn_guardar.clicked.connect(lambda: persistir_whisperx(mostrar_snack=True))
    outer.addWidget(btn_guardar)

    def get_whisperx_config():
        return whisperx_config

    return group, get_whisperx_config
```

**Verificación:**

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.state import AppState
from ui.panel_whisperx import build_panel_whisperx
state = AppState()
w, get_cfg = build_panel_whisperx(None, state)
w.resize(400, 280)
w.show()
print('panel_whisperx OK')
app.exec()
"
```

**Criterio de éxito:** Imprime `panel_whisperx OK`. El panel muestra el checkbox,
el combo de modelo y el campo de ruta Python.

---

## Paso B-4 — REEMPLAZAR `ui/panel_ai_studio.py`

**Contrato que debe mantener:**
```python
expansion_ai_studio, _ = build_panel_ai_studio(page, state)
```

**Nota sobre `QTextEdit` y foco perdido:** `QTextEdit` no tiene `editingFinished`.
Se usa una subclase con `focusOutEvent` para replicar el comportamiento de `on_blur` de Flet.

**Contenido completo:**

```python
# ui/panel_ai_studio.py
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QWidget, QLabel,
    QLineEdit, QPushButton, QTextEdit,
)
from PyQt6.QtCore import pyqtSignal

from config import guardar_config, normalizar_ai_studio_config


class _FocusTextEdit(QTextEdit):
    """QTextEdit que emite focus_lost al perder el foco (equivale a on_blur de Flet)."""
    focus_lost = pyqtSignal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_lost.emit()


def build_panel_ai_studio(_page=None, state=None):
    """
    Panel de Prompts de Imagen - AI Studio.

    Retorna
    -------
    (widget: QGroupBox, get_ai_studio_config: callable)
    """
    ai_studio_config = state.ai_studio_config
    config_actual    = state.config_actual

    group = QGroupBox("🤖 Prompts de Imagen - AI Studio")
    group.setCheckable(True)
    group.setChecked(False)
    group.setStyleSheet(
        "QGroupBox { font-weight: bold; font-size: 13px; margin-top: 6px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
    )

    outer = QVBoxLayout(group)
    outer.setContentsMargins(8, 12, 8, 8)
    outer.setSpacing(8)

    # --- Espera respuesta ---
    lbl_wait = QLabel("Espera respuesta AI Studio (segundos):")
    lbl_wait.setStyleSheet("font-size: 11px; color: #718096;")
    outer.addWidget(lbl_wait)

    txt_wait = QLineEdit()
    txt_wait.setText(str(ai_studio_config.get("espera_respuesta_segundos", 15)))
    txt_wait.setStyleSheet(
        "QLineEdit { border: 1px solid #CBD5E0; border-radius: 4px;"
        " padding: 4px 8px; font-size: 12px; max-width: 220px; }"
    )
    txt_wait.setMaximumWidth(220)
    outer.addWidget(txt_wait)

    # --- Prompt AI Studio ---
    lbl_prompt = QLabel("Prompt para Google AI Studio (se envía al finalizar WhisperX):")
    lbl_prompt.setStyleSheet("font-size: 11px; color: #718096;")
    outer.addWidget(lbl_prompt)

    txt_prompt = _FocusTextEdit()
    txt_prompt.setPlainText(ai_studio_config.get("prompt", ""))
    txt_prompt.setPlaceholderText("Escribe aquí el prompt que se pegará en AI Studio...")
    txt_prompt.setMinimumHeight(80)
    txt_prompt.setMaximumHeight(160)
    txt_prompt.setStyleSheet(
        "QTextEdit { border: 1px solid #CBD5E0; border-radius: 4px;"
        " padding: 4px 8px; font-size: 12px; }"
    )
    outer.addWidget(txt_prompt)

    # --- Nota ---
    lbl_nota = QLabel("Los prompts extraídos se guardarán en prompts_imagenes.txt.")
    lbl_nota.setStyleSheet("font-size: 11px; color: #A0AEC0; font-style: italic;")
    outer.addWidget(lbl_nota)

    def persistir_ai_studio(mostrar_snack=False):
        ai_studio_config["prompt"] = txt_prompt.toPlainText()
        ai_studio_config["espera_respuesta_segundos"] = txt_wait.text().strip()

        normalizado = normalizar_ai_studio_config(ai_studio_config)
        ai_studio_config.update(normalizado)

        txt_prompt.setPlainText(ai_studio_config["prompt"])
        txt_wait.setText(str(ai_studio_config["espera_respuesta_segundos"]))

        config_actual["ai_studio"]      = dict(ai_studio_config)
        config_actual["prompt_ai_studio"] = ai_studio_config["prompt"]

        guardar_config(ai_studio=ai_studio_config)

    # Guardar al perder foco
    txt_prompt.focus_lost.connect(persistir_ai_studio)
    txt_wait.editingFinished.connect(persistir_ai_studio)

    # --- Botón guardar ---
    btn_guardar = QPushButton("💾  Guardar configuración AI Studio")
    btn_guardar.setStyleSheet(
        "QPushButton { background: #2B6CB0; color: white; border-radius: 6px;"
        " padding: 8px 12px; font-size: 12px; font-weight: bold; }"
        "QPushButton:hover { background: #2C5282; }"
    )
    btn_guardar.clicked.connect(lambda: persistir_ai_studio(mostrar_snack=True))
    outer.addWidget(btn_guardar)

    def get_ai_studio_config():
        return ai_studio_config

    return group, get_ai_studio_config
```

**Verificación:**

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.state import AppState
from ui.panel_ai_studio import build_panel_ai_studio
state = AppState()
w, get_cfg = build_panel_ai_studio(None, state)
w.resize(420, 320)
w.show()
print('panel_ai_studio OK')
app.exec()
"
```

**Criterio de éxito:** Imprime `panel_ai_studio OK`. El panel muestra el campo de espera,
el área de texto del prompt y el botón guardar.

---

## Verificación final del Plan B

Verificar que todos los módulos migrados hasta ahora importan juntos sin errores:

```bash
python -c "
from ui.compat        import PageCompat, ProgressBarCompat, TextCompat, DropdownCompat
from ui.consola       import build_consola
from ui.tracker       import construir_tracker_fases
from ui.header        import build_header
from ui.panel_proyecto  import build_panel_proyecto
from ui.panel_tts       import build_panel_tts
from ui.panel_whisperx  import build_panel_whisperx
from ui.panel_ai_studio import build_panel_ai_studio
from ui.state           import AppState
print('Plan A + Plan B: todos los modulos importan OK')
"
```

**Criterio de éxito:** Imprime el mensaje sin errores.

---

## Qué viene después

Al terminar el Plan B quedan pendientes en Flet:
- `ui/panel_prompts.py` — el más complejo (~600 líneas)
- `ui/panel_flow.py`
- `ui_main.py`
- `clusiv-auto.py`

El **Plan C** migrará solo `panel_prompts.py`.
El **Plan D** migrará `panel_flow.py` + `ui_main.py` + `clusiv-auto.py`
y dejará la app completamente en PyQt6.
