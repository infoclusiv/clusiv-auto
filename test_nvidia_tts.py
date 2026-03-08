import argparse
import json
import os
import re
import sys
import wave

import riva.client


CONFIG_FILE = "config_automatizacion.json"
ENV_FILE = ".env"
NVIDIA_TTS_SERVER = "grpc.nvcf.nvidia.com:443"
NVIDIA_MAGPIE_TTS_FUNCTION_ID = "877104f7-e885-42b9-8de8-f6e4c6303969"
NVIDIA_GRPC_MAX_MESSAGE_BYTES = 32 * 1024 * 1024


def obtener_tts_config_default():
    return {
        "enabled": True,
        "provider": "nvidia",
        "language_code": "en-US",
        "voice": "Magpie-Multilingual.EN-US.Aria",
        "output_filename": "audio.wav",
        "sample_rate_hz": 44100,
    }


def normalizar_tts_config(tts_config):
    defaults = obtener_tts_config_default()
    normalizado = dict(defaults)

    if isinstance(tts_config, dict):
        for key, value in tts_config.items():
            if value is not None:
                normalizado[key] = value

    normalizado["provider"] = str(normalizado.get("provider", defaults["provider"])).strip().lower() or defaults["provider"]
    normalizado["language_code"] = str(normalizado.get("language_code", defaults["language_code"])).strip() or defaults["language_code"]
    normalizado["voice"] = str(normalizado.get("voice", defaults["voice"])).strip() or defaults["voice"]

    output_filename = str(normalizado.get("output_filename", defaults["output_filename"])).strip() or defaults["output_filename"]
    if not output_filename.lower().endswith(".wav"):
        output_filename = f"{output_filename}.wav"
    normalizado["output_filename"] = output_filename

    try:
        sample_rate_hz = int(normalizado.get("sample_rate_hz", defaults["sample_rate_hz"]))
    except (TypeError, ValueError):
        sample_rate_hz = defaults["sample_rate_hz"]
    if sample_rate_hz <= 0:
        sample_rate_hz = defaults["sample_rate_hz"]
    normalizado["sample_rate_hz"] = sample_rate_hz

    return normalizado


def cargar_config():
    if not os.path.exists(CONFIG_FILE):
        return {"ruta_proyectos": "", "tts": obtener_tts_config_default()}

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["tts"] = normalizar_tts_config(data.get("tts"))
    return data


def cargar_nvidia_api_key():
    env_value = os.getenv("NVIDIA_API_KEY")
    if env_value:
        return env_value

    if not os.path.exists(ENV_FILE):
        return None

    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "NVIDIA_API_KEY":
                return value.strip().strip('"').strip("'")

    return None


def obtener_ultimo_video(ruta_base):
    if not ruta_base or not os.path.exists(ruta_base):
        return None

    carpetas = [
        d for d in os.listdir(ruta_base) if os.path.isdir(os.path.join(ruta_base, d))
    ]
    nums = [
        int(m.group(1))
        for c in carpetas
        if (m := re.search(r"video\s*(\d+)", c, re.IGNORECASE))
    ]
    if not nums:
        return None

    return os.path.join(ruta_base, f"video {max(nums)}")


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


def sintetizar_script(project_dir, tts_config, api_key, verbose=True):
    if tts_config.get("provider") != "nvidia":
        raise RuntimeError("Proveedor TTS no soportado actualmente.")

    ruta_script = os.path.join(project_dir, "script.txt")
    if not os.path.exists(ruta_script):
        raise FileNotFoundError(f"No se encontró script.txt en {project_dir}")

    with open(ruta_script, "r", encoding="utf-8") as f:
        texto = f.read()

    valido, error_validacion = validar_texto_para_tts(texto)
    if not valido:
        raise RuntimeError(error_validacion)

    chunks = dividir_texto_para_tts(texto)

    auth = riva.client.Auth(
        uri=NVIDIA_TTS_SERVER,
        use_ssl=True,
        metadata_args=[
            ["function-id", NVIDIA_MAGPIE_TTS_FUNCTION_ID],
            ["authorization", f"Bearer {api_key}"],
        ],
        options=[
            ("grpc.max_receive_message_length", NVIDIA_GRPC_MAX_MESSAGE_BYTES),
            ("grpc.max_send_message_length", NVIDIA_GRPC_MAX_MESSAGE_BYTES),
        ],
    )
    service = riva.client.SpeechSynthesisService(auth)

    audios_pcm = []
    for idx, chunk in enumerate(chunks, start=1):
        if verbose:
            print(f"[{idx}/{len(chunks)}] Sintetizando fragmento de {len(chunk)} caracteres...")
        response = service.synthesize(
            text=chunk,
            voice_name=tts_config["voice"],
            language_code=tts_config["language_code"],
            sample_rate_hz=tts_config["sample_rate_hz"],
            encoding=riva.client.AudioEncoding.LINEAR_PCM,
        )
        if not getattr(response, "audio", None):
            raise RuntimeError("NVIDIA devolvió audio vacío.")
        audios_pcm.append(response.audio)

    ruta_audio = os.path.join(project_dir, tts_config["output_filename"])
    guardar_audio_pcm_como_wav(ruta_audio, audios_pcm, tts_config["sample_rate_hz"])
    return ruta_audio, len(chunks), len(texto)


def main():
    parser = argparse.ArgumentParser(description="Prueba directa de NVIDIA TTS sobre script.txt")
    parser.add_argument("--project-dir", help="Carpeta del proyecto que contiene script.txt")
    parser.add_argument("--voice", help="Sobrescribe la voz configurada")
    parser.add_argument("--language-code", help="Sobrescribe el language code configurado")
    parser.add_argument("--output", help="Nombre del archivo WAV de salida")
    parser.add_argument("--sample-rate-hz", type=int, help="Sobrescribe el sample rate configurado")
    parser.add_argument("--json-output", action="store_true", help="Devuelve el resultado en JSON")
    args = parser.parse_args()

    config = cargar_config()
    tts_config = normalizar_tts_config(config.get("tts"))

    if args.voice:
        tts_config["voice"] = args.voice.strip()
    if args.language_code:
        tts_config["language_code"] = args.language_code.strip()
    if args.output:
        tts_config["output_filename"] = args.output.strip()
    if args.sample_rate_hz:
        tts_config["sample_rate_hz"] = args.sample_rate_hz
    tts_config = normalizar_tts_config(tts_config)

    project_dir = args.project_dir or obtener_ultimo_video(config.get("ruta_proyectos", ""))
    if not project_dir:
        raise RuntimeError("No se pudo resolver la carpeta del proyecto a probar.")

    api_key = cargar_nvidia_api_key()
    if not api_key:
        raise RuntimeError("No se encontró NVIDIA_API_KEY en variables de entorno ni en .env.")

    if not args.json_output:
        print(f"Proyecto: {project_dir}")
        print(f"Voz: {tts_config['voice']}")
        print(f"Idioma: {tts_config['language_code']}")
        print(f"Salida: {tts_config['output_filename']}")

    ruta_audio, total_chunks, total_chars = sintetizar_script(
        project_dir,
        tts_config,
        api_key,
        verbose=not args.json_output,
    )

    if args.json_output:
        print(
            json.dumps(
                {
                    "ok": True,
                    "msg": f"Audio generado correctamente en {tts_config['output_filename']} ({total_chunks} fragmento(s)).",
                    "path": ruta_audio,
                    "chars": total_chars,
                    "chunks": total_chunks,
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"OK: audio generado en {ruta_audio}")
        print(f"Resumen: {total_chars} caracteres, {total_chunks} fragmento(s)")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        if "--json-output" in sys.argv:
            print(json.dumps({"ok": False, "msg": str(ex), "path": None}, ensure_ascii=False))
        else:
            print(f"ERROR: {ex}")
        sys.exit(1)