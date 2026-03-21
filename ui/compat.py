"""
Adaptadores de compatibilidad Flet -> PyQt6 para FlowContext.
Imitan la interfaz de widgets Flet sin importar Flet.
"""
from PyQt6.QtWidgets import QApplication


class PageCompat:
    """Reemplaza ft.Page. page.update() -> processEvents() para no bloquear la UI."""

    controls = []

    def update(self):
        QApplication.processEvents()


class ProgressBarCompat:
    """
    Reemplaza ft.ProgressBar.
    Asignar .visible dispara el callback on_visible_change(bool).
    """

    def __init__(self, on_visible_change=None):
        self._visible = False
        self._cb = on_visible_change

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        self._visible = bool(value)
        if self._cb:
            self._cb(self._visible)


class TextCompat:
    """
    Reemplaza ft.Text.
    Asignar .value dispara el callback on_value_change(str).
    """

    def __init__(self, initial_value: str = "", on_value_change=None):
        self._value = initial_value
        self._cb = on_value_change

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value: str):
        self._value = str(value)
        if self._cb:
            self._cb(self._value)


class DropdownCompat:
    """
    Reemplaza ft.Dropdown para dropdown_ref_mode.
    Se enlaza a un QComboBox real mediante set_combo().
    .value devuelve el texto/dato del item seleccionado actualmente.
    """

    def __init__(self, default_value: str = "ingredients"):
        self._default = default_value
        self._combo = None

    def set_combo(self, combo_box):
        """Llamar justo despues de crear el QComboBox para enlazarlo."""
        self._combo = combo_box

    @property
    def value(self):
        if self._combo is not None:
            data = self._combo.currentData()
            return data if data is not None else self._combo.currentText()
        return self._default

    @value.setter
    def value(self, value: str):
        self._default = value
        if self._combo is not None:
            index = self._combo.findData(value)
            if index >= 0:
                self._combo.setCurrentIndex(index)