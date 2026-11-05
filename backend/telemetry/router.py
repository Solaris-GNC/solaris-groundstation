import logging
from typing import Optional
from .models import (
    TelemetryPacket, BAROPacket, IMUPacket, FSMPacket, LogLevel,
)
from .state import global_state
from backend.recording.telemetry_logger import telemetry_logger

# ==================================================================
logger = logging.getLogger(__name__)

LINK_GAP_MS = 2000      # Un APID que no llega en más de esto se avisa en Eventos
MIN_PERIOD_MS = 20      # Intervalos menores (ráfagas) no cuentan como periodo nominal


class TelemetryRouter:
    def __init__(self):
        # Último paquete de cada APID (seq, timestamp y crc), para detectar pérdidas y duplicados
        self.last_packets: dict = {}

    def route_packet(self, packet: TelemetryPacket) -> bool:
        """Guarda el paquete en los CSV y comprueba el enlace. False si es un duplicado."""
        apid = packet.primary_header.apid
        seq = packet.primary_header.seq
        ts = packet.secondary_header.timestamp_ms
        crc = packet.crc16

        # La FSM se manda una sola vez con seq fijo a 0: no tiene sentido comprobar su secuencia
        if not isinstance(packet.payload, FSMPacket):
            name = "IMU" if isinstance(packet.payload, IMUPacket) else "BARO"
            if not self.check_sequence(apid, seq, ts, crc, name):
                return False

        # Se enruta por el tipo de payload (el decoder ya identificó el sensor), no por KPID
        if isinstance(packet.payload, FSMPacket):
            self.handle_fsm(packet)
        elif isinstance(packet.payload, BAROPacket):
            self.handle_baro(packet)
        elif isinstance(packet.payload, IMUPacket):
            self.handle_imu(packet)
        return True

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
# Comprobación del enlace (pérdidas, duplicados, reinicios)
#
# El seq de cada APID cuenta TODAS las muestras del sensor, pero por radio solo se envía una de
# cada ~30 (en los logs el IMU salta de 30 en 30 y el BARO de 13 a 67): un salto de seq no es una
# pérdida. Las pérdidas se estiman por el tiempo: cada APID aprende su periodo nominal (el menor
# intervalo visto) y un hueco de N periodos son N-1 paquetes perdidos. Solo se avisa en Eventos
# cuando un APID deja de llegar más de LINK_GAP_MS.
    def check_sequence(self, apid, current_seq, current_ts, current_crc, name: str = ""):
        """Devuelve False si el paquete es un duplicado exacto del anterior de su APID."""
        label = f"{name} (APID {hex(apid)})" if name else f"APID {hex(apid)}"
        last = self.last_packets.get(apid)
        is_new = True
        if last is not None:
            dt = current_ts - last["t"]
            if dt < 0:
                # El tiempo del firmware retrocede: la placa se ha reiniciado
                self._log(f"{label}: reinicio de la placa detectado (t {last['t']} -> {current_ts} ms)",
                          level=LogLevel.WARNING, timestamp_ms=current_ts)
                last["period"] = None
            elif dt == 0:
                if current_seq == last["seq"] and current_crc == last["crc"]:
                    is_new = False      # Duplicado exacto (p. ej. reenvío): no se cuenta ni se guarda
                else:
                    self._log(f"{label}: dos paquetes distintos con el mismo timestamp ({current_ts} ms)",
                              level=LogLevel.WARNING, timestamp_ms=current_ts)
            else:
                period = last.get("period")
                if dt >= MIN_PERIOD_MS and (period is None or dt < period):
                    period = dt
                if period:
                    lost = max(0, round(dt / period) - 1)
                    if lost:
                        global_state.add_lost_packets(lost)
                if dt > LINK_GAP_MS:
                    self._log(f"{label}: {dt / 1000:.1f} s sin paquetes", level=LogLevel.WARNING,
                              timestamp_ms=current_ts)
                last["period"] = period
        if is_new:
            period = last.get("period") if last else None
            self.last_packets[apid] = {"seq": current_seq, "t": current_ts, "crc": current_crc,
                                       "period": period}
        return is_new


# ==================================================================
# Helper: manda el mismo log a memoria (frontend) y a fichero (backup)
    def _log(self, message: str, level: LogLevel = LogLevel.INFO, timestamp_ms: Optional[int] = None):
        global_state.add_log(message, level, timestamp_ms)
        telemetry_logger.log_event(level, message, timestamp_ms)


global_router = TelemetryRouter()
