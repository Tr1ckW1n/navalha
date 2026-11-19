"""Rotas de administração (cadastros) — Fase 1.

PROVISÓRIO: protegidas por X-Admin-Key (deps.require_admin), com o shop_id no caminho.
Na Fase 3 passam para o painel com token Firebase, e o shop_id vem das claims (invariante 1).
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_now, get_repo, require_admin
from app.domain.booking import BookingRequest, day_bounds
from app.domain.errors import InvalidRequest, NotFound
from app.models import (
    AppointmentAdminOut,
    BarberCreate,
    BarberOut,
    BarbershopCreate,
    BarbershopOut,
    BarbershopUpdate,
    BarberUpdate,
    BlockCreate,
    BlockOut,
    BookingIn,
    ServiceCreate,
    ServiceOut,
    ServiceUpdate,
    StatusIn,
)
from app.repo.base import Repository
from app.config import get_settings
from app import services as uc

router = APIRouter(prefix="/admin", tags=["admin (provisório)"], dependencies=[Depends(require_admin)])


def _dump(model) -> dict:
    return model.model_dump(by_alias=True, exclude_unset=True)


def shop_or_404(shop_id: str, repo: Repository = Depends(get_repo)) -> dict:
    shop = repo.get_shop(shop_id)
    if not shop:
        raise NotFound("barbearia")
    return shop


# ---------------- barbearias ----------------

@router.post("/shops", response_model=BarbershopOut, status_code=status.HTTP_201_CREATED)
def create_shop(body: BarbershopCreate, repo: Repository = Depends(get_repo)):
    return repo.create_shop(body.model_dump(by_alias=True))


@router.get("/shops/{shop_id}", response_model=BarbershopOut)
def get_shop(shop: dict = Depends(shop_or_404)):
    return shop


@router.patch("/shops/{shop_id}", response_model=BarbershopOut)
def update_shop(body: BarbershopUpdate, shop: dict = Depends(shop_or_404), repo: Repository = Depends(get_repo)):
    return repo.update_shop(shop["id"], _dump(body))


# ---------------- barbeiros ----------------

@router.get("/shops/{shop_id}/barbers", response_model=list[BarberOut])
def list_barbers(shop: dict = Depends(shop_or_404), repo: Repository = Depends(get_repo)):
    return repo.list("barbers", shop["id"])


@router.post("/shops/{shop_id}/barbers", response_model=BarberOut, status_code=status.HTTP_201_CREATED)
def create_barber(body: BarberCreate, shop: dict = Depends(shop_or_404), repo: Repository = Depends(get_repo)):
    return repo.create("barbers", shop["id"], body.model_dump(by_alias=True))


@router.patch("/shops/{shop_id}/barbers/{barber_id}", response_model=BarberOut)
def update_barber(barber_id: str, body: BarberUpdate, shop: dict = Depends(shop_or_404), repo: Repository = Depends(get_repo)):
    data = _dump(body)
    if data.pop("useShopHours", None):
        if "hours" in data:
            raise InvalidRequest("envie 'hours' OU 'useShopHours', não os dois")
        data["hours"] = None
    return repo.update("barbers", shop["id"], barber_id, data)


# ---------------- serviços ----------------

@router.get("/shops/{shop_id}/services", response_model=list[ServiceOut])
def list_services(shop: dict = Depends(shop_or_404), repo: Repository = Depends(get_repo)):
    return repo.list("services", shop["id"])


@router.post("/shops/{shop_id}/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(body: ServiceCreate, shop: dict = Depends(shop_or_404), repo: Repository = Depends(get_repo)):
    return repo.create("services", shop["id"], body.model_dump(by_alias=True))


@router.patch("/shops/{shop_id}/services/{service_id}", response_model=ServiceOut)
def update_service(service_id: str, body: ServiceUpdate, shop: dict = Depends(shop_or_404), repo: Repository = Depends(get_repo)):
    return repo.update("services", shop["id"], service_id, _dump(body))


# ---------------- bloqueios ----------------

@router.get("/shops/{shop_id}/blocks", response_model=list[BlockOut])
def list_blocks(
    barber_id: str = Query(alias="barberId"),
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
    shop: dict = Depends(shop_or_404),
    repo: Repository = Depends(get_repo),
):
    if start.tzinfo is None or end.tzinfo is None:
        raise InvalidRequest("from/to precisam de fuso (ex.: 2026-11-16T00:00:00-03:00)")
    return repo.list_blocks(shop["id"], barber_id, start, end)


@router.post("/shops/{shop_id}/blocks", response_model=BlockOut, status_code=status.HTTP_201_CREATED)
def create_block(body: BlockCreate, shop: dict = Depends(shop_or_404), repo: Repository = Depends(get_repo)):
    if not repo.get("barbers", shop["id"], body.barber_id):
        raise NotFound("barbeiro")
    return repo.create("blocks", shop["id"], {**body.model_dump(by_alias=True), "createdAt": datetime.now().astimezone()})


@router.delete("/shops/{shop_id}/blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_block(block_id: str, shop: dict = Depends(shop_or_404), repo: Repository = Depends(get_repo)):
    repo.delete("blocks", shop["id"], block_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- agenda (consulta e encaixe) ----------------

@router.get("/shops/{shop_id}/appointments", response_model=list[AppointmentAdminOut])
def list_appointments(
    day: date = Query(alias="date"),
    barber_id: str | None = Query(default=None, alias="barberId"),
    shop: dict = Depends(shop_or_404),
    repo: Repository = Depends(get_repo),
):
    start, end = day_bounds(day, shop["timezone"])
    return repo.list_appointments(shop["id"], start=start, end=end, barber_id=barber_id)


@router.patch("/shops/{shop_id}/appointments/{appointment_id}", response_model=AppointmentAdminOut)
def set_status(
    appointment_id: str, body: StatusIn, shop: dict = Depends(shop_or_404),
    repo: Repository = Depends(get_repo), now: datetime = Depends(get_now),
):
    """Concluído, não veio ou cancelado (RF07). Cancelar libera o horário na hora."""
    return repo.set_appointment_status(shop["id"], appointment_id, body.status, now=now)


@router.post("/shops/{shop_id}/appointments", response_model=AppointmentAdminOut, status_code=status.HTTP_201_CREATED)
def create_manual_appointment(
    body: BookingIn,
    shop: dict = Depends(shop_or_404),
    repo: Repository = Depends(get_repo),
    now: datetime = Depends(get_now),
):
    """Encaixe pelo balcão (RF08): mesma transação e mesma regra do link público, sem exigir consentimento."""
    s = get_settings()
    req = BookingRequest(
        barbershop_id=shop["id"], barber_id=body.barber_id, service_id=body.service_id, starts_at=body.starts_at,
        client_phone=body.client_phone, client_name=body.client_name, source="panel", consent=body.consent,
    )
    if body.barber_id == "any":
        return uc.book_any(repo, shop, req, now=now, step_min=s.slot_step_minutes)
    return repo.book(req, now=now, step_min=s.slot_step_minutes)
