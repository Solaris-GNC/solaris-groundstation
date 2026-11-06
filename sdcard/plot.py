"""Gráfica de altitud del vuelo con el apogeo marcado (pyqtgraph, con los colores de la app)."""

import os
import sys
from pathlib import Path

import numpy as np

from .dump import Apogee


def show_altitude(t_ms: np.ndarray, altitude: np.ndarray, apogee: Apogee, png: Path,
                  theme: str = "light", interactive: bool = True):
    """Guarda la gráfica en `png` y, si hay pantalla e `interactive`, la abre en una ventana."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        interactive = False

    import pyqtgraph as pg
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

    from groundstation.theme import THEMES, app_icon, load_font

    c = THEMES[theme]
    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(app_icon())
    family = load_font()
    pg.setConfigOptions(antialias=True, segmentedLineMode="on")

    # El eje x es el tiempo desde el despegue si se ve, si no desde el primer dato del barómetro
    t0 = apogee.liftoff_ts if apogee.liftoff_ts is not None else t_ms[0]
    t = (t_ms - t0) / 1000
    t_apo = (apogee.ts - t0) / 1000
    x_label = "T+ desde el despegue (s)" if apogee.liftoff_ts is not None else "t (s)"

    plot = pg.PlotWidget()
    plot.setBackground(c["panel"])
    plot.showGrid(x=True, y=True, alpha=0.25)
    for side in ("left", "bottom"):
        axis = plot.getAxis(side)
        axis.setPen(pg.mkPen(c["axis"]))
        axis.setTextPen(pg.mkPen(c["muted"]))
        if family:
            axis.setTickFont(QFont(family, 10))
    plot.setLabel("left", "Altitud sobre la rampa (m)", color=c["text"])
    plot.setLabel("bottom", x_label, color=c["text"])

    plot.plot(t, altitude - apogee.ground, pen=pg.mkPen(c["x"], width=2))
    plot.addItem(pg.InfiniteLine(pos=t_apo, angle=90, pen=pg.mkPen(c["rocket"], width=1, style=Qt.DashLine)))
    plot.addItem(pg.InfiniteLine(pos=apogee.agl, angle=0, pen=pg.mkPen(c["rocket"], width=1, style=Qt.DashLine)))
    plot.plot([t_apo], [apogee.agl], pen=None, symbol="star", symbolSize=26,
              symbolBrush=c["rocket"], symbolPen=pg.mkPen(c["panel"], width=1))

    # El apogeo va en una cabecera encima de la gráfica: así nunca tapa la curva (el título de
    # pyqtgraph corta las letras grandes)
    when = f"T+{apogee.t_from_liftoff:.2f} s" if apogee.liftoff_ts is not None else f"t = {apogee.ts} ms"
    header = QLabel(f'<span style="color:{c["rocket"]}; font-size:26pt; font-weight:700">APOGEO {apogee.agl:.1f} m</span>'
                    f'<span style="color:{c["text"]}; font-size:13pt">&nbsp;&nbsp;&nbsp;{when} · '
                    f'{apogee.altitude:.1f} m del barómetro</span>')
    header.setAlignment(Qt.AlignCenter)
    if family:
        header.setFont(QFont(family))
    # Margen por arriba para que no se corte la estrella
    low = float(np.min(altitude)) - apogee.ground
    plot.setYRange(low, apogee.agl + 0.15 * (apogee.agl - low or 1), padding=0)

    window = QWidget()
    window.setWindowTitle("Solaris · altitud del vuelo")
    window.setStyleSheet(f"background: {c['panel']};")
    layout = QVBoxLayout(window)
    layout.addWidget(header)
    layout.addWidget(plot, stretch=1)
    window.resize(1280, 720)

    # Sin mostrarla Qt no la maqueta y el PNG saldría a 640x480: si no se quiere ver, se "muestra"
    # fuera de la pantalla
    window.setAttribute(Qt.WA_DontShowOnScreen, not interactive)
    window.show()
    app.processEvents()
    window.grab().save(str(png))
    if interactive:
        app.exec()
