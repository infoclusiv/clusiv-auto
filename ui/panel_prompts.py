from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import (
    describir_alcance_prompts,
    guardar_config,
    normalizar_ejecutar_hasta_prompt,
    obtener_cortes_validos_prueba,
)


def _make_badge(texto, color_texto, color_fondo, color_borde):
    """Crea un QLabel con estilo de badge/chip redondeado."""
    lbl = QLabel(texto)
    lbl.setStyleSheet(
        f"QLabel {{"
        f"  color: {color_texto};"
        f"  background: {color_fondo};"
        f"  border: 1px solid {color_borde};"
        f"  border-radius: 8px;"
        f"  padding: 2px 7px;"
        f"  font-size: 10px;"
        f"  font-weight: 500;"
        f"}}"
    )
    lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return lbl


def _get_tier_label(val):
    if val >= 301:
        return f"{val} WPM ⚡ Turbo"
    if val >= 121:
        return f"{val} WPM 🏃 Rápido"
    if val >= 51:
        return f"{val} WPM 🚶 Palabra"
    return f"{val} WPM 🐢 Stealth"


class _FocusTextEdit(QTextEdit):
    """QTextEdit que emite focus_lost al perder el foco."""

    focus_lost = pyqtSignal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_lost.emit()


class EditorPromptDialog(QDialog):
    """
    Diálogo modal para editar los campos de un prompt.
    Equivale al ft.AlertDialog de Flet.
    """

    def __init__(self, prompt_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar Prompt: {prompt_data.get('nombre', '')}")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMaximumWidth(600)

        self._data = dict(prompt_data)
        self._build_ui()

    def _build_ui(self):
        prompt_data = self._data
        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        outer.setContentsMargins(16, 16, 16, 16)

        outer.addWidget(QLabel("Nombre:"))
        self.f_nombre = QLineEdit(prompt_data.get("nombre", ""))
        self.f_nombre.setStyleSheet(
            "QLineEdit { border:1px solid #CBD5E0; border-radius:4px; padding:4px 8px; }"
        )
        outer.addWidget(self.f_nombre)

        outer.addWidget(QLabel("Texto del prompt (usa [REF_TITLE] o [TITULO]):"))
        self.f_texto = _FocusTextEdit()
        self.f_texto.setPlainText(prompt_data.get("texto", ""))
        self.f_texto.setMinimumHeight(120)
        self.f_texto.setMaximumHeight(200)
        self.f_texto.setStyleSheet(
            "QTextEdit { border:1px solid #CBD5E0; border-radius:4px;"
            " padding:4px 8px; font-size:12px; }"
        )
        outer.addWidget(self.f_texto)

        row1 = QWidget()
        hrow1 = QHBoxLayout(row1)
        hrow1.setContentsMargins(0, 0, 0, 0)
        hrow1.setSpacing(8)

        col_modo = QWidget()
        vcol_modo = QVBoxLayout(col_modo)
        vcol_modo.setContentsMargins(0, 0, 0, 0)
        vcol_modo.addWidget(QLabel("Modo de ventana:"))
        self.f_modo = QComboBox()
        self.f_modo.addItem("🆕 Nueva ventana", "nueva")
        self.f_modo.addItem("📌 Ventana activa", "activa")
        idx_modo = self.f_modo.findData(prompt_data.get("modo", "nueva"))
        if idx_modo >= 0:
            self.f_modo.setCurrentIndex(idx_modo)
        self.f_modo.setStyleSheet(
            "QComboBox { border:1px solid #CBD5E0; border-radius:4px; padding:4px 8px; }"
        )
        vcol_modo.addWidget(self.f_modo)
        hrow1.addWidget(col_modo)

        col_espera = QWidget()
        vcol_espera = QVBoxLayout(col_espera)
        vcol_espera.setContentsMargins(0, 0, 0, 0)
        vcol_espera.addWidget(QLabel("Espera (segundos):"))
        self.f_espera = QLineEdit(str(prompt_data.get("espera_segundos", 30)))
        self.f_espera.setMaximumWidth(150)
        self.f_espera.setStyleSheet(
            "QLineEdit { border:1px solid #CBD5E0; border-radius:4px; padding:4px 8px; }"
        )
        vcol_espera.addWidget(self.f_espera)
        hrow1.addWidget(col_espera)
        hrow1.addStretch()
        outer.addWidget(row1)

        row2 = QWidget()
        hrow2 = QHBoxLayout(row2)
        hrow2.setContentsMargins(0, 0, 0, 0)
        hrow2.setSpacing(8)

        col_accion = QWidget()
        vcol_accion = QVBoxLayout(col_accion)
        vcol_accion.setContentsMargins(0, 0, 0, 0)
        vcol_accion.addWidget(QLabel("Post-Acción:"))
        self.f_post_accion = QComboBox()
        self.f_post_accion.addItem("📥 Extraer [FINAL_TITLE]", "extraer_titulo")
        self.f_post_accion.addItem("📥 Guardar respuesta completa", "guardar_respuesta")
        self.f_post_accion.addItem("📤 Solo enviar", "solo_enviar")
        idx_accion = self.f_post_accion.findData(prompt_data.get("post_accion", "solo_enviar"))
        if idx_accion >= 0:
            self.f_post_accion.setCurrentIndex(idx_accion)
        self.f_post_accion.setStyleSheet(
            "QComboBox { border:1px solid #CBD5E0; border-radius:4px; padding:4px 8px; }"
        )
        vcol_accion.addWidget(self.f_post_accion)
        hrow2.addWidget(col_accion)

        col_archivo = QWidget()
        vcol_archivo = QVBoxLayout(col_archivo)
        vcol_archivo.setContentsMargins(0, 0, 0, 0)
        vcol_archivo.addWidget(QLabel("Archivo de salida:"))
        self.f_archivo = QLineEdit(prompt_data.get("archivo_salida", ""))
        self.f_archivo.setStyleSheet(
            "QLineEdit { border:1px solid #CBD5E0; border-radius:4px; padding:4px 8px; }"
        )
        vcol_archivo.addWidget(self.f_archivo)
        hrow2.addWidget(col_archivo)
        outer.addWidget(row2)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #E2E8F0;")
        outer.addWidget(sep)

        antibot_box = QFrame()
        antibot_box.setStyleSheet(
            "QFrame { border:1px solid #81E6D9; border-radius:8px; background:#F0FFF4; }"
        )
        vbox_ab = QVBoxLayout(antibot_box)
        vbox_ab.setContentsMargins(10, 10, 10, 10)
        vbox_ab.setSpacing(6)

        self.f_antibot = QCheckBox(
            "🛡️ Anti-Bot (Escritura humanizada, pausas aleatorias, scroll)"
        )
        self.f_antibot.setChecked(bool(prompt_data.get("antibot", True)))
        self.f_antibot.setStyleSheet("font-size: 12px;")
        vbox_ab.addWidget(self.f_antibot)

        wpm_row = QWidget()
        hbox_wpm = QHBoxLayout(wpm_row)
        hbox_wpm.setContentsMargins(0, 0, 0, 0)
        hbox_wpm.setSpacing(8)

        lbl_vel = QLabel("Velocidad de escritura:")
        lbl_vel.setStyleSheet("font-size: 12px; color: #4A5568;")
        hbox_wpm.addWidget(lbl_vel)

        self.f_wpm_slider = QSlider(Qt.Orientation.Horizontal)
        self.f_wpm_slider.setMinimum(20)
        self.f_wpm_slider.setMaximum(500)
        self.f_wpm_slider.setSingleStep(1)
        self.f_wpm_slider.setPageStep(20)
        self.f_wpm_slider.setValue(prompt_data.get("wpm_escritura", 200))
        self.f_wpm_slider.setStyleSheet(
            "QSlider::groove:horizontal { height:4px; background:#81E6D9; border-radius:2px; }"
            "QSlider::handle:horizontal { background:#319795; width:14px; height:14px;"
            " margin:-5px 0; border-radius:7px; }"
        )
        hbox_wpm.addWidget(self.f_wpm_slider, stretch=1)

        self.f_wpm_label = QLabel(_get_tier_label(prompt_data.get("wpm_escritura", 200)))
        self.f_wpm_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #2C7A7B;"
        )
        self.f_wpm_label.setMinimumWidth(170)
        hbox_wpm.addWidget(self.f_wpm_label)

        self.f_wpm_slider.valueChanged.connect(
            lambda v: self.f_wpm_label.setText(_get_tier_label(v))
        )
        vbox_ab.addWidget(wpm_row)

        lbl_escala = QLabel(
            "🐢 20 ← Stealth | 51 → Palabra 🚶 | 121 → Rápido 🏃 | 301 → Turbo ⚡ → 500"
        )
        lbl_escala.setStyleSheet(
            "font-size: 10px; color: #718096; font-style: italic;"
        )
        lbl_escala.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox_ab.addWidget(lbl_escala)

        outer.addWidget(antibot_box)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        btn_box.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        btn_box.button(QDialogButtonBox.StandardButton.Save).setStyleSheet(
            "QPushButton { background:#276749; color:white; border-radius:6px;"
            " padding:6px 16px; font-weight:bold; }"
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        outer.addWidget(btn_box)

    def get_valores(self) -> dict:
        """Devuelve un dict con los valores editados, listo para actualizar prompts_lista[idx]."""
        try:
            espera = int(self.f_espera.text())
        except ValueError:
            espera = 30
        return {
            "nombre": self.f_nombre.text().strip(),
            "texto": self.f_texto.toPlainText(),
            "modo": self.f_modo.currentData(),
            "espera_segundos": espera,
            "post_accion": self.f_post_accion.currentData(),
            "archivo_salida": self.f_archivo.text().strip(),
            "antibot": self.f_antibot.isChecked(),
            "wpm_escritura": self.f_wpm_slider.value(),
        }


def _crear_tarjeta(idx, p, on_toggle, on_editar, on_subir, on_bajar, on_eliminar, es_primero, es_ultimo):
    """
    Construye el QFrame que representa un prompt en la galería.
    Equivale a la variable `card` en el código Flet original.
    """
    habilitado = p.get("habilitado", True)
    nombre = p.get("nombre", f"Prompt {idx + 1}")
    antibot = p.get("antibot", False)
    wpm = p.get("wpm_escritura", 45)
    modo = p.get("modo", "nueva")
    espera = p.get("espera_segundos", 30)
    accion = p.get("post_accion", "solo_enviar")
    archivo = p.get("archivo_salida", "")

    borde = "#68D391" if habilitado else "#CBD5E0"
    fondo = "white" if habilitado else "#F7FAFC"

    card = QFrame()
    card.setStyleSheet(
        f"QFrame {{ border:1.5px solid {borde}; border-radius:10px;"
        f" background:{fondo}; padding:0px; }}"
    )

    vbox = QVBoxLayout(card)
    vbox.setContentsMargins(12, 10, 12, 10)
    vbox.setSpacing(6)

    row1 = QWidget()
    hrow1 = QHBoxLayout(row1)
    hrow1.setContentsMargins(0, 0, 0, 0)
    hrow1.setSpacing(6)

    lbl_num = QLabel(f"#{idx + 1}")
    lbl_num.setFixedSize(26, 26)
    lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
    num_bg = "#718096" if habilitado else "#A0AEC0"
    lbl_num.setStyleSheet(
        f"QLabel {{ background:{num_bg}; color:white; border-radius:13px;"
        f" font-size:10px; font-weight:bold; }}"
    )
    hrow1.addWidget(lbl_num)

    chk = QCheckBox()
    chk.setChecked(habilitado)
    chk.setFixedWidth(40)
    chk.setStyleSheet(
        "QCheckBox::indicator { width:32px; height:18px; }"
        "QCheckBox::indicator:checked { background:#38A169; border-radius:9px; }"
        "QCheckBox::indicator:unchecked { background:#CBD5E0; border-radius:9px; }"
    )
    chk.stateChanged.connect(lambda state, i=idx: on_toggle(i, state == 2))
    hrow1.addWidget(chk)

    lbl_nombre = QLabel(nombre)
    lbl_nombre.setStyleSheet(
        f"font-weight:bold; font-size:13px;"
        f" color:{'#2D3748' if habilitado else '#A0AEC0'};"
        f" border:none; background:transparent;"
    )
    lbl_nombre.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    hrow1.addWidget(lbl_nombre, stretch=1)
    vbox.addWidget(row1)

    badges_row = QWidget()
    badges_layout = QHBoxLayout(badges_row)
    badges_layout.setContentsMargins(0, 0, 0, 0)
    badges_layout.setSpacing(4)
    badges_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

    if antibot:
        if wpm >= 301:
            tier = "⚡"
        elif wpm >= 121:
            tier = "🏃"
        elif wpm >= 51:
            tier = "🚶"
        else:
            tier = "🐢"
        badges_layout.addWidget(
            _make_badge(f"🛡️ {wpm} WPM {tier}", "#285E61", "#E6FFFA", "#81E6D9")
        )

    modo_txt = "🆕 Nueva" if modo == "nueva" else "📌 Activa"
    badges_layout.addWidget(_make_badge(modo_txt, "#2C5282", "#EBF8FF", "#90CDF4"))
    badges_layout.addWidget(_make_badge(f"⏳ {espera}s", "#7B341E", "#FFFAF0", "#FBD38D"))

    if accion == "extraer_titulo":
        badges_layout.addWidget(_make_badge("📥 Título", "#553C9A", "#FAF5FF", "#D6BCFA"))
    elif accion == "guardar_respuesta":
        badges_layout.addWidget(_make_badge("📥 Respuesta", "#553C9A", "#FAF5FF", "#D6BCFA"))

    badges_layout.addStretch()
    vbox.addWidget(badges_row)

    if archivo:
        lbl_archivo = QLabel(f"💾 {archivo}")
        lbl_archivo.setStyleSheet(
            "font-size:10px; color:#718096; font-style:italic; border:none; background:transparent;"
        )
        vbox.addWidget(lbl_archivo)

    btn_row = QWidget()
    hbtn = QHBoxLayout(btn_row)
    hbtn.setContentsMargins(0, 0, 0, 0)
    hbtn.setSpacing(0)
    hbtn.addStretch()

    def _icon_btn(emoji, tooltip, callback, disabled=False):
        button = QPushButton(emoji)
        button.setToolTip(tooltip)
        button.setFixedSize(28, 28)
        button.setEnabled(not disabled)
        button.setStyleSheet(
            "QPushButton { border:none; background:transparent; font-size:14px; }"
            "QPushButton:hover { background:#EDF2F7; border-radius:4px; }"
            "QPushButton:disabled { color:#CBD5E0; }"
        )
        button.clicked.connect(callback)
        return button

    hbtn.addWidget(_icon_btn("✏️", "Editar", lambda _, i=idx: on_editar(i)))
    hbtn.addWidget(_icon_btn("⬆️", "Subir", lambda _, i=idx: on_subir(i), disabled=es_primero))
    hbtn.addWidget(_icon_btn("⬇️", "Bajar", lambda _, i=idx: on_bajar(i), disabled=es_ultimo))
    hbtn.addWidget(_icon_btn("🗑️", "Eliminar", lambda _, i=idx: on_eliminar(i)))

    vbox.addWidget(btn_row)
    return card


def build_panel_prompts(_page=None, state=None, on_alcance_cambiado=None):
    """
    Panel de Prompts -> ChatGPT.

    Parámetros
    ----------
    _page              : ignorado (compatibilidad con firma Flet)
    state              : AppState
    on_alcance_cambiado: callable(texto_boton: str, descripcion: str)

    Retorna
    -------
    (widget: QGroupBox,
     obtener_prompts_para_ejecucion: callable,
     actualizar_resumen_alcance: callable)
    """
    prompts_lista = state.prompts_lista
    ejecutar_hasta_prompt = state.ejecutar_hasta_prompt
    config_actual = state.config_actual

    group = QGroupBox("💬 Prompts → ChatGPT")
    group.setCheckable(True)
    group.setChecked(False)
    group.setStyleSheet(
        "QGroupBox { font-weight:bold; font-size:13px; margin-top:6px; }"
        "QGroupBox::title { subcontrol-origin:margin; left:8px; }"
    )

    outer = QVBoxLayout(group)
    outer.setContentsMargins(8, 12, 8, 8)
    outer.setSpacing(8)

    toolbar = QWidget()
    htool = QHBoxLayout(toolbar)
    htool.setContentsMargins(0, 0, 0, 0)
    htool.setSpacing(6)

    lbl_count = QLabel(f"{len(prompts_lista)} prompts")
    lbl_count.setStyleSheet("font-size:12px; color:#718096; font-style:italic;")
    htool.addWidget(lbl_count)
    htool.addStretch()

    btn_style_outline = (
        "QPushButton { border:1px solid #CBD5E0; background:white; border-radius:6px;"
        " padding:4px 10px; font-size:12px; }"
        "QPushButton:hover { background:#F7FAFC; }"
    )
    btn_style_purple = (
        "QPushButton { background:#6B46C1; color:white; border-radius:6px;"
        " padding:4px 10px; font-size:12px; font-weight:bold; }"
        "QPushButton:hover { background:#553C9A; }"
    )

    btn_desactivar = QPushButton("⊘  Desactivar todos")
    btn_desactivar.setStyleSheet(btn_style_outline)
    htool.addWidget(btn_desactivar)

    btn_activar = QPushButton("✔  Activar todos")
    btn_activar.setStyleSheet(btn_style_outline)
    htool.addWidget(btn_activar)

    btn_agregar = QPushButton("➕  Agregar Prompt")
    btn_agregar.setStyleSheet(btn_style_purple)
    htool.addWidget(btn_agregar)

    outer.addWidget(toolbar)

    sep1 = QFrame()
    sep1.setFrameShape(QFrame.Shape.HLine)
    sep1.setStyleSheet("color:#E2E8F0;")
    outer.addWidget(sep1)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setMinimumHeight(0)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea { border:none; }")

    galeria_container = QWidget()
    galeria_layout = QVBoxLayout(galeria_container)
    galeria_layout.setContentsMargins(4, 4, 4, 4)
    galeria_layout.setSpacing(8)
    galeria_layout.addStretch()

    scroll.setWidget(galeria_container)
    outer.addWidget(scroll)

    sep2 = QFrame()
    sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setStyleSheet("color:#E2E8F0;")
    outer.addWidget(sep2)

    lbl_alcance_titulo = QLabel("⏩  Alcance de prueba")
    lbl_alcance_titulo.setStyleSheet("font-size:12px; font-weight:bold; color:#2D3748;")
    outer.addWidget(lbl_alcance_titulo)

    combo_alcance = QComboBox()
    combo_alcance.setStyleSheet(
        "QComboBox { border:1px solid #CBD5E0; border-radius:4px; padding:4px 8px; font-size:12px; }"
    )
    outer.addWidget(combo_alcance)

    lbl_alcance_nota = QLabel(
        "La prueba siempre corre desde el prompt 1 y solo permite cortes en prompts de teleprompter."
    )
    lbl_alcance_nota.setWordWrap(True)
    lbl_alcance_nota.setStyleSheet("font-size:11px; color:#718096; font-style:italic;")
    outer.addWidget(lbl_alcance_nota)

    btn_guardar_alcance = QPushButton("💾  Guardar alcance")
    btn_guardar_alcance.setStyleSheet(
        "QPushButton { background:#C05621; color:white; border-radius:6px;"
        " padding:6px 12px; font-size:12px; font-weight:bold; }"
        "QPushButton:hover { background:#9C4221; }"
    )
    outer.addWidget(btn_guardar_alcance)

    def guardar_prompts():
        ejecutar_hasta_prompt[0] = normalizar_ejecutar_hasta_prompt(
            ejecutar_hasta_prompt[0], prompts_lista
        )
        config_actual["ejecutar_hasta_prompt"] = ejecutar_hasta_prompt[0]
        guardar_config(
            prompts=prompts_lista,
            ejecutar_hasta_prompt=ejecutar_hasta_prompt[0],
        )
        actualizar_selector_ejecucion()
        actualizar_resumen_alcance()

    def obtener_prompts_para_ejecucion():
        limite = normalizar_ejecutar_hasta_prompt(ejecutar_hasta_prompt[0], prompts_lista)
        ejecutar_hasta_prompt[0] = limite
        config_actual["ejecutar_hasta_prompt"] = limite
        if limite == 0:
            return list(prompts_lista), len(prompts_lista)
        return list(prompts_lista[:limite]), limite

    def actualizar_resumen_alcance():
        descripcion = describir_alcance_prompts(prompts_lista, ejecutar_hasta_prompt[0])
        limite = normalizar_ejecutar_hasta_prompt(ejecutar_hasta_prompt[0], prompts_lista)
        texto_boton = "EJECUTAR FLUJO COMPLETO" if limite == 0 else f"EJECUTAR FLUJO 1-{limite}"
        if on_alcance_cambiado:
            on_alcance_cambiado(texto_boton, descripcion)

    def actualizar_selector_ejecucion():
        total = len(prompts_lista)
        valor_actual = normalizar_ejecutar_hasta_prompt(
            ejecutar_hasta_prompt[0], prompts_lista
        )
        ejecutar_hasta_prompt[0] = valor_actual
        config_actual["ejecutar_hasta_prompt"] = valor_actual

        combo_alcance.blockSignals(True)
        combo_alcance.clear()
        combo_alcance.addItem(
            f"Flujo completo (1-{total})" if total else "Flujo completo", "0"
        )
        for corte in obtener_cortes_validos_prueba(prompts_lista):
            if corte >= total:
                continue
            nombre_corte = prompts_lista[corte - 1].get("nombre", f"Prompt {corte}")
            combo_alcance.addItem(f"Prueba 1-{corte} · {nombre_corte}", str(corte))

        idx_sel = combo_alcance.findData(str(valor_actual))
        combo_alcance.setCurrentIndex(max(0, idx_sel))
        combo_alcance.blockSignals(False)

    def persistir_alcance_ejecucion():
        valor_str = combo_alcance.currentData() or "0"
        ejecutar_hasta_prompt[0] = normalizar_ejecutar_hasta_prompt(
            valor_str, prompts_lista
        )
        config_actual["ejecutar_hasta_prompt"] = ejecutar_hasta_prompt[0]
        guardar_config(ejecutar_hasta_prompt=ejecutar_hasta_prompt[0])
        actualizar_selector_ejecucion()
        actualizar_resumen_alcance()

    def refrescar_prompts():
        while galeria_layout.count() > 1:
            item = galeria_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        lbl_count.setText(f"{len(prompts_lista)} prompts")
        total = len(prompts_lista)

        for idx, prompt in enumerate(prompts_lista):
            tarjeta = _crear_tarjeta(
                idx,
                prompt,
                on_toggle=toggle_prompt,
                on_editar=abrir_editor_prompt,
                on_subir=lambda i: mover_prompt(i, -1),
                on_bajar=lambda i: mover_prompt(i, 1),
                on_eliminar=eliminar_prompt,
                es_primero=(idx == 0),
                es_ultimo=(idx == total - 1),
            )
            galeria_layout.insertWidget(galeria_layout.count() - 1, tarjeta)

    def toggle_prompt(idx, valor):
        prompts_lista[idx]["habilitado"] = valor
        guardar_prompts()
        refrescar_prompts()

    def deshabilitar_todos():
        for prompt in prompts_lista:
            prompt["habilitado"] = False
        guardar_prompts()
        refrescar_prompts()

    def habilitar_todos():
        for prompt in prompts_lista:
            prompt["habilitado"] = True
        guardar_prompts()
        refrescar_prompts()

    def mover_prompt(idx, direccion):
        nuevo_idx = idx + direccion
        if 0 <= nuevo_idx < len(prompts_lista):
            prompts_lista[idx], prompts_lista[nuevo_idx] = (
                prompts_lista[nuevo_idx],
                prompts_lista[idx],
            )
            guardar_prompts()
            refrescar_prompts()

    def eliminar_prompt(idx):
        prompts_lista.pop(idx)
        guardar_prompts()
        refrescar_prompts()

    def agregar_prompt_nuevo():
        nuevo = {
            "nombre": f"Nuevo Prompt {len(prompts_lista) + 1}",
            "texto": "",
            "modo": "nueva",
            "espera_segundos": 30,
            "habilitado": True,
            "antibot": True,
            "wpm_escritura": 200,
            "post_accion": "solo_enviar",
            "archivo_salida": "",
        }
        prompts_lista.append(nuevo)
        guardar_prompts()
        refrescar_prompts()
        abrir_editor_prompt(len(prompts_lista) - 1)

    def abrir_editor_prompt(idx):
        dlg = EditorPromptDialog(prompts_lista[idx], parent=group)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            prompts_lista[idx].update(dlg.get_valores())
            guardar_prompts()
            refrescar_prompts()

    btn_desactivar.clicked.connect(deshabilitar_todos)
    btn_activar.clicked.connect(habilitar_todos)
    btn_agregar.clicked.connect(agregar_prompt_nuevo)
    combo_alcance.currentIndexChanged.connect(lambda _: persistir_alcance_ejecucion())
    btn_guardar_alcance.clicked.connect(persistir_alcance_ejecucion)

    actualizar_selector_ejecucion()
    actualizar_resumen_alcance()
    refrescar_prompts()

    return group, obtener_prompts_para_ejecucion, actualizar_resumen_alcance