"""Carga dos dados da barbearia a partir de um JSON (backend/data/barbearia-mf.json).

`apply_shop_data` é idempotente: cria a barbearia se não existir; se existir, atualiza os
dados, atualiza barbeiros/serviços com o mesmo nome, cria os novos e DESATIVA (não apaga) os que
saíram do arquivo — o histórico de agendamentos continua íntegro (snapshots).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.errors import Conflict, InvalidRequest
from app.models import BarberCreate, BarbershopCreate, ServiceCreate
from app.repo.base import Repository

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "barbearia-mf.json"


def load(path: str | Path = DEFAULT_FILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _service_payload(s: dict) -> dict:
    s = dict(s)
    if "priceReais" in s:  # o arquivo usa reais para facilitar; o sistema guarda centavos
        s["price"] = round(float(str(s.pop("priceReais")).replace(",", ".")) * 100)
    return ServiceCreate.model_validate(s).model_dump(by_alias=True)


def apply_shop_data(repo: Repository, data: dict) -> dict:
    shop_in = BarbershopCreate.model_validate(data["shop"]).model_dump(by_alias=True)
    barbers_in = [BarberCreate.model_validate(b).model_dump(by_alias=True) for b in data.get("barbers", [])]
    services_in = [_service_payload(s) for s in data.get("services", [])]
    if not barbers_in or not services_in:
        raise InvalidRequest("o arquivo precisa de pelo menos um barbeiro e um serviço")

    shop = repo.get_shop_by_slug(shop_in["slug"])
    if shop is None:
        try:
            shop = repo.create_shop(shop_in)
        except Conflict:
            shop = repo.get_shop_by_slug(shop_in["slug"])
    else:
        upd = {k: v for k, v in shop_in.items() if k not in ("slug", "timezone")}
        shop = repo.update_shop(shop["id"], upd)

    sid = shop["id"]
    for col, items in (("barbers", barbers_in), ("services", services_in)):
        existing = {d["name"].strip().lower(): d for d in repo.list(col, sid)}
        keep = set()
        for item in items:
            key = item["name"].strip().lower()
            keep.add(key)
            if key in existing:
                repo.update(col, sid, existing[key]["id"], item)
            else:
                repo.create(col, sid, item)
        for key, d in existing.items():
            if key not in keep and d.get("active", True):
                repo.update(col, sid, d["id"], {"active": False})
    return repo.get_shop(sid)


def seed_barbearia_mf(repo: Repository) -> dict:
    """Atalho usado pelo modo demo (REPOSITORY=memory, SEED_DEMO=true)."""
    return apply_shop_data(repo, load())
