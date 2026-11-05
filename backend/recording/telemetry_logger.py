import os
import logging
from datetime import datetime
from backend.telemetry.models import TelemetryPacket, BAROPacket, IMUPacket, FSMPacket, LogLevel

# ==================================================================
logger = logging.getLogger(__name__)

# ==================================================================
# Cabeceras CSV
BARO_FIELDS = ["timestamp_ms", "seq", "drop_counter", "altitude", "pressure", "temperature"]
# Un solo CSV de IMU; cada paquete IMU (44 B, 11 floats) rellena una fila completa
IMU_FIELDS = ["timestamp_ms", "seq", "drop_counter",
              "accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z",
              "quat_w", "quat_x", "quat_y", "quat_z", "accuracy"]
# Init bits de la FSM: una fila por arranque. "failed" separa los nombres con ';' (el CSV usa ',')
FSM_FIELDS = ["timestamp_ms", "seq", "fsm_errors", "common_errors", "failed"]
EVENTS_FIELDS = ["timestamp_ms", "level", "message"]

# ==================================================================
class TelemetryLogger:
    def __init__(self, log_dir: str = "logs"):
        self._log_dir = log_dir

        # Momento de la sesión (se fija al crear el logger)
        session = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Rutas de cada CSV. Los ficheros NO se crean aquí, sino de forma
        # en la primera escritura.
        self._baro_path = os.path.join(log_dir, f"telemetry_baro_{session}.csv")
        self._imu_path = os.path.join(log_dir, f"telemetry_imu_{session}.csv")
        self._fsm_path = os.path.join(log_dir, f"telemetry_fsm_{session}.csv")
        self._events_path = os.path.join(log_dir, f"telemetry_events_{session}.csv")

        # Cabeceras por fichero, para escribirlas la primera vez que se use
        self._fields = {
            self._baro_path: BARO_FIELDS,
            self._imu_path: IMU_FIELDS,
            self._fsm_path: FSM_FIELDS,
            self._events_path: EVENTS_FIELDS,
        }
        self._handles: dict = {}     

# ==================================================================
    def log_baro(self, packet: TelemetryPacket):
        payload: BAROPacket = packet.payload
        row = {
            "timestamp_ms": packet.secondary_header.timestamp_ms,
            "seq": packet.primary_header.seq,
            "drop_counter": packet.secondary_header.drop_counter,
            "altitude": payload.altitude,
            "pressure": payload.pressure,
            "temperature": payload.temperature,
        }
        self._write_row(self._baro_path, BARO_FIELDS, row)

    def log_imu(self, packet: TelemetryPacket):
        payload: IMUPacket = packet.payload
        row = {
            "timestamp_ms": packet.secondary_header.timestamp_ms,
            "seq": packet.primary_header.seq,
            "drop_counter": packet.secondary_header.drop_counter,
            "accel_x": payload.accel_x, "accel_y": payload.accel_y, "accel_z": payload.accel_z,
            "gyro_x": payload.gyro_x,  "gyro_y":  payload.gyro_y,  "gyro_z":  payload.gyro_z,
            "quat_w": payload.quat_w, "quat_x": payload.quat_x, "quat_y": payload.quat_y,
            "quat_z": payload.quat_z, "accuracy": payload.accuracy,
        }
        self._write_row(self._imu_path, IMU_FIELDS, row)

    def log_fsm(self, packet: TelemetryPacket):
        payload: FSMPacket = packet.payload
        row = {
            "timestamp_ms": packet.secondary_header.timestamp_ms,
            "seq": packet.primary_header.seq,
            "fsm_errors": f"0x{payload.fsm_errors:04X}",
            "common_errors": f"0x{payload.common_errors:04X}",
            "failed": ";".join(payload.failed),
        }
        self._write_row(self._fsm_path, FSM_FIELDS, row)

    def log_event(self, level, message: str, timestamp_ms: float = None):
        row = {
            "timestamp_ms": timestamp_ms,
            "level": getattr(level, "value", level),   # LogLevel.WARNING -> "WARNING"
            "message": message,
        }
        self._write_row(self._events_path, EVENTS_FIELDS, row)

    # ==================================================================

    def _get_handle(self, path: str):
        # Abre el fichero una unica vez (con la cabecera) y reutiliza el handle
        handle = self._handles.get(path)
        if handle is None:
            os.makedirs(self._log_dir, exist_ok=True)
            handle = open(path, "w", buffering=1)          # line-buffered: flush en cada '\n'
            handle.write(",".join(self._fields[path]) + "\n")
            self._handles[path] = handle
        return handle

    def _write_row(self, path: str, fields: list, row: dict) -> None:
        try:
            handle = self._get_handle(path)
            datos_texto = [str(row.get(campo, 0.0)) for campo in fields]
            handle.write(",".join(datos_texto) + "\n")
        except Exception as e:
            logger.error(f"Error crítico escribiendo en {path}: {e}")

    def close(self):
        # Cierre ordenado de todos los ficheros (llamar en el shutdown de la app)
        for handle in self._handles.values():
            try:
                handle.close()
            except Exception:
                pass
        self._handles.clear()

telemetry_logger = TelemetryLogger()