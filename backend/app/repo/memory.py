"""Repositório em memória — para testes e desenvolvimento sem emulador.

Uma trava global torna cada `book` serializável, o que equivale à garantia que a
transação + documento-trava dão no Firestore. A regra em si vem de plan_booking.
"""

from __future__ import annotations

import copy
import threading
import uuid
from collections import defaultdict
from datetime import datetime

from app.domain.booking import (
    BookingContext,
    BookingRequest,
    client_id,
    day_bounds,
    local_day,
    normalize_phone_br,
    plan_booking,
    plan_status_change,
)
from app.domain.errors import Conflict, NotFound
from app.repo.base import Repository, check_collection


def _new_id() -> str:
    return uuid.uuid4().hex[:20]


class InMemoryRepository(Repository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db: dict[str, dict[str, dict]] = defaultdict(dict)

    # ---------- utilitários ----------
    def _out(self, col: str, doc_id: str) -> dict | None:
        d = self._db[col].get(doc_id)
        return None if d is None else {**copy.deepcopy(d), "id": doc_id}

    # ---------- barbearias ----------
    def get_shop(self, shop_id):
        with self._lock:
            return self._out("barbershops", shop_id)

    def get_shop_by_slug(self, slug):
        with self._lock:
            ref = self._db["slugs"].get(slug)
            return self._out("barbershops", ref["barbershopId"]) if ref else None

    def create_shop(self, data):
        with self._lock:
            if data["slug"] in self._db["slugs"]:
                raise Conflict(f"slug já usado: {data['slug']}")
            sid = _new_id()
            self._db["barbershops"][sid] = copy.deepcopy(data)
            self._db["slugs"][data["slug"]] = {"barbershopId": sid}
            return self._out("barbershops", sid)

    def update_shop(self, shop_id, data):
        with self._lock:
            if shop_id not in self._db["barbershops"]:
                raise NotFound("barbearia")
            self._db["barbershops"][shop_id].update(copy.deepcopy(data))
            return self._out("barbershops", shop_id)

    # ---------- coleções do tenant ----------
    def list(self, col, shop_id, *, active_only=False):
        check_collection(col)
        with self._lock:
            return [
                self._out(col, i) for i, d in self._db[col].items()
                if d.get("barbershopId") == shop_id and (not active_only or d.get("active", True))
            ]

    def get(self, col, shop_id, doc_id):
        check_collection(col)
        with self._lock:
            d = self._db[col].get(doc_id)
            return self._out(col, doc_id) if d and d.get("barbershopId") == shop_id else None

    def create(self, col, shop_id, data):
        check_collection(col)
        with self._lock:
            i = _new_id()
            self._db[col][i] = {**copy.deepcopy(data), "barbershopId": shop_id}
            return self._out(col, i)

    def update(self, col, shop_id, doc_id, data):
        with self._lock:
            if self.get(col, shop_id, doc_id) is None:
                raise NotFound(col)
            self._db[col][doc_id].update(copy.deepcopy(data))
            return self._out(col, doc_id)

    def delete(self, col, shop_id, doc_id):
        with self._lock:
            if self.get(col, shop_id, doc_id) is None:
                raise NotFound(col)
            del self._db[col][doc_id]

    # ---------- consultas ----------
    def list_blocks(self, shop_id, barber_id, start, end):
        with self._lock:
            return [
                self._out("blocks", i) for i, d in self._db["blocks"].items()
                if d["barbershopId"] == shop_id and d["barberId"] == barber_id and d["start"] < end and d["end"] > start
            ]

    def list_appointments(self, shop_id, *, start, end, barber_id=None):
        with self._lock:
            out = [
                self._out("appointments", i) for i, d in self._db["appointments"].items()
                if d["barbershopId"] == shop_id and start <= d["startsAt"] < end
                and (barber_id is None or d["barberId"] == barber_id)
            ]
            return sorted(out, key=lambda a: a["startsAt"])

    def get_client(self, shop_id, phone_e164):
        with self._lock:
            return self._out("clients", client_id(shop_id, phone_e164))

    def set_appointment_status(self, shop_id, appointment_id, status, *, now):
        with self._lock:
            upd = plan_status_change(self._out("appointments", appointment_id), shop_id, status, now=now)
            self._db["appointments"][appointment_id].update(upd)
            return self._out("appointments", appointment_id)

    # ---------- reserva ----------
    def book(self, req: BookingRequest, *, now: datetime, step_min: int = 30) -> dict:
        with self._lock:
            sid = req.barbershop_id
            shop = self._out("barbershops", sid)
            barber = self._out("barbers", req.barber_id)
            service = self._out("services", req.service_id)
            old = self._out("appointments", req.replace_appointment_id) if req.replace_appointment_id else None
            appts, blocks, client = [], [], None
            if shop:
                tz = shop["timezone"]
                start, end = day_bounds(local_day(req.starts_at, tz), tz)
                appts = self.list_appointments(sid, start=start, end=end, barber_id=req.barber_id)
                blocks = self.list_blocks(sid, req.barber_id, start, end)
                client = self.get_client(sid, normalize_phone_br(req.client_phone))
            plan = plan_booking(
                req, BookingContext(shop, barber, service, appts, blocks, client, old), now=now, step_min=step_min
            )
            new_id = _new_id()
            self._db["appointments"][new_id] = plan.appointment
            if plan.old_update is not None:
                self._db["appointments"][req.replace_appointment_id].update({**plan.old_update, "rescheduledTo": new_id})
            if plan.client_create is not None:
                self._db["clients"][plan.client_id] = plan.client_create
            if plan.client_update is not None:
                self._db["clients"][plan.client_id].update(plan.client_update)
            for k in plan.lock_keys:
                lk = self._db["barberDayLocks"].setdefault(k, {"barbershopId": sid, "version": 0})
                lk["version"] += 1
            return self._out("appointments", new_id)
