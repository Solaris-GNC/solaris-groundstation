from threading import Lock
from typing import List

from .models import LogEntry, LogLevel


# ==================================================================
class TelemetryState:
    """Estado compartido entre el hilo de lectura (router) y la interfaz: eventos y pérdidas."""

    def __init__(self):
        self._lock = Lock()
        self.logs: List[LogEntry] = []  # Últimos logs del sistema
        self.packets_lost: int = 0

    def add_log(self, message: str, level: LogLevel = LogLevel.INFO, timestamp_ms=None):
        with self._lock:
            self.logs.append(LogEntry(level=level, message=message, timestamp_ms=timestamp_ms))
            if len(self.logs) > 50:  # Se mantienen los últimos 50 logs en la RAM
                self.logs.pop(0)

    def add_lost_packets(self, count: int):
        with self._lock:
            self.packets_lost += count


# ==================================================================
global_state = TelemetryState()
