"""Buscar la SD de vuelo entre los discos del ordenador y volcarla a un fichero.

Solo se LEE del dispositivo, nunca se escribe en él. Aun así no se adivina: un disco es candidato
si es extraíble y no tiene nada montado (la SD de vuelo no tiene sistema de ficheros, así que nunca
se monta), y solo se da por buena si en el primer sector de datos hay tramas SPP con CRC válido.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

from .dump import find_frames

MIB = 1024 * 1024
CHUNK = MIB
PROBE_SIZE = 8 * 512           # 8 sectores: 64 tramas si el firmware escribió algo


@dataclass
class BlockDevice:
    path: str
    size: int                  # Bytes
    model: str
    tran: str                  # usb, mmc... ("" si lsblk no lo sabe)

    def describe(self) -> str:
        parts = [self.path, f"{self.size / 1024 ** 3:.1f} GiB", self.model, self.tran]
        return " · ".join(p for p in parts if p)


def _flag(value) -> bool:
    # lsblk antiguos dan "0"/"1" en vez de booleanos
    return value in (True, 1, "1")


def _mountpoints(dev: dict) -> list[str]:
    points = dev.get("mountpoints") or [dev.get("mountpoint")]   # mountpoint: util-linux < 2.37
    points = [p for p in points if p]
    for child in dev.get("children", []):
        points += _mountpoints(child)
    return points


def removable_disks(lsblk: dict) -> list[BlockDevice]:
    """Discos extraíbles sin nada montado, a partir de la salida de lsblk -J -b."""
    disks = []
    for dev in lsblk.get("blockdevices", []):
        tran = dev.get("tran") or ""
        removable = (_flag(dev.get("rm")) or _flag(dev.get("hotplug")) or tran in ("usb", "mmc")
                     or dev["name"].startswith("mmcblk"))
        size = int(dev.get("size") or 0)   # 0: lector de tarjetas sin tarjeta
        if dev.get("type") != "disk" or not removable or size == 0 or _mountpoints(dev):
            continue
        disks.append(BlockDevice(path=dev.get("path") or f"/dev/{dev['name']}", size=size,
                                 model=(dev.get("model") or "").strip(), tran=tran))
    return disks


def list_removable_disks() -> list[BlockDevice]:
    out = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,PATH,SIZE,MODEL,TRAN,RM,HOTPLUG,TYPE,MOUNTPOINTS"],
                         capture_output=True, text=True, check=True)
    return removable_disks(json.loads(out.stdout))


class DeviceReader:
    """Lee el dispositivo a partir de un offset. Si no hay permiso (lo normal: /dev/sdX es de root)
    se lee con sudo dd y por una tubería, así el volcado queda a nombre del usuario y no de root."""

    def __init__(self, path: str, offset: int):
        self._proc = None
        self._stream: BinaryIO
        try:
            self._stream = open(path, "rb")
            self._stream.seek(offset)
        except PermissionError:
            self._proc = subprocess.Popen(
                ["sudo", "dd", f"if={path}", f"bs={CHUNK}", f"skip={offset}", "iflag=skip_bytes,fullblock",
                 "status=none"],
                stdout=subprocess.PIPE)
            self._stream = self._proc.stdout

    def chunks(self, size: int = CHUNK) -> Iterator[bytes]:
        while chunk := self._stream.read(size):
            yield chunk

    def close(self):
        self._stream.close()
        if self._proc is not None:
            self._proc.terminate()   # Si se para antes del final, dd ya no tiene a quién escribir
            self._proc.wait()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def needs_sudo(path: str) -> bool:
    try:
        open(path, "rb").close()
        return False
    except PermissionError:
        return True


def ask_sudo_password(reason: str):
    """Pide la contraseña antes de empezar, para que no se mezcle con la barra de progreso."""
    print(reason, file=sys.stderr)
    subprocess.run(["sudo", "-v"], check=True)


def has_spp_data(path: str, offset: int) -> bool:
    with DeviceReader(path, offset) as reader:
        head = next(reader.chunks(PROBE_SIZE), b"")
    return bool(find_frames(head))


def dump_device(path: str, out: Path, offset: int, max_bytes: int, stop_after_empty: int) -> int:
    """Copia el dispositivo a `out` desde `offset`. Para tras `stop_after_empty` bytes seguidos sin
    ninguna trama (se acabaron los datos) o al llegar a `max_bytes`. Devuelve los bytes copiados."""
    copied = with_data = 0
    with DeviceReader(path, offset) as reader, open(out, "wb") as f:
        for chunk in reader.chunks():
            chunk = chunk[:max_bytes - copied]
            f.write(chunk)
            copied += len(chunk)
            if find_frames(chunk):
                with_data = copied
            print(f"\r  {copied / MIB:7.1f} MiB leídos · datos hasta {with_data / MIB:.1f} MiB",
                  end="", file=sys.stderr, flush=True)
            if copied >= max_bytes or copied - with_data >= stop_after_empty:
                break
    print(file=sys.stderr)
    return copied
