# Plan A — Migración Base (PyQt6)

> **Alcance exacto:** 4 archivos solamente.
> - CREAR: `ui/compat.py`
> - REEMPLAZAR: `ui/consola.py`
> - REEMPLAZAR: `ui/tracker.py`
> - REEMPLAZAR: `ui/header.py`
>
> **Al terminar este plan:** `ui_main.py` y `clusiv-auto.py` siguen sin cambios.
> La app Flet todavía corre igual. Solo se reemplaza la implementación interna
> de estos 4 módulos.
>
> **NO tocar:** `ui/state.py`, `ui/panel_*.py`, `ui_main.py`, `clusiv-auto.py`,
> ni ningún archivo fuera de `ui/`.

---

## Paso A-0 — Instalar PyQt6

```bash
pip install PyQt6
```

Verificar en el entorno del proyecto (`.venv`):

```bash
python -c "from PyQt6.QtWidgets import QApplication; from PyQt6.QtCore import QThread, pyqtSignal; print('PyQt6 OK')"
```

**Criterio de éxito:** Imprime `PyQt6 OK` sin errores.
Si falla, instalar dentro del `.venv` activo del proyecto antes de continuar.

---

## Paso A-1 — CREAR `ui/compat.py`

Este archivo es nuevo. No reemplaza nada existente.

**Por qué existe:** `flow_orchestrator.py` recibe objetos Flet en `FlowContext`
(`page`, `prg`, `txt_proximo`, `dropdown_ref_mode`) y llama `.update()`, `.visible`,
`.value` en ellos. No se puede tocar el orquestador, así que estos adaptadores
imitan esa interfaz usando PyQt6 por debajo.

**Contenido completo:**

```python
# ui/compat.py
"""
Adaptadores de compatibilidad Flet → PyQt6 para FlowContext.
Imitan la interfaz de widgets Flet sin importar Flet.
"""
from PyQt6.QtWidgets import QApplication


class PageCompat:
    """Reemplaza ft.Page. page.update() → processEvents() para no bloquear la UI."""

    def update(self):
        QApplication.processEvents()

    # Atributos que flow_orchestrator podría leer (defensivo)
    controls = []


class ProgressBarCompat:
    """
    Reemplaza ft.ProgressBar.
    Asignar .visible dispara el callback on_visible_change(bool).
    """

    def __init__(self, on_visible_change=None):
        self._visible = False
        self._cb = on_visible_change

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        self._visible = bool(value)
        if self._cb:
            self._cb(self._visible)


class TextCompat:
    """
    Reemplaza ft.Text.
    Asignar .value dispara el callback on_value_change(str).
    """

    def __init__(self, initial_value: str = "", on_value_change=None):
        self._value = initial_value
        self._cb = on_value_change

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v: str):
        self._value = str(v)
        if self._cb:
            self._cb(self._value)


class DropdownCompat:
    """
    Reemplaza ft.Dropdown para dropdown_ref_mode.
    Se enlaza a un QComboBox real mediante set_combo().
    .value devuelve el texto/dato del item seleccionado actualmente.
    """

    def __init__(self, default_value: str = "ingredients"):
        self._default = default_value
        self._combo = None

    def set_combo(self, combo_box):
        """Llamar justo después de crear el QComboBox para enlazarlo."""
        self._combo = combo_box

    @property
    def value(self):
        if self._combo is not None:
            data = self._combo.currentData()
            return data if data is not None else self._combo.currentText()
        return self._default

    @value.setter
    def value(self, v: str):
        self._default = v
        if self._combo is not None:
            idx = self._combo.findData(v)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
```

**Verificación:**

```bash
python -c "
from ui.compat import PageCompat, ProgressBarCompat, TextCompat, DropdownCompat
p = PageCompat(); p.update()
prg = ProgressBarCompat(on_visible_change=lambda v: print('visible:', v))
prg.visible = True
txt = TextCompat(on_value_change=lambda v: print('value:', v))
txt.value = 'hola'
d = DropdownCompat()
print('valor por defecto:', d.value)
print('compat OK')
"
```

**Criterio de éxito:** Imprime `visible: True`, `value: hola`, `valor por defecto: ingredients`, `compat OK`.

---

## Paso A-2 — REEMPLAZAR `ui/consola.py`

**Contrato que debe mantener** (lo que `ui_main.py` espera recibir):
```python
log_container, log_msg, limpiar_log = build_consola(page)
```
- `log_container`: widget montable en la UI
- `log_msg(texto, color=None, weight=None, italic=False, is_divider=False)`: agrega mensaje
- `limpiar_log(e=None)`: vacía la consola

**Cambio de firma:** `build_consola(page)` → `build_consola()`.
`ui_main.py` se actualizará en el Plan D para reflejar esto.
Por ahora el módulo simplemente ignora el argumento `page` si se pasa.

> **Nota sobre colores:** `flow_orchestrator.py` y los paneles llaman `log_msg`
> pasando valores como `ft.Colors.RED_700`, `ft.Colors.GREEN_700`, etc.
> Esos valores son strings como `"red700"`, `"green700"`. El mapa `FLET_COLOR_MAP`
> los convierte a hex. Verificar el valor exacto con:
> `python -c "import flet as ft; print(repr(ft.Colors.RED_700))"`
> y ajustar el mapa si difiere de lo esperado.

**Contenido completo:**

```python
# ui/consola.py
from datetime import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from PyQt6.QtGui import QTextCursor
from PyQt6.QtCore import Qt

# Mapa de valores ft.Colors.* → color hex CSS.
# ft.Colors.RED_700 es el string "red700" (sin guion bajo en la mayoría de versiones).
# Si los colores no aparecen bien, imprimir repr(ft.Colors.RED_700) para confirmar.
FLET_COLOR_MAP = {
    "red":         "#E53E3E",
    "red700":      "#C53030",
    "red_700":     "#C53030",
    "green700":    "#276749",
    "green_700":   "#276749",
    "green800":    "#22543D",
    "green_800":   "#22543D",
    "orange":      "#DD6B20",
    "orange700":   "#C05621",
    "orange_700":  "#C05621",
    "orange800":   "#9C4221",
    "orange_800":  "#9C4221",
    "blue":        "#3182CE",
    "blue800":     "#2C5282",
    "blue_800":    "#2C5282",
    "amber800":    "#975A16",
    "amber_800":   "#975A16",
}
_DEFAULT_COLOR = "#2D3748"
_MAX_MESSAGES = 150


def _color_hex(color) -> str:
    """Convierte un valor ft.Colors (string) o None a un color hex CSS."""
    if color is None:
        return _DEFAULT_COLOR
    key = str(color).lower().replace(" ", "")
    return FLET_COLOR_MAP.get(key, _DEFAULT_COLOR)


def build_consola(_page=None):
    """
    Construye la consola de logs.

    Parámetros
    ----------
    _page : ignorado — se mantiene para compatibilidad con la firma Flet
            mientras ui_main.py no se actualice.

    Retorna
    -------
    (widget: QWidget, log_msg: callable, limpiar_log: callable)
    """
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)

    log_area = QTextEdit()
    log_area.setReadOnly(True)
    log_area.setStyleSheet(
        "QTextEdit {"
        "  background: #F8F9FA;"
        "  font-family: Consolas, 'Courier New', monospace;"
        "  font-size: 12px;"
        "  border: 1px solid #CBD5E0;"
        "  border-radius: 8px;"
        "  padding: 8px;"
        "}"
    )
    layout.addWidget(log_area)

    _count = [0]

    def log_msg(texto, color=None, weight=None, italic=False, is_divider=False):
        if is_divider:
            log_area.append(
                '<hr style="border:none; border-top:1px solid #E2E8F0; margin:4px 0"/>'
            )
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        color_hex = _color_hex(color)
        fw = "bold" if weight in ("bold", "w700", "w800", "w900") else "normal"
        fs = "italic" if italic else "normal"

        html = (
            f'<span style="color:#A0AEC0; font-size:10px;">[{timestamp}]</span> '
            f'<span style="color:{color_hex}; font-weight:{fw}; font-style:{fs};">'
            f'{texto}</span>'
        )
        log_area.append(html)
        _count[0] += 1

        # Limitar cantidad de mensajes eliminando los más viejos
        if _count[0] > _MAX_MESSAGES:
            cursor = QTextCursor(log_area.document())
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()
            _count[0] -= 1

        # Auto-scroll al final
        log_area.moveCursor(QTextCursor.MoveOperation.End)

    def limpiar_log(e=None):
        log_area.clear()
        _count[0] = 0

    return widget, log_msg, limpiar_log
```

**Verificación:**

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.consola import build_consola
w, log_msg, limpiar = build_consola()
log_msg('Mensaje normal')
log_msg('Error critico', color='red700')
log_msg('Exito', color='green700', weight='bold')
log_msg('Advertencia', color='orange800', italic=True)
log_msg('', is_divider=True)
w.resize(600, 300)
w.show()
# Solo verificar que no lanza excepciones — cerrar la ventana manualmente
# o usar: app.exec()
print('consola OK')
"
```

**Criterio de éxito:** Imprime `consola OK` sin excepciones. La ventana muestra mensajes con colores distintos.

---

## Paso A-3 — REEMPLAZAR `ui/tracker.py`

**Contrato que debe mantener:**
```python
tracker_widget, set_fase_estado, reset_tracker = construir_tracker_fases(page)
```
- `tracker_widget`: widget montable en la UI
- `set_fase_estado(fase_id, estado, detalle="", refresh=True)`: actualiza una fase
- `reset_tracker()`: pone todas en `pending`

**Cambio de firma:** `construir_tracker_fases(page)` → `construir_tracker_fases()`.
El argumento `page` se ignora si se pasa (compatibilidad mientras `ui_main.py` no se actualice).

**Fases (igual que el original):**
```
youtube, chatgpt, texto, tts, whisperx, aistudio, flow
```

**Estados y sus estilos:**

| Estado | Fondo | Borde | Emoji indicador |
|--------|-------|-------|-----------------|
| pending | `#F7FAFC` | `#E2E8F0` | ○ |
| running | `#EBF8FF` | `#90CDF4` | ↻ |
| done | `#F0FFF4` | `#9AE6B4` | ✓ |
| error | `#FFF5F5` | `#FEB2B2` | ✗ |
| skipped | `#FFFBEB` | `#FAF089` | ⏭ |

**Contenido completo:**

```python
# ui/tracker.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt

FASES = [
    ("youtube",  "📺", "Análisis YouTube"),
    ("chatgpt",  "💬", "ChatGPT - Prompts"),
    ("texto",    "📄", "Post-proceso texto"),
    ("tts",      "🔊", "Síntesis TTS"),
    ("whisperx", "🎙️", "Transcripción"),
    ("aistudio", "🤖", "Prompts de imagen"),
    ("flow",     "🖼️", "Generación imágenes"),
]

_ESTILOS = {
    "pending": ("background:#F7FAFC; border:1px solid #E2E8F0; border-radius:8px;", "#A0AEC0", "○"),
    "running": ("background:#EBF8FF; border:1px solid #90CDF4; border-radius:8px;", "#2B6CB0", "↻"),
    "done":    ("background:#F0FFF4; border:1px solid #9AE6B4; border-radius:8px;", "#276749", "✓"),
    "error":   ("background:#FFF5F5; border:1px solid #FEB2B2; border-radius:8px;", "#C53030", "✗"),
    "skipped": ("background:#FFFBEB; border:1px solid #FAF089; border-radius:8px;", "#975A16", "⏭"),
}


def construir_tracker_fases(_page=None):
    """
    Construye el tracker visual de fases del pipeline.

    Parámetros
    ----------
    _page : ignorado — se mantiene para compatibilidad con la firma Flet.

    Retorna
    -------
    (widget: QWidget, set_fase_estado: callable, reset_tracker: callable)
    """
    container = QWidget()
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(0, 0, 0, 0)
    vbox.setSpacing(4)

    controles = {}

    for fase_id, icono, nombre in FASES:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setStyleSheet(_ESTILOS["pending"][0])

        hbox = QHBoxLayout(frame)
        hbox.setContentsMargins(10, 6, 10, 6)
        hbox.setSpacing(10)

        lbl_indicador = QLabel("○")
        lbl_indicador.setFixedWidth(16)
        lbl_indicador.setStyleSheet(f"color: #A0AEC0; font-size: 14px;")
        lbl_indicador.setAlignment(Qt.AlignmentFlag.AlignCenter)

        col_texto = QWidget()
        vbox_texto = QVBoxLayout(col_texto)
        vbox_texto.setContentsMargins(0, 0, 0, 0)
        vbox_texto.setSpacing(1)

        lbl_nombre = QLabel(f"{icono}  {nombre}")
        lbl_nombre.setStyleSheet("font-weight: bold; font-size: 12px; color: #2D3748;")

        lbl_detalle = QLabel("-")
        lbl_detalle.setStyleSheet("font-size: 10px; color: #A0AEC0; font-style: italic;")

        vbox_texto.addWidget(lbl_nombre)
        vbox_texto.addWidget(lbl_detalle)

        hbox.addWidget(lbl_indicador)
        hbox.addWidget(col_texto, stretch=1)

        controles[fase_id] = {
            "frame":     frame,
            "indicador": lbl_indicador,
            "detalle":   lbl_detalle,
        }
        vbox.addWidget(frame)

    def set_fase_estado(fase_id: str, estado: str, detalle: str = "", refresh: bool = True):
        ctrl = controles.get(fase_id)
        if ctrl is None:
            return

        estilo_frame, color_texto, emoji = _ESTILOS.get(estado, _ESTILOS["pending"])
        ctrl["frame"].setStyleSheet(estilo_frame)
        ctrl["indicador"].setText(emoji)
        ctrl["indicador"].setStyleSheet(f"color: {color_texto}; font-size: 14px;")
        ctrl["detalle"].setText(detalle or estado)
        ctrl["detalle"].setStyleSheet(
            f"font-size: 10px; color: {color_texto}; font-style: italic;"
        )
        # PyQt6 actualiza automáticamente — refresh se ignora

    def reset_tracker():
        for fase_id, _, _ in FASES:
            set_fase_estado(fase_id, "pending", "-")

    return container, set_fase_estado, reset_tracker
```

**Verificación:**

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.tracker import construir_tracker_fases
w, set_fase, reset = construir_tracker_fases()
set_fase('youtube', 'done', '3 videos analizados')
set_fase('chatgpt', 'running', 'Enviando prompt 2/5...')
set_fase('tts', 'error', 'API key invalida')
set_fase('whisperx', 'skipped', 'Deshabilitado')
w.resize(320, 350)
w.show()
print('tracker OK')
"
```

**Criterio de éxito:** Imprime `tracker OK`. La ventana muestra las fases con colores distintos por estado.

---

## Paso A-4 — REEMPLAZAR `ui/header.py`

**Contrato que debe mantener:**
```python
header_bar, actualizar_ext_status_header = build_header(page)
```
- `header_bar`: widget montable en la UI
- `actualizar_ext_status_header(conectada: bool, version: str = "")`: cambia el indicador

**Cambio de firma:** `build_header(page)` → `build_header()`.
El argumento se ignora si se pasa.

**Importante:** `ws_bridge` llama a `actualizar_ext_status_header` desde un hilo
secundario. En PyQt6 eso es seguro solo si el método no modifica widgets directamente
desde ese hilo. La solución es usar `QMetaObject.invokeMethod` con
`Qt.ConnectionType.QueuedConnection`, o garantizar que el callback solo
se llame desde el hilo principal. Por seguridad se usa `invokeMethod`.

**Contenido completo:**

```python
# ui/header.py
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QMetaObject, Q_ARG, pyqtSlot
from PyQt6.QtGui import QFont


def build_header(_page=None):
    """
    Construye la barra de cabecera con título y estado de la extensión Chrome.

    Parámetros
    ----------
    _page : ignorado — se mantiene para compatibilidad con la firma Flet.

    Retorna
    -------
    (widget: QWidget, actualizar_ext_status_header: callable)
    """
    widget = QWidget()
    widget.setFixedHeight(50)
    widget.setStyleSheet(
        "QWidget {"
        "  background: white;"
        "  border-bottom: 1px solid #E2E8F0;"
        "}"
    )

    hbox = QHBoxLayout(widget)
    hbox.setContentsMargins(20, 0, 20, 0)
    hbox.setSpacing(0)

    # --- Grupo izquierdo: logo + título ---
    logo_group = QWidget()
    logo_layout = QHBoxLayout(logo_group)
    logo_layout.setContentsMargins(0, 0, 0, 0)
    logo_layout.setSpacing(6)

    lbl_icon = QLabel("✨")
    lbl_icon.setStyleSheet("font-size: 20px;")

    lbl_clusiv = QLabel("Clusiv")
    lbl_clusiv.setStyleSheet("font-size: 20px; font-weight: bold; color: #2C5282;")

    lbl_auto = QLabel("Automation")
    lbl_auto.setStyleSheet("font-size: 20px; color: #2D3748;")

    logo_layout.addWidget(lbl_icon)
    logo_layout.addWidget(lbl_clusiv)
    logo_layout.addWidget(lbl_auto)

    # --- Grupo derecho: indicador + estado extensión ---
    status_group = QWidget()
    status_layout = QHBoxLayout(status_group)
    status_layout.setContentsMargins(0, 0, 0, 0)
    status_layout.setSpacing(6)

    lbl_punto = QLabel("●")
    lbl_punto.setStyleSheet("color: #DD6B20; font-size: 10px;")

    lbl_estado = QLabel("Extensión: desconectada")
    lbl_estado.setStyleSheet("font-size: 11px; color: #C05621;")

    status_layout.addWidget(lbl_punto)
    status_layout.addWidget(lbl_estado)

    hbox.addWidget(logo_group)
    hbox.addStretch()
    hbox.addWidget(status_group)

    # Guardar referencias para actualizar
    widget._lbl_punto = lbl_punto
    widget._lbl_estado = lbl_estado

    @pyqtSlot(bool, str)
    def _actualizar_en_hilo_principal(conectada: bool, version: str):
        version_label = f" v{version}" if version else ""
        if conectada:
            lbl_punto.setStyleSheet("color: #38A169; font-size: 10px;")
            lbl_estado.setStyleSheet("font-size: 11px; color: #276749;")
            lbl_estado.setText(f"Extensión: conectada{version_label}")
        else:
            lbl_punto.setStyleSheet("color: #DD6B20; font-size: 10px;")
            lbl_estado.setStyleSheet("font-size: 11px; color: #C05621;")
            lbl_estado.setText("Extensión: desconectada")

    def actualizar_ext_status_header(conectada: bool, version: str = ""):
        """
        Puede llamarse desde cualquier hilo.
        Delega la modificación de widgets al hilo principal mediante invokeMethod.
        """
        QMetaObject.invokeMethod(
            widget,
            "_actualizar_estado",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(bool, bool(conectada)),
            Q_ARG(str, str(version)),
        )

    # Registrar el slot en el widget para que invokeMethod lo encuentre
    def _slot_actualizar(conectada: bool, version: str):
        _actualizar_en_hilo_principal(conectada, version)

    widget._actualizar_estado = _actualizar_en_hilo_principal

    # Alternativa más simple y robusta: usar una señal lambda
    # Si invokeMethod da problemas, reemplazar con esta implementación:
    #
    # from PyQt6.QtCore import QTimer
    # def actualizar_ext_status_header(conectada, version=""):
    #     QTimer.singleShot(0, lambda: _actualizar_en_hilo_principal(conectada, version))

    return widget, actualizar_ext_status_header
```

> **Nota de implementación:** Si `QMetaObject.invokeMethod` con el slot nombrado
> da `TypeError` en el entorno real, reemplazar `actualizar_ext_status_header`
> con la alternativa comentada usando `QTimer.singleShot(0, lambda: ...)`.
> `QTimer.singleShot` con delay 0 siempre ejecuta en el hilo principal y es
> la forma más simple y robusta de hacer thread-safe UI updates en PyQt6.

**Verificación:**

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.header import build_header
w, actualizar = build_header()
actualizar(False)
w.resize(800, 50)
w.show()
# Simular conexión después de 1 segundo
from PyQt6.QtCore import QTimer
QTimer.singleShot(1000, lambda: actualizar(True, '1.2.3'))
print('header OK')
app.exec()
"
```

**Criterio de éxito:** Imprime `header OK`. La ventana muestra el header con el estado
desconectado (naranja) y tras 1 segundo cambia a conectado (verde).

---

## Verificación final del Plan A

Después de completar los 4 pasos anteriores, verificar que todos los módulos
importan correctamente juntos:

```bash
python -c "
from ui.compat import PageCompat, ProgressBarCompat, TextCompat, DropdownCompat
from ui.consola import build_consola
from ui.tracker import construir_tracker_fases
from ui.header import build_header
from ui.state import AppState   # no debe haber cambiado
print('Todos los modulos del Plan A importan OK')
"
```

**Criterio de éxito:** Imprime el mensaje sin errores ni warnings de importación.

---

## Qué viene después

Al terminar el Plan A quedan pendientes en Flet:
- `ui/panel_proyecto.py`
- `ui/panel_prompts.py`
- `ui/panel_tts.py`
- `ui/panel_whisperx.py`
- `ui/panel_ai_studio.py`
- `ui/panel_flow.py`
- `ui_main.py`
- `clusiv-auto.py`

El **Plan B** migrará los paneles simples: `panel_proyecto`, `panel_tts`,
`panel_whisperx` y `panel_ai_studio`.

El **Plan C** migrará solo `panel_prompts` (el más complejo).

El **Plan D** migrará `panel_flow` + `ui_main.py` + `clusiv-auto.py`
y dejará la app completamente en PyQt6.
