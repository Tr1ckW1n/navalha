"""Schemas da API (spec v2.3 §9). JSON em camelCase, igual aos campos do Firestore.

Convenções: dinheiro em centavos (int); datas com fuso (UTC na saída); horários de
funcionamento como {"0": [{"opens": "09:00", "closes": "20:00"}], ...} com 0 = segunda.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.domain.booking import normalize_phone_br
from app.domain.errors import InvalidRequest
from app.domain.slugs import validate_slug

Status = Literal["scheduled", "completed", "no_show", "canceled"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


# ---------------- validadores compartilhados ----------------

def _hm(v: str) -> time:
    """Aceita "9:00" ou "09:00"."""
    h, m = str(v).strip().split(":")
    if not (h.isdigit() and m.isdigit() and len(m) == 2):
        raise ValueError(v)
    return time(int(h), int(m))


def normalize_hours(v: dict | None) -> dict[str, list[dict]] | None:
    """Valida e normaliza horários: chaves 0–6, janelas HH:MM ordenadas e sem sobreposição."""
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ValueError("horário deve ser um objeto {dia: [janelas]}")
    out: dict[str, list[dict]] = {}
    for k, wins in v.items():
        try:
            wd = int(k)
        except (TypeError, ValueError):
            raise ValueError(f"dia inválido: {k!r} (use 0=segunda … 6=domingo)") from None
        if not 0 <= wd <= 6:
            raise ValueError(f"dia inválido: {k!r} (use 0=segunda … 6=domingo)")
        parsed = []
        for w in wins or []:
            try:
                o, c = _hm(w["opens"]), _hm(w["closes"])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"janela inválida no dia {wd}: use {{'opens':'09:00','closes':'20:00'}}") from None
            if c <= o:
                raise ValueError(f"no dia {wd}, o fechamento precisa ser depois da abertura")
            parsed.append((o, c))
        parsed.sort()
        for (_, c1), (o2, _) in zip(parsed, parsed[1:]):
            if o2 < c1:
                raise ValueError(f"no dia {wd}, as janelas se sobrepõem")
        out[str(wd)] = [{"opens": o.strftime("%H:%M"), "closes": c.strftime("%H:%M")} for o, c in parsed]
    for wd in range(7):
        out.setdefault(str(wd), [])
    return out


def _phone(v: str | None) -> str | None:
    if v is None:
        return None
    try:
        return normalize_phone_br(v)
    except InvalidRequest as e:
        raise ValueError(str(e)) from None


Name = Annotated[str, Field(min_length=1, max_length=80)]
Cents = Annotated[int, Field(ge=0, le=10_000_000)]
Duration = Annotated[int, Field(ge=5, le=480, multiple_of=5)]
Pct = Annotated[int, Field(ge=0, le=100)]


# ---------------- barbearia ----------------

class ShopSettings(CamelModel):
    cancel_min_hours: Annotated[int, Field(ge=0, le=72)] = 2
    inactive_days: Annotated[int, Field(ge=7, le=365)] = 45
    barber_sees_revenue: bool = True


class BarbershopCreate(CamelModel):
    name: Name
    slug: str
    timezone: str = "America/Sao_Paulo"
    address: str = ""
    cep: str = ""
    whatsapp: str | None = None
    opening_hours: dict
    settings: ShopSettings = ShopSettings()

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v):
        return _slug_or_value_error(v)
    @field_validator("opening_hours")
    @classmethod
    def check_opening_hours(cls, v):
        return normalize_hours(v)
    @field_validator("whatsapp")
    @classmethod
    def check_whatsapp(cls, v):
        return _phone(v)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"fuso inválido: {v}") from None
        return v


def _slug_or_value_error(v: str) -> str:
    try:
        return validate_slug(v)
    except InvalidRequest as e:
        raise ValueError(str(e)) from None


class BarbershopUpdate(CamelModel):
    """Slug e fuso não mudam depois de criados (quebrariam links e histórico)."""

    name: Name | None = None
    address: str | None = None
    cep: str | None = None
    whatsapp: str | None = None
    opening_hours: dict | None = None
    settings: ShopSettings | None = None

    @field_validator("opening_hours")
    @classmethod
    def check_opening_hours(cls, v):
        return normalize_hours(v)
    @field_validator("whatsapp")
    @classmethod
    def check_whatsapp(cls, v):
        return _phone(v)


class BarbershopOut(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")
    id: str
    name: str
    slug: str
    timezone: str
    address: str = ""
    cep: str = ""
    whatsapp: str | None = None
    opening_hours: dict
    settings: ShopSettings = ShopSettings()


class BarbershopPublic(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")
    id: str  # não é segredo: as rotas /admin exigem chave
    name: str
    slug: str
    timezone: str
    address: str = ""
    cep: str = ""
    whatsapp: str | None = None
    opening_hours: dict
    cancel_min_hours: int = 2


# ---------------- barbeiros ----------------

class BarberCreate(CamelModel):
    name: Name
    active: bool = True
    commission_pct: Pct = 50
    hours: dict | None = None  # None = usa o horário da casa
    uid: str | None = None  # usuário do Firebase Auth (Fase 3)

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v):
        return normalize_hours(v)


class BarberUpdate(CamelModel):
    name: Name | None = None
    active: bool | None = None
    commission_pct: Pct | None = None
    hours: dict | None = None
    use_shop_hours: bool | None = None  # true limpa `hours`
    uid: str | None = None

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v):
        return normalize_hours(v)


class BarberOut(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")
    id: str
    name: str
    active: bool
    commission_pct: int = 0
    hours: dict | None = None


class BarberPublic(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")
    id: str
    name: str


# ---------------- serviços ----------------

class ServiceCreate(CamelModel):
    name: Name
    price: Cents
    duration_min: Duration
    active: bool = True


class ServiceUpdate(CamelModel):
    name: Name | None = None
    price: Cents | None = None
    duration_min: Duration | None = None
    active: bool | None = None


class ServiceOut(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")
    id: str
    name: str
    price: int
    duration_min: int
    active: bool = True


class ServicePublic(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")
    id: str
    name: str
    price: int
    duration_min: int


# ---------------- bloqueios ----------------

class BlockCreate(CamelModel):
    barber_id: str
    start: AwareDatetime
    end: AwareDatetime
    reason: Annotated[str, Field(max_length=120)] = ""

    @model_validator(mode="after")
    def _order(self):
        if self.end <= self.start:
            raise ValueError("o fim do bloqueio precisa ser depois do início")
        return self


class BlockOut(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")
    id: str
    barber_id: str
    start: datetime
    end: datetime
    reason: str = ""


# ---------------- disponibilidade e agendamento ----------------

class Slot(CamelModel):
    starts_at: datetime  # UTC
    local_time: str  # "HH:MM" no fuso da barbearia
    barber_ids: list[str]


class AvailabilityOut(CamelModel):
    date: date
    timezone: str
    service_id: str
    duration_min: int
    barber_id: str  # id ou "any"
    slots: list[Slot]


class BookingIn(CamelModel):
    service_id: str
    barber_id: str  # id do barbeiro ou "any"
    starts_at: AwareDatetime
    client_name: Name
    client_phone: str
    consent: bool = False

    @field_validator("client_phone")
    @classmethod
    def check_client_phone(cls, v):
        return _phone(v)


class AppointmentOut(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")
    id: str
    barber_id: str
    barber_name: str
    service_id: str
    service_name: str
    price: int
    starts_at: datetime
    ends_at: datetime
    status: Status
    client_name: str
    source: str = "public"


class StatusIn(CamelModel):
    status: Literal["completed", "no_show", "canceled"]


class AppointmentAdminOut(AppointmentOut):
    client_phone: str
    commission_pct: int = 0
    cancel_reason: str | None = None
    rescheduled_from: str | None = None
    rescheduled_to: str | None = None
