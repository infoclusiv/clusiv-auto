from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import guardar_config
from database import agregar_canal_db, eliminar_canal_db, obtener_canales_db


def build_panel_proyecto(_page=None, state=None, on_ruta_cambiada=None):
    """
    Panel de Proyecto & Canales YouTube.

    Retorna
    -------
    (widget: QGroupBox, None, refrescar_canales: callable, None)
    El segundo valor era ft.FilePicker - ya no aplica en PyQt6.
    """

    group = QGroupBox("📁 Proyecto & Canales YouTube")
    group.setCheckable(True)
    group.setChecked(True)
    group.setStyleSheet(
        "QGroupBox { font-weight: bold; font-size: 13px; margin-top: 6px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
    )

    outer = QVBoxLayout(group)
    outer.setContentsMargins(8, 12, 8, 8)
    outer.setSpacing(8)

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

    sep1 = QFrame()
    sep1.setFrameShape(QFrame.Shape.HLine)
    sep1.setStyleSheet("color: #E2E8F0;")
    outer.addWidget(sep1)

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

    sep2 = QFrame()
    sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setStyleSheet("color: #E2E8F0;")

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)

    lista_container = QWidget()
    lista_layout = QVBoxLayout(lista_container)
    lista_layout.setContentsMargins(0, 0, 0, 0)
    lista_layout.setSpacing(6)
    lista_layout.addStretch()

    scroll.setWidget(lista_container)

    def refrescar_canales():
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
