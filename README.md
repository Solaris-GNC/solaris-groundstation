# Solaris · Ground station

Estación de tierra de escritorio para ver la telemetría de Solaris en directo. Es un único programa
que lee el puerto serie del receptor y pinta, sin servidor, sin localhost y sin navegador.
Tema de día y de noche con la fuente Oxanium.

## Estructura

- `groundstation/`: la app (PySide6 + pyqtgraph).
- `sdcard/`: volcado y análisis de la SD de vuelo (`python -m sdcard`, ver más abajo).
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
git clone https://github.com/Solaris-GNC/solaris-groundstation.git
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

## Datos de la SD de vuelo

En vuelo el datalogger guarda cada paquete SPP (64 B) en sectores crudos de la SD, sin particiones
ni sistema de ficheros, a partir del sector 16384. Después del vuelo, con la SD metida en el
ordenador:

```bash
uv run python -m sdcard                         # busca la SD, la vuelca, saca los CSV y el apogeo
uv run python -m sdcard --device /dev/sda       # sin buscar la SD
uv run python -m sdcard --bin spp_dump.bin      # analizar un volcado hecho a mano con dd
```

- **Búsqueda de la SD:** solo cuenta un disco extraíble sin nada montado (la SD de vuelo no tiene
  sistema de ficheros, así que nunca se monta), y solo se da por buena si en el sector 16384 hay
  tramas SPP con CRC válido. Antes de volcar pregunta (`-y` para no preguntar). Del disco solo se
  lee, nunca se escribe en él. Pide la contraseña de sudo para leer `/dev/sdX`.
- **Volcado:** lee desde el sector 16384 hasta que hay 16 MiB seguidos sin datos (`--stop-empty-mib`)
  o hasta 1 GiB (`--max-mib`). No hace falta calcular cuántos MiB ocupa el vuelo.
- **Salida** en `logs/sd_AAAAMMDD_HHMMSS/`: `spp_dump.bin`, los CSV de BARO, IMU y FSM (el mismo
  formato que en directo), `apogeo.txt` y `altitud.png`. El apogeo sale resaltado en la terminal y
  en una ventana con la gráfica de altitud (`--no-plot` para no abrirla).
- **Apogeo:** máximo de la altitud del barómetro tras un filtro de mediana de 5 muestras (un pico
  suelto no cuenta), sobre la altitud de la rampa (mediana de las 50 primeras muestras). El T+
  cuenta desde la última vez que la altitud estuvo a menos de 5 m de la rampa.
- **Sesiones:** cada arranque de la placa vuelve a escribir desde el sector 16384, así que detrás
  del último vuelo pueden quedar restos de arranques anteriores. Se separan cuando el tiempo del
  firmware retrocede, el seq de un sensor no avanza o hay un hueco de sectores vacíos, y se analiza
  la 1 (el último arranque) salvo `--session N`. Unos restos que encajen en tiempo y seq no se
  pueden separar; solo se avisa del salto de tiempo. Lo seguro es borrar la SD antes de cada vuelo.
- `--bin` da por hecho que el volcado empieza en el sector 16384 (`skip=16384` en dd). Si no,
  indicar el sector de inicio con `--first-sector`.

## Tests

```bash
uv run pytest
```

Las rutas de los tests están en `pyproject.toml`.
