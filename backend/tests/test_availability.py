"""Testes do núcleo de disponibilidade — risco nº 1 da spec."""
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.availability import (
    Busy, Window, candidate_starts, find_conflict, free_slots, is_bookable,
    local_day_bounds_utc, overlaps,
)

TZ = "America/Sao_Paulo"
SP = ZoneInfo(TZ)
DAY = date(2026, 11, 16)  # segunda-feira
HOURS = {0: [Window(time(9), time(12)), Window(time(13), time(18))]}  # almoço 12–13


def local(h, m=0, d=DAY):
    return datetime.combine(d, time(h, m), tzinfo=SP).astimezone(UTC)


def busy(h, m, dur, status="scheduled"):
    s = local(h, m)
    return Busy(s, s + timedelta(minutes=dur), status)


def as_local(slots):
    return [s.astimezone(SP).strftime("%H:%M") for s in slots]


# --- overlap -----------------------------------------------------------------

def test_overlap_basico():
    assert overlaps(local(10), local(11), local(10, 30), local(11, 30))

def test_encostar_nao_e_conflito():
    assert not overlaps(local(10), local(10, 30), local(10, 30), local(11))
    assert not overlaps(local(10, 30), local(11), local(10), local(10, 30))

def test_contido_e_contendo():
    assert overlaps(local(10), local(12), local(10, 30), local(11))
    assert overlaps(local(10, 30), local(11), local(10), local(12))

def test_naive_e_rejeitado():
    with pytest.raises(ValueError):
        overlaps(datetime(2026, 1, 1, 10), local(11), local(10), local(12))


# --- grade e duração dinâmica -------------------------------------------------

def test_servico_precisa_caber_na_janela():
    # 45 min: manhã 09:00..11:00 (11:30 terminaria 12:15), tarde 13:00..17:00
    slots = as_local(candidate_starts(DAY, TZ, HOURS, 45, 30))
    assert slots[0] == "09:00" and "11:00" in slots and "11:30" not in slots
    assert "12:00" not in slots and "12:30" not in slots
    assert slots[-1] == "17:00"

def test_dia_fechado_sem_slots():
    assert free_slots(day=DAY + timedelta(days=6), tz=TZ, opening_hours=HOURS,
                      existing=[], duration_min=30) == []

def test_servico_longo_bloqueia_slot_seguinte():
    # corte de 45 min às 14:00 -> 14:30 indisponível mesmo com grade de 30
    slots = as_local(free_slots(day=DAY, tz=TZ, opening_hours=HOURS,
                                existing=[busy(14, 0, 45)], duration_min=30))
    assert "14:00" not in slots and "14:30" not in slots and "15:00" in slots

def test_pedido_longo_nao_cabe_antes_de_existente():
    # existente 15:00; pedido de 60 min: 14:00 ok, 14:30 colide
    slots = as_local(free_slots(day=DAY, tz=TZ, opening_hours=HOURS,
                                existing=[busy(15, 0, 30)], duration_min=60))
    assert "14:00" in slots and "14:30" not in slots and "15:00" not in slots and "15:30" in slots


# --- status --------------------------------------------------------------------

@pytest.mark.parametrize("status,bloqueia", [
    ("scheduled", True), ("completed", True), ("canceled", False), ("no_show", False),
])
def test_status_que_bloqueiam(status, bloqueia):
    assert (find_conflict([busy(10, 0, 30, status)], local(10), local(10, 30)) is not None) == bloqueia


# --- tempo / fuso ----------------------------------------------------------------

def test_remove_horarios_passados():
    slots = as_local(free_slots(day=DAY, tz=TZ, opening_hours=HOURS, existing=[],
                                duration_min=30, now=local(10, 0)))
    assert "10:00" not in slots and slots[0] == "10:30"

def test_grade_e_montada_no_fuso_local():
    # 09:00 em São Paulo = 12:00 UTC
    first = candidate_starts(DAY, TZ, HOURS, 30, 30)[0]
    assert first == datetime(2026, 11, 16, 12, 0, tzinfo=UTC)

def test_limites_do_dia_local_em_utc():
    start, end = local_day_bounds_utc(DAY, TZ)
    assert start == datetime(2026, 11, 16, 3, tzinfo=UTC)
    assert end - start == timedelta(days=1)

def test_agendamento_noturno_fica_no_dia_local():
    # 21:30 local = 00:30 UTC do dia seguinte; precisa cair no dia local certo
    hours = {0: [Window(time(20), time(23))]}
    slots = free_slots(day=DAY, tz=TZ, opening_hours=hours, existing=[], duration_min=30)
    assert "21:30" in as_local(slots)
    assert any(s.date() == DAY + timedelta(days=1) for s in slots)  # UTC já virou o dia


# --- revalidação usada na transação ------------------------------------------------

def test_is_bookable():
    kw = dict(tz=TZ, opening_hours=HOURS, duration_min=30)
    assert is_bookable(start=local(10), existing=[], **kw)
    assert not is_bookable(start=local(10), existing=[busy(10, 0, 30)], **kw)
    assert not is_bookable(start=local(10, 10), existing=[], **kw)  # fora da grade
    assert not is_bookable(start=local(12, 0), existing=[], **kw)   # almoço
    assert is_bookable(start=local(10), existing=[busy(10, 0, 30, "canceled")], **kw)
