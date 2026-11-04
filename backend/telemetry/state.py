from typing import Optional, Dict, Any, List
from threading import Lock
from .models import BAROPacket, IMUPacket, FSMPacket, LogLevel, LogEntry
from .motion import MotionEstimator

# ==================================================================
class TelemetryState:
    def __init__(self):
        self.motion = MotionEstimator()
        self._lock = Lock()
        # Últimos valores conocidos
        self.latest_baro: Optional[BAROPacket] = None
        self.latest_imu: Optional[IMUPacket] = None
        self.latest_baro_ts: Optional[int] = None       # timestamp_ms del firmware de cada muestra
        self.latest_imu_ts: Optional[int] = None
        self.latest_fsm: Optional[FSMPacket] = None     # Init bits del último arranque
        self.latest_fsm_ts: Optional[int] = None
        self.logs: List[LogEntry] = []  # Últimos logs del sistema
        self.packets_lost: int = 0

# ==================================================================
# Updates:
    def update_fsm(self, packet: FSMPacket, timestamp_ms: int):
        with self._lock:
            self.latest_fsm = packet
            self.latest_fsm_ts = timestamp_ms

    def update_baro(self, packet: BAROPacket, timestamp_ms: int):
        with self._lock:
            self.latest_baro = packet
            self.latest_baro_ts = timestamp_ms

    def update_imu(self, packet: IMUPacket, timestamp_ms: int):
        with self._lock:
            self.latest_imu = packet
            self.latest_imu_ts = timestamp_ms

            self.motion.update(
                timestamp_ms=timestamp_ms,
                ax_g=packet.accel_x,
                ay_g=packet.accel_y,
                az_g=packet.accel_z,
            )
            
    # def update_imu1(self, packet: IMUPacket1, timestamp_ms: int):
    #     with self._lock:
    #         self.latest_imu1 = packet

    #         self.motion.update(
    #             timestamp_ms=timestamp_ms,
    #             ax_g=packet.accel_x,
    #             ay_g=packet.accel_y,
    #             az_g=packet.accel_z,
    #         )

    # def update_imu2(self, packet: IMUPacket2):
    #     with self._lock:
    #         self.latest_imu2 = packet

    def add_log(self, message: str, level: LogLevel = LogLevel.INFO, timestamp_ms=None):
        with self._lock:
            self.logs.append(LogEntry(level=level, message=message, timestamp_ms=timestamp_ms))
            if len(self.logs) > 50:  # Se mantienen los últimos 50 logs en la RAM
                self.logs.pop(0)

    def add_lost_packets(self, count: int):
        with self._lock:
            self.packets_lost += count

# ==================================================================
# Foto del último estado:
    def current_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                # timestamp_ms permite al frontend dibujar contra el tiempo del firmware
                # y descartar las muestras repetidas entre envíos
                "baro":   ({**self.latest_baro.model_dump(), "timestamp_ms": self.latest_baro_ts}
                           if self.latest_baro else None),
                "imu":    ({**self.latest_imu.model_dump(), "timestamp_ms": self.latest_imu_ts}
                           if self.latest_imu else None),
                "fsm":    ({**self.latest_fsm.model_dump(), "timestamp_ms": self.latest_fsm_ts}
                           if self.latest_fsm else None),
                # "imu1":   self.latest_imu1.model_dump()   if self.latest_imu1   else None,
                # "imu2":   self.latest_imu2.model_dump()   if self.latest_imu2   else None,
                "motion": self.motion.snapshot(),
                "logs":   [l.model_dump() for l in self.logs],
                "packets_lost": self.packets_lost,
            }

# ==================================================================
global_state = TelemetryState()
