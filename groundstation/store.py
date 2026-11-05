"""Datos acumulados de la sesión y cálculos derivados.

Llega cada paquete decodificado, así que no se pierde ninguna muestra entre el puerto serie
y la pantalla.
Sin dependencias de Qt: se puede probar suelto.
"""

import math
import time
from dataclasses import dataclass, field

import numpy as np

MAX_SAMPLES = 200_000      # Por serie: ~10 h de IMU al ritmo actual del enlace
STALE_S = 3.0              # Sin muestras nuevas durante este tiempo -> "Sin datos"
RATE_WINDOW_S = 5.0        # Ventana para calcular muestras/s
VZ_MAX_DT_S = 5.0          # Huecos mayores no se derivan (demasiados paquetes perdidos)
VIEW_GYRO_DEADBAND_DPS = 1.0  # Vista 3D: giros más lentos se toman como ruido/sesgo del giróscopio
VIEW_MAX_GYRO_DT_S = 1.0      # Vista 3D: con huecos mayores no se integra el giróscopio
GROUND_AVG_S = 2.0         # Al fijar la rampa, la altitud de referencia es la media de estos segundos

# Eje del sensor alineado con el eje longitudinal del cohete: el morro va por +Y de la placa
# (con el cohete en vertical, ay ≈ 1 g). Cambiar si se monta de otra forma.
ROCKET_AXIS = "y"

# Init bits: módulos que se muestran y qué bits les afectan.
# Los bits de UART no se muestran: el UART no se usa en vuelo.
# Ojo: 'datalogggerPubsubError' lleva tres 'g' porque así está en el firmware (main/custom.h).
INIT_MODULES = [
    ("BMP390", "Barómetro", [("bmpPubsubError", "registro"), ("bmpInitError", "init")]),
    ("ICM20948", "IMU", [("icmPubsubError", "registro"), ("icmInitError", "init")]),
    ("SD", "Datalogger", [("datalogggerPubsubError", "registro"), ("dataloggerInitError", "init")]),
    ("SX1262", "Radio LoRa", [("sx1262PubsubError", "registro"), ("sx1262InitError", "init")]),
    ("FSM", "Máquina de estados", [("fsmInitError", "init")]),
    ("Core", "Núcleo SPP", [("coreInitError", "core"), ("logInitError", "log"),
                            ("dataBankInitError", "databank"), ("pubsubInitError", "pubsub")]),
]


# Ejes del cuerpo reordenados (permutación cíclica, conserva la orientación) para que el eje
# del cohete haga de Z
_BODY_AXES = {
    "z": (0, 1, 2),  # morro por +Z de la placa (placa plana)
    "x": (1, 2, 0),  # morro por +X de la placa
    "y": (2, 0, 1),  # morro por +Y de la placa (actual)
}


def rocket_matrix(w: float, x: float, y: float, z: float) -> np.ndarray:
    """Matriz de rotación cuerpo -> mundo con los ejes del cuerpo reordenados según ROCKET_AXIS:
    su columna 2 es el eje del cohete (el morro) en ejes del mundo."""
    r = np.array((
        (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
    ))
    return r[:, _BODY_AXES[ROCKET_AXIS]]


def attitude(w: float, x: float, y: float, z: float) -> tuple[float, float, float, float]:
    """Actitud del cohete en grados: (tilt, roll, pitch, yaw).

    Ángulos de Euler en orden X-Y-Z (pitch, después yaw, y el roll al final, sobre el eje del
    propio cohete). No se usa el orden de avión (ZYX): con el cohete en vertical, ese orden reparte
    el giro sobre su eje entre roll y pitch, y su singularidad (gimbal lock) cae justo en vertical.
    Con X-Y-Z:
      - pitch y yaw solo dependen de hacia dónde apunta el cohete: girar sobre su eje no los mueve
      - roll es solo el giro sobre el eje del cohete
      - la singularidad queda con el cohete en horizontal (yaw = ±90º)
    Con el cohete recto hacia arriba los tres valen 0.
      tilt: ángulo entre el eje del cohete y la vertical
      pitch: inclinación sobre el eje X del mundo (positivo: el morro va hacia -Y)
      yaw: inclinación sobre el eje Y del mundo (positivo: el morro va hacia +X)
      roll: giro sobre el eje del cohete, entre -180 y 180
    Los ejes X/Y del mundo los fija el DMP con el magnetómetro, así que el roll absoluto
    depende de su calibración; su variación (el giro) es fiable.
    """
    r = rocket_matrix(w, x, y, z)
    # R = Rx(pitch) · Ry(yaw) · Rz(roll)
    tilt = math.acos(max(-1.0, min(1.0, r[2][2])))
    pitch = math.atan2(-r[1][2], r[2][2])
    yaw = math.asin(max(-1.0, min(1.0, r[0][2])))
    roll = math.atan2(-r[0][1], r[0][0])
    return (math.degrees(tilt), math.degrees(roll), math.degrees(pitch), math.degrees(yaw))


def align_up(v) -> np.ndarray:
    """Giro mínimo que lleva el vector v a +Z (gira sobre un eje horizontal: no cambia el rumbo)."""
    v = np.asarray(v, dtype=float) / np.linalg.norm(v)
    axis = np.cross(v, (0.0, 0.0, 1.0))
    s, c = np.linalg.norm(axis), v[2]
    if s < 1e-9:
        # Ya está arriba (identidad) o justo abajo (media vuelta sobre X)
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    k = axis / s
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + s * kx + (1 - c) * kx @ kx


def _rotvec(w) -> np.ndarray:
    """Matriz de giro de un vector de rotación (eje · ángulo en rad)."""
    a = np.linalg.norm(w)
    if a < 1e-12:
        return np.eye(3)
    k = w / a
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(a) * kx + (1 - math.cos(a)) * kx @ kx


class ViewOrientation:
    """Orientación del cohete para la vista 3D: inclinación del DMP y rumbo del giróscopio.

    El rumbo del DMP (giro alrededor de la vertical) depende del magnetómetro y se desvía decenas
    de grados en segundos con la placa quieta; su inclinación sí es fiable (coincide con el
    acelerómetro). Aquí se integra el giróscopio (en ejes del cohete) y en cada muestra se corrige
    la inclinación con la del DMP girando sobre un eje horizontal, sin tocar el rumbo. Así el
    rumbo solo cambia cuando el giróscopio mide giro, y girar el cohete sobre su eje se ve como
    tal. Los giros por debajo de VIEW_GYRO_DEADBAND_DPS se ignoran para que no derive en reposo.

    El rumbo no tiene referencia absoluta: center() lo fija con la orientación actual (la cara
    de la placa hacia la cámara). Se centra solo con la primera muestra.
    `matrix`: cuerpo del cohete (columnas de rocket_matrix) -> ejes de la vista, Z arriba.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.matrix: np.ndarray | None = None
        self.t: float | None = None
        self.gyro: np.ndarray | None = None

    def center(self):
        if self.matrix is not None:
            # Fila 2: la vertical en ejes del cohete. Se deja solo la inclinación, rumbo 0
            self.matrix = align_up(self.matrix[2])

    def update(self, t: float, r_dmp: np.ndarray, gyro_dps) -> None:
        """r_dmp: rocket_matrix() del DMP. gyro_dps: giróscopio en ejes de la placa (°/s)."""
        gyro = np.radians(np.asarray(gyro_dps, dtype=float)[list(_BODY_AXES[ROCKET_AXIS])])
        up = r_dmp[2]                                   # Vertical en ejes del cohete, según el DMP
        if self.matrix is None:
            self.matrix, self.t, self.gyro = align_up(up), t, gyro
            return
        dt = t - self.t
        r = self.matrix
        if 0 < dt <= VIEW_MAX_GYRO_DT_S:
            w = (gyro + self.gyro) / 2                  # Trapecio entre las dos muestras
            if np.degrees(np.linalg.norm(w)) >= VIEW_GYRO_DEADBAND_DPS:
                r = r @ _rotvec(w * dt)
        # Corrección de inclinación: la vertical del DMP, llevada a la vista, se gira a +Z
        self.matrix = align_up(r @ up) @ r
        self.t, self.gyro = t, gyro


class Series:
    """Columnas de una serie temporal: t (s desde el arranque de la placa) y un valor por campo.

    Arrays de numpy que crecen por bloques: las gráficas reciben vistas sin copiar.
    """

    def __init__(self, fields: list[str], capacity: int = 4096):
        self.fields = fields
        self._data = np.empty((len(fields) + 1, capacity))  # Fila 0: t
        self._n = 0

    def __len__(self):
        return self._n

    @property
    def t(self) -> np.ndarray:
        return self._data[0, :self._n]

    @property
    def cols(self) -> dict[str, np.ndarray]:
        return {f: self._data[i + 1, :self._n] for i, f in enumerate(self.fields)}

    def append(self, t: float, **values: float):
        if self._n == self._data.shape[1]:
            if self._n < MAX_SAMPLES:
                grown = np.empty((self._data.shape[0], min(2 * self._n, MAX_SAMPLES)))
                grown[:, :self._n] = self._data[:, :self._n]
                self._data = grown
            else:
                # Lleno: se descarta la mitad más antigua
                half = self._n // 2
                self._data[:, :self._n - half] = self._data[:, half:self._n]
                self._n -= half
        self._data[0, self._n] = t
        for i, name in enumerate(self.fields):
            self._data[i + 1, self._n] = values[name]
        self._n += 1

    def last(self, name: str) -> float | None:
        return float(self._data[self.fields.index(name) + 1, self._n - 1]) if self._n else None

    def last_t(self) -> float | None:
        return float(self._data[0, self._n - 1]) if self._n else None

    def window_start(self, t_min: float | None) -> int:
        """Índice de la primera muestra con t >= t_min (los t vienen ordenados)."""
        return 0 if t_min is None else int(np.searchsorted(self.t, t_min))


@dataclass
class Store:
    # Sin filtrar: altitud medida y velocidad vertical como su derivada directa
    baro: Series = field(default_factory=lambda: Series(["altitude", "pressure", "temperature", "vz"]))
    imu: Series = field(default_factory=lambda: Series(
        ["ax", "ay", "az", "amag", "gx", "gy", "gz", "tilt", "roll", "pitch", "yaw"]))
    fsm: dict | None = None                  # Último paquete de init bits (sobrevive a reinicios)
    apogee: tuple[float, float] | None = None  # (t, altitud en bruto)
    max_g: float | None = None
    # Altitud (en bruto) de la rampa: la altitud, el apogeo y las gráficas se dan respecto a ella.
    # La serie guarda siempre la altitud en bruto; la resta se hace al leer (altitude_agl).
    # Sobrevive a los reinicios de la placa: la altitud del firmware no depende del arranque
    ground_alt: float | None = None
    view: ViewOrientation = field(default_factory=ViewOrientation)  # Para la vista 3D
    reboots: int = 0                         # Reinicios de la placa detectados en esta sesión
    last_sample_at: float | None = None      # time.monotonic() de la última muestra nueva
    sample_times: list[float] = field(default_factory=list)
    version: int = 0                         # Sube con cada muestra nueva: la UI solo repinta si cambia

    # ==================================================================
    def _reset_flight(self):
        """La placa se ha reiniciado: se empieza de cero (salvo init bits y contador de reinicios)."""
        self.baro = Series(self.baro.fields)
        self.imu = Series(self.imu.fields)
        self.apogee = None
        self.max_g = None
        self.view.reset()
        self.reboots += 1

    def _check_reboot(self, series: Series, t: float) -> bool:
        """Devuelve True si la muestra se debe descartar (repetida)."""
        last = series.last_t()
        if last is not None and t < last:
            # Si el tiempo del firmware retrocede, la placa se ha reiniciado
            self._reset_flight()
            return False
        return t == last

    def _mark_new(self, now: float):
        self.sample_times.append(now)
        self.last_sample_at = now
        self.version += 1

    # ==================================================================
    def add_baro(self, timestamp_ms: int, altitude: float, pressure: float, temperature: float,
                 now: float | None = None):
        now = time.monotonic() if now is None else now
        t = timestamp_ms / 1000
        if self._check_reboot(self.baro, t):
            return
        vz = math.nan
        last_t = self.baro.last_t()
        if last_t is not None and t - last_t <= VZ_MAX_DT_S:
            vz = (altitude - self.baro.last("altitude")) / (t - last_t)
        self.baro.append(t, altitude=altitude, pressure=pressure, temperature=temperature, vz=vz)
        if self.apogee is None or altitude > self.apogee[1]:
            self.apogee = (t, altitude)
        self._mark_new(now)

    def add_imu(self, timestamp_ms: int, accel: tuple[float, float, float],
                gyro: tuple[float, float, float], quat: tuple[float, float, float, float],
                now: float | None = None):
        now = time.monotonic() if now is None else now
        t = timestamp_ms / 1000
        if self._check_reboot(self.imu, t):
            return
        ax, ay, az = accel
        amag = math.sqrt(ax * ax + ay * ay + az * az)
        tilt, roll, pitch, yaw = attitude(*quat)
        self.view.update(t, rocket_matrix(*quat), gyro)
        self.imu.append(t, ax=ax, ay=ay, az=az, amag=amag, gx=gyro[0], gy=gyro[1], gz=gyro[2],
                        tilt=tilt, roll=roll, pitch=pitch, yaw=yaw)
        self.max_g = amag if self.max_g is None else max(self.max_g, amag)
        self._mark_new(now)

    def set_ground(self) -> bool:
        """Fija la rampa: la altitud actual (media de los últimos GROUND_AVG_S) pasa a ser 0 y se
        olvidan el apogeo y la aceleración máxima acumulados en tierra. False si no hay barómetro."""
        if not len(self.baro):
            return False
        t, alt = self.baro.t, self.baro.cols["altitude"]
        self.ground_alt = float(np.mean(alt[t >= t[-1] - GROUND_AVG_S]))
        self.apogee = None
        self.max_g = None
        self.version += 1
        return True

    def clear_ground(self):
        self.ground_alt = None
        # El apogeo vuelve a contar toda la sesión
        self.apogee = None
        if len(self.baro):
            k = int(np.argmax(self.baro.cols["altitude"]))
            self.apogee = (float(self.baro.t[k]), float(self.baro.cols["altitude"][k]))
        self.version += 1

    def altitude_agl(self, altitude):
        """Altitud (o array de altitudes) respecto a la rampa; sin rampa fijada, tal cual."""
        return altitude if self.ground_alt is None or altitude is None else altitude - self.ground_alt

    def set_fsm(self, timestamp_ms: int, fsm_errors: int, common_errors: int, failed: list[str]):
        self.fsm = {"timestamp_ms": timestamp_ms, "fsm_errors": fsm_errors,
                    "common_errors": common_errors, "failed": failed}
        self.version += 1

    # ==================================================================
    def t_now(self) -> float:
        return max(self.baro.last_t() or 0.0, self.imu.last_t() or 0.0)

    def sample_rate(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        self.sample_times = [s for s in self.sample_times if now - s <= RATE_WINDOW_S]
        return len(self.sample_times) / RATE_WINDOW_S

    def data_age(self, now: float | None = None) -> float | None:
        now = time.monotonic() if now is None else now
        return None if self.last_sample_at is None else now - self.last_sample_at

    def is_stale(self, now: float | None = None) -> bool:
        age = self.data_age(now)
        return age is None or age > STALE_S
