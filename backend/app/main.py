from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.domain.errors import Conflict, DomainError, InvalidRequest, NotFound
from app.ratelimit import RateLimitMiddleware
from app.repo.base import Repository
from app.routers import admin, health, public

_STATUS = {NotFound: 404, Conflict: 409, InvalidRequest: 422}


def create_app(repo: Repository | None = None, clock: Callable[[], datetime] | None = None) -> FastAPI:
    """`repo`/`clock` permitem injetar repositório em memória e relógio fixo nos testes."""
    settings = get_settings()
    app = FastAPI(title="Navalha API", version="0.3.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.repo = repo
    app.state.clock = clock
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        booking_rule=settings.rate_limit_booking,
        read_rule=settings.rate_limit_read,
        enabled=settings.rate_limit_enabled,
    )

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError):
        status = next((code for cls, code in _STATUS.items() if isinstance(exc, cls)), 400)
        return JSONResponse(status_code=status, content={"error": exc.code, "detail": str(exc)})

    app.include_router(health.router)  # /health (Cloud Run)
    app.include_router(health.router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    _mount_site(app, Path(settings.static_dir))
    return app


def _mount_site(app: FastAPI, root: Path) -> None:
    """Serve o build do React na mesma URL da API. Qualquer caminho que não seja /api devolve
    o arquivo pedido ou o index.html (rotas do React como /barbearia-mf e /barbearia-mf/painel)."""
    index = root / "index.html"
    if not index.is_file():
        return
    root = root.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def site(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "not_found", "detail": "rota inexistente"})
        f = (root / full_path).resolve()
        if full_path and f.is_file() and root in f.parents:
            return FileResponse(f)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
