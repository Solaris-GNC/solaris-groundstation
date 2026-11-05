"""Hilo de lectura: puerto serie (o un log grabado) -> paquetes decodificados en una cola.

Reutiliza el pipeline del backend (UART, framer, decoder) y, en directo, también el router,
que guarda los CSV en logs/ y comprueba la secuencia.
"""

import logging
import queue
import threading
import time
from pathlib import Path

from backend.comms.framer import SPPFramer
from backend.comms.packet_buffer import PacketBuffer
from backend.comms.uart import UART
from backend.telemetry.decoder import Decoder

logger = logging.getLogger(__name__)

DISCARD_REPORT_S = 10.0   # Los paquetes descartados se resumen en un aviso cada tantos segundos


class DiscardReport:
    """Avisa del primer paquete descartado y resume el resto cada DISCARD_REPORT_S: si el firmware
    manda algo que no entendemos de forma continua, no se llena la consola de avisos."""

    def __init__(self):
        self.count = 0
        self.last_reason = ""
        self.next_report = 0.0

    def add(self, reason: str):
        now = time.monotonic()
        self.count += 1
        self.last_reason = reason
        if now >= self.next_report:
            extra = f" (y {self.count - 1} más en los últimos {DISCARD_REPORT_S:.0f} s)" if self.count > 1 else ""
            logger.warning(f"Paquete descartado: {reason}{extra}")
            self.count = 0
            self.next_report = now + DISCARD_REPORT_S


class ReplayReader:
    """Reproduce un raw_uart_* de logs/ (una trama en hexadecimal por línea) a un ritmo fijo."""

    def __init__(self, path: Path, fps: float, loop: bool = True):
        self.frames = []
        for line in path.read_text(errors="replace").splitlines():
            try:
                if line.strip():
                    self.frames.append(bytes.fromhex(line))
            except ValueError:
                pass                     # Línea dañada (log cortado, editado a mano): se salta
        if not self.frames:
            raise ValueError(f"{path} no tiene ninguna trama")
        self.period = 1 / fps
        self.loop = loop
        self.index = 0
        self.next_at = time.monotonic()
        self.connected_port = f"repetición {path.name}"

    @property
    def connected(self) -> bool:
        return self.loop or self.index < len(self.frames)

    def read(self) -> bytes:
        delay = self.next_at - time.monotonic()
        if delay > 0:
            time.sleep(min(delay, 0.1))
            return b""
        if not self.connected:
            time.sleep(0.1)
            return b""
        frame = self.frames[self.index % len(self.frames)]
        self.index += 1
        self.next_at += self.period
        return frame


class TelemetrySource(threading.Thread):
    """Lee sin parar y deja cada TelemetryPacket en self.packets para la interfaz."""

    def __init__(self, port: str | None = None, baud_rate: int = 9600,
                 replay: Path | None = None, replay_fps: float = 8.0):
        super().__init__(daemon=True, name="telemetry-source")
        self.packets: queue.SimpleQueue = queue.SimpleQueue()
        self.replay = replay is not None
        self.reader = ReplayReader(replay, replay_fps) if replay else UART(port=port, baud_rate=baud_rate)
        self._stop_event = threading.Event()

    @property
    def connected(self) -> bool:
        return self.reader.connected

    @property
    def port(self) -> str | None:
        return self.reader.connected_port

    def stop(self):
        """Para el hilo y espera a que cierre los ficheros de logs/."""
        self._stop_event.set()
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout=2.0)

    def _handle_frame(self, frame, decoder, router, raw_logger, discards):
        """Una trama con CRC válido: log en bruto, decodificar, pantalla, CSV. Cada paso por
        separado, para que un fallo al guardar no impida ver el paquete (ni al revés)."""
        if raw_logger:
            try:
                raw_logger.log_frame(frame)     # Antes de decodificar: queda aunque no se entienda
            except Exception:
                logger.exception("Error en el log en bruto")
        try:
            packet = decoder.frame_to_packet(frame)
        except Exception as e:
            if hasattr(e, "errors"):            # pydantic: qué campo y por qué (p. ej. quat_w NaN)
                err = e.errors()[0]
                reason = f"{e.title}.{'.'.join(map(str, err['loc']))}: {err['msg']}"
            else:
                reason = str(e).splitlines()[0]
            discards.add(reason)
            return
        is_new = True
        if router:
            try:
                is_new = router.route_packet(packet)
            except Exception:
                logger.exception("Error guardando el paquete o comprobando el enlace")
        if is_new:
            self.packets.put(packet)

    def run(self):
        buffer = PacketBuffer()
        framer = SPPFramer()
        decoder = Decoder()
        discards = DiscardReport()
        connections = getattr(self.reader, "connections", 0)

        # En repetición no se pasa por el router: volvería a escribir en logs/ datos que ya están
        router = raw_logger = None
        if not self.replay:
            from backend.recording.raw_logger import raw_logger
            from backend.telemetry.router import global_router as router

        while not self._stop_event.is_set():
            # Cualquier fallo inesperado se registra y se sigue leyendo: si el hilo muriera, la
            # pantalla se quedaría congelada sin avisar (pasaba con el backend web)
            try:
                data = self.reader.read()
                # Tras reconectar, lo que quedara de la conexión anterior es media trama: fuera
                if getattr(self.reader, "connections", 0) != connections:
                    connections = self.reader.connections
                    buffer.clear()
                if data:
                    buffer.write(data)
                while (frame := framer.extract(buffer)) is not None:
                    self._handle_frame(frame, decoder, router, raw_logger, discards)
            except Exception:
                logger.exception("Error inesperado en el hilo de lectura; se sigue leyendo")
                time.sleep(0.5)

        if raw_logger:
            from backend.recording.telemetry_logger import telemetry_logger
            if hasattr(self.reader, "close"):
                self.reader.close()
            raw_logger.close()
            telemetry_logger.close()
