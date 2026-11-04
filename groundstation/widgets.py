"""Componentes de la interfaz."""

import html
import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .store import INIT_MODULES

SPARK_POINTS = 120  # Más puntos no se distinguen a este tamaño


def fmt(value: float | None, digits: int = 1) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    s = f"{value:.{digits}f}"
    # Valores negativos que redondean a cero: '-0.0' -> '0.0'
    return s[1:] if s.startswith("-") and float(s) == 0 else s


def set_state(widget: QWidget, state: str):
    """Cambia la 'clase' de un widget para la hoja de estilo (QLabel[state="ok"], ...)."""
    if widget.property("state") != state:
        widget.setProperty("state", state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def status_text(text: str) -> str:
    # Punto de color y siempre texto al lado (el color nunca va solo)
    return f'<span style="font-size:9px">●</span>&nbsp;{html.escape(text)}'


# ==================================================================
# Contenedores


class Zone(QFrame):
    """Bloque: agrupa paneles relacionados con un fondo y un título propios."""

    def __init__(self, title: str):
        super().__init__(objectName="zone")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(6, 6, 6, 6)
        self.body.setSpacing(6)
        label = QLabel(title.upper(), objectName="zoneTitle")
        font = label.font()
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        label.setFont(font)
        self.body.addWidget(label)


class Panel(QFrame):
    """Panel con barra de título tipo Grafana. En `self.head_layout` caben controles a la derecha."""

    def __init__(self, title: str, unit: str = ""):
        super().__init__(objectName="panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        head = QFrame(objectName="panelHead")
        self.head_layout = QHBoxLayout(head)
        self.head_layout.setContentsMargins(8, 4, 8, 4)
        self.head_layout.setSpacing(4)
        self.head_layout.addWidget(QLabel(title, objectName="panelTitle"))
        if unit:
            self.head_layout.addWidget(QLabel(unit, objectName="unit"))
        self.head_layout.addStretch(1)
        outer.addWidget(head)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(8, 6, 8, 6)
        self.body.setSpacing(4)
        outer.addLayout(self.body, 1)


class Segmented(QFrame):
    """Selector de opciones exclusivo (ventana de tiempo, día/noche)."""

    changed = Signal(object)

    def __init__(self, options: list[tuple[str, object]], current: object):
        super().__init__(objectName="segmented")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.group = QButtonGroup(self)
        for label, value in options:
            button = QPushButton(label, checkable=True, checked=value == current)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, v=value: self.changed.emit(v))
            self.group.addButton(button)
            layout.addWidget(button)


# ==================================================================
# Medidas


class Sparkline(QWidget):
    """Tendencia dentro de la ventana de tiempo actual (Tufte): una línea de 1 px, sin ejes."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(18)
        self.values: list[float] = []
        self.color = QColor("#888")

    def set_values(self, values):
        v = np.asarray(values, dtype=float)
        v = v[np.isfinite(v)]
        step = max(1, math.ceil(len(v) / SPARK_POINTS))
        last = v[-1:] if len(v) and (len(v) - 1) % step else v[:0]
        self.values = np.concatenate([v[::step], last]).tolist()
        self.update()

    def paintEvent(self, _):
        v = self.values
        if len(v) < 2:
            return
        lo, hi = min(v), max(v)
        span = (hi - lo) or 1
        w, h = self.width() - 1, self.height() - 1
        points = QPolygonF([QPointF(i / (len(v) - 1) * w, h - 0.5 - (val - lo) / span * (h - 1))
                            for i, val in enumerate(v)])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.color, 1))
        painter.drawPolyline(points)


class StatCard(QFrame):
    """Valor único al estilo Grafana: etiqueta, valor grande, sparkline y una línea secundaria."""

    def __init__(self, label: str, unit: str):
        super().__init__(objectName="panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(QLabel(label, objectName="statLabel"))

        body = QVBoxLayout()
        body.setContentsMargins(10, 4, 10, 6)
        body.setSpacing(0)
        row = QHBoxLayout()
        row.setSpacing(3)
        self.value = QLabel("—", objectName="statValue")
        row.addWidget(self.value, 0, Qt.AlignBaseline)
        row.addWidget(QLabel(unit, objectName="statUnit"), 0, Qt.AlignBaseline)
        row.addStretch(1)
        body.addLayout(row)
        self.spark = Sparkline()
        body.addWidget(self.spark)
        self.sub = QLabel("", objectName="statSub")
        body.addWidget(self.sub)
        layout.addLayout(body)

    def set(self, value: str, trend=None, sub: str = ""):
        self.value.setText(value)
        self.spark.set_values([] if trend is None else trend)
        self.sub.setText(sub)

    def set_theme(self, c: dict):
        self.spark.color = QColor(c["muted"])
        self.spark.update()


# ==================================================================
# Gráficas


class LegendItem(QLabel):
    """Muestra + nombre + último valor. Al pulsar se oculta/muestra la serie."""

    toggled = Signal(bool)

    def __init__(self, label: str, color_key: str, digits: int):
        super().__init__(objectName="legend")
        self.label, self.color_key, self.digits = label, color_key, digits
        self.hidden = False
        self.value: float | None = None
        self.c: dict = {}
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Ocultar serie")

    def mousePressEvent(self, _):
        self.hidden = not self.hidden
        self.setToolTip("Mostrar serie" if self.hidden else "Ocultar serie")
        self.toggled.emit(self.hidden)
        self.render_label()

    def render_label(self):
        if not self.c:
            return
        c = self.c
        swatch = c["muted"] if self.hidden else c[self.color_key]
        name = c["border_strong"] if self.hidden else c["muted"]
        value = c["border_strong"] if self.hidden else c["text_strong"]
        self.setText(f'<span style="color:{swatch}">━</span> <span style="color:{name}">{self.label}</span>'
                     f' <b style="color:{value}">{fmt(self.value, self.digits)}</b>')


class TimePlot(Panel):
    """Gráfica pequeña con el eje de tiempo compartido.

    series: lista de (nombre, clave de color, decimales, ancho, discontinua)
    """

    def __init__(self, title: str, unit: str, series: list[tuple], zero_line: bool = False):
        super().__init__(title, unit)
        self.series_spec = series
        self.zero_line = zero_line
        self.family = ""

        self.legends: list[LegendItem] = []
        for name, color_key, digits, *_ in series:
            item = LegendItem(name, color_key, digits)
            item.toggled.connect(lambda hidden, i=len(self.legends): self.curves[i].setVisible(not hidden))
            self.legends.append(item)
            self.head_layout.addWidget(item)
            self.head_layout.addSpacing(6)

        self.plot = pg.PlotWidget()
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(False, False)
        self.plot.hideButtons()
        self.plot.setClipToView(True)
        self.plot.setDownsampling(auto=True, mode="peak")
        self.plot.getPlotItem().getViewBox().setAutoVisible(y=True)
        self.plot.setMinimumHeight(120)
        self.plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.body.setContentsMargins(2, 2, 6, 2)
        self.body.addWidget(self.plot, 1)

        self.curves = [self.plot.plot([], [], connect="finite") for _ in series]
        self.marker = pg.ScatterPlotItem(symbol="t1", size=10)  # Apogeo (triángulo hacia arriba)
        self.plot.addItem(self.marker)
        self.zero = pg.InfiniteLine(pos=0, angle=0) if zero_line else None
        if self.zero:
            self.plot.addItem(self.zero, ignoreBounds=True)

    def set_theme(self, c: dict, family: str):
        self.plot.setBackground(c["panel"])
        tick_font = QFont(family or self.font().family())
        tick_font.setPixelSize(11)
        bottom, left = self.plot.getAxis("bottom"), self.plot.getAxis("left")
        # Sin títulos de eje ni rejilla vertical; rejilla horizontal casi invisible
        bottom.setPen(c["axis"])
        bottom.setTextPen(c["chart_muted"])
        left.setPen(c["grid"])
        left.setTextPen(c["chart_muted"])
        left.setGrid(255)
        for axis in (bottom, left):
            axis.setStyle(tickFont=tick_font, tickTextOffset=4)
        left.setStyle(tickLength=0)
        left.setWidth(40)
        bottom.tickStrings = lambda values, scale, spacing: [f"{round(v)}s" for v in values]

        for curve, (_, color_key, _, width, dashed) in zip(self.curves, self.series_spec):
            pen = pg.mkPen(c[color_key], width=width)
            if dashed:
                pen.setStyle(Qt.CustomDashLine)
                pen.setDashPattern([4 / width, 3 / width])
            curve.setPen(pen)
        self.marker.setBrush(pg.mkBrush(c["ink"]))
        self.marker.setPen(pg.mkPen(None))
        if self.zero:
            self.zero.setPen(pg.mkPen(c["axis"], width=1))
        for item in self.legends:
            item.c = c
            item.render_label()

    def set_data(self, t, columns: list, x_range: tuple[float, float] | None, marker=None):
        for curve, legend, y in zip(self.curves, self.legends, columns):
            curve.setData(t, y)
            legend.value = y[-1] if len(y) else None
            legend.render_label()
        self.marker.setData(*marker) if marker else self.marker.clear()
        if x_range:
            self.plot.setXRange(*x_range, padding=0)
        else:
            self.plot.enableAutoRange(axis="x")
        self.plot.enableAutoRange(axis="y")


class PlaceholderPanel(Panel):
    """Hueco reservado para algo que aún no llega (el GPS)."""

    def __init__(self, title: str, message: str):
        super().__init__(title)
        label = QLabel(message, objectName="muted", alignment=Qt.AlignCenter, wordWrap=True)
        self.body.addWidget(label, 1)


# ==================================================================
# Estado


class InitBitsPanel(Panel):
    """Init bits de la FSM, siempre a la vista."""

    def __init__(self):
        super().__init__("Init bits")
        self.boot = QLabel("", objectName="muted")
        self.head_layout.addWidget(self.boot)

        self.summary = QLabel("", objectName="initSummary")
        self.body.addWidget(self.summary)

        self.rows = []
        grid = QVBoxLayout()
        grid.setSpacing(0)
        for name, detail, _ in INIT_MODULES:
            row = QFrame(objectName="initRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.setSpacing(8)
            dot = QLabel("●")
            dot.setFixedWidth(8)
            layout.addWidget(dot)
            layout.addWidget(QLabel(f'{name} <span style="font-weight:normal">&nbsp;{detail}</span>',
                                    objectName="initName"), 1)
            state = QLabel("—", objectName="initState")
            layout.addWidget(state)
            grid.addWidget(row)
            self.rows.append((row, dot, state))
        self.body.addLayout(grid)

        self.meta = QLabel("", objectName="muted", alignment=Qt.AlignRight)
        self.body.addWidget(self.meta)
        self.c: dict = {}
        self.fsm: dict | None = None

    def set_theme(self, c: dict):
        self.c = c
        self.set_fsm(self.fsm)

    def set_fsm(self, fsm: dict | None):
        self.fsm = fsm
        failed = set(fsm["failed"]) if fsm else set()
        failed_modules = [name for name, _, bits in INIT_MODULES if any(b in failed for b, _ in bits)]

        if not fsm:
            set_state(self.summary, "pending")
            self.summary.setText("Esperando paquete de init")
        elif not failed_modules:
            set_state(self.summary, "ok")
            self.summary.setText("Todos los módulos OK")
        else:
            set_state(self.summary, "fail")
            self.summary.setText(f"Fallo en {', '.join(failed_modules)}")

        for (row, dot, state), (_, _, bits) in zip(self.rows, INIT_MODULES):
            module_failed = [label for bit, label in bits if bit in failed]
            status = "pending" if not fsm else "fail" if module_failed else "ok"
            set_state(row, status)
            set_state(state, status)
            state.setText({"pending": "—", "ok": "OK"}.get(status, f"FALLO {' + '.join(module_failed)}"))
            if self.c:
                color = {"pending": self.c["border_strong"], "ok": self.c["ok"], "fail": self.c["fail"]}[status]
                dot.setStyleSheet(f"color: {color}; font-size: 9px;")

        self.boot.setText(f"arranque T+ {fmt(fsm['timestamp_ms'] / 1000, 2)} s" if fsm else "")
        self.meta.setText(f"fsm 0x{fsm['fsm_errors']:04X} · core 0x{fsm['common_errors']:04X}" if fsm else "")


class EventLog(Panel):
    """Eventos del backend, el más reciente arriba."""

    def __init__(self):
        super().__init__("Eventos")
        self.show_losses = QCheckBox("mostrar pérdidas")
        self.show_losses.toggled.connect(lambda _: self.render())
        self.head_layout.addWidget(self.show_losses)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.body.addWidget(self.view, 1)
        self.logs: list = []
        self.c: dict = {}

    def set_theme(self, c: dict):
        self.c = c
        self.render()

    def set_logs(self, logs: list):
        self.logs = logs
        self.render()

    def render(self):
        if not self.c:
            return
        c = self.c
        # Avisos de paquetes perdidos: llegan constantemente y ya se resumen en el indicador de enlace
        visible = [l for l in self.logs if self.show_losses.isChecked() or "Perdidos:" not in l.message]
        hidden = len(self.logs) - len(visible)
        color = {"INFO": c["text"], "WARNING": c["warn"], "ERROR": c["fail"]}
        rows = []
        for log in reversed(visible):
            t = "" if log.timestamp_ms is None else f"T+{fmt(log.timestamp_ms / 1000, 1)}"
            rows.append(
                f'<tr><td width="52" style="color:{c["muted"]}">{t}</td>'
                f'<td style="color:{color.get(log.level.value, c["text"])}">{html.escape(log.message)}</td></tr>')
        if not visible:
            rows.append(f'<tr><td style="color:{c["muted"]}">Sin eventos</td></tr>')
        if hidden:
            rows.append(f'<tr><td colspan="2" style="color:{c["muted"]}">'
                        f'{hidden} avisos de paquetes perdidos ocultos</td></tr>')
        scroll = self.view.verticalScrollBar().value()
        self.view.setHtml(f'<table width="100%" cellspacing="0" cellpadding="2" '
                          f'style="border-collapse:collapse">{"".join(rows)}</table>')
        self.view.verticalScrollBar().setValue(scroll)


def grid_of(widgets: list[QWidget], columns: int, spacing: int = 6) -> QGridLayout:
    grid = QGridLayout()
    grid.setSpacing(spacing)
    grid.setContentsMargins(0, 0, 0, 0)
    for i, widget in enumerate(widgets):
        grid.addWidget(widget, i // columns, i % columns)
    for col in range(columns):
        grid.setColumnStretch(col, 1)
    return grid
