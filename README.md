# Observatorio Ceres-Rialma

Sistema local para coletar, armazenar, auditar e visualizar dados publicos de transparencia das prefeituras de Ceres-GO e Rialma-GO.

O projeto hoje cobre:

- coleta de licitacoes e contratos;
- coleta historica de despesas de 2025 e 2026;
- persistencia em SQLite via SQLAlchemy;
- API FastAPI;
- dashboard web por abas;
- auditoria de dinheiro em formato brasileiro;
- motor de pontos de revisao/anomalias com evidencias auditaveis.

> Linguagem do sistema: o projeto nao acusa irregularidade. Ele aponta pontos de revisao, concentracoes, divergencias potenciais e outliers que requerem verificacao documental.

## Estado Atual

Fontes principais:

- Ceres: `https://acessoainformacao.ceres.go.gov.br`
- Rialma: `https://acessoainformacao.rialma.go.gov.br`

Coleta de despesas:

- Ceres usa endpoint interno `POST /api` com acao `sgdespesas/listar`.
- Rialma usa endpoint interno `POST /api` com acao `megasoft/empenhos`.
- A coleta por ano foi validada para 2025 e 2026.
- O tamanho de lote padrao e `length=1000`, evitando navegacao lenta por milhares de paginas.

Dados gerados localmente:

- `data/history/ceres/despesas_2025.json`
- `data/history/ceres/despesas_2026.json`
- `data/history/rialma/despesas_2025.json`
- `data/history/rialma/despesas_2026.json`
- `data/observatorio.db`

Esses arquivos sao gerados e nao devem ser enviados ao GitHub.

## Setup

No PowerShell, dentro da pasta do projeto:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\bootstrap.ps1
```

O bootstrap cria o `.venv`, instala as dependencias e instala o Chromium do Playwright.

Para rodar verificacoes basicas:

```powershell
.\scripts\run_checks.ps1
```

## Coleta

### Inspecao dos Portais

```powershell
.\.venv\Scripts\python.exe scripts\inspect_portals.py
.\.venv\Scripts\python.exe scripts\inspect_with_playwright.py
```

Para inspecionar chamadas de rede usadas pelo portal:

```powershell
.\.venv\Scripts\python.exe scripts\inspect_network.py --municipality ceres --module expenses --year 2026
.\.venv\Scripts\python.exe scripts\inspect_network.py --municipality rialma --module expenses --year 2026
```

Para reproduzir a chamada HTTP de despesas:

```powershell
.\.venv\Scripts\python.exe scripts\replay_expenses_request.py --municipality ceres --year 2026
.\.venv\Scripts\python.exe scripts\replay_expenses_request.py --municipality rialma --year 2026
```

### Licitacoes e Contratos

```powershell
.\.venv\Scripts\python.exe scripts\collect_mvp.py
```

Observacao: licitacoes e contratos ainda representam coleta parcial/amostral. O foco historico completo atual esta em despesas.

### Despesas por Ano

Coleta de teste com poucas paginas:

```powershell
.\.venv\Scripts\python.exe scripts\collect_expenses.py --municipality all --year 2026 --max-pages 2
```

Coleta completa via HTTP direto:

```powershell
.\.venv\Scripts\python.exe scripts\collect_expenses.py --municipality all --years 2025 2026 --all
```

Exemplos especificos:

```powershell
.\.venv\Scripts\python.exe scripts\collect_expenses.py --municipality ceres --year 2026 --all
.\.venv\Scripts\python.exe scripts\collect_expenses.py --municipality rialma --year 2026 --all
```

Os arquivos sao salvos em:

```text
data/history/<municipio>/despesas_<ano>.json
```

## Banco de Dados

O banco local padrao e SQLite:

```text
data/observatorio.db
```

A URL do banco pode ser trocada pela variavel de ambiente:

```powershell
$env:DATABASE_URL="sqlite:///C:/caminho/observatorio.db"
```

ou, futuramente:

```powershell
$env:DATABASE_URL="postgresql+psycopg2://usuario:senha@localhost:5432/observatorio"
```

### Importar Dados

```powershell
.\.venv\Scripts\python.exe scripts\import_json_to_db.py
```

O importador le os JSONs gerados, cria/atualiza registros e evita duplicidade por chave natural.

### Consultar Totais

```powershell
.\.venv\Scripts\python.exe scripts\query_db.py
.\.venv\Scripts\python.exe scripts\debug_data.py
```

## Auditoria de Valores

Valores monetarios usam parsing centralizado para formato brasileiro.

Arquivos importantes:

- `app/core/money.py`
- `tests/test_money_parsing.py`
- `scripts/audit_money.py`
- `scripts/audit_payment_flow.py`
- `scripts/audit_accounting_findings.py`

Rodar auditoria:

```powershell
.\.venv\Scripts\python.exe scripts\audit_money.py
.\.venv\Scripts\python.exe scripts\audit_payment_flow.py
.\.venv\Scripts\python.exe scripts\audit_accounting_findings.py
```

Regra importante: nao mascarar erro financeiro no frontend. Se houver divergencia, rastrear a cadeia completa:

```text
portal -> parser -> JSON -> SQLite -> API -> dashboard
```

## Pontos de Revisao e Anomalias

O motor fica em:

```text
analytics/anomaly_engine.py
```

Ele gera achados auditaveis em `anomaly_findings`, com:

- categoria;
- severidade;
- score;
- explicacao tecnica;
- evidencias em JSON.

Categorias previstas ou implementadas incluem:

- outlier de valor;
- concentracao em fornecedor;
- pagamentos recorrentes;
- divergencia contabil;
- possivel fracionamento;
- descricao repetida;
- fornecedor novo na base local;
- correspondencia com sancoes externas, quando houver fonte configurada.

Recalcular tudo:

```powershell
.\.venv\Scripts\python.exe scripts\rebuild_anomalies.py --all
```

Recalcular uma categoria:

```powershell
.\.venv\Scripts\python.exe scripts\rebuild_anomalies.py --category value_outlier
.\.venv\Scripts\python.exe scripts\rebuild_anomalies.py --category payment_flow_inconsistency
```

Com filtros:

```powershell
.\.venv\Scripts\python.exe scripts\rebuild_anomalies.py --municipality Ceres-GO --year 2026
```

## API e Dashboard

Subir a API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

URLs:

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Dashboard: `http://127.0.0.1:8000/dashboard`

Principais endpoints:

- `GET /health`
- `GET /api/summary`
- `GET /api/records`
- `GET /api/records/{record_id}`
- `GET /api/attention`
- `GET /api/anomalies`
- `GET /api/expenses/summary`
- `GET /api/municipalities`

O dashboard possui abas:

- Dashboard;
- Registros;
- Atencao;
- Fornecedores.

## Performance

Medir endpoints principais:

```powershell
.\.venv\Scripts\python.exe scripts\profile_api.py
```

Diretrizes:

- filtros devem acontecer no banco, nao em listas Python carregadas inteiras;
- endpoints de lista devem usar `limit` e `offset`;
- dashboard nao deve renderizar dezenas de milhares de linhas de uma vez;
- busca textual deve usar debounce no frontend.

## Testes

Rodar todos:

```powershell
.\.venv\Scripts\python.exe -m pytest --cache-clear
```

Areas cobertas:

- parsing monetario;
- API;
- dashboard estatico;
- importacao e banco;
- coleta de despesas;
- analytics;
- motor de anomalias;
- performance e filtros.

## Estrutura

```text
app/
  api/              Rotas FastAPI
  core/             Configuracao e dinheiro
  static/           Dashboard HTML/CSS/JS
  models/           Modelos Pydantic auxiliares
analytics/          Relatorios, anomalias e normalizacao
collectors/
  base/             Coletores genericos, Playwright e HTTP
  ceres/            Adaptadores de Ceres
  rialma/           Adaptadores de Rialma
database/           SQLAlchemy models/session
external/           Adapters planejados para PNCP, CNPJ e Portal Transparencia
scripts/            Coleta, importacao, auditoria e diagnostico
tests/              Testes automatizados
data/               Dados gerados localmente, ignorados no Git
```

## Git e Dados Gerados

Antes de commitar, confira:

```powershell
git status
```

Nao subir:

- `.venv/`
- `data/observatorio.db`
- `data/history/`
- `data/network/`
- JSONs grandes de coleta;
- screenshots;
- `.env`.

Esses arquivos devem estar no `.gitignore`.

Fluxo basico:

```powershell
git add .
git commit -m "Atualiza documentacao do projeto"
git push
```

## Proximos Passos

1. Validar globalmente as regras de divergencia contabil, sem excecoes hardcoded.
2. Reduzir falsos positivos do IQR com grupos mais especificos, percentis e limites absolutos.
3. Separar entidades publicas internas de fornecedores externos nas regras de concentracao.
4. Evoluir licitacoes e contratos para coleta historica completa.
5. Migrar SQLite para PostgreSQL com SQLAlchemy/Alembic.
6. Integrar enriquecimentos externos de forma opcional e cacheada: PNCP, CEIS/CNEP e base CNPJ.
