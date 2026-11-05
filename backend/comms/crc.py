def _make_table(poly: int) -> list[int]:
    table = []
    for byte in range(256):
        crc = byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
        table.append(crc)
    return table


_TABLE = _make_table(0x1021)


def crc16_ccitt(data: bytes, poly=0x1021, init=0xFFFF):
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), el del firmware.

    Con tabla precalculada: al resincronizar se calcula un CRC por cada byte descartado, y bit a
    bit no daba abasto con ruido a 115200 baudios.
    """
    if poly != 0x1021:
        table = _make_table(poly)
    else:
        table = _TABLE
    crc = init
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ table[(crc >> 8) ^ b]
    return crc
