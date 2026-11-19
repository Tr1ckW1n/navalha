# CLAUDE.md — Navalha

SaaS de agendamento e gestão para barbearias. Cliente agenda por link web (sem senha); dono/barbeiro opera agenda e consome dashboard de analytics no painel. WhatsApp entra só como lembrete/confirmação (Fase 6). O diferencial é o dashboard, não a agenda.

**Fonte de verdade:** `docs/ESPECIFICACAO.md` (v2.3). Em conflito, a spec prevalece. Execução por fases em `ROADMAP.md`.

## Stack

- Backend: Python 3.12+ / FastAPI (`backend/`)
- Banco: Firestore (emulador em dev — nunca projeto real)
- Auth: Firebase Auth com custom claims `barbershopId` e `role` (`owner` | `barber`)
- Deploy: Cloud Run; jobs: Cloud Scheduler + Cloud Functions
- Frontend: React + Vite (`frontend/`), Recharts
- Mensageria: Meta Cloud API (Fase 6)

## Estrutura

```
backend/app/
  main.py          # create_app(repo, clock): monta routers e traduz erros de domínio em HTTP
  config.py        # settings via env (REPOSITORY, ADMIN_API_KEY, SEED_DEMO…)
  deps.py          # injeção: repositório, relógio, chave de admin
  models.py        # schemas Pydantic (JSON camelCase, igual ao Firestore)
  services.py      # casos de uso: disponibilidade, "qualquer barbeiro"
  seed.py          # dados da Barbearia MF
  firestore.py     # cliente Firestore (respeita FIRESTORE_EMULATOR_HOST)
  domain/          # lógica pura, sem I/O — testável isoladamente
    availability.py  # overlap, slots livres
    booking.py       # plan_booking: valida a reserva e devolve o que gravar
    errors.py        # NotFound 404 · Conflict/SlotUnavailable 409 · InvalidRequest 422
    slugs.py
  repo/            # SÓ leitura/escrita; nenhuma regra de negócio aqui
    base.py          # contrato Repository
    memory.py        # testes e dev sem emulador (trava global = serializável)
    firestore_repo.py  # transação + barberDayLocks
  routers/         # health, public, admin (provisório)
backend/scripts/seed.py
backend/tests/     # pytest; test_repo_contract roda contra memória E Firestore (emulador)
frontend/src/      # React; rotas públicas /:slug e painel /panel
docs/              # spec
```

Regra: **lógica de negócio em `domain/`, sem dependência de FastAPI nem de banco**. Repositórios só leem/gravam e chamam `plan_booking`. Routers só validam entrada, resolvem o tenant e chamam casos de uso.

**Ao mudar o contrato do repositório:** implemente nos DOIS (`memory.py` e `firestore_repo.py`) e cubra em `tests/test_repo_contract.py`.

## Como rodar

Ver `README.md`. Resumo: `firebase emulators:start --only firestore,auth` · `uvicorn app.main:app --reload` (em `backend/`) · `npm run dev` (em `frontend/`). Testes: `pytest` em `backend/`.

## Convenções

- Commits pequenos, imperativos, prefixados por área: `backend: ...`, `frontend: ...`, `docs: ...`.
- Datas sempre `datetime` com tz; nunca naive.
- Dinheiro em **centavos (int)** no backend; formatação só na UI.
- Nomes de campos do Firestore em camelCase (conforme spec §9); código Python em snake_case.

## INVARIANTES — não violar

1. **Tenant:** todo documento (exceto `barbershops`) tem `barbershopId`; **toda** query filtra por ele. No painel, `barbershopId`/`role` vêm **das custom claims do token verificado**, nunca de parâmetro do cliente.
2. **Cliente:** id de `clients` = `{barbershopId}_{phone}` (telefone normalizado E.164). Nunca indexar só por telefone.
3. **Agendamento é transacional:** criar/editar `appointments` acontece dentro de transação Firestore que relê os agendamentos do barbeiro no dia e **aborta** em sobreposição. Vale para público e painel. Proibido "consulta e grava" em dois passos soltos. Use `domain/booking.py`, não reimplemente.
4. **Overlap:** `start < existing_end and end > existing_start`, calculado em memória contra a `durationMin` real. Firestore só filtra `barberId` + range do dia. Passo de início configurável (padrão 30 min).
   - **Janela** = `barbers.hours` se definido, senão `barbershops.openingHours`.
   - **Bloqueios** (`blocks`) do barbeiro entram como ocupados, igual a um agendamento.
   - **Remarcação** acontece na mesma transação: ignora o agendamento antigo no cálculo e o cancela (`cancelReason: remarcado`, `rescheduledTo`).
5. **Status que ocupam slot:** só `scheduled` e `completed`. `canceled` reabre; `no_show` não bloqueia futuro. Enum fechado: `scheduled | completed | no_show | canceled`.
6. **Snapshots:** ao criar `appointment`, copiar `price`, `serviceName`, `barberName` e `commissionPct`. Analytics e comissão leem os snapshots, nunca fazem join.
7. **Analytics:** query filtra só `barbershopId` + range de data (+ `barberId` opcional); todo o resto (serviço, weekday, faixa, status) é filtrado/agregado em Python.
8. **Fuso:** persistir em UTC; converter para `barbershops.timezone` **antes** de agrupar por dia/faixa ou montar slots do dia.
9. **Segredos:** só via env. Nada de chave de serviço no repo. Sem dados sensíveis em URL.
10. **LGPD:** agendamento público sem `consent=True` é rejeitado; `clients.consentAt` registra quando. "Apagar meus dados" anonimiza (nome/telefone) nos agendamentos e apaga o `client`; números financeiros permanecem.
11. **Ocupação** = minutos `scheduled`+`completed` ÷ minutos abertos do barbeiro (janela − bloqueios). `no_show` não conta como ocupado.
12. **Protótipo** (`docs/prototipo/`) é referência de UX e de regra, não código de produção: o frontend React consome a API e **não** reimplementa disponibilidade.
13. **Cliente logado** só acessa agendamentos com `clientPhone` igual ao `phone` do token (`role: client`). Agendar continua sem login.

## Regras de trabalho

- Trabalhe por fase do `ROADMAP.md`. Ao terminar uma fase, **pare e apresente** o que foi feito; aguarde OK.
- Decisão estrutural (dependência relevante, desvio da spec): **pergunte**.
- Spec ambígua ou aparentemente errada: **aponte**, não chute.
- Toda mudança em `domain/` vem com teste.
