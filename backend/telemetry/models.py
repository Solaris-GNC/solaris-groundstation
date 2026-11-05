from pydantic import BaseModel, ConfigDict, Field
from typing import Union, Optional
from enum import Enum

# ==================================================================
# KPIDs fijos del firmware (spp/services/kpid.h)
KPID_LOG = 0x01
KPID_FSM = 0x02

# KPIDs de sensores: los asigna pubsub según el orden de registro en custom.c,
# así que pueden cambiar. Solo se usan como referencia (fake_stream, tests);
# el decoder identifica los sensores por payload_len.
APID_BARO = 0x04   # BMP
APID_IMU  = 0x08   # IMU

# SOLUCIÓN TEMPORAL: el sensor se identifica por su payload_len.
# Deja de funcionar si dos sensores tienen la misma longitud (p. ej. un GNSS de 3 floats)
BARO_PAYLOAD_LEN = 12   # 3 floats
IMU_PAYLOAD_LEN  = 44   # 11 floats
FSM_PAYLOAD_LEN  = 4    # 2 x uint16 (FsmErrors_t + CommonBitErrors_t)

# Bits de error del paquete FSM, en orden de bit (0 = LSB). Nombres tal cual en el firmware.
# FsmErrors_t (main/custom.h). OJO: fsmInitError, uartPubsubError y uartInitError
# nunca los escribe custom.c, así que un 0 ahí no significa OK sino "no comprobado".
FSM_ERROR_BITS = [
    "fsmInitError", "bmpPubsubError", "icmPubsubError", "datalogggerPubsubError",
    "uartPubsubError", "sx1262PubsubError", "bmpInitError", "icmInitError",
    "dataloggerInitError", "uartInitError", "sx1262InitError",
]
# CommonBitErrors_t (spp/core/commonbit.h)
COMMON_ERROR_BITS = ["coreInitError", "logInitError", "dataBankInitError", "pubsubInitError"]

# Versión del protocolo SPP esperada
K_SPP_PKT_VERSION = 1

# ==================================================================
# Cabeceras
class SPPPrimaryHeader(BaseModel):                                                  # Valorar seriamente usar StrictInt
    version: int = Field(..., ge=K_SPP_PKT_VERSION, le=K_SPP_PKT_VERSION)           # (1 Byte) forzado a 1
    apid: int = Field(..., ge=0, le=0xFFFF)                                         # (2 Bytes)
    seq: int = Field(..., ge=0, le=0xFFFF)                                          # (2 Bytes)
    payload_len: int = Field(..., serialization_alias="payloadLen", ge=0, le=50)    # (2 Bytes)

class SPPSecondaryHeader(BaseModel):
    timestamp_ms: int = Field(..., serialization_alias="timestampMs",
                              ge=0, le=0xFFFFFFFF)                                  # (4 Bytes)
    drop_counter: int = Field(..., ge=0, le=0xFF)                                   # (1 Byte)

# ==================================================================
# BARO (BMP) · payload_len esperado ~12 (3 floats)
#TODO: asignar rangos de validación según datasheet
class BAROPacket(BaseModel):
    # NaN/inf (sensor sin inicializar, trama corrupta que pasa el CRC) se rechazan: en las gráficas
    # y en la orientación 3D un solo NaN lo estropea todo
    model_config = ConfigDict(allow_inf_nan=False)
    altitude: float = Field(...)      # metros
    pressure: float = Field(...)      # Pa
    temperature: float = Field(...)   # ºC

# ==================================================================
class IMUPacket(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    accel_x: float = Field(...)   # G
    accel_y: float = Field(...)
    accel_z: float = Field(...)
    gyro_x: float = Field(...)    # dps
    gyro_y: float = Field(...)
    gyro_z: float = Field(...)
    quat_w: float = Field(...)
    quat_x: float = Field(...)
    quat_y: float = Field(...)
    quat_z: float = Field(...)
    accuracy: float = Field(...)

# ==================================================================
# FSM · init bits (KPID 0x02, payload_len 4). Lo manda action_emitTelemetry() una vez
# al arrancar, con el estado de inicialización de todos los módulos
class FSMPacket(BaseModel):
    fsm_errors: int = Field(..., ge=0, le=0xFFFF)       # FsmErrors_t.errors
    common_errors: int = Field(..., ge=0, le=0xFFFF)    # CommonBitErrors_t.errors
    failed: list[str] = Field(default_factory=list)     # Nombres de los bits a 1

# ==================================================================
# Logging del backend (NO es un paquete del cohete)
class LogLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

class LogEntry(BaseModel):
    level: LogLevel = LogLevel.INFO
    message: str
    timestamp_ms: Optional[int] = None

# ==================================================================
# Paquete completo
class TelemetryPacket(BaseModel):
    primary_header: SPPPrimaryHeader
    secondary_header: SPPSecondaryHeader
    payload: Union[BAROPacket, IMUPacket, FSMPacket]
    crc16: int = Field(..., ge=0, le=0xFFFF)  # (2 Bytes)
