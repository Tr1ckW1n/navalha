import pytest

from app.domain.booking import BookingError, client_id, normalize_phone_br, parse_opening_hours


@pytest.mark.parametrize("raw", ["(62) 99999-1234", "62999991234", "+55 62 99999-1234", "5562999991234"])
def test_normaliza_telefone(raw):
    assert normalize_phone_br(raw) == "+5562999991234"

def test_telefone_invalido():
    with pytest.raises(BookingError):
        normalize_phone_br("123")

def test_client_id_escopado_ao_tenant():
    p = "+5562999991234"
    assert client_id("shopA", p) != client_id("shopB", p)

def test_parse_opening_hours():
    oh = parse_opening_hours({"0": [{"opens": "09:00", "closes": "12:00"}]})
    assert oh[0][0].opens.hour == 9
