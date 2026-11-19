"""Contrato do repositório: a MESMA suíte roda contra memória e Firestore (emulador).

Rodar contra o Firestore:  FIRESTORE_EMULATOR_HOST=localhost:8080 pytest tests/test_repo_contract.py
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from app.domain.booking import day_bounds
from app.domain.errors import Busy, Conflict, InvalidRequest, NotFound, SlotUnavailable
from tests.conftest import DAY, NOW, TZ, at, req, seed_shop


# ---------------- tenant e cadastros ----------------

def test_isolamento_entre_barbearias(repo, shop):
    outra = seed_shop(repo)
    assert repo.get("barbers", outra.id, shop.ze["id"]) is None
    assert {b["id"] for b in repo.list("barbers", outra.id)} == {outra.ze["id"], outra.rafa["id"]}
    with pytest.raises(NotFound):
        repo.update("services", outra.id, shop.corte["id"], {"price": 1})
    with pytest.raises(NotFound):
        repo.delete("barbers", outra.id, shop.ze["id"])


def test_slug_unico_e_busca_por_slug(repo, shop):
    assert repo.get_shop_by_slug(shop.shop["slug"])["id"] == shop.id
    with pytest.raises(Conflict):
        seed_shop(repo, slug=shop.shop["slug"])


def test_list_active_only(repo, shop):
    repo.update("barbers", shop.id, shop.rafa["id"], {"active": False})
    assert [b["id"] for b in repo.list("barbers", shop.id, active_only=True)] == [shop.ze["id"]]


# ---------------- reserva ----------------

def test_reserva_grava_snapshots_e_cliente(repo, shop):
    a = repo.book(req(shop, 10), now=NOW)
    assert (a["barberName"], a["serviceName"], a["price"], a["commissionPct"]) == ("Zé", "Corte", 4000, 50)
    assert a["endsAt"] - a["startsAt"] == timedelta(minutes=45)
    c = repo.get_client(shop.id, "+5562999990000")
    assert c["name"] == "Cliente" and c.get("consentAt") is not None


def test_snapshot_nao_muda_com_preco_novo(repo, shop):
    a = repo.book(req(shop, 10), now=NOW)
    repo.update("services", shop.id, shop.corte["id"], {"price": 5000, "name": "Corte degradê"})
    start, end = day_bounds(DAY, TZ)
    got = next(x for x in repo.list_appointments(shop.id, start=start, end=end) if x["id"] == a["id"])
    assert (got["price"], got["serviceName"]) == (4000, "Corte")


def test_duracao_real_bloqueia_slot_seguinte(repo, shop):
    repo.book(req(shop, 10), now=NOW)  # 10:00–10:45
    with pytest.raises(SlotUnavailable):
        repo.book(req(shop, 10, 30, phone="62988880001"), now=NOW)
    repo.book(req(shop, 11, phone="62988880002"), now=NOW)  # encostado: ok
    repo.book(req(shop, 10, 30, barber=shop.rafa, phone="62988880003"), now=NOW)  # outro barbeiro: ok


def test_bloqueio_impede_reserva_so_do_proprio_barbeiro(repo, shop):
    repo.create("blocks", shop.id, {"barberId": shop.ze["id"], "start": at(14), "end": at(16), "reason": "Médico"})
    with pytest.raises(SlotUnavailable):
        repo.book(req(shop, 15), now=NOW)
    repo.book(req(shop, 15, barber=shop.rafa), now=NOW)
    assert len(repo.list_blocks(shop.id, shop.ze["id"], at(0), at(23))) == 1


def test_horario_proprio_do_barbeiro(repo, shop):
    tarde = {str(d): [{"opens": "14:00", "closes": "20:00"}] for d in range(7)}
    repo.update("barbers", shop.id, shop.rafa["id"], {"hours": tarde})
    with pytest.raises(SlotUnavailable):
        repo.book(req(shop, 10, barber=shop.rafa), now=NOW)
    repo.book(req(shop, 14, barber=shop.rafa), now=NOW)


def test_remarcacao_atomica(repo, shop):
    old = repo.book(req(shop, 10), now=NOW)
    new = repo.book(req(shop, 10, 30, replace_appointment_id=old["id"]), now=NOW)  # sobre o próprio horário
    start, end = day_bounds(DAY, TZ)
    by_id = {a["id"]: a for a in repo.list_appointments(shop.id, start=start, end=end)}
    assert by_id[old["id"]]["status"] == "canceled" and by_id[old["id"]]["rescheduledTo"] == new["id"]
    assert by_id[new["id"]]["rescheduledFrom"] == old["id"]
    repo.book(req(shop, 9, 30, phone="62988880009"), now=NOW)  # 09:30–10:15 só cabe porque o antigo saiu


def test_remarcacao_com_telefone_diferente_e_recusada(repo, shop):
    old = repo.book(req(shop, 10), now=NOW)
    with pytest.raises(InvalidRequest):
        repo.book(req(shop, 11, phone="62977776666", replace_appointment_id=old["id"]), now=NOW)


def test_consentimento_obrigatorio(repo, shop):
    with pytest.raises(InvalidRequest):
        repo.book(req(shop, 10, consent=False), now=NOW)


def test_list_appointments_filtra_barbeiro_e_dia(repo, shop):
    repo.book(req(shop, 10), now=NOW)
    repo.book(req(shop, 10, barber=shop.rafa, phone="62988880001"), now=NOW)
    repo.book(req(shop, 10, d=DAY + timedelta(days=1), phone="62988880002"), now=NOW)
    start, end = day_bounds(DAY, TZ)
    assert len(repo.list_appointments(shop.id, start=start, end=end)) == 2
    assert len(repo.list_appointments(shop.id, start=start, end=end, barber_id=shop.ze["id"])) == 1


# ---------------- concorrência (RNF03) ----------------

def test_concorrencia_um_unico_vencedor(repo, shop):
    n = 10

    def tentar(i):
        try:
            return repo.book(req(shop, 14, phone=f"6299999{i:04d}"), now=NOW)
        except (SlotUnavailable, Busy):  # Busy = Firestore desistiu sob disputa; também é 409
            return None

    with ThreadPoolExecutor(max_workers=n) as ex:
        results = list(ex.map(tentar, range(n)))
    assert sum(r is not None for r in results) == 1
    start, end = day_bounds(DAY, TZ)
    assert len([a for a in repo.list_appointments(shop.id, start=start, end=end) if a["status"] == "scheduled"]) == 1


def test_concorrencia_sobreposicao_parcial(repo, shop):
    """Horários diferentes mas sobrepostos (14:00 e 14:30 com 45 min) também têm um só vencedor."""
    starts = [(14, 0), (14, 30)] * 4

    def tentar(i):
        h, m = starts[i]
        try:
            return repo.book(req(shop, h, m, phone=f"6298888{i:04d}"), now=NOW)
        except (SlotUnavailable, Busy):  # Busy = Firestore desistiu sob disputa; também é 409
            return None

    with ThreadPoolExecutor(max_workers=len(starts)) as ex:
        results = list(ex.map(tentar, range(len(starts))))
    assert sum(r is not None for r in results) == 1


# ---------------- status (RF07) ----------------

def test_mudar_status_e_cancelar_libera_horario(repo, shop):
    a = repo.book(req(shop, 10), now=NOW)
    done = repo.set_appointment_status(shop.id, a["id"], "canceled", now=NOW)
    assert done["status"] == "canceled" and done["cancelReason"] == "cancelado pela barbearia"
    repo.book(req(shop, 10, phone="62988880001"), now=NOW)  # horário voltou a ficar livre
    with pytest.raises(InvalidRequest):
        repo.set_appointment_status(shop.id, a["id"], "completed", now=NOW)  # não sai de canceled
    outra = seed_shop(repo)
    with pytest.raises(NotFound):
        repo.set_appointment_status(outra.id, a["id"], "no_show", now=NOW)


# ---------------- carga de dados (seed por JSON) ----------------

def test_apply_shop_data_e_idempotente_e_desativa_removidos(repo):
    from app.seed import apply_shop_data, load

    data = load()
    data["shop"]["slug"] = "mf-" + __import__("uuid").uuid4().hex[:8]
    s1 = apply_shop_data(repo, data)
    assert len(repo.list("services", s1["id"])) == len(data["services"])
    data["services"] = data["services"][:2]
    data["services"][0]["priceReais"] = 45
    data["barbers"].append({"name": "Biel", "commissionPct": 40})
    s2 = apply_shop_data(repo, data)
    assert s1["id"] == s2["id"]
    svcs = {s["name"]: s for s in repo.list("services", s2["id"])}
    assert svcs["Corte"]["price"] == 4500 and not svcs["Pezinho"]["active"] and len(svcs) == 6
    assert {b["name"] for b in repo.list("barbers", s2["id"], active_only=True)} == {"Zé", "Rafa", "Biel"}
