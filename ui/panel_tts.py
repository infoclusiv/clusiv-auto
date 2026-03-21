from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
    widget = QLineEdit()
    widget.setPlaceholderText(placeholder)
    widget.setText(str(value))
    widget.setStyleSheet(
        "QLineEdit { border: 1px solid #CBD5E0; border-radius: 4px;"
        " padding: 4px 8px; font-size: 12px; }"
    )
    return widget


def build_panel_tts(_page=None, state=None, log_msg=None):
    """
    Panel de Sintesis de Voz - NVIDIA TTS.

    Retorna
    -------
    (widget: QGroupBox, get_tts_config: callable)
    """
    tts_config = state.tts_config
    worker_ref = [None]

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

    if NVIDIA_API_KEY:
        lbl_nvidia = QLabel("✅ NVIDIA API: detectada")
        lbl_nvidia.setStyleSheet("font-size: 12px; color: #276749; font-style: italic;")
    else:
        lbl_nvidia = QLabel("⚠️ NVIDIA API: no configurada")
        lbl_nvidia.setStyleSheet("font-size: 12px; color: #C05621; font-style: italic;")
    outer.addWidget(lbl_nvidia)

    chk_enabled = QCheckBox("🔊 Generar audio automáticamente al crear script.txt")
    chk_enabled.setChecked(bool(tts_config.get("enabled", False)))
    chk_enabled.setStyleSheet("font-size: 12px;")
    outer.addWidget(chk_enabled)

    txt_language = _make_line_edit("Language Code", tts_config.get("language_code", "en-US"))
    txt_voice = _make_line_edit("Voice", tts_config.get("voice", ""))
    txt_output = _make_line_edit("Archivo WAV", tts_config.get("output_filename", "audio.wav"))

    row_rate = QWidget()
    hbox_rate = QHBoxLayout(row_rate)
    hbox_rate.setContentsMargins(0, 0, 0, 0)
    hbox_rate.setSpacing(6)
    txt_sample_rate = _make_line_edit(
        "Sample Rate (Hz)", str(tts_config.get("sample_rate_hz", 44100))
    )
    hbox_rate.addWidget(txt_output)
    hbox_rate.addWidget(txt_sample_rate)

    for lbl_txt, widget in [
        ("Language Code:", txt_language),
        ("Voice:", txt_voice),
        ("Archivo WAV / Sample Rate:", row_rate),
    ]:
        lbl = QLabel(lbl_txt)
        lbl.setStyleSheet("font-size: 11px; color: #718096;")
        outer.addWidget(lbl)
        outer.addWidget(widget)

    lbl_nota = QLabel("Voz válida: Magpie-Multilingual.EN-US.Aria")
    lbl_nota.setStyleSheet("font-size: 11px; color: #A0AEC0; font-style: italic;")
    outer.addWidget(lbl_nota)

    def persistir_tts(mostrar_snack=False):
        tts_config["enabled"] = chk_enabled.isChecked()
        tts_config["language_code"] = txt_language.text().strip()
        tts_config["voice"] = txt_voice.text().strip()
        tts_config["output_filename"] = txt_output.text().strip()
        tts_config["sample_rate_hz"] = txt_sample_rate.text().strip()

        normalizado = normalizar_tts_config(tts_config)
        tts_config.update(normalizado)

        txt_language.setText(tts_config["language_code"])
        txt_voice.setText(tts_config["voice"])
        txt_output.setText(tts_config["output_filename"])
        txt_sample_rate.setText(str(tts_config["sample_rate_hz"]))

        guardar_config(tts=tts_config)

    chk_enabled.stateChanged.connect(lambda _: persistir_tts())
    txt_language.editingFinished.connect(persistir_tts)
    txt_voice.editingFinished.connect(persistir_tts)
    txt_output.editingFinished.connect(persistir_tts)
    txt_sample_rate.editingFinished.connect(persistir_tts)

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
        worker_ref[0] = worker

        def _on_result(ok, msg):
            if log_msg:
                log_msg(
                    f"{'✅' if ok else '❌'} {msg}",
                    color="green700" if ok else "red700",
                    weight="bold" if ok else None,
                )
            btn_probar.setEnabled(True)
            worker_ref[0] = None

        worker.resultado.connect(_on_result)
        worker.start()

    btn_probar.clicked.connect(_on_probar_tts)
    outer.addWidget(btn_probar)

    def get_tts_config():
        return tts_config

    return group, get_tts_config
