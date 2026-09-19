# 04 — Modelo: estimar a probabilidade de calote

> Capítulo anterior: [03 — Features](03-features.md) · Próximo: [05 — Score](05-score.md)
> Código: [`src/modelo.py`](../src/modelo.py) · Figuras: [`notebooks/04-modelagem.ipynb`](../notebooks/04-modelagem.ipynb)

## O que este passo resolve

Dada uma proposta de financiamento, qual a probabilidade de esse contrato ficar 90 dias em atraso
nos 12 meses seguintes? Esse número — a **PD**, *probability of default* — é o insumo de tudo que
vem depois: ele vira faixa de score, multiplica EAD e LGD para dar a perda esperada, e é o que
separa "aprovar a 1,4% a.m." de "negar".

Duas qualidades diferentes são exigidas dele, e é fácil confundi-las:

- **Ordenação** — pôr os piores clientes na frente dos melhores. É o que o AuROC mede, e é o que
  vale os 40 pontos do entregável de modelo.
- **Nível** — acertar a magnitude. Um modelo pode ordenar com perfeição e ainda prever 3% onde a
  realidade é 8%. O AuROC não enxerga isso; a política, sim, porque precifica com o número.

### Vocabulário mínimo

**AuROC** (0,5 = sorteio, 1,0 = perfeito) é a chance de o modelo dar nota de risco maior a um
inadimplente do que a um adimplente sorteados ao acaso. **Gini** = 2 × AuROC − 1, mesma informação
noutra escala. **KS** é a maior distância entre as curvas acumuladas de bons e maus — diz *onde* a
separação é mais forte, que é onde faz sentido pôr um corte. **Brier** é o erro quadrático médio da
probabilidade: diferente dos outros três, ele pune errar o nível.

---

## Decisões, com a alternativa descartada

### 1. Validação out-of-time, e hiperparâmetro escolhido sem olhar para ela

O split é temporal: treino em 2022-2023 (6.670 contratos, PD 8,80%), validação em 2024 (3.330
contratos, PD 7,18%). Isso imita a situação real — a Base B é jan-jun/2025, posterior a tudo que
temos. Um split aleatório mediria a capacidade de interpolar dentro do mesmo período, que é
pergunta mais fácil e diferente da que a nota faz.

O ponto fino, que é onde a maioria escorrega: **os hiperparâmetros foram escolhidos por validação
cruzada de 5 dobras dentro de 2022-2023**, nunca olhando 2024.

E não só os do vencedor. **Todos os quatro candidatos ajustáveis passam pela mesma busca**, na mesma
janela, com a mesma métrica — 149 combinações no total:

| Modelo | combinações | melhor AuROC CV | ±dp | vencedor da grade |
|---|---:|---:|---:|---|
| Regressão logística | 7 | 0,6540 | 0,0319 | `C=0,01` |
| Árvore de decisão | 48 | 0,6923 | 0,0197 | `entropy, max_depth=6, min_samples_leaf=200` |
| Random Forest | 40 | 0,7126 | 0,0272 | `max_depth=12, max_features=0.5, min_samples_leaf=20` |
| **HistGB regularizado** | 54 | **0,7249** | 0,0197 | `lr=0,03, 4 folhas, min 50, L2=1` |

Buscar só para o favorito e deixar os concorrentes com parâmetro de fábrica produz uma comparação
arranjada: o vencedor ganharia por ter sido ajustado, não por ser melhor. Foi assim que a primeira
versão desta tabela foi montada, e a correção mudou números de verdade — a árvore subiu de 0,6777
para 0,7044 no out-of-time, e a Random Forest de 0,7312 para 0,7353.

Se as grades tivessem sido avaliadas em 2024, o número reportado deixaria de ser uma previsão do
que acontecerá na Base B e passaria a ser o melhor resultado entre 149 tentativas na própria
régua — otimista por construção. **Alternativa descartada:** ajustar parâmetro contra o out-of-time
"porque é só uma métrica". É exatamente assim que um modelo chega à apuração valendo menos do que
prometeu.

### 2. Gradient boosting regularizado, com a logística mantida como referência

Todos abaixo estão com a grade vencedora da busca, exceto o `HistGB padrão`, que fica de fábrica
de propósito — o papel dele é exibir o overfit que a regularização evita.

| Modelo | AUC treino | AUC OOT | queda | Gini OOT | KS OOT | Brier OOT | viés OOT |
|---|---:|---:|---:|---:|---:|---:|---:|
| Regressão logística | 0,6658 | 0,6521 | 0,0137 | 0,304 | 0,244 | 0,0648 | +0,0149 |
| Árvore de decisão | 0,7351 | 0,7044 | 0,0307 | 0,409 | 0,305 | 0,0644 | +0,0138 |
| Random Forest | 0,9212 | 0,7353 | 0,1860 | 0,471 | 0,374 | 0,0619 | +0,0152 |
| HistGB padrão | 0,9982 | 0,7097 | 0,2886 | 0,419 | 0,333 | 0,0645 | −0,0007 |
| **HistGB regularizado** | 0,8117 | **0,7410** | 0,0707 | **0,482** | **0,376** | **0,0616** | +0,0151 |

#### O que é gradient boosting

É construir o modelo **em série, corrigindo o próprio erro**. Começa com um chute único para todo
mundo — a inadimplência média do treino, 8,80%. Depois, repetidamente: mede o quanto esse chute
errou em cada contrato, treina uma árvore *pequena* (aqui, 4 folhas) para prever **o erro**, e soma
uma fração dessa correção ao resultado anterior. A fração é o `learning_rate`, 0,03 no nosso caso:
cada árvore só pode mexer 3% do que ela acha que deveria. Isso 400 vezes.

O "gradient" vem daí — cada árvore aprende na direção em que o erro cai mais rápido, o gradiente da
função de perda. Nenhuma árvore sozinha sabe nada; 400 correções pequenas e encadeadas formam uma
superfície de decisão detalhada.

O prefixo `Hist` é implementação: em vez de testar todo valor possível de renda como ponto de corte,
o algoritmo agrupa cada variável em 255 faixas antes. Fica muito mais rápido e, de brinde, aprende
para que lado mandar o `NaN` em cada corte — a decisão 4 do [capítulo 03](03-features.md).

#### As cinco abordagens, e no que diferem

| Modelo | Como decide | O que o distingue |
|---|---|---|
| Regressão logística | soma ponderada das variáveis, achatada numa curva S | um coeficiente por variável; só representa relação em linha reta |
| Árvore de decisão | sequência de perguntas sim/não; a folha devolve a inadimplência do grupo | totalmente legível — mas cada folha é uma média, e nada entre elas |
| Random Forest | 300 árvores **em paralelo**, cada uma sobre uma amostra e um sorteio de variáveis; tira a média | árvores independentes; a média cancela o erro individual de cada uma |
| HistGB padrão | boosting com os parâmetros de fábrica | árvores **em série**, cada uma corrigindo a anterior — sem freio |
| HistGB regularizado | o mesmo, com freio: 4 folhas, mínimo 50 por folha, passo 0,03, penalidade L2 | o freio é o que faz funcionar fora da amostra |

A diferença de fundo entre floresta e boosting é **paralelo contra série**. A floresta faz muitas
tentativas independentes e tira a média: ataca a instabilidade. O boosting encadeia correções:
ataca o erro sistemático. Aqui o boosting ganhou, mas por pouco.

#### As três leituras da tabela

**O overfit é visível a olho nu.** `HistGB padrão` e `HistGB regularizado` são o *mesmo algoritmo*:
0,9982 no treino contra 0,8117. O de cima decorou a base contrato a contrato e generalizou pior
(0,7097 contra 0,7410). Pôr o freio derruba o treino em 0,19 e **sobe** o teste em 0,03.
Regularizar não é conservadorismo; é a diferença entre um modelo que sabe e um que decorou. A
Random Forest mostra a versão intermediária do mesmo fenômeno: 0,9212 no treino, queda de 0,186.

**A vitória do boosting sobre a floresta não é estatisticamente decisiva.** São 0,0057 de AuROC,
contra um desvio de validação de ~0,02. Com os dois devidamente ajustados, escolher entre eles
pela terceira casa decimal seria o erro que a decisão 5 deste capítulo descreve. O que decide são
os outros critérios, e todos apontam para o mesmo lado: Brier melhor (0,0616 contra 0,0619), KS
melhor (0,376 contra 0,374) e, sobretudo, uma queda treino→teste de 0,07 contra 0,19. Entre dois
modelos de desempenho equivalente, fica o que depende menos de ter decorado.

**A logística é o piso honesto.** Ela custa 0,089 de AuROC, caro demais para ser o modelo final,
mas é o referencial: se o boosting não superasse com folga, não pagaria a própria opacidade diante
do conselho. A árvore ajustada é o melhor modelo *legível* que temos, e vale guardar para a defesa:
**seis perguntas encadeadas chegam a 0,7044**, contra 0,7410 de 400 árvores somadas. A diferença
entre o que se explica num quadro branco e o que se explica num gráfico de importâncias custa
0,037 de AuROC.

### 3. Calibração sigmoide, não isotônica

O AuROC ignora calibração. A política, não: a perda esperada é `PD × EAD × LGD`, e um erro de nível
na PD vira erro de preço direto. A tabela de calibração do vencedor no out-of-time, por decil de
risco previsto:

| decil | n | PD prevista | PD observada | razão |
|---:|---:|---:|---:|---:|
| 1 | 333 | 3,32% | 1,50% | 2,21 |
| 2 | 333 | 4,02% | 3,00% | 1,34 |
| 5 | 333 | 5,64% | 2,10% | 2,68 |
| 8 | 333 | 9,60% | 8,11% | 1,18 |
| 9 | 333 | 13,74% | 13,81% | 0,99 |
| 10 | 333 | 27,00% | 23,42% | 1,15 |

A ordenação é sólida — do decil 1 ao 10 a PD observada vai de 1,5% a 23,4% — mas o nível é
otimista invertido: o modelo superestima o risco nos decis bons. `CalibratedClassifierCV` corrige a
curva em dobras internas do treino e, de brinde, agrega as cinco dobras, o que vale **+0,0024 de
AuROC** (0,7410 → 0,7434).

**Sigmoide (Platt), não isotônica.** As duas empatam em discriminação (0,7436 contra 0,7437) e no
Brier (0,0616), então o critério é o comportamento no extremo: por ser uma função escada, a
isotônica devolve `PD = 1,0000` para 2 contratos da Base A. Probabilidade de exatamente 1 é
indefensável como estimativa — e, multiplicada por EAD e LGD, produz uma perda esperada igual à
exposição inteira, o que distorce qualquer decisão de preço. A sigmoide vai no máximo a 0,8556.

### 4. Reajustar o modelo final em toda a Base A

Validado o desenho, o modelo de produção é retreinado em 2022-2024 inteiro. Segurar 2024 fora do
treino depois que a pergunta "isto generaliza?" já foi respondida joga fora um terço dos dados — e
justamente o terço mais próximo, no tempo, da Base B. A configuração está congelada antes disso;
nenhuma decisão é tomada a partir do reajuste.

Resultado: PD média 8,30% na Base A contra 8,26% observada, com PDs entre 1,56% e 87,41%.

### 5. A poda de variáveis que parecia boa e não era

A importância por permutação no out-of-time sugeria cortar muita coisa — `ltv` e `valor_bem` com
contribuição **negativa**, e sete variáveis em torno de zero:

| variável | queda de AuROC ao embaralhar | dp |
|---|---:|---:|
| `idade_cliente` | 0,0816 | 0,0047 |
| `score_bureau` | 0,0683 | 0,0063 |
| `prazo_meses` | 0,0608 | 0,0090 |
| `comprometimento_renda` | 0,0283 | 0,0046 |
| `qtd_restricoes_ativas` | 0,0247 | 0,0050 |
| `ocupacao` | 0,0184 | 0,0061 |
| `tempo_emprego_meses` | 0,0126 | 0,0051 |
| … | … | … |
| `valor_bem` | −0,0018 | 0,0013 |
| `ltv` | −0,0044 | 0,0038 |

E a poda parecia confirmada pelo out-of-time: quanto mais se corta, melhor fica.

Não podei, e essa é a decisão mais importante do capítulo. O out-of-time de 2024 já vinha sendo
consultado várias vezes; escolher o conjunto de variáveis por ele é transformá-lo em conjunto de
treino. Montei então uma validação temporal **encadeada**, em três janelas que nunca haviam sido
usadas para nada e todas anteriores a 2024:

| Conjunto | 2022 → 2023-S1 | 2022 → 2023 | 2022+23-S1 → 2023-S2 | média | *OOT 2024* |
|---|---:|---:|---:|---:|---:|
| **17 (atual)** | 0,7171 | 0,7228 | 0,7279 | **0,7226** | *0,7434* |
| 18 (com `ano_modelo`) | 0,7171 | 0,7228 | 0,7279 | 0,7226 | *0,7434* |
| 15 (sem `valor_bem` e `ltv`) | 0,7142 | 0,7210 | 0,7299 | 0,7217 | *0,7486* |
| 11 (sem as de importância ~0) | 0,7134 | 0,7200 | 0,7303 | 0,7212 | *0,7518* |
| 7 principais | 0,7205 | 0,7127 | 0,7149 | 0,7160 | ***0,7546*** |

As duas últimas colunas são a mesma lista de conjuntos lida por duas réguas, e elas discordam de
ponta a ponta: **no out-of-time de 2024 a qualidade sobe monotonicamente conforme se poda** (0,7434
→ 0,7546); nas janelas independentes, **desce** (0,7226 → 0,7160). Os 0,011 de vantagem das 7
variáveis eram coincidência de janela, e teriam sido apresentados ao conselho como melhoria se a
única régua fosse aquela.

A única variável removida foi `ano_modelo`, e por motivo que não depende de métrica: o capítulo 02
já a havia reprovado (IV 0,013 com PSI 1,394), a contribuição medida é zero — sai e entra sem mudar
o AuROC em nenhuma casa decimal — e **31,8% da Base C tem ano de modelo acima do máximo do treino**
(o treino vai até 2022; as propostas chegam a 2025). Árvore não extrapola: para esses casos a
variável só pode empurrar a predição para a folha do extremo conhecido. Variável com contribuição
nula e domínio estourado é risco puro.

> Erro de processo registrado: a remoção estava decidida e escrita em `docs/02-exploracao.md` desde a
> sessão anterior, mas nunca chegou ao código — `ano_modelo` continuava em `FEATURES`. Foi a
> importância por permutação, medida por outro motivo, que denunciou. Decisão documentada não é
> decisão implementada, e só o código sabe a diferença.

O conjunto ficou separado em dois nomes, para que isso não volte a acontecer: `CANDIDATAS` (18) é o
que a exploração mede, `FEATURES` (17) é o que o modelo usa. A diferença é explícita e auditável.

---

## O código que importa

O split, que é uma linha e decide a honestidade de todo o resto:

```python
def dividir(a):
    return a[a["ano"] < ANO_CORTE].copy(), a[a["ano"] == ANO_CORTE].copy()
```

As métricas separadas por finalidade — três de ordenação, duas de nível:

```python
def metricas(y, p):
    auc = roc_auc_score(y, p)
    return {"auroc": auc, "gini": 2 * auc - 1, "ks": ks(y, p),
            "brier": brier_score_loss(y, p),
            "pd_prevista": p.mean(), "pd_observada": y.mean(),
            "vies": p.mean() - y.mean()}
```

A busca, com `cv` sobre o treino e nada mais:

```python
busca = GridSearchCV(montar_pipeline(HistGradientBoostingClassifier(random_state=SEED)),
                     grade, scoring="roc_auc",
                     cv=StratifiedKFold(5, shuffle=True, random_state=SEED), n_jobs=-1)
busca.fit(matriz(treino), treino[ALVO])      # `oot` não aparece nesta função
```

E o modelo final, envelopado na calibração:

```python
def treinar_final(a, calibrar=True):
    pipe = montar_pipeline(HistGradientBoostingClassifier(random_state=SEED, **MELHORES))
    if calibrar:
        pipe = CalibratedClassifierCV(pipe, method="sigmoid", cv=5)
    return pipe.fit(matriz(a), a[ALVO])      # toda a Base A, configuração congelada
```

---

## Os números que saíram

```
treino 2022-01–2023-12: n=6,670 (PD=0.0880) | OOT 2024-01–2024-12: n=3,330 (PD=0.0718)
Vencedor por AuROC out-of-time: HistGB regularizado

                    AuROC    Brier  PD prevista  PD observada
  sem calibrar     0.7410   0.0616       0.0869        0.0718
  calibrado        0.7434   0.0616       0.0876        0.0718

Modelo final: PD média na Base A 0.0830 | observada 0.0826 | faixa 0.0156 a 0.8741
```

### Dois achados que a política vai ter de enfrentar

**A PD está caindo safra a safra.**

| safra | n | PD |
|---|---:|---:|
| 2022-S1 | 1.702 | 8,58% |
| 2022-S2 | 1.678 | 8,76% |
| 2023-S1 | 1.683 | 9,57% |
| 2023-S2 | 1.607 | 8,28% |
| 2024-S1 | 1.717 | 7,80% |
| 2024-S2 | 1.613 | **6,51%** |

A Base B é 2025-S1 e a Base C é 2025-S2, ambas depois do fim da série. Um modelo calibrado na Base A
inteira carrega o nível médio de 2022-2024 e tende a **superestimar** a PD dessas safras. Para a
submissão do modelo isso é irrelevante — AuROC só lê ordenação. Para a política, não.

**E a Base C é muito pior que a Base A.**

| Base | PD média prevista | mediana | p90 | acima de 20% | acima de 46% (break-even) |
|---|---:|---:|---:|---:|---:|
| A (2022-2024, aprovados) | 8,30% | 5,31% | 17,21% | 7,8% | 0,9% |
| B (2025-S1, aprovados) | 7,93% | 5,25% | 16,04% | 6,9% | 0,6% |
| **C (2025-S2, mar aberto)** | **15,53%** | 9,59% | 34,22% | **30,1%** | 4,7% |

A PD média prevista na Base C é **quase o dobro** da Base A. Não é defeito do modelo: é o viés de
aprovados aparecendo em número. A Base C contém os perfis que a política antiga recusava, e o
modelo — corretamente — os pontua como piores.

Os dois efeitos empurram em sentidos opostos: a deriva temporal diz que estamos superestimando, o
mar aberto diz que a carteira de fato piorou. **Eles não se cancelam automaticamente**, e resolver
isso é trabalho do capítulo de política, não deste. O que este capítulo entrega é o tamanho de cada
um, medido.

---

## Como reproduzir

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python src/modelo.py            # comparação, calibração, importâncias, modelo final
PYTHONIOENCODING=utf-8 python src/modelo.py --busca    # refaz as 149 combinações das quatro grades
PYTHONIOENCODING=utf-8 python src/modelo.py --poda     # a tabela da decisão 5, com as duas réguas
```

**O que conferir para saber que deu certo:**

1. `HistGB regularizado` vence com AuROC OOT 0,7410 e queda de treino para teste abaixo de 0,08.
   Queda acima de 0,20 significa que a regularização não foi aplicada.
   A Random Forest ajustada fica logo atrás, em 0,7353 — se a diferença aparecer muito maior que
   isso, os baselines voltaram a rodar sem busca de hiperparâmetros.
2. A calibração sobe o AuROC para 0,7434 e mantém o Brier em 0,0616.
3. O modelo final sai com PD média 0,0830 contra 0,0826 observada e **máximo abaixo de 0,90** — se
   aparecer 1,0000, a calibração voltou para isotônica.
4. `artefatos/modelo_pd.joblib` (~1,2 MB) e `artefatos/modelo.json` com seed, versões e a grade
   vencedora.

Com `--busca`, os vencedores das quatro grades têm de coincidir com `MELHORES` e
`MELHORES_BASELINES` no código; se divergirem, o script imprime `DIVERGE do código` em vez de
seguir em silêncio.
