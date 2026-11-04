# Solaris · Ground station

Estación de tierra de escritorio para ver la telemetría de Solaris en directo. Es un único programa
que lee el puerto serie del receptor y pinta, sin servidor, sin localhost y sin navegador.
Tema de día y de noche con la fuente Oxanium.

Viene de [solaris-live-telemetry](https://github.com/Software-Solaris/solaris-live-telemetry),
sin el dashboard web.

## Estructura

- `groundstation/`: la app (PySide6 + pyqtgraph).
- `backend/`: lectura del puerto serie, tramas SPP, decoder y CSV en `logs/` (raw_uart, baro, imu,
  fsm, eventos). Conserva el servidor FastAPI (`backend/main.py`), que la app no necesita.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r groundstation/requirements.txt
```

## Uso

Desde la raíz del repo:

```bash
python -m groundstation                     # busca el receptor solo
python -m groundstation --port /dev/serial/by-id/usb-...
python -m groundstation --replay logs/raw_uart_20261104_204244   # repite un log grabado
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
python -m pytest groundstation/tests backend/tests/comms
```
