# Solaris · Ground station

Estación de tierra de escritorio para ver la telemetría de Solaris en directo. Es un único programa
que lee el puerto serie del receptor y pinta, sin servidor, sin localhost y sin navegador.
Tema de día y de noche con la fuente Oxanium.

Viene de [solaris-live-telemetry](https://github.com/Software-Solaris/solaris-live-telemetry),
sin el dashboard web.

## Estructura

- `groundstation/`: la app (PySide6 + pyqtgraph).
- `backend/`: lectura del puerto serie, tramas SPP, decoder y CSV en `logs/` (raw_uart, baro, imu,
  fsm, eventos).

## Instalación

Las dependencias se gestionan con [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`).
uv descarga él solo la versión de Python de `.python-version` (3.13): no hace falta instalar Python.

### Linux

**Ubuntu / Debian**

```bash
sudo apt install git curl libxcb-cursor0          # libxcb-cursor0: la necesita Qt para abrir ventanas
curl -LsSf https://astral.sh/uv/install.sh | sh   # instala uv en ~/.local/bin (abre otra terminal)
sudo usermod -aG dialout $USER                    # permiso para el puerto serie (cerrar sesión y volver a entrar)
```

**Fedora**

```bash
sudo dnf install git uv xcb-util-cursor           # xcb-util-cursor: la necesita Qt para abrir ventanas
sudo usermod -aG dialout $USER                    # permiso para el puerto serie (cerrar sesión y volver a entrar)
```

Después, en las dos:

```bash
git clone <url-del-repo> solaris-groundstation
cd solaris-groundstation
uv sync                                           # crea .venv con la app y las herramientas de desarrollo
uv run python -m groundstation                    # busca el receptor solo
```

**Opcional: icono en el dock y en el menú de aplicaciones**

Sin esto la app funciona igual, pero en GNOME el dock enseña un icono genérico (o el de la terminal
desde la que se lanza): desde GNOME 44 el icono solo sale de un `.desktop` instalado. Una vez:

```bash
scripts/install-desktop.sh                         # con uv
scripts/install-desktop.sh --python /ruta/python   # o con otro Python (p. ej. un entorno conda)
```

Escribe `~/.local/share/applications/solaris-groundstation.desktop` apuntando a esta copia del
repo. Desde entonces la insignia de Solaris sale en el dock, aunque se lance desde la terminal, y
la app se puede abrir desde el buscador de aplicaciones como "Solaris Ground Station". Si se mueve
la carpeta del repo hay que repetirlo; para quitarlo: `scripts/install-desktop.sh --uninstall`.

### Windows

En PowerShell:

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e               # o: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Cerrar y volver a abrir PowerShell (para que encuentre `git` y `uv`), y después:

```powershell
git clone <url-del-repo> solaris-groundstation
cd solaris-groundstation
uv sync
uv run python -m groundstation --port COM3
```

- En Windows hay que indicar el puerto: la búsqueda automática solo mira las rutas de Linux
  (`/dev/...`). El número sale en el Administrador de dispositivos, en "Puertos (COM y LPT)".
- Si el receptor no aparece ahí, falta el driver de su chip USB-serie (CP210x o CH340, según
  la placa).

### Gestión de dependencias

Los comandos se lanzan con `uv run` delante (`uv run python -m groundstation`), o activando antes
el entorno: `source .venv/bin/activate` en Linux, `.venv\Scripts\activate` en Windows.

- Añadir una dependencia: `uv add paquete` (desarrollo: `uv add --dev paquete`).
- Actualizar versiones: `uv lock --upgrade` y `uv sync`.
- `uv.lock` se sube al repo: así todos instalan exactamente las mismas versiones.

## Uso

Desde la raíz del repo:

```bash
uv run python -m groundstation                     # busca el receptor solo
uv run python -m groundstation --port /dev/serial/by-id/usb-...   # Windows: --port COM3
uv run python -m groundstation --replay logs/raw_uart_AAAAMMDD_HHMMSS   # repite un log grabado
```

- Sin `--port` se usa el primer puerto de `/dev/serial/by-id/`, y si no hay ninguno `/dev/ttyUSB*`
  o `/dev/ttyACM*`. Es mejor la ruta de `by-id`: no cambia al desenchufar y volver a enchufar
  (`ttyUSB0` puede volver como `ttyUSB1`).
- Si se desenchufa el receptor, la cabecera muestra "Receptor desconectado" y se reconecta solo.
- `--replay` sirve para probar sin hardware: no escribe nada en `logs/`.
- `--baud` (por defecto 9600), `--replay-fps` (por defecto 8), `--theme light|dark`.

## Tests

```bash
uv run pytest
```

Las rutas de los tests están en `pyproject.toml`.
