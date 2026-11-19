# Navalha

SaaS de agendamento e gestão para barbearias. Spec: [`docs/ESPECIFICACAO.md`](docs/ESPECIFICACAO.md) · Regras para o agente: [`CLAUDE.md`](CLAUDE.md) · Fases: [`ROADMAP.md`](ROADMAP.md).

## Colocar no ar (produção)

Veja **[`deploy/GUIA.md`](deploy/GUIA.md)**: um comando no Cloud Shell publica site + API no Cloud Run, cria o Firestore e carrega a Barbearia MF.

- Link dos clientes: `/{slug}` · Painel do dono: `/{slug}/painel` · API: `/api/...` · Documentação: `/api/docs`
- Dados da barbearia: `backend/data/barbearia-mf.json` → `python -m scripts.seed --real --project SEU-PROJETO`

## Rodar no Google Cloud Shell para desenvolver

Cloud Shell já tem Python, Node, Java e `gcloud`. Abra https://shell.cloud.google.com, suba o projeto (upload do zip ou `git clone`) e use **três abas** do terminal.

**1. Emulador (aba 1)**
```bash
cd navalha
npx -y firebase-tools@13 emulators:start --only firestore,auth
```
UI do emulador na porta 4000 (Web Preview → Change port).

**2. API (aba 2)**
```bash
cd navalha/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

**3. Front (aba 3)**
```bash
cd navalha/frontend
npm install
npm run dev
```
Abra **Web Preview → porta 5173**. Abra `/barbearia-mf` (agendamento) e `/barbearia-mf/painel` (dono). O Vite repassa `/api` para o FastAPI. Para testar sem emulador, suba a API com `REPOSITORY=memory SEED_DEMO=true ADMIN_API_KEY=dev`.

## Testar a API sem emulador (mais rápido)

```bash
cd navalha/backend && source .venv/bin/activate
REPOSITORY=memory SEED_DEMO=true ADMIN_API_KEY=dev uvicorn app.main:app --reload --port 8000
```
Abra `/api/docs` (Web Preview → 8000 → acrescente `/api/docs`). A Barbearia MF já existe em `/public/barbearia-mf`. Os dados somem ao reiniciar.

## API (Fase 1)

| Método | Rota | Para quê |
|---|---|---|
| GET | `/api/public/{slug}` | Página pública: barbearia, barbeiros e serviços ativos |
| GET | `/api/public/{slug}/availability?serviceId=&date=AAAA-MM-DD&barberId=` | Horários livres do dia (`barberId` = id ou `any`) |
| POST | `/api/public/{slug}/appointments` | Agendar (exige `consent: true`; `barberId: "any"` escolhe o menos ocupado) |
| * | `/api/admin/shops/...` | Cadastros, bloqueios, agenda do dia e encaixe. **Provisório:** header `X-Admin-Key`; vira login com claims na Fase 3 |

Painel: `PATCH /api/admin/shops/{id}/appointments/{aid}` muda status (concluído/não veio/cancelado). Rotas públicas têm limite por IP (6 agendamentos/10 min, 120 leituras/min).

Erros vêm como `{"error": "...", "detail": "..."}`: 404 `not_found`, 409 `slot_unavailable`/`conflict`, 422 `invalid_request`.

Cadastrar a Barbearia MF no emulador: `FIRESTORE_EMULATOR_HOST=localhost:8080 python -m scripts.seed`.

## Testes

```bash
cd backend && source .venv/bin/activate
pytest                                         # 91 testes: domínio, contrato (memória) e API
FIRESTORE_EMULATOR_HOST=localhost:8080 pytest  # + a mesma suíte de contrato contra o Firestore (14 testes)
```
`tests/test_repo_contract.py` roda **igual** nos dois repositórios. Os testes de concorrência disparam 10 reservas simultâneas no mesmo horário (e 8 em horários sobrepostos) e exigem exatamente 1 sucesso. **Precisam passar no emulador antes de fechar a Fase 1.**

## Desenvolvendo com Claude Code (VSCode)

O agente lê o `CLAUDE.md` automaticamente. Para seguir para a próxima fase, peça explicitamente: *"Leia CLAUDE.md, ROADMAP.md e docs/ESPECIFICACAO.md. Execute a Fase 2 e pare ao final para revisão."*

## Segurança

Nenhum segredo no repo. `backend/app/firestore.py` **recusa** conectar em Firestore real com `ENV=dev` sem emulador.
