"""Volcado de la SD de vuelo -> tramas SPP, sesiones y apogeo.

La SD no tiene particiones ni sistema de ficheros: el datalogger del firmware escribe los
SPP_Packet_t (64 B, 8 por sector) en sectores crudos a partir de K_DATALOGGER_FIRST_SECTOR. No se
da nada por supuesto sobre cómo están colocados: se buscan tramas cuyo CRC cuadre en todo el
volcado, igual que hace el framer con el puerto serie.
"""

import binascii
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from backend.comms.framer import SPPFramer
from backend.telemetry.decoder import Decoder
from backend.telemetry.models import K_SPP_PKT_VERSION, KPID_FSM, BAROPacket, TelemetryPacket

FRAME_SIZE = SPPFramer.FRAME_SIZE
CRC_SIZE = SPPFramer.CRC_SIZE
SECTOR_SIZE = 512
FIRST_DATA_SECTOR = 16384      # K_DATALOGGER_FIRST_SECTOR (spp/services/datalogger/datalogger.h)

# Cada arranque de la placa vuelve a escribir desde FIRST_DATA_SECTOR: si la SD no se borró, detrás
# del último vuelo quedan restos de sesiones anteriores. El datalogger escribe los paquetes en el
# orden de la cola FIFO de pubsub y el timestamp se pone al crear el paquete, así que dentro de un
# arranque el tiempo nunca retrocede en el disco y el seq de cada APID siempre avanza. Una nueva
# sesión empieza cuando no es así o cuando hay un hueco de sectores sin ninguna trama.
SESSION_GAP_SECTORS = 16
SESSION_SEQ_JUMP = 1000        # Un avance de seq mayor (o un retroceso, que da la vuelta) es otro arranque
# Restos de un arranque anterior que siguen justo detrás, con tiempos y seq que encajan, no se pueden
# separar. Al menos se avisa de los saltos de tiempo raros dentro de una sesión.
SUSPICIOUS_GAP_MS = 1000

# Apogeo
MEDIAN_WINDOW = 5              # Filtro de mediana: un pico suelto del barómetro no es el apogeo
# El firmware ya da la altitud respecto a la presión media de 500 muestras al arrancar (rampa = 0 m),
# pero se resta igual la de las primeras muestras: por si deriva o se arrancó lejos de la rampa
GROUND_SAMPLES = 50
LIFTOFF_MARGIN_M = 5.0         # El despegue es la última vez antes del apogeo a menos de esto del suelo


def frame_is_valid(frame: bytes) -> bool:
    # binascii.crc_hqx con init 0xFFFF es el CRC-16/CCITT-FALSE del firmware, pero en C: con
    # cientos de MiB de volcado, crc16_ccitt en Python tarda minutos
    return (frame[0] == K_SPP_PKT_VERSION
            and binascii.crc_hqx(frame[:-CRC_SIZE], 0xFFFF) == int.from_bytes(frame[-CRC_SIZE:], "little"))


def find_frames(data: bytes) -> list[tuple[int, bytes]]:
    """(offset, trama) de todas las tramas con CRC válido, en el orden del disco.

    Solo se prueba el CRC donde hay un byte de versión: en las zonas a cero o a 0xFF de la SD no
    se calcula ninguno.
    """
    candidates = np.flatnonzero(np.frombuffer(data, dtype=np.uint8) == K_SPP_PKT_VERSION)
    last = len(data) - FRAME_SIZE
    frames = []
    k = 0
    while k < len(candidates):
        offset = int(candidates[k])
        if offset > last:
            break
        frame = data[offset:offset + FRAME_SIZE]
        if frame_is_valid(frame):
            frames.append((offset, frame))
            k = int(np.searchsorted(candidates, offset + FRAME_SIZE))
        else:
            k += 1
    return frames


@dataclass
class Record:
    offset: int                 # Posición en el volcado (bytes)
    packet: TelemetryPacket

    @property
    def ts(self) -> int:
        return self.packet.secondary_header.timestamp_ms


@dataclass
class Session:
    records: list[Record] = field(default_factory=list)   # Ordenados por timestamp, sin duplicados
    duplicates: int = 0
    gaps: list[tuple[int, int]] = field(default_factory=list)   # (offset, ms) de saltos > SUSPICIOUS_GAP_MS
    first_offset: int = 0
    last_offset: int = 0

    @property
    def t_start(self) -> int:
        return self.records[0].ts

    @property
    def t_end(self) -> int:
        return self.records[-1].ts

    def count(self, payload_type) -> int:
        return sum(isinstance(r.packet.payload, payload_type) for r in self.records)


@dataclass
class DumpContents:
    sessions: list[Session]
    frames: int                 # Tramas con CRC válido
    discarded: Counter          # Motivo -> tramas con CRC válido que el decoder rechaza


def decode_dump(data: bytes) -> DumpContents:
    decoder = Decoder()
    discarded = Counter()
    frames = find_frames(data)
    decoded: list[tuple[int, bytes, TelemetryPacket]] = []
    for offset, frame in frames:
        try:
            decoded.append((offset, frame, decoder.frame_to_packet(frame)))
        except ValueError as e:   # Incluye la ValidationError de pydantic (NaN, versión...)
            discarded[str(e).splitlines()[0]] += 1
    return DumpContents(sessions=split_sessions(decoded), frames=len(frames), discarded=discarded)


def split_sessions(decoded: list[tuple[int, bytes, TelemetryPacket]]) -> list[Session]:
    """Separa por arranques de la placa (en el orden del disco) y ordena cada sesión por tiempo."""
    groups: list[list[tuple[int, bytes, TelemetryPacket]]] = []
    prev_offset = prev_ts = None
    last_seq: dict[int, tuple[int, int]] = {}   # APID -> (seq, ts) del último paquete de la sesión
    for item in decoded:
        offset, _, packet = item
        ts = packet.secondary_header.timestamp_ms
        apid, seq = packet.primary_header.apid, packet.primary_header.seq
        new = prev_ts is None or ts < prev_ts or offset - prev_offset > SESSION_GAP_SECTORS * SECTOR_SIZE
        if not new and apid != KPID_FSM and apid in last_seq:   # La FSM lleva siempre seq 0
            prev_seq, prev_seq_ts = last_seq[apid]
            step = (seq - prev_seq) & 0xFFFF
            new = step > SESSION_SEQ_JUMP or (step == 0 and ts != prev_seq_ts)
        if new:
            groups.append([])
            last_seq = {}
        groups[-1].append(item)
        last_seq[apid] = (seq, ts)
        prev_offset, prev_ts = offset, ts

    sessions = []
    for group in groups:
        session = Session(first_offset=group[0][0], last_offset=group[-1][0])
        for (_, _, a), (offset, _, b) in zip(group, group[1:]):
            dt = b.secondary_header.timestamp_ms - a.secondary_header.timestamp_ms
            if dt > SUSPICIOUS_GAP_MS:
                session.gaps.append((offset, dt))
        seen = set()
        for offset, frame, packet in group:
            if frame in seen:      # El firmware puede escribir el mismo paquete dos veces
                session.duplicates += 1
                continue
            seen.add(frame)
            session.records.append(Record(offset, packet))
        session.records.sort(key=lambda r: r.ts)
        sessions.append(session)
    return sessions


@dataclass
class Apogee:
    ts: int                     # Tiempo del firmware (ms)
    altitude: float             # Altitud del barómetro en el apogeo (m), ya filtrada
    ground: float               # Altitud de la rampa (m)
    liftoff_ts: int | None      # None si no se ve el despegue (el log empieza ya en vuelo)

    @property
    def agl(self) -> float:
        return self.altitude - self.ground

    @property
    def t_from_liftoff(self) -> float | None:
        return None if self.liftoff_ts is None else (self.ts - self.liftoff_ts) / 1000


def baro_series(session: Session) -> tuple[np.ndarray, np.ndarray]:
    """(t en ms, altitud en m) del barómetro."""
    baro = [r for r in session.records if isinstance(r.packet.payload, BAROPacket)]
    return (np.array([r.ts for r in baro], dtype=float),
            np.array([r.packet.payload.altitude for r in baro], dtype=float))


def median_filter(x: np.ndarray, window: int = MEDIAN_WINDOW) -> np.ndarray:
    if len(x) < window:
        return x.copy()
    half = window // 2
    padded = np.pad(x, half, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(padded, window), axis=1)


def find_apogee(t_ms: np.ndarray, altitude: np.ndarray) -> Apogee | None:
    if len(altitude) == 0:
        return None
    smooth = median_filter(altitude)
    peak = int(np.argmax(smooth))
    ground = float(np.median(smooth[:GROUND_SAMPLES]))
    on_ground = np.flatnonzero(smooth[:peak + 1] <= ground + LIFTOFF_MARGIN_M)
    liftoff_ts = int(t_ms[on_ground[-1]]) if len(on_ground) and on_ground[-1] < peak else None
    return Apogee(ts=int(t_ms[peak]), altitude=float(smooth[peak]), ground=ground, liftoff_ts=liftoff_ts)
