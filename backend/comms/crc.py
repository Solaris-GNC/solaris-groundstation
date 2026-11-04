def crc16_ccitt(data: bytes, poly=0x1021, init=0xFFFF):

    crc = init

    for b in data:
        crc ^= (b << 8)

        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1

            crc &= 0xFFFF

    return crc

