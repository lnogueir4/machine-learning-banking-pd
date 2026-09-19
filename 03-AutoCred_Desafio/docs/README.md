# Desafio AutoCred — documentação da construção

Este diretório explica **como** a solução foi construída, passo a passo. Foi escrito para quem
nunca viu o projeto: o jargão bancário é explicado onde aparece, e todo número citado pode ser
reproduzido com um comando.

Se você quer saber *o que foi entregue*, vá para `reports/`. Se quer saber *por que* cada decisão
foi tomada em formato curto, veja `aprendizado.md` na raiz do repositório. Aqui está o **como**.

## O problema de negócio

A AutoCred é uma fintech de financiamento de veículos leves, em operação desde janeiro de 2022.
Ela cresceu rápido com uma política de concessão escrita no primeiro ano e nunca revisada. Em 2024
a inadimplência estourou o planejado, e o conselho concluiu que o problema está na **entrada** da
carteira — em quem é aprovado e em que condições — e não na cobrança.

Dois números explicam o diagnóstico:

- **LTV médio de 74%**, com contratos chegando a 95%. LTV (*loan to value*) é o quanto se financia
  dividido pelo valor do veículo. Quanto mais alto, menos o carro cobre a dívida se for preciso
  retomá-lo.
- **LGD de ~70%**, contra 45%–55% em instituições mais maduras. LGD (*loss given default*) é o
  percentual que se perde de fato depois que o cliente deixa de pagar e o bem é retomado e vendido.

O conselho pediu uma política de concessão para 2026 com **ROI anualizado acima de 15%**, sem parar
de originar e dentro do apetite a risco.

## Os dois entregáveis

| | O que é | Como é avaliado |
|---|---|---|
| **Modelo de PD** | probabilidade de um contrato atingir 90 dias de atraso nos 12 meses seguintes à concessão | AuROC numa base futura e oculta (Base B) |
| **Política de crédito** | regras de aprovação, taxa, prazo e entrada por faixa de score | ROI anualizado na carteira simulada (Base C) |

Os dois pesam igual. A nota é relativa ao melhor grupo da turma, e há 20 pontos para a **defesa**
diante de um conselho — sustentar por que cada decisão foi tomada.

A cadeia que precisa ficar explícita, do dado ao resultado:

```
Dados → PD → Score 1-10 → EAD/LGD → Perda esperada → Política → Aceite → ROI
```

## Capítulos

| Capítulo | Código | Assunto |
|---|---|---|
| [01 — Dados](01-dados.md) | `src/dados.py` | as três bases, schema, vazamento e viés de aprovados |
| [02 — Exploração](02-exploracao.md) | `notebooks/01-exploracao.py` | WoE/IV, faltantes, monotonicidade e PSI |
| [03 — Features](03-features.md) | `src/features.py` | imputação, encoding, o pipeline sem vazamento e a parcela reconstruída |
| [04 — Modelo](04-modelo.md) | `src/modelo.py` | candidatos, validação out-of-time, calibração, escolha do vencedor |
| [05 — Score](05-score.md) | `src/score.py` | PD contínua → faixas 1-10, monotonicidade e estabilidade |
| [06 — Risco](06-risco.md) | `src/risco.py` | EAD, LGD e perda esperada a partir das tabelas oficiais |
| [07 — Política](07-politica.md) | `src/politica.py` | alavancas, guardrails, simulação de aceite e ROI |
| [08 — Submissões](08-submissoes.md) | `src/submissoes.py` | geração e conferência dos dois CSVs |

Os oito capítulos estão escritos. O que falta do desafio são os dois documentos de
`reports/`, derivados deles: o relatório do modelo (capítulos 01-05) e o documento de
política (capítulos 06-07).

Dois notebooks acompanham os capítulos e carregam as figuras: [`notebooks/01-exploracao.ipynb`](../notebooks/01-exploracao.ipynb) para o capítulo 02 e [`notebooks/04-modelagem.ipynb`](../notebooks/04-modelagem.ipynb) para os capítulos 04 e 05. Os dois são **gerados por script** a partir das funções de `src/`, nunca editados à mão — notebook mantido em paralelo diverge do pipeline na primeira correção.

## Como reproduzir

Python 3.12.3 com `pandas`, `scikit-learn`, `pyarrow` e `openpyxl`. Não há ambiente virtual: os
pacotes estão no Python global instalado via pyenv-win.

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python src/dados.py             # auditoria das bases
PYTHONIOENCODING=utf-8 python notebooks/01-exploracao.py   # WoE/IV, monotonicidade, PSI
PYTHONIOENCODING=utf-8 python src/features.py           # matriz e pré-processadores
PYTHONIOENCODING=utf-8 python src/modelo.py             # comparação, calibração e modelo final
PYTHONIOENCODING=utf-8 python notebooks/03-decisoes-score.py  # as cinco estratégias de corte
PYTHONIOENCODING=utf-8 python src/score.py              # tabela de faixas 1-10 e testes
PYTHONIOENCODING=utf-8 python src/risco.py              # EAD, LGD, perda esperada e a cadeia
PYTHONIOENCODING=utf-8 python src/politica.py           # alavancas, guardrails, aceite e ROI
PYTHONIOENCODING=utf-8 python src/submissoes.py         # os dois CSVs de entrega e 30 conferências
PYTHONIOENCODING=utf-8 python notebooks/gerar_notebook_modelagem.py  # as figuras dos cap. 04-05
```

`PYTHONIOENCODING=utf-8` é necessário no Windows: o console usa cp1252 e os acentos saem corrompidos
sem isso.

Toda execução que produz artefato grava um JSON em `artefatos/` com data, seed e versões de
biblioteca. A seed é **42** em todo o projeto.

## Regras que o código respeita

1. `bases/` é somente leitura. Nada ali é modificado ou sobrescrito.
2. As duas submissões são geradas por script, nunca editadas à mão.
3. Imputação, encoding e seleção de variáveis são ajustados **apenas no treino**, dentro de um
   `Pipeline` do scikit-learn.
4. Nenhuma coluna marcada como indisponível na concessão entra como preditora — e isso é verificado
   em código, não por memória.
