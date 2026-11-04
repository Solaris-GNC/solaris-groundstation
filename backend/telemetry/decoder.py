import struct
from .models import (
    TelemetryPacket, SPPPrimaryHeader, SPPSecondaryHeader,
    BAROPacket, IMUPacket, FSMPacket,
    KPID_LOG, KPID_FSM, BARO_PAYLOAD_LEN, IMU_PAYLOAD_LEN, FSM_PAYLOAD_LEN,
    FSM_ERROR_BITS, COMMON_ERROR_BITS,
)

# Queda pendiente saber el cambio de estrucutura de los paquetes

# Definir tamaños en macros

class Decoder():

    def frame_to_packet(self, frame: bytes) -> TelemetryPacket:
        self.version      = frame[0]
        self.apid         = int.from_bytes(frame[1:3], "little")
        self.seq          = int.from_bytes(frame[3:5], "little")
        self.payload_len  = int.from_bytes(frame[5:7], "little")
        self.timestamp    = int.from_bytes(frame[7:11], "little")
        self.drop_counter = frame[11]                               # Por que no se convierte a int?
        self.payload_bytes = frame[12:12 + self.payload_len]
        self.crc16 = int.from_bytes(frame[-2:], "little")

        # LOG y FSM tienen KPID fijo: se tratan antes de mirar la longitud
        if self.apid == KPID_FSM:
            if self.payload_len != FSM_PAYLOAD_LEN:
                raise ValueError(f"FSM con payload_len {self.payload_len}, esperado {FSM_PAYLOAD_LEN}")
            payload = self.fsm_payload_decoder()
        elif self.apid == KPID_LOG:
            raise ValueError(f"KPID {hex(self.apid)} (LOG) aún no soportado")
        # Sensores: KPID dinámico, se identifican por payload_len (solución temporal)
        elif self.payload_len == BARO_PAYLOAD_LEN:
            payload = self.baro_payload_decoder()
        elif self.payload_len == IMU_PAYLOAD_LEN:
            payload = self.imu_payload_decoder()
        else:
            raise ValueError(f"KPID {hex(self.apid)} con payload_len desconocido: {self.payload_len}")

        # Montar el paquete
        return TelemetryPacket(
            primary_header=SPPPrimaryHeader(
                version=self.version, apid=self.apid, seq=self.seq, payload_len=self.payload_len,    # He cambiado camelCase a snake_case
            ),
            secondary_header=SPPSecondaryHeader(
                timestamp_ms=self.timestamp, drop_counter=self.drop_counter,
            ),
            payload=payload,
            crc16=self.crc16,
        )

    # Decoders de payload (leen solo los bytes útiles; el resto es padding)
    def baro_payload_decoder(self):
        altitude, pressure, temperature = struct.unpack("<3f", self.payload_bytes)
        return BAROPacket(altitude=altitude, pressure=pressure, temperature=temperature)

    def fsm_payload_decoder(self):
        # 2 uint16: FsmErrors_t.errors, CommonBitErrors_t.errors
        fsm_errors, common_errors = struct.unpack("<2H", self.payload_bytes)
        failed = ([name for bit, name in enumerate(FSM_ERROR_BITS) if fsm_errors >> bit & 1]
                  + [name for bit, name in enumerate(COMMON_ERROR_BITS) if common_errors >> bit & 1])
        return FSMPacket(fsm_errors=fsm_errors, common_errors=common_errors, failed=failed)

    def imu_payload_decoder(self):
        # 11 floats: accel xyz, gyro xyz, quat_w, quat_x, quat_y, quat_z, accuracy
        (ax, ay, az, gx, gy, gz, qw, qx, qy, qz, acc) = struct.unpack("<11f", self.payload_bytes)
        return IMUPacket(
            accel_x=ax, accel_y=ay, accel_z=az,
            gyro_x=gx, gyro_y=gy, gyro_z=gz,
            quat_w=qw, quat_x=qx, quat_y=qy,
            quat_z=qz, accuracy=acc,
        ) 

    # def imu1_payload_decoder(self):
    #     # 12 floats: accel xyz, gyro xyz, mag xyz, quat_w, quat_x, quat_y
    #     (ax, ay, az, gx, gy, gz, mx, my, mz,
    #      qw, qx, qy) = struct.unpack("<12f", self.payload_bytes[:48])
    #     return IMUPacket1(
    #         accel_x=ax, accel_y=ay, accel_z=az,
    #         gyro_x=gx, gyro_y=gy, gyro_z=gz,
    #         mag_x=mx, mag_y=my, mag_z=mz,
    #         quat_w=qw, quat_x=qx, quat_y=qy,
    #     )

    # def imu2_payload_decoder(self):
    #     # 4 floats: quat_z, accuracy
    #     qz, accuracy = struct.unpack("<2f", self.payload_bytes[:8])
    #     return IMUPacket2(quat_z=qz, accuracy=accuracy)

