"""API ponta a ponta com repositório em memória e relógio fixo."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.repo.memory import InMemoryRepository
from tests.conftest import HOURS, NOW, at

KEY = "chave-de-teste"
H = {"X-Admin-Key": KEY}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", KEY)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    c = TestClient(create_app(repo=InMemoryRepository(), clock=lambda: NOW))
    yield c
    get_settings.cache_clear()


@pytest.fixture
def mf(client):
    """Barbearia MF configurada pelas rotas de admin."""
    r = client.post("/api/admin/shops", headers=H, json={
        "name": "Barbearia MF", "slug": "barbearia-mf", "address": "R. Maria Aparecida, Qd 142, Lt 7-A",
        "cep": "74843-180", "whatsapp": "(62) 9455-4348", "openingHours": HOURS,
    })
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    ze = client.post(f"/api/admin/shops/{sid}/barbers", headers=H, json={"name": "Zé", "commissionPct": 50}).json()
    rafa = client.post(f"/api/admin/shops/{sid}/barbers", headers=H, json={"name": "Rafa", "commissionPct": 40}).json()
    corte = client.post(f"/api/admin/shops/{sid}/services", headers=H, json={"name": "Corte", "price": 4000, "durationMin": 45}).json()
    return {"id": sid, "ze": ze["id"], "rafa": rafa["id"], "corte": corte["id"]}


def booking(mf, h, m=0, barber=None, phone="62999990000", consent=True):
    return {"serviceId": mf["corte"], "barberId": barber or mf["ze"], "startsAt": at(h, m).isoformat(),
            "clientName": "Ana", "clientPhone": phone, "consent": consent}


# ---------------- admin ----------------

def test_admin_exige_chave(client):
    assert client.post("/api/admin/shops", json={}).status_code == 401
    assert client.post("/api/admin/shops", headers={"X-Admin-Key": "errada"}, json={}).status_code == 401


def test_admin_desligado_sem_chave_configurada(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    get_settings.cache_clear()
    c = TestClient(create_app(repo=InMemoryRepository(), clock=lambda: NOW))
    assert c.post("/api/admin/shops", headers=H, json={}).status_code == 503
    get_settings.cache_clear()


def test_slug_reservado_duplicado_e_horario_invalido(client, mf):
    base = {"name": "X", "openingHours": HOURS}
    assert client.post("/api/admin/shops", headers=H, json={**base, "slug": "admin"}).status_code == 422
    r = client.post("/api/admin/shops", headers=H, json={**base, "slug": "barbearia-mf"})
    assert r.status_code == 409 and r.json()["error"] == "conflict"
    bad = {"0": [{"opens": "09:00", "closes": "12:00"}, {"opens": "11:00", "closes": "13:00"}]}
    assert client.post("/api/admin/shops", headers=H, json={**base, "slug": "outra", "openingHours": bad}).status_code == 422


def test_servico_valida_duracao_e_preco(client, mf):
    url = f"/api/admin/shops/{mf['id']}/services"
    assert client.post(url, headers=H, json={"name": "X", "price": -1, "durationMin": 30}).status_code == 422
    assert client.post(url, headers=H, json={"name": "X", "price": 100, "durationMin": 7}).status_code == 422


def test_barbeiro_horario_proprio_e_volta_ao_da_casa(client, mf):
    url = f"/api/admin/shops/{mf['id']}/barbers/{mf['rafa']}"
    r = client.patch(url, headers=H, json={"hours": {"0": [{"opens": "14:00", "closes": "20:00"}]}})
    assert r.json()["hours"]["0"] == [{"opens": "14:00", "closes": "20:00"}] and r.json()["hours"]["1"] == []
    assert client.patch(url, headers=H, json={"useShopHours": True}).json()["hours"] is None


def test_admin_nao_ve_outra_barbearia(client, mf):
    outra = client.post("/api/admin/shops", headers=H, json={"name": "Outra", "slug": "outra", "openingHours": HOURS}).json()
    r = client.patch(f"/api/admin/shops/{outra['id']}/barbers/{mf['ze']}", headers=H, json={"name": "Hack"})
    assert r.status_code == 404


# ---------------- público ----------------

def test_pagina_publica_nao_expoe_comissao(client, mf):
    r = client.get("/api/public/barbearia-mf").json()
    assert r["shop"]["name"] == "Barbearia MF" and r["shop"]["whatsapp"] == "+556294554348"
    assert {"id", "name"} == set(r["barbers"][0]) and "commissionPct" not in str(r)
    assert client.get("/api/public/nao-existe").status_code == 404


def test_disponibilidade_any_e_especifico(client, mf):
    q = {"serviceId": mf["corte"], "date": "2026-11-16"}
    any_ = client.get("/api/public/barbearia-mf/availability", params=q).json()
    assert any_["slots"][0]["localTime"] == "09:00" and set(any_["slots"][0]["barberIds"]) == {mf["ze"], mf["rafa"]}
    assert any_["slots"][-1]["localTime"] == "19:00"  # 45 min precisa caber até 20:00
    ze = client.get("/api/public/barbearia-mf/availability", params={**q, "barberId": mf["ze"]}).json()
    assert all(s["barberIds"] == [mf["ze"]] for s in ze["slots"])


def test_disponibilidade_datas_invalidas(client, mf):
    url = "/api/public/barbearia-mf/availability"
    assert client.get(url, params={"serviceId": mf["corte"], "date": "2026-11-15"}).status_code == 422  # ontem
    assert client.get(url, params={"serviceId": mf["corte"], "date": "2027-03-01"}).status_code == 422  # > 60 dias
    assert client.get(url, params={"serviceId": "x", "date": "2026-11-16"}).status_code == 404


def test_domingo_fechado(client, mf):
    r = client.get("/api/public/barbearia-mf/availability", params={"serviceId": mf["corte"], "date": "2026-11-22"})
    assert r.json()["slots"] == []


def test_agendar_conflito_e_qualquer_barbeiro(client, mf):
    url = "/api/public/barbearia-mf/appointments"
    r = client.post(url, json=booking(mf, 10))
    assert r.status_code == 201 and r.json()["barberName"] == "Zé" and "clientPhone" not in r.json()
    r2 = client.post(url, json=booking(mf, 10, phone="62988887777"))
    assert r2.status_code == 409 and r2.json()["error"] == "slot_unavailable"
    r3 = client.post(url, json=booking(mf, 10, barber="any", phone="62988887777"))
    assert r3.status_code == 201 and r3.json()["barberName"] == "Rafa"
    r4 = client.post(url, json=booking(mf, 10, barber="any", phone="62977776666"))
    assert r4.status_code == 409  # os dois ocupados
    slots = client.get("/api/public/barbearia-mf/availability", params={"serviceId": mf["corte"], "date": "2026-11-16"}).json()["slots"]
    assert "10:00" not in [s["localTime"] for s in slots] and "10:30" not in [s["localTime"] for s in slots]


def test_qualquer_barbeiro_escolhe_o_menos_carregado(client, mf):
    url = "/api/public/barbearia-mf/appointments"
    client.post(url, json=booking(mf, 15, phone="62911110001"))  # Zé com 1 no dia
    r = client.post(url, json=booking(mf, 11, barber="any", phone="62911110002"))
    assert r.json()["barberName"] == "Rafa"


def test_agendar_valida_consentimento_e_telefone(client, mf):
    url = "/api/public/barbearia-mf/appointments"
    r = client.post(url, json=booking(mf, 10, consent=False))
    assert r.status_code == 422 and "LGPD" in r.json()["detail"]
    assert client.post(url, json=booking(mf, 10, phone="123")).status_code == 422


def test_bloqueio_tira_horarios_e_pode_ser_removido(client, mf):
    b = client.post(f"/api/admin/shops/{mf['id']}/blocks", headers=H, json={
        "barberId": mf["ze"], "start": at(9).isoformat(), "end": at(12).isoformat(), "reason": "Médico"}).json()
    q = {"serviceId": mf["corte"], "date": "2026-11-16", "barberId": mf["ze"]}
    first = client.get("/api/public/barbearia-mf/availability", params=q).json()["slots"][0]["localTime"]
    assert first == "12:00"
    assert client.delete(f"/api/admin/shops/{mf['id']}/blocks/{b['id']}", headers=H).status_code == 204
    assert client.get("/api/public/barbearia-mf/availability", params=q).json()["slots"][0]["localTime"] == "09:00"


def test_encaixe_pelo_balcao_e_agenda_do_dia(client, mf):
    body = {**booking(mf, 16), "consent": False}
    r = client.post(f"/api/admin/shops/{mf['id']}/appointments", headers=H, json=body)
    assert r.status_code == 201 and r.json()["source"] == "panel" and r.json()["commissionPct"] == 50
    day = client.get(f"/api/admin/shops/{mf['id']}/appointments", headers=H, params={"date": "2026-11-16"}).json()
    assert [a["clientPhone"] for a in day] == ["+5562999990000"]


def test_mudar_status_pelo_painel(client, mf):
    a = client.post("/api/public/barbearia-mf/appointments", json=booking(mf, 10)).json()
    url = f"/api/admin/shops/{mf['id']}/appointments/{a['id']}"
    assert client.patch(url, headers=H, json={"status": "scheduled"}).status_code == 422  # fora do enum
    r = client.patch(url, headers=H, json={"status": "no_show"})
    assert r.status_code == 200 and r.json()["status"] == "no_show"
    assert client.patch(url, headers=H, json={"status": "completed"}).status_code == 422


def test_pagina_publica_traz_id(client, mf):
    assert client.get("/api/public/barbearia-mf").json()["shop"]["id"] == mf["id"]


def test_limite_por_ip(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", KEY)
    monkeypatch.setenv("RATE_LIMIT_BOOKING", "2/600")
    monkeypatch.setenv("RATE_LIMIT_READ", "3/60")
    get_settings.cache_clear()
    from app.seed import seed_barbearia_mf
    repo = InMemoryRepository()
    seed_barbearia_mf(repo)
    c = TestClient(create_app(repo=repo, clock=lambda: NOW))
    codes = [c.get("/api/public/barbearia-mf").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    # outro IP não é afetado
    assert c.get("/api/public/barbearia-mf", headers={"X-Forwarded-For": "200.1.2.3"}).status_code == 200
    # forjar o começo do cabeçalho não engana: vale o último IP (o que o Google acrescenta)
    for _ in range(3):
        c.get("/api/public/barbearia-mf", headers={"X-Forwarded-For": "1.1.1.1, 7.7.7.7"})
    assert c.get("/api/public/barbearia-mf", headers={"X-Forwarded-For": "2.2.2.2, 7.7.7.7"}).status_code == 429
    posts = [c.post("/api/public/barbearia-mf/appointments", json={}, headers={"X-Forwarded-For": "9.9.9.9"}).status_code for _ in range(3)]
    assert posts[:2] == [422, 422] and posts[2] == 429
    get_settings.cache_clear()


def test_api_serve_o_site_com_rotas_do_react(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>navalha</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    get_settings.cache_clear()
    c = TestClient(create_app(repo=InMemoryRepository(), clock=lambda: NOW))
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert "navalha" in c.get("/barbearia-mf/painel").text  # rota do React cai no index.html
    assert c.get("/api/nao-existe").status_code == 404
    assert c.get("/../../etc/passwd").status_code in (200, 404) and "root:" not in c.get("/../../etc/passwd").text
    assert c.get("/health").json()["status"] == "ok"
    get_settings.cache_clear()
