# memory.md — memória de sessões

Estado atual, tratativas em aberto e próximos passos. Entrada nova **no topo**. Resumido: o que mudou,
a decisão, a pendência. Detalhe técnico duradouro vai para o `CLAUDE.md`.

---

## 2026-09-20 (meio-dia) — README da raiz criado; `docs/README.md` auditado

- **Novo:** `README.md` na raiz — porta de entrada do repositório (problema, entregáveis,
  resultado com guardrails, três decisões que definem o projeto, onde ler o quê). 16 links
  conferidos, nenhum quebrado.
- **Corrigido em `docs/README.md`:** o bloco de reprodução rodava `src/modelo.py` sem `--poda`,
  e sem ele `validacao_encadeada.csv` não existe — clone limpo quebrava com `FileNotFoundError`
  no relatório do modelo. Faltavam também `notebooks/02-decisoes-features.py` e
  `gerar_notebook.py`, e a nota atribuía `importancias.csv` ao `--poda` (sai de qualquer run).
- **Corrigido em `CLAUDE.md`:** dizia que o repositório é "de dados e documentos, sem código" e
  que "não há git" — falso desde o primeiro commit. Atualizados também a estrutura de pastas (era
  "ainda não existe"), a lista de dependências com versões e a dependência de ordem do `--poda`.
- Commitado e enviado para `origin/main`.

---

## 2026-09-20 (manhã) — relatório do modelo pronto: **os dois entregáveis escritos estão fechados**

**Construído**
- `src/relatorio_modelo.py` — gera `reports/relatorio_modelo.md` (~35 KB, 13 seções) para a banca
  técnica, com 21 conferências. Markdown porque o desafio não deu template para este; o único
  `.docx` fornecido é o do documento de política.
- `modelo.py` passou a gravar `artefatos/importancias.csv` e `validacao_encadeada.csv` — as duas
  tabelas que sustentam a decisão de não podar variáveis e que só existiam no stdout.
- Rodei `modelo.py --poda`: `modelo_pd.joblib` e `modelo_comparacao.csv` saíram **byte a byte
  idênticos**. O pipeline é determinístico de ponta a ponta.

**Erro corrigido** — `docs/05-score.md`
- A tabela de granularidade comparava 5/10/20 faixas, mas a linha de dez trazia a estratégia
  **progressiva** (0,7297) entre duas linhas por quantil. Devolvida à família certa (0,7276), com
  a progressiva num parágrafo próprio. Mesma doença no meu rascunho: a faixa de AuROC reportada
  misturava calibrado (0,7226) com não calibrado (0,7410). Correta: **0,7226 a 0,7434**.
- 1 entrada nova em `aprendizado.md` (25 no total).

**Estado da entrega**
- Submissões e `documento_politica.md` seguem byte a byte idênticos. 30 + 13 + 21 conferências,
  0 falhas.
- Continua faltando preencher à mão no `.docx`: **número do grupo** e os **três nomes** da seção 8.
  O usuário disse que preenche depois.

**Próximo passo**
Nada obrigatório em aberto. O que resta é opcional e nesta ordem: (1) uma passada de revisão nos
dois documentos com olhos de banca; (2) commit do que está solto. **5 dias** até 25/09/2026 23h59.

---

## 2026-09-19 (fim da noite) — `relatorios.py` + documento de política: **falta só o relatório do modelo**

**Construído**
- `src/relatorios.py` — gera `reports/documento_politica.md` e `.docx` preenchendo o template
  oficial, com 13 conferências de coerência contra `submissao_politica.csv` lido do disco.
  Nenhum número digitado. Refaz o teste de estresse (9 células) sobre a oferta publicada.
- 2,7 páginas no template de 2 a 3. Tabelas a 9pt com larguras explícitas — a 11pt dava 4,2.
- 1 entrada nova em `aprendizado.md` (24 no total).

**Erro corrigido na origem** — `politica.py`
- A coluna `prazo_medio` de `tabela_politica.csv` era média **simples**; o `roi` da mesma linha
  usava a média **ponderada por volume e aceite**. Quem refizesse a conta pela linha errava até
  **0,59 p.p. na faixa 5**, com viés crescente em direção às faixas piores. Corrigido para a
  ponderada; virou checagem. Capítulo 07 atualizado (prazos 42/42/41/42/41/41) e a coluna de PD
  daquela tabela passou a se chamar `PD precificada`, que é o que ela sempre foi.
- Escrevi "faixas 1 a 4 = 30% da base" de cabeça; são **20%** na Base A e 47,2% na Base C. Agora
  os dois saem do artefato.

**Decisões do documento**
- A coluna `Perda esperada` da tabela publicada é a das **condições pedidas** — a única régua que
  compara faixa aprovada com faixa negada na mesma coluna.
- O documento cita o canto duro em toda projeção (volume, inadimplência, ROI), e diz com todas as
  letras que o ROI adverso de 14,8% fica abaixo dos 15% pedidos.

**Pendências**
- `reports/`: **relatório do modelo** (capítulos 01-05). É o que sobrou do desafio.
- No `.docx`, faltam dois campos que o script não sabe: **número do grupo** e os **três nomes**
  da seção 8. Marcados com `___`.
- Fragilidade que sobrevive à entrega: PD 40% acima da prevista quebra a inadimplência nos
  cenários central e pessimista (o otimista aguenta). Sem dado para medir o nível em mar aberto.

**Próximo passo**
Relatório do modelo em `reports/`, derivado dos capítulos 01-05, pelo mesmo `relatorios.py`.
**5 dias** até 25/09/2026 23h59.

---

## 2026-09-19 (noite) — `submissoes.py` + capítulo 08: **as duas entregas estão prontas**

**Construído**
- `src/submissoes.py` — gera os dois CSVs, faz 30 conferências relendo os arquivos do disco e
  roda um autoteste que estraga o arquivo de 9 formas para provar que as checagens mordem.
  `docs/08-submissoes.md`. 1 entrada nova em `aprendizado.md` (23 no total).
- `entregaveis/submissao_modelo.csv` (3.000 linhas) e `entregaveis/submissao_politica.csv`
  (5.000). Byte a byte idênticos entre execuções. `artefatos/submissoes.json`.

**O que vai ser entregue**
- Modelo: PD da Base B, média 0,0793, de 0,0188 a 0,7791, 2.954 valores distintos.
- Política: 2.642 APROVAR / 2.358 NEGAR (52,8%). Faixas 5-10 aprovadas, taxa de 2,27% (faixa 10)
  a 2,82% (faixa 5), entrada mínima de 21% nas faixas 5 e 6, prazo sempre o desejado.

**Decisões fechadas**
- **PD publicada = a do enquadramento** (condições pedidas), não a de oferta. É a única que faz
  `faixa(pd)` reproduzir `score_1a10` a partir do próprio CSV — 10 pontos de coerência.
  `tabela_politica.csv` passou a publicar as duas colunas: `pd_publicada` e `pd_precificada`.
- **6 casas decimais na PD**, não as 4 do exemplo. Não por AuROC (4 casas custam 0,00002, que é
  ruído), e sim porque a 4 casas 19 das 5.000 propostas trocam de faixa. A 6, zero.
- **Linha NEGAR sai com taxa, prazo e entrada vazios**, como o exemplo. Exigiu `Int64` no prazo
  para não gravar `48.0` nas aprovadas.
- **A conferência relê o arquivo do disco**, nunca o DataFrame que o gerou — BOM, índice vazado e
  `48.0` não existem no objeto de origem.

**Erros corrigidos** (em `docs/08-submissoes.md`)
- Ia justificar as 6 casas com um ganho de AuROC que a medição nega. Decisão certa, razão errada.
- Tabela da política e submissão publicavam PDs diferentes para a mesma faixa (6,93% x 7,47%),
  sem nenhuma checagem que notasse. Descoberto por acaso, comparando duas saídas impressas.
- Cabeçalho errado abortava em `KeyError` — achado pelo autoteste, não pelas 30 checagens.
- Heredoc corrompeu `chr(10)` e `"﻿"` de novo, pela quarta vez. Usar a ferramenta Write.

**Pendências** — o que falta do desafio
- `reports/`: **documento de política** (capítulos 06-07, no template
  `entregaveis/template_documento_politica.docx`) e **relatório do modelo** (capítulos 01-05).
  É o que sobrou, e é o que fecha os 20 pontos de defesa.
- Fragilidade que sobrevive à submissão: **PD 40% acima da prevista quebra o guardrail de
  inadimplência em qualquer cenário de aceite.** Sem dado para medir o nível em mar aberto.
- Projeto ainda não é repositório git.

**Próximo passo**
Documento de política em `reports/`, derivado do capítulo 07 e recortado para o `.docx` do
desafio. Depois o relatório do modelo. **6 dias** até 25/09/2026 23h59.

---

## 2026-09-19 — `politica.py` + capítulo 07

**Construído**
- `src/politica.py` — modelo de aceite, seleção adversa, preço por bisseção, grade de 384 regras,
  teste de estresse e os quatro guardrails (seções 1 a 7). `docs/07-politica.md`.
- `artefatos/politica_base_c.csv` (5.000 ofertas), `tabela_politica.csv` (10 faixas), `politica.json`.
  3 entradas novas em `aprendizado.md` (22 no total).

**A política escolhida** — `corte>=5 alvo=15%+4% entrada<7/0 prazo<0:60m`
- Aprova faixas 5-10 (52,8%). Taxa de **2,27% a 2,82% a.m.** (teto de CET é 3,5%). Entrada mínima
  de 21% nas faixas 5 e 6; nas demais vale a do cliente. **Prazo sempre igual ao desejado.**
- Central: ROI **15,7%**, volume R$ 67,4 mi, inadimplência 5,93%, aceite médio 70,7%.
- Canto duro (aceite pessimista + PD x1,2): ROI 14,8%, volume R$ 42,8 mi, inadimplência 7,67%,
  folga mínima 4,2%. Todos os guardrails cumpridos.

**Decisões fechadas**
- **Nunca alongar prazo.** A fórmula de ROI premia prazo longo duas vezes e cobra zero pelo risco
  (PD é de 12m e não é anualizada). Base A: default 6,44% em 24m contra 11,62% em 60m. E o salto
  é em parte composição — quem pede 60m ganha 20% menos.
- **Preço resolvido por bisseção** sobre o alvo de ROI, com o laço preço-risco do capítulo 06
  dentro. Inclinação de +4 p.p. de alvo da faixa 10 para a 1: rende 0,83 p.p. de ROI, custa
  R$ 2,2 mi de volume, quase não mexe na inadimplência.
- **Entrada mínima de 21%**, não 20% — a fronteira de LTV é de limite inferior fechado (cap. 06).
- **Escolha pelo canto duro**, não pelo cenário central. Das 384 regras, 22 sobrevivem e 10 têm
  4% de folga. O máximo da grade dá 21,6% de ROI com −53% de folga; a conta de indiferença exige
  q > 45% de chance de o guardrail segurar para compensar. Não chega perto.
- **Faixa 1 fica resolvida** (pendência do cap. 06): nem no teto de CET ela fecha — 9,4% a.a.
  O motivo é o `(1 − PD)` dos juros, não a perda comer a taxa. Faixas 1 e 2 não têm preço;
  faixas 3 e 4 têm preço e são negadas pelo guardrail de inadimplência do portfólio.
- **CET = taxa efetiva mensal** (não há tarifa, seguro nem IOF nas bases).

**Pendências**
- **Nível da PD na Base C continua aberto e é a maior fragilidade.** Com PD 40% acima da prevista
  o guardrail de inadimplência quebra em qualquer cenário de aceite. Não há dado para identificar
  o nível; a política foi construída com folga em vez de correção.
- O modelo de aceite é uma construção nossa: não existe uma só proposta recusada por cliente nas
  três bases. Única âncora é que o piso de R$ 40 mi só derruba a solução degenerada a partir do
  cenário central — inferência fraca, registrada como tal.
- Projeto ainda não é repositório git.

**Erros corrigidos no caminho** (todos em `docs/07-politica.md`, seção "O que deu errado")
- Alvo de ROI congelado antes da busca (24%) colapsou a escada de preço no teto de CET.
- Veredito "cabe/não cabe" testava a mediana da taxa saturada em vez do ROI no teto — quebrou
  monotonicidade entre faixas adjacentes, que foi o sintoma que denunciou.
- Frase de fechamento afirmava "acima de 15% nos dois" com 14,8% no canto duro. Texto em
  português não quebra teste; passou a ser derivado dos valores.

**Próximo passo**
`src/submissoes.py` + `docs/08`: gerar `submissao_modelo.csv` (Base B, 3.000 linhas) e
`submissao_politica.csv` (Base C, 5.000 linhas) no formato exato, conferir colunas e ordem, e
garantir que a tabela de faixas do documento bate linha a linha com a submissão (10 pontos de
coerência). Depois o documento de política em `reports/`. **6 dias** até 25/09/2026 23h59.

---

## 2026-09-14 — `risco.py` + capítulo 06

**Construído**
- `src/risco.py` — lookups de EAD/LGD, fórmula fechada do EAD, ajuste de avalista, perda esperada e
  auditoria dos parâmetros contra os realizados (8 seções). `docs/06-risco.md`.
- `artefatos/perda_esperada_base_c.csv` (5.000 linhas) + `risco.json`. 3 entradas novas em
  `aprendizado.md` (19 no total).

**Números novos**
- Fórmula do EAD reconstruída: `saldo Price(m−3) + 3 parcelas`. Reproduz `ead_realizado` com erro
  máximo de **meio centavo** nos 826 defaults.
- Fronteira de LTV: **limite inferior fechado** (`até 60%` = `ltv < 0,60`). Erro nas 20 células cai
  de 0,00338 para 0,00048. LTV de exatamente 80% cai na faixa **pior**.
- Fator de EAD a 48 meses: 1,0320 a 1,59% a.m. (= lookup) → **1,0941 a 3,5% a.m.**, +6,0%.
- Avalista: efeito bruto −0,061, **dentro da célula −0,079** (IC [−0,101; −0,057], n=163). Tabela já
  embute 19,7% de avalistas. Base C tem 25,3%, Base A 16,0%.
- Cadeia na Base A: PD 1,0019, EAD 1,0003, LGD 1,0146, total **1,0123**. Perda realizada 5,50% do
  volume (R$ 19,06 mi sobre R$ 346,7 mi).
- Base C sem política: perda esperada **10,31% do volume**. Faixa 1: 32,7% do volume = 2,73% a.m. só
  de perda, contra teto de CET de 3,50%.

**Decisões fechadas**
- EAD pela **fórmula fechada avaliada na taxa ofertada**, não pelo lookup congelado em 1,59% a.m.
  A coluna de LTV do lookup é ruído (corr −0,896 com o mês médio de default da célula).
- LGD = `tabela − 0,079 × (avalista − 0,197)`. Zera o resíduo nos dois grupos; a regra literal deixa
  +0,016 sem provisão em 84% da carteira. `lgd(..., oficial=True)` reproduz a literal.
- EAD/LGD **não** são modelados, mesmo com 826 realizados — o enunciado os declara dados.
- Horizonte de 12 meses, sem trazer a perda a valor presente (a receita também não é descontada).

**Pendências**
- Faixa 1 confirmada como **decisão de regra, não de preço** (não cabe no CET). Falta escrever a
  regra: negar, ou exigir entrada que a mova de faixa.
- Nível da PD na Base C (queda entre safras vs viés de aprovados) continua aberto — capítulo 07.
- Volume de R$ 40 mi vs curva de aceite; convenção de CET (efetivo x nominal); projeto ainda não é
  repositório git.

**Armadilha de ferramenta** (custou três correções): `\n` dentro de heredoc multilinha no Bash deste
ambiente chega ao Python como quebra de linha real → `SyntaxError: unterminated string literal`.
Editar `.py` por heredoc só sem escapes; se precisar, monte com `chr(92) + "n"` ou use o Write.

**Próximo passo**
`src/politica.py` + `docs/07`: alavancas (taxa, prazo, entrada), guardrails, simulação de aceite e
ROI. Depois submissões + `docs/08`. **11 dias** até 25/09/2026 23h59.

---

## 2026-09-13 (noite) — `score.py` + capítulo 05

**Construído**
- `src/score.py` — faixas 1-10 com cortes congelados, PD out-of-fold cacheada, testes de
  monotonicidade, inversão material, pares indistinguíveis e PSI. `--refazer` recalcula os cortes.
- `notebooks/03-decisoes-score.py` — cinco estratégias de corte comparadas na mesma régua.
- `docs/05-score.md`. Três entradas novas em `aprendizado.md` (16 no total).
- `notebooks/04-modelagem.ipynb` + `gerar_notebook_modelagem.py` — seis figuras dos cap. 04-05
  (dumbbell treino×OOT, ROC, calibração, faixas com IC 95%, perfil A/B/C, guardrail acumulado).
  Decidido **não** converter `02-decisoes-features.py` e `03-decisoes-score.py` em `.ipynb`: as
  tabelas deles já estão na `docs/`, e notebook guarda saída dentro do arquivo — envelhece calado.
  Paleta: vermelho do guia reprovado contra o laranja (ΔE 7,1); verde `#1f9e6e` no lugar.

**Números novos**
- Cortes (PD ascendente): `0,0369 0,0448 0,0542 0,0663 0,0839 0,1067 0,1428 0,2096 0,3017`.
  Percentis 20/36/50/62/72/80/87/93/97 da PD out-of-fold — faixas grandes no risco baixo.
- Faixa 1: PD observada **42,0%** · faixa 10: **3,34%** — separação de 12,6x. rho −0,988,
  1 inversão de direção, **nenhuma inversão material**.
- **AuROC out-of-fold 0,7326** (terceira medição independente; encadeada 0,7226, OOT 0,7434).
  Custo do agrupamento em 10 faixas: **0,0029**.
- **PSI A→C = 0,473** (população trocada); A→B = 0,006, entre safras de A = 0,002–0,005.
- Base C: faixas 8-10 somam **30,4%** — abaixo do guardrail de 35%. Descer até a faixa 7 dá 38,0%.

**Decisões fechadas**
- Cortes saem da PD **out-of-fold**, nunca de dentro da amostra (lá a faixa 10 promete 0,6% e
  entrega 3,7%). Cortes são **números fixos**, não quantis recalculados por base — senão o PSI mede
  zero justamente quando a população troca.
- Faixas **desiguais e progressivas**, não decis: com decis a faixa 10 quebrava mais que a 9.
- PD representativa da faixa = **média prevista na população decidida** (Base C), não a observada
  em A.
- Só 2 dos 9 pares de faixas vizinhas se separam com 95% de confiança → **a política precifica
  grupos de faixas, não dez preços distintos**.

**Pendências**
- Nível da PD na Base C: duas derivas opostas (queda entre safras vs viés de aprovados) continuam
  sem resolução — é decisão do capítulo 07.
- Faixa 1 da Base C (713 propostas, PD prevista 43,1%) é extrapolação, não medição. Tratar por
  regra (negar / exigir entrada), não por preço.
- Volume de R$ 40 mi vs curva de aceite; convenção de CET (efetivo x nominal); projeto ainda não é
  repositório git.


**Próximo passo**
`src/risco.py` (lookups EAD/LGD, ajuste de avalista −0,061, perda esperada) + `docs/06`. Depois
`politica.py` + `docs/07`, submissões + `docs/08`. **12 dias** até 25/09/2026 23h59.

---

## 2026-09-13 — `features.py` + `modelo.py`, capítulos 03 e 04

**Construído**
- `src/features.py` — matriz canônica, guarda antivazamento, `parcela_price()`, `preparar_aplicacao()`
  (reconstrói `comprometimento_renda` na Base C por Price), dois pré-processadores.
- `src/modelo.py` — busca de hiperparâmetros por CV no treino, 5 candidatos, calibração,
  importância por permutação, `--poda` (validação temporal encadeada), modelo final serializado.
- `notebooks/02-decisoes-features.py` — as cinco tabelas do capítulo 03, reprodutíveis.
- `docs/03-features.md`, `docs/04-modelo.md`. Quatro entradas novas em `aprendizado.md`.

**Números novos**
- **AuROC OOT 0,7410** (HistGB regularizado) → **0,7434 calibrado**. Gini 0,482, KS 0,376.
  Treino 0,8117: queda de 0,07, contra 0,29 do HistGB sem poda.
- Modelo final em toda a Base A: PD média 0,0830 (observada 0,0826), faixa 0,0156–0,8741.
- **PD média prevista na Base C: 15,53%** — quase o dobro de A (8,30%) e B (7,93%). 30,1% de C
  acima de 20% de PD.
- **PD cai safra a safra**: 9,57% (2023-S1) → 6,51% (2024-S2). B é 2025-S1, C é 2025-S2.
- Teto de comprometimento no treino **0,4493** com 0% acima de 45% — terceiro corte da política
  antiga. 11,3% de C o estoura; com prazo 60m + entrada 30%, só 66 das 566 continuam fora.

**Decisões fechadas**
- `ano_modelo` **removido** (estava decidido em `docs/02` desde ontem e nunca chegou ao código).
  `CANDIDATAS` (18, exploração) agora é distinto de `FEATURES` (17, modelo).
- Zero variáveis derivadas: as 7 testadas não superam o desvio da validação.
- Calibração **sigmoide (Platt)**, não isotônica — isotônica devolvia PD = 1,0000.
- Nenhuma outra poda: ganho no OOT de 2024 não se reproduz em janelas independentes.
- Treino usa a parcela contratada (não a reconstruída), porque a Base B também traz a contratada.
- **Grid search agora roda para os 4 candidatos ajustáveis** (149 combinações), não só o vencedor —
  lacuna apontada pela comparação com o prompt do Vini. Corrigido: árvore 0,6777 -> 0,7044 e
  Random Forest 0,7312 -> **0,7353** no OOT. HistGB regularizado segue vencendo (0,7410), mas a
  margem sobre a floresta é 0,0057 — decide o Brier, o KS e a queda treino->teste (0,07 vs 0,19).

**Pendências** (sem mudança desde ontem, mais uma)
- Sem git. Região sem suporte ainda sem regra. Piso de R$ 40 mi vs aceite. Convenção do CET.
- **Nova:** deriva de safra (superestima) e viés de aprovados (subestima) empurram o nível da PD
  em sentidos opostos na Base C. Decidir o nível é trabalho da política, com os dois medidos.
- **Nova:** não há mais partição intocada na Base A — 2024 foi consultado muitas vezes. O 0,7434 é
  otimista por exposição. Reportar **faixa 0,72-0,74** (encadeada 0,7226 subestima por treinar com
  menos dados; OOT 0,7434 superestima por contaminação). Não dá para consertar; dá para declarar.

**Próximo passo**
- `src/score.py` (faixas 1-10, reusando `src/exploracao.py`) + `docs/05`. Depois `risco.py`.
- **12 dias** até 25/09/2026 23h59.

## 2026-09-12 — Estudo dos 3 materiais, `src/dados.py`, `src/exploracao.py` e EDA dirigida

Primeira sessão de trabalho. Materiais 01, 02 e 03 estudados **contra as bases**, não em abstrato;
oito entradas em `aprendizado.md` e dois capítulos em `docs/` (01-dados, 02-exploracao).

**Números que orientam tudo**
- PD 8,26% | perda 5,50% do volume | fator EAD 1,0288 | LGD 69,6% | ROI histórico **9,56% a.a.**
- Conselho exige **ROI > 15% a.a.** — a meta é 57% acima do que a operação entrega hoje.
- **Teto honesto de AuROC ≈ 0,74** (HistGB regularizado, OOT 2022-23 → 2024). Sinal fraco e
  distribuído: maior IV é 0,173, total 0,99. Não há nada escondido esperando ser achado.
- **PD de break-even = 46%.** Quem obriga a negar é o guardrail de 8%, não a economia.
- **39,5% da Base C (1.976 propostas) está fora do domínio de treino.** Política de 2022 recuperada
  dos dados: `score_bureau >= 460 E qtd_restricoes_ativas <= 2`. É o maior risco técnico do desafio.

**Construído**
- `CLAUDE.md`: seção de documentação didática (`docs/`), fronteira de 3 colunas com `memory.md` e
  `aprendizado.md`, capítulos numerados por etapa do pipeline.
- `src/dados.py` — carga, auditoria, `mapear_base_c()`, guarda antivazamento com a lista de proibidas
  lida do dicionário. `src/exploracao.py` — binning/WoE/IV/PSI (será reusado em `score.py`).
- `notebooks/01-exploracao.py` (texto) e `gerar_notebook.py` → `01-exploracao.ipynb` (narrado, 5
  gráficos). Notebook é **gerado**, nunca editado à mão.
- `matplotlib` 3.11.2 instalado no Python global.

**Decisões fechadas**
- Modelo: gradient boosting regularizado, seed 42; logística como benchmark interpretável.
- **18 features** (`FEATURES` em `dados.py`). Fora: `taxa_juros_am` e `parcela_mensal` (decisão nossa
  em C, e pioram o AuROC isoladas) e `ano_modelo` (IV 0,013 + PSI 1,394).
- `comprometimento_renda` fica, recalculado em C em duas passadas (desejado → oferta).
- Sem indicador de ausência — hipótese testada e descartada (razões 1,05x a 1,15x).
- Sem API/endpoint: vale 0 ponto.

**Pendências**
- Sem git.
- **Regra de política para a região sem suporte** (3+ restrições, score < 460) — ainda sem desenho.
- Piso de R$ 40 mi contratados pode ser mais restritivo que os 35% de aprovação; validar contra aceite.
- Convenção do CET (efetiva/nominal) antes de precificar.
- Calibração da PD precisa ser validada — não vale nota direta, mas a política usa a magnitude.

**Próximo passo**
- `src/features.py` + `src/modelo.py`, com `docs/03` e `docs/04` no mesmo turno.
- **13 dias** até 25/09/2026 23h59.

## 2026-09-12 — Setup do repositório

- Criado `CLAUDE.md` a partir da leitura dos três materiais de mentoria, do enunciado AutoCred, do dicionário
  de dados e da planilha de parâmetros EAD/LGD.
- Acoplados ao `CLAUDE.md`: perfil operacional, regra de data dinâmica, estrutura de pastas proposta e as
  convenções de `memory.md` e `aprendizado.md`.
- Repositório ainda sem código, sem git e sem venv.

**Pendências**
- Confirmar (ou ajustar) a estrutura de pastas proposta em `CLAUDE.md` antes de escrever a primeira linha de código.
- Decidir se o projeto vira repositório git — hoje não é.
- Desafio lançado em 12/09/2026, submissão em 25/09/2026 23h59: **13 dias**.

**Próximo passo**
- Auditoria da Base A: alvo, safras, duplicidades, maturação e faltantes, antes de qualquer modelagem.
