"""Estación de tierra de escritorio.

Uso (desde la raíz del repo):
    uv run python -m groundstation                       # busca el receptor solo
    uv run python -m groundstation --port /dev/ttyUSB0
    uv run python -m groundstation --replay logs/raw_uart_AAAAMMDD_HHMMSS   # repite un log grabado
"""

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(prog="groundstation", description="Solaris · estación de tierra")
    parser.add_argument("--port", help="puerto serie del receptor (por defecto se busca solo)")
    parser.add_argument("--baud", type=int, default=9600, help="baudios (por defecto 9600)")
    parser.add_argument("--replay", type=Path, help="repite un raw_uart_* de logs/ en vez de leer el puerto")
    parser.add_argument("--replay-fps", type=float, default=8.0, help="tramas por segundo al repetir")
    parser.add_argument("--theme", choices=["light", "dark"], help="modo de color inicial")
    args = parser.parse_args()
    replay = args.replay.resolve() if args.replay else None

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # El backend escribe sus CSV en "logs/" relativo al directorio actual: igual que con uvicorn,
    # se trabaja desde la raíz del repo
    os.chdir(REPO)
    (REPO / "logs").mkdir(exist_ok=True)
    sys.path.insert(0, str(REPO))

    import pyqtgraph as pg
    from PySide6.QtWidgets import QApplication

    from .source import TelemetrySource
    from .theme import load_font
    from .window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Solaris Ground Station")
    # segmentedLineMode: con antialiasing, Qt pinta muy despacio las líneas de más de 1 px
    # (250 ms frente a 12 ms con 50 000 puntos); por segmentos va igual de bien
    pg.setConfigOptions(antialias=True, segmentedLineMode="on")
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C en la terminal cierra la app

    source = TelemetrySource(port=args.port, baud_rate=args.baud, replay=replay, replay_fps=args.replay_fps)
    source.start()
    window = MainWindow(source, load_font(), args.theme)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
