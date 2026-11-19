"""Dependências injetáveis (repositório, relógio, chave de admin)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import Header, HTTPException, Request

from app.config import get_settings
from app.repo.base import Repository


def get_repo(request: Request) -> Repository:
    repo = getattr(request.app.state, "repo", None)
    if repo is None:
        s = get_settings()
        if s.repository == "memory":
            from app.repo.memory import InMemoryRepository

            repo = InMemoryRepository()
            if s.seed_demo:
                from app.seed import seed_barbearia_mf

                seed_barbearia_mf(repo)
        else:
            from app.firestore import get_db
            from app.repo.firestore_repo import FirestoreRepository

            repo = FirestoreRepository(get_db())
        request.app.state.repo = repo
    return repo


def get_now(request: Request) -> datetime:
    clock = getattr(request.app.state, "clock", None)
    return clock() if clock else datetime.now(UTC)


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """Proteção provisória das rotas /admin (Fase 1–2). Na Fase 3 vira token Firebase + claims."""
    key = get_settings().admin_api_key
    if not key:
        raise HTTPException(status_code=503, detail="rotas de administração desligadas (defina ADMIN_API_KEY)")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, key):
        raise HTTPException(status_code=401, detail="chave de administração inválida")
