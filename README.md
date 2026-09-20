# Banking Analytics — Desafio AutoCred

Workspace de uma mentoria de **risco de crédito** (Analítica Educação — Programa Jump) e,
sobretudo, a solução completa do **Desafio AutoCred**: um modelo de probabilidade de
inadimplência e a política de concessão construída em cima dele.

Nada aqui foi editado à mão. As duas submissões, os dois documentos de entrega e todas as
tabelas citadas na documentação saem de scripts em [`src/`](03-AutoCred_Desafio/src/), com
seed fixa e **64 conferências automáticas** que falham alto se um número deixar de bater.

## O problema

A AutoCred é uma fintech de financiamento de veículos, em operação desde 2022, que cresceu
com uma política de concessão escrita no primeiro ano e nunca revisada. Em 2024 a
inadimplência estourou o planejado. O conselho concluiu que o problema está em **quem é
aprovado e em que condições**, e pediu uma política para 2026 com ROI anualizado acima de 15%
— sem parar de originar.

A cadeia que precisa estar explícita, do dado ao resultado:

```
Dados → PD → Score 1-10 → EAD/LGD → Perda esperada → Política → Aceite → ROI
```

## O que foi entregue

| Entregável | O que é | Como é avaliado |
|---|---|---|
| [`submissao_modelo.csv`](03-AutoCred_Desafio/entregaveis/submissao_modelo.csv) | PD de 3.000 contratos futuros (Base B) | AuROC numa base oculta |
| [`submissao_politica.csv`](03-AutoCred_Desafio/entregaveis/submissao_politica.csv) | decisão, taxa, prazo e entrada de 5.000 propostas (Base C) | ROI anualizado da carteira simulada |
| [`relatorio_modelo.md`](03-AutoCred_Desafio/reports/relatorio_modelo.md) | 13 seções para a banca técnica | qualidade técnica e coerência |
| [`documento_politica.docx`](03-AutoCred_Desafio/reports/documento_politica.docx) | 3 páginas para o conselho, no template oficial | defesa de negócio |

**Modelo:** `HistGradientBoosting` regularizado sobre 17 variáveis, calibrado por Platt.
AuROC medido três vezes em dados que o modelo não viu — validação encadeada em janelas
anteriores a 2024, *out-of-fold* na base inteira e *out-of-time* em 2024: **0,7226 a 0,7434**.
Reportamos a faixa, não o melhor dos três.

**Política:** aprovar da faixa 5 para cima, com taxa entre 2,27% e 2,82% ao mês e entrada
mínima de 21% nas duas faixas de baixo. Ela não foi escolhida por maximizar o ROI projetado, e
sim por ser a que sobrevive ao cenário adverso — aceite pessimista e PD 20% acima da prevista
ao mesmo tempo:

| Indicador | Cenário central | Cenário adverso | Guard-rail |
|---|---|---|---|
| Taxa de aprovação | 52,8% (2.642 de 5.000) | — | ≥ 35% |
| Volume originado | R$ 67,4 mi | R$ 42,8 mi | ≥ R$ 40 mi |
| Inadimplência | 5,93% | 7,67% | ≤ 8% |
| Taxa média ao mês | 2,46% (máx. 2,82%) | — | ≤ 3,5% |
| ROI anualizado | 15,7% | 14,8% | meta > 15% |

A regra de maior ROI encontrada na busca projeta 21,6% e quebra guard-rail nesse mesmo teste.

## Três decisões que definem o projeto

- **Não podar variáveis.** A importância por permutação sugeria cortar cinco delas, e o
  *out-of-time* de 2024 concordava: o AuROC subia de 0,7434 para 0,7546. Em janelas
  independentes ele **caía** — 0,7226 para 0,7160. Quando as duas réguas discordam de ponta a
  ponta, a que foi consultada dezenas de vezes durante o desenvolvimento é a suspeita.
  [Cap. 04](03-AutoCred_Desafio/docs/04-modelo.md)
- **42,6% da Base C está fora do domínio histórico** em pelo menos uma variável de crédito.
  As bases de treino só contêm contratos que a política antiga aprovou; a base de política é
  mar aberto. Árvores não extrapolam, então a PD desses perfis é **subestimada** por
  construção — o risco técnico mais sério do desafio, publicado em vez de escondido.
  [Cap. 01](03-AutoCred_Desafio/docs/01-dados.md)
- **`qtd_parcelas_em_atraso_12m` sozinha dá AuROC de 0,9644** e não entra no modelo. Parece
  variável de bureau, mas é comportamento posterior à concessão: usá-la seria prever o passado.
  A checagem de vazamento é código, não memória. [Cap. 03](03-AutoCred_Desafio/docs/03-features.md)

## Estrutura

```
03-AutoCred_Desafio/
├── bases/        # entrada, somente leitura — nunca modificada
├── src/          # dados, exploração, features, modelo, score, risco, política, relatórios
├── notebooks/    # scripts de decisão e os dois .ipynb com as figuras (gerados, não escritos)
├── docs/         # 8 capítulos: como cada etapa foi construída
├── artefatos/    # modelo serializado, tabelas e um JSON por execução (data, seed, versões)
├── entregaveis/  # as duas submissões
└── reports/      # os dois documentos de entrega
```

Na raiz, três arquivos de trabalho: [`CLAUDE.md`](CLAUDE.md) (regras operacionais do projeto),
[`aprendizado.md`](aprendizado.md) (o *porquê* de cada decisão, em formato de resposta ao
conselho) e [`memory.md`](memory.md) (estado entre sessões).

## Como reproduzir

Python 3.12.3 com `pandas`, `scikit-learn`, `pyarrow` e `openpyxl`. Seed **42** em todo o
projeto; `PYTHONIOENCODING=utf-8` é necessário no Windows, senão os acentos saem corrompidos.

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python src/dados.py         # auditoria das bases: 1 minuto, nenhum artefato alterado
```

A cadeia completa, na ordem certa, está em
[`docs/README.md`](03-AutoCred_Desafio/docs/README.md). Repeti-la aqui garantiria que uma das
duas listas ficasse desatualizada na primeira mudança.

## Por onde começar a leitura

| Se você quer | Abra |
|---|---|
| ver o resultado em 3 páginas | [`reports/documento_politica.md`](03-AutoCred_Desafio/reports/documento_politica.md) |
| avaliar o modelo em detalhe | [`reports/relatorio_modelo.md`](03-AutoCred_Desafio/reports/relatorio_modelo.md) |
| entender **como** foi construído | [`docs/`](03-AutoCred_Desafio/docs/README.md), capítulo por capítulo |
| entender **por que** cada decisão | [`aprendizado.md`](aprendizado.md) |

O material das mentorias que originou o desafio (PDFs e transcrições) fica fora do controle de
versão por decisão do autor — o repositório carrega o trabalho, não o material de aula.
