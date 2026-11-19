"""Rotas públicas do link de agendamento (navalha.app/{slug}). Sem login (RF01–RF04a)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, status

from app.config import get_settings
from app.deps import get_now, get_repo
from app.domain.booking import BookingRequest
from app.domain.errors import NotFound
from app.models import (
    AppointmentOut,
    AvailabilityOut,
    BarbershopPublic,
    BarberPublic,
    BookingIn,
    ServicePublic,
    Slot,
)
from app.repo.base import Repository
from app import services as uc

router = APIRouter(prefix="/public", tags=["público"])


def shop_by_slug(slug: str, repo: Repository = Depends(get_repo)) -> dict:
    shop = repo.get_shop_by_slug(slug.lower())
    if not shop:
        raise NotFound("barbearia")
    return shop


@router.get("/{slug}")
def shop_page(shop: dict = Depends(shop_by_slug), repo: Repository = Depends(get_repo)) -> dict:
    """Dados da página pública: barbearia, barbeiros e serviços ativos (sem comissão nem dados internos)."""
    return {
        "shop": BarbershopPublic.model_validate({**shop, "cancelMinHours": shop.get("settings", {}).get("cancelMinHours", 2)}).model_dump(by_alias=True),
        "barbers": [BarberPublic.model_validate(b).model_dump(by_alias=True) for b in repo.list("barbers", shop["id"], active_only=True)],
        "services": [ServicePublic.model_validate(s).model_dump(by_alias=True) for s in repo.list("services", shop["id"], active_only=True)],
    }


@router.get("/{slug}/availability", response_model=AvailabilityOut)
def get_availability(
    service_id: str = Query(alias="serviceId"),
    day: date = Query(alias="date"),
    barber_id: str = Query(default="any", alias="barberId"),
    shop: dict = Depends(shop_by_slug),
    repo: Repository = Depends(get_repo),
    now: datetime = Depends(get_now),
):
    s = get_settings()
    uc.check_day(shop, day, now, s.booking_horizon_days)
    service = uc.active_service(repo, shop["id"], service_id)
    barbers = uc.barbers_in_scope(repo, shop["id"], barber_id)
    zone = ZoneInfo(shop["timezone"])
    slots = uc.availability(repo, shop, service, barbers, day, now=now, step_min=s.slot_step_minutes)
    return AvailabilityOut(
        date=day, timezone=shop["timezone"], service_id=service_id, duration_min=service["durationMin"], barber_id=barber_id,
        slots=[Slot(starts_at=t, local_time=t.astimezone(zone).strftime("%H:%M"), barber_ids=bids) for t, bids in slots],
    )


@router.post("/{slug}/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    body: BookingIn,
    shop: dict = Depends(shop_by_slug),
    repo: Repository = Depends(get_repo),
    now: datetime = Depends(get_now),
):
    s = get_settings()
    starts = body.starts_at.astimezone(UTC)
    uc.check_day(shop, starts.astimezone(ZoneInfo(shop["timezone"])).date(), now, s.booking_horizon_days)
    req = BookingRequest(
        barbershop_id=shop["id"], barber_id=body.barber_id, service_id=body.service_id, starts_at=starts,
        client_phone=body.client_phone, client_name=body.client_name, source="public", consent=body.consent,
    )
    if body.barber_id == "any":
        return uc.book_any(repo, shop, req, now=now, step_min=s.slot_step_minutes)
    return repo.book(req, now=now, step_min=s.slot_step_minutes)
