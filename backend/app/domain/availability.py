"""Cálculo de disponibilidade — lógica pura, sem I/O (spec §7.1, invariantes 4, 5 e 8).

Convenções:
- Todo datetime que entra/sai daqui é tz-aware. Persistência é UTC; a grade de
  horários é montada no fuso local da barbearia e convertida para UTC.
- Dia da semana: 0 = segunda ... 6 = domingo (datetime.weekday()).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Invariante 5: só estes status ocupam horário.
BLOCKING_STATUSES: frozenset[str] = frozenset({"scheduled", "completed"})
ALL_STATUSES: frozenset[str] = frozenset({"scheduled", "completed", "no_show", "canceled"})


@dataclass(frozen=True)
class Window:
    """Janela de funcionamento em horário local, ex.: 09:00–12:00."""

    opens: time
    closes: time

    def __post_init__(self) -> None:
        if self.closes <= self.opens:
            raise ValueError(f"janela inválida: {self.opens}–{self.closes}")


# weekday -> janelas do dia (permite intervalo de almoço: duas janelas)
OpeningHours = dict[int, list[Window]]


@dataclass(frozen=True)
class Busy:
    """Agendamento existente do barbeiro (já lido do Firestore)."""

    starts_at: datetime
    ends_at: datetime
    status: str


def _require_aware(*dts: datetime) -> None:
    for dt in dts:
        if dt.tzinfo is None:
            raise ValueError("datetime naive não é permitido; use tz-aware (UTC)")


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Intervalos semiabertos [start, end): encostar (fim == início) não é conflito."""
    _require_aware(a_start, a_end, b_start, b_end)
    return a_start < b_end and a_end > b_start


def find_conflict(existing: list[Busy], start: datetime, end: datetime) -> Busy | None:
    """Primeiro agendamento que bloqueia [start, end), ou None."""
    for b in existing:
        if b.status in BLOCKING_STATUSES and overlaps(start, end, b.starts_at, b.ends_at):
            return b
    return None


def local_day_bounds_utc(day: date, tz: str) -> tuple[datetime, datetime]:
    """[início, fim) do dia local em UTC — é o range usado na query do Firestore."""
    zone = ZoneInfo(tz)
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def candidate_starts(
    day: date, tz: str, opening_hours: OpeningHours, duration_min: int, step_min: int
) -> list[datetime]:
    """Inícios possíveis (UTC) respeitando funcionamento: o serviço precisa CABER na janela."""
    if duration_min <= 0 or step_min <= 0:
        raise ValueError("duration_min e step_min devem ser positivos")
    zone = ZoneInfo(tz)
    duration = timedelta(minutes=duration_min)
    step = timedelta(minutes=step_min)
    out: list[datetime] = []
    for w in opening_hours.get(day.weekday(), []):
        cursor = datetime.combine(day, w.opens, tzinfo=zone)
        close = datetime.combine(day, w.closes, tzinfo=zone)
        while cursor + duration <= close:
            out.append(cursor.astimezone(UTC))
            cursor += step
    return out


def free_slots(
    *,
    day: date,
    tz: str,
    opening_hours: OpeningHours,
    existing: list[Busy],
    duration_min: int,
    step_min: int = 30,
    now: datetime | None = None,
) -> list[datetime]:
    """Horários livres (UTC) para um serviço de `duration_min` com um barbeiro no dia local.

    A grade usa `step_min`, mas o conflito é sempre checado contra a duração REAL.
    `now` (UTC) remove horários que já passaram.
    """
    if now is not None:
        _require_aware(now)
    duration = timedelta(minutes=duration_min)
    result = []
    for start in candidate_starts(day, tz, opening_hours, duration_min, step_min):
        if now is not None and start <= now:
            continue
        if find_conflict(existing, start, start + duration) is None:
            result.append(start)
    return result


def is_bookable(
    *,
    start: datetime,
    tz: str,
    opening_hours: OpeningHours,
    existing: list[Busy],
    duration_min: int,
    step_min: int = 30,
    now: datetime | None = None,
) -> bool:
    """Revalidação usada DENTRO da transação: o início pedido é um slot livre válido?"""
    _require_aware(start)
    day = start.astimezone(ZoneInfo(tz)).date()
    slots = free_slots(
        day=day,
        tz=tz,
        opening_hours=opening_hours,
        existing=existing,
        duration_min=duration_min,
        step_min=step_min,
        now=now,
    )
    return start.astimezone(UTC) in slots
