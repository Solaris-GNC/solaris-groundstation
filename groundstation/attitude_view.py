"""Vista 3D de la actitud del cohete.

Adaptada de Rocket-orientation-visualization (Three.js): el mismo cohete en alambre, cámara
ortográfica trimétrica y rejilla que se difumina con la distancia. Aquí se pinta con QPainter,
sin navegador ni OpenGL: son unos cientos de segmentos.

El cohete apunta por +Z de su cuerpo y se orienta con store.ViewOrientation: la inclinación del
DMP y el rumbo del giróscopio integrado. El rumbo del DMP no se usa: depende del magnetómetro y se
desvía decenas de grados en segundos con la placa quieta.

El rumbo no tiene referencia absoluta. Se fija de dos formas:
  - "Centrar vista": con el cohete en vertical y la cara de componentes de la placa hacia ti. La
    vista queda relativa a ti (con ROCKET_AXIS = "y"): +X hacia ti (la cámara mira desde aquí),
    +Y tu derecha, +Z arriba. Lo que inclinas hacia ti viene hacia la cámara, aunque antes hayas
    girado el cohete sobre su eje.
  - "Orientar", con el cohete en la rampa: se indica el acimut hacia el que está inclinada y la
    vista se gira para que la inclinación del cohete apunte ahí. Queda orientada al norte (+X
    este, +Y norte), con los puntos cardinales en el suelo y la cámara de lado a la rampa.
"""

import math

import numpy as np
from PySide6.QtCore import QLineF, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from .widgets import Panel, fmt, install_fullscreen_keys, toggle_fullscreen

# Cámara por defecto: desde +X (desde donde estás tú mirando la cara de la placa), algo elevada
DEFAULT_AZIMUTH = 0.0      # Grados, desde +X hacia +Y
DEFAULT_ELEVATION = 24.0
VIEW_SIZE = 220.0          # Media altura visible, en unidades del modelo

GRID_Z = -170.0            # Altura del suelo, justo por debajo de la cola del cohete
GRID_CELL = 25.0
GRID_EXTENT = 350.0        # La rejilla se desvanece hasta este radio
COMPASS_RADIUS = 240.0     # Radio de las letras N/E/S/O sobre el suelo
COMPASS = [("N", 0), ("NE", 45), ("E", 90), ("SE", 135), ("S", 180), ("SO", 225), ("O", 270), ("NO", 315)]


def compass_name(azimuth: float) -> str:
    """Punto cardinal más cercano (8 rumbos) de un acimut en grados desde el norte."""
    return COMPASS[round(azimuth / 45) % 8][0]
AXIS_LEN = 40.0
RING_RES = 32              # Puntos por anillo
SEGMENTS = 16              # Aristas longitudinales del cuerpo y la ojiva


def _ring(radius: float, z: float) -> list[tuple]:
    a = np.linspace(0, 2 * math.pi, RING_RES + 1)
    pts = np.column_stack([radius * np.cos(a), radius * np.sin(a), np.full_like(a, z)])
    return list(zip(pts[:-1], pts[1:]))


def rocket_segments() -> np.ndarray:
    """Segmentos del cohete en ejes del cuerpo, forma (n, 2, 3). Misma geometría que el original."""
    r, oz = 15.0, -40.0
    z_bot, z_mid, z_tip = -100 + oz, 100 + oz, 180 + oz
    segs = []
    # Cuerpo: anillos y aristas longitudinales
    for i in range(9):
        segs += _ring(r, z_bot + i * (z_mid - z_bot) / 8)
    # Ojiva: anillos que se estrechan y aristas hasta la punta
    for i in range(1, 5):
        t = i / 5
        segs += _ring(r * (1 - t), z_mid + t * (z_tip - z_mid))
    for a in np.linspace(0, 2 * math.pi, SEGMENTS, endpoint=False):
        c, s = math.cos(a), math.sin(a)
        segs.append(((r * c, r * s, z_bot), (r * c, r * s, z_mid)))
        segs.append(((r * c, r * s, z_mid), (0, 0, z_tip)))
    # Aletas: triángulos
    span, z_top = 22.0, -55 + oz
    for a in np.radians([0, 90, 180, 270]):
        c, s = math.cos(a), math.sin(a)
        root_bot, tip, root_top = (r * c, r * s, z_bot), ((r + span) * c, (r + span) * s, z_bot), (r * c, r * s, z_top)
        segs += [(root_bot, tip), (tip, root_top), (root_top, root_bot)]
    return np.array(segs, dtype=float) * 1.1


def grid_segments() -> tuple[np.ndarray, np.ndarray]:
    """Rejilla del suelo troceada para difuminarla con la distancia: (segmentos, opacidad)."""
    n = int(GRID_EXTENT // GRID_CELL)
    ticks = np.arange(-n, n + 1) * GRID_CELL
    pieces = np.linspace(-GRID_EXTENT, GRID_EXTENT, 29)
    segs, alpha = [], []
    for k in ticks:
        for a, b in zip(pieces[:-1], pieces[1:]):
            for p, q in (((k, a), (k, b)), ((a, k), (b, k))):
                mid = math.hypot((p[0] + q[0]) / 2, (p[1] + q[1]) / 2) / GRID_EXTENT
                fade = 1 - min(1.0, mid / 0.9) ** 2
                if fade <= 0:
                    continue
                segs.append(((*p, GRID_Z), (*q, GRID_Z)))
                # Línea gruesa cada 4 celdas, como las mayores del original
                alpha.append(fade * (0.9 if round(k / GRID_CELL) % 4 == 0 else 0.45))
    return np.array(segs), np.array(alpha)


class AttitudeView(QWidget):
    """Cohete en 3D. Arrastrar con el ratón gira la cámara; doble clic la devuelve a su sitio."""

    ROCKET = rocket_segments()
    GRID = grid_segments()

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(260, 260)
        self.setCursor(Qt.OpenHandCursor)
        self.azimuth, self.elevation = DEFAULT_AZIMUTH, DEFAULT_ELEVATION
        self.angles: tuple[float, float, float, float] | None = None  # (tilt, roll, pitch, yaw)
        self.matrix: np.ndarray | None = None
        self.rail_azimuth: float | None = None   # Vista orientada al norte (store.ViewOrientation)
        self.nose_azimuth: float | None = None
        self.c: dict = {}
        self.family = ""
        self._drag_from: QPointF | None = None

    def set_theme(self, c: dict, family: str):
        self.c, self.family = c, family
        self.update()

    def set_attitude(self, tilt, roll, pitch, yaw, matrix: np.ndarray | None,
                     rail_azimuth: float | None = None, nose_azimuth: float | None = None):
        """Ángulos en grados para la lectura y matriz cuerpo -> vista para el dibujo
        (store.ViewOrientation.matrix). None si aún no hay datos de la IMU.
        rail_azimuth: acimut de la rampa si la vista está orientada al norte (X este, Y norte)."""
        angles = None if pitch is None or matrix is None else (tilt, roll, pitch, yaw)
        if rail_azimuth != self.rail_azimuth:
            self.rail_azimuth = rail_azimuth
            self.azimuth, self.elevation = self._default_camera()
        self.matrix = matrix
        self.angles = angles
        self.nose_azimuth = nose_azimuth
        self.update()

    def _default_camera(self) -> tuple[float, float]:
        """Vista relativa: desde +X (quien mira la cara de la placa). Orientada al norte: de lado,
        con la dirección de lanzamiento hacia la derecha de la pantalla, para ver la inclinación."""
        if self.rail_azimuth is None:
            return DEFAULT_AZIMUTH, DEFAULT_ELEVATION
        return -self.rail_azimuth, DEFAULT_ELEVATION

    # ==================================================================
    # Cámara

    def _camera(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Vectores (derecha, arriba, hacia la cámara) de la vista, en ejes del mundo."""
        az, el = math.radians(self.azimuth), math.radians(self.elevation)
        back = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
        right = np.array([-math.sin(az), math.cos(az), 0.0])
        return right, np.cross(back, right), back

    def mousePressEvent(self, event):
        self._drag_from = event.position()
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_from is None:
            return
        delta = event.position() - self._drag_from
        self._drag_from = event.position()
        self.azimuth = (self.azimuth - delta.x() * 0.4) % 360
        self.elevation = max(-89.0, min(89.0, self.elevation + delta.y() * 0.4))
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag_from = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        self.azimuth, self.elevation = self._default_camera()
        self.update()

    # ==================================================================
    # Pintado

    def paintEvent(self, event):
        if not self.c:
            return
        c = self.c
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(c["panel"]))

        right, up, back = self._camera()
        scale = min(self.width(), self.height()) / (2 * VIEW_SIZE)
        cx, cy = self.width() / 2, self.height() / 2 + 0.06 * self.height()

        def project(points: np.ndarray) -> np.ndarray:
            """(..., 3) del mundo -> (..., 2) en píxeles."""
            return np.stack([cx + scale * (points @ right), cy - scale * (points @ up)], axis=-1)

        # Rejilla del suelo, difuminada hacia los bordes
        segs, alphas = self.GRID
        grid_color = QColor(c["chart_muted"])
        for (p, q), a in zip(project(segs), alphas):
            grid_color.setAlphaF(0.55 * a)
            painter.setPen(QPen(grid_color, 1))
            painter.drawLine(QLineF(*p, *q))

        # Puntos cardinales sobre el suelo, con la vista orientada al norte (X este, Y norte)
        if self.rail_azimuth is not None:
            font = QFont(self.family or self.font().family())
            font.setPixelSize(13)
            font.setBold(True)
            painter.setFont(font)
            for name, az in COMPASS:
                a = math.radians(az)
                p = project(np.array([math.sin(a), math.cos(a), 0.0]) * COMPASS_RADIUS + (0, 0, GRID_Z))
                painter.setPen(QColor(c["text_strong"] if len(name) == 1 else c["muted"]))
                painter.drawText(QPointF(p[0] - 5 * len(name), p[1] + 5), name)

        # Ejes de la vista, sin nombre (colores de X/Y/Z). Relativa: X hacia ti, Y a tu derecha.
        # Orientada al norte: X este, Y norte. Z siempre arriba
        origin = project(np.zeros(3))
        for axis, key in (((1, 0, 0), "x"), ((0, 1, 0), "y"), ((0, 0, 1), "z")):
            end = project(np.array(axis) * AXIS_LEN)
            painter.setPen(QPen(QColor(c[key]), 2.5, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QLineF(*origin, *end))

        # Cohete: las aristas del fondo, más tenues, para dar profundidad al alambre
        if self.angles is not None:
            _, roll, pitch, yaw = self.angles
            world = self.ROCKET @ self.matrix.T
            depth = (world @ back).mean(axis=1)
            fade = 0.35 + 0.65 * np.clip((depth + 30) / 60, 0, 1)
            color = QColor(c["rocket"])
            for (p, q), a in sorted(zip(project(world), fade), key=lambda s: s[1]):
                color.setAlphaF(a)
                painter.setPen(QPen(color, 1.3))
                painter.drawLine(QLineF(*p, *q))

        self._paint_readout(painter)
        painter.end()

    def _paint_readout(self, painter: QPainter):
        c = self.c
        font = QFont(self.family or self.font().family())
        font.setPixelSize(12)
        painter.setFont(font)
        line = 18
        x, y = 14, 22
        if self.angles is None:
            painter.setPen(QColor(c["muted"]))
            painter.drawText(QPointF(x, y), "Sin datos de la IMU")
            return
        tilt, roll, pitch, yaw = self.angles
        rows = [("Inclinación", tilt, "ink"), ("Roll", roll, "z"), ("Pitch", pitch, "x"), ("Yaw", yaw, "y")]
        for i, (name, value, key) in enumerate(rows):
            painter.setPen(QColor(c[key]))
            painter.drawText(QPointF(x, y + i * line), "━")
            painter.setPen(QColor(c["muted"]))
            painter.drawText(QPointF(x + 18, y + i * line), name)
            painter.setPen(QColor(c["text_strong"]))
            painter.drawText(QPointF(x + 100, y + i * line), f"{fmt(value)}°")
        painter.setPen(QColor(c["muted"]))
        if self.rail_azimuth is None:
            note = "Vista relativa a quien mira (sin orientar al norte)"
        else:
            nose = f"{self.nose_azimuth:.0f}° {compass_name(self.nose_azimuth)}" if self.nose_azimuth is not None else "—"
            note = f"Orientada con la rampa a {self.rail_azimuth:.0f}°: el morro apunta a {nose}"
        painter.drawText(QPointF(x, y + len(rows) * line + 4), note)
        painter.drawText(QPointF(x, self.height() - 12), "Arrastrar: girar la vista · doble clic: volver · F11: pantalla completa")


class OrientationWindow(QMainWindow):
    """Ventana aparte con el cohete en 3D. F11 (o el botón) la pone a pantalla completa.

    La rellena la ventana principal (MainWindow._redraw) solo mientras está abierta.
    """

    center_requested = Signal()       # "Centrar vista": la ventana principal centra store.view
    align_requested = Signal(float)   # "Orientar": acimut de la rampa, en grados desde el norte

    def __init__(self, parent: QWidget | None = None):
        # Con padre, Qt la cierra con la principal; Qt.Window la hace ventana independiente
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Solaris · Orientación")
        self.setMinimumSize(560, 480)
        self.resize(900, 760)

        root = QWidget(objectName="root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        self.setCentralWidget(root)

        view_panel = Panel("Actitud del cohete")
        rail_label = QLabel("Rampa hacia", objectName="muted")
        self.rail_azimuth = QSpinBox(minimum=0, maximum=359, suffix="°", wrapping=True)
        self.rail_azimuth.setToolTip("Acimut hacia el que está inclinada la rampa, en grados desde el\n"
                                     "norte en sentido horario (90° = este, 180° = sur)")
        align = QPushButton("Orientar", objectName="topButton")
        align.setToolTip("Con el cohete en la rampa: gira la vista para que su inclinación apunte al\n"
                         "acimut de la rampa. Aparecen los puntos cardinales en el suelo")
        align.clicked.connect(lambda: self.align_requested.emit(float(self.rail_azimuth.value())))
        align.setCursor(Qt.PointingHandCursor)
        for widget in (rail_label, self.rail_azimuth, align):
            view_panel.head_layout.addWidget(widget)
        view_panel.head_layout.addSpacing(12)
        center = QPushButton("Centrar vista", objectName="topButton")
        center.setToolTip("Con el cohete en vertical y la cara de componentes de la placa hacia ti:\n"
                          "la vista se orienta desde donde estás tú. Solo afecta a esta vista")
        center.clicked.connect(self.center_requested.emit)
        full = QPushButton("Pantalla completa", objectName="topButton")
        full.setToolTip("Pantalla completa (F11). Esc o F11 para salir")
        full.clicked.connect(lambda: toggle_fullscreen(self))
        for button in (center, full):
            button.setCursor(Qt.PointingHandCursor)
            view_panel.head_layout.addWidget(button)
        view_panel.body.setContentsMargins(0, 0, 0, 0)
        self.view = AttitudeView()
        view_panel.body.addWidget(self.view, 1)
        layout.addWidget(view_panel)
        install_fullscreen_keys(self)

    def set_theme(self, c: dict, family: str):
        self.view.set_theme(c, family)

    def set_attitude(self, store):
        """Última muestra de la IMU y orientación de la vista (store.view)."""
        last = store.imu.last
        self.view.set_attitude(last("tilt"), last("roll"), last("pitch"), last("yaw"), store.view.matrix,
                               store.view.rail_azimuth, store.view.nose_azimuth())
