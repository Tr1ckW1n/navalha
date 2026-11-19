"""Fixtures compartilhadas. Relógio fixo: segunda 16/11/2026, 08:00 em São Paulo.

A fixture `repo` é parametrizada: sempre roda com o repositório em memória e, quando
FIRESTORE_EMULATOR_HOST está definido, roda a MESMA suíte contra o Firestore (emulador).
"""

import os
import uuid
from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.domain.booking import BookingRequest
from app.repo.memory import InMemoryRepository

TZ = "America/Sao_Paulo"
SP = ZoneInfo(TZ)
DAY = date(2026, 11, 16)  # segunda-feira
NOW = datetime(2026, 11, 16, 11, 0, tzinfo=UTC)  # 08:00 local
# horário real da Barbearia MF: seg–sáb 9h–20h
HOURS = {**{str(d): [{"opens": "09:00", "closes": "20:00"}] for d in range(6)}, "6": []}

EMULATOR = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))


def at(h: int, m: int = 0, d: date = DAY) -> datetime:
    return datetime.combine(d, time(h, m), tzinfo=SP)


def make_repo(kind: str):
    if kind == "memory":
        return InMemoryRepository()
    from google.cloud import firestore

    from app.repo.firestore_repo import FirestoreRepository

    return FirestoreRepository(firestore.Client(project="navalha-test"))


@pytest.fixture(params=["memory", pytest.param("firestore", marks=pytest.mark.skipif(not EMULATOR, reason="emulador do Firestore não ativo"))])
def repo(request):
    return make_repo(request.param)


def seed_shop(repo, *, slug: str | None = None):
    s = repo.create_shop({
        "name": "Barbearia MF", "slug": slug or f"mf-{uuid.uuid4().hex[:8]}", "timezone": TZ,
        "address": "R. Maria Aparecida, Qd 142, Lt 7-A", "cep": "74843-180", "whatsapp": "+556294554348",
        "openingHours": HOURS, "settings": {"cancelMinHours": 2, "inactiveDays": 45, "barberSeesRevenue": True},
    })
    sid = s["id"]
    return SimpleNamespace(
        id=sid, shop=s,
        ze=repo.create("barbers", sid, {"name": "Zé", "active": True, "commissionPct": 50, "hours": None}),
        rafa=repo.create("barbers", sid, {"name": "Rafa", "active": True, "commissionPct": 40, "hours": None}),
        corte=repo.create("services", sid, {"name": "Corte", "price": 4000, "durationMin": 45, "active": True}),
        barba=repo.create("services", sid, {"name": "Barba", "price": 3000, "durationMin": 30, "active": True}),
    )


@pytest.fixture
def shop(repo):
    return seed_shop(repo)


def req(sh, h, m=0, *, barber=None, service=None, phone="62999990000", name="Cliente", consent=True, d=DAY, **kw):
    return BookingRequest(
        sh.id, (barber or sh.ze)["id"], (service or sh.corte)["id"], at(h, m, d), phone, name, consent=consent, **kw
    )
