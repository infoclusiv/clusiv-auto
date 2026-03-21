from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


def build_header(_page=None):
    """
    Construye la barra de cabecera con titulo y estado de la extension Chrome.

    Parametros
    ----------
    _page : ignorado - se mantiene para compatibilidad con la firma Flet.

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
        QTimer.singleShot(0, lambda: _actualizar_en_hilo_principal(conectada, version))

    return widget, actualizar_ext_status_header