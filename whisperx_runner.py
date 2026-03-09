"""
whisperx_runner.py
Script standalone para transcripción y alineación de audio con WhisperX.
Diseñado para ser invocado como subproceso desde clusiv-auto.py.

Uso:
    python whisperx_runner.py --audio-path "ruta/al/audio.wav" [--model medium] [--json-output]
"""

import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audio-path",
        required=True,
        help="Ruta al archivo de audio (.wav, .mp3, etc.)",
    )
    parser.add_argument(
        "--model",
        default="medium",
        help="Tamaño del modelo WhisperX (tiny, base, small, medium, large)",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Imprime resultado JSON en última línea de stdout",
    )
    args = parser.parse_args()

    audio_path = args.audio_path
    model_size = args.model
    use_json_output = args.json_output

    def emit(ok, msg, path=None):
        if use_json_output:
            print(json.dumps({"ok": ok, "msg": msg, "path": path}, ensure_ascii=False))
        elif not ok:
            print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(0 if ok else 1)

    # Validar que el archivo existe
    if not os.path.exists(audio_path):
        emit(False, f"El archivo de audio no existe: {audio_path}")

    # Ruta de salida JSON (mismo nombre, misma carpeta)
    output_path = os.path.splitext(audio_path)[0] + ".json"

    # Si ya existe el JSON, no reprocesar
    if os.path.exists(output_path):
        emit(True, "El archivo JSON ya existía, no se reprocesó.", output_path)

    # Importar dependencias pesadas solo cuando se necesitan
    try:
        import torch
        import whisperx
    except ImportError as e:
        emit(
            False,
            f"Dependencia no disponible: {e}. Asegúrate de ejecutar en el entorno whisperx-env.",
        )

    try:
        # Determinar dispositivo
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

        # Cargar modelo
        print(f"Cargando modelo WhisperX ({model_size}) en {device}...", flush=True)
        model = whisperx.load_model(model_size, device, compute_type=compute_type)

        # Cargar audio (soporta .wav, .mp3, etc. via ffmpeg)
        print(f"Cargando audio: {os.path.basename(audio_path)}...", flush=True)
        audio = whisperx.load_audio(audio_path)

        # Transcribir con reintentos ante OOM
        batch_size = 8 if device == "cuda" else 4
        result = None
        while batch_size > 0:
            try:
                print(f"Transcribiendo (batch_size={batch_size})...", flush=True)
                result = model.transcribe(audio, batch_size=batch_size)
                break
            except RuntimeError as e:
                if "out of memory" in str(e) and batch_size > 1:
                    batch_size = batch_size // 2
                    torch.cuda.empty_cache()
                else:
                    raise

        if result is None:
            emit(False, "Fallo en la transcripción después de varios intentos.")

        # Liberar VRAM
        if device == "cuda":
            del model
            torch.cuda.empty_cache()

        # Alineación forzada por palabra
        language_code = result.get("language")
        if not language_code:
            emit(False, "No se pudo detectar el idioma del audio.")

        print(
            f"Idioma detectado: {language_code}. Cargando modelo de alineación...",
            flush=True,
        )
        try:
            model_a, metadata = whisperx.load_align_model(
                language_code=language_code, device=device
            )
        except Exception as e:
            emit(
                False,
                f"No se pudo cargar el modelo de alineación para '{language_code}': {e}",
            )

        # Alinear
        if not result.get("segments"):
            word_data = []
        else:
            print("Alineando transcripción...", flush=True)
            aligned_result = whisperx.align(
                result["segments"],
                model_a,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )
            word_data = aligned_result.get("word_segments", [])
            word_data = [w for w in word_data if w.get("word", "").strip()]

        if device == "cuda":
            del model_a
            torch.cuda.empty_cache()

        # Guardar JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(word_data, f, indent=2, ensure_ascii=False)

        print(f"JSON guardado en: {output_path}", flush=True)
        emit(
            True,
            f"Transcripción completada. {len(word_data)} palabras con timestamps.",
            output_path,
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        emit(False, f"Error durante la transcripción: {str(e)}")


if __name__ == "__main__":
    main()
