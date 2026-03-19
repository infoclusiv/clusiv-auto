"""
antibot.py
----------
Funciones de escritura humanizada y esperas aleatorias para evitar
detección de automatización en interfaces web (ChatGPT, AI Studio, etc.).

Tiers de escritura según WPM:
  20-50  WPM → Carácter por carácter (_escribir_caracter)
  51-120 WPM → Palabra por palabra via clipboard (_escribir_por_palabras)
  121-300 WPM → Chunks de líneas via clipboard (_escribir_por_chunks_linea)
  301-500 WPM → Paste directo con micro-pausa (_escribir_paste_directo)

Funciones públicas:
  escribir_humanizado(texto, wpm, stop_event) → bool
  espera_humanizada(segundos, stop_event)     → bool
  scroll_simulado(stop_event)                 → bool
  sleep_cancelable(segundos, stop_event)      → bool
"""

import re
import time
import random

import pyautogui
import pyperclip


# ---------------------------------------------------------------------------
# Router principal
# ---------------------------------------------------------------------------

def escribir_humanizado(texto, wpm=45, stop_event=None):
    """Router principal de escritura. Selecciona estrategia según WPM.

    Tiers:
      20-50  WPM → Carácter por carácter (máximo stealth)
      51-120 WPM → Palabra por palabra via clipboard
      121-300 WPM → Chunks de líneas via clipboard
      301-500 WPM → Paste directo con micro-pausa
    """
    if wpm >= 301:
        return _escribir_paste_directo(texto, stop_event)
    elif wpm >= 121:
        return _escribir_por_chunks_linea(texto, wpm, stop_event)
    elif wpm >= 51:
        return _escribir_por_palabras(texto, wpm, stop_event)
    else:
        return _escribir_caracter(texto, wpm, stop_event)


# ---------------------------------------------------------------------------
# Implementaciones por tier (privadas)
# ---------------------------------------------------------------------------

def _escribir_caracter(texto, wpm=45, stop_event=None):
    """Tier 🐢 Stealth (20-50 WPM): Carácter por carácter.
    Multiplicadores REDUCIDOS vs la versión original para que sea más fiel al WPM real."""
    wpm_real = wpm * random.uniform(0.9, 1.1)
    base_delay = 60.0 / (wpm_real * 5)
    for char in texto:
        if stop_event and stop_event.is_set():
            return False
        if char == " ":
            time.sleep(random.uniform(base_delay * 1.0, base_delay * 1.5))
            pyautogui.press("space")
        elif char == "\n":
            time.sleep(random.uniform(base_delay * 1.2, base_delay * 2.0))
            pyautogui.press("enter")
        elif char == "\t":
            time.sleep(random.uniform(base_delay * 0.3, base_delay * 0.6))
            pyautogui.press("tab")
        else:
            time.sleep(random.uniform(base_delay * 0.6, base_delay * 1.1))
            if char.isascii() and char.isprintable():
                pyautogui.typewrite(char, interval=0)
            else:
                try:
                    pyperclip.copy(char)
                    pyautogui.hotkey("ctrl", "v")
                except Exception:
                    pass
    return True


def _escribir_por_palabras(texto, wpm=80, stop_event=None):
    """Tier 🚶 Normal (51-120 WPM): Palabra por palabra via clipboard.
    Cada palabra se pega con Ctrl+V, luego espacio/newline se teclea manual.
    Mucho más rápido que char-by-char porque clipboard es instantáneo."""

    tokens = re.split(r"(\s)", texto)
    palabra_delay = 60.0 / wpm

    for token in tokens:
        if stop_event and stop_event.is_set():
            return False

        if token == "":
            continue
        elif token == " ":
            time.sleep(random.uniform(palabra_delay * 0.1, palabra_delay * 0.3))
            pyautogui.press("space")
        elif token == "\n":
            time.sleep(random.uniform(palabra_delay * 0.2, palabra_delay * 0.5))
            pyautogui.press("enter")
        elif token == "\t":
            time.sleep(random.uniform(palabra_delay * 0.05, palabra_delay * 0.15))
            pyautogui.press("tab")
        elif token.strip() == "":
            for ch in token:
                if stop_event and stop_event.is_set():
                    return False
                pyautogui.press("space")
                time.sleep(random.uniform(0.01, 0.05))
        else:
            time.sleep(random.uniform(palabra_delay * 0.3, palabra_delay * 0.8))
            pyperclip.copy(token)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(random.uniform(0.02, 0.06))

    return True


def _escribir_por_chunks_linea(texto, wpm=200, stop_event=None):
    """Tier 🏃 Rápido (121-300 WPM): Chunks de líneas/frases via clipboard.
    Pega líneas completas con pausas breves entre ellas."""

    lineas = texto.split("\n")
    line_delay = max(0.05, 60.0 / wpm)

    for i, linea in enumerate(lineas):
        if stop_event and stop_event.is_set():
            return False

        if linea:
            pyperclip.copy(linea)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(random.uniform(0.02, 0.08))

        if i < len(lineas) - 1:
            time.sleep(random.uniform(line_delay * 0.5, line_delay * 1.2))
            pyautogui.press("enter")

    return True


def _escribir_paste_directo(texto, stop_event=None):
    """Tier ⚡ Turbo (301-500 WPM): Paste directo completo.
    Pega todo el texto de una vez. Máxima velocidad, mínimo stealth."""
    if stop_event and stop_event.is_set():
        return False

    pyperclip.copy(texto)
    time.sleep(random.uniform(0.1, 0.3))
    pyautogui.hotkey("ctrl", "v")
    time.sleep(random.uniform(0.1, 0.3))

    return True


# ---------------------------------------------------------------------------
# Utilidades de espera y comportamiento
# ---------------------------------------------------------------------------

def espera_humanizada(segundos, stop_event=None):
    """Espera con variación aleatoria ±20% y decimales.
    Fragmenta la espera en intervalos de 0.5s para permitir cancelación."""
    total = random.uniform(segundos * 0.8, segundos * 1.2)
    elapsed = 0.0
    while elapsed < total:
        if stop_event and stop_event.is_set():
            return False
        chunk = min(0.5, total - elapsed)
        time.sleep(chunk)
        elapsed += chunk
    return True


def scroll_simulado(stop_event=None):
    """Simula scroll aleatorio de lectura/atención.
    Se detiene si stop_event está activado."""
    veces = random.randint(1, 3)
    for _ in range(veces):
        if stop_event and stop_event.is_set():
            return False
        pyautogui.scroll(random.choice([-3, -2, -1, 1, 2, 3]))
        time.sleep(random.uniform(0.3, 0.8))
    return True


def sleep_cancelable(segundos, stop_event=None):
    """time.sleep fragmentado que permite cancelación."""
    elapsed = 0.0
    while elapsed < segundos:
        if stop_event and stop_event.is_set():
            return False
        chunk = min(0.5, segundos - elapsed)
        time.sleep(chunk)
        elapsed += chunk
    return True