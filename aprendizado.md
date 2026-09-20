# aprendizado.md — trilha de estudo

Material de estudo, não log de trabalho. Alvo: sustentar diante do conselho **por que** cada decisão foi
tomada (20 pts de Defesa). Teste de toda entrada: *se perguntarem isso, respondo sem abrir o notebook?*

Ordem **cronológica** — entrada nova no fim. Formato: `## AAAA-MM-DD — título`, linha `Conceitos:` para
busca por `grep`, corpo de até ~40 linhas, fórmula sempre com exemplo numérico das bases.
Sessão sem aprendizado real não gera entrada.

---

## 2026-09-12 — A perda esperada decomposta na Base A: de onde vem cada fator

Conceitos: perda esperada, PD, EAD, LGD, tabela Price, workout, avalista, média ponderada, decomposição de perda

A identidade `Perda = PD × EAD × LGD` do material 01 não é didática — ela **fecha na Base A**, e fecha de um
jeito específico que precisa ser dito corretamente diante do conselho.

Perda realizada total: R$ 19.057.787 sobre R$ 346.684.813 financiados = **5,50% do volume**. Mas
`PD_média × fator_EAD_médio × LGD_média` = 0,0826 × 1,0288 × 0,6958 = **5,91%**. Os 0,41 p.p. de diferença
não são erro: produto de médias ≠ média de produtos. A decomposição que fecha exata é ponderada por volume:

```
0,0775 (volume em default / volume total) × 1,0292 (ΣEAD/Σfinanciado) × 0,6889 (LGD ponderada por EAD) = 0,0550
```

Repare que a PD em *volume* (7,75%) é menor que a PD em *contratos* (8,26%): o ticket médio de quem dá
default é R$ 32.538 contra R$ 34.668 da carteira. Inadimplência é mais frequente em contrato pequeno.
Métrica de contagem e métrica de volume não são intercambiáveis — o guardrail de inadimplência do desafio
(≤ 8%) é de **contratos fechados**, o de volume (≥ R$ 40 mi) é de reais. São dois cortes diferentes.

Por que `Fator_EAD` passa de 1: EAD = saldo Price no mês do default + as 3 parcelas vencidas que
caracterizam o atraso de 90 dias. Em contrato de 60 meses com default no mês 6, quase nada foi amortizado e
as 3 parcelas empurram a exposição acima do financiado — o fator vai a 1,042. Em 24 meses com default
tardio, a amortização domina e o fator cai a 0,980. Observado na Base A: média 1,0288, faixa 0,816–1,151.

**Achado com consequência.** A tabela oficial de LGD é a média **de todos** os defaults, avalistas
incluídos — reproduzi célula a célula (3-5 anos × 70-80%: 0,704 na tabela, 0,704 no cálculo bruto). Logo o
desconto do avalista já está diluído dentro dela, e aplicar `-0,061` por cima **subestima a LGD em ~1,2 p.p.**
(19,7% dos defaults têm avalista × 0,061). O baseline sem avalista é 0,717 nessa mesma célula.
Ainda assim, **usamos a regra oficial na submissão**: o simulador da apuração roda com ela, e divergir
desincroniza nossa conta da conta que vale nota. O ajuste vale para a economia interna e para a defesa —
não para o arquivo entregue.

## 2026-09-12 — A variável mais preditiva da base é a que está proibida

Conceitos: vazamento, data leakage, disponível na concessão, viés de aprovados, reject inference, suporte amostral

`qtd_parcelas_em_atraso_12m` sozinha dá **AuROC 0,964** na Base A. `score_bureau` sozinho dá **0,608**.
A relação é quase determinística: 0 parcelas em atraso → 0,17% de default; 10 ou mais → 100%. Não é
predição, é a mesma informação com outro nome — o default 90/12 *é* ter acumulado atraso no período.
A causa é temporal, não estatística: a coluna conta atrasos dos **12 meses seguintes** à originação, e o
alvo é ter chegado a 90 dias de atraso nesses mesmos 12 meses. Três parcelas em aberto *são* 90 dias —
a "preditora" é um pedaço da definição do alvo. Na Base A, `atraso >= 3` acerta 688 dos 826 defaults
contra 409 falsos positivos; na concessão, esse número ainda não existe.

**O que torna a armadilha perfeita:** a coluna está nas três bases, então o `fit` roda sem erro. Mas em
B e C ela vem **constante zero** (3.000 e 5.000 linhas, zero nulos) — é o valor de uma proposta que ainda
não pagou nada. O modelo aprendeu a ler o mundo por ela e, quando ela é zero para todos, responde "todos
são ótimos". Simulei zerando a coluna na safra de 2024:

| HistGB com a variável proibida | AuROC | PD média prevista |
|---|---:|---:|
| OOT 2024, coluna real | 0,9603 | 7,42% |
| OOT 2024, coluna = 0 (o que B entrega) | **0,5888** | **0,17%** |
| *(observado em 2024)* | — | *7,18%* |

Ou seja: o modelo de AuROC 0,96 entrega **0,59 na submissão** — pior que a logística honesta (0,656) — e
precifica a carteira inteira a 0,17% de PD, 42× abaixo do real. Em política isso é aprovar tudo.
Alternativa descartada: "usar só um pouquinho, como feature secundária" — vazamento não tem dosagem,
a variável entra ou não entra.

Regra de detecção que fica: antes de usar uma coluna, pergunte **quando ela é preenchida**, não quanto
ela prediz. Se a resposta for "depois da decisão", é alvo disfarçado por melhor que seja o IV — e
conferir a distribuição dela na base de aplicação denuncia o caso em dez segundos.

O problema irmão, e mais difícil: A e B só têm **aprovados** pela política antiga; C é mar aberto.

| Corte | Base A (aprovados) | Base C (propostas) |
|---|---:|---:|
| `score_bureau` < 500 | 8,7% | **36,1%** |
| alguma restrição ativa | 47,6% | 66,2% |
| LTV > 90% | 11,9% | 20,9% |
| score médio | 645 | 549 |

Um terço da Base C vive numa região onde temos ~870 contratos históricos, todos eles selecionados por
terem passado num filtro que já os considerava aceitáveis. A PD estimada ali é extrapolação, não
interpolação — e extrapolação otimista, porque o histórico daquela faixa é o dos sobreviventes do filtro.
Consequência prática: qualquer corte de score calibrado só em A tende a **aprovar demais** no fundo da
distribuição de C.

## 2026-09-12 — O teto honesto de AuROC nesta base, e o que o split out-of-time revela

Conceitos: split out-of-time, estratificação, overfit, concept drift, AuROC, Gini, KS, generalização, seed

Rodei a validação do material 02 na Base A com as 20 variáveis legítimas (seed 42, treino 2022-23 = 6.670
contratos, teste 2024 = 3.330). Números, não impressões:

> **Nota de 13/09:** esta tabela é o experimento exploratório com 20 variáveis e sem busca de
> hiperparâmetros nos concorrentes. A tabela oficial do modelo está em `docs/04-modelo.md` — 17
> variáveis, as quatro grades buscadas, HistGB regularizado em 0,7410. As três leituras abaixo
> continuam valendo; os números foram superados. Ver também a entrada de 13/09 sobre comparação
> arranjada.

| Modelo | AUC treino | AUC teste (OOT) | Queda | Gini | KS |
|---|---:|---:|---:|---:|---:|
| Regressão logística | 0,6691 | 0,6560 | +0,013 | 0,312 | 0,252 |
| Árvore prof=2 | 0,6253 | 0,6104 | +0,015 | 0,221 | 0,208 |
| Random Forest sem poda | **1,0000** | 0,6957 | +0,304 | 0,391 | 0,338 |
| HistGB default | 0,9983 | 0,7076 | +0,291 | 0,415 | 0,320 |
| **HistGB regularizado** | 0,8788 | **0,7390** | +0,140 | 0,478 | 0,369 |
| *(com a variável proibida)* | *0,9705* | *0,9548* | — | *0,910* | *0,795* |

Três leituras que valem defesa:

**1. O teto é ~0,74, não 0,85.** Na escala do Vini (0,60 útil / 0,70 bom / 0,80-0,85 excelente), estamos em
"bom". Quem apresentar 0,85 nesta base sem explicar como chegou lá provavelmente vazou algo — e o modelo com
`qtd_parcelas_em_atraso_12m` dá 0,9548, batendo exatamente na regra "acima de 0,90, investigue a base".
A regra do mentor funciona como detector de vazamento, não só como régua de qualidade.

**2. O overfit do Random Forest é real mas não é o vilão que parece.** Treino 1,0000 é decorar cliente a
cliente, e ainda assim o teste (0,6957) supera a logística (0,6560). Ordenação sobrevive à decoreba. Mesmo
assim regularizamos: o ganho real veio da poda (0,7076 → 0,7390 com `max_leaf_nodes=8, lr=0,05, l2=1`), e
apresentar treino=1,0000 ao conselho é entregar de graça a pergunta mais fácil de fazer.
Alternativa descartada: logística como modelo final. Perde 0,083 de AUC — cara demais por interpretabilidade
que podemos recuperar com a tabela de faixas e a árvore de profundidade 2.

**3. Não há concept drift dentro da Base A.** Split aleatório estratificado e split out-of-time dão
praticamente o mesmo resultado (LR 0,6549 vs 0,6560; GB 0,7103 vs 0,7076 — deltas de ±0,003). As safras
2022-2024 são o mesmo regime. **Cuidado com a conclusão fácil:** isso não quer dizer que estamos seguros,
quer dizer que o OOT dentro de A não mede o nosso risco. O nosso drift é de *população* (A→C), não de
*conceito* no tempo — e nenhum split dentro da Base A o captura.

Árvore de profundidade 2, como política mínima interpretável (PD observada por folha):
`restrições ≤ 1` + `idade > 28` → 6,3% | `restrições ≥ 2` + `score ≤ 519` → **28,2%**. Duas regras,
4,5x de separação. É o piso contra o qual o modelo sofisticado tem de provar que vale a complexidade.

## 2026-09-12 — A matriz de custo do AutoCred: a PD de break-even é 46%, não 8%

Conceitos: matriz de custo, limiar, ponto de operação, break-even, guardrail, restrição ativa, ROI

O material 02 manda transformar limiar em problema econômico: dá valor a cada quadrante e escolhe o corte que
maximiza resultado. Fiz isso com os parâmetros oficiais e o resultado reorienta a política inteira.

Contrato médio da Base A: R$ 34.668 financiados, 1,589% a.m., 44 meses.

```
Ganho se paga      = 1.101 × 44 − 34.668           = R$ 14.140
Perda se dá default (mês esperado 6,89, da Distribuicao_Mes_Default):
  recebe 6,89 parcelas                              = R$  7.586
  perde EAD × LGD = 1,03 × 34.668 × 0,70            = R$ 25.016
  resultado líquido                                 = R$ −16.370
PD de break-even = 14.140 / (14.140 + 16.370)       = 46,3%
```

A perda de um default vale **1,77x** o juro de um contrato bom — mas o contrato bom roda 44 meses e o default
morre no mês 7, e a razão 1 mau : 6 bons já se paga. Distribuição do break-even na base: mediana 46,3%,
p10 = 35,1%, mínimo 22,3%. Cresce com prazo (24m: 38,1% → 60m: 53,8%) e cai com idade do veículo
(0-2 anos: 54,4% → 9+ anos: 38,7%), que é a LGD entrando na conta.

**A consequência é contraintuitiva e é o achado da sessão.** A pior folha da árvore tem PD de 28,2% — abaixo
do break-even. Pelo critério de valor esperado puro, **quase nada na Base C deveria ser negado**. Subir o
preço só afrouxa mais: a 3,5% a.m. (teto do CET) o break-even vai a 71,7%.

Então o que obriga a ser seletivo não é a economia, é o **guardrail de inadimplência ≤ 8%** — restrição
regulatória imposta pelo desafio, não consequência da conta. Negar proposta lucrativa para caber em 8% é
destruir valor por imposição, e é assim que tem de ser apresentado ao conselho: não "negamos porque dá
prejuízo", e sim "negamos porque o mandato de risco é 8%".

Segunda restrição, que puxa no sentido oposto: R$ 40 mi **contratados**. Ticket médio desejado em C é
R$ 33.411. Com aceite de 50% precisamos aprovar 48% das 5.000 propostas — bem acima do piso de 35%. Com
aceite de 30%, 80%. Preço alto derruba aceite e pode estourar o piso de volume pelo lado de baixo.

*Limitação a declarar na defesa:* essa conta não desconta custo de funding nem traz os fluxos a valor
presente — assim como a fórmula de ROI do próprio desafio. O break-even real de um banco seria bem menor.

## 2026-09-12 — Por que a taxa de juros ficou fora do modelo

Conceitos: endogeneidade, variável de decisão, escopo de features, comprometimento de renda, Base C

Pergunta provável do conselho: *"vocês tinham a taxa contratada de cada operação e não usaram?"*

Não usamos, por dois motivos independentes — e o segundo sozinho já bastaria.

**1. A Base C não tem essa coluna, e não tem por um bom motivo.** A e B descrevem contratos
*fechados*; C descreve *propostas*, com o que o cliente deseja (`ltv_desejado`,
`prazo_desejado_meses`). Nove colunas permitidas pelo dicionário somem em C, e `taxa_juros_am` é
uma delas — porque quem define a taxa somos nós, na política. Um modelo que dependa dela consegue
pontuar a Base B e **não consegue pontuar a Base C**, que é metade da nota.

**2. Medida isoladamente, ela piora o modelo.** Sobre o conjunto de 17 features (AuROC OOT 0,7245):

```
+ taxa_juros_am          -> 0,7155   (−0,0090)
+ parcela_mensal         -> 0,7171   (−0,0074)
+ comprometimento_renda  -> 0,7377   (+0,0132)
```

A taxa antiga isolada tem AuROC de 0,5654 e correlação de apenas −0,079 com o `score_bureau`. Ou
seja: a política de 2022 **quase não precificava risco** — cobrava taxa praticamente descolada do
perfil do cliente. Esse achado é munição de defesa por si só, porque confirma o diagnóstico do
conselho de que o problema está na concessão.

**Decisão:** 18 features. Alternativa descartada: o conjunto completo de 20, que dá 0,7390 — ganho
de 0,0013 de AuROC em troca de não conseguir aplicar a política. Custo irrisório, benefício enorme.

`comprometimento_renda` (parcela ÷ renda) fica, apesar de também não existir em C, porque é
*recalculável* a partir da oferta que fizermos. A circularidade aparente (PD → faixa → oferta →
parcela → comprometimento → PD) resolve-se em duas passadas determinísticas: pontua com o desejado,
enquadra na faixa, oferta, recalcula, decide.

## 2026-09-12 — O corte invisível da política antiga: 28% da Base C tem mais restrições que o treino viu

Conceitos: suporte amostral, inferência de rejeitados, extrapolação, árvores não extrapolam, PSI, WoE

A tabela de WoE de `qtd_restricoes_ativas` (2ª maior IV da base, 0,1328) termina no bin `2`:

| Restrições | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|---:|
| Base A | 52,4% | 32,6% | 15,0% | — | — | — |
| Base C | 33,8% | 24,1% | 14,0% | 8,7% | 5,7% | **13,7%** |

**As Bases A e B vão de 0 a 2 restrições. Só.** Isso não é coincidência: é a política antiga
impressa nos dados — a AutoCred **recusava automaticamente quem tinha 3 ou mais restrições**. O
corte não está escrito em nenhum material do desafio; foi deduzido do domínio da variável.

**1.404 propostas da Base C (28,1%) estão acima do máximo já visto.** PSI de 2,335 — "população
trocada" com folga.

Por que isso é pior do que parece: **modelos de árvore não extrapolam.** Um proponente com 5
restrições cai na mesma folha de um com 2 e recebe a mesma PD, ~16%. E 2 restrições já **triplicam**
a PD em relação a 1 (7,78% → 16,36%). Supor que 5 equivalem a 2 erra na direção perigosa: o modelo
**subestima** o risco de mais de um quarto da carteira que vamos decidir.

Não se resolve com modelagem melhor — não existe informação na base sobre quem tem 5 restrições.
A saída é **regra de política explícita** na região sem suporte, defendida como decisão de risco e
não como saída de modelo. Alternativa descartada: extrapolar a tendência (7,17% → 7,78% → 16,36%
→ projetar 3, 4 e 5). Seria inventar número com cara de evidência; a inclinação entre 1 e 2 não
autoriza nada sobre 5.

Como detectar isso de novo: comparar **min/max de cada variável** entre desenvolvimento e aplicação
antes de treinar. PSI pega o deslocamento, mas o domínio truncado é mais fácil de ver no min/max —
e é ele que quebra a extrapolação.

> Os 28,1% são só o corte de restrições. Aplicando o mesmo teste a todas as variáveis apareceu um
> segundo corte (`score_bureau >= 460`), e o perímetro combinado chega a **39,5%** — ver a entrada
> *"Duas regras da política antiga recuperadas do domínio das variáveis"*, mais abaixo.

## 2026-09-12 — Bin virou texto e a ordem se perdeu: o bug que não dá erro

Conceitos: binning, WoE, monotonicidade, categórica ordenada, erro silencioso

Na EDA, os bins numéricos saíam de `pd.cut(serie, bins=cortes).astype(str)`. O `groupby` então
ordenava os rótulos **como texto**: `"(1000.0, 1500.0]"` vem antes de `"(400.0, 450.0]"`.

Resultado: a monotonicidade de **todas** as variáveis numéricas foi medida na ordem errada. Sem
exceção, sem aviso, com números plausíveis na tela. Depois da correção:

```
renda_mensal_declarada   rho −0,68 → −0,90
tempo_emprego_meses      rho −0,52 → −0,77
valor_entrada            rho −0,27 → −0,65
qtd_restricoes_ativas    rho   NaN →  1,00
```

O que revelou o bug não foi conferência: foi `qtd_restricoes_ativas` devolver `rho` nulo, porque o
corte por quantil colapsa numa variável de 3 valores distintos. Um sintoma acidental, numa variável
diferente.

Correção: devolver `pd.Categorical(rotulos, categories=ordem + [AUSENTE], ordered=True)` em vez de
string.

**Heurística que fica:** em qualquer análise por faixa — WoE, PSI, tabela de safra, faixa de score —
o bin tem de carregar a ordem junto. Assim que o rótulo vira texto, a ordem morre. E como o
resultado continua parecendo razoável, esse erro atravessa revisão. Vale para a tabela de faixas
1-10 da submissão, onde ordem trocada custa os 10 pontos de coerência.

## 2026-09-12 — Duas regras da política antiga recuperadas do domínio das variáveis

Conceitos: suporte amostral, política implícita, min/max, reject inference, engenharia reversa de política

Ampliando o teste de domínio para todas as variáveis, apareceu uma segunda regra além do corte de
restrições já registrado:

| Variável | mín. treino | máx. treino | mín. Base C | % de C fora |
|---|---:|---:|---:|---:|
| `score_bureau` | **460** | 1000 | 0 | 27,7% |
| `qtd_restricoes_ativas` | 0 | **2** | 0 | 28,1% |
| `ltv` | 0,25 | 0,95 | 0,25 | 7,1% |

A Base A **não tem nenhum contrato com score abaixo de 460**, e a Base C desce até 0 num contínuo
(0, 10, 24, 42, 57…) — são scores reais, não código de ausência. A política de 2022, que nenhum
documento do desafio descreve, era:

```
score_bureau >= 460   E   qtd_restricoes_ativas <= 2
```

Somando o perímetro, **39,5% da Base C (1.976 de 5.000)** cai fora do domínio em ao menos uma
variável de crédito — bem mais que os 28,1% das restrições sozinhas.

**Heurística que fica:** política de crédito antiga deixa impressão digital no **min/max** das
variáveis, não na média nem no PSI. Antes de treinar qualquer modelo que será aplicado em
população diferente da de desenvolvimento, comparar domínio por domínio. Valor de corte que
aparece como mínimo exato e redondo (460) é regra, não acaso.

Isso também recalibra a leitura do IV: `ltv` com IV de 0,017 parecia inútil para risco de veículo.
Não é a variável que é fraca — é a amostra que foi truncada pela política, sobrando pouca variação
para medir. Em Base C, onde o LTV vai a 0,98, ela pode importar muito mais do que o IV histórico
sugere. Mais um motivo para não descartar variável só por IV baixo quando há viés de seleção.

## 2026-09-13 — O terceiro corte: 45% de comprometimento é regra, e é a única que dá para negociar

Conceitos: capacidade de pagamento, comprometimento de renda, domínio de treino, Tabela Price, alavanca de política, reestruturação de oferta

Com o `comprometimento_renda` finalmente calculável na Base C (reconstruído por Price), apareceu um
limite que os capítulos anteriores não podiam enxergar — a variável não existia lá.

| | treino 2022-23 | Base C (desejado) |
|---|---:|---:|
| acima de 40% da renda | 4,44% | 15,64% |
| **acima de 45%** | **0,00%** | **11,32%** |
| máximo observado | **0,4493** | 1,6286 |

Zero em 10.000 contratos não é acaso: a política antiga tinha teto de 45% de comprometimento.
Junto com `score_bureau >= 460` e `restrições <= 2`, os três cortes atingem **42,6% da Base C**
(2.130 propostas), contra 36,0% dos dois cortes anteriores sozinhos.

**A diferença que importa para a política.** Score de bureau e restrições ativas são atributos do
proponente — não há oferta que os mude. Comprometimento é consequência da *oferta*, e oferta é o
que nós controlamos:

| Condição oferecida às 566 propostas acima do teto | ainda acima de 44,9% |
|---|---:|
| condições desejadas pelo cliente | 566 |
| prazo esticado para 60 meses | 174 |
| prazo 60m + entrada mínima de 30% | **66** |

500 das 566 voltam ao domínio de treino sem relaxar risco — e com entrada maior o LTV cai, o que
reduz PD e LGD ao mesmo tempo. A leitura de mercado é a mesma: banco não nega por capacidade, ele
**reestrutura** — alonga prazo ou exige entrada até a parcela caber no bolso. Negar é o último
recurso, porque proposta negada não gera receita e proposta reestruturada gera.

**Heurística que fica:** ao mapear a região sem suporte histórico, separe os cortes em *atributo do
cliente* e *consequência da oferta*. Só o primeiro grupo é restrição de verdade; o segundo é
parâmetro de desenho disfarçado de restrição. Confundir os dois faz negar quem só precisava de
outro prazo.

Continua aberto: os 27,7% com score < 460 e os 28,1% com 3+ restrições — esses não têm alavanca, e
é lá que a política vai precisar de uma regra explícita e defensável.

## 2026-09-13 — Sete variáveis criadas, sete descartadas: quando o ganho é menor que o ruído

Conceitos: engenharia de atributos, validação cruzada, desvio padrão da métrica, seleção de variáveis, out-of-time, parcimônia

Criei sete razões plausíveis — entrada/renda, financiado/renda, bem/renda, score por restrição,
pressão de bureau (restrições + consultas), estabilidade no emprego (tempo/idade) e idade do veículo
ao fim do contrato — todas calculáveis na Base C. Nenhuma entrou no modelo.

| Conjunto | AuROC CV (5 dobras, treino) | ±dp | AuROC OOT 2024 |
|---|---:|---:|---:|
| 17 features | 0,7249 | 0,0197 | **0,7410** |
| melhor derivada (`idade_veiculo_no_fim`) | 0,7254 | 0,0211 | 0,7439 |
| todas as sete juntas | 0,7170 | 0,0196 | 0,7368 |

Seis das sete **pioram** a validação cruzada. A sétima melhora em **+0,0005** — um quarentavo do
desvio padrão da própria medida. Não é ganho, é o segundo decimal do ruído.

**O erro que isso evita** é o mais comum em competição: escolher variável olhando um número sem
olhar a incerteza dele. Com 6.670 linhas e 587 defaults na janela de treino, o desvio da AuROC entre
dobras é ~0,02. Qualquer diferença abaixo disso é indistinguível de sorte no sorteio das dobras. A
régua prática que fica: **ganho tem de superar o desvio padrão da validação, não o zero.**

Por que não havia nada a ganhar aqui já estava no capítulo 02: IV total 0,99, maior variável isolada
0,17. Sinal fraco e distribuído. Além disso, gradient boosting constrói interações sozinho; razões
manuais só ajudam onde a árvore não alcança — divisões entre variáveis —, e a única que realmente
paga (`comprometimento_renda` = parcela/renda, +0,0132) já estava na base desde o começo.

**Alternativa descartada:** manter as derivadas "porque não custam nada". Custam. Cada variável é
uma linha a justificar na defesa, uma a monitorar em produção e uma a calcular na Base C — onde
metade delas depende da renda, ausente em 7,9% das propostas. Parcimônia aqui não é estética, é
redução de superfície de falha.

## 2026-09-13 — A poda de variáveis que ganhava no teste e perdia em toda janela independente

Conceitos: seleção no conjunto de teste, importância por permutação, validação temporal encadeada, generalização, parcimônia enganosa

A importância por permutação no out-of-time dizia para cortar: `ltv` com contribuição **−0,0044**,
`valor_bem` **−0,0018**, sete variáveis em torno de zero. E o corte parecia confirmado — 7 variáveis
davam **0,7546** de AuROC em 2024 contra 0,7434 das 17.

Não podei, e a razão é a lição. O out-of-time de 2024 já tinha sido consultado muitas vezes ao longo
do projeto; escolher o conjunto de variáveis por ele é convertê-lo em conjunto de treino. Montei uma
validação temporal **encadeada** que nunca toca 2024:

| Conjunto | 2022→2023-S1 | 2022→2023 | 2022+23S1→2023-S2 | média | *OOT 2024* |
|---|---:|---:|---:|---:|---:|
| 17 variáveis | 0,7171 | 0,7228 | 0,7279 | **0,7226** | *0,7434* |
| 15 | 0,7142 | 0,7210 | 0,7299 | 0,7217 | *0,7486* |
| 11 | 0,7134 | 0,7200 | 0,7303 | 0,7212 | *0,7518* |
| 7 principais | 0,7205 | 0,7127 | 0,7149 | 0,7160 | ***0,7546*** |

As duas réguas discordam de ponta a ponta: **no OOT de 2024 a qualidade sobe monotonicamente
conforme se poda; nas janelas independentes, desce.** Os 0,011 de vantagem em 2024 eram
coincidência de janela — e teriam sido apresentados ao conselho como melhoria se a única régua
fosse aquela.

**Regra que fica:** quando um conjunto de validação já foi olhado várias vezes, ele não é mais
imparcial para decidir nada novo. Ou se reserva uma partição intocada desde o início, ou se constrói
uma validação independente (aqui, janelas temporais anteriores ao teste) para a decisão seguinte.
Importância por permutação medida no teste **sugere** hipótese; não a confirma.

Detalhe sobre importância negativa: `ltv` piorar o AuROC ao ser embaralhada significa que, naquela
janela, ela atrapalhava. Com IV de 0,017 e amostra truncada pela política antiga (cap. 02), isso é o
esperado — e não autoriza conclusão sobre a Base C, onde o LTV vai a 0,98 e a variável entra na
tabela oficial de EAD/LGD de qualquer jeito.

**Única remoção feita:** `ano_modelo`, e por motivo que não depende de métrica — contribuição zero
(sai e entra sem mudar o AuROC em nenhuma casa decimal) somada a **31,8% da Base C acima do máximo
do treino**, que vai só até 2022. Árvore não extrapola: fora do domínio, a variável só pode empurrar
a predição para a folha do extremo conhecido. Contribuição nula com domínio estourado é risco puro.

**Erro de processo, registrado:** essa remoção já estava decidida e escrita em `docs/02` na sessão
anterior e nunca chegou ao código. Foi a importância por permutação, medida por outro motivo, que
denunciou. Decisão documentada não é decisão implementada — e só o código sabe a diferença. Separei
`CANDIDATAS` (18, o que a exploração mede) de `FEATURES` (17, o que o modelo usa) para que a
divergência fique explícita.

## 2026-09-13 — AuROC não vê o nível da PD, e dois deslocamentos opostos escondidos nele

Conceitos: calibração, Platt, isotônica, Brier, deriva de safra, viés de aprovados, perda esperada, decil de risco

O AuROC é invariante a qualquer transformação monótona: um modelo que prevê 3% onde a realidade é 8%
tem exatamente o mesmo AuROC do modelo correto. Para os 40 pontos de Modelo isso não custa nada.
Para os 40 pontos de Política custa tudo, porque `Perda = PD × EAD × LGD` usa o número, não a ordem.

Medido no out-of-time: o modelo ordena bem (decil 1 com 1,50% observado, decil 10 com 23,42%) mas
superestima o risco nos decis bons — razão prevista/observada de 2,21 no decil 1 e 2,68 no decil 5.
A calibração em dobras internas do treino corrige a curva e, por agregar as cinco dobras, ainda
soma **+0,0024 de AuROC** (0,7410 → 0,7434).

**Sigmoide (Platt), não isotônica.** Empatam em discriminação (0,7436 vs 0,7437) e no Brier
(0,0616), então decide o extremo: a isotônica é uma escada e devolve `PD = 1,0000` para 2 contratos
da Base A. PD de exatamente 1 multiplicada por EAD e LGD dá perda esperada igual à exposição
inteira — número indefensável e que envenena o preço. A sigmoide para em 0,8556.

**O que a calibração não resolve — dois deslocamentos em sentidos opostos:**

| | evidência | direção do erro na Base C |
|---|---|---|
| Deriva de safra | PD cai de 9,57% (2023-S1) a **6,51%** (2024-S2); B é 2025-S1 e C é 2025-S2 | superestima |
| Viés de aprovados | PD média prevista: A 8,30%, B 7,93%, **C 15,53%** — 30,1% de C acima de 20% | subestima |

Calibrar na Base A inteira carrega o nível médio de 2022-2024 para safras onde o risco vinha
caindo. Ao mesmo tempo, a Base C é mar aberto: contém os perfis que a política antiga recusava, e o
modelo corretamente os pontua como muito piores — PD média quase o dobro da Base A.

**Eles não se cancelam automaticamente**, e tratar um sem o outro é pior que tratar nenhum: corrigir
só a deriva para baixo, num público já mais arriscado, é o caminho direto para estourar o guardrail
de 8% de inadimplência. A decisão de nível fica para a política, com os dois números medidos —
nunca com um ajuste "de sensibilidade" escolhido a olho.

## 2026-09-13 — Comparação arranjada: ajustar só o modelo favorito

Conceitos: grid search, comparação justa, baseline, random forest, gradient boosting, overfit, critério de desempate

A primeira versão da tabela de candidatos comparava um HistGB submetido a 54 combinações de busca
contra logística, árvore e random forest com os parâmetros que eu escolhi à mão. É luta arranjada:
o vencedor ganha por ter sido ajustado, não por ser melhor. A pergunta que expõe isso numa banca é
uma só — *"você otimizou o seu e não os deles?"*.

Corrigido: as quatro grades rodam na mesma janela, com a mesma validação cruzada e a mesma métrica
(149 combinações no total). O que mudou:

| Modelo | AuROC OOT antes | depois | AUC treino | queda |
|---|---:|---:|---:|---:|
| Árvore de decisão | 0,6777 | **0,7044** | 0,7351 | 0,031 |
| Random Forest | 0,7312 | **0,7353** | 0,9212 | 0,186 |
| Regressão logística | 0,6553 | 0,6521 | 0,6658 | 0,014 |
| HistGB regularizado | 0,7410 | 0,7410 | 0,8117 | 0,071 |

A conclusão sobrevive — o boosting continua vencendo — mas **a margem sobre a floresta caiu para
0,0057**, contra um desvio de validação de ~0,02. Ou seja: a escolha do modelo final **não é
estatisticamente decisiva**, e dizer que é seria repetir o erro da entrada anterior sobre poda.

**Como desempatar quando o AuROC empata.** Três critérios, em ordem de peso:

1. **Queda treino→teste**: 0,071 do boosting contra 0,186 da floresta. Entre modelos de desempenho
   igual, fica o que depende menos de ter decorado — porque a Base C é uma população diferente, e
   quem decorou o passado generaliza pior para o que nunca viu.
2. **Brier** (0,0616 contra 0,0619): mede o nível da PD, não só a ordem. É o que a política usa.
3. **KS** (0,376 contra 0,374): onde a separação é mais forte, que é onde o corte vai ficar.

**Heurística que fica:** baseline sem ajuste não é baseline, é espantalho. Ou todos os candidatos
passam pela mesma busca, ou a tabela não sustenta a frase "escolhemos o melhor modelo". E quando a
diferença cabe dentro do desvio da validação, o desempate tem de ser declarado explicitamente —
não escondido atrás da terceira casa decimal.

Achado lateral com valor de defesa: a árvore de decisão ajustada (profundidade 6, mínimo de 200
contratos por folha) chega a **0,7044**. Seis perguntas encadeadas contra 400 árvores somadas, por
0,037 de AuROC. É o modelo que cabe num quadro branco, e o preço de ter um está medido.

## 2026-09-13 — Faixa de score sai da PD out-of-fold: dentro da amostra a faixa 10 promete 0,6%

Conceitos: out-of-fold, cross_val_predict, tabela de faixas, calibração, memória x capacidade, nível da PD

O modelo final é reajustado em toda a Base A. Perguntar a ele a PD desses mesmos 10.000 contratos
para definir os cortes das faixas parece inofensivo — a distribuição é a mesma, afinal. E é: os
percentis batem na terceira casa decimal (p50 de 0,0542 out-of-fold contra 0,0531 dentro da
amostra, razão 0,98). Foi por isso que quase passou.

O que não bate é a **atribuição**. Cada contrato cai numa faixa diferente quando a PD vem de um
modelo que já o viu, e o efeito na promessa de nível é de outra ordem de grandeza:

| PD usada para montar a tabela | AuROC | PD observada na faixa 1 | na faixa 10 | separação |
|---|---|---|---|---|
| out-of-fold (25 ajustes) | 0,7326 | 29,60% | **3,70%** | 8,0x |
| dentro da amostra | 0,8088 | 35,00% | **0,60%** | 58,3x |

A tabela de dentro da amostra levaria ao conselho uma faixa 10 com 0,6% de inadimplência. A
realidade fora da amostra é 3,7% — **seis vezes mais**. A política precificaria a melhor faixa
quase de graça, e o erro só apareceria na apuração do ROI, quando não há mais o que corrigir.

**O que fica:** a distribuição de PD não denuncia o overfit; a distribuição de *acertos* denuncia.
Sempre que um número for usado para prometer nível — e não apenas para ordenar — ele tem de vir de
previsão que não viu o próprio alvo. `cross_val_predict` com 5 dobras custa um minuto de CPU e é o
preço inteiro dessa garantia.

**Como detectar da próxima vez:** compare a separação extremo-a-extremo (PD da pior faixa dividida
pela da melhor) nas duas versões. Se a razão muda de 8 para 58, a tabela não é tabela, é retrato do
treino. AuROC de 0,81 num modelo cujo out-of-time é 0,74 é o mesmo alarme, dito de outro jeito.

## 2026-09-13 — Dez faixas é exigência de formato; o dado sustenta quatro

Conceitos: faixas de score, intervalo de confiança, erro amostral, monotonicidade, granularidade, agrupamento por WoE

Primeira tentativa de faixa: decis da PD, 1.000 contratos cada. A tabela saiu com a **faixa 10 — a
melhor — quebrando mais que as faixas 7, 8 e 9**:

| faixa (decil) | 7 | 8 | 9 | 10 |
|---|---|---|---|---|
| PD observada | 3,2% | 3,3% | 3,0% | **3,7%** |

O reflexo foi caçar bug na inversão da escala. Não havia bug. Seis faixas inteiras (5 a 10) caíam
entre 2,72% e 5,86% de PD prevista, com 30 a 37 defaults em cada uma — a diferença entre 3,0% e
3,7% cabe inteira dentro do erro amostral.

Daí saiu o teste que passou a decidir: **duas faixas vizinhas só são faixas diferentes se o
intervalo de confiança de 95% da inadimplência de uma não tocar o da outra.** Na tabela final,
escolhida e monotônica, o resultado é desconfortável e verdadeiro: **7 dos 9 pares vizinhos não se
separam**. Só (1,2) e (3,4) se separam. Com 10.000 contratos e PD média de 8,26%, a Base A sustenta
quatro ou cinco níveis de risco distinguíveis, não dez.

Isso **não** invalida a tabela — a ordenação está correta de ponta a ponta (rho de Spearman −0,988,
nenhuma inversão fora do IC, faixa 1 quebrando 12,6x mais que a faixa 10). Invalida a pretensão de
dez preços distintos. A política diferencia grupos de faixas; a submissão reporta as dez porque o
campo `score_1a10` exige.

**Correção de desenho que veio junto:** separar duas faixas exige população proporcional à
dificuldade da separação. Distinguir 42% de 25% de PD cabe em 300 contratos; distinguir 3,3% de
3,4% não cabe em 2.000. Logo as faixas boas têm de ser **grandes** e as ruins **pequenas** — o
inverso do decil, que trata todas igual. Os cortes usados são os percentis 20/36/50/62/72/80/87/93/97.

**Armadilha registrada:** a estratégia de largura igual em log-odds deu monotonicidade perfeita
(rho −1,000, zero inversões) e foi descartada — conseguia isso porque a faixa 1 tinha **sete
contratos**. Métrica de monotonicidade não olha tamanho de faixa. Nunca leia uma sem a coluna de
população ao lado.

## 2026-09-13 — O viés de aprovados em um número só: PSI 0,473, e o guardrail de 35% já está apertado

Conceitos: PSI, viés de aprovados, reject inference, extrapolação, guardrail de aprovação, out-of-domain

Até aqui o viés de aprovados era uma coleção de cortes marginais — 27,7% da Base C abaixo de score
460, 28,1% com três ou mais restrições, 11,3% acima de 45% de comprometimento. A tabela de faixas
resolveu isso num indicador único.

| população | faixa média | % nas faixas 1-3 | PSI vs 2022 |
|---|---|---|---|
| Base A 2023 | 6,96 | 13,7% | 0,005 |
| Base A 2024 | 6,97 | 12,8% | 0,002 |
| Base B (2025-S1) | 7,13 | 11,8% | 0,006 |
| **Base C (2025-S2)** | **5,19** | **39,9%** | **0,473** |

Dentro do universo de aprovados a régua é notavelmente estável — PSI de 0,002 a 0,006, inclusive na
Base B, que é meio ano posterior a tudo que o modelo viu. A Base C dá **0,473**, que a régua de
mercado classifica como população trocada. Não é deterioração do modelo: é o mar aberto.

**A consequência operacional, que muda a política antes de ela ser escrita:** as faixas 8, 9 e 10
da Base C somam **30,4%** das 5.000 propostas, e o guardrail exige **≥ 35% de aprovação**. Aprovar
só as três melhores faixas **reprova no guardrail**. É obrigatório descer até a faixa 7 (38,0%
acumulado) ou aprovar parte da faixa 6 sob condições mais duras. O espaço de política é muito mais
estreito do que parecia.

**O limite de honestidade da defesa, dito uma vez:** a tabela de faixas foi validada em contratos
que a política antiga aprovou. A faixa 1 da Base C tem 713 propostas com PD prevista média de
43,1%, e boa parte desse perfil nunca recebeu crédito nesta casa. Para elas o número é
**extrapolação de árvore, não medição** — e árvore não extrapola, repete a folha mais próxima. O
erro nessa região é maior do que qualquer métrica da Base B consegue mostrar, e a política tem de
tratá-la por regra (negar, ou exigir entrada) e não por preço.

## 2026-09-14 — O parâmetro entregue traz uma decisão embutida: o −0,061 do avalista

Conceitos: LGD, avalista, média bruta x efeito dentro da célula, viés de composição, centragem, provisão

A aba `Leia-me` do arquivo de parâmetros diz uma frase: *some −0,061 à LGD da tabela quando o
contrato tem avalista*. Parece instrução de implementação. É decisão de modelagem disfarçada, e
aplicá-la ao pé da letra deixa perda sem provisão em 84% da carteira.

O −0,061 é a **diferença bruta de médias** entre os 826 defaults da Base A: 0,6468 com avalista
contra 0,7078 sem. Mas avalista não se espalha por igual — é 19,7% da carteira e 32,5% da célula de
LTV acima de 90% em veículo novo, onde a LGD já é alta por outro motivo. Medido **dentro da célula**,
o efeito é −0,079 (IC 95% [−0,101; −0,057], n=163). Os dois números não brigam: o oficial cabe no
intervalo. A média bruta é menor porque mistura o efeito do avalista com a composição de células.

O segundo problema é mais simples e mais caro: **a tabela não é a LGD de quem não tem avalista**.
Ela é a média da carteira inteira, com os 19,7% de avalistas já dentro. Somar o ajuste sobre ela
conta o efeito duas vezes para um grupo e nenhuma para o outro:

| regra aplicada | resíduo sem avalista | resíduo com avalista | LGD média |
|---|---|---|---|
| tabela crua | +0,0157 | −0,0634 | 0,6957 |
| oficial: tabela + (−0,061) | +0,0157 | −0,0024 | 0,6837 |
| tabela − 0,079 × (avalista − 0,197) | +0,0001 | +0,0000 | 0,6957 |
| *realizado* | | | *0,6958* |

A regra oficial acerta o grupo com avalista **por cancelamento de dois erros** — efeito subestimado
em 0,018 contra base subestimada em 0,0156 — e erra o resto. Na Base C, onde 25,3% das propostas
têm avalista contra 16,0% na Base A, a maioria mal provisionada continua sendo maioria.

**O erro que eu cometi no caminho, que é o mais instrutivo:** identifiquei que a tabela era uma
média de mistura e recentrei o ajuste mantendo o −0,061. Corrigir metade piorou o resultado — o
grupo com avalista saiu de −0,0024 para −0,0144. As duas metades tinham de ser corrigidas juntas.

**Como detectar da próxima vez:** nunca valide um parâmetro pelo agregado. O total da cadeia dava
1,012 para a versão correta e 0,995 para a literal, sugerindo que a literal era melhor. Só a
decomposição (PD 1,0019, EAD 1,0003, LGD 1,0146) mostrou onde estava a discussão, e só o **resíduo
por grupo** arbitrou. Agregado que fecha esconde dois erros que se cancelam.

## 2026-09-14 — O EAD depende da taxa que você cobra, e o lookup está congelado no preço antigo

Conceitos: EAD, Tabela Price, saldo devedor, mês do default, fator de EAD, laço preço-risco, CET

O fator de EAD do desafio vem por lookup de `prazo × faixa de LTV`. A aba `Leia-me` também descreve
a fórmula por trás: saldo devedor pela Price no mês do default mais as 3 parcelas vencidas do atraso
de 90 dias. Reconstruída — quem quebra no mês `m` parou de pagar em `m − 3` —, ela reproduz o campo
`ead_realizado` dos 826 defaults com **erro máximo de meio centavo**. Não é aproximação: é a mesma
fórmula que gerou a base.

Isso muda o que o parâmetro é. A fórmula é função de `(taxa, prazo, mês do default)` e **não tem
LTV dentro**. Duas consequências que o lookup esconde:

**A coluna de LTV é ruído.** O desvio de cada célula em relação à média da sua linha tem correlação
de −0,896 com o desvio do mês médio do default daquela célula. O que separa as colunas é qual delas
sorteou defaults mais cedo — informação que não existe na concessão. Células de 24 meses têm 11 a
28 contratos.

**A tabela está presa a 1,59% a.m.**, a mediana da carteira antiga. Juro alto amortiza devagar:

| taxa a.m. | fator de EAD, 48 meses |
|---|---|
| 1,59% (a da tabela) | 1,0320 — e o lookup dá 1,0322 |
| 3,00% | 1,0779 |
| 3,50% (teto de CET) | 1,0941 → **+6,0% de exposição** |

**A heurística que fica, e que vale além deste desafio:** preço não é só receita, é também risco.
Cobrar mais caro aumenta a exposição no default, aumenta a perda esperada e justifica cobrar mais
caro — o laço existe e é real. Onde a régua de EAD vem de uma carteira com preço homogêneo, ela é
otimista exatamente na região em que a política nova quer operar. Resolve-se avaliando o EAD na
taxa candidata, não numa média histórica.

## 2026-09-14 — Reproduza a tabela que te entregaram: ela conta como foi feita

Conceitos: engenharia reversa de parâmetro, fronteira de faixa, convenção de intervalo, auditoria de lookup

As tabelas de EAD e LGD do desafio são "dados". Rodar as células contra os realizados da Base A
mostrou que são exatamente as médias por célula daquela base — erro máximo de 0,00048 e 0,00049,
que é o arredondamento de três casas da própria planilha. Isso parece um teste inútil (reproduzir o
que foi entregue) e produziu duas coisas que não estavam escritas em lugar nenhum.

**1. A convenção de fronteira.** Os rótulos são `até 60%`, `60% a 70%`, ... e não dizem onde cai um
LTV de exatamente 0,80. Testando as duas hipóteses contra as 20 células:

| convenção | erro máximo |
|---|---|
| limite superior fechado (`ltv <= 0,60`) | 0,00338 |
| limite inferior fechado (`ltv < 0,60`) | **0,00048** |

As faixas são `[0; 0,60) [0,60; 0,70) [0,70; 0,80) [0,80; 0,90) [0,90; ∞)`. **LTV de exatamente 80%
cai na faixa pior.** Isso decide uma alavanca: exigir 20% de entrada achando que muda de faixa não
muda nada — a entrada tem de furar o corte, não encostar nele. Seis contratos da Base A decidiram a
questão; evidência magra, mas é a única, e o custo de errar é assimétrico.

**2. A dimensão que não é dimensão.** A mesma reprodução expôs que a coluna de LTV do fator de EAD é
ruído amostral, não risco (ver a entrada acima).

**O que fica:** parâmetro entregue por terceiro tem três perguntas obrigatórias antes do primeiro
uso — *de que amostra ele saiu*, *qual convenção de fronteira ele usa*, e *que regime ele
pressupõe* (aqui: preço de 1,59% a.m.). Nenhuma delas estava no `Leia-me`; todas saíram de
reproduzir as células. É meia hora de trabalho que muda decisão de política.

## 2026-09-19 — Preço não resolve risco extremo: o `(1 − PD)` dos juros

Conceitos: precificação a risco, juros esperados, teto de CET, sobrevivência do contrato, corte de política

A pergunta que o conselho vai fazer é direta: *por que negar a faixa 1 em vez de cobrar mais caro
dela?* A resposta errada — e a que o capítulo 06 quase deu — é "porque a perda esperada de 32,7%
do volume não cabe num teto de CET de 3,5% a.m.". Essa conta compara uma perda acumulada ao longo
do contrato com uma taxa mensal, e o próprio capítulo 06 marcou-a como piso otimista.

A conta certa anualiza os dois lados pela fórmula do enunciado, e o resultado é outro. Cobrando o
teto de 3,5% a.m. em 48 meses, a faixa 1 acumula **108% de juros** sobre 33% de perda. Parece
folgado. Mas juros só existem enquanto alguém paga:

```
juros esperados = (1 − PD) · juros do contrato inteiro + PD · juros até o mês do default
```

Com PD de 40,7%, o contrato médio da faixa 1 entrega `0,593 × 108% + 0,407 × ~12% ≈ 69%` de juros
contra 34% de perda, ao longo de quatro anos — **9,4% ao ano**. A faixa 8, com PD de 4,9%, entrega
24,1% no mesmo teto. O que separa as duas não é o preço, é quem sobrevive para pagá-lo.

| faixa | PD | juros brutos a 3,5% | ROI anualizado a 3,5% |
|---|---|---|---|
| 1 | 40,7% | 108% do valor financiado | **9,4%** |
| 2 | 24,0% | 108% | 16,3% |
| 8 | 4,9% | 108% | 24,1% |

**A heurística que fica:** existe um ponto em que a PD é alta demais para qualquer preço, e ele
chega muito antes de a perda esperada igualar a receita bruta. O termo `(1 − PD)` é o que localiza
esse ponto, e é exatamente o que falta numa análise que só compara "perda esperada" com "taxa".
É a razão matemática de um banco negar em vez de precificar — e a razão de "crédito para todos, a
preço de risco" ser uma frase, não um modelo de negócio.

**Erro que isto corrigiu:** o capítulo 06 concluiu certo por um caminho errado. Vale a checagem
geral: quando duas contas dão a mesma conclusão, a que está certa é a que responde na mesma
unidade e no mesmo horizonte.

## 2026-09-19 — A métrica premia prazo longo, e o risco de prazo não aparece nela

Conceitos: ROI anualizado, Tabela Price, horizonte da PD, gaming de métrica, extrapolação de modelo

`ROI anual = [(juros − perda) / volume] / prazo médio em anos`. Alongar o prazo mexe nos dois
termos, e nos dois para o mesmo lado. O numerador cresce porque o saldo Price amortiza devagar e o
juro incide sobre ele; o denominador dilui uma perda que acontece **uma vez só** por um prazo
maior. A 2,5% a.m., os juros anualizados vão de 17,10% em 24 meses para 18,82% em 60, e uma perda
de 5% do volume vira 2,50% ao ano em 24 meses contra 1,00% em 60.

O risco não aparece porque a PD é medida numa janela fixa de 12 meses e não é anualizada. A
métrica, literalmente, **cobra zero por alongar o prazo**. Os dados cobram:

| prazo | contratos | default 90/12 | renda mediana |
|---|---|---|---|
| 24 meses | 1.553 | 6,44% | R$ 6.125 |
| 60 meses | 2.608 | **11,62%** | R$ 4.882 |

E aqui está a sutileza que separa a decisão fácil da decisão certa: **boa parte desse salto é
composição, não causa.** Quem pede 60 meses ganha 20% menos. O prazo que a pessoa escolhe carrega
informação sobre ela. Impor 60 meses a quem pediu 24 leva o modelo a uma região que ele nunca
observou — renda alta em contrato longo é rara na base porque a combinação não ocorria, não porque
fosse segura. O modelo prevê +35% de PD média nesse cenário e não há como saber quanto disso é
real.

**O que fica:** quando o horizonte da métrica é mais curto que o horizonte do contrato, a métrica
tem um buraco, e ele fica exatamente na alavanca de prazo. Quem for otimizar a métrica vai achar o
buraco. O freio, aqui, foi o guardrail de inadimplência — que conta contratos e não anualiza nada —
e a regra de nunca ofertar prazo maior que o pedido. A defesa de uma decisão de prazo não é o ROI
simulado: é a resposta a "o que este modelo já viu?".

## 2026-09-19 — Decidir sob incerteza que não se pode medir: o canto duro e a conta da indiferença

Conceitos: elasticidade de aceite, seleção adversa, guardrail, decisão sob incerteza, probabilidade de indiferença

A política depende de uma curva de aceite que **nenhum dado do projeto contém**: as Bases A e B são
contratos (ofertas já aceitas) e a C são propostas sem desfecho. Não há uma só recusa de cliente
registrada. Pior, a submissão é única e o simulador é oculto — não dá para calibrar por tentativa e
erro. É a situação real de quem lança produto novo.

Três coisas que este projeto fez e que se repetem fora dele:

**1. Transformar o guardrail em âncora.** O enunciado afirma que o piso de R$ 40 mi existe para
impedir a solução degenerada (aprovar pouco, cobrar o teto, exigir entrada alta). Testamos a
degenerada nos três cenários de elasticidade: ela passa no otimista (R$ 50,9 mi) e quebra no
central (R$ 32,9 mi) e no pessimista (R$ 11,6 mi). Logo, **se o enunciado diz a verdade sobre a
função do guardrail, a elasticidade real é pelo menos a do cenário central.** É inferência fraca e
é a única disponível — o valor está em ser explícita sobre isso.

**2. Escolher pelo canto ruim, não pelo provável.** O critério foi: entre as regras que cumprem os
quatro guardrails com aceite pessimista **e** PD 20% acima da prevista, a de maior ROI. Das 384
regras testadas, 22 sobrevivem ao canto duro e 10 mantêm 4% de folga em todos os guardrails.

**3. Resolver a aposta com uma conta, não com adjetivos.** A regra mais agressiva da grade entrega
21,6% de ROI contra 15,7% da escolhida — 5,9 pontos. A penalidade de quebrar guardrail é metade da
nota. Então apostar só compensa se a probabilidade `q` de o guardrail segurar satisfizer:

```
q · r_b + (1 − q) · r_b/2 > r_a    ⟹    q > 2·r_a/r_b − 1
```

Aqui, `q > 45%`. E a folga dessa regra no canto duro é de −53%: ela precisa que o volume venha 53%
acima do que o próprio modelo projeta. Nem perto de 45%.

**O que fica:** "ser conservador" não é uma postura, é um número. Sempre que houver penalidade
descontínua — guardrail, covenant, limite regulatório —, a pergunta certa é *qual probabilidade de
sucesso tornaria a aposta indiferente*, e depois se essa probabilidade é plausível. Quase sempre a
resposta é óbvia depois da conta e ambígua antes dela.

## 2026-09-19 (noite) — Uma bateria de checagens que só diz "ok" não prova nada

Conceitos: conferência de entregável, teste de mutação, coerência de submissão, arredondamento, empate em AuROC

O entregável do desafio são dois CSVs. Gerá-los é trivial; o risco é que **erro de formato não dá
erro** — produz um arquivo legível com o número errado dentro, e a nota vai embora sem aviso. O
módulo de submissão ficou com 30 checagens. A pergunta que faltava era: elas checam alguma coisa?

A resposta foi estragar o arquivo de propósito, de nove formas, e exigir que a conferência pegasse
todas — teste de mutação aplicado a um entregável, não a uma função:

| sabotagem | o que foi acusado |
|---|---|
| BOM no início | sem BOM no início do arquivo |
| coluna renomeada / fora de ordem | colunas e ordem idênticas ao exemplo |
| uma linha a menos | 5.000 linhas |
| taxa acima do teto de CET | taxa entre 1,59% e 3,5% |
| taxa diferente do resto da faixa | uma só taxa por faixa |
| prazo gravado como `48.0` | prazo gravado como inteiro |
| linha NEGAR com preço | linhas NEGAR com as colunas vazias |
| score que não bate com `faixa(pd)` | score reproduzível pelo CSV |

O autoteste encontrou um defeito que as 30 checagens jamais mostrariam: cabeçalho errado abortava em
`KeyError` em vez de acusar a falha. **Quem escreve a checagem e nunca a vê falhar não sabe o que
ela faz quando falha.**

Duas disciplinas irmãs, das mesmas duas horas:

**1. Conferir o arquivo do disco, nunca o DataFrame que o gerou.** BOM, índice vazando para uma
primeira coluna, separador errado, `48.0` onde se esperava `48`, float em notação científica —
nenhum desses erros existe no objeto de origem. Ele está perfeito. Só a releitura vê.

**2. A hipótese que a medição derrubou.** Ia publicar a PD com 6 casas em vez das 4 do exemplo
"porque empate destrói AuROC". Medido na PD out-of-fold da Base A: 4 casas empatam 78% dos valores
e custam **0,00002 de AuROC** — nada, porque um AuROC bem implementado pontua par empatado como 0,5,
que é o tratamento certo para "o modelo não distingue estes dois".

A decisão continuou de pé, por outro motivo: a 4 casas, **19 das 5.000 propostas caem do outro lado
de um corte de faixa**, e quem reconferir `faixa(pd)` pelo CSV acha uma faixa diferente da que a
política usou — num desafio com 10 pontos de coerência. A 6 casas, zero.

**O que fica:** decisão certa com razão errada é pior do que parece, porque a razão é o que se leva
para a defesa. Se o conselho perguntar "quanto isso vale de AuROC?", a resposta honesta é "nada, e
não é por isso que eu faço". Mede-se antes de justificar, não depois.

**Corolário de coerência:** a mesma grandeza medida em dois pontos da cadeia vira duas colunas com
nomes diferentes, nunca uma. A PD da Base C existe nas condições pedidas (enquadramento, de onde a
faixa sai) e nas condições ofertadas (depois de a entrada derrubar o LTV, que é a que o preço
cobre) — 7,47% contra 6,93% na faixa 6. A submissão publica a primeira, porque é a que reproduz a
coluna `score_1a10` ao lado dela; a tabela publicada carrega as duas, com nome. Publicar só uma
fazia documento e submissão divergirem sem que ninguém soubesse por quê.

## 2026-09-19 (noite) — A linha que não reproduz o próprio número

Conceitos: tabela publicada, média ponderada, ROI anualizado, convenção de medida, auditabilidade

O documento que vai ao conselho tem uma tabela com uma linha por faixa de score: juros esperados,
perda esperada, prazo médio e ROI. Ao escrever o gerador desse documento, refiz de propósito a
conta da linha — `(juros − perda) / (prazo / 12)` — para conferir o ROI impresso ao lado. **Não
batia.** Faixa 5: a linha dizia 16,7% e a conta dava 16,1%.

Nenhum dos dois números estava errado. O que estava errado era a tabela publicar **duas
convenções diferentes de prazo médio na mesma linha**:

| | o que é | faixa 5 |
|---|---|---|
| coluna `prazo_medio` publicada | média simples dos prazos das 320 propostas | 42,9 meses |
| prazo que alimentava o `roi` | média ponderada por volume **e por aceite** | 41,4 meses |

O ROI usa a ponderada, e está certo: uma proposta que não fecha não entra na carteira, e uma de
R$ 80 mil pesa o dobro de uma de R$ 40 mil. A média simples entrou na coluna publicada porque era
a conta óbvia de escrever, não porque alguém a escolhesse.

O erro tem **viés, e não é ruído**: cresce em direção às faixas piores.

| faixa | erro de ROI ao refazer a conta pela linha |
|---|---|
| 10 | −0,005 p.p. |
| 8 | −0,19 p.p. |
| 6 | −0,53 p.p. |
| 5 | **−0,59 p.p.** |

A razão é mecânica e vale para qualquer carteira: nas faixas piores a taxa é maior, o aumento da
parcela é maior, e o aceite dos prazos longos cai mais. A carteira efetivamente contratada fica
mais curta que a carteira proposta — e quanto pior a faixa, maior a diferença. Na faixa 10 as duas
médias quase coincidem (42,47 contra 42,49) porque quase todo mundo aceita.

**O que fica:** a mesma grandeza medida com duas convenções vira duas colunas com nomes
diferentes, ou vira uma só — nunca uma coluna com o nome de uma e o uso da outra. E o teste que
pega isso é barato: **toda linha de tabela publicada tem de reproduzir os próprios números
derivados a partir das próprias colunas**. Virou checagem no gerador, com erro máximo de 1e-4.

É o irmão do erro das duas PDs da Base C, registrado na entrada anterior — o segundo em dois
dias. O padrão é sempre o mesmo: um número calculado num lugar, publicado de outro, e ninguém
comparando os dois. Diante do conselho, a pergunta "por que essa linha não fecha?" não tem
resposta boa — nem quando os dois números estão certos.

**Corolário prático:** nunca escreva de cabeça um número que um artefato já tem. Na mesma sessão,
escrevi "as faixas 1 a 4 concentram 30% da base"; são **20%** na Base A — e 47,2% na Base C, que
era o número interessante e que eu teria perdido. Frase de memória é frase não auditada.

## 2026-09-20 — A comparação que troca duas coisas ao mesmo tempo

Conceitos: tabela comparativa, variável de controle, família de medida, calibração, AuROC reportado

O capítulo 05 publicava esta tabela para justificar o número de faixas de score:

| granularidade | AuROC |
|---|---|
| 5 faixas | 0,7154 |
| **10 faixas** | **0,7297** |
| 20 faixas | 0,7311 |

Ao escrever o relatório do modelo, que lê tudo de artefato, a linha do meio saiu **0,7276**. Não
era erro de arredondamento. O script que gera a tabela usa cortes por quantil para as três
granularidades; a linha de dez faixas havia sido substituída, na escrita do capítulo, pela
estratégia **progressiva** — que é a escolhida, tem dez faixas e entrega 0,7297.

Os dois números estão certos e medem coisas diferentes. O defeito é a tabela: ela promete variar
**só o número de faixas** e varia também a estratégia de corte na linha do meio. Quem lê conclui
que ir de 5 para 10 faixas ganha 0,0143 quando o ganho real, na mesma família, é 0,0122 — e quem
roda o script encontra um número que a tabela não tem.

**A regra: numa tabela comparativa, uma coluna varia e o resto é controle.** Se a linha vencedora
pertence a outra família, ela sai da tabela e ganha um parágrafo próprio. Foi o que passou a
acontecer: a comparação ficou com as três granularidades em quantis, e a progressiva escolhida
aparece depois, nomeada, contra a PD contínua.

**A mesma doença, duas horas depois, no meu próprio rascunho.** O relatório reportava a faixa de
AuROC como "0,7226 a 0,7410". Os dois extremos vêm de famílias diferentes: 0,7226 é o modelo
**calibrado** em janelas encadeadas, e 0,7410 é o vencedor **sem calibrar**, da tabela que compara
os cinco candidatos (que é crua de propósito, para a disputa ser justa). O modelo entregue é
calibrado, e calibrado ele mede **0,7434** no mesmo out-of-time. A faixa correta é 0,7226 a 0,7434
— e a errada era mais estreita, o que a fazia parecer mais cuidadosa.

Três sessões, três instâncias do mesmo mecanismo: duas PDs na Base C, duas convenções de prazo
médio, e agora duas famílias de medida na mesma faixa. **Sempre que um número tem duas versões
legítimas, o erro não é escolher a errada — é publicar as duas sob o mesmo rótulo.** A defesa
barata é a checagem que o gerador agora faz: `calibrar sobe o AuROC out-of-time`, que falha se
alguém voltar a misturar as famílias.
