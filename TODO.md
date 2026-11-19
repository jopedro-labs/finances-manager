# TODO — finances-manager

---

## Estado Concluído Recente ✓

- [x] **`scripts/extract_xtb_open_positions.py`** — corrigir field names: `ticker` → `yahoo_ticker`, `currency` → `native_currency`
- [x] **`data/portfolio_targets.json`** — alocações validadas a 100%
- [x] **`core/analysis.py`** — alinhamento de thresholds de qualidade
- [x] **`data/rules.md`** — alinhamento de fórmulas matemáticas e estratégia de longo prazo
- [x] **`scripts/run_quality.py`** — auditoria de qualidade fundamental (Tier A/B/C, persistência no SQLite e geração de `reports/quality_report.md` para os 10 ativos)
- [x] **`scripts/gdrive_jsons_sync.py`** & **`Makefile`** — pull automático de JSONs antes da execução de `make quality`
- [x] **Fase 1: Motor de Scoring Determinístico** — `config.py` (pesos e calibração por `.env`), `core/models.py` (`ScoredAsset` + `HOLD/REBAL`), `core/scoring.py` (cálculo puro offline) e `tests/test_scoring.py` (9/9 testes unitários passados)
- [x] **Fase 2: Alinhamento de Dados & Ciclo de Vida SQLite** — `data/portfolio.json` alinhado (tickers/moedas), `infra/database/schema.py` com inicialização única por processo e `scripts/migrate_json_to_sqlite.py` (`make migrate`) conciliando os 17 ativos
- [x] **Fase 3: Orquestrador de Análise e Oportunidades** — `scripts/run_analysis.py` implementado com look-through, cálculo de penalizações, ranking determinístico e persistência completa em `opportunities` + `opportunity_asset_metrics` sem custos de API

---

## Fase 4 — Relatório com IA e Camada Narrativa (`generate_portfolio_report.py`) ✓

- [x] **`scripts/generate_portfolio_report.py`**:
  - Atualizar para consumir diretamente os dados estruturados do SQLite (`opportunities` + `asset_fundamentals` + snapshots)
  - Enviar contexto enriquecido e pré-calculado ao Gemini (`analyst.md` e `reporter.md`)
  - Mecanismo de fallback: se a API Gemini falhar ou esgotar quota, gerar relatório determinístico local em Markdown
- [x] **Validação end-to-end de `make report` e `make report-html`** (gerado com sucesso em `reports/2026-11-19.md`)

---

## Fase 5 — Interfaces de Terminal (Rich Dashboard & Projeções) ✓

- [x] **`scripts/run_dashboard.py`** — dashboard de terminal executando cálculos de drawdown e métricas históricas (`make dashboard`)
- [x] **`scripts/run_projections.py`** — simulação de cenários de juros compostos e acumulação a longo prazo em matriz 3x3 (`make projections`)
- [x] **`Makefile`** — alvos `make dashboard` e `make projections` operacionais

---

## Fase 6 — Governação e Limpeza de Dependências ✓

- [x] **Auditoria prévia de `infra/` vs. `jopedro-core-lib`**:
  - `infra/` auditado: wrappers redundantes eliminados; `infra/` contém exclusivamente o domínio local do SQLite (`connection.py`, `schema.py`, `finance_sql_extraction.py`)
  - Todo o projeto importa utilitários exclusivamente de `core_lib.logger`, `core_lib.gdrive` e `core_lib.file_utils`
- [x] **Conformidade de Qualidade Global**:
  - `make lint` aprovado a 100% (Ruff lint + format check + `mypy --strict` em todos os 31 ficheiros fonte)
  - `pytest` com 100% de testes passados em `tests/test_scoring.py`
