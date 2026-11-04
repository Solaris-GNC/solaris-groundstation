import pytest
import telemetry.models as models
from pydantic import ValidationError


@pytest.fixture
def valid_header_data():

    return {
        "version": 1,
        "apid": 0,
        "seq": 65535,
        "payload_len": 0
    }


# Try to check this for every packet
def test_valid_data_works(valid_header_data):

    head = models.SPPPrimaryHeader(**valid_header_data)     # En vez de levantar error debería logearlo
    assert head.version == 1
    assert head.apid == 0
    assert head.seq == 65535
    assert head.payload_len == 0


@pytest.mark.parametrize("missing_arg", ["version", "apid", "seq", "payload_len"])
def test_missing_argument_raises_error(valid_header_data, missing_arg):

    valid_header_data.pop(missing_arg)
    with pytest.raises(ValidationError, match=missing_arg):         # Checks exception is raised exclusively due to missing arg
        models.SPPPrimaryHeader(**valid_header_data)


def test_type_coercion_works():     # No sense

    strange_types_head = models.SPPPrimaryHeader(version=1.0, apid="0", seq=0xFF, payload_len=False)
    assert strange_types_head.version == 1 and isinstance(strange_types_head.version, int)
    assert strange_types_head.apid == 0 and isinstance(strange_types_head.apid, int)
    assert strange_types_head.seq == 255 and isinstance(strange_types_head.seq, int)
    assert strange_types_head.payload_len == 0 and isinstance(strange_types_head.payload_len, int)      # Is a good idea to accept bool or string values?


@pytest.mark.parametrize("invalid_arg, invalid_data", [("version", "idc"), ("apid", 6.7), ("seq", [7, 8, 9]), ("payload_len", {"key": 33})])
def test_invalid_types_raise_errors(valid_header_data, invalid_arg, invalid_data):

    wrong_head = valid_header_data
    wrong_head[invalid_arg] = invalid_data
    with pytest.raises(ValidationError, match=invalid_arg):
        models.SPPPrimaryHeader(**wrong_head)


@pytest.mark.parametrize("invalid_field, invalid_range", [("version", 0), ("apid", 66000), ("seq", -1), ("payload_len", 51)])
def test_range_restrictions(valid_header_data, invalid_field, invalid_range):

    wrong_head = valid_header_data
    wrong_head[invalid_field] = invalid_range
    with pytest.raises(ValidationError, match=invalid_field):
        models.SPPPrimaryHeader(**wrong_head)

