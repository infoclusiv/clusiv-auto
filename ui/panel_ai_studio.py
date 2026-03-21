from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

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
    config_actual = state.config_actual

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

        config_actual["ai_studio"] = dict(ai_studio_config)
        config_actual["prompt_ai_studio"] = ai_studio_config["prompt"]

        guardar_config(ai_studio=ai_studio_config)

    txt_prompt.focus_lost.connect(persistir_ai_studio)
    txt_wait.editingFinished.connect(persistir_ai_studio)

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