from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
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

    chk_enabled = QCheckBox("🎙️ Transcribir audio con WhisperX automáticamente")
    chk_enabled.setChecked(bool(whisperx_config.get("enabled", False)))
    chk_enabled.setStyleSheet("font-size: 12px;")
    outer.addWidget(chk_enabled)

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

    lbl_python = QLabel("Ruta Python (whisperx-env):")
    lbl_python.setStyleSheet("font-size: 11px; color: #718096;")
    outer.addWidget(lbl_python)

    txt_python = QLineEdit()
    txt_python.setText(whisperx_config.get("python_path", ""))
    txt_python.setPlaceholderText(r"C:\Users\carlo\miniconda3\envs\whisperx-env\python.exe")
    txt_python.setStyleSheet(
        "QLineEdit { border: 1px solid #CBD5E0; border-radius: 4px;"
        " padding: 4px 8px; font-size: 12px; }"
    )
    outer.addWidget(txt_python)

    def persistir_whisperx(mostrar_snack=False):
        whisperx_config["enabled"] = chk_enabled.isChecked()
        whisperx_config["model"] = combo_model.currentData() or "medium"
        whisperx_config["python_path"] = txt_python.text().strip()
        guardar_config(whisperx=whisperx_config)

    chk_enabled.stateChanged.connect(lambda _: persistir_whisperx())
    combo_model.currentIndexChanged.connect(lambda _: persistir_whisperx())
    txt_python.editingFinished.connect(persistir_whisperx)

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
