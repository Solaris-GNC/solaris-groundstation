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
uv descarga él solo la versión de Python de `.python-version` (3.13).

```bash
sudo dnf install uv              # o: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync                          # crea .venv con la app y las herramientas de desarrollo
```

Los comandos de abajo se lanzan con `uv run` delante (`uv run python -m groundstation`), o
activando antes el entorno con `source .venv/bin/activate`.

- Añadir una dependencia: `uv add paquete` (desarrollo: `uv add --dev paquete`).
- Actualizar versiones: `uv lock --upgrade` y `uv sync`.
- `uv.lock` se sube al repo: así todos instalan exactamente las mismas versiones.

## Uso

Desde la raíz del repo:

```bash
uv run python -m groundstation                     # busca el receptor solo
uv run python -m groundstation --port /dev/serial/by-id/usb-...
uv run python -m groundstation --replay logs/raw_uart_AAAAMMDD_HHMMSS   # repite un log grabado
```

- Sin `--port` se usa el primer puerto de `/dev/serial/by-id/`, y si no hay ninguno `/dev/ttyUSB*`
  o `/dev/ttyACM*`. Es mejor la ruta de `by-id`: no cambia al desenchufar y volver a enchufar
  (`ttyUSB0` puede volver como `ttyUSB1`).
- Si se desenchufa el receptor, la cabecera muestra "Receptor desconectado" y se reconecta solo.
- `--replay` sirve para probar sin hardware: no escribe nada en `logs/`.
- `--baud` (por defecto 9600), `--replay-fps` (por defecto 8), `--theme light|dark`.

## Notas

- Llega cada paquete a la pantalla, sin pasar por un servidor.
- Las gráficas reciben solo la ventana visible y se repintan solo con datos nuevos. Si repintar
  tarda (sesiones muy largas en "Todo"), se repinta menos a menudo en vez de congelarse.
- El mapa GPS aún no está: el firmware no envía posición.
- La fuente Oxanium va en `groundstation/assets/fonts` con su licencia (SIL OFL 1.1).

## Tests

```bash
uv run pytest
```

Las rutas de los tests están en `pyproject.toml`.
