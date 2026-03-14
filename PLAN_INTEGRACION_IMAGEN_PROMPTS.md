# Plan: Integración de Generación de Imágenes — Clusiv-Auto → Flow Image Automator

## Contexto y arquitectura

Clusiv-Auto (`clusiv-auto.py`) ya tiene un servidor WebSocket corriendo en `localhost:8765` con el handler `ws_handler`. La extensión Chrome (Flow Image Automator) ya tiene una cola de tareas en IndexedDB (`queueDB.js`) y un content script que ejecuta esas tareas en `labs.google`.

Lo que se va a implementar:

1. **Python** aprende a leer `prompts_imagenes.txt` y enviar las tareas via WebSocket con una nueva acción `QUEUE_IMAGE_PROMPTS`.
2. **background.js** (extensión) aprende a conectarse como *cliente* WebSocket a Python, recibir esas tareas y cargarlas en la cola existente.
3. **queueDB.js** (extensión) recibe una función nueva `addTasks()` para inserción en batch.
4. **UI de Clusiv-Auto** recibe una nueva tarjeta "Generación de Imágenes" con controles para configurar y disparar el envío de prompts manualmente o de forma automática al finalizar el flujo de AI Studio.

---

## Archivos a modificar

| # | Archivo | Tipo de cambio |
|---|---------|---------------|
| 1 | `clusiv-auto.py` | Agregar función `send_image_prompts_to_extension()`, handler en `ws_handler`, config en `guardar_config`/`cargar_toda_config`, UI nueva tarjeta, hook automático post AI Studio |
| 2 | `background.js` (extensión) | Agregar cliente WebSocket que se conecta a Python, handler de mensajes entrantes |
| 3 | `queueDB.js` (extensión) | Agregar función `addTasks(newTasks)` para inserción en batch |
| 4 | `manifest.json` (extensión) | Sin cambios (permisos ya son suficientes) |

---

## Archivo 1: `clusiv-auto.py`

### 1.1 — Agregar configuración de imagen en `obtener_ai_studio_config_default()`

**Localizar la función:**
```python
def obtener_ai_studio_config_default():
    return {
        "prompt": "",
        "espera_respuesta_segundos": 15,
        "archivo_salida": AI_STUDIO_OUTPUT_FILENAME_DEFAULT,
    }
```

**Reemplazar con:**
```python
def obtener_ai_studio_config_default():
    return {
        "prompt": "",
        "espera_respuesta_segundos": 15,
        "archivo_salida": AI_STUDIO_OUTPUT_FILENAME_DEFAULT,
        "auto_send_to_extension": False,
        "imagen_model": "imagen4",
        "imagen_aspect_ratio": "landscape",
        "imagen_count": 1,
    }
```

---

### 1.2 — Actualizar `normalizar_ai_studio_config()` para propagar los nuevos campos

**Localizar** la función `normalizar_ai_studio_config`. Al final del bloque de normalizaciones, antes del `return normalizado`, agregar:

```python
    # Nuevos campos: imagen config
    normalizado["auto_send_to_extension"] = bool(
        normalizado.get("auto_send_to_extension", defaults["auto_send_to_extension"])
    )

    imagen_model = str(normalizado.get("imagen_model", defaults["imagen_model"])).strip()
    normalizado["imagen_model"] = imagen_model or defaults["imagen_model"]

    imagen_aspect_ratio = str(
        normalizado.get("imagen_aspect_ratio", defaults["imagen_aspect_ratio"])
    ).strip()
    normalizado["imagen_aspect_ratio"] = imagen_aspect_ratio or defaults["imagen_aspect_ratio"]

    try:
        imagen_count = int(normalizado.get("imagen_count", defaults["imagen_count"]))
    except (TypeError, ValueError):
        imagen_count = defaults["imagen_count"]
    imagen_count = max(1, min(4, imagen_count))
    normalizado["imagen_count"] = imagen_count
```

---

### 1.3 — Agregar función `send_image_prompts_to_extension()`

**Ubicación:** Justo antes de la función `construir_prompt_ai_studio` (aproximadamente línea 1137).

**Insertar el siguiente bloque completo:**

```python
def send_image_prompts_to_extension(ruta_txt, modelo="imagen4", aspect_ratio="landscape", count=1):
    """
    Lee un archivo .txt con prompts de imagen (uno por línea, ignorando líneas vacías
    y líneas que empiecen con #) y los envía a la extensión Chrome via WebSocket
    para que los encole y procese en Google Labs Flow.

    Retorna: (ok: bool, mensaje: str, cantidad: int)
    """
    if not ruta_txt or not os.path.exists(ruta_txt):
        return False, f"No se encontró el archivo de prompts: {ruta_txt}", 0

    try:
        with open(ruta_txt, "r", encoding="utf-8") as f:
            lineas = [
                l.strip()
                for l in f.readlines()
                if l.strip() and not l.strip().startswith("#")
            ]
    except Exception as ex:
        return False, f"Error al leer el archivo de prompts: {str(ex)}", 0

    if not lineas:
        return False, "El archivo de prompts está vacío o no tiene líneas válidas.", 0

    ts_base = int(time.time() * 1000)
    tareas = [
        {
            "id": f"clusiv_{ts_base}_{i}",
            "type": "createimage",
            "prompt": prompt,
            "status": "pending",
            "settings": {
                "model": modelo,
                "aspectRatio": aspect_ratio,
                "count": str(count),
            },
        }
        for i, prompt in enumerate(lineas)
    ]

    payload = {
        "action": "QUEUE_IMAGE_PROMPTS",
        "tasks": tareas,
        "autoStart": True,
    }

    if not send_ws_msg(payload):
        return False, "La extensión Chrome no está conectada al orquestador.", 0

    return True, f"{len(tareas)} prompt(s) enviados correctamente a la extensión.", len(tareas)
```

---

### 1.4 — Actualizar el handler `ws_handler()` para recibir confirmaciones de la extensión

**Localizar** dentro de `async def ws_handler(websocket):` el bloque `async for message in websocket:` y su estructura de `if/elif`. Agregar **al final** de esa cadena, después del último `elif accion == "JOURNEY_STATUS":`:

```python
            elif accion == "EXTENSION_CONNECTED":
                version = data.get("version", "?")
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
                    if ui_log_cb:
                        ui_log_cb(
                            f"🖼️ Extensión confirmó encolar: {msg}",
                            color=ft.Colors.TEAL_700,
                        )
                elif status == "queue_status":
                    if ui_log_cb:
                        ui_log_cb(
                            f"📊 Estado de la cola: {msg}",
                            color=ft.Colors.BLUE_700,
                        )
                elif status == "processing_started":
                    if ui_log_cb:
                        ui_log_cb(
                            f"🚀 Extensión comenzó a procesar imágenes.",
                            color=ft.Colors.GREEN_700,
                            weight="bold",
                        )
                elif status == "processing_complete":
                    if ui_log_cb:
                        ui_log_cb(
                            f"✅ Extensión terminó de procesar todas las imágenes.",
                            color=ft.Colors.GREEN_800,
                            weight="bold",
                        )
                elif status == "error":
                    if ui_log_cb:
                        ui_log_cb(
                            f"❌ Error en extensión: {msg}",
                            color=ft.Colors.RED,
                        )
```

---

### 1.5 — Hook automático post AI Studio: envío automático de prompts

**Localizar** en el flujo principal (dentro de `proceso_hilo`) el bloque exacto que guarda los prompts de AI Studio exitosamente:

```python
                                                                    ruta_prompts = guardar_prompts_ai_studio(
                                                                        path,
                                                                        prompts_extraidos,
                                                                        ai_studio_runtime.get(
                                                                            "archivo_salida"
                                                                        ),
                                                                    )
                                                                    log_msg(
                                                                        f"✅ AI Studio: {len(prompts_extraidos)} prompt(s) guardados en {os.path.basename(ruta_prompts)}.",
                                                                        color=ft.Colors.GREEN_700,
                                                                        weight="bold",
                                                                    )
```

**Inmediatamente después del `log_msg` de confirmación** (y antes del `else` de `if prompts_extraidos:`), agregar:

```python
                                                                    # Hook automático: enviar prompts a la extensión
                                                                    if (
                                                                        not stop_event.is_set()
                                                                        and ai_studio_runtime.get("auto_send_to_extension", False)
                                                                    ):
                                                                        log_msg(
                                                                            "🖼️ Enviando prompts de imagen a la extensión Chrome...",
                                                                            color=ft.Colors.TEAL_700,
                                                                            italic=True,
                                                                        )
                                                                        img_ok, img_msg, img_count = send_image_prompts_to_extension(
                                                                            ruta_prompts,
                                                                            modelo=ai_studio_runtime.get("imagen_model", "imagen4"),
                                                                            aspect_ratio=ai_studio_runtime.get("imagen_aspect_ratio", "landscape"),
                                                                            count=int(ai_studio_runtime.get("imagen_count", 1)),
                                                                        )
                                                                        log_msg(
                                                                            f"{'✅' if img_ok else '⚠'} {img_msg}",
                                                                            color=ft.Colors.GREEN_700 if img_ok else ft.Colors.ORANGE_700,
                                                                            weight="bold" if img_ok else None,
                                                                        )
```

---

### 1.6 — Agregar controles UI para la nueva tarjeta "Generación de Imágenes"

**Ubicación:** En la función `main()`, localizar la sección `# ==========================================` que contiene `# --- UI: CONTROL DE EXTENSIÓN WEB ---` (aproximadamente línea 3051). Justo **antes** de esa sección (antes del comentario de extensión web), agregar el bloque completo siguiente:

```python
    # ==========================================
    # --- UI: GENERACIÓN DE IMÁGENES (FLOW AUTOMATOR) ---
    # ==========================================

    # Refrescar ai_studio_config desde config_actual para tener los nuevos campos
    imagen_model_inicial = ai_studio_config.get("imagen_model", "imagen4")
    imagen_aspect_inicial = ai_studio_config.get("imagen_aspect_ratio", "landscape")
    imagen_count_inicial = str(ai_studio_config.get("imagen_count", 1))
    auto_send_inicial = ai_studio_config.get("auto_send_to_extension", False)

    switch_auto_send = ft.Switch(
        label="🔄 Enviar automáticamente al finalizar AI Studio",
        value=auto_send_inicial,
        active_color=ft.Colors.TEAL_600,
    )

    dropdown_imagen_model = ft.Dropdown(
        label="Modelo de imagen",
        value=imagen_model_inicial,
        options=[
            ft.dropdown.Option("imagen4", "Imagen 4"),
            ft.dropdown.Option("nano_banana2", "NB 2"),
            ft.dropdown.Option("nano_banana_pro", "NB Pro"),
        ],
        dense=True,
        expand=True,
    )

    dropdown_imagen_aspect = ft.Dropdown(
        label="Aspect Ratio",
        value=imagen_aspect_inicial,
        options=[
            ft.dropdown.Option("landscape", "16:9 Landscape"),
            ft.dropdown.Option("portrait", "9:16 Portrait"),
        ],
        dense=True,
        expand=True,
    )

    dropdown_imagen_count = ft.Dropdown(
        label="Imágenes por prompt",
        value=imagen_count_inicial,
        options=[
            ft.dropdown.Option("1", "1×"),
            ft.dropdown.Option("2", "2×"),
            ft.dropdown.Option("3", "3×"),
            ft.dropdown.Option("4", "4×"),
        ],
        dense=True,
        expand=True,
    )

    lbl_imagen_status = ft.Text(
        "Estado: esperando...",
        size=11,
        color=ft.Colors.GREY_500,
        italic=True,
    )

    def persistir_imagen_config(e=None):
        ai_studio_config["auto_send_to_extension"] = bool(switch_auto_send.value)
        ai_studio_config["imagen_model"] = dropdown_imagen_model.value or "imagen4"
        ai_studio_config["imagen_aspect_ratio"] = dropdown_imagen_aspect.value or "landscape"
        try:
            ai_studio_config["imagen_count"] = int(dropdown_imagen_count.value or "1")
        except ValueError:
            ai_studio_config["imagen_count"] = 1
        config_actual["ai_studio"] = dict(ai_studio_config)
        guardar_config(ai_studio=ai_studio_config)

    switch_auto_send.on_change = persistir_imagen_config
    dropdown_imagen_model.on_change = persistir_imagen_config
    dropdown_imagen_aspect.on_change = persistir_imagen_config
    dropdown_imagen_count.on_change = persistir_imagen_config

    def enviar_prompts_manualmente(e):
        """Lee prompts_imagenes.txt del último proyecto y lo envía a la extensión."""
        persistir_imagen_config()

        ultimo_video = obtener_ultimo_video(ruta_base[0])
        if not ultimo_video:
            show_snack("No hay proyectos generados todavía.", ft.Colors.RED)
            return

        nombre_archivo = ai_studio_config.get("archivo_salida", AI_STUDIO_OUTPUT_FILENAME_DEFAULT)
        ruta_txt = os.path.join(ultimo_video, nombre_archivo)

        def hilo_envio():
            lbl_imagen_status.value = "Enviando..."
            page.update()
            ok, msg, cantidad = send_image_prompts_to_extension(
                ruta_txt,
                modelo=ai_studio_config.get("imagen_model", "imagen4"),
                aspect_ratio=ai_studio_config.get("imagen_aspect_ratio", "landscape"),
                count=int(ai_studio_config.get("imagen_count", 1)),
            )
            lbl_imagen_status.value = msg
            lbl_imagen_status.color = ft.Colors.GREEN_700 if ok else ft.Colors.RED_700
            log_msg(
                f"{'✅' if ok else '❌'} Imágenes: {msg}",
                color=ft.Colors.GREEN_700 if ok else ft.Colors.RED,
            )
            page.update()

        threading.Thread(target=hilo_envio, daemon=True).start()

    def solicitar_estado_cola(e):
        if not send_ws_msg({"action": "GET_QUEUE_STATUS"}):
            show_snack("La extensión no está conectada.", ft.Colors.RED)
        else:
            lbl_imagen_status.value = "Solicitando estado de la cola..."
            page.update()

    tile_imagen = ft.Card(
        col={"md": 4},
        content=ft.Container(
            padding=20,
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.IMAGE, color=ft.Colors.TEAL_600),
                    ft.Text("GENERACIÓN DE IMÁGENES", weight="bold"),
                ]),
                ft.Divider(),
                switch_auto_send,
                ft.Row([dropdown_imagen_model, dropdown_imagen_count]),
                dropdown_imagen_aspect,
                ft.Divider(),
                lbl_imagen_status,
                ft.Row([
                    ft.ElevatedButton(
                        "Enviar Prompts",
                        icon=ft.Icons.SEND,
                        on_click=enviar_prompts_manualmente,
                        expand=True,
                        bgcolor=ft.Colors.TEAL_700,
                        color="white",
                    ),
                    ft.IconButton(
                        ft.Icons.INFO_OUTLINE,
                        on_click=solicitar_estado_cola,
                        tooltip="Ver estado de la cola",
                        icon_color=ft.Colors.TEAL_700,
                        bgcolor=ft.Colors.TEAL_50,
                    ),
                ]),
            ]),
        ),
    )
```

---

### 1.7 — Agregar `tile_imagen` al `page.add()`

**Localizar** al final de `main()` la llamada a `page.add()`:

```python
    page.add(
        ft.Row([...]),
        ft.ResponsiveRow([tile_gestion, tile_flujo, tile_config, tile_web_extension]),
        ft.ResponsiveRow([tile_prompts]),
    )
```

**Reemplazar la segunda línea** para incluir `tile_imagen`:

```python
    page.add(
        ft.Row([...]),
        ft.ResponsiveRow([tile_gestion, tile_flujo, tile_config, tile_web_extension, tile_imagen]),
        ft.ResponsiveRow([tile_prompts]),
    )
```

> **Nota:** Si la fila queda muy cargada visualmente, mover `tile_imagen` a una fila separada:
> ```python
> ft.ResponsiveRow([tile_web_extension, tile_imagen]),
> ```

---

## Archivo 2: `background.js` (extensión Chrome)

### 2.1 — Agregar cliente WebSocket al final del archivo

**Localizar** la última línea funcional del archivo. Es el bloque de funciones `q`, `$`, `I`, `_` de zoom y cache al final del service worker.

**Agregar al final del archivo**, después de todos los handlers existentes:

```javascript
// ── WebSocket client: conexión a Clusiv-Auto Python (localhost:8765) ──────────

let _pySocket = null;
let _pyReconnectTimer = null;
let _pyConnecting = false;

function _connectToPython() {
  if (_pyConnecting || (_pySocket && _pySocket.readyState === WebSocket.OPEN)) return;
  _pyConnecting = true;

  try {
    _pySocket = new WebSocket("ws://localhost:8765");

    _pySocket.onopen = () => {
      _pyConnecting = false;
      clearTimeout(_pyReconnectTimer);
      console.log("✅ [ClusivBridge] Conectado a Clusiv-Auto Python");
      _pySocket.send(JSON.stringify({
        action: "EXTENSION_CONNECTED",
        version: chrome.runtime.getManifest().version,
      }));
    };

    _pySocket.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);
        await _handlePythonMessage(data);
      } catch (err) {
        console.error("❌ [ClusivBridge] Error parseando mensaje:", err);
      }
    };

    _pySocket.onclose = () => {
      _pyConnecting = false;
      console.log("🔴 [ClusivBridge] Desconectado. Reintentando en 5s...");
      _pyReconnectTimer = setTimeout(_connectToPython, 5000);
    };

    _pySocket.onerror = (err) => {
      console.warn("⚠️ [ClusivBridge] Error de WebSocket:", err.message || err);
      _pyConnecting = false;
      _pySocket.close();
    };

  } catch (err) {
    _pyConnecting = false;
    console.error("❌ [ClusivBridge] No se pudo crear WebSocket:", err);
    _pyReconnectTimer = setTimeout(_connectToPython, 5000);
  }
}

async function _handlePythonMessage(data) {
  const action = data.action;

  if (action === "QUEUE_IMAGE_PROMPTS") {
    const tasks = data.tasks || [];
    if (!tasks.length) {
      _sendStatusToPython("error", "Se recibió QUEUE_IMAGE_PROMPTS sin tareas.");
      return;
    }

    try {
      // Cargar las tareas en la cola existente de IndexedDB
      await _addTasksToQueue(tasks);

      _sendStatusToPython("queued", `${tasks.length} tarea(s) agregadas a la cola`);
      console.log(`✅ [ClusivBridge] ${tasks.length} tareas encoladas`);

      // Si autoStart=true, notificar al content script de labs.google para que comience
      if (data.autoStart) {
        const tabs = await chrome.tabs.query({});
        let notified = false;
        for (const tab of tabs) {
          if (tab.url && (
            tab.url.includes("labs.google/fx/tools/flow") ||
            tab.url.includes("labs.google/fx/") && tab.url.includes("/tools/flow")
          )) {
            chrome.tabs.sendMessage(tab.id, { action: "startProcessing" }).catch(() => {});
            notified = true;
          }
        }
        if (notified) {
          _sendStatusToPython("processing_started", "Orden de inicio enviada al tab de Google Labs");
        } else {
          console.warn("⚠️ [ClusivBridge] autoStart=true pero no hay tab de labs.google abierto");
        }
      }
    } catch (err) {
      console.error("❌ [ClusivBridge] Error al encolar tareas:", err);
      _sendStatusToPython("error", `Error al encolar tareas: ${err.message}`);
    }
  }

  else if (action === "GET_QUEUE_STATUS") {
    try {
      const tasks = await _getAllTasksFromQueue();
      const summary = {
        total: tasks.length,
        pending: tasks.filter(t => t.status === "pending").length,
        processed: tasks.filter(t => t.status === "processed").length,
        current: tasks.filter(t => t.status === "current").length,
        error: tasks.filter(t => t.status === "error").length,
      };
      _sendStatusToPython("queue_status", JSON.stringify(summary));
    } catch (err) {
      _sendStatusToPython("error", `Error al leer la cola: ${err.message}`);
    }
  }
}

function _sendStatusToPython(status, message) {
  if (_pySocket && _pySocket.readyState === WebSocket.OPEN) {
    _pySocket.send(JSON.stringify({ action: "QUEUE_STATUS", status, message }));
  }
}

// ── Helpers para acceder a queueDB desde background ──────────────────────────
// Estos helpers replican la lógica mínima de queueDB.js sin importar el módulo
// (los service workers MV3 no permiten importaciones dinámicas en todos los contextos)

const _QUEUE_DB_NAME = "flowAutomatorDB";
const _QUEUE_STORE   = "tasks";
const _QUEUE_KEY     = "taskQueue";

function _openQueueDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(_QUEUE_DB_NAME, 1);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(_QUEUE_STORE)) {
        db.createObjectStore(_QUEUE_STORE);
      }
    };
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror   = (e) => reject(e.target.error);
  });
}

async function _getAllTasksFromQueue() {
  const db = await _openQueueDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction(_QUEUE_STORE, "readonly");
    const store = tx.objectStore(_QUEUE_STORE);
    const req   = store.get(_QUEUE_KEY);
    req.onsuccess = () => resolve(req.result || []);
    req.onerror   = (e) => reject(e.target.error);
  });
}

async function _addTasksToQueue(newTasks) {
  const db       = await _openQueueDB();
  const existing = await _getAllTasksFromQueue();
  const merged   = [...existing, ...newTasks];

  return new Promise((resolve, reject) => {
    const tx    = db.transaction(_QUEUE_STORE, "readwrite");
    const store = tx.objectStore(_QUEUE_STORE);
    const req   = store.put(merged, _QUEUE_KEY);
    req.onsuccess = () => {
      // Notificar al sidepanel que la cola cambió
      chrome.runtime.sendMessage({ action: "queueUpdated" }).catch(() => {});
      resolve(merged);
    };
    req.onerror = (e) => reject(e.target.error);
  });
}

// Iniciar conexión al arrancar el service worker
_connectToPython();
```

> **Importante:** Los nombres de la base de datos (`flowAutomatorDB`), el object store (`tasks`) y la clave (`taskQueue`) **deben coincidir exactamente** con los que usa `queueDB.js`. El agente debe verificar estos valores antes de escribir el código inspeccionando el archivo `queueDB.js` del repositorio. Si los valores difieren, actualizar las constantes `_QUEUE_DB_NAME`, `_QUEUE_STORE` y `_QUEUE_KEY` según lo que encuentre.

---

## Archivo 3: `queueDB.js` (extensión Chrome)

### 3.1 — Verificar los nombres internos de la base de datos

Antes de modificar, el agente debe abrir `queueDB.js` y encontrar:
- El nombre de la base de datos (`indexedDB.open(...)`)
- El nombre del object store
- La clave bajo la que se guarda el array de tareas

Anotar estos tres valores. Si difieren de los usados en el paso 2.1, actualizar las constantes del `background.js`.

### 3.2 — Agregar la función `addTasks()`

**Localizar** en `queueDB.js` la función que guarda la lista de tareas (probablemente llamada `saveTasks` o similar — buscar `put(` o el equivalente de escritura). Agregar **antes de la línea `export`** al final del archivo:

```javascript
export async function addTasks(newTasks) {
  if (!Array.isArray(newTasks) || newTasks.length === 0) return;
  const existing = await getAllTasks();   // usar la función que ya existe en queueDB.js
  const merged   = [...existing, ...newTasks];
  await saveTasks(merged);               // usar la función de escritura que ya existe
  chrome.runtime.sendMessage({ action: "queueUpdated" }).catch(() => {});
  return merged;
}
```

> **Nota:** Los nombres `getAllTasks` y `saveTasks` son ejemplos. El agente debe verificar los nombres reales en `queueDB.js` e igualarlos. La lógica es: leer el array existente, concatenar las tareas nuevas, guardar el resultado, y notificar con `queueUpdated`.

---

## Verificación post-cambios

### En Python (Clusiv-Auto)

- [ ] El servidor WebSocket arranca sin errores en `localhost:8765`
- [ ] En el log aparece "🔗 Flow Image Automator v2.0.1 conectado y listo." al abrir el navegador con la extensión activa
- [ ] La tarjeta "GENERACIÓN DE IMÁGENES" aparece en la UI
- [ ] Al hacer click en "Enviar Prompts" con un proyecto que tenga `prompts_imagenes.txt`, el log muestra "✅ N prompt(s) enviados correctamente"
- [ ] La extensión responde con "🖼️ Extensión confirmó encolar: N tarea(s) agregadas a la cola"
- [ ] Al activar `switch_auto_send` y ejecutar el flujo completo hasta AI Studio, los prompts se envían automáticamente al final sin intervención manual
- [ ] `config_automatizacion.json` contiene los nuevos campos `auto_send_to_extension`, `imagen_model`, `imagen_aspect_ratio`, `imagen_count` dentro de `"ai_studio": {}`

### En la extensión Chrome

- [ ] No hay errores en la consola del service worker (`chrome://extensions` → Inspect Service Worker)
- [ ] En la consola del service worker aparece "✅ [ClusivBridge] Conectado a Clusiv-Auto Python" al abrir el navegador
- [ ] Si Python no está corriendo, aparece "🔴 [ClusivBridge] Desconectado. Reintentando en 5s..." y se reintenta automáticamente
- [ ] Al recibir `QUEUE_IMAGE_PROMPTS`, las tareas aparecen en el Task Manager de la extensión
- [ ] El Task Manager muestra las tareas con `status: "pending"` antes de procesar
- [ ] Si hay una pestaña de `labs.google/fx/tools/flow` abierta, el procesamiento comienza automáticamente
- [ ] El sidepanel se actualiza en tiempo real cuando llegan nuevas tareas

---

## Troubleshooting

### La extensión no se conecta al servidor Python

1. Verificar que `clusiv-auto.py` está corriendo (el servidor WS arranca al importar el módulo)
2. En la consola del service worker, ejecutar:
   ```js
   fetch("http://localhost:8765").catch(e => console.log(e.message))
   ```
   Si dice "Failed to fetch" en lugar de un error de WS, el servidor no está escuchando
3. Verificar que no hay firewall bloqueando `localhost:8765`
4. El objeto `_pySocket` se puede inspeccionar desde la consola del service worker:
   ```js
   console.log(_pySocket?.readyState)  // 1 = OPEN, 3 = CLOSED
   ```

### Las tareas se agregan a IndexedDB pero el sidepanel no se actualiza

- Verificar que el mensaje `queueUpdated` llega al sidepanel: en la consola del sidepanel ejecutar:
  ```js
  chrome.runtime.onMessage.addListener((msg) => { if(msg.action === "queueUpdated") console.log("✅ queueUpdated recibido"); });
  ```
- Si no llega, revisar que `chrome.runtime.sendMessage({ action: "queueUpdated" })` se ejecuta después de `addTasks()`

### Los nombres de la base de datos no coinciden

Si `background.js` y `queueDB.js` usan bases de datos diferentes, habrá dos bases separadas y el sidepanel no verá las tareas de Python. Para diagnosticarlo, en la consola del service worker:
```js
indexedDB.databases().then(dbs => console.log(dbs))
```
Esto lista todas las bases. Identificar cuál usa el sidepanel (la que existía antes de este cambio) y usar ese nombre en las constantes de `background.js`.

### `addTasks()` en `queueDB.js` no exporta correctamente

Si el archivo usa `export {}` al final en lugar de `export function`, agregar `addTasks` dentro del bloque de exports existente en lugar de agregar un `export` nuevo.

---

## Notas sobre el formato del archivo de prompts (`prompts_imagenes.txt`)

El parser de Python (`send_image_prompts_to_extension`) trata cada línea no vacía como un prompt independiente. Las líneas que empiezan con `#` se ignoran (sirven para comentarios). Ejemplo de archivo válido:

```
# Prompts generados por AI Studio para video 42
A majestic mountain range at golden hour, cinematic lighting, 8k photography
A futuristic city skyline at night, neon lights reflecting on rain-soaked streets
An ancient forest with bioluminescent mushrooms, ethereal atmosphere
```

Esto generará 3 tareas de imagen. El agente NO necesita modificar el formato del archivo — solo el parser Python y el receptor en `background.js`.
