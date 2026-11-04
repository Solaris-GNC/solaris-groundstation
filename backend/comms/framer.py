import logging
from .crc import crc16_ccitt

logger = logging.getLogger(__name__)

class SPPFramer:

    HEADER_SIZE = 12
    PAYLOAD_SIZE = 50
    CRC_SIZE = 2
    FRAME_SIZE = HEADER_SIZE + PAYLOAD_SIZE + CRC_SIZE

    def extract(self, buffer):

        while True:

            raw_data = buffer.peek()                                            # Devuelve todos los bytes que hay en buffer inmutabilizados

            if (len(raw_data) < self.FRAME_SIZE):                               # Descartamos trama incompleta
                return None
            
            else:
                frame = raw_data[:self.FRAME_SIZE]                              # Seccionamos y clasificamos la trama bruta
                data = frame[:-self.CRC_SIZE]
                crc_received = int.from_bytes(frame[-self.CRC_SIZE:], "little")

                crc_calculated = crc16_ccitt(data)                              # Verificamos crc, si corrupto -> sincronizamos
                if (crc_received != crc_calculated):
                    logger.warning("CRC inválido, resincronizando (descarto 1 byte)")
                    buffer.consume(1)
                    continue

                else:
                    buffer.consume(self.FRAME_SIZE)
                    return frame

