import os
import logging
from datetime import datetime



class RawLogger():
    def __init__(self, log_dir:str = "logs"):

        self._log_dir = log_dir

        session = datetime.now().strftime("%Y%m%d_%H%M%S")

        self._raw_uart_path = os.path.join(log_dir, f"raw_uart_{session}")

        self._handle = open( self._raw_uart_path, "w", buffering=1)


    def log_frame(self, frame: bytes ):
        self._handle.write(frame.hex(" ").upper())
        self._handle.write("\n")

    def close(self):
        self._handle.close()

raw_logger = RawLogger()