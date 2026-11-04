import logging
import time
from threading import Thread
import pandas as pd
from pathlib import Path



from backend.comms.packet_buffer import PacketBuffer
from backend.comms.framer import SPPFramer
from backend.telemetry.decoder import Decoder
from backend.telemetry.router import global_router
from backend.fake_stream import make_imu_frames, make_baro_frame
from backend.api.websocket import app          # la app FastAPI (con el endpoint /ws)

logger = logging.getLogger(__name__)

IMU_HZ = 230        # ritmo real de la IMU
BARO_HZ = 50        # ritmo real del barómetro
TICK_S = 1.0 / IMU_HZ   # el bucle corre al ritmo del sensor más rápido (la IMU)

LOG = Path(__file__).parent.parent / "data" / "log_uart.txt"



def pipeline_loop():

    #uart = UART(port=, baud_rate=)
    buffer = PacketBuffer()
    framer = SPPFramer()
    decoder = Decoder()

    hex_text = LOG.read_text()
    data = bytes.fromhex(hex_text) 
    buffer = PacketBuffer()
    buffer.write(data) 
    
    packets = []

    while (frame := framer.extract(buffer)) is not None:
        
            packet = decoder.frame_to_packet(frame)
            global_router.route_packet(packet)
            packets.append(packet)

if __name__ == "__main__":
    pipeline_loop()

@app.on_event("startup")
def start_pipeline():
    Thread(target=pipeline_loop, daemon=True).start()
