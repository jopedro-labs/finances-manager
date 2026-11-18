# TODO — finances-manager

---

## Fase 1 — Correcções críticas (bloqueantes) ✓

- [x] **`scripts/extract_xtb_open_positions.py`** — corrigir field names: `ticker` → `yahoo_ticker`, `currency` → `native_currency` (quebra silenciosa no pipeline de snapshot)
- [x] **`data/portfolio_targets.json`** — corrigir alocações para somarem exactamente 100% (actualmente ~97%, distorce o gap score)
- [x] **`core/analysis.py`** — corrigir threshold ETF Tier A: `age_years <= 3.0` → `age_years <= 5.0` (alinhamento com rules.md)
- [x] **`data/rules.md`** — corrigir fórmula FV_pmt: remover `× (1 + r_monthly)` (anuidade postecipada, alinhamento com código)
- [x] **`data/rules.md`** — adicionar secção de estratégia de investimento (horizonte 20+ anos, acumulação via ETFs globais + acções de qualidade)

---

## Fase 2 — Motor de scoring determinístico

- [ ] **`config.py`** — adicionar campos de scoring weights:
  - `stock_weight_dip`, `stock_weight_forward_pe`, `stock_weight_52w_range`, `stock_weight_allocation`
  - `etf_weight_dip`, `etf_weight_ter`, `etf_weight_allocation`
  - `snapshot_freshness_hours`
  - Reference parameters: `dip_min_pct`, `dip_max_pct`, `alloc_gap_max_pct`, `pe_growth_multiplier`, `pe_neutral_score`, `range_bottom_band`, `ter_low_pct`, `ter_high_pct`, `alloc_gap_normalizer_pct`
- [ ] **`core/models.py`** — adicionar `ScoredAsset` dataclass (score, tier, recommendation, bull_case, bear_case, valuation_status, penalty_factor)
- [ ] **`core/scoring.py`** — implementar motor determinístico completo (fórmulas rules.md Section 1 + decision matrix Section 2):
  - `score_stock(asset, details, current_alloc_pct, target_alloc_pct) → ScoredAsset`
  - `score_etf(asset, details, current_alloc_pct, target_alloc_pct) → ScoredAsset`
  - `apply_exposure_penalty(score, penalty_factor) → float`
  - `build_recommendation(tier, valuation, score, alloc_gap) → RebalanceRecommendation`
- [ ] **`tests/test_scoring.py`** — testes unitários do motor de scoring:
  - Stocks: dip score (falling knife, dip normal, sem dip), P/E growth multiplier, 52w range, allocation gap
  - ETFs: dip score, TER score (excelente/mau), allocation gap
  - Decision matrix: todos os cruzamentos Tier × Valuation × Gap
  - Penalizações de exposição: sector, país, empresa

---

## Fase 3 — Migração e bootstrapping do SQLite

> Antecipada da Fase 4 original — necessária antes do orquestrador para ter dados reais disponíveis.

- [ ] **`scripts/migrate_json_to_sqlite.py`** — adaptar do projecto anterior:
  - Migrar assets de `data/portfolio.json` → tabela `assets`
  - Migrar histórico de `snapshots/snapshots.json` → tabelas `portfolio_snapshots` + `asset_snapshots`
  - Ajustar field names (`ticker` → `yahoo_ticker`, `currency` → `native_currency`)
  - Remover assets obsoletos do SQLite que já não estão em `portfolio.json`
- [ ] **`Makefile`** — adicionar target `make migrate`

---

## Fase 4 — Script de análise principal

- [ ] **`scripts/run_analysis.py`** — orquestrador principal:
  1. Carrega portfolio + targets do SQLite via `repositories.py`
  2. Verifica frescura do snapshot (`snapshot_freshness_hours`)
  3. Enriquece cada asset: preço actual, P/E, 52w, TER, fundamentals via `data_collectors.py`
  4. Calcula exposição consolidada via `core/exposure.py`
  5. Calcula penalty factors por asset
  6. Calcula scores determinísticos via `core/scoring.py`
  7. Persiste em `opportunities` + `opportunity_asset_metrics` via `repositories.py`
  8. Passa dados estruturados ao agente Gemini (`.gemini/agents/analyst.md`)
  9. Salva output em `reports/`
- [ ] **`Makefile`** — adicionar target `make analysis`

---

## Fase 5 — Relatório enriquecido

- [ ] **`scripts/generate_portfolio_report.py`** — actualizar para ler do SQLite em vez de `snapshots/snapshots.json`:
  - Incluir scores determinísticos no contexto enviado ao Gemini
  - Incluir dados de qualidade (Tier, bull/bear cases) de `stock_fundamental_history` / `etf_fundamental_history`
  - Incluir resultado da última análise de oportunidades de `opportunity_asset_metrics`
- [ ] **Validar `make report` e `make report-html` end-to-end**

---

## Fase 6 — CLI de qualidade e dashboard (terminal)

- [ ] **`scripts/run_quality.py`** — análise de qualidade fundamentalista:
  - Itera todos os assets do portfolio + watchlist
  - Corre `evaluate_stock_quality()` / `evaluate_etf_quality()` de `core/analysis.py`
  - Persiste em `stock_fundamental_history` / `etf_fundamental_history`
  - Output Rich no terminal (Tier A/B/C, bull/bear, valuation)
- [ ] **`scripts/run_dashboard.py`** — dashboard terminal com Rich:
  - KPIs: total value, cost basis, ROI, max drawdown, top contributor
  - Usa `core/portfolio_analytics.py` + `infra/database/finance_sql_extraction.py`
  - Output via `PortfolioDashboardPresenter` (criar em `infra/presenters/`)
- [ ] **`Makefile`** — adicionar targets `make quality` e `make dashboard`

---

## Fase 7 — Projecções (terminal)

- [ ] **`scripts/run_projections.py`** — cenários de crescimento no terminal:
  - Conservative 5%, Realistic 8%, Optimistic 11% — PMT €300/mês
  - Usa `core/projections.py` (já implementado)
  - Output Rich: tabela 3×3 (cenários × horizontes 10/20/30 anos)
  - Calcula CAGR histórico via `ProjectionEngine.calculate_historical_cagr()`
- [ ] **`Makefile`** — adicionar target `make projections`

---

## Fase 8 — Alinhar data model

- [ ] **Alinhar `data/portfolio.json`** com o modelo `Asset` de `core/models.py` (verificar todos os campos obrigatórios)
- [ ] **Alinhar `data/portfolio_targets.json`** com o modelo (verificar campos, remover `ticker` se existir)
- [ ] **Alinhar `snapshots/snapshots.json`** com o modelo `PortfolioSnapshot` / `AssetSnapshot` (verificar keys currency-suffixed)
- [ ] **Analisar o ficheiro de workflows**

---

## Organização GitHub

- [ ] Incluir detalhes técnicos e de segurança no README
- [ ] Remover `https://github.com/jopedro-labs/finances-lab` da organização e arquivar no GitHub
- [ ] Mover `https://github.com/JoPedro15/finances-manager` para a organização `jopedro-labs`

---

## Backlog — Infraestrutura (pós-lançamento)

> Não bloquear a conclusão funcional do projecto por estas tarefas.

- [ ] Extrair o logger (`infra/logger/`) para um repo separado na organização `jopedro-labs`
- [ ] Extrair o GDrive client (`infra/gdrive/`) para um repo separado na organização `jopedro-labs`
- [ ] Usar esses repos como dependências em todos os projetos da organização

---

## Backlog — Funcionalidades futuras

- [ ] Script de webscraping para recolher automaticamente os dados do XTB (sem screenshot)
- [ ] Notificações Discord após `make analysis` e `make quality`

---

## Backlog — Métricas XTB adicionais (não urgente)

Campos actualmente ignorados pelo pipeline de extracção:

| Campo | Descrição | Relevância |
|---|---|---|
| `swap` | Custos de financiamento acumulados | Relevante se CFDs ou alavancagem forem introduzidos |
| `commission` | Comissões de transacção | Útil para tracking de custo líquido real |
| `margin` | Nível de alavancagem | Relevante para auditoria de risco (actualmente assumido 1:1) |
| `open_time` | Timestamp de execução da ordem | Útil para análise de período de detenção e fiscalidade |
