"""ui_main.py - Interfaz principal de Clusiv Automation (PyQt6)."""

import sys

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

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


class _RefModeComboProxy:
    def __init__(self, get_ref_mode_fn):
        self._get_ref_mode_fn = get_ref_mode_fn

    def currentData(self):
        return self._get_ref_mode_fn()

    def currentText(self):
        return self._get_ref_mode_fn()

    def findData(self, value):
        return 0 if value == self._get_ref_mode_fn() else -1

    def setCurrentIndex(self, index):
        return None


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

    def _build_ui(self):
        self.log_widget, self.log_msg, self.limpiar_log = build_consola()
        self.tracker_widget, self.set_fase_estado, self.reset_tracker = construir_tracker_fases()
        self.header_widget, self.actualizar_ext_status = build_header()

        self.page_compat = PageCompat()
        self.prg_compat = ProgressBarCompat(on_visible_change=self._on_prg_visible)
        self.txt_proximo_compat = TextCompat(on_value_change=self._on_txt_proximo_change)
        self.dropdown_ref_compat = DropdownCompat(default_value="ingredients")

        self.panel_proyecto, _, self.refrescar_canales, _ = build_panel_proyecto(
            None,
            self.state,
            on_ruta_cambiada=self._actualizar_txt_proximo,
        )
        (
            self.panel_prompts,
            self.obtener_prompts_para_ejecucion,
            self.actualizar_resumen_alcance,
        ) = build_panel_prompts(
            None,
            self.state,
            on_alcance_cambiado=self._sync_boton_ejecutar,
        )
        self.panel_tts, _ = build_panel_tts(None, self.state, self.log_msg)
        self.panel_whisperx, _ = build_panel_whisperx(None, self.state)
        self.panel_ai_studio, _ = build_panel_ai_studio(None, self.state)
        (
            self.panel_flow,
            _,
            self.actualizar_estado_imagen,
            self.refrescar_journeys_ui,
            self.lbl_imagen_status_sidebar,
            self._get_ref_mode,
        ) = build_panel_flow(None, self.state, self.log_msg)

        self.dropdown_ref_compat.set_combo(_RefModeComboProxy(self._get_ref_mode))

        self.prg_bar = QProgressBar()
        self.prg_bar.setRange(0, 0)
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
            self.panel_proyecto,
            self.panel_prompts,
            self.panel_tts,
            self.panel_whisperx,
            self.panel_ai_studio,
            self.panel_flow,
        ]:
            vbox_izq.addWidget(panel)
        vbox_izq.addStretch()

        scroll_izq = QScrollArea()
        scroll_izq.setWidget(col_izq_inner)
        scroll_izq.setWidgetResizable(True)
        scroll_izq.setFixedWidth(440)
        scroll_izq.setFrameShape(QFrame.Shape.NoFrame)

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
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setStyleSheet("color:#E2E8F0;")
            return separator

        for widget in [
            lbl_pipeline,
            _sep(),
            self.lbl_proximo,
            _sep(),
            self.btn_ejecutar,
            self.lbl_alcance,
            self.btn_detener,
            self.prg_bar,
            _sep(),
            lbl_estado_flujo,
            self.tracker_widget,
        ]:
            vbox_central.addWidget(widget)
        vbox_central.addStretch()

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

        def _sep_v():
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.VLine)
            separator.setStyleSheet("color:#E2E8F0;")
            return separator

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

    def _connect_ws_bridge(self):
        ws_bridge.ui_log_cb = self.log_msg
        ws_bridge.ui_ext_status_cb = self.actualizar_ext_status
        ws_bridge.ui_image_status_cb = self.actualizar_estado_imagen
        ws_bridge.ui_update_journeys_cb = self.refrescar_journeys_ui

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

    def _actualizar_txt_proximo(self, ruta):
        self.txt_proximo_compat.value = f"Próximo Proyecto: video {obtener_siguiente_num(ruta)}"

    def _on_txt_proximo_change(self, texto):
        self.lbl_proximo.setText(texto)

    def _on_prg_visible(self, visible):
        self.prg_bar.setVisible(visible)

    def _sync_boton_ejecutar(self, texto_boton, descripcion):
        if hasattr(self, "btn_ejecutar"):
            self.btn_ejecutar.setText(texto_boton)
        if hasattr(self, "lbl_alcance"):
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
            stop_event=self.state.stop_event,
            log_msg=self.log_msg,
            ruta_base=self.state.ruta_base,
            prompts_lista=self.state.prompts_lista,
            tts_config=self.state.tts_config,
            whisperx_config=self.state.whisperx_config,
            config_actual=self.state.config_actual,
            ejecutar_hasta_prompt=self.state.ejecutar_hasta_prompt,
            ref_image_paths_state=self.state.ref_image_paths_state,
            dropdown_ref_mode=self.dropdown_ref_compat,
            prg=self.prg_compat,
            txt_proximo=self.txt_proximo_compat,
            page=self.page_compat,
            set_estado_ejecutando=self._set_estado_ejecutando,
            obtener_prompts_para_ejecucion=self.obtener_prompts_para_ejecucion,
            set_fase_estado=self.set_fase_estado,
            reset_tracker=self.reset_tracker,
        )

        self._flow_worker = _FlowWorker(ctx)
        self._flow_worker.finished.connect(self._on_flujo_terminado)
        self._flow_worker.start()

    def _on_flujo_terminado(self):
        self.prg_compat.visible = False
        self._set_estado_ejecutando(False)
        self._flow_worker = None


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())