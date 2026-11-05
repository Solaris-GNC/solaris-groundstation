import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class RawLogger:
    """Guarda cada trama recibida, en hexadecimal, en logs/raw_uart_<sesión> (una por línea).

    El fichero se abre con la primera trama, no al importar. Si no se puede escribir (sin permisos,
    disco lleno) se avisa una vez y se sigue sin log: la telemetría en pantalla no depende de él.
    """

    def __init__(self, log_dir: str = "logs"):
        self._log_dir = log_dir
        session = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._raw_uart_path = os.path.join(log_dir, f"raw_uart_{session}")
        self._handle = None
        self._failed = False

    def log_frame(self, frame: bytes):
        if self._failed:
            return
        try:
            if self._handle is None:
                os.makedirs(self._log_dir, exist_ok=True)
                self._handle = open(self._raw_uart_path, "w", buffering=1)  # Línea a línea: flush en cada '\n'
            self._handle.write(frame.hex(" ").upper() + "\n")
        except OSError as e:
            self._failed = True
            logger.error(f"No se puede escribir {self._raw_uart_path} ({e}): se sigue sin log en bruto")

    def close(self):
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None


raw_logger = RawLogger()
