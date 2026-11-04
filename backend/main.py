import logging
import os
import time
from threading import Thread

from .comms.packet_buffer import PacketBuffer
from .comms.framer import SPPFramer
from .comms.uart import UART
from .recording.raw_logger import raw_logger
from .telemetry.decoder import Decoder
from .telemetry.router import global_router
from .fake_stream import make_imu_frames, make_baro_frame
from .api.websocket import app

logger = logging.getLogger(__name__)

def pipeline_loop():

    # Sin SOLARIS_UART_PORT se busca el receptor solo (ver comms/uart.py)
    uart = UART(port=os.environ.get("SOLARIS_UART_PORT"), baud_rate=9600)
    buffer = PacketBuffer()
    framer = SPPFramer()
    decoder = Decoder()

    while True:
        data = uart.read()
        if data:
            buffer.write(data)

        # Extraer los paquetes completos que haya en el buffer
        drain(buffer, framer, decoder, global_router, raw_logger)

def drain(buffer, framer, decoder, router, raw_logger):
    while(frame := framer.extract(buffer)) is not None:
        try:
            raw_logger.log_frame(frame)
            router.route_packet(decoder.frame_to_packet(frame))
        except Exception as e:
            logger.warning(f"Paquete descartado: {e}")

# if __name__ == "__main__":
#     pipeline_loop()


# Para iniciar: uvicorn backend.main:app --host localhost --port 8008
@app.on_event("startup")
def start_pipeline():
    Thread(target=pipeline_loop, daemon=True).start()

