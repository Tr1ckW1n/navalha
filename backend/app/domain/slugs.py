"""Slug público da barbearia (navalha.app/{slug}) — spec §9.1."""

import re

from app.domain.errors import InvalidRequest

# Caminhos que o app usa; um slug com esses nomes quebraria as rotas.
RESERVED = frozenset({
    "api", "admin", "panel", "painel", "public", "login", "logout", "perfil", "health", "docs",
    "openapi", "static", "assets", "app", "www", "navalha", "suporte", "ajuda", "termos", "privacidade",
})
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")


def validate_slug(slug: str) -> str:
    s = (slug or "").strip().lower()
    if not _SLUG.fullmatch(s) or "--" in s:
        raise InvalidRequest("slug deve ter 3 a 40 caracteres: letras minúsculas, números e hífen (sem hífen nas pontas)")
    if s in RESERVED:
        raise InvalidRequest(f"slug reservado: {s}")
    return s
