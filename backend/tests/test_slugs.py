import pytest

from app.domain.errors import InvalidRequest
from app.domain.slugs import validate_slug


@pytest.mark.parametrize("raw,ok", [("barbearia-mf", "barbearia-mf"), ("  MF-123 ", "mf-123")])
def test_validos(raw, ok):
    assert validate_slug(raw) == ok


@pytest.mark.parametrize("raw", ["ab", "-mf", "mf-", "mf--x", "mf_x", "barbearia mf", "admin", "panel", "x" * 41])
def test_invalidos(raw):
    with pytest.raises(InvalidRequest):
        validate_slug(raw)
