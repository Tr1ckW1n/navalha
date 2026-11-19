"""Regra de reserva pura (plan_booking) — sem banco."""

from datetime import timedelta

import pytest

from app.domain.booking import BookingContext, BookingRequest, plan_booking
from app.domain.errors import InvalidRequest, NotFound, SlotUnavailable
from tests.conftest import DAY, HOURS, NOW, TZ, at

SHOP = {"id": "s1", "timezone": TZ, "openingHours": HOURS}
ZE = {"id": "b1", "barbershopId": "s1", "name": "Zé", "active": True, "commissionPct": 50, "hours": None}
CORTE = {"id": "c1", "barbershopId": "s1", "name": "Corte", "price": 4000, "durationMin": 45, "active": True}


def R(h, m=0, **kw):
    base = dict(barbershop_id="s1", barber_id="b1", service_id="c1", starts_at=at(h, m), client_phone="62999990000",
                client_name="Ana", consent=True)
    return BookingRequest(**{**base, **kw})


def ctx(**kw):
    base = dict(shop=SHOP, barber=ZE, service=CORTE)
    return BookingContext(**{**base, **kw})


def appt(h, m=0, dur=45, status="scheduled", id="a1", **kw):
    s = at(h, m)
    return {"id": id, "barbershopId": "s1", "barberId": "b1", "startsAt": s, "endsAt": s + timedelta(minutes=dur),
            "status": status, "clientPhone": "+5562999990000", **kw}


def test_snapshots_e_cliente_novo():
    p = plan_booking(R(10), ctx(), now=NOW)
    a = p.appointment
    assert (a["barberName"], a["serviceName"], a["price"], a["commissionPct"]) == ("Zé", "Corte", 4000, 50)
    assert a["endsAt"] - a["startsAt"] == timedelta(minutes=45) and a["status"] == "scheduled"
    assert p.client_id == "s1_+5562999990000" and p.client_create["consentAt"] == NOW
    assert p.lock_keys == ["b1_2026-11-16"]


def test_consentimento():
    with pytest.raises(InvalidRequest):
        plan_booking(R(10, consent=False), ctx(), now=NOW)
    assert plan_booking(R(10, consent=False, source="panel"), ctx(), now=NOW)  # balcão não exige


def test_cliente_existente_sem_consentimento_ganha_consentAt():
    p = plan_booking(R(10), ctx(client={"phone": "+5562999990000"}), now=NOW)
    assert p.client_create is None and p.client_update == {"consentAt": NOW}


@pytest.mark.parametrize("field,value", [("barber", {**ZE, "barbershopId": "outra"}), ("barber", {**ZE, "active": False}),
                                         ("service", {**CORTE, "barbershopId": "outra"}), ("service", {**CORTE, "active": False}),
                                         ("shop", None)])
def test_tenant_e_inativos_viram_404(field, value):
    with pytest.raises(NotFound):
        plan_booking(R(10), ctx(**{field: value}), now=NOW)


@pytest.mark.parametrize("h,m", [(8, 30), (19, 30), (10, 10)])  # antes de abrir, não cabe até 20h, fora da grade
def test_fora_da_janela_ou_grade(h, m):
    with pytest.raises(SlotUnavailable):
        plan_booking(R(h, m), ctx(), now=NOW)


def test_passado():
    with pytest.raises(SlotUnavailable):
        plan_booking(R(10), ctx(), now=at(10, 30))


@pytest.mark.parametrize("status,ok", [("scheduled", False), ("completed", False), ("canceled", True), ("no_show", True)])
def test_status_que_ocupam(status, ok):
    c = ctx(appointments=[appt(10, status=status)])
    if ok:
        plan_booking(R(10), c, now=NOW)
    else:
        with pytest.raises(SlotUnavailable):
            plan_booking(R(10), c, now=NOW)


def test_duracao_real_contra_grade():
    c = ctx(appointments=[appt(10)])  # 10:00–10:45
    with pytest.raises(SlotUnavailable):
        plan_booking(R(10, 30), c, now=NOW)
    plan_booking(R(11), c, now=NOW)


def test_bloqueio_ocupa():
    blk = {"start": at(14), "end": at(16)}
    with pytest.raises(SlotUnavailable):
        plan_booking(R(15), ctx(blocks=[blk]), now=NOW)
    plan_booking(R(16), ctx(blocks=[blk]), now=NOW)


def test_horario_proprio_do_barbeiro_sobrepoe_o_da_casa():
    so_tarde = {**ZE, "hours": {**{str(d): [{"opens": "14:00", "closes": "20:00"}] for d in range(7)}}}
    with pytest.raises(SlotUnavailable):
        plan_booking(R(10), ctx(barber=so_tarde), now=NOW)
    plan_booking(R(14), ctx(barber=so_tarde), now=NOW)


def test_remarcacao_ignora_o_proprio_horario_e_cancela_o_antigo():
    old = appt(10, id="old")
    p = plan_booking(R(10, 30, replace_appointment_id="old"), ctx(appointments=[old], old=old), now=NOW)
    assert p.appointment["rescheduledFrom"] == "old"
    assert p.old_update["status"] == "canceled" and p.old_update["cancelReason"] == "remarcado"


def test_remarcacao_para_outro_dia_trava_os_dois_dias():
    old = appt(10, id="old")
    p = plan_booking(R(10, replace_appointment_id="old", starts_at=at(10, d=DAY + timedelta(days=1))), ctx(old=old), now=NOW)
    assert p.lock_keys == ["b1_2026-11-17", "b1_2026-11-16"]


@pytest.mark.parametrize("old,err", [(None, NotFound), ({"barbershopId": "outra"}, NotFound),
                                     ({"status": "completed"}, InvalidRequest), ({"clientPhone": "+5562988887777"}, InvalidRequest)])
def test_remarcacao_invalida(old, err):
    o = None if old is None else {**appt(10, id="old"), **old}
    with pytest.raises(err):
        plan_booking(R(11, replace_appointment_id="old"), ctx(old=o), now=NOW)


def test_nome_vazio_e_telefone_invalido():
    with pytest.raises(InvalidRequest):
        plan_booking(R(10, client_name="  "), ctx(), now=NOW)
    with pytest.raises(InvalidRequest):
        plan_booking(R(10, client_phone="123"), ctx(), now=NOW)
