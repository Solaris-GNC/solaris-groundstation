#!/usr/bin/env sh
# Añade la estación de tierra al menú de aplicaciones de Linux, con la insignia de Solaris como
# icono. En GNOME es la única forma de que el dock enseñe el icono: desde GNOME 44 ignora el que
# pone la propia ventana y lo saca siempre de un .desktop.
#
# Uso (desde cualquier sitio):
#   scripts/install-desktop.sh                       # lanza la app con uv
#   scripts/install-desktop.sh --python /ruta/python # o con ese Python (p. ej. un entorno conda)
#   scripts/install-desktop.sh --uninstall
#
# El .desktop apunta a esta copia del repo: si se mueve, hay que volver a instalarlo.
set -eu

NAME="solaris-groundstation"   # Tiene que coincidir con DESKTOP_FILE_NAME de groundstation/__main__.py
REPO="$(cd "$(dirname "$0")/.." && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP="$APPS/$NAME.desktop"

refresh() {
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$APPS" || true
}

case "${1:-}" in
    --uninstall)
        rm -f "$DESKTOP"
        refresh
        echo "Quitado $DESKTOP"
        exit 0
        ;;
    --python)
        PYTHON="${2:?Falta la ruta del Python}"
        EXEC="\"$PYTHON\" -m groundstation"
        ;;
    "")
        UV="$(command -v uv || true)"
        if [ -z "$UV" ]; then
            echo "No se encuentra uv. Instálalo (ver README) o indica un Python: $0 --python /ruta/python" >&2
            exit 1
        fi
        EXEC="\"$UV\" run --project \"$REPO\" python -m groundstation"
        ;;
    *)
        echo "Uso: $0 [--python /ruta/python | --uninstall]" >&2
        exit 2
        ;;
esac

mkdir -p "$APPS"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Solaris Ground Station
Comment=Telemetría de Solaris en directo
Exec=$EXEC
Path=$REPO
Icon=$REPO/groundstation/assets/solaris_insignia.svg
Terminal=false
Categories=Science;Engineering;
StartupWMClass=$NAME
EOF
refresh
echo "Instalado $DESKTOP"
echo "La app aparece en el menú de aplicaciones como \"Solaris Ground Station\"."
