import glob
import logging
import time

import serial

logger = logging.getLogger(__name__)                                            # Guardamos el logger de este archivo

# Rutas donde buscar el receptor si no se indica puerto. /dev/serial/by-id/ va primero: su nombre
# no cambia al desenchufar y volver a enchufar (ttyUSB0 puede volver como ttyUSB1)
AUTO_PORT_PATTERNS = ["/dev/serial/by-id/*", "/dev/ttyUSB*", "/dev/ttyACM*"]


def find_port() -> str | None:
    for pattern in AUTO_PORT_PATTERNS:
        ports = sorted(glob.glob(pattern))
        if ports:
            return ports[0]
    return None


class UART:

    def __init__(self, port: str | None = None, baud_rate: int = 115200, timeout: float = 0.1,
                 reconnect_delay: float = 1.0):                                 # port=None: se busca solo (find_port)
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.reconnect_delay = reconnect_delay
        self._ser = None                                                        # Es el parametro donde guardaremos el objeto Serial
        self.connected_port: str | None = None                                  # Puerto abierto ahora mismo (None = desconectado)

    @property
    def connected(self) -> bool:
        return self._ser is not None

    def _connect(self) -> bool:
        # Un solo intento: si falla se espera y se vuelve al bucle de lectura, que así no se queda
        # bloqueado aquí y puede informar del estado
        port = self.port or find_port()
        if port is None:
            logger.warning(f"No se pudo abrir ningún puerto (no hay receptor conectado). "
                           f"Reintentando en {self.reconnect_delay}s…")
            time.sleep(self.reconnect_delay)
            return False
        try:
            self._ser = serial.Serial(port, self.baud_rate, timeout=self.timeout)
            self.connected_port = port
            logger.info(f"UART conectado: {port} @ {self.baud_rate} baud")
            return True
        except (serial.SerialException, OSError) as e:
            logger.warning(f"No se pudo abrir {port} ({e}). "
                           f"Reintentando en {self.reconnect_delay}s…")
            time.sleep(self.reconnect_delay)                                    # Critico!
            return False

    def read(self) -> bytes:
        if self._ser is None and not self._connect():                           # Comprueba si comunicacion serie esta asignada a _ser, NO si tiene datos
            return b""
        try:
            n = self._ser.in_waiting
            if n:                                                               # Comprobamos si hay datos
                return self._ser.read(size=n)                                   # Lee todo lo que haya en buffer (Serial.read devuelve bytes)
            return self._ser.read(size=1)                                       # Espera un tiempo timeout, si no llega nada, devuelve b""
        # Al desenchufar el USB, in_waiting lanza OSError (EIO), no SerialException. Si no se
        # captura, el hilo de lectura muere y no se vuelven a recibir datos hasta reiniciar
        except (serial.SerialException, OSError) as e:
            logger.warning(f"UART desconectado ({e}). Reconectando…")
            self.close()
            return b""

    def close(self):
        if self._ser is not None:
            try:
                self._ser.close()
            except (serial.SerialException, OSError):
                pass
            self._ser = None                                                    # Una vez cierras conexion vacias _ser para poder abrir conexion de nuevo en futuro
            self.connected_port = None
