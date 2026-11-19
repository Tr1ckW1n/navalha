"""Contrato de acesso a dados. Toda leitura/escrita de coleção de tenant recebe `shop_id`
e só devolve documentos daquela barbearia (CLAUDE.md invariante 1).

Documentos trafegam como dict com campos camelCase (iguais aos do Firestore) + "id".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.booking import BookingRequest

# coleções genéricas acessíveis por list/get/create/update/delete
TENANT_COLLECTIONS = frozenset({"barbers", "services", "blocks"})


class Repository(ABC):
    # ---------- barbearias ----------
    @abstractmethod
    def get_shop(self, shop_id: str) -> dict | None: ...

    @abstractmethod
    def get_shop_by_slug(self, slug: str) -> dict | None: ...

    @abstractmethod
    def create_shop(self, data: dict) -> dict:
        """Cria a barbearia garantindo slug único (levanta Conflict)."""

    @abstractmethod
    def update_shop(self, shop_id: str, data: dict) -> dict: ...

    # ---------- coleções do tenant ----------
    @abstractmethod
    def list(self, col: str, shop_id: str, *, active_only: bool = False) -> list[dict]: ...

    @abstractmethod
    def get(self, col: str, shop_id: str, doc_id: str) -> dict | None: ...

    @abstractmethod
    def create(self, col: str, shop_id: str, data: dict) -> dict: ...

    @abstractmethod
    def update(self, col: str, shop_id: str, doc_id: str, data: dict) -> dict:
        """Levanta NotFound se o documento não existe ou é de outro tenant."""

    @abstractmethod
    def delete(self, col: str, shop_id: str, doc_id: str) -> None: ...

    # ---------- consultas específicas ----------
    @abstractmethod
    def list_blocks(self, shop_id: str, barber_id: str, start: datetime, end: datetime) -> list[dict]:
        """Bloqueios do barbeiro que tocam [start, end)."""

    @abstractmethod
    def list_appointments(
        self, shop_id: str, *, start: datetime, end: datetime, barber_id: str | None = None
    ) -> list[dict]:
        """Agendamentos com startsAt em [start, end) — invariante 7: só tenant + data (+ barbeiro)."""

    @abstractmethod
    def get_client(self, shop_id: str, phone_e164: str) -> dict | None: ...

    @abstractmethod
    def set_appointment_status(self, shop_id: str, appointment_id: str, status: str, *, now: datetime) -> dict:
        """Aplica domain.booking.plan_status_change. Levanta NotFound/InvalidRequest."""

    # ---------- reserva ----------
    @abstractmethod
    def book(self, req: BookingRequest, *, now: datetime, step_min: int = 30) -> dict:
        """Reserva (ou remarca) dentro de uma transação usando domain.booking.plan_booking."""


def check_collection(col: str) -> None:
    if col not in TENANT_COLLECTIONS:
        raise ValueError(f"coleção não suportada no acesso genérico: {col}")
