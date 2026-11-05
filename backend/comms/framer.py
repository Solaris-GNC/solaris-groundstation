import logging
from .crc import crc16_ccitt

logger = logging.getLogger(__name__)


class SPPFramer:
    """Saca tramas SPP de tamaño fijo del buffer de recepción.

    No hay palabra de sincronía: una trama es válida si su CRC cuadra. Si no cuadra (bytes
    perdidos, ruido, se empezó a escuchar a mitad de trama), se descarta un byte y se prueba en la
    siguiente posición hasta volver a cuadrar. Las tramas que llegan partidas en varias lecturas se
    esperan: solo se miran cuando hay una trama completa en el buffer.
    """

    HEADER_SIZE = 12
    PAYLOAD_SIZE = 50
    CRC_SIZE = 2
    FRAME_SIZE = HEADER_SIZE + PAYLOAD_SIZE + CRC_SIZE

    def __init__(self):
        self.discarded = 0          # Bytes descartados en la resincronización en curso
        self.discarded_total = 0    # En toda la sesión (para diagnóstico)

    def extract(self, buffer):
        """Devuelve la siguiente trama válida (bytes), o None si aún no hay una completa."""
        while buffer.size() >= self.FRAME_SIZE:
            frame = buffer.peek(self.FRAME_SIZE)
            crc_received = int.from_bytes(frame[-self.CRC_SIZE:], "little")
            if crc16_ccitt(frame[:-self.CRC_SIZE]) == crc_received:
                buffer.consume(self.FRAME_SIZE)
                if self.discarded:
                    # Un solo aviso por resincronización, no uno por byte (con ruido eran miles)
                    logger.warning(f"Resincronizado: descartados {self.discarded} bytes sin trama válida")
                    self.discarded = 0
                return frame
            buffer.consume(1)
            self.discarded += 1
            self.discarded_total += 1
        return None
