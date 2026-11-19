"""Limite de requisições por IP nas rotas públicas (risco "abuso de endpoints públicos", spec §15).

Janela deslizante em memória, por instância. Com Cloud Run em poucas instâncias (deploy usa
--max-instances=2) isso basta para barrar robôs simples. Se crescer, trocar por Redis/Cloud Armor.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


def parse_rule(rule: str) -> tuple[int, int]:
    """"6/600" -> (6 requisições, 600 segundos)."""
    n, secs = rule.split("/")
    return int(n), int(secs)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, booking_rule: str, read_rule: str, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self.rules = {"booking": parse_rule(booking_rule), "read": parse_rule(read_rule)}
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self.lock = threading.Lock()

    @staticmethod
    def client_ip(request: Request) -> str:
        # No Cloud Run o Google ACRESCENTA o IP real no fim do X-Forwarded-For; o começo pode ser
        # forjado pelo cliente. Por isso vale o último valor.
        fwd = request.headers.get("x-forwarded-for")
        return fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "?")

    def bucket(self, request: Request) -> str | None:
        p = request.url.path
        if not p.startswith("/api/public/"):
            return None
        return "booking" if request.method == "POST" else "read"

    async def dispatch(self, request: Request, call_next):
        b = self.bucket(request) if self.enabled else None
        if b:
            limit, window = self.rules[b]
            key, now = (self.client_ip(request), b), time.monotonic()
            with self.lock:
                q = self.hits[key]
                while q and q[0] <= now - window:
                    q.popleft()
                if len(q) >= limit:
                    retry = int(window - (now - q[0])) + 1
                    return JSONResponse(
                        status_code=429, headers={"Retry-After": str(retry)},
                        content={"error": "rate_limited", "detail": "muitas tentativas; aguarde um pouco e tente de novo"},
                    )
                q.append(now)
        return await call_next(request)
