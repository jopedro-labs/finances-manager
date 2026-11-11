# TODO

- analisar o file de workflows
- criar repo e fazer commit
- incluir detalhes tecnicos e de segurança no readme
- validar a criação de reports: 

## Estratégia de Investimento

Objetivo de longo prazo — horizonte de 20 anos ou mais, focado em rendimento composto através de uma carteira diversificada de ETFs globais e ações de qualidade. A prioridade é a acumulação consistente, não o timing de mercado.


## Futuro — Métricas XTB adicionais

Campos atualmente ignorados pelo pipeline de extração que podem ser considerados no futuro:

- **Swaps / Financing Fees** (`swap`) — custos de financiamento acumulados; relevante se CFDs ou alavancagem forem introduzidos
- **Commissions** (`commission`) — comissões de transação; útil para tracking de custo líquido real
- **Margin / Leverage** (`margin`) — nível de alavancagem; relevante para auditoria de risco (atualmente assumido 1:1)
- **Open Time** (`open_time`) — timestamp de execução da ordem; útil para análise de período de detenção e fiscalidade

> Estes campos são não-essenciais porque o scoring, gaps de alocação e projeções dependem apenas de valores soberanos do broker (market value, P&L e targets).
