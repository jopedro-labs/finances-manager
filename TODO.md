# TODO

## Repositório & Organização GitHub

- [ ] Mover `finances-manager` (https://github.com/JoPedro15/finances-manager) para a organization `jopedro-labs`
- [ ] Remover `finances-lab` (https://github.com/jopedro-labs/finances-lab) da organization e manter no GitHub como repo pessoal arquivado
- [ ] Extrair `infra/logger` para repo separado na organization — módulo partilhado por vários projetos
- [ ] Extrair `infra/gdrive` para repo separado na organization — módulo partilhado por vários projetos

## Documentação

- [ ] Adicionar detalhes técnicos e de segurança ao README (OAuth2 scope, gitignore de `secrets/`, aviso sobre `.env`)
- [ ] Adicionar a estratégia de investimento ao `data/rules.md` (ver secção abaixo)

## Pipeline

- [ ] Validar a criação de reports end-to-end (`make report` e `make report-html`)

## GitHub Actions

- [ ] Analisar e rever `.github/workflows/lint.yml` — verificar se cobre todos os casos necessários (python version, dependências, mypy strict)

---

## Estratégia de Investimento — a adicionar ao `data/rules.md`

> Objetivo de longo prazo — horizonte de 20 anos ou mais, focado em rendimento composto através de uma carteira diversificada de ETFs globais e ações de qualidade. A prioridade é a acumulação consistente, não o timing de mercado.

---

## Backlog — Métricas XTB adicionais (não urgente)

Campos actualmente ignorados pelo pipeline de extracção que podem ser considerados no futuro:

| Campo         | Descrição                                                                                       |
|---------------|-------------------------------------------------------------------------------------------------|
| `swap`        | Swaps / Financing Fees — custos de financiamento acumulados; relevante se CFDs ou alavancagem  |
| `commission`  | Comissões de transacção — útil para tracking de custo líquido real                              |
| `margin`      | Nível de alavancagem — relevante para auditoria de risco (actualmente assumido 1:1)             |
| `open_time`   | Timestamp de execução da ordem — útil para análise de período de detenção e fiscalidade         |

> Estes campos são não-essenciais porque o scoring, gaps de alocação e projecções dependem apenas de valores soberanos do broker (market value, P&L e targets).
