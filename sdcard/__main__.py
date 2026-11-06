"""Volcar y leer la SD de vuelo: busca la SD, la copia a un .bin, saca los CSV y marca el apogeo.

Uso (desde la raíz del repo):
    uv run python -m sdcard                         # busca la SD sola, la vuelca y la analiza
    uv run python -m sdcard --device /dev/sda       # sin buscar
    uv run python -m sdcard --bin spp_dump.bin      # analizar un volcado ya hecho con dd
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from backend.recording.telemetry_logger import TelemetryLogger  # noqa: E402
from backend.telemetry.models import BAROPacket, FSMPacket, IMUPacket  # noqa: E402

from . import device  # noqa: E402
from .dump import FIRST_DATA_SECTOR, SECTOR_SIZE, Apogee, DumpContents, Session, baro_series, decode_dump, find_apogee  # noqa: E402

MIB = device.MIB


def main():
    parser = argparse.ArgumentParser(prog="sdcard", description="Solaris · volcado y análisis de la SD de vuelo")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--device", help="dispositivo de la SD, p. ej. /dev/sda (por defecto se busca solo)")
    source.add_argument("--bin", type=Path, help="analizar un volcado ya hecho en vez de leer la SD")
    parser.add_argument("--first-sector", type=int, default=FIRST_DATA_SECTOR,
                        help=f"primer sector de datos de la SD (por defecto {FIRST_DATA_SECTOR}); "
                             "con --bin, el sector en el que empieza el volcado (el skip de dd)")
    parser.add_argument("--max-mib", type=int, default=1024, help="tope de MiB a leer de la SD (por defecto 1024)")
    parser.add_argument("--stop-empty-mib", type=int, default=16,
                        help="dejar de leer tras tantos MiB seguidos sin datos (por defecto 16)")
    parser.add_argument("--session", type=int, default=1,
                        help="sesión a analizar si en la SD hay varias (1 = el último arranque, por defecto)")
    parser.add_argument("--out", type=Path, help="carpeta de salida (por defecto logs/sd_AAAAMMDD_HHMMSS)")
    parser.add_argument("-y", "--yes", action="store_true", help="no preguntar antes de volcar la SD detectada")
    parser.add_argument("--no-plot", action="store_true", help="no abrir la gráfica (se guarda el PNG igual)")
    parser.add_argument("--theme", choices=["light", "dark"], default="light", help="colores de la gráfica")
    args = parser.parse_args()

    out = args.out or REPO / "logs" / f"sd_{datetime.now():%Y%m%d_%H%M%S}"

    if args.bin:
        dump_path = args.bin
        out.mkdir(parents=True, exist_ok=True)
    else:
        path = args.device or detect_sd(args.first_sector, args.yes)
        out.mkdir(parents=True, exist_ok=True)   # Después de buscar la SD: si no está, no deja carpetas vacías
        dump_path = out / "spp_dump.bin"
        print(f"Volcando {path} desde el sector {args.first_sector} a {dump_path}")
        copied = device.dump_device(path, dump_path, args.first_sector * SECTOR_SIZE,
                                    args.max_mib * MIB, args.stop_empty_mib * MIB)
        print(f"Copiados {copied / MIB:.1f} MiB")

    contents = decode_dump(dump_path.read_bytes())
    print_sessions(contents, args.first_sector)
    if not contents.sessions:
        sys.exit(f"No hay ninguna trama SPP válida en {dump_path}. ¿Es la SD de vuelo? ¿Está bien --first-sector?")
    if not 1 <= args.session <= len(contents.sessions):
        sys.exit(f"--session tiene que estar entre 1 y {len(contents.sessions)}")
    session = contents.sessions[args.session - 1]

    write_csvs(session, out)
    t_ms, altitude = baro_series(session)
    apogee = find_apogee(t_ms, altitude)
    summary = apogee_banner(apogee)
    (out / "apogeo.txt").write_text(summary + "\n")
    print_highlighted(summary)
    print(f"\nCSV, apogeo.txt y altitud.png en {out}")

    if apogee is not None:
        from .plot import show_altitude
        show_altitude(t_ms, altitude, apogee, out / "altitud.png", theme=args.theme, interactive=not args.no_plot)


def detect_sd(first_sector: int, assume_yes: bool) -> str:
    disks = device.list_removable_disks()
    if not disks:
        sys.exit("No hay ningún disco extraíble sin montar. ¿Está metida la SD? "
                 "Se puede indicar a mano con --device (mirar lsblk -o NAME,SIZE,MODEL,MOUNTPOINTS).")
    if any(device.needs_sudo(d.path) for d in disks):
        device.ask_sudo_password("Para leer la SD hace falta sudo (solo se lee, nunca se escribe en ella).")

    flight = [d for d in disks if device.has_spp_data(d.path, first_sector * SECTOR_SIZE)]
    others = [d for d in disks if d not in flight]
    for d in others:
        print(f"  descartado {d.describe()}: no tiene tramas SPP en el sector {first_sector}")
    if not flight:
        sys.exit("Ningún disco extraíble tiene datos de vuelo. Si la SD está ahí, indicarla con --device.")
    if len(flight) > 1:
        sys.exit("Hay varias SD con datos de vuelo, elegir una con --device:\n"
                 + "\n".join(f"  {d.describe()}" for d in flight))

    sd = flight[0]
    print(f"SD de vuelo: {sd.describe()}")
    if not assume_yes and input("¿Volcarla? [S/n] ").strip().lower() not in ("", "s", "si", "sí", "y", "yes"):
        sys.exit("Cancelado")
    return sd.path


def print_sessions(contents: DumpContents, first_sector: int):
    print(f"\n{contents.frames} tramas con CRC válido")
    for reason, n in contents.discarded.most_common():
        print(f"  {n} descartadas: {reason}")
    if len(contents.sessions) > 1:
        print("Hay varias sesiones (arranques de la placa) en la SD; la 1 es la del último arranque:")
    for i, s in enumerate(contents.sessions, 1):
        sectors = f"sectores {first_sector + s.first_offset // SECTOR_SIZE}-{first_sector + s.last_offset // SECTOR_SIZE}"
        dup = f", {s.duplicates} duplicados" if s.duplicates else ""
        print(f"  sesión {i}: t {s.t_start / 1000:.1f}-{s.t_end / 1000:.1f} s ({(s.t_end - s.t_start) / 1000:.1f} s), "
              f"{s.count(BAROPacket)} BARO, {s.count(IMUPacket)} IMU, {s.count(FSMPacket)} FSM{dup} · {sectors}")
        for offset, dt in s.gaps:
            print(f"    OJO: salto de {dt / 1000:.1f} s en el sector {first_sector + offset // SECTOR_SIZE}: "
                  "un corte del log o restos de otro arranque (borrar la SD antes de volar lo evita)")


def write_csvs(session: Session, out: Path):
    # Mismo formato que los CSV de la telemetría en directo
    csv = TelemetryLogger(log_dir=str(out))
    for r in session.records:
        if isinstance(r.packet.payload, BAROPacket):
            csv.log_baro(r.packet)
        elif isinstance(r.packet.payload, IMUPacket):
            csv.log_imu(r.packet)
        elif isinstance(r.packet.payload, FSMPacket):
            csv.log_fsm(r.packet)
    csv.close()


def apogee_banner(apogee: Apogee | None) -> str:
    if apogee is None:
        return "Sin datos del barómetro: no se puede calcular el apogeo"
    lines = [f"APOGEO   {apogee.agl:.1f} m sobre la rampa",
             f"         {apogee.altitude:.1f} m de altitud del barómetro (rampa: {apogee.ground:.1f} m)"]
    if apogee.liftoff_ts is not None:
        lines.append(f"         T+{apogee.t_from_liftoff:.2f} s desde el despegue")
    else:
        lines.append("         (no se ve el despegue: el log empieza ya en el aire)")
    lines.append(f"         t = {apogee.ts} ms del firmware")
    if apogee.agl < 10:
        lines.append("         OJO: menos de 10 m sobre la rampa, no parece un vuelo")
    width = max(len(line) for line in lines) + 4
    return "\n".join(["╔" + "═" * width + "╗"] + [f"║  {line:<{width - 2}}║" for line in lines] + ["╚" + "═" * width + "╝"])


def print_highlighted(text: str):
    if sys.stdout.isatty():
        text = f"\033[1;93m{text}\033[0m"   # Negrita amarilla
    print("\n" + text)


if __name__ == "__main__":
    main()
