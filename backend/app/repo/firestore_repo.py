"""Repositório Firestore. Só lê e grava: a regra de reserva vem de domain.booking.plan_booking.

Consultas seguem a invariante 7 (tenant + range de data, + barbeiro); o resto é feito em memória.
Índices compostos necessários estão em firestore.indexes.json.
"""

from __future__ import annotations

from datetime import datetime

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.domain.booking import (
    BookingContext,
    BookingRequest,
    client_id,
    day_bounds,
    local_day,
    normalize_phone_br,
    plan_booking,
    plan_status_change,
    required_lock_keys,
)
from google.api_core import exceptions as gexc

from app.domain.errors import Busy, Conflict, NotFound
from app.repo.base import Repository, check_collection


def _doc(snap) -> dict | None:
    if not snap.exists:
        return None
    d = snap.to_dict()
    d["id"] = snap.id
    return d


def _eq(field: str, value) -> FieldFilter:
    return FieldFilter(field, "==", value)


MAX_ATTEMPTS = 10  # padrão do cliente é 5; reservas concorrentes no mesmo dia disputam o mesmo documento-trava


class FirestoreRepository(Repository):
    def __init__(self, db: firestore.Client) -> None:
        self.db = db

    def _col(self, name: str):
        return self.db.collection(name)

    # ---------- barbearias ----------
    def get_shop(self, shop_id):
        return _doc(self._col("barbershops").document(shop_id).get())

    def get_shop_by_slug(self, slug):
        ref = _doc(self._col("slugs").document(slug).get())
        return self.get_shop(ref["barbershopId"]) if ref else None

    def create_shop(self, data):
        slug_ref = self._col("slugs").document(data["slug"])
        shop_ref = self._col("barbershops").document()

        @firestore.transactional
        def _txn(t: firestore.Transaction):
            if slug_ref.get(transaction=t).exists:
                raise Conflict(f"slug já usado: {data['slug']}")
            t.set(shop_ref, data)
            t.set(slug_ref, {"barbershopId": shop_ref.id})

        _txn(self.db.transaction())
        return self.get_shop(shop_ref.id)

    def update_shop(self, shop_id, data):
        ref = self._col("barbershops").document(shop_id)
        if not ref.get().exists:
            raise NotFound("barbearia")
        ref.update(data)
        return self.get_shop(shop_id)

    # ---------- coleções do tenant ----------
    def list(self, col, shop_id, *, active_only=False):
        check_collection(col)
        q = self._col(col).where(filter=_eq("barbershopId", shop_id))
        if active_only:
            q = q.where(filter=_eq("active", True))
        return [_doc(s) for s in q.stream()]

    def get(self, col, shop_id, doc_id):
        check_collection(col)
        d = _doc(self._col(col).document(doc_id).get())
        return d if d and d.get("barbershopId") == shop_id else None

    def create(self, col, shop_id, data):
        check_collection(col)
        ref = self._col(col).document()
        ref.set({**data, "barbershopId": shop_id})
        return _doc(ref.get())

    def update(self, col, shop_id, doc_id, data):
        if self.get(col, shop_id, doc_id) is None:
            raise NotFound(col)
        self._col(col).document(doc_id).update(data)
        return self.get(col, shop_id, doc_id)

    def delete(self, col, shop_id, doc_id):
        if self.get(col, shop_id, doc_id) is None:
            raise NotFound(col)
        self._col(col).document(doc_id).delete()

    # ---------- consultas ----------
    def _blocks_query(self, shop_id, barber_id, end):
        # um só campo de range por query: filtra start < end aqui e end > start em memória
        return (
            self._col("blocks").where(filter=_eq("barbershopId", shop_id))
            .where(filter=_eq("barberId", barber_id)).where(filter=FieldFilter("start", "<", end))
        )

    def list_blocks(self, shop_id, barber_id, start, end):
        return [d for d in (_doc(s) for s in self._blocks_query(shop_id, barber_id, end).stream()) if d["end"] > start]

    def _appts_query(self, shop_id, start, end, barber_id=None):
        q = self._col("appointments").where(filter=_eq("barbershopId", shop_id))
        if barber_id is not None:
            q = q.where(filter=_eq("barberId", barber_id))
        return q.where(filter=FieldFilter("startsAt", ">=", start)).where(filter=FieldFilter("startsAt", "<", end))

    def list_appointments(self, shop_id, *, start, end, barber_id=None):
        out = [_doc(s) for s in self._appts_query(shop_id, start, end, barber_id).stream()]
        return sorted(out, key=lambda a: a["startsAt"])

    def get_client(self, shop_id, phone_e164):
        return _doc(self._col("clients").document(client_id(shop_id, phone_e164)).get())

    def set_appointment_status(self, shop_id, appointment_id, status, *, now):
        ref = self._col("appointments").document(appointment_id)

        @firestore.transactional
        def _txn(t: firestore.Transaction):
            upd = plan_status_change(_doc(ref.get(transaction=t)), shop_id, status, now=now)
            t.update(ref, upd)

        _txn(self.db.transaction())
        return _doc(ref.get())

    # ---------- reserva ----------
    def book(self, req: BookingRequest, *, now: datetime, step_min: int = 30) -> dict:
        sid = req.barbershop_id
        phone = normalize_phone_br(req.client_phone)
        appt_ref = self._col("appointments").document()
        old_ref = self._col("appointments").document(req.replace_appointment_id) if req.replace_appointment_id else None

        @firestore.transactional
        def _txn(t: firestore.Transaction) -> None:
            # --- leituras (todas antes de qualquer escrita) ---
            shop = _doc(self._col("barbershops").document(sid).get(transaction=t))
            barber = _doc(self._col("barbers").document(req.barber_id).get(transaction=t))
            service = _doc(self._col("services").document(req.service_id).get(transaction=t))
            old = _doc(old_ref.get(transaction=t)) if old_ref else None
            appts, blocks, client, locks = [], [], None, {}
            if shop:
                tz = shop["timezone"]
                start, end = day_bounds(local_day(req.starts_at, tz), tz)
                for k in required_lock_keys(req, tz, old if old and old.get("barbershopId") == sid else None):
                    ref = self._col("barberDayLocks").document(k)
                    locks[k] = (ref, ref.get(transaction=t))
                client = _doc(self._col("clients").document(client_id(sid, phone)).get(transaction=t))
                appts = [_doc(s) for s in self._appts_query(sid, start, end, req.barber_id).get(transaction=t)]
                blocks = [
                    d for d in (_doc(s) for s in self._blocks_query(sid, req.barber_id, end).get(transaction=t))
                    if d["end"] > start
                ]
            plan = plan_booking(
                req, BookingContext(shop, barber, service, appts, blocks, client, old), now=now, step_min=step_min
            )
            # --- escritas ---
            for k in plan.lock_keys:
                ref, snap = locks[k]
                version = ((snap.to_dict() or {}) if snap.exists else {}).get("version", 0)
                t.set(ref, {"barbershopId": sid, "version": version + 1, "updatedAt": now})
            t.set(appt_ref, plan.appointment)
            if plan.old_update is not None:
                t.update(old_ref, {**plan.old_update, "rescheduledTo": appt_ref.id})
            cref = self._col("clients").document(plan.client_id)
            if plan.client_create is not None:
                t.set(cref, plan.client_create)
            if plan.client_update is not None:
                t.update(cref, plan.client_update)

        try:
            _txn(self.db.transaction(max_attempts=MAX_ATTEMPTS))
        except gexc.Aborted as e:
            raise Busy("muita gente agendando este barbeiro agora; tente de novo") from e
        except ValueError as e:
            # o cliente Python sinaliza "Failed to commit transaction in N attempts" com ValueError
            if "attempts" in str(e):
                raise Busy("muita gente agendando este barbeiro agora; tente de novo") from e
            raise
        return _doc(appt_ref.get())
