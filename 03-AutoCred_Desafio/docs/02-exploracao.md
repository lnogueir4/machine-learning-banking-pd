# 02 — Exploração: WoE, IV, monotonicidade e estabilidade

Código: [`src/exploracao.py`](../src/exploracao.py) (biblioteca) ·
[`notebooks/01-exploracao.py`](../notebooks/01-exploracao.py) (relatório em texto) ·
[`notebooks/01-exploracao.ipynb`](../notebooks/01-exploracao.ipynb) (versão narrada, com gráficos)

## O que este passo resolve

Esta não é uma exploração aberta. São três perguntas cujas respostas mudam o que os próximos
módulos vão fazer — e só elas:

1. **Quais das 18 variáveis têm poder preditivo, e como agrupá-las em faixas?**
2. **O valor ausente carrega informação?** Se carregar, a ausência vira variável em vez de ser
   imputada em silêncio.
3. **A relação entre cada variável e a inadimplência é monotônica?** A política opera em faixas de
   score de 1 a 10; relação que sobe e desce produz faixa indefensável diante do conselho.

Tudo o mais — histograma, boxplot, matriz de correlação — ficou de fora deliberadamente. Com prazo
curto, exploração que não muda uma decisão é tempo gasto sem contrapartida.

## A regra que quase todo mundo viola aqui

**Todas as decisões são calculadas na janela de treino (2022-2023).** A safra de 2024 aparece só
para conferir estabilidade, nunca para decidir.

Parece detalhe, mas é o vazamento do slide 5 da mentoria 02 na sua versão sutil: *"selecionar
variáveis pela correlação com a resposta usando todos os dados"*. Escolher features olhando o
conjunto inteiro contamina a validação out-of-time — o modelo passa a ser avaliado num período que
já influenciou quais variáveis ele usa, e a estimativa deixa de ser independente.

```python
treino = a[a["ano"] < ANO_CORTE]        # 6.670 contratos, PD 8,80% — decide
conferencia = a[a["ano"] == ANO_CORTE]  # 3.330 contratos, PD 7,18% — só confere
```

## Os conceitos, em uma passada

**WoE** (*weight of evidence*) mede, dentro de um grupo de contratos, o quanto bons e maus pagadores
estão desproporcionalmente representados:

```
WoE = ln( % dos bons que caem neste bin / % dos maus que caem neste bin )
```

WoE positivo = bin com mais bons que a média. Negativo = mais maus. Zero = o bin não distingue nada.

**IV** (*information value*) soma essa evidência sobre todos os bins e devolve um número por
variável:

```
IV = Σ (%bons − %maus) × WoE
```

A régua usada no mercado de crédito (convenção difundida, não norma): abaixo de 0,02 inútil; até
0,10 fraco; até 0,30 médio; até 0,50 forte; **acima de 0,50, suspeite de vazamento** em vez de
comemorar.

**PSI** (*population stability index*) usa a mesma ideia para comparar duas populações em vez de
bons contra maus: abaixo de 0,10 estável, 0,10-0,25 atenção, acima de 0,25 a população trocada.

Ausentes viram um bin próprio, `AUSENTE`, em vez de serem imputados antes. É isso que permite
responder à pergunta 2 — se o bin de ausentes tiver WoE longe de zero, a ausência tem sinal.

## Resultado 1 — sinal fraco e distribuído

| Variável | IV treino | IV 2024 | Força | PSI A→C |
|---|---:|---:|---|---:|
| `score_bureau` | 0,1731 | 0,2864 | médio | 0,488 |
| `qtd_restricoes_ativas` | 0,1328 | 0,1083 | médio | 2,335 |
| `idade_cliente` | 0,1171 | 0,1599 | médio | 0,003 |
| `renda_mensal_declarada` | 0,1125 | 0,1697 | médio | 0,141 |
| `prazo_meses` | 0,0773 | 0,0586 | fraco | 0,003 |
| `valor_entrada` | 0,0590 | 0,0612 | fraco | 0,111 |
| `valor_bem` | 0,0545 | 0,0477 | fraco | 0,040 |
| `comprometimento_renda` | 0,0503 | 0,1330 | fraco | — |
| `valor_financiado` | 0,0486 | 0,0209 | fraco | 0,009 |
| `ocupacao` | 0,0469 | 0,0375 | fraco | 0,002 |
| `tempo_emprego_meses` | 0,0361 | 0,0604 | fraco | 0,001 |
| `ltv` | 0,0173 | 0,0556 | inútil | 0,082 |
| `idade_veiculo_anos` | 0,0137 | 0,0494 | inútil | 0,022 |
| `ano_modelo` | 0,0130 | 0,0458 | inútil | 1,394 |
| `tipo_residencia` | 0,0118 | 0,0300 | inútil | 0,003 |
| `qtd_consultas_bureau_3m` | 0,0109 | 0,0276 | inútil | 0,076 |
| `possui_avalista` | 0,0093 | 0,0197 | inútil | 0,056 |
| `canal_originacao` | 0,0080 | 0,0433 | inútil | 0,004 |

Nenhuma variável passa de 0,18 de IV. **Este é um problema de sinal fraco e distribuído**, não um
problema com uma variável dominante — o que explica o teto de AuROC em torno de 0,74 medido no
capítulo anterior e confirma que não há nada escondido esperando ser descoberto.

Leituras:

- `ltv` com IV de 0,017 é contraintuitivo em financiamento de veículo, onde LTV é *a* variável de
  garantia. A explicação é o viés de aprovados: a política antiga truncava o LTV, e o que sobrou na
  base tem pouca variação. Em compensação `ltv` continua indispensável fora do modelo — as tabelas
  oficiais de EAD e LGD são indexadas por faixa de LTV.
- `ano_modelo` junta IV inútil (0,013) com PSI de 1,394. O PSI alto é artefato de calendário:
  propostas de 2025 têm veículos mais novos que contratos de 2022. Variável que não prediz e não é
  estável sai do modelo.
- `comprometimento_renda` não tem PSI porque na primeira passada da Base C ela ainda não existe —
  só é calculável depois que a política define a parcela (ver [capítulo 01](01-dados.md)).

## Resultado 2 — o faltante quase não informa

| Coluna | % ausente | PD ausente | PD presente | Razão |
|---|---:|---:|---:|---:|
| `renda_mensal_declarada` | 7,63% | 9,23% | 8,76% | 1,05x |
| `tempo_emprego_meses` | 11,69% | 9,74% | 8,68% | 1,12x |
| `score_bureau` | 3,42% | 10,09% | 8,76% | 1,15x |

A hipótese de partida era a do mercado: quem não declara renda costuma ter perfil de risco pior, e
a ausência viraria um indicador. **A hipótese não se sustentou nesta base.** As razões ficam entre
1,05x e 1,15x, e o caso mais forte (`score_bureau` ausente, PD de 10,09%) tem n de apenas 228
contratos — o intervalo de confiança cobre a média geral.

Decisão: **não criar indicadores de ausência.** Imputação simples pela mediana, dentro do pipeline.
Registrar a hipótese testada e descartada vale mais que o indicador que ela teria gerado — é
exatamente a pergunta que o conselho faz ("vocês trataram os faltantes como?") e agora há resposta
com número.

## Resultado 3 — `score_bureau` satura acima de 600

O WoE por faixa mostrou algo que o IV sozinho esconde:

| Faixa de `score_bureau` | n | PD | IC 95% |
|---|---:|---:|---|
| até 503 | 656 | 16,92% | 14,05% – 19,79% |
| 503 – 601 | 1.923 | 11,02% | 9,62% – 12,42% |
| 601 – 661 | 1.292 | 6,97% | 5,58% – 8,35% |
| 661 – 695 | 639 | 5,16% | 3,45% – 6,88% |
| 695 – 740 | 648 | 5,40% | 3,66% – 7,14% |
| 740 – 807 | 644 | 6,21% | 4,35% – 8,08% |
| acima de 807 | 640 | **6,72%** | 4,78% – 8,66% |

*(janela de treino, 2022-2023 — como todo o resto deste capítulo)*

A PD **para de cair** a partir de 601 e volta a subir no topo. A tentação é interpretar isso como
descoberta — "clientes de score altíssimo são mais arriscados". **Não é.** Testando as diferenças:

```
(661,695] vs (740,807]   z = +0,81   indistinguível
(661,695] vs (807,1000]  z = +1,18   indistinguível
(601,661] vs (807,1000]  z = −0,20   indistinguível
```

Nenhuma diferença passa de |z| = 1,96. O que os dados dizem é mais simples e mais útil: **acima de
601, o `score_bureau` não discrimina mais nada nesta carteira.** Toda a capacidade preditiva dele
está na metade inferior da escala.

Consequência direta para o capítulo 05 (Score, ainda não escrito): não adianta criar quatro faixas de score no
topo baseadas em bureau. A separação lá em cima, se existir, terá de vir de outras variáveis.

## Resultado 4 — o achado mais grave: 39,5% da Base C está fora do domínio de treino

`qtd_restricoes_ativas` é a segunda variável mais preditiva, com relação perfeitamente monotônica:

| Restrições | n (treino) | PD |
|---|---:|---:|
| 0 | 3.472 | 7,17% |
| 1 | 2.159 | 7,78% |
| 2 | 1.039 | 16,36% |

Repare onde a tabela termina. **A Base A vai de 0 a 2 restrições. Só.** O mesmo vale para a Base B.
A Base C vai até 5:

| Restrições | Base A | Base B | Base C |
|---|---:|---:|---:|
| 0 | 52,4% | 52,7% | 33,8% |
| 1 | 32,6% | 32,8% | 24,1% |
| 2 | 15,0% | 14,5% | 14,0% |
| 3 | — | — | 8,7% |
| 4 | — | — | 5,7% |
| 5 | — | — | **13,7%** |

**1.404 propostas da Base C — 28,1% — têm mais restrições ativas do que qualquer contrato que o
modelo já viu.** E não é uma cauda rala: o valor 5 sozinho concentra 13,7%.

Isso torna visível a regra da política antiga: a AutoCred **recusava automaticamente quem tinha 3
ou mais restrições**. O corte não está escrito em lugar nenhum do material — está impresso nos
dados.

A consequência é grave e específica. Modelos baseados em árvore **não extrapolam**: um proponente
com 5 restrições cai na mesma folha de um com 2 e recebe a mesma PD, ~16%. Como 2 restrições já
triplicam a PD em relação a 1, supor que 5 equivalem a 2 é um erro na direção perigosa — o modelo
vai **subestimar sistematicamente** o risco de mais de um quarto da Base C.

### E há um segundo corte, no bureau

O mesmo teste aplicado a todas as variáveis revelou outra regra escondida: **a Base A tem mínimo
de `score_bureau` exatamente 460**, e a Base B também. A Base C desce até 0, num contínuo
(0, 10, 24, 42, 57...) — não é código de ausência, são scores reais. **27,7% das propostas estão
abaixo do piso histórico.**

| Variável | mín. treino | máx. treino | mín. Base C | máx. Base C | % de C fora |
|---|---:|---:|---:|---:|---:|
| `score_bureau` | 460 | 1000 | 0 | 1000 | 27,7% |
| `qtd_restricoes_ativas` | 0 | 2 | 0 | 5 | 28,1% |
| `ltv` | 0,25 | 0,95 | 0,25 | 0,98 | 7,1% |
| `valor_entrada` | 1.107 | 92.223 | 440 | 116.780 | 3,7% |

Somando o perímetro — quantas propostas caem fora do domínio em **ao menos uma** variável de
crédito — chega-se a **39,5% da Base C: 1.976 de 5.000 propostas.** (`ano_modelo` fica de fora da
conta: o deslocamento dele é de calendário, não regra de crédito.)

Duas regras da política de 2022, recuperadas dos dados e não de documento algum:

```
score_bureau >= 460   E   qtd_restricoes_ativas <= 2
```

Este é o problema de inferência de rejeitados que o enunciado antecipa, agora localizado em
variáveis específicas e medido. Ele não se resolve com modelagem melhor: não existe informação na
base sobre como se comporta quem tem 5 restrições ou score 150. A solução tem de ser uma **regra
de política explícita** para a região sem suporte, tratada no capítulo 07 (Política, ainda não escrito) e
defendida como decisão de risco, não como saída de modelo.

## O que deu errado

**Dois bugs, e o segundo era invisível.**

O primeiro foi barulhento: `comprometimento_renda` saiu com PSI de 25,3. É toda `NaN` na primeira
passada da Base C, então a comparação era contra 100% de ausentes. Corrigido devolvendo `NaN` quando
não há o que comparar.

O segundo é o que vale registrar. Os bins numéricos vinham de `pd.cut(...).astype(str)`, e o
`groupby` ordena texto: `"(1000.0, 1500.0]"` vem **antes** de `"(400.0, 450.0]"`. A monotonicidade
de todas as variáveis numéricas estava sendo medida na ordem errada, sem erro, sem aviso, com
números plausíveis na tela. Só apareceu porque `qtd_restricoes_ativas` devolveu `rho` nulo e me
obrigou a olhar o binning de perto.

O estrago era material — depois da correção:

```
renda_mensal_declarada   rho −0,68 → −0,90
tempo_emprego_meses      rho −0,52 → −0,77
valor_entrada            rho −0,27 → −0,65
qtd_restricoes_ativas    rho   NaN →  1,00
```

A correção foi devolver categórica **ordenada** em vez de string:

```python
recortada = pd.cut(serie, bins=cortes, duplicates="drop")
ordem = [str(c) for c in recortada.cat.categories]
rotulos = recortada.astype(str).where(serie.notna(), AUSENTE)
return pd.Categorical(rotulos, categories=ordem + [AUSENTE], ordered=True), cortes
```

Lição generalizável: **em análise por faixas, todo bin precisa carregar sua ordem junto**. Assim que
o rótulo vira texto, a ordem se perde — e como o resultado continua parecendo razoável, o erro
sobrevive à revisão.

Houve ainda um terceiro ajuste, de método e não de bug: o PSI de `qtd_restricoes_ativas` deu 3,34
porque valores presentes em C e ausentes no treino ganhavam esperado quase nulo e explodiam o
logaritmo. Agregando o fora-de-domínio ao bin extremo, caiu para 2,335 — ainda "população trocada",
que é a leitura correta.

## Decisões que este capítulo fecha

| Decisão | Evidência |
|---|---|
| Descartar `ano_modelo` do modelo | IV 0,013 e PSI 1,394 — artefato de calendário |
| Manter `ltv` fora do modelo, mas ativo no cálculo de risco | IV 0,017; indexa as tabelas de EAD e LGD |
| Não criar indicadores de ausência | razões de 1,05x a 1,15x, dentro do ruído |
| Imputação simples pela mediana, dentro do pipeline | corolário da decisão acima |
| Não abrir múltiplas faixas de score no topo via bureau | saturação acima de 601, z < 1,96 |
| Regra de política explícita para 3+ restrições | 28,1% da Base C fora do domínio de treino |

As variáveis com IV abaixo de 0,02 **não** são descartadas em bloco. O modelo escolhido é gradient
boosting, que lida bem com variável fraca, e IV mede relação univariada — pode haver interação que
o IV não enxerga. A exceção é `ano_modelo`, descartada pela combinação de IV baixo **com** PSI alto.

## Como reproduzir

Duas formas, mesma lógica — as funções de binning, WoE, IV e PSI vivem em
[`src/exploracao.py`](../src/exploracao.py) e são consumidas pelas duas:

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python notebooks/01-exploracao.py     # relatório em texto
PYTHONIOENCODING=utf-8 python notebooks/gerar_notebook.py    # gera e executa o .ipynb
```

O [`01-exploracao.ipynb`](../notebooks/01-exploracao.ipynb) é a versão narrada, com gráficos e
saídas embutidas — feita para ser lida por quem não vai rodar nada. Ele é **gerado**, nunca
editado à mão: notebook e script mantidos em paralelo divergiriam na primeira correção, e um
notebook que contradiz o pipeline é pior que não ter notebook.

Confira: `treino n=6,670 (PD=0.0880)`; `score_bureau` no topo da tabela de IV com 0,1731; IV total
somado de 0,9923; a tabela de WoE de `qtd_restricoes_ativas` terminando no bin `2`. A tabela
completa fica em `artefatos/eda_iv_psi.csv` e os metadados da execução em
`artefatos/eda_exploracao.json`.

---

**Próximo capítulo:** 03 — Features, onde estas decisões viram um `Pipeline` que só aprende com o
treino.
