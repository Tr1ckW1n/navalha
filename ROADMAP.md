# ROADMAP — Navalha

Execução por fases. Cada fase termina com revisão; não avançar sem OK.

## Fase 0 — Setup ✅ (bootstrap)
- [x] Monorepo `backend/`, `frontend/`, `docs/`
- [x] `CLAUDE.md` com invariantes; spec v2.0 em `docs/`
- [x] FastAPI com `GET /health`
- [x] Config via env + cliente Firestore apontando para emulador
- [x] `firebase.json` com emuladores Firestore + Auth
- [x] React + Vite com rotas pública (`/:slug`) e painel (`/panel`) placeholders
- [x] `.gitignore`, `.env.example`, README
- [x] **Antecipado da Fase 1:** núcleo puro de disponibilidade (`domain/availability.py`) + testes
- [ ] Criar repositório no GitHub e primeiro push
- [ ] Rodar tudo no ambiente de dev (Cloud Shell) e confirmar `/health` + front

**Marco:** ambiente rodando.

## Fase 1 — Modelo de dados + CRUD + disponibilidade transacional
- [x] Schemas Pydantic (`app/models.py`): barbearia, barbeiro, serviço, bloqueio, reserva; horários validados (sem sobreposição), dinheiro em centavos, duração múltipla de 5
- [x] Normalização de telefone (E.164) e id `{barbershopId}_{phone}`
- [x] Regra de reserva **pura** (`domain/booking.plan_booking`) + repositórios que só leem/gravam
- [x] Repositórios com filtro obrigatório por `barbershopId`: `InMemoryRepository` e `FirestoreRepository` (transação + documento-trava)
- [x] Slug único global (`slugs/{slug}` criado na mesma transação) e validação contra paths reservados
- [x] CRUD provisório em `/admin/shops/...` (barbearia, barbeiros, serviços, bloqueios, agenda do dia, encaixe) com `X-Admin-Key`
- [x] Público: `GET /public/{slug}`, `GET /public/{slug}/availability`, `POST /public/{slug}/appointments` (com "qualquer barbeiro")
- [x] Seed da Barbearia MF (`app/seed.py`, `python -m scripts.seed`)
- [x] Testes: 91 passando (domínio, contrato do repositório em memória, API ponta a ponta)
- [ ] **Rodar a suíte de contrato contra o emulador** (`FIRESTORE_EMULATOR_HOST=localhost:8080 pytest`): 14 testes, incluindo concorrência (10 reservas simultâneas → 1 vencedora) e sobreposição parcial
- [ ] Deploy de teste no Cloud Run (opcional nesta fase)

**Marco:** API funcional.

## Versão de lançamento (piloto Barbearia MF) ✅
- [x] Site React servido pela própria API (uma URL só, Cloud Run)
- [x] Agendamento público ligado à API (serviço → barbeiro/qualquer um → horário → dados + LGPD)
- [x] Painel provisório do dono (chave única): agenda do dia por barbeiro, concluído/não veio/cancelar, encaixe, lembrete wa.me
- [x] Limite por IP nas rotas públicas; status do agendamento (RF07) com transação
- [x] Dados da barbearia por JSON idempotente (`scripts/seed.py`); deploy em um comando (`deploy/deploy.sh`)
- [x] PDF de levantamento para o dono
- [ ] Preencher `backend/data/barbearia-mf.json` com os dados reais e aplicar
- [ ] Rodar a suíte de contrato no emulador

## Fase 2 — Agendamento público (web)
- [ ] Qualquer barbeiro (RF04a)
- [ ] Perfil do cliente com telefone + senha (RF04e, spec §12.1): primeiro acesso, entrar, sair, trocar senha, recado ao barbeiro
- [ ] No perfil: remarcar, cancelar, repetir, apagar dados (RF04b–d)
- [ ] "Liberar nova senha" na ficha do cliente (painel)
- [ ] Consentimento LGPD no formulário
- [ ] Página `/:slug`: serviço → barbeiro → data → horário → nome/telefone → confirmação
- [x] Throttle por IP nos endpoints públicos
- [ ] Tratamento de conflito (409) com recarga dos horários

**Marco:** cliente marca horário.

## Fase 3 — Painel + auth + agenda + summary
- [ ] Login Firebase Auth; middleware que verifica token e extrai claims
- [ ] Script de provisionamento manual (cria barbearia + usuário + claims)
- [ ] Agenda dia/semana (owner vê todos; barber vê a própria)
- [ ] Mudar status (concluído / no-show / cancelado); agendamento manual
- [ ] CRUD de serviços/barbeiros no painel, com comissão e horário próprio
- [ ] Bloqueios do barbeiro (RF10b) e anotações de cliente (RF10c)
- [ ] Configurações: prazo de cancelamento, dias para inativo, barbeiro vê faturamento
- [ ] `/analytics/summary` (faturamento, lucro, ticket médio, no-show) — ver nota abaixo
- [ ] **Lembrete manual gratuito** (spec §11.1): fila hoje/amanhã por barbeiro e geral, link `wa.me` com texto pronto, registro `reminder` (sentAt, reply), marcação de resposta
- [ ] Métrica: no-show de quem confirmou × quem não respondeu

**Marco:** produto utilizável + validação com barbearia-cobaia.

> Nota: a spec v2.0 antecipa o `/analytics/summary` para a Fase 3 (validação toca o diferencial). A instrução original do projeto era não antecipar dashboard antes de dados reais. **Decisão pendente do Patrick.**

## Fase 4 — Dashboard analítico
- [ ] Agregação em memória com conversão de fuso (spec §10)
- [ ] `/analytics/heatmap`, `/analytics/services`, `/analytics/clients` (inativos + "chamar de volta")
- [ ] Comissões por barbeiro e lucro líquido; comparação com período anterior
- [ ] Filtros cruzáveis (RF17)
- [ ] UI com Recharts

**Marco:** diferencial no ar.

## Fase 5 — Gastos + lucro
- [ ] CRUD de `expenses`; lucro por período

**Marco:** visão financeira completa.

## Fase 6 — WhatsApp automático (API oficial)
> Só iniciar se o modo manual mostrar queda de no-show na barbearia-cobaia. Custo: ~US$ 0,0068/lembrete (spec §11.2).
- [ ] Template de lembrete (utilidade) com quick-reply carregando `appointmentId`
- [ ] Job diário + disparo no ato para agendamentos < 24h
- [ ] Webhook de resposta correlacionado por `appointmentId`

**Marco:** canal híbrido ativo.
