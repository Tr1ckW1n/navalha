# Colocar o Navalha no ar — passo a passo (Cloud Shell)

Tudo roda no navegador, pelo Google Cloud Shell. Não precisa instalar nada no computador.
Resultado: **um link para os clientes agendarem** e **um painel para o dono**.

## 0. Antes (uma vez)

1. Entre em https://console.cloud.google.com com sua conta Google.
2. Crie um projeto (ex.: `navalha-mf`). Anote o **ID do projeto** (aparece embaixo do nome).
3. Vincule uma **conta de faturamento** ao projeto (Faturamento → Vincular). O Cloud Run e o Cloud Build exigem isso,
   mesmo que o uso fique dentro da cota gratuita. Para uma barbearia, o custo esperado é **R$ 0 ou centavos por mês**.
   Para ficar tranquilo, crie um **alerta de orçamento** de R$ 10 (Faturamento → Orçamentos e alertas).

## 1. Subir os arquivos

1. Abra https://shell.cloud.google.com
2. Menu **⋮ → Fazer upload** → envie o `navalha.zip`.
3. No terminal:
   ```bash
   unzip -o navalha.zip && cd navalha
   ```

## 2. Colocar no ar

```bash
PROJECT_ID=navalha-mf bash deploy/deploy.sh
```
(troque `navalha-mf` pelo ID do seu projeto)

O script faz tudo sozinho, e pode ser rodado de novo sem problema:
- ativa os serviços do Google;
- cria o banco (Firestore, em São Paulo) e os índices;
- cria a **chave do painel** e mostra na tela. **Anote**;
- publica o site e a API no Cloud Run, o que leva de 3 a 6 minutos;
- carrega os dados da Barbearia MF a partir de `backend/data/barbearia-mf.json`.

No fim aparecem:
```
Link para os clientes:  https://navalha-xxxx.a.run.app/barbearia-mf
Painel do dono:         https://navalha-xxxx.a.run.app/barbearia-mf/painel
```

> Na primeira vez, espere **uns 5 minutos** depois do fim do script antes de testar: os índices do banco ainda
> estão sendo criados. Se aparecer erro de "index" nesse intervalo, é só aguardar.

Esqueceu a chave do painel? `gcloud secrets versions access latest --secret=navalha-admin-key`

## 3. Testar (5 minutos)

1. Abra o **link dos clientes** no celular e faça um agendamento de teste com o seu número.
2. Abra o **painel**, entre com a chave e confira o agendamento no dia.
3. No painel, toque em **Cancelar → Confirmar cancelamento**. O horário volta a aparecer no link.
4. Faça um **encaixe** pelo painel.

## 4. Depois da conversa com o dono: dados reais

1. No Cloud Shell, edite o arquivo de dados:
   ```bash
   cloudshell edit backend/data/barbearia-mf.json
   ```
   Preencha com o PDF de levantamento: horário, barbeiros (nome e comissão), serviços (preço em reais e
   duração em minutos) e o WhatsApp.
2. Aplique, **sem precisar publicar de novo**:
   ```bash
   cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -q -r requirements.txt
   python -m scripts.seed --real --project navalha-mf
   ```
   - Barbeiros e serviços com o mesmo nome são atualizados.
   - Os novos são criados.
   - Os que saírem do arquivo são **desativados**, não apagados, e o histórico continua intacto.
   - O link e o painel mostram a mudança na hora.

## 5. Atualizar o sistema (quando eu mandar um zip novo)

```bash
cd ~ && unzip -o navalha.zip && cd navalha && PROJECT_ID=navalha-mf bash deploy/deploy.sh
```
Os dados no banco **não são apagados** ao publicar de novo.

## O que entregar ao dono hoje

- **Link de agendamento** (`.../barbearia-mf`): vai na bio do Instagram, no status e na resposta automática do WhatsApp Business.
- **Painel** (`.../barbearia-mf/painel`) + **chave**: ele salva na tela inicial do celular (Compartilhar → Adicionar à tela inicial).
- **Lembrete:** no painel, no dia anterior, tocar em **Lembrar no WhatsApp** em cada cliente. Abre o WhatsApp com a mensagem pronta.

## Limitações desta versão (avisar o dono)

- O painel usa **uma chave única** para todos. Logins por barbeiro entram na próxima versão.
- O cliente **não remarca nem cancela sozinho** ainda. Ele fala com a barbearia, e o painel cancela.
- **Bloqueios** (folga, médico) ainda não têm tela. Por enquanto, faço pelo `/api/docs` ou o dono avisa e eu bloqueio.
- O dashboard de faturamento, picos e clientes sumidos vem na próxima etapa, já com os dados reais acumulando.

## Problemas comuns

| Sintoma | Solução |
|---|---|
| `billing` / faturamento | Vincule a conta de faturamento (passo 0) e rode o script de novo |
| `DefaultCredentialsError` ao carregar os dados | `gcloud auth application-default login` e rode de novo |
| Erro mencionando `index` | Índices ainda sendo criados; aguarde alguns minutos |
| Painel diz "Chave incorreta" | Pegue a chave com o comando do passo 2 |
| "Muitas tentativas" no link | Proteção contra robô (6 agendamentos a cada 10 min por aparelho); aguarde |
