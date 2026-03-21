from datetime import datetime

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

FLET_COLOR_MAP = {
    "red": "#E53E3E",
    "red700": "#C53030",
    "red_700": "#C53030",
    "green700": "#276749",
    "green_700": "#276749",
    "green800": "#22543D",
    "green_800": "#22543D",
    "orange": "#DD6B20",
    "orange700": "#C05621",
    "orange_700": "#C05621",
    "orange800": "#9C4221",
    "orange_800": "#9C4221",
    "blue": "#3182CE",
    "blue800": "#2C5282",
    "blue_800": "#2C5282",
    "amber800": "#975A16",
    "amber_800": "#975A16",
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

    Parametros
    ----------
    _page : ignorado - se mantiene para compatibilidad con la firma Flet
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

    count = [0]

    def log_msg(texto, color=None, weight=None, italic=False, is_divider=False):
        if is_divider:
            log_area.append(
                '<hr style="border:none; border-top:1px solid #E2E8F0; margin:4px 0"/>'
            )
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        color_hex = _color_hex(color)
        font_weight = "bold" if weight in ("bold", "w700", "w800", "w900") else "normal"
        font_style = "italic" if italic else "normal"

        html = (
            f'<span style="color:#A0AEC0; font-size:10px;">[{timestamp}]</span> '
            f'<span style="color:{color_hex}; font-weight:{font_weight}; font-style:{font_style};">'
            f"{texto}</span>"
        )
        log_area.append(html)
        count[0] += 1

        if count[0] > _MAX_MESSAGES:
            cursor = QTextCursor(log_area.document())
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()
            count[0] -= 1

        log_area.moveCursor(QTextCursor.MoveOperation.End)

    def limpiar_log(e=None):
        log_area.clear()
        count[0] = 0

    return widget, log_msg, limpiar_log
