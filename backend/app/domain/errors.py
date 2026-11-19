"""Erros de domínio. A camada HTTP traduz cada um para um status (ver app/main.py)."""


class DomainError(Exception):
    """Base de todos os erros de regra de negócio."""

    code = "domain_error"


class NotFound(DomainError):
    """Recurso inexistente, inativo ou de outro tenant (HTTP 404). Nunca revela qual dos três."""

    code = "not_found"


class Conflict(DomainError):
    """Estado conflitante, ex.: slug já usado (HTTP 409)."""

    code = "conflict"


class SlotUnavailable(Conflict):
    """Horário ocupado ou fora da grade no instante da gravação (HTTP 409)."""

    code = "slot_unavailable"


class Busy(Conflict):
    """Disputa alta pelo mesmo barbeiro/dia: o banco desistiu após várias tentativas (HTTP 409).
    O cliente deve recarregar os horários e tentar de novo."""

    code = "busy_retry"


class InvalidRequest(DomainError):
    """Entrada válida no formato mas inválida pela regra (HTTP 422)."""

    code = "invalid_request"
