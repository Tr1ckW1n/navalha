"""Regras de reserva — puras, sem I/O (spec v2.3 §7.1; CLAUDE.md invariantes 2–6, 10).

Fluxo: o repositório abre uma transação, lê o necessário (`BookingContext`), chama
`plan_booking` e grava exatamente o `BookingPlan` devolvido. Assim a regra existe em um
só lugar e é testada sem banco; o adaptador do Firestore só cuida de ler/gravar.

Concorrência: toda reserva escreve os documentos-trava de `plan.lock_keys`
(`barberDayLocks/{barberId}_{AAAA-MM-DD}`). Duas reservas concorrentes no mesmo barbeiro/dia
disputam o mesmo documento e o Firestore serializa: uma refaz a transação e enxerga a outra.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.availability import Busy, OpeningHours, Window, is_bookable
from app.domain.errors import InvalidRequest, NotFound, SlotUnavailable

# compatibilidade com código/testes anteriores
BookingError = InvalidRequest

_PHONE_DIGITS = re.compile(r"\D+")


def normalize_phone_br(raw: str) -> str:
    """Normaliza para E.164 (+55DDDNÚMERO). Aceita com/sem +55, máscara, espaços."""
    digits = _PHONE_DIGITS.sub("", raw or "")
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) not in (10, 11):
        raise InvalidRequest(f"telefone inválido: {raw!r}")
    return f"+55{digits}"


def client_id(barbershop_id: str, phone_e164: str) -> str:
    """Invariante 2: id de cliente escopado ao tenant."""
    return f"{barbershop_id}_{phone_e164}"


def parse_opening_hours(raw: dict | None) -> OpeningHours:
    """Firestore: {"0": [{"opens": "09:00", "closes": "20:00"}], ...} -> OpeningHours."""
    return {
        int(wd): [Window(time.fromisoformat(w["opens"]), time.fromisoformat(w["closes"])) for w in ws]
        for wd, ws in (raw or {}).items()
    }


def opening_hours_for(shop: dict, barber: dict) -> OpeningHours:
    """Janela = horário próprio do barbeiro, senão o da casa."""
    return parse_opening_hours(barber.get("hours") or shop.get("openingHours"))


def local_day(dt: datetime, tz: str) -> date:
    return dt.astimezone(ZoneInfo(tz)).date()


def day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    """[início, fim) do dia local em UTC."""
    zone = ZoneInfo(tz)
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def lock_key(barber_id: str, day: date) -> str:
    return f"{barber_id}_{day.isoformat()}"


def busy_from(appointments: list[dict], blocks: list[dict], ignore_id: str | None = None) -> list[Busy]:
    """Agendamentos (com status) + bloqueios (sempre ocupam) -> lista de ocupados."""
    out = [Busy(a["startsAt"], a["endsAt"], a["status"]) for a in appointments if a.get("id") != ignore_id]
    out += [Busy(b["start"], b["end"], "scheduled") for b in blocks]
    return out


@dataclass(frozen=True)
class BookingRequest:
    barbershop_id: str
    barber_id: str
    service_id: str
    starts_at: datetime  # tz-aware
    client_phone: str  # bruto; será normalizado
    client_name: str
    source: str = "public"  # "public" | "panel"
    consent: bool = False  # LGPD: obrigatório em reserva pública que não é remarcação
    replace_appointment_id: str | None = None  # remarcação atômica


@dataclass
class BookingContext:
    """Tudo que a regra precisa, lido DENTRO da transação."""

    shop: dict | None
    barber: dict | None
    service: dict | None
    appointments: list[dict] = field(default_factory=list)  # do barbeiro, no dia local do novo horário
    blocks: list[dict] = field(default_factory=list)  # do barbeiro, que tocam esse dia
    client: dict | None = None
    old: dict | None = None  # agendamento a remarcar (com "id")


@dataclass
class BookingPlan:
    """O que o repositório deve gravar, na mesma transação."""

    appointment: dict
    client_id: str
    client_create: dict | None
    client_update: dict | None
    old_update: dict | None
    lock_keys: list[str]


def required_lock_keys(req: BookingRequest, tz: str, old: dict | None) -> list[str]:
    keys = [lock_key(req.barber_id, local_day(req.starts_at, tz))]
    if old is not None:
        k = lock_key(old["barberId"], local_day(old["startsAt"], tz))
        if k not in keys:
            keys.append(k)
    return keys


STAFF_TRANSITIONS = {"scheduled": {"completed", "no_show", "canceled"}}


def plan_status_change(appt: dict | None, shop_id: str, new_status: str, *, now: datetime) -> dict:
    """Mudança de status pela equipe (RF07). Só sai de `scheduled`; voltar exige novo agendamento
    (reabrir um horário já liberado poderia sobrepor outra reserva)."""
    if not appt or appt.get("barbershopId") != shop_id:
        raise NotFound("agendamento")
    allowed = STAFF_TRANSITIONS.get(appt.get("status"), set())
    if new_status not in allowed:
        raise InvalidRequest(f"não é possível mudar de {appt.get('status')} para {new_status}")
    upd = {"status": new_status, "updatedAt": now}
    if new_status == "canceled":
        upd["cancelReason"] = "cancelado pela barbearia"
    return upd


def plan_booking(req: BookingRequest, ctx: BookingContext, *, now: datetime, step_min: int = 30) -> BookingPlan:
    """Valida a reserva contra o contexto e devolve o plano de escrita. Levanta erro de domínio."""
    if req.starts_at.tzinfo is None or now.tzinfo is None:
        raise InvalidRequest("datas precisam ter fuso (tz-aware)")
    is_resched = req.replace_appointment_id is not None
    if req.source == "public" and not is_resched and not req.consent:
        raise InvalidRequest("consentimento obrigatório (LGPD)")
    phone = normalize_phone_br(req.client_phone)
    name = (req.client_name or "").strip()
    if not name:
        raise InvalidRequest("nome obrigatório")

    shop, barber, service = ctx.shop, ctx.barber, ctx.service
    if not shop:
        raise NotFound("barbearia")
    sid = req.barbershop_id
    if not barber or barber.get("barbershopId") != sid or not barber.get("active", True):
        raise NotFound("barbeiro")
    if not service or service.get("barbershopId") != sid or not service.get("active", True):
        raise NotFound("serviço")

    old = ctx.old
    if is_resched:
        if not old or old.get("barbershopId") != sid:
            raise NotFound("agendamento a remarcar")
        if old.get("status") != "scheduled":
            raise InvalidRequest("só é possível remarcar agendamento com status scheduled")
        if old.get("clientPhone") != phone:
            raise InvalidRequest("telefone não confere com o agendamento original")

    tz = shop["timezone"]
    duration = int(service["durationMin"])
    existing = busy_from(ctx.appointments, ctx.blocks, ignore_id=req.replace_appointment_id)
    if not is_bookable(
        start=req.starts_at,
        tz=tz,
        opening_hours=opening_hours_for(shop, barber),
        existing=existing,
        duration_min=duration,
        step_min=step_min,
        now=now,
    ):
        raise SlotUnavailable("horário indisponível")

    starts = req.starts_at.astimezone(UTC)
    appointment = {
        "barbershopId": sid,
        "barberId": req.barber_id,
        "barberName": barber["name"],  # snapshot
        "serviceId": req.service_id,
        "serviceName": service["name"],  # snapshot
        "price": int(service["price"]),  # snapshot, centavos
        "commissionPct": int(barber.get("commissionPct", 0)),  # snapshot
        "clientPhone": phone,
        "clientName": name,
        "startsAt": starts,
        "endsAt": starts + timedelta(minutes=duration),
        "status": "scheduled",
        "source": req.source,
        "reminder": None,
        "createdAt": now,
        "updatedAt": now,
    }
    if is_resched:
        appointment["rescheduledFrom"] = req.replace_appointment_id

    cid = client_id(sid, phone)
    client_create = client_update = None
    if ctx.client is None:
        client_create = {"barbershopId": sid, "phone": phone, "name": name, "notes": "", "createdAt": now}
        if req.consent:
            client_create["consentAt"] = now
    elif req.consent and not ctx.client.get("consentAt"):
        client_update = {"consentAt": now}

    old_update = None
    if is_resched:
        # "rescheduledTo" é preenchido pelo repositório, que conhece o id gerado do novo documento
        old_update = {"status": "canceled", "cancelReason": "remarcado", "updatedAt": now}

    return BookingPlan(
        appointment=appointment,
        client_id=cid,
        client_create=client_create,
        client_update=client_update,
        old_update=old_update,
        lock_keys=required_lock_keys(req, tz, old if is_resched else None),
    )
