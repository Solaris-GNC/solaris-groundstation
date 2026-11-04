from dataclasses import dataclass, asdict

G0 = 9.80665
MAX_DT_S = 0.25


@dataclass
class MotionState:
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class MotionEstimator:
    def __init__(self) -> None:
        self.state = MotionState()

        self._last_timestamp_ms: int | None = None
        self._last_accel_ms2: tuple[float, float, float] | None = None

    def update(
        self,
        timestamp_ms: int,
        ax_g: float,
        ay_g: float,
        az_g: float,
    ) -> None:
        # Conversión de g a m/s².
        # Se resta 1 g en Z como compensación provisional de gravedad.
        accel = (
            ax_g * G0,
            ay_g * G0,
            (az_g - 1.0) * G0,
        )

        if self._last_timestamp_ms is None:
            self._last_timestamp_ms = timestamp_ms
            self._last_accel_ms2 = accel
            return

        dt = (timestamp_ms - self._last_timestamp_ms) / 1000.0
        self._last_timestamp_ms = timestamp_ms

        # Evita integrar timestamps repetidos, invertidos
        # o saltos de tiempo demasiado grandes.
        if dt <= 0.0 or dt > MAX_DT_S:
            self._last_accel_ms2 = accel
            return

        previous_accel = self._last_accel_ms2 or accel

        old_velocity = (
            self.state.vx,
            self.state.vy,
            self.state.vz,
        )

        # Aceleración -> velocidad mediante integración trapezoidal.
        self.state.vx += 0.5 * (previous_accel[0] + accel[0]) * dt
        self.state.vy += 0.5 * (previous_accel[1] + accel[1]) * dt
        self.state.vz += 0.5 * (previous_accel[2] + accel[2]) * dt

        # Velocidad -> posición mediante integración trapezoidal.
        self.state.x += 0.5 * (old_velocity[0] + self.state.vx) * dt
        self.state.y += 0.5 * (old_velocity[1] + self.state.vy) * dt
        self.state.z += 0.5 * (old_velocity[2] + self.state.vz) * dt

        self._last_accel_ms2 = accel

    def snapshot(self) -> dict[str, float]:
        return asdict(self.state)

    def reset(self) -> None:
        self.__init__()

