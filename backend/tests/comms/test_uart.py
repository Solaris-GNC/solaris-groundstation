# Hay que instalar plugin pytest-mock

import pytest
import logging
from pathlib import Path
# import backend.comms.uart as uart
from backend.comms.uart import UART
from serial import SerialException


"""
QUE TESTEAR:

- Si algo erroneo checkear que logee fallo
- Comprobar que duerme
- Configurar mal baud rate
- Recibir paquete a mitad
- Que antena se desincronice dejes de recibir y luego vuelvas a recibir
- Que sea capaz de identificar bien un paquete y engancharse y sincronizarse
- Que sea capaz de hacer frente a velocidad baud rate

EXTRAS:
- Que uart reintenta si falla

"""

# ===== We obtain the real flight data saved to create our tests =====

current_route = Path(__file__).resolve()
backend_route = current_route.parent.parent.parent
data_route = backend_route / "data" / "log_uart.txt"
data = data_route.read_text()

# ===== FIXTURES =====

@pytest.fixture
def fake_buffer():
    return bytes.fromhex(data)          # It returns: b'\x01\x02\xff...'
                                        # Each position represents a single byte
                                        # fake_buffer[1] -> b'\x02'

@pytest.fixture
def fake_serial_object(fake_buffer):
    class Fake_Serial():
        @property
        def in_waiting(self):           # Return number of bytes in buffer
            return len(fake_buffer)
        def read(self, size=1):
            return fake_buffer[:size]
    fake_serial = Fake_Serial()
    return fake_serial





# ===== TESTS =====

# @pytest.mark.skip(reason="we are working on the tests")
def test_uart_read_method_works(mocker, fake_serial_object):        # Posible upgrade: several calls to .read()
    mock_serial = mocker.patch("backend.comms.uart.serial.Serial")
    mock_serial.return_value = fake_serial_object
    uart = UART(port="/dev/ttyUSB0")
    assert uart.read() == bytes.fromhex(data)



def test_connect_method_logs_info(mocker, fake_serial_object, caplog):
    caplog.set_level(logging.INFO)
    mock_serial = mocker.patch("backend.comms.uart.serial.Serial")
    mock_serial.return_value = fake_serial_object
    uart = UART(port="/dev/ttyUSB0")
    uart.read()
    assert "UART conectado" in caplog.text
    # print(f"\n\nAqui el log mi rey:\n\n{caplog.text}")


"""
STILL IN PROGRESS!!!
"""
def test_connect_method_logs_warning(mocker, caplog):

    mock_serial = mocker.patch("backend.comms.uart.serial.Serial")
    mock_serial.side_effect = SerialException("Simulated error")
    uart = UART(port="/dev/ttyUSB0")
    uart.read()
    assert "No se pudo abrir" in caplog.text








def test_read_survives_usb_unplug(mocker, caplog):
    # Al desenchufar el USB, pyserial lanza OSError (EIO) desde in_waiting, no SerialException
    class Unplugged():
        @property
        def in_waiting(self):
            raise OSError(5, "Input/output error")
        def close(self):
            pass
    mock_serial = mocker.patch("backend.comms.uart.serial.Serial")
    mock_serial.return_value = Unplugged()
    uart = UART(port="/dev/ttyUSB0")
    assert uart.read() == b""
    assert not uart.connected
    assert "UART desconectado" in caplog.text
