"""
ws_bridge.py
------------
Servidor WebSocket local que actua como bridge entre Clusiv Automation
y la extension Chrome Flow Image Automator.
"""

import asyncio
import json
import os
import random
import shutil
import sys
import threading
import time
import webbrowser

import flet as ft
import pyautogui
import pyperclip
import websockets

from config import FLOW_LABS_URL, PATH_AI_STUDIO, PROMPT_AI_STUDIO_SCRIPT_PLACEHOLDER


active_ws_connection = None
ws_loop = None
available_journeys = []
extension_connected_event = threading.Event()
extension_bridge_state = {
    "connected": False,
    "status": "disconnected",
    "version": None,
    "last_seen": 0.0,
    "last_error": None,
}
ws_request_waiters = {}
ws_request_waiters_lock = threading.Lock()
pending_journey_chain = {
    "active": False,
    "first_journey_id": None,
    "second_journey_id": None,
    "second_sent": False,
}
BROWSER_DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
IMAGE_DOWNLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
pending_image_download = {
    "active": False,
    "project_dir": None,
    "target_dir": None,
    "download_dir": BROWSER_DOWNLOADS_DIR,
    "snapshot": set(),
    "started_at": 0.0,
    "expected_count": 0,
    "processed_files": set(),
    "transfer_thread": None,
}
pending_image_download_lock = threading.Lock()

ui_update_journeys_cb = None
ui_log_cb = None
ui_image_status_cb = None
ui_ext_status_cb = None


def reset_pending_journey_chain():
    pending_journey_chain["active"] = False
    pending_journey_chain["first_journey_id"] = None
    pending_journey_chain["second_journey_id"] = None
    pending_journey_chain["second_sent"] = False


def set_pending_journey_chain(first_journey_id, second_journey_id):
    pending_journey_chain["active"] = True
    pending_journey_chain["first_journey_id"] = first_journey_id
    pending_journey_chain["second_journey_id"] = second_journey_id
    pending_journey_chain["second_sent"] = False


def _normalize_fs_path(path):
    return os.path.normcase(os.path.abspath(path))


def _path_is_within(path, parent):
    try:
        return os.path.commonpath([_normalize_fs_path(path), _normalize_fs_path(parent)]) == _normalize_fs_path(parent)
    except ValueError:
        return False


def _iter_image_files(root_dir, exclude_dirs=None):
    if not root_dir or not os.path.isdir(root_dir):
        return

    excludes = [_normalize_fs_path(path) for path in (exclude_dirs or []) if path]

    for current_root, dirs, files in os.walk(root_dir, topdown=True):
        current_root_norm = _normalize_fs_path(current_root)
        if any(_path_is_within(current_root_norm, excluded) for excluded in excludes):
            dirs[:] = []
            continue

        dirs[:] = [
            directory
            for directory in dirs
            if not any(
                _path_is_within(os.path.join(current_root, directory), excluded)
                for excluded in excludes
            )
        ]

        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in IMAGE_DOWNLOAD_EXTENSIONS:
                continue
            full_path = os.path.join(current_root, filename)
            if full_path.lower().endswith(".crdownload"):
                continue
            yield full_path


def _snapshot_image_files(root_dir, exclude_dirs=None):
    return {
        _normalize_fs_path(path)
        for path in _iter_image_files(root_dir, exclude_dirs=exclude_dirs) or []
    }


def _build_unique_destination(dest_dir, filename):
    base_name, ext = os.path.splitext(filename)
    candidate = os.path.join(dest_dir, filename)
    suffix = 1
    while os.path.exists(candidate):
        candidate = os.path.join(dest_dir, f"{base_name}_{suffix}{ext}")
        suffix += 1
    return candidate


def _wait_until_file_ready(file_path, timeout_seconds=20, stable_checks=2, interval_seconds=0.75):
    deadline = time.time() + timeout_seconds
    last_size = -1
    stable_hits = 0

    while time.time() < deadline:
        if not os.path.exists(file_path):
            return False
        try:
            size = os.path.getsize(file_path)
        except OSError:
            size = -1

        if size > 0 and size == last_size:
            stable_hits += 1
            if stable_hits >= stable_checks:
                try:
                    with open(file_path, "ab"):
                        return True
                except OSError:
                    pass
        else:
            stable_hits = 0

        last_size = size
        time.sleep(interval_seconds)

    return False


def _move_file_into_project_images(source_path, target_dir, retries=5, retry_wait_seconds=1.0):
    if not _wait_until_file_ready(source_path):
        return False, None, "El archivo no termino de descargarse a tiempo."

    last_error = None
    for _ in range(retries):
        destination_path = _build_unique_destination(
            target_dir, os.path.basename(source_path)
        )
        try:
            shutil.move(source_path, destination_path)
            return True, destination_path, None
        except Exception as ex:
            last_error = ex
            time.sleep(retry_wait_seconds)

    return False, None, str(last_error) if last_error else "Error desconocido al mover archivo."


def set_image_status(texto, color=ft.Colors.GREY_500):
    if ui_image_status_cb:
        ui_image_status_cb(texto, color)


def reset_pending_image_download(clear_status=False):
    with pending_image_download_lock:
        pending_image_download["active"] = False
        pending_image_download["project_dir"] = None
        pending_image_download["target_dir"] = None
        pending_image_download["download_dir"] = BROWSER_DOWNLOADS_DIR
        pending_image_download["snapshot"] = set()
        pending_image_download["started_at"] = 0.0
        pending_image_download["expected_count"] = 0
        pending_image_download["processed_files"] = set()
        pending_image_download["transfer_thread"] = None

    if clear_status:
        set_image_status("Estado: esperando...", ft.Colors.GREY_500)


def prepare_pending_image_download(project_dir, expected_count=0, download_dir=None):
    project_dir = os.path.abspath(project_dir) if project_dir else None
    source_dir = os.path.abspath(download_dir or BROWSER_DOWNLOADS_DIR)

    if not project_dir:
        return False, "No se definio la carpeta del proyecto para recibir imagenes."
    if not os.path.isdir(source_dir):
        return False, f"No se encontro la carpeta de descargas: {source_dir}"

    target_dir = os.path.join(project_dir, "images")
    os.makedirs(target_dir, exist_ok=True)

    snapshot = _snapshot_image_files(source_dir, exclude_dirs=[project_dir])

    with pending_image_download_lock:
        pending_image_download["active"] = True
        pending_image_download["project_dir"] = project_dir
        pending_image_download["target_dir"] = target_dir
        pending_image_download["download_dir"] = source_dir
        pending_image_download["snapshot"] = snapshot
        pending_image_download["started_at"] = time.time()
        pending_image_download["expected_count"] = max(0, int(expected_count or 0))
        pending_image_download["processed_files"] = set()
        pending_image_download["transfer_thread"] = None

    return True, target_dir


def _collect_pending_download_candidates(context):
    candidates = []
    source_dir = context.get("download_dir")
    project_dir = context.get("project_dir")
    snapshot = context.get("snapshot") or set()
    processed_files = context.get("processed_files") or set()
    started_at = float(context.get("started_at") or 0)

    for path in _iter_image_files(source_dir, exclude_dirs=[project_dir]) or []:
        normalized = _normalize_fs_path(path)
        if normalized in snapshot or normalized in processed_files:
            continue
        try:
            modified_at = os.path.getmtime(path)
        except OSError:
            continue
        if modified_at + 2 < started_at:
            continue
        candidates.append((modified_at, path))

    candidates.sort(key=lambda item: item[0])
    return [path for _, path in candidates]


def _transfer_pending_downloads_worker():
    with pending_image_download_lock:
        if not pending_image_download["active"]:
            pending_image_download["transfer_thread"] = None
            return
        context = {
            "project_dir": pending_image_download["project_dir"],
            "target_dir": pending_image_download["target_dir"],
            "download_dir": pending_image_download["download_dir"],
            "snapshot": set(pending_image_download["snapshot"]),
            "started_at": pending_image_download["started_at"],
            "expected_count": pending_image_download["expected_count"],
            "processed_files": set(),
        }

    expected_count = context["expected_count"]
    moved_paths = []
    errors = []
    found_any = False
    consecutive_idle_rounds = 0
    max_wait_seconds = 45 if expected_count else 25
    deadline = time.time() + max_wait_seconds

    set_image_status(
        "Extension completo. Buscando imagenes descargadas...",
        ft.Colors.BLUE_700,
    )
    if ui_log_cb:
        ui_log_cb(
            f"🗂️ Buscando imagenes nuevas en {context['download_dir']} para moverlas a {context['target_dir']}...",
            color=ft.Colors.BLUE_700,
        )

    while time.time() < deadline:
        candidates = _collect_pending_download_candidates(context)
        if not candidates:
            consecutive_idle_rounds += 1
            if found_any and consecutive_idle_rounds >= 3:
                break
            time.sleep(1.0)
            continue

        consecutive_idle_rounds = 0
        found_any = True

        for source_path in candidates:
            normalized = _normalize_fs_path(source_path)
            context["processed_files"].add(normalized)

            set_image_status(
                f"Moviendo imagenes al proyecto... ({len(moved_paths) + 1})",
                ft.Colors.BLUE_700,
            )
            ok, destination_path, error_msg = _move_file_into_project_images(
                source_path,
                context["target_dir"],
            )
            if ok and destination_path:
                moved_paths.append(destination_path)
                if ui_log_cb:
                    ui_log_cb(
                        f"📥 Imagen movida: {os.path.basename(destination_path)}",
                        color=ft.Colors.GREEN_700,
                    )
            else:
                errors.append(
                    f"{os.path.basename(source_path)}: {error_msg or 'No se pudo mover.'}"
                )
                if ui_log_cb:
                    ui_log_cb(
                        f"⚠ No se pudo mover {os.path.basename(source_path)}: {error_msg}",
                        color=ft.Colors.ORANGE_700,
                    )

        if expected_count and len(moved_paths) >= expected_count:
            break

    if moved_paths:
        set_image_status(
            f"{len(moved_paths)} imagen(es) movidas a images.",
            ft.Colors.GREEN_700,
        )
        if ui_log_cb:
            ui_log_cb(
                f"✅ Se movieron {len(moved_paths)} imagen(es) a {context['target_dir']}.",
                color=ft.Colors.GREEN_800,
                weight="bold",
            )
    elif errors:
        set_image_status(
            "La extension termino, pero hubo errores al mover imagenes.",
            ft.Colors.ORANGE_700,
        )
    else:
        set_image_status(
            "La extension termino, pero no se detectaron imagenes nuevas.",
            ft.Colors.ORANGE_700,
        )
        if ui_log_cb:
            ui_log_cb(
                "⚠ No se detectaron imagenes nuevas en la carpeta de descargas despues del procesamiento.",
                color=ft.Colors.ORANGE_700,
            )

    if errors and ui_log_cb:
        ui_log_cb(
            f"⚠ Errores al mover imagenes: {' | '.join(errors)}",
            color=ft.Colors.ORANGE_700,
        )

    reset_pending_image_download(clear_status=False)


def start_pending_image_download_transfer():
    with pending_image_download_lock:
        if not pending_image_download["active"]:
            return False
        current_thread = pending_image_download.get("transfer_thread")
        if current_thread and current_thread.is_alive():
            return False
        worker = threading.Thread(target=_transfer_pending_downloads_worker, daemon=True)
        pending_image_download["transfer_thread"] = worker

    worker.start()
    return True


def journey_chain_matches_first(journey_id):
    first_journey_id = pending_journey_chain["first_journey_id"]
    return not journey_id or journey_id == first_journey_id


def is_paste_completion_signal(data):
    status = (data.get("status") or "").lower()
    event = (data.get("event") or "").lower()
    phase = (data.get("phase") or "").lower()
    msg = (data.get("message") or "").lower()

    explicit_signals = {"paste_completed", "paste_done", "pasted"}
    if status in explicit_signals or event in explicit_signals or phase in explicit_signals:
        return True

    return "paste" in msg and any(token in msg for token in ("completed", "done", "finished", "pegado"))


def dispatch_second_journey(trigger_label):
    if not pending_journey_chain["active"] or pending_journey_chain["second_sent"]:
        return False

    second_journey_id = pending_journey_chain["second_journey_id"]
    if not second_journey_id:
        reset_pending_journey_chain()
        return False

    payload = {
        "action": "RUN_JOURNEY",
        "journey_id": second_journey_id,
        "triggered_by": trigger_label,
    }

    if not send_ws_msg(payload):
        if ui_log_cb:
            ui_log_cb(
                "❌ No se pudo disparar la segunda automatizacion porque la extension no esta conectada.",
                color=ft.Colors.RED,
            )
        reset_pending_journey_chain()
        return False

    pending_journey_chain["second_sent"] = True
    if ui_log_cb:
        ui_log_cb(
            "🔁 Segunda automatizacion enviada a la extension.",
            color=ft.Colors.BLUE_800,
            weight="bold",
        )
    reset_pending_journey_chain()
    return True


def _make_ws_request_id(prefix="py"):
    return f"{prefix}_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


def _register_ws_waiter(request_id):
    event = threading.Event()
    waiter = {"event": event, "payload": None}
    with ws_request_waiters_lock:
        ws_request_waiters[request_id] = waiter
    return waiter


def _resolve_ws_waiter(data):
    request_id = data.get("requestId") or data.get("replyTo")
    if not request_id:
        return False

    with ws_request_waiters_lock:
        waiter = ws_request_waiters.get(request_id)

    if not waiter:
        return False

    waiter["payload"] = data
    waiter["event"].set()
    return True


def _pop_ws_waiter(request_id):
    with ws_request_waiters_lock:
        return ws_request_waiters.pop(request_id, None)


def wait_for_extension_connection(timeout_s=10.0):
    if active_ws_connection and extension_connected_event.is_set():
        return True
    return extension_connected_event.wait(timeout_s)


def _open_flow_tab_for_extension(flow_url=FLOW_LABS_URL):
    ultimo_error = None

    try:
        if sys.platform.startswith("win"):
            os.startfile(flow_url)
        else:
            webbrowser.open_new_tab(flow_url)
        return True, ""
    except Exception as ex:
        ultimo_error = ex

    try:
        opened = webbrowser.open_new_tab(flow_url)
        if opened:
            return True, ""
    except Exception as ex:
        ultimo_error = ex

    detalle = str(ultimo_error) if ultimo_error else "sin detalle adicional"
    return False, f"No se pudo abrir Google Labs Flow automaticamente: {detalle}"


def _ping_extension_bridge(timeout_s=8.0, source="image-prompts"):
    ok, pong, err = send_ws_request_and_wait(
        {"action": "PING", "source": source},
        expected_actions={"PONG"},
        timeout_s=timeout_s,
    )
    if ok:
        extension_bridge_state["connected"] = True
        extension_bridge_state["status"] = "connected"
        extension_bridge_state["last_seen"] = time.time()
        extension_bridge_state["last_error"] = None
        if pong and pong.get("version"):
            extension_bridge_state["version"] = pong.get("version")
    else:
        extension_bridge_state["status"] = (
            "connected_unresponsive" if extension_connected_event.is_set() else "disconnected"
        )
        extension_bridge_state["last_error"] = err
    return ok, pong, err


def bootstrap_extension_bridge(
    flow_url=FLOW_LABS_URL,
    attempts=2,
    connect_timeout_s=6.0,
    ping_timeout_s=6.0,
    reason="",
):
    ultimo_error = reason or "La extension no respondio al bridge."

    for intento in range(1, max(1, attempts) + 1):
        extension_bridge_state["status"] = "bootstrapping"
        extension_bridge_state["last_error"] = ultimo_error

        if ui_log_cb:
            ui_log_cb(
                f"🧩 Intentando despertar la extension y Google Flow ({intento}/{attempts})...",
                color=ft.Colors.BLUE_700,
                italic=True,
            )
        set_image_status(
            f"Activando extension Chrome y Google Flow ({intento}/{attempts})...",
            ft.Colors.BLUE_700,
        )

        opened, open_err = _open_flow_tab_for_extension(flow_url)
        if not opened and open_err:
            ultimo_error = open_err
            if ui_log_cb:
                ui_log_cb(f"⚠ {open_err}", color=ft.Colors.ORANGE_700)

        if wait_for_extension_connection(timeout_s=max(1.0, connect_timeout_s)):
            ok, _, err = _ping_extension_bridge(
                timeout_s=max(1.0, ping_timeout_s),
                source="bridge-bootstrap",
            )
            if ok:
                mensaje = "La extension respondio nuevamente al orquestador."
                if ui_log_cb:
                    ui_log_cb(f"✅ {mensaje}", color=ft.Colors.TEAL_700)
                return True, mensaje
            ultimo_error = err or "La extension se conecto, pero no respondio al ping."
        else:
            ultimo_error = (
                "La extension no abrio el bridge con Clusiv despues de intentar levantar Google Flow."
            )

        extension_bridge_state["last_error"] = ultimo_error

        if intento < attempts:
            time.sleep(1.5)

    extension_bridge_state["status"] = "disconnected"
    return False, ultimo_error


def _ensure_extension_bridge_alive(flow_url=FLOW_LABS_URL, timeout_s=35.0):
    handshake_timeout = min(timeout_s, 3.0)
    ping_timeout = min(timeout_s, 8.0)

    if wait_for_extension_connection(timeout_s=handshake_timeout):
        ok, pong, err = _ping_extension_bridge(
            timeout_s=ping_timeout,
            source="image-prompts",
        )
        if ok:
            return True, pong, ""
        motivo_bootstrap = err
    else:
        motivo_bootstrap = "La extension Chrome no se conecto al orquestador a tiempo."

    if ui_log_cb:
        ui_log_cb(
            f"⚠ {motivo_bootstrap}",
            color=ft.Colors.ORANGE_700,
        )

    boot_ok, boot_msg = bootstrap_extension_bridge(
        flow_url=flow_url,
        attempts=2,
        connect_timeout_s=min(timeout_s, 7.0),
        ping_timeout_s=ping_timeout,
        reason=motivo_bootstrap,
    )
    if not boot_ok:
        return False, None, boot_msg

    ok, pong, err = _ping_extension_bridge(
        timeout_s=ping_timeout,
        source="image-prompts-post-bootstrap",
    )
    if not ok:
        return False, None, err

    return True, pong, ""


def send_ws_request_and_wait(msg_dict, expected_actions=None, timeout_s=10.0):
    if not isinstance(msg_dict, dict):
        return False, None, "Mensaje WS invalido."

    request_id = str(msg_dict.get("requestId") or _make_ws_request_id())
    payload = dict(msg_dict)
    payload["requestId"] = request_id
    waiter = _register_ws_waiter(request_id)

    if not send_ws_msg(payload):
        _pop_ws_waiter(request_id)
        return False, None, "La extension Chrome no esta conectada al orquestador."

    if not waiter["event"].wait(timeout_s):
        _pop_ws_waiter(request_id)
        return False, None, f"Timeout esperando respuesta de la extension para {payload.get('action', 'request')}."

    data = waiter.get("payload")
    _pop_ws_waiter(request_id)

    if expected_actions:
        acciones = set(expected_actions)
        if (data or {}).get("action") not in acciones:
            return False, data, "La extension respondio con una accion inesperada."

    return True, data, ""


def ensure_extension_ready_for_images(flow_url=FLOW_LABS_URL, timeout_s=35.0):
    if ui_log_cb:
        ui_log_cb(
            "🔌 Verificando conexion con la extension Chrome...",
            color=ft.Colors.BLUE_700,
        )
    set_image_status("Verificando extension Chrome...", ft.Colors.BLUE_700)

    last_error = ""
    max_attempts = 2

    for intento in range(1, max_attempts + 1):
        bridge_ok, pong, err = _ensure_extension_bridge_alive(
            flow_url=flow_url,
            timeout_s=timeout_s,
        )
        if not bridge_ok:
            last_error = err
            if intento < max_attempts:
                continue
            return False, err

        if pong and pong.get("version"):
            extension_bridge_state["version"] = pong.get("version")

        if ui_log_cb:
            ui_log_cb(
                "🌐 Preparando Google Labs Flow en Chrome...",
                color=ft.Colors.BLUE_700,
            )
        set_image_status("Abriendo o validando Google Labs Flow...", ft.Colors.BLUE_700)

        ok, ready, err = send_ws_request_and_wait(
            {
                "action": "ENSURE_FLOW_READY",
                "url": flow_url,
                "openIfMissing": True,
                "timeoutMs": int(timeout_s * 1000),
            },
            expected_actions={"FLOW_READY_STATUS"},
            timeout_s=timeout_s,
        )
        if ok and ready and ready.get("ok"):
            mensaje = ready.get("message") or "Google Labs Flow listo."
            extension_bridge_state["status"] = "flow_ready"
            extension_bridge_state["last_error"] = None
            set_image_status("Google Labs Flow listo para procesar prompts.", ft.Colors.TEAL_700)
            if ui_log_cb:
                ui_log_cb(
                    f"✅ {mensaje}",
                    color=ft.Colors.TEAL_700,
                    weight="bold",
                )
            return True, mensaje

        last_error = err or (ready or {}).get("message") or "Flow no quedo listo para procesar prompts."
        extension_bridge_state["status"] = "flow_not_ready"
        extension_bridge_state["last_error"] = last_error

        if intento < max_attempts:
            if ui_log_cb:
                ui_log_cb(
                    f"⚠ {last_error} Reintentando preparacion de Flow...",
                    color=ft.Colors.ORANGE_700,
                )
            _open_flow_tab_for_extension(flow_url)
            time.sleep(1.5)

    return False, last_error or "Flow no quedo listo para procesar prompts."


async def ws_handler(websocket):
    global active_ws_connection, available_journeys
    active_ws_connection = websocket
    extension_connected_event.set()
    extension_bridge_state["connected"] = True
    extension_bridge_state["status"] = "connected"
    extension_bridge_state["last_seen"] = time.time()
    extension_bridge_state["last_error"] = None

    if ui_ext_status_cb:
        ui_ext_status_cb(True, extension_bridge_state.get("version") or "")

    if ui_log_cb:
        ui_log_cb("🟢 Extension web conectada al orquestador", color=ft.Colors.GREEN_700, weight="bold")

    try:
        async for message in websocket:
            data = json.loads(message)
            accion = data.get("action")

            if accion in {"PONG", "FLOW_READY_STATUS"}:
                extension_bridge_state["last_seen"] = time.time()
                if data.get("version"):
                    extension_bridge_state["version"] = data.get("version")
                _resolve_ws_waiter(data)
                continue

            if accion == "JOURNEYS_LIST":
                available_journeys = data.get("data", [])
                if ui_update_journeys_cb:
                    ui_update_journeys_cb()

            elif accion == "JOURNEY_STATUS":
                status = data.get("status")
                msg = data.get("message", "")
                if status == "completed":
                    if ui_log_cb:
                        ui_log_cb(f"✅ {msg}", color=ft.Colors.GREEN_700, weight="bold")
                elif status == "error":
                    if ui_log_cb:
                        ui_log_cb(f"❌ Extension: {msg}", color=ft.Colors.RED)
                elif status == "started":
                    if ui_log_cb:
                        ui_log_cb(f"🚀 {msg}", color=ft.Colors.PURPLE_700, weight="bold")
                else:
                    if ui_log_cb:
                        ui_log_cb(f"▶ {msg}", color=ft.Colors.BLUE_700)

                if pending_journey_chain["active"] and not pending_journey_chain["second_sent"]:
                    if status == "error" and journey_chain_matches_first(data.get("journey_id")):
                        reset_pending_journey_chain()
                    elif journey_chain_matches_first(data.get("journey_id")) and is_paste_completion_signal(data):
                        dispatch_second_journey("paste_completed")
                    elif status == "completed" and journey_chain_matches_first(data.get("journey_id")):
                        if ui_log_cb:
                            ui_log_cb(
                                "⚠ El primer journey termino, pero la extension no envio una senal explicita de pegado completado. La segunda automatizacion queda cancelada hasta que la extension emita 'paste_completed'.",
                                color=ft.Colors.ORANGE_700,
                            )
                        reset_pending_journey_chain()

            elif accion == "EXTENSION_CONNECTED":
                version = data.get("version", "?")
                extension_bridge_state["connected"] = True
                extension_bridge_state["status"] = "connected"
                extension_bridge_state["version"] = version
                extension_bridge_state["last_seen"] = time.time()
                extension_bridge_state["last_error"] = None
                extension_connected_event.set()
                if ui_ext_status_cb:
                    ui_ext_status_cb(True, version)
                if ui_log_cb:
                    ui_log_cb(
                        f"🔗 Flow Image Automator v{version} conectado y listo.",
                        color=ft.Colors.TEAL_700,
                        weight="bold",
                    )

            elif accion == "QUEUE_STATUS":
                status = data.get("status", "")
                msg = data.get("message", "")
                if status == "queued":
                    set_image_status(
                        "Prompts encolados. Esperando inicio de procesamiento...",
                        ft.Colors.TEAL_700,
                    )
                    if ui_log_cb:
                        ui_log_cb(
                            f"🖼️ Extension confirmo encolar: {msg}",
                            color=ft.Colors.TEAL_700,
                        )
                elif status == "queue_status":
                    if ui_log_cb:
                        ui_log_cb(
                            f"📊 Estado de la cola: {msg}",
                            color=ft.Colors.BLUE_700,
                        )
                elif status == "processing_started":
                    set_image_status(
                        "Flow esta generando y descargando imagenes...",
                        ft.Colors.GREEN_700,
                    )
                    if ui_log_cb:
                        ui_log_cb(
                            "🚀 Extension comenzo a procesar imagenes.",
                            color=ft.Colors.GREEN_700,
                            weight="bold",
                        )
                elif status == "processing_complete":
                    transfer_started = start_pending_image_download_transfer()
                    if not transfer_started:
                        set_image_status(
                            "Extension completo el procesamiento.",
                            ft.Colors.GREEN_700,
                        )
                    if ui_log_cb:
                        ui_log_cb(
                            "✅ Extension termino de procesar todas las imagenes.",
                            color=ft.Colors.GREEN_800,
                            weight="bold",
                        )
                elif status == "error":
                    set_image_status(
                        f"Error en extension: {msg}",
                        ft.Colors.RED_700,
                    )
                    reset_pending_image_download(clear_status=False)
                    if ui_log_cb:
                        ui_log_cb(
                            f"❌ Error en extension: {msg}",
                            color=ft.Colors.RED,
                        )
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        active_ws_connection = None
        extension_connected_event.clear()
        extension_bridge_state["connected"] = False
        extension_bridge_state["status"] = "disconnected"
        extension_bridge_state["last_seen"] = 0.0
        extension_bridge_state["last_error"] = "La extension cerro la conexion con el orquestador."
        reset_pending_journey_chain()
        if ui_ext_status_cb:
            ui_ext_status_cb(False, "")
        if ui_log_cb:
            ui_log_cb("🔴 Extension web desconectada. Esperando reconexion...", color=ft.Colors.ORANGE_700, weight="bold")


def start_ws_server():
    global ws_loop

    async def runner():
        async with websockets.serve(ws_handler, "localhost", 8765):
            await asyncio.Future()

    ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(ws_loop)
    ws_loop.run_until_complete(runner())


def send_ws_msg(msg_dict):
    if active_ws_connection and ws_loop:
        asyncio.run_coroutine_threadsafe(
            active_ws_connection.send(json.dumps(msg_dict)), ws_loop
        )
        return True
    return False


threading.Thread(target=start_ws_server, daemon=True).start()


def send_image_prompts_to_extension(
    ruta_txt,
    modelo="imagen4",
    aspect_ratio="landscape",
    count=1,
    reference_image_paths=None,
    reference_mode="ingredients",
    project_folder=None,
    download_dir=None,
):
    if not ruta_txt or not os.path.exists(ruta_txt):
        return False, f"No se encontro el archivo de prompts: {ruta_txt}", 0

    try:
        with open(ruta_txt, "r", encoding="utf-8") as f:
            lineas = [
                linea.strip()
                for linea in f.readlines()
                if linea.strip() and not linea.strip().startswith("#")
            ]
    except Exception as ex:
        return False, f"Error al leer el archivo de prompts: {str(ex)}", 0

    if not lineas:
        return False, "El archivo de prompts esta vacio o no tiene lineas validas.", 0

    try:
        count_normalizado = max(1, min(4, int(count)))
    except (TypeError, ValueError):
        count_normalizado = 1

    ref_images_payload = encode_images_to_payload(
        reference_image_paths,
        reference_mode,
    )

    ts_base = int(time.time() * 1000)
    created_at = int(time.time() * 1000)
    tareas = []
    for indice, prompt in enumerate(lineas):
        tarea = {
            "id": f"clusiv_{ts_base}_{indice}",
            "type": "createimage",
            "prompt": prompt,
            "status": "pending",
            "createdAt": created_at + indice,
            "settings": {
                "model": modelo,
                "aspectRatio": aspect_ratio,
                "count": str(count_normalizado),
            },
        }
        if ref_images_payload:
            tarea["referenceImages"] = ref_images_payload
        tareas.append(tarea)

    payload = {
        "action": "QUEUE_IMAGE_PROMPTS",
        "tasks": tareas,
        "autoStart": True,
    }

    ready_ok, ready_msg = ensure_extension_ready_for_images()
    if not ready_ok:
        reset_pending_image_download(clear_status=False)
        set_image_status(f"Error de readiness: {ready_msg}", ft.Colors.RED_700)
        return False, ready_msg, 0

    if project_folder:
        prepared, destino_o_error = prepare_pending_image_download(
            project_folder,
            expected_count=len(tareas) * count_normalizado,
            download_dir=download_dir,
        )
        if not prepared:
            return False, destino_o_error, 0
        if ui_log_cb:
            ui_log_cb(
                f"🗂️ Las imagenes nuevas se moveran a {destino_o_error}",
                color=ft.Colors.BLUE_700,
            )
    else:
        reset_pending_image_download(clear_status=False)

    if not send_ws_msg(payload):
        reset_pending_image_download(clear_status=False)
        return False, "La extension Chrome no esta conectada al orquestador.", 0

    return True, f"{len(tareas)} prompt(s) enviados correctamente a la extension.", len(tareas)


def encode_images_to_payload(image_paths, mode="ingredients"):
    import base64
    import io
    import mimetypes

    if not image_paths:
        return None

    max_images = 5
    max_side_px = 1024
    images_encoded = []

    for path in image_paths[:max_images]:
        if not os.path.isfile(path):
            continue

        mime, _ = mimetypes.guess_type(path)
        if not mime or not mime.startswith("image/"):
            mime = "image/png"

        try:
            output_mime = mime
            try:
                from PIL import Image

                img = Image.open(path)
                if max(img.size) > max_side_px:
                    img.thumbnail((max_side_px, max_side_px), Image.LANCZOS)

                buffer = io.BytesIO()
                if mime == "image/jpeg":
                    output_mime = "image/jpeg"
                    if img.mode not in ("RGB", "L"):
                        img = img.convert("RGB")
                    img.save(buffer, format="JPEG", optimize=True)
                else:
                    output_mime = "image/png"
                    img.save(buffer, format="PNG", optimize=True)
                raw = buffer.getvalue()
            except ImportError:
                with open(path, "rb") as f:
                    raw = f.read()

            b64 = base64.b64encode(raw).decode("utf-8")
            data_url = f"data:{output_mime};base64,{b64}"
            images_encoded.append(
                {
                    "name": os.path.basename(path),
                    "data": data_url,
                }
            )
        except Exception:
            continue

    if not images_encoded:
        return None

    return {
        "mode": mode if mode in ("ingredients", "frames") else "ingredients",
        "images": images_encoded,
    }


def construir_prompt_ai_studio(prompt_base, carpeta_proyecto):
    if not prompt_base or not prompt_base.strip():
        return False, "El prompt de AI Studio esta vacio.", None

    ruta_script = os.path.join(carpeta_proyecto, "script.txt")
    if not os.path.exists(ruta_script):
        return False, "No se abrio AI Studio: no se encontro script.txt en la carpeta del proyecto.", None

    try:
        with open(ruta_script, "r", encoding="utf-8") as f:
            texto_script = f.read().strip()
    except Exception as ex:
        return False, f"No se pudo leer script.txt para AI Studio: {str(ex)}", None

    if not texto_script:
        return False, "No se abrio AI Studio: script.txt esta vacio.", None

    prompt_limpio = prompt_base.strip()
    if PROMPT_AI_STUDIO_SCRIPT_PLACEHOLDER in prompt_limpio:
        prompt_final = prompt_limpio.replace(
            PROMPT_AI_STUDIO_SCRIPT_PLACEHOLDER,
            texto_script,
            1,
        )
        return (
            True,
            "Prompt de AI Studio preparado insertando script.txt en el placeholder.",
            prompt_final,
        )

    prompt_final = f"{prompt_limpio.rstrip()}\n\n{texto_script}"
    return (
        True,
        "Prompt de AI Studio preparado anexando script.txt al final porque no se encontro el placeholder.",
        prompt_final,
    )


def abrir_ai_studio_con_prompt(texto_prompt):
    if not texto_prompt or not texto_prompt.strip():
        return False, "El prompt de AI Studio esta vacio."

    if not os.path.exists(PATH_AI_STUDIO):
        return False, f"No se encontro el acceso directo de AI Studio en:\n{PATH_AI_STUDIO}"

    try:
        pyperclip.copy(texto_prompt)
        os.startfile(PATH_AI_STUDIO)
        time.sleep(4)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.5)
        pyautogui.press("enter")
        return True, "AI Studio abierto, prompt pegado y enviado."
    except Exception as ex:
        return False, f"Error al abrir AI Studio: {str(ex)}"