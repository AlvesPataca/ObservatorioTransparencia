# Observatorio Ceres-Rialma

MVP para coletar dados publicos de transparencia das prefeituras de Ceres-GO e Rialma-GO, comecando por licitacoes e contratos.

## Status atual

- Ambiente Python preparado no Windows.
- Dependencias principais instaladas: FastAPI, Uvicorn, SQLAlchemy, Pydantic Settings, HTTPX, BeautifulSoup, Pandas, Playwright e Pytest.
- Chromium do Playwright instalado.
- Primeiro MVP foca em descobrir e validar rotas reais antes de fazer scraping pesado.

## Fontes publicas confirmadas

Fontes verificadas em 2026-09-16:

- Ceres: site oficial `https://ceres.go.gov.br/transparencia/`
- Ceres: portal indicado para licitacoes `https://acessoainformacao.ceres.go.gov.br/cidadao/informacao/licitacoes`
- Rialma: site oficial `https://rialma.go.gov.br/transparencia/`
- Rialma: portal indicado para despesas/receitas e folha em `https://acessoainformacao.rialma.go.gov.br`

Observacao: os portais `acessoainformacao.*` bloqueiam ou podem retornar 403 para `httpx`. O MVP tenta `httpx` primeiro e usa Playwright com Chromium headless como fallback, coletando somente links, tabelas e cards visiveis. As rotas de licitacoes e contratos usadas pelo coletor foram confirmadas na inspeção Playwright; nenhuma API/Swagger foi inventada.

## Como rodar no PowerShell

Abra esta pasta no VS Code e rode:

```powershell
.\scripts\bootstrap.ps1
.\scripts\run_checks.ps1
```

Se voce ja criou o ambiente virtual em outro lugar e ele ja esta ativo, pode pular os comandos de criacao/instalacao e rodar direto os scripts.

Para subir a API basica:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

A API fica disponível em `http://127.0.0.1:8000` e a documentação automática em `http://127.0.0.1:8000/docs`.

Para abrir o dashboard web, inicie a API e acesse `http://127.0.0.1:8000/dashboard`.

O script `run_checks.ps1` tambem gera `data/playwright_portal_inspection.json` e screenshots dos portais quando o navegador consegue abrir as paginas.

Para persistir a coleta localmente em SQLite e consultar os totais:

```powershell
.\.venv\Scripts\python.exe scripts\collect_mvp.py
.\.venv\Scripts\python.exe scripts\import_json_to_db.py
.\.venv\Scripts\python.exe scripts\query_db.py
.\.venv\Scripts\python.exe scripts\analyze_db.py
```

Para coletar despesas paginadas de Ceres:

```powershell
.\.venv\Scripts\python.exe scripts\collect_expenses.py --municipality ceres --max-pages 2
.\.venv\Scripts\python.exe scripts\collect_expenses.py --municipality ceres --all
```

O coletor usa a tabela e a paginação visíveis do portal, registra o total esperado e salva em `data/ceres_despesas.json`.

Para volumes grandes, a coleta de Ceres usa a chamada interna observada na rede (`POST /api`, ação `sgdespesas/listar`) com paginação `start, length`. O Playwright é usado para descobrir/validar a chamada e permanece como fallback para volumes pequenos ou quando o endpoint não puder ser reproduzido.

Para inspecionar e reproduzir a chamada:

```powershell
.\.venv\Scripts\python.exe scripts\inspect_network.py
.\.venv\Scripts\python.exe scripts\replay_expenses_request.py
```

Os detalhes ficam em `data/network/ceres_despesas_2026_requests.json`.

O banco e criado em `data/observatorio.db`. A URL pode ser trocada pela variavel `DATABASE_URL` quando a persistencia for migrada para PostgreSQL.

## Estrutura

```text
app/
  core/       Configuracao base
  models/     Modelos Pydantic do dominio
collectors/
  base/       Cliente HTTP e contratos comuns
  ceres/      Coletor de Ceres
  rialma/     Coletor de Rialma
scripts/
  inspect_portals.py
  collect_mvp.py
  collect_expenses.py
  inspect_network.py
  replay_expenses_request.py
  import_json_to_db.py
  query_db.py
  analyze_db.py
database/
  models.py
  session.py
data/
  saidas locais geradas pelo MVP
tests/
```

## Proximos passos

1. Rodar a inspecao em rede local e confirmar se alguma rota publica responde com HTML, JSON, CSV ou XLSX.
2. Se a API de dados abertos aparecer no portal, registrar a URL exata da especificacao antes de implementar.
3. Migrar a URL do banco para PostgreSQL com SQLAlchemy.
4. Criar analises iniciais de fornecedores, valores, datas e concentracao por modalidade.
