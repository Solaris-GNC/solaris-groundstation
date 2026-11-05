"""Tema de la app: colores de día y de noche y la fuente Oxanium.

Heredado del dashboard web de solaris-live-telemetry (index.css y theme.ts).
"""

from pathlib import Path

from PySide6.QtGui import QFontDatabase

ASSETS = Path(__file__).resolve().parent / "assets"
FONT_FILE = ASSETS / "fonts" / "Oxanium.ttf"
LOGOS = {"light": ASSETS / "logo_solaris_light.png", "dark": ASSETS / "logo_solaris_dark.png"}

# Oxanium en todo (sus cifras tienen ancho fijo: los números no bailan al cambiar)
FONT_FAMILY = "Oxanium"

THEMES = {
    "light": {
        # Interfaz
        "bg": "#cfcdc5", "zone": "#e7e5df", "zone_border": "#bdbbb2",
        "header": "#fdfdfc", "panel": "#fdfdfc", "panel_head": "#f1f0eb", "panel_2": "#f1f0eb",
        "border": "#cbc9c1", "border_strong": "#b5b3aa",
        "text": "#2b2a27", "text_strong": "#0b0b0b", "muted": "#6f6e69",
        "ok": "#1d7a1d", "ok_bg": "#e9f3e6", "fail": "#c42b35", "fail_bg": "#fbeceb",
        "warn": "#9a6200",
        # Gráficas
        "x": "#2a78d6", "y": "#eb6834", "z": "#1baf7a", "ink": "#2b2a27",
        "chart_muted": "#898781", "grid": "#e8e7e1", "axis": "#c3c2b7",
        "rocket": "#d4002a",
    },
    "dark": {
        "bg": "#050505", "zone": "#111110", "zone_border": "#2a2a27",
        "header": "#1b1b1a", "panel": "#1b1b1a", "panel_head": "#242422", "panel_2": "#242422",
        "border": "#353531", "border_strong": "#4a4a45",
        "text": "#d6d5cf", "text_strong": "#f0efec", "muted": "#9a9993",
        "ok": "#4cb84c", "ok_bg": "#1d2a1c", "fail": "#e86464", "fail_bg": "#2f1e1d",
        "warn": "#e0a43a",
        "x": "#3987e5", "y": "#d95926", "z": "#199e70", "ink": "#e6e5e0",
        "chart_muted": "#898781", "grid": "#2c2c2a", "axis": "#383835",
        "rocket": "#ff2a4d",
    },
}


def load_font() -> str:
    """Registra Oxanium en Qt. Si no está el archivo se usa la fuente del sistema."""
    if FONT_FILE.exists() and QFontDatabase.addApplicationFont(str(FONT_FILE)) >= 0:
        return FONT_FAMILY
    return ""


def stylesheet(c: dict, family: str) -> str:
    """Hoja de estilo Qt (QSS).

    Los widgets se marcan con objectName (#id) o con propiedades dinámicas ([state="ok"]),
    que hacen el papel de las clases CSS.
    """
    font = f'font-family: "{family}";' if family else ""
    return f"""
    * {{ {font} font-size: 13px; color: {c['text']}; }}
    QMainWindow, #root {{ background: {c['bg']}; }}
    QToolTip {{ background: {c['panel']}; color: {c['text_strong']}; border: 1px solid {c['border']}; }}

    /* Cabecera */
    #topbar {{ background: {c['header']}; border-bottom: 1px solid {c['border']}; }}
    #title {{ font-size: 19px; font-weight: 600; color: {c['text_strong']};
              padding-left: 18px; border-left: 1px solid {c['border_strong']}; }}
    #clock {{ font-size: 18px; font-weight: 600; color: {c['text_strong']}; min-width: 110px; }}
    QLabel[state="ok"] {{ color: {c['ok']}; }}
    QLabel[state="fail"] {{ color: {c['fail']}; font-weight: 600; }}
    QLabel[state="warn"] {{ color: {c['warn']}; font-weight: 600; }}

    /* Selector segmentado (ventana de tiempo, día/noche) */
    #segmented {{ border: 1px solid {c['border_strong']}; border-radius: 2px; }}
    #segmented QPushButton {{ background: transparent; color: {c['muted']}; border: 0;
                              padding: 5px 11px; }}
    #segmented QPushButton + QPushButton {{ border-left: 1px solid {c['border_strong']}; }}
    #segmented QPushButton:hover {{ color: {c['text_strong']}; }}
    /* Botones sueltos de las cabeceras y paneles */
    #topButton {{ background: transparent; color: {c['muted']}; border: 1px solid {c['border_strong']};
                  border-radius: 2px; padding: 5px 11px; }}
    #topButton:hover {{ color: {c['text_strong']}; }}
    #segmented QPushButton:checked {{ background: {c['panel_2']}; color: {c['text_strong']};
                                      font-weight: 600; }}

    /* Bloques: agrupan paneles con fondo y título propios */
    #zone {{ background: {c['zone']}; border: 1px solid {c['zone_border']}; border-radius: 3px; }}
    /* Arriba hay margen para las tildes de mayúsculas (Á): Oxanium no las tiene y la fuente
       de reserva es más alta. Qt no admite letter-spacing en QSS: se aplica en widgets.Zone */
    #zoneTitle {{ font-size: 11px; font-weight: 700; color: {c['muted']}; padding: 3px 2px 0 2px; }}

    /* Paneles con barra de título tipo Grafana */
    #panel {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 2px; }}
    #panelHead {{ background: {c['panel_head']}; border-bottom: 1px solid {c['border']}; }}
    #panelTitle {{ font-size: 13px; font-weight: 600; color: {c['text_strong']}; }}
    #unit, #muted {{ font-size: 11px; color: {c['muted']}; }}

    /* Leyenda de las gráficas: muestra + nombre + último valor; pulsar oculta la serie */
    #legend {{ background: none; border: 0; padding: 0; font-size: 11px; color: {c['muted']}; }}

    /* Medidas */
    #statLabel {{ font-size: 11px; color: {c['muted']}; background: {c['panel_head']};
                  border-bottom: 1px solid {c['border']}; padding: 3px 10px; }}
    #statValue {{ font-size: 22px; font-weight: 600; color: {c['text_strong']}; }}
    #statUnit {{ font-size: 11px; color: {c['muted']}; }}
    #statSub {{ font-size: 11px; color: {c['muted']}; }}

    /* Init bits */
    #initSummary {{ padding: 4px 8px; border-radius: 2px; font-weight: 600; }}
    #initSummary[state="ok"] {{ color: {c['ok']}; background: {c['ok_bg']};
                                border-left: 3px solid {c['ok']}; }}
    #initSummary[state="fail"] {{ color: {c['fail']}; background: {c['fail_bg']};
                                  border-left: 3px solid {c['fail']}; }}
    #initSummary[state="pending"] {{ color: {c['muted']}; background: {c['panel_2']};
                                     border-left: 3px solid {c['muted']}; }}
    #initRow {{ border-radius: 2px; }}
    #initRow[state="fail"] {{ background: {c['fail_bg']}; }}
    #initName {{ font-weight: 600; color: {c['text_strong']}; }}
    #initState {{ font-size: 11px; font-weight: 600; color: {c['muted']}; }}
    #initState[state="ok"] {{ color: {c['ok']}; }}
    #initState[state="fail"] {{ color: {c['fail']}; }}

    /* Eventos */
    QTextBrowser {{ background: transparent; border: 0; font-size: 11px; }}
    QCheckBox {{ font-size: 11px; color: {c['muted']}; spacing: 4px; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; }}
    QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 3px; min-height: 20px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    """
