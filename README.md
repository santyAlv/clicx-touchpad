# ClicX

Usá tu teléfono como **touchpad de laptop** (inspirado en [mouse.ly](https://mouse.ly/)).

- **Emisor:** app React Native (Expo Go / APK)
- **Receptor (host):** Python en Windows → WebSocket + mouse/teclado
- **Red:** Wi‑Fi LAN, QR, o **USB** (`adb reverse`). Sin cloud.

## Estructura

```
clicx/
  mobile/     # Expo app
  receiver/   # Host Python (.exe opcional)
  shared/     # Protocolo JSON
```

## 1. Arrancar el host (PC)

```powershell
cd receiver
pip install -r requirements.txt
python main.py
```

Vas a ver la IP, puerto `51234` y estado. Botones útiles:

- **Mostrar QR** — escanear desde la app
- **Activar USB** — `adb reverse` para cable Android

Si Windows Firewall pregunta, **permití acceso** en redes privadas.

### Build .exe (opcional)

```powershell
cd receiver
.\build-exe.bat
```

El ejecutable queda en `receiver/dist/clicx-host.exe`.

## 2. Arrancar la app

```powershell
cd mobile
npm install
npm run start:fast
```

Escaneá el QR de Metro con **Expo Go** (o usá el APK).

### Conectar

| Modo | Cómo |
| --- | --- |
| **Wi‑Fi** | Misma red · IP del host + puerto `51234` |
| **Escanear QR** | Host → Mostrar QR · app → Escanear QR |
| **Cable USB** | Host → Activar USB · app → Cable USB → Connect (`127.0.0.1`) |
| **Bluetooth** | Anclaje Bluetooth activo · host → elegir la conexión Bluetooth · app → escanear QR |

### USB (Android)

1. Depuración USB activa en el teléfono  
2. `adb` en la PC (platform-tools / PATH)  
3. Host: **Activar USB**  
4. App: **Cable USB** → Connect  

iOS sigue principalmente por Wi‑Fi (sin `adb reverse`).

### Bluetooth

ClicX viaja por Bluetooth usando **anclaje / PAN**: el enlace Bluetooth da una IP y el
protocolo de siempre (WebSocket + UDP) corre encima sin cambios.

1. Emparejá el teléfono con la PC desde la configuración de Bluetooth de Windows
2. Activá el anclaje Bluetooth en el teléfono (*Bluetooth tethering*), o unite a la
   red de área personal desde **Dispositivos Bluetooth → Unirse a una red de área personal**
3. Host: en **Conectar** elegí la conexión Bluetooth de la lista — el QR y la dirección
   pasan a apuntar a esa IP en vez de la de Wi‑Fi
4. App: escaneá el QR

Alcanza para puntero, teclado y deck. El ancho de banda de PAN (~1 Mbps) hace lenta la
transferencia de archivos; para eso conviene Wi‑Fi o cable.

### Centro de control (Fase 1 + Fase 2)

Desde el panel tocá `⌂` para abrir el Centro de control:

- **Trackpad** — panel, gestos y Deck
- **Estado de la PC** — CPU, RAM, disco, batería
- **Acciones** — bloqueo, apagado, capturas
- **Multimedia** — reproducción y volumen
- **Teclado** — F1–F12, atajos y escritura
- **Volumen por app** — ajuste por aplicación
- **Ventanas** — foco, minimizar, restaurar, cerrar
- **Portapapeles** — copiar/pegar entre PC y teléfono (sincronización **OFF** por defecto; historial borrable, nunca se loguea el contenido)
- **Archivos** — enviar desde el teléfono a `%LOCALAPPDATA%\ClicX\From Phone` y recibir la carpeta `From PC` (validación host: paths fijos, límites, cancelación)

### Latencia

Un mouse USB suele ir a 1–8 ms. Por Wi‑Fi + touch la física impone más (~15–40 ms). ClicX mitiga con predicción (`CLICX_PRED_MS`, default 18; `0` para apagar).

```powershell
$env:CLICX_PRED_MS="24"; python main.py
$env:CLICX_PRED_MS="0"; python main.py
```

## Gestos

| Gesto | Acción |
| --- | --- |
| 1 dedo arrastrar | Mover cursor |
| Tap | Click izquierdo |
| Doble tap | Doble click |
| Tap 2 dedos | Click derecho |
| 2 dedos arrastrar | Scroll |
| Pellizco | Zoom (Ctrl + rueda) |
| Mantener + mover | Arrastrar (drag) |
| 3 dedos swipe | Escritorio / Alt+Tab / Win+Tab |
| 3 dedos tap | Búsqueda (Win+S) |
| Barra de atajos | Escritorio, Tareas, Esc |

## Protocolo

Ver [`shared/protocol.md`](shared/protocol.md) y [`shared/examples.json`](shared/examples.json).

## Notas

- Expo Go usa **WebSocket** (compatible sin native modules extra).
- El host solo acepta conexiones en tu LAN / USB reverse; no expongas el puerto a internet.
