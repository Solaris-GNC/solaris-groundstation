import logging
from typing import Optional
from .models import (
    TelemetryPacket, BAROPacket, IMUPacket, FSMPacket, LogLevel,
)
from .state import global_state
from backend.recording.telemetry_logger import telemetry_logger

# ==================================================================
logger = logging.getLogger(__name__)


class TelemetryRouter:
    def __init__(self):
        # Último paquete de cada APID (seq, timestamp y crc), para detectar pérdidas y duplicados
        self.last_packets: dict = {}

    def route_packet(self, packet: TelemetryPacket):
        apid = packet.primary_header.apid
        seq = packet.primary_header.seq
        ts = packet.secondary_header.timestamp_ms
        crc = packet.crc16

        # La FSM se manda una sola vez con seq fijo a 0: no tiene sentido comprobar su secuencia
        if not isinstance(packet.payload, FSMPacket):
            self.check_sequence(apid, seq, ts, crc)

        # Se enruta por el tipo de payload (el decoder ya identificó el sensor), no por KPID
        if isinstance(packet.payload, FSMPacket):
            self.handle_fsm(packet)
        elif isinstance(packet.payload, BAROPacket):
            self.handle_baro(packet)
        elif isinstance(packet.payload, IMUPacket):
            self.handle_imu(packet)

# ==================================================================
# Funciones de cada sensor:
    def handle_fsm(self, packet: TelemetryPacket):
        payload: FSMPacket = packet.payload
        ts = packet.secondary_header.timestamp_ms
        telemetry_logger.log_fsm(packet)

        bits = f"fsm=0x{payload.fsm_errors:04X} common=0x{payload.common_errors:04X}"
        if payload.failed:
            self._log(f"INIT CON ERRORES: {', '.join(payload.failed)} ({bits})",
                      level=LogLevel.ERROR, timestamp_ms=ts)
        else:
            self._log(f"INIT OK: todos los módulos inicializados ({bits})",
                      level=LogLevel.INFO, timestamp_ms=ts)

    def handle_baro(self, packet: TelemetryPacket):
        telemetry_logger.log_baro(packet)
        logger.debug(f"BARO actualizado (Seq: {packet.primary_header.seq})")

    def handle_imu(self, packet: TelemetryPacket):
        telemetry_logger.log_imu(packet)
        logger.debug(f"IMU actualizado (Seq: {packet.primary_header.seq})")

# ==================================================================
# Comprobación de paquetes perdidos:
    def check_sequence(self, apid, current_seq, current_ts, current_crc):

        if apid in self.last_packets:

            last = self.last_packets[apid]

            expected_seq = (last["seq"] + 1) % 65536

            # Si el tiempo del firmware retrocede, la placa se ha reiniciado y el seq vuelve a 0:
            # no son paquetes perdidos, se reinicia el control de secuencia
            if current_ts < last["t"]:
                self._log(
                    f"APID {hex(apid)}. Reinicio de la placa detectado "
                    f"(t {last['t']} -> {current_ts} ms). Secuencia reiniciada",
                    level=LogLevel.WARNING, timestamp_ms=current_ts
                )

            elif current_seq == last["seq"]:

                if (
                    current_ts == last["t"]
                    and current_crc == last["crc"]
                ):
                    self._log(
                        f"Duplicado identico ignorado: seq {current_seq}",
                        level=LogLevel.WARNING
                    )
                else:
                    self._log(
                        f"Seq repetido con datos distintos: {current_seq}",
                        level=LogLevel.WARNING
                    )

            elif current_seq != expected_seq:

                lost_count = (current_seq - expected_seq) % 65536

                global_state.add_lost_packets(lost_count)

                self._log(
                    f"APID {hex(apid)}. "
                    f"Esperado: {expected_seq}, "
                    f"Recibido: {current_seq}. "
                    f"Perdidos: {lost_count}",
                    level=LogLevel.WARNING
                )

        self.last_packets[apid] = {
            "seq": current_seq,
            "t": current_ts,
            "crc": current_crc,
        }


# ==================================================================
# Helper: manda el mismo log a memoria (frontend) y a fichero (backup)
    def _log(self, message: str, level: LogLevel = LogLevel.INFO, timestamp_ms: Optional[int] = None):
        global_state.add_log(message, level, timestamp_ms)
        telemetry_logger.log_event(level, message, timestamp_ms)


global_router = TelemetryRouter()
