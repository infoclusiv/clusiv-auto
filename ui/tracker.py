from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

FASES = [
    ("youtube", "📺", "Análisis YouTube"),
    ("chatgpt", "💬", "ChatGPT - Prompts"),
    ("texto", "📄", "Post-proceso texto"),
    ("tts", "🔊", "Síntesis TTS"),
    ("whisperx", "🎙️", "Transcripción"),
    ("aistudio", "🤖", "Prompts de imagen"),
    ("flow", "🖼️", "Generación imágenes"),
]

_ESTILOS = {
    "pending": ("background:#F7FAFC; border:1px solid #E2E8F0; border-radius:8px;", "#A0AEC0", "○"),
    "running": ("background:#EBF8FF; border:1px solid #90CDF4; border-radius:8px;", "#2B6CB0", "↻"),
    "done": ("background:#F0FFF4; border:1px solid #9AE6B4; border-radius:8px;", "#276749", "✓"),
    "error": ("background:#FFF5F5; border:1px solid #FEB2B2; border-radius:8px;", "#C53030", "✗"),
    "skipped": ("background:#FFFBEB; border:1px solid #FAF089; border-radius:8px;", "#975A16", "⏭"),
}


def construir_tracker_fases(_page=None):
    """
    Construye el tracker visual de fases del pipeline.

    Parametros
    ----------
    _page : ignorado - se mantiene para compatibilidad con la firma Flet.

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
        lbl_indicador.setStyleSheet("color: #A0AEC0; font-size: 14px;")
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
            "frame": frame,
            "indicador": lbl_indicador,
            "detalle": lbl_detalle,
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

    def reset_tracker():
        for fase_id, _, _ in FASES:
            set_fase_estado(fase_id, "pending", "-")

    return container, set_fase_estado, reset_tracker
