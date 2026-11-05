"""Ventana principal: cabecera, medidas, estado y gráficas."""

import queue
import time

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget,
)

from backend.telemetry.models import BAROPacket, FSMPacket, IMUPacket, LogLevel
from backend.telemetry.state import global_state

from .attitude_view import OrientationWindow
from .source import TelemetrySource
from .store import Store
from .theme import LOGOS, THEMES, stylesheet
from .widgets import (
    EventLog, GroundButtons, InitBitsPanel, Segmented, StatCard, TimePlot, Zone, break_wraps, fmt,
    grid_of, install_fullscreen_keys, set_state, status_text,
)

REFRESH_MS = 100  # Ritmo de refresco
# Si repintar las gráficas tarda, se espera proporcionalmente antes del siguiente repintado:
# con sesiones muy largas en "Todo" se refresca menos a menudo, pero la ventana nunca se congela
REDRAW_BUDGET = 0.3
WINDOWS = [("30 s", 30), ("2 min", 120), ("Todo", None)]

DEFAULT_W = 1  # Ancho de línea por defecto de las series (más de 1 px es bastante más lento)


class MainWindow(QMainWindow):
    def __init__(self, source: TelemetrySource, font_family: str, theme: str | None = None):
        super().__init__()
        self.source = source
        self.family = font_family
        self.store = Store()
        self.settings = QSettings("Solaris", "GroundStation")
        self.theme = theme or self.settings.value("theme", "dark")
        self.window_s = WINDOWS[0][1]
        self.drawn_version = -1
        self.next_redraw_at = 0.0
        self.was_connected: bool | None = None

        self.setWindowTitle("Solaris · Ground station")
        self.setMinimumSize(1200, 760)
        self.resize(1440, 900)
        self.orientation = OrientationWindow(self)
        self.orientation.center_requested.connect(self.center_view)
        install_fullscreen_keys(self)
        self._build()
        self.apply_theme(self.theme)
        if self.settings.value("orientation_open", False, type=bool):
            self.open_orientation()

        self.timer = QTimer(self, interval=REFRESH_MS, timeout=self.tick)
        self.timer.start()

    # ==================================================================
    # Construcción

    def _build(self):
        root = QWidget(objectName="root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(8)
        self.setCentralWidget(root)

        layout.addWidget(self._build_topbar())

        # Medidas
        self.stats = {
            "altitude": StatCard("Altitud", "m"),
            "apogee": StatCard("Apogeo", "m"),
            "vz": StatCard("Vel. vertical", "m/s"),
            "accel": StatCard("Aceleración", "g"),
            "tilt": StatCard("Inclinación", "°"),
            "temperature": StatCard("Temperatura", "°C"),
            "pressure": StatCard("Presión", "hPa"),
            "link": StatCard("Enlace", "muestras/s"),
        }
        stats_zone = Zone("Medidas")
        self.ground = GroundButtons()
        self.ground.set_clicked.connect(self.set_ground)
        self.ground.clear_clicked.connect(self.clear_ground)
        stats_zone.head_layout.addWidget(self.ground)
        stats_zone.body.addLayout(grid_of(list(self.stats.values()), columns=8))
        wrap = QHBoxLayout()
        wrap.setContentsMargins(8, 0, 8, 0)
        wrap.addWidget(stats_zone)
        layout.addLayout(wrap)

        # Estado | gráficas
        main = QHBoxLayout()
        main.setContentsMargins(8, 0, 8, 0)
        main.setSpacing(8)

        sidebar = Zone("Estado")
        sidebar.setFixedWidth(300)
        self.init_bits = InitBitsPanel()
        self.events = EventLog()
        sidebar.body.addWidget(self.init_bits)
        sidebar.body.addWidget(self.events, 1)
        main.addWidget(sidebar)

        # Gráficas pequeñas con el mismo eje de tiempo, una magnitud por gráfica.
        # Series: (nombre, clave de color, decimales, ancho de línea, discontinua)
        self.plots = {
            "altitude": TimePlot("Altitud", "m", [("Altitud", "x", 1, 1.5, False)]),
            "vz": TimePlot("Velocidad vertical", "m/s", [("Vz", "x", 1, 1.5, False)], zero_line=True),
            "accel": TimePlot("Aceleración", "g", [
                ("|a|", "ink", 2, 1.5, False), ("X", "x", 2, DEFAULT_W, False),
                ("Y", "y", 2, DEFAULT_W, False), ("Z", "z", 2, DEFAULT_W, False)]),
            "gyro": TimePlot("Velocidad angular", "°/s", [
                ("X", "x", 0, DEFAULT_W, False), ("Y", "y", 0, DEFAULT_W, False),
                ("Z", "z", 0, DEFAULT_W, False)], zero_line=True),
            # Pitch/yaw y roll por separado: el roll recorre ±180º y aplastaría la inclinación
            "attitude": TimePlot("Actitud", "°", [
                ("Inclinación", "ink", 1, 1.5, False), ("Pitch", "x", 1, DEFAULT_W, True),
                ("Yaw", "y", 1, DEFAULT_W, True)], zero_line=True),
            "roll": TimePlot("Roll", "°", [("Roll", "z", 0, DEFAULT_W, False)], zero_line=True),
        }
        # Dos filas de tres: barómetro y aceleración arriba, giro y actitud abajo
        charts = Zone("Gráficas")
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        layout_rows = [["altitude", "vz", "accel"], ["gyro", "attitude", "roll"]]
        for row, keys in enumerate(layout_rows):
            for col, key in enumerate(keys):
                grid.addWidget(self.plots[key], row, col)
            grid.setRowStretch(row, 1)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        charts.body.addLayout(grid, 1)
        main.addWidget(charts, 1)
        layout.addLayout(main, 1)

    def _build_topbar(self) -> QFrame:
        bar = QFrame(objectName="topbar")
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(18)

        self.logo = QLabel()
        layout.addWidget(self.logo)
        layout.addWidget(QLabel("Ground station", objectName="title"))
        layout.addStretch(1)

        self.receiver_state = QLabel()
        self.data_state = QLabel()
        self.reboots_state = QLabel()
        status = QHBoxLayout()
        status.setSpacing(14)
        for label in (self.receiver_state, self.data_state, self.reboots_state):
            label.setTextFormat(Qt.RichText)
            status.addWidget(label)
        layout.addLayout(status)

        self.clock = QLabel("T+ 0.0 s", objectName="clock", alignment=Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.clock)

        orientation = QPushButton("Orientación 3D", objectName="topButton")
        orientation.setCursor(Qt.PointingHandCursor)
        orientation.setToolTip("Abre una ventana con el cohete en 3D (F11: pantalla completa)")
        orientation.clicked.connect(self.open_orientation)
        layout.addWidget(orientation)

        windows = Segmented(WINDOWS, self.window_s)
        windows.changed.connect(self.set_window)
        layout.addWidget(windows)
        self.theme_selector = Segmented([("Día", "light"), ("Noche", "dark")], self.theme)
        self.theme_selector.changed.connect(self.apply_theme)
        layout.addWidget(self.theme_selector)
        return bar

    # ==================================================================
    # Acciones

    def set_window(self, seconds):
        self.window_s = seconds
        self.drawn_version = -1  # Fuerza repintado
        self.next_redraw_at = 0.0

    def set_ground(self):
        if not self.store.set_ground():
            global_state.add_log("No se puede fijar la rampa: aún no hay datos del barómetro",
                                 LogLevel.WARNING)
            return
        global_state.add_log(f"Rampa fijada a {fmt(self.store.ground_alt)} m: altitud y apogeo "
                             "se miden desde aquí")
        self._ground_changed()

    def clear_ground(self):
        self.store.clear_ground()
        global_state.add_log("Rampa quitada: altitud en bruto del barómetro")
        self._ground_changed()

    def _ground_changed(self):
        self.ground.set_ground(self.store.ground_alt)
        self.next_redraw_at = 0.0

    def center_view(self):
        self.store.view.center()
        self.store.version += 1  # Repinta aunque no lleguen datos
        self.next_redraw_at = 0.0

    def open_orientation(self):
        geometry = self.settings.value("orientation_geometry")
        if geometry is not None and not self.orientation.isVisible():
            self.orientation.restoreGeometry(geometry)
        self.orientation.show()
        self.orientation.raise_()
        self.orientation.activateWindow()
        self.drawn_version = -1  # Mientras está cerrada no se rellena: se pone al día
        self.next_redraw_at = 0.0

    def apply_theme(self, theme: str):
        self.theme = theme
        self.settings.setValue("theme", theme)
        c = THEMES[theme]
        QApplication.instance().setStyleSheet(stylesheet(c, self.family))
        logo = QPixmap(str(LOGOS[theme]))
        if not logo.isNull():
            self.logo.setPixmap(logo.scaledToHeight(40, Qt.SmoothTransformation))
        for plot in self.plots.values():
            plot.set_theme(c, self.family)
        for card in self.stats.values():
            card.set_theme(c)
        self.orientation.set_theme(c, self.family)
        self.init_bits.set_theme(c)
        self.events.set_theme(c)
        self.drawn_version = -1

    # ==================================================================
    # Bucle de refresco

    def tick(self):
        self._drain_packets()
        self._update_receiver()
        self._update_status()
        now = time.monotonic()
        if self.store.version != self.drawn_version and now >= self.next_redraw_at:
            self._redraw()
            self.drawn_version = self.store.version
            took = time.monotonic() - now
            self.next_redraw_at = now + took / REDRAW_BUDGET
        self._update_logs()

    def _drain_packets(self):
        while True:
            try:
                packet = self.source.packets.get_nowait()
            except queue.Empty:
                return
            ts = packet.secondary_header.timestamp_ms
            p = packet.payload
            if isinstance(p, BAROPacket):
                self.store.add_baro(ts, p.altitude, p.pressure, p.temperature)
            elif isinstance(p, IMUPacket):
                self.store.add_imu(ts, (p.accel_x, p.accel_y, p.accel_z), (p.gyro_x, p.gyro_y, p.gyro_z),
                                   (p.quat_w, p.quat_x, p.quat_y, p.quat_z))
            elif isinstance(p, FSMPacket):
                self.store.set_fsm(ts, p.fsm_errors, p.common_errors, p.failed)
                self.init_bits.set_fsm(self.store.fsm)

    def _update_receiver(self):
        connected = self.source.connected
        if connected != self.was_connected:
            if connected:
                global_state.add_log(f"Receptor conectado: {self.source.port}")
            elif self.was_connected is not None:
                global_state.add_log("Receptor desconectado", LogLevel.WARNING)
            self.was_connected = connected
        port = (self.source.port or "").rsplit("/", 1)[-1]
        set_state(self.receiver_state, "ok" if connected else "fail")
        self.receiver_state.setText(status_text(f"Receptor {port}" if connected else "Receptor desconectado"))
        self.receiver_state.setToolTip(self.source.port or "Buscando el receptor en los puertos serie…")

    def _update_status(self):
        s = self.store
        age = s.data_age()
        stale = s.is_stale()
        set_state(self.data_state, "fail" if stale else "ok")
        self.data_state.setText(status_text(
            ("Sin datos" + ("" if age is None else f" {fmt(age, 0)} s")) if stale else "En vivo"))
        self.reboots_state.setVisible(s.reboots > 0)
        set_state(self.reboots_state, "warn")
        self.reboots_state.setText(status_text(f"{s.reboots} reinicios"))
        self.clock.setText(f"T+ {fmt(s.t_now(), 1)} s")
        self.stats["link"].set(fmt(s.sample_rate(), 1), sub=f"{global_state.packets_lost} paquetes perdidos")

    def _update_logs(self):
        with global_state._lock:
            logs = list(global_state.logs)
        if len(logs) != len(self.events.logs) or (logs and logs[-1] is not self.events.logs[-1]):
            self.events.set_logs(logs)

    def _redraw(self):
        s = self.store
        t_now = s.t_now()
        x_min = None if self.window_s is None or t_now == 0 else max(0.0, t_now - self.window_s)
        x_range = None if x_min is None else (x_min, t_now)

        # Cada gráfica recibe solo las muestras de la ventana visible (vistas, sin copiar)
        b0, i0 = s.baro.window_start(x_min), s.imu.window_start(x_min)
        bt, it = s.baro.t[b0:], s.imu.t[i0:]
        b = {k: v[b0:] for k, v in s.baro.cols.items()}
        i = {k: v[i0:] for k, v in s.imu.cols.items()}

        # Altitud y apogeo respecto a la rampa, si está fijada
        altitude = s.altitude_agl(b["altitude"])
        apogee_alt = s.altitude_agl(s.apogee[1]) if s.apogee else None
        apogee = None
        if s.apogee and (x_min is None or s.apogee[0] >= x_min):
            apogee = ([s.apogee[0]], [apogee_alt])
        self.plots["altitude"].set_data(bt, [altitude], x_range, marker=apogee)
        self.plots["vz"].set_data(bt, [b["vz"]], x_range)
        self.plots["accel"].set_data(it, [i["amag"], i["ax"], i["ay"], i["az"]], x_range)
        self.plots["gyro"].set_data(it, [i["gx"], i["gy"], i["gz"]], x_range)
        self.plots["attitude"].set_data(it, [i["tilt"], i["pitch"], i["yaw"]], x_range)
        self.plots["roll"].set_data(*break_wraps(it, i["roll"]), x_range)
        if self.orientation.isVisible():
            self.orientation.set_attitude(s)

        last_b = lambda k: s.baro.last(k)
        last_i = lambda k: s.imu.last(k)
        pressure = last_b("pressure")
        self.stats["altitude"].set(fmt(s.altitude_agl(last_b("altitude"))), altitude)
        self.stats["apogee"].set(fmt(apogee_alt),
                                 sub=f"T+ {fmt(s.apogee[0], 1)} s" if s.apogee else "")
        self.stats["vz"].set(fmt(last_b("vz")), b["vz"])
        self.stats["accel"].set(fmt(last_i("amag"), 2), i["amag"], sub=f"máx {fmt(s.max_g, 2)} g")
        self.stats["tilt"].set(fmt(last_i("tilt")), i["tilt"])
        self.stats["temperature"].set(fmt(last_b("temperature")), b["temperature"])
        self.stats["pressure"].set(fmt(pressure / 100 if pressure is not None else None),
                                   b["pressure"])

    def closeEvent(self, event):
        # Se recuerda si la ventana de orientación estaba abierta y dónde, para la próxima vez
        if self.orientation.isFullScreen():
            self.orientation.showNormal()  # Se guarda el tamaño normal, no el de pantalla completa
        self.settings.setValue("orientation_open", self.orientation.isVisible())
        self.settings.setValue("orientation_geometry", self.orientation.saveGeometry())
        self.orientation.close()
        self.source.stop()
        super().closeEvent(event)
