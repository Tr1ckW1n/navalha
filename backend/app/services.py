"""Casos de uso que combinam repositório + domínio (usados pelas rotas)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.availability import free_slots
from app.domain.booking import BookingRequest, busy_from, day_bounds, local_day, opening_hours_for
from app.domain.errors import Busy, InvalidRequest, NotFound, SlotUnavailable
from app.repo.base import Repository


def active_service(repo: Repository, shop_id: str, service_id: str) -> dict:
    s = repo.get("services", shop_id, service_id)
    if not s or not s.get("active", True):
        raise NotFound("serviço")
    return s


def barbers_in_scope(repo: Repository, shop_id: str, barber_id: str) -> list[dict]:
    """barber_id = id específico ou "any" (todos os ativos)."""
    if barber_id == "any":
        return repo.list("barbers", shop_id, active_only=True)
    b = repo.get("barbers", shop_id, barber_id)
    if not b or not b.get("active", True):
        raise NotFound("barbeiro")
    return [b]


def check_day(shop: dict, day: date, now: datetime, horizon_days: int) -> None:
    today = now.astimezone(ZoneInfo(shop["timezone"])).date()
    if day < today:
        raise InvalidRequest("data no passado")
    if day > today + timedelta(days=horizon_days):
        raise InvalidRequest(f"só é possível agendar até {horizon_days} dias à frente")


def availability(
    repo: Repository, shop: dict, service: dict, barbers: list[dict], day: date, *, now: datetime, step_min: int
) -> list[tuple[datetime, list[str]]]:
    """Horários livres do dia (UTC) com os barbeiros livres em cada um. Mesma regra da reserva."""
    tz = shop["timezone"]
    start, end = day_bounds(day, tz)
    by_slot: dict[datetime, list[str]] = {}
    for b in barbers:
        appts = repo.list_appointments(shop["id"], start=start, end=end, barber_id=b["id"])
        blocks = repo.list_blocks(shop["id"], b["id"], start, end)
        for s in free_slots(
            day=day, tz=tz, opening_hours=opening_hours_for(shop, b), existing=busy_from(appts, blocks),
            duration_min=int(service["durationMin"]), step_min=step_min, now=now,
        ):
            by_slot.setdefault(s, []).append(b["id"])
    return sorted(by_slot.items())


def book_any(
    repo: Repository, shop: dict, base: BookingRequest, *, now: datetime, step_min: int
) -> dict:
    """"Qualquer barbeiro" (RF04a): tenta, em ordem de menor carga no dia, os barbeiros livres
    naquele horário. Cada tentativa é uma reserva transacional; perder a corrida passa ao próximo."""
    service = active_service(repo, shop["id"], base.service_id)
    day = local_day(base.starts_at, shop["timezone"])
    slots = dict(availability(repo, shop, service, repo.list("barbers", shop["id"], active_only=True), day, now=now, step_min=step_min))
    candidates = slots.get(base.starts_at)
    if not candidates:
        raise SlotUnavailable("horário indisponível")
    start, end = day_bounds(day, shop["timezone"])
    load = {bid: sum(1 for a in repo.list_appointments(shop["id"], start=start, end=end, barber_id=bid) if a["status"] != "canceled")
            for bid in candidates}
    for bid in sorted(candidates, key=lambda b: (load[b], b)):
        try:
            return repo.book(_with_barber(base, bid), now=now, step_min=step_min)
        except (SlotUnavailable, Busy):
            continue
    raise SlotUnavailable("horário indisponível")


def _with_barber(req: BookingRequest, barber_id: str) -> BookingRequest:
    from dataclasses import replace

    return replace(req, barber_id=barber_id)
