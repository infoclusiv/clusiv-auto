import os

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
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


class _EnvioPromptsWorker(QThread):
    resultado = pyqtSignal(bool, str)
    estado = pyqtSignal(str, str)

    def __init__(self, ruta_txt, modelo, aspect_ratio, count, ref_paths, ref_mode, project_folder):
        super().__init__()
        self._ruta_txt = ruta_txt
        self._modelo = modelo
        self._aspect_ratio = aspect_ratio
        self._count = count
        self._ref_paths = ref_paths
        self._ref_mode = ref_mode
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
    ai_studio_config = state.ai_studio_config
    config_actual = state.config_actual
    ref_image_paths_state = state.ref_image_paths_state
    ruta_base = state.ruta_base

    worker_ref = [None]

    status_colors = {
        "blue700": "#2B6CB0",
        "blue800": "#2C5282",
        "teal700": "#2C7A7B",
        "red700": "#C53030",
        "green700": "#276749",
        "grey500": "#A0AEC0",
    }

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
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #E2E8F0;")
        return separator

    def _lbl_section(texto):
        label = QLabel(texto)
        label.setStyleSheet("font-size: 12px; font-weight: bold; color: #4A5568;")
        return label

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
    combo_model.addItem("Imagen 4", "imagen4")
    combo_model.addItem("NB 2", "nano_banana2")
    combo_model.addItem("NB Pro", "nano_banana_pro")
    _set_combo_by_data(combo_model, ai_studio_config.get("imagen_model", "imagen4"))
    hbox_mc.addWidget(combo_model, stretch=1)

    combo_count = QComboBox()
    combo_count.setStyleSheet(_combo_style())
    for value, text in [("1", "1x"), ("2", "2x"), ("3", "3x"), ("4", "4x")]:
        combo_count.addItem(text, value)
    _set_combo_by_data(combo_count, str(ai_studio_config.get("imagen_count", 1)))
    hbox_mc.addWidget(combo_count, stretch=1)
    outer.addWidget(row_model_count)

    combo_aspect = QComboBox()
    combo_aspect.setStyleSheet(_combo_style())
    combo_aspect.addItem("16:9 Landscape", "landscape")
    combo_aspect.addItem("9:16 Portrait", "portrait")
    _set_combo_by_data(combo_aspect, ai_studio_config.get("imagen_aspect_ratio", "landscape"))
    outer.addWidget(combo_aspect)

    def persistir_imagen_config():
        ai_studio_config["auto_send_to_extension"] = chk_auto_send.isChecked()
        ai_studio_config["imagen_model"] = combo_model.currentData() or "imagen4"
        ai_studio_config["imagen_aspect_ratio"] = combo_aspect.currentData() or "landscape"
        ai_studio_config["imagen_count"] = combo_count.currentData() or "1"

        normalizado = normalizar_ai_studio_config(ai_studio_config)
        ai_studio_config.update(normalizado)
        config_actual["ai_studio"] = dict(ai_studio_config)
        config_actual["prompt_ai_studio"] = ai_studio_config["prompt"]
        guardar_config(ai_studio=ai_studio_config)

    chk_auto_send.stateChanged.connect(lambda _: persistir_imagen_config())
    combo_model.currentIndexChanged.connect(lambda _: persistir_imagen_config())
    combo_aspect.currentIndexChanged.connect(lambda _: persistir_imagen_config())
    combo_count.currentIndexChanged.connect(lambda _: persistir_imagen_config())

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
            nombres = ", ".join(os.path.basename(path) for path in ref_image_paths_state)
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
        for archivo in archivos:
            if archivo not in ref_image_paths_state:
                ref_image_paths_state.append(archivo)
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

    outer.addWidget(_sep())

    lbl_status = QLabel("Estado: esperando...")
    lbl_status.setStyleSheet("font-size: 11px; color: #A0AEC0; font-style: italic;")
    lbl_status.setWordWrap(True)
    outer.addWidget(lbl_status)

    lbl_imagen_status_sidebar = QLabel("Estado: esperando...")
    lbl_imagen_status_sidebar.setStyleSheet(
        "font-size: 11px; color: #A0AEC0; font-style: italic;"
    )

    def actualizar_estado_imagen(texto, color=None):
        color_hex = status_colors.get(
            str(color).lower().replace("_", "").replace(".", ""),
            "#A0AEC0",
        )

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
        worker_ref[0] = worker

        worker.estado.connect(lambda txt, col: actualizar_estado_imagen(txt, col))
        worker.resultado.connect(
            lambda ok, msg: (
                log_msg(
                    f"{'✅' if ok else '❌'} Imágenes: {msg}",
                    color="green700" if ok else "red700",
                ) if log_msg else None,
                btn_enviar.setEnabled(True),
                worker_ref.__setitem__(0, None),
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
            prev_primary = combo_journeys.currentData()
            prev_secondary = combo_second_journey.currentData()
            valid_ids = {journey["id"] for journey in ws_bridge.available_journeys}

            combo_journeys.blockSignals(True)
            combo_second_journey.blockSignals(True)
            combo_journeys.clear()
            combo_second_journey.clear()

            for journey in ws_bridge.available_journeys:
                combo_journeys.addItem(journey["name"], journey["id"])
                combo_second_journey.addItem(journey["name"], journey["id"])

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
        with open(script_path, "r", encoding="utf-8") as file_handle:
            return file_handle.read(), None

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

    _actualizar_label_ref_images()

    def get_ref_mode():
        return combo_ref_mode.currentData() or "ingredients"

    return (
        group,
        None,
        actualizar_estado_imagen,
        refrescar_journeys_ui,
        lbl_imagen_status_sidebar,
        get_ref_mode,
    )


def _set_combo_by_data(combo, data_value):
    """Selecciona el item del QComboBox cuyo data() coincida con data_value."""
    idx = combo.findData(data_value)
    if idx >= 0:
        combo.setCurrentIndex(idx)