import logging

logger = logging.getLogger(__name__)


class PacketBuffer:
    """Bytes recibidos del puerto serie a la espera de formar una trama.

    Tiene un tope (max_size): si llega más de lo que el framer consume (ruido continuo, el hilo
    atascado), se descartan los bytes más antiguos en vez de crecer sin límite.
    """

    def __init__(self, max_size: int = 64 * 1024):
        self.buffer = bytearray()               # Version mutable de "bytes"
        self.max_size = max_size
        self.dropped = 0                        # Bytes descartados por el tope (para diagnóstico)

    def write(self, data: bytes):
        self.buffer.extend(data)
        excess = len(self.buffer) - self.max_size
        if excess > 0:
            del self.buffer[:excess]
            self.dropped += excess
            logger.warning(f"Buffer de recepción lleno: descartados {excess} bytes antiguos")

    def size(self):
        return len(self.buffer)

    def consume(self, n: int):
        del self.buffer[:n]

    def clear(self):
        self.buffer.clear()

    def peek(self, n: int | None = None) -> bytes:
        """Copia (inmutable) de los primeros n bytes, o de todo el buffer si n es None."""
        return bytes(self.buffer if n is None else self.buffer[:n])
