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
- El botón "Orientación 3D" de la cabecera abre una ventana aparte con el cohete en 3D, adaptado
  de [Rocket-orientation-visualization](https://github.com/voltia999/Rocket-orientation-visualization).
  Se pinta con QPainter (sin navegador ni OpenGL). Usa la inclinación del DMP y el rumbo del
  giróscopio integrado (`store.ViewOrientation`): el rumbo del DMP depende del magnetómetro y se
  desvía decenas de grados en segundos con la placa quieta. "Centrar vista", con el cohete en
  vertical y la cara de componentes de la placa hacia ti, orienta la vista desde donde estás.
  Arrastrar con el ratón gira la vista; doble clic la devuelve a la inicial.
- F11 pone a pantalla completa la ventana activa (la principal o la 3D); Esc la quita.
- "Fijar rampa" (bloque Medidas): con el cohete en la rampa, la altitud actual (media de 2 s) pasa
  a ser 0 y se borran el apogeo y la aceleración máxima acumulados en tierra, para que en vuelo no
  arrastren la deriva del barómetro durante la espera. No toca la actitud. Los CSV guardan siempre
  la altitud en bruto.
- La fuente Oxanium va en `groundstation/assets/fonts` con su licencia (SIL OFL 1.1).

## Tests

```bash
uv run pytest
```

Las rutas de los tests están en `pyproject.toml`.
