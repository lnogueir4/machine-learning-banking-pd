# 03 — Features: preparar os dados sem contaminá-los

> Capítulo anterior: [02 — Exploração](02-exploracao.md) · Próximo: [04 — Modelo](04-modelo.md)
> Código: [`src/features.py`](../src/features.py) · Evidência: [`notebooks/02-decisoes-features.py`](../notebooks/02-decisoes-features.py)

## O que este passo resolve

Um modelo de crédito não recebe a planilha crua. Antes do treino é preciso decidir o que fazer com
cada informação que falta, como transformar texto (`ocupacao`, `canal_originacao`) em número, e se
as grandezas precisam ser colocadas em escala comparável. São decisões pequenas que, somadas,
mudam o resultado — e uma delas, se feita na ordem errada, invalida a validação inteira.

Este capítulo também resolve um problema específico deste desafio: **a Base C não tem parcela**.
As bases A e B são contratos fechados, com taxa e parcela registradas. A Base C são propostas, e
quem define taxa e parcela somos nós, através da política. Uma das variáveis do modelo é
`comprometimento_renda` = parcela ÷ renda. Ela simplesmente não existe na base onde a política vai
operar, e precisa ser reconstruída.

### Dois conceitos, para quem chega agora

**Vazamento de pré-processamento** é o primo discreto do vazamento de variável. Se você calcula a
mediana da renda usando a base inteira e depois separa treino e teste, a mediana usada para
preencher os ausentes do treino já carrega informação do teste. O modelo parece melhor do que é, e
não há mensagem de erro. A defesa é o `Pipeline` do scikit-learn: ele guarda a imputação como uma
etapa que aprende no `fit` e só aplica no `transform`.

**Tabela Price** é o sistema de amortização usado em financiamento de veículo no Brasil: parcelas
iguais do começo ao fim, em que a fatia de juros cai e a de amortização sobe. A parcela sai de
`PV · i / (1 − (1+i)^−n)`.

---

## Decisões, com a alternativa descartada

Todas as medidas de seleção abaixo usam validação cruzada de 5 dobras **dentro da janela de treino**
(2022-2023, 6.670 contratos, PD 8,80%). A safra de 2024 aparece como confirmação out-of-time, nunca
como critério de escolha — a razão está no [capítulo 04](04-modelo.md), decisão 5.

### 1. Não criar variáveis novas

A tentação natural depois da exploração é engenharia de atributos: razões, interações, agregados.
Testei sete candidatas, todas calculáveis também na Base C.

| Conjunto | AuROC CV | ±dp | AuROC OOT 2024 | ΔCV |
|---|---:|---:|---:|---:|
| **17 features (baseline)** | **0,7249** | 0,0197 | **0,7410** | — |
| + `entrada_sobre_renda` | 0,7210 | 0,0211 | 0,7366 | −0,0039 |
| + `financiado_sobre_renda` | 0,7186 | 0,0259 | 0,7395 | −0,0064 |
| + `bem_sobre_renda` | 0,7214 | 0,0221 | 0,7397 | −0,0035 |
| + `score_por_restricao` | 0,7195 | 0,0198 | 0,7387 | −0,0054 |
| + `pressao_bureau` | 0,7240 | 0,0197 | 0,7427 | −0,0009 |
| + `estabilidade_emprego` | 0,7192 | 0,0223 | 0,7376 | −0,0057 |
| + `idade_veiculo_no_fim` | 0,7254 | 0,0211 | 0,7439 | +0,0005 |
| + todas as sete | 0,7170 | 0,0196 | 0,7368 | −0,0080 |

Seis das sete pioram a validação cruzada. A sétima, `idade_veiculo_no_fim`, melhora em **0,0005** —
um quarentavo do desvio padrão da própria medida. Não é ganho, é o segundo decimal do ruído.

A leitura não é "engenharia de atributos não funciona". É que o sinal desta base já foi medido no
capítulo anterior: IV total 0,99, maior variável isolada 0,17. Não há estrutura escondida esperando
ser combinada, e gradient boosting já constrói interações por conta própria. **Alternativa
descartada:** manter `idade_veiculo_no_fim` porque o número é positivo. Cada variável a mais é uma
a justificar na defesa, monitorar em produção e calcular na Base C — variável que não paga o
próprio custo sai.

### 2. Reconstruir `comprometimento_renda` por Price, em vez de deixá-la vazia

A Base C não traz parcela. A primeira versão do `mapear_base_c()` deixava a variável como `NaN`.
Medi o custo disso no análogo out-of-time — treinar em 2022-23 e aplicar em 2024 com a coluna
adulterada para imitar o que a Base C entrega:

| `comprometimento_renda` na aplicação | AuROC OOT | PD prevista |
|---|---:|---:|
| real (parcela contratada) | 0,7410 | 8,69% |
| **`NaN` — o que a Base C entregava** | **0,7232** | **7,80%** |
| Price à taxa mediana do treino (1,59% a.m.) | **0,7418** | 8,60% |
| Price à taxa do p90 (1,76% a.m.) | 0,7428 | 8,71% |
| sem juros (financiado ÷ prazo) | 0,7350 | 8,04% |
| *(PD observada em 2024)* | — | *7,18%* |

Duas conclusões. Primeira: deixar `NaN` custa 0,018 de AuROC — muito mais do que qualquer ganho que
a engenharia de atributos ofereceu. A razão é a mesma da variável proibida do capítulo 01, em versão
branda: a coluna tem **0% de ausentes no treino**, então o modelo não tem uma folha de ausente
treinada para ela; pedir que julgue 5.000 propostas todas com a coluna vazia é pedir uma
extrapolação que ele não tem como fazer.

Segunda: a reconstrução é *indistinguível* da parcela real (0,7418 contra 0,7410). Ela funciona
porque a Base A foi gerada por Price — a fórmula reproduz a `parcela_mensal` registrada com erro
relativo mediano de 2,3 × 10⁻⁶ — e porque a carteira antiga mal diferenciava preço: p10 = 1,43% e
p90 = 1,76% a.m. Errar a taxa de ponta a ponta move o AuROC em 0,0010.

**Alternativa descartada:** aproximar a parcela por `valor_financiado ÷ prazo`, ignorando juros.
É mais simples e dispensa taxa de referência, mas entrega 0,7350 — perde um terço do ganho.

### 3. O laço circular do score, e como ele se rompe

Para dar um score preciso é preciso a parcela. Para ter a parcela é preciso a taxa. A taxa depende
da faixa de risco, que vem do score. É circular, e é assim em qualquer banco que pratica preço por
risco. A saída padrão do mercado é iterar:

```
passada 1: condições desejadas + taxa de referência -> PD -> faixa 1-10
passada 2: taxa/prazo/entrada ofertados pela política -> PD final -> decisão
```

Duas passadas bastam porque a dispersão de taxa é estreita — a tabela acima mostra que a diferença
entre a mediana e o p90 vale 0,0010 de AuROC. `taxa_referencia()` devolve a mediana da janela de
treino, 1,587% a.m., e não é digitada no código: é lida da Base A a cada execução.

### 4. `NaN` preservado para a árvore, imputado para o modelo linear

Os ausentes do desafio são conhecidos: `tempo_emprego_meses` 11,69%, `renda_mensal_declarada`
7,63%, `score_bureau` 3,42% (percentuais da janela de treino; B e C são praticamente iguais).

| Configuração | AuROC CV | ±dp | AuROC OOT |
|---|---:|---:|---:|
| **HistGB, `NaN` preservado + ordinal** | **0,7249** | 0,0197 | **0,7410** |
| HistGB, imputação pela mediana + ordinal | 0,7238 | 0,0241 | 0,7398 |
| Logística, mediana + one-hot + padronização | 0,6520 | 0,0312 | 0,6553 |

O `HistGradientBoostingClassifier` aprende, em cada corte, para que lado mandar o ausente. Isso é
estritamente mais informativo do que substituir por mediana, que apaga a distinção entre "renda de
R$ 5.222" e "renda não declarada". A vantagem é pequena (+0,0011 na CV, +0,0012 no OOT) e, sozinha,
não decidiria nada — mas as duas réguas apontam para o mesmo lado, e preservar o ausente é também
a opção que não inventa dado.

A logística não aceita `NaN` e lê código ordinal como grandeza, então recebe o tratamento clássico:
mediana (não média, por causa da cauda longa de renda e valor do bem), one-hot com `drop="first"` e
padronização. Ela não é candidata a vencer; é o **benchmark interpretável** cujos coeficientes
entram na defesa.

### 5. Treinar com o dado como ele é, porque a Base B também é assim

Há um detalhe fino: na Base A, `comprometimento_renda` está preenchido **mesmo nas linhas em que a
renda declarada é ausente** — a renda implícita (`parcela ÷ comprometimento`) tem mediana 5.193
contra 5.222 das observadas, ou seja, a renda existia e foi mascarada só naquela coluna. Na Base C
não temos essa sorte: sem a renda, não há como calcular a razão, e 7,9% das propostas ficam com
`NaN` numa coluna que o modelo viu 100% preenchida.

Testei a solução purista — reconstruir o `comprometimento_renda` do treino do mesmo jeito que ele
será reconstruído na aplicação, para que as duas pontas tenham a mesma forma:

| Estratégia | AuROC OOT |
|---|---:|
| treino completo → aplicação completa (irreal na Base C) | 0,7410 |
| treino completo → aplicação como a Base C (`NaN` onde falta renda) | 0,7418 |
| treino completo → aplicação com renda imputada antes da razão | 0,7409 |
| treino reconstruído para imitar a Base C → aplicação como a Base C | **0,7442** |

**A métrica não decide isto, e é importante dizer por quê.** Os quatro números cabem numa faixa de
0,0033, contra um desvio padrão de validação de 0,02. Uma versão anterior deste teste, com 18
variáveis e hiperparâmetros não ajustados, dava vantagem de 0,014 para o lado *oposto*. Efeito que
troca de sinal quando se mexe em outra coisa não é efeito.

Quando a evidência empata, decide o princípio — e aqui o princípio é o destino do modelo: **a Base B
é uma base de contratos fechados e traz a `parcela_mensal` contratada.** É nela que os 40 pontos de
modelo são apurados. Treinar com a parcela reconstruída desalinharia o treino justamente da base
pontuada, para alinhá-lo à outra. Então o treino usa o dado como ele é, e o descasamento fica
concentrado na Base C — onde a medição diz que ele não custa nada (0,7410 → 0,7418).

**Alternativa descartada:** escolher a linha de maior AuROC da tabela. Seria selecionar pela
terceira casa decimal num out-of-time já consultado dezenas de vezes; o [capítulo 04](04-modelo.md)
mostra o que acontece quando isso é feito com convicção.

---

## O código que importa

A matriz sempre passa pela guarda antivazamento — não como cerimônia, mas porque é a única barreira
que separa o pipeline do erro que custa o desafio:

```python
def matriz(df: pd.DataFrame) -> pd.DataFrame:
    faltando = [f for f in FEATURES if f not in df.columns]
    if faltando:
        raise KeyError("Colunas ausentes para montar a matriz: " + ", ".join(faltando) + ...)
    return df[validar_features()].copy()      # validar_features() lê o dicionário oficial
```

A reconstrução da parcela, que é o que torna a Base C pontuável:

```python
def preparar_aplicacao(base_c, taxa_am=None, prazo_meses=None, valor_entrada=None):
    taxa = taxa_referencia() if taxa_am is None else taxa_am     # 1ª passada: 1,587% a.m.
    df = mapear_base_c(base_c, prazo_meses=prazo_meses, valor_entrada=valor_entrada)
    parcela = parcela_price(df["valor_financiado"], taxa, df["prazo_meses"])
    df["comprometimento_renda"] = parcela / df["renda_mensal_declarada"]
    return df
```

Os dois pré-processadores declaram as colunas **explicitamente**, sem `remainder="passthrough"`.
Com `remainder`, a ordem de saída depende da ordem de entrada e as importâncias do modelo passam a
ser lidas com nomes trocados — erro silencioso e difícil de perceber:

```python
def preparador_arvore() -> ColumnTransformer:
    return ColumnTransformer([
        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CATEGORICAS),
        ("num", "passthrough", NUMERICAS),      # NaN chega intacto ao HistGB, de propósito
    ])
```

E o `Pipeline`, que é onde a promessa de "ajustar só no treino" deixa de ser disciplina pessoal e
vira propriedade do objeto:

```python
def montar_pipeline(estimador, linear: bool = False) -> Pipeline:
    preparador = preparador_linear() if linear else preparador_arvore()
    return Pipeline([("preparar", preparador), ("modelo", estimador)])
```

---

## Os números que saíram

```
17 features | 4 categóricas | 13 numéricas
taxa de referência da 1ª passada: 1.5870% a.m.

Base A              10,000 x 17  colunas  OK
Base B               3,000 x 17  colunas  OK
Base C (preparada)   5,000 x 17  colunas  OK

coluna                       treino        B        C
renda_mensal_declarada        7.63%    8.60%    7.90%
tempo_emprego_meses          11.69%   11.87%   11.60%
score_bureau                  3.42%    3.07%    3.50%
comprometimento_renda         0.00%    0.00%    7.90%

árvore : 17 colunas | NaN remanescentes: 1517
linear : 24 colunas | NaN remanescentes: 0
```

Os 1.517 `NaN` que sobrevivem ao preparador de árvore não são um defeito: são a decisão 4 em
funcionamento. O preparador linear zera os dele, como tem de ser.

### O achado que só apareceu agora: o terceiro corte da política antiga

Com `comprometimento_renda` finalmente calculável na Base C, a comparação de domínios revelou um
limite que o capítulo 02 não podia ver:

| | treino (2022-23) | Base C (condições desejadas) |
|---|---:|---:|
| acima de 30% da renda | 20,85% | 31,48% |
| acima de 35% | 11,18% | 22,10% |
| acima de 40% | 4,44% | 15,64% |
| **acima de 45%** | **0,00%** | **11,32%** |
| máximo observado | **0,4493** | 1,6286 |

Zero contratos acima de 45% em 10.000 não é acaso amostral: é uma **regra**. A política antiga
recusava — ou reestruturava — qualquer proposta que comprometesse mais de 45% da renda. Somando aos
dois cortes já recuperados no capítulo 02:

| Corte da política de 2022 | Propostas de C atingidas |
|---|---:|
| `score_bureau < 460` | 27,7% (1.384) |
| `qtd_restricoes_ativas > 2` | 28,1% (1.404) |
| `comprometimento_renda > 44,9%` | 11,3% (566) |
| **ao menos um dos três** | **42,6% (2.130)** |

**Mas o terceiro corte é diferente dos outros dois, e essa é a boa notícia do capítulo.** Score de
bureau e restrições ativas são atributos do proponente: não há nada que a AutoCred possa fazer para
mudá-los. Comprometimento de renda é consequência da **oferta** — e oferta é exatamente a alavanca
que a política controla:

| Condição oferecida às 566 propostas acima do teto | ainda acima de 44,9% |
|---|---:|
| condições desejadas pelo cliente | 566 |
| prazo esticado para 60 meses | 174 |
| prazo 60 meses + entrada mínima de 30% | **66** |

De 566 propostas fora do domínio, 500 podem ser trazidas para dentro dele mudando a estrutura da
operação, sem relaxar risco — ao contrário: mais entrada reduz LTV, que reduz PD e LGD ao mesmo
tempo. Isso deixa de ser um problema de suporte amostral e vira desenho de produto, e é a primeira
peça concreta da resposta à maior pendência do projeto, a região sem suporte histórico.

---

## Como reproduzir

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python src/features.py                    # diagnóstico do pré-processamento
PYTHONIOENCODING=utf-8 python notebooks/02-decisoes-features.py  # as cinco tabelas deste capítulo
```

**O que conferir para saber que deu certo:**

1. As três bases montam matriz `n × 17`. Se a Base C falhar, `preparar_aplicacao()` não foi chamada.
2. `comprometimento_renda` aparece com 7,90% de ausentes em C e 0,00% no treino — se aparecer
   100% em C, a reconstrução por Price não rodou.
3. O erro relativo do Price contra a parcela registrada fica na ordem de 10⁻⁶.
4. O preparador de árvore termina com 1.517 `NaN` remanescentes (esperado); o linear, com zero.
5. Nenhuma das sete derivadas supera o baseline por mais que o desvio padrão da validação.

Se qualquer coluna proibida entrar em `FEATURES`, os dois scripts **não rodam**:
`validar_features()` levanta `VazamentoDetectado` antes de qualquer `fit`.
