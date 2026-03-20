"""
tts_nvidia.py
-------------
Pipeline completo de síntesis de voz (Text-to-Speech) con NVIDIA Riva
y transcripción automática con WhisperX.

Flujo principal:
  sintetizar_script_a_audio_nvidia()
    - Intenta usar riva.client directamente (gRPC)
    - Si ImportError -> sintetizar_script_a_audio_nvidia_via_standalone()
                           -> Lanza test_nvidia_tts.py como subproceso

Funciones públicas:
  sintetizar_script_a_audio_nvidia(carpeta_proyecto, tts_config)
      -> tuple[bool, str, str | None]
  transcribir_audio_whisperx(ruta_audio, whisperx_config)
      -> tuple[bool, str, str | None]

Funciones internas (usadas solo dentro de este módulo):
  validar_texto_para_tts(texto)
  dividir_texto_para_tts(texto, max_chars)
  guardar_audio_pcm_como_wav(ruta_salida, audio_pcm, sample_rate_hz, silencio_ms)
  resolver_python_para_tts()
  sintetizar_script_a_audio_nvidia_via_standalone(carpeta_proyecto, tts_config)
"""

import json
import os
import re
import subprocess
import sys
import wave

from config import (
    NVIDIA_API_KEY,
    NVIDIA_GRPC_MAX_MESSAGE_BYTES,
    NVIDIA_MAGPIE_TTS_FUNCTION_ID,
    NVIDIA_TTS_SERVER,
    normalizar_tts_config,
)


def validar_texto_para_tts(texto):
    texto_limpio = (texto or "").strip()
    if not texto_limpio:
        return False, "script.txt está vacío."
    if len(texto_limpio) < 40:
        return False, "script.txt es demasiado corto para sintetizar audio útil."

    artefactos = [
        "your full script here",
        "do not write anything after",
        "do not write anything before",
        "<<<start_teleprompter_script>>>",
        "<<<end_teleprompter_script>>>",
    ]
    texto_lower = texto_limpio.lower()
    for artefacto in artefactos:
        if artefacto in texto_lower:
            return False, "script.txt todavía contiene artefactos del prompt."

    return True, None


def dividir_texto_para_tts(texto, max_chars=1400):
    bloques = []
    actual = ""

    def agregar_bloque(segmento):
        nonlocal actual
        segmento = segmento.strip()
        if not segmento:
            return
        separador = "\n\n" if actual else ""
        if len(actual) + len(separador) + len(segmento) <= max_chars:
            actual = f"{actual}{separador}{segmento}"
        else:
            if actual:
                bloques.append(actual.strip())
            actual = segmento

    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]

    for parrafo in parrafos:
        if len(parrafo) <= max_chars:
            agregar_bloque(parrafo)
            continue

        frases = re.split(r"(?<=[.!?])\s+", parrafo)
        frase_actual = ""
        for frase in frases:
            frase = frase.strip()
            if not frase:
                continue
            separador = " " if frase_actual else ""
            if len(frase_actual) + len(separador) + len(frase) <= max_chars:
                frase_actual = f"{frase_actual}{separador}{frase}"
                continue

            if frase_actual:
                agregar_bloque(frase_actual)
                frase_actual = ""

            if len(frase) <= max_chars:
                frase_actual = frase
                continue

            palabras = frase.split()
            segmento = ""
            for palabra in palabras:
                separador_palabra = " " if segmento else ""
                if len(segmento) + len(separador_palabra) + len(palabra) <= max_chars:
                    segmento = f"{segmento}{separador_palabra}{palabra}"
                else:
                    agregar_bloque(segmento)
                    segmento = palabra
            if segmento:
                agregar_bloque(segmento)

        if frase_actual:
            agregar_bloque(frase_actual)

    if actual:
        bloques.append(actual.strip())

    return bloques or [texto.strip()]


def guardar_audio_pcm_como_wav(ruta_salida, audio_pcm, sample_rate_hz, silencio_ms=250):
    silencio_frames = int(sample_rate_hz * (silencio_ms / 1000.0))
    silencio = b"\x00\x00" * silencio_frames

    with wave.open(ruta_salida, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)

        total = len(audio_pcm)
        for idx, chunk in enumerate(audio_pcm):
            wav_file.writeframes(chunk)
            if idx < total - 1 and silencio:
                wav_file.writeframes(silencio)


def resolver_python_para_tts():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidatos = [
        os.path.join(base_dir, ".venv", "Scripts", "python.exe"),
        os.path.join(base_dir, ".venv", "bin", "python"),
        sys.executable,
    ]

    for candidato in candidatos:
        if candidato and os.path.exists(candidato):
            return candidato

    return sys.executable


def sintetizar_script_a_audio_nvidia_via_standalone(carpeta_proyecto, tts_config):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    python_tts = resolver_python_para_tts()
    script_tts = os.path.join(base_dir, "test_nvidia_tts.py")

    if not os.path.exists(script_tts):
        return False, "No se encontró test_nvidia_tts.py para el fallback TTS.", None

    cmd = [
        python_tts,
        script_tts,
        "--project-dir",
        carpeta_proyecto,
        "--voice",
        tts_config["voice"],
        "--language-code",
        tts_config["language_code"],
        "--output",
        tts_config["output_filename"],
        "--sample-rate-hz",
        str(tts_config["sample_rate_hz"]),
        "--json-output",
    ]

    try:
        resultado = subprocess.run(
            cmd,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as ex:
        return False, f"No se pudo lanzar el fallback TTS: {str(ex)}", None

    salida = (resultado.stdout or "").strip()
    error = (resultado.stderr or "").strip()
    payload = None

    if salida:
        ultima_linea = salida.splitlines()[-1].strip()
        try:
            payload = json.loads(ultima_linea)
        except json.JSONDecodeError:
            payload = None

    if payload:
        return payload.get("ok", False), payload.get("msg", "Sin mensaje"), payload.get("path")

    if resultado.returncode == 0:
        ruta_audio = os.path.join(carpeta_proyecto, tts_config["output_filename"])
        return True, "Audio generado por fallback TTS.", ruta_audio

    detalle = error or salida or "Error desconocido en fallback TTS."
    return False, f"Fallback TTS falló: {detalle}", None


def transcribir_audio_whisperx(ruta_audio, whisperx_config):
    python_path = whisperx_config.get("python_path", "")
    runner_script = whisperx_config.get("runner_script", "whisperx_runner.py")
    model = whisperx_config.get("model", "medium")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    runner_path = os.path.join(base_dir, runner_script)

    if not python_path or not os.path.exists(python_path):
        return False, f"Python de WhisperX no encontrado en: {python_path}. Verifica la ruta en la config.", None

    if not os.path.exists(runner_path):
        return False, f"No se encontró {runner_script} en {base_dir}.", None

    if not ruta_audio or not os.path.exists(ruta_audio):
        return False, f"El archivo de audio no existe: {ruta_audio}", None

    cmd = [
        python_path,
        runner_path,
        "--audio-path",
        ruta_audio,
        "--model",
        model,
        "--json-output",
    ]

    try:
        resultado = subprocess.run(
            cmd,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as ex:
        return False, f"No se pudo lanzar whisperx_runner: {str(ex)}", None

    salida = (resultado.stdout or "").strip()
    error_salida = (resultado.stderr or "").strip()
    payload = None

    if salida:
        ultima_linea = salida.splitlines()[-1].strip()
        try:
            payload = json.loads(ultima_linea)
        except json.JSONDecodeError:
            payload = None

    if payload:
        return payload.get("ok", False), payload.get("msg", "Sin mensaje"), payload.get("path")

    if resultado.returncode == 0:
        ruta_json = os.path.splitext(ruta_audio)[0] + ".json"
        return True, "Transcripción completada (sin payload JSON).", ruta_json

    detalle = error_salida or salida or "Error desconocido en whisperx_runner."
    return False, f"WhisperX falló (código {resultado.returncode}): {detalle}", None


def sintetizar_script_a_audio_nvidia(carpeta_proyecto, tts_config):
    tts_config = normalizar_tts_config(tts_config)

    if tts_config.get("provider") != "nvidia":
        return False, "Proveedor TTS no soportado actualmente.", None

    if not NVIDIA_API_KEY:
        return False, "Falta NVIDIA_API_KEY en .env.", None

    ruta_script = os.path.join(carpeta_proyecto, "script.txt")
    if not os.path.exists(ruta_script):
        return False, "No se encontró script.txt para sintetizar.", None

    with open(ruta_script, "r", encoding="utf-8") as file_handle:
        texto = file_handle.read()

    valido, error_validacion = validar_texto_para_tts(texto)
    if not valido:
        return False, error_validacion, None

    try:
        import riva.client
    except ImportError:
        return sintetizar_script_a_audio_nvidia_via_standalone(
            carpeta_proyecto,
            tts_config,
        )

    chunks = dividir_texto_para_tts(texto)
    if not chunks:
        return False, "No se pudo dividir el texto para síntesis.", None

    try:
        auth = riva.client.Auth(
            uri=NVIDIA_TTS_SERVER,
            use_ssl=True,
            metadata_args=[
                ["function-id", NVIDIA_MAGPIE_TTS_FUNCTION_ID],
                ["authorization", f"Bearer {NVIDIA_API_KEY}"],
            ],
            options=[
                ("grpc.max_receive_message_length", NVIDIA_GRPC_MAX_MESSAGE_BYTES),
                ("grpc.max_send_message_length", NVIDIA_GRPC_MAX_MESSAGE_BYTES),
            ],
        )
        service = riva.client.SpeechSynthesisService(auth)

        audios_pcm = []
        for chunk in chunks:
            response = service.synthesize(
                text=chunk,
                voice_name=tts_config["voice"],
                language_code=tts_config["language_code"],
                sample_rate_hz=tts_config["sample_rate_hz"],
                encoding=riva.client.AudioEncoding.LINEAR_PCM,
            )
            if not getattr(response, "audio", None):
                return False, "NVIDIA devolvió audio vacío.", None
            audios_pcm.append(response.audio)

        ruta_audio = os.path.join(carpeta_proyecto, tts_config["output_filename"])
        guardar_audio_pcm_como_wav(
            ruta_audio,
            audios_pcm,
            tts_config["sample_rate_hz"],
        )
        return (
            True,
            f"Audio generado correctamente en {tts_config['output_filename']} ({len(chunks)} fragmento(s)).",
            ruta_audio,
        )
    except Exception as ex:
        return False, f"Error NVIDIA TTS: {str(ex)}", None