# 06 — Risco: de probabilidade para reais

> Capítulo anterior: [05 — Score](05-score.md) · Próximo: [07 — Política](07-politica.md)
> Código: [`src/risco.py`](../src/risco.py) · Parâmetros: [`bases/AutoCred_parametros_ead_lgd.xlsx`](../bases/AutoCred_parametros_ead_lgd.xlsx)

## O que este passo resolve

Até aqui o projeto sabe dizer, para cada proposta, a chance de o contrato quebrar nos doze meses
seguintes, e sabe arrumar essas chances em dez faixas. Nenhum desses números é dinheiro.

Duas propostas com a mesma PD de 8% podem custar coisas muito diferentes ao banco. Uma é um
financiamento de R$ 15 mil de um carro de dois anos com 40% de entrada; a outra é R$ 90 mil num
veículo de dez anos com 5% de entrada. Se as duas quebrarem, a primeira deixa um rombo pequeno
sobre um bem fácil de vender, e a segunda deixa um rombo grande sobre um bem que se desvaloriza
mais rápido do que a dívida cai. **Preço não se faz com probabilidade; se faz com perda esperada.**

```
Perda esperada = PD  ×  EAD  ×  LGD
                 │       │       └── que fração disso não volta
                 │       └────────── quanto ainda se deve no momento em que quebra
                 └────────────────── qual a chance de quebrar
```

O desafio entrega EAD e LGD prontos, em tabelas de consulta: só a PD é modelada. Isso reduz o
trabalho, não o elimina — **parâmetro entregue ainda precisa ser lido, conferido e encaixado no
lugar certo**. Este capítulo é sobre as três decisões que sobram depois que alguém diz "está tudo
na planilha".

### Três conceitos, para quem chega agora

- **EAD** (*exposure at default*) é o saldo que o cliente ainda deve no instante em que o contrato
  vira default. Não é o valor emprestado: parte já foi paga. Mas também não é só o saldo da
  planilha de amortização — quem chega a 90 dias de atraso deixou três parcelas vencidas, e elas
  entram na conta. É por isso que o **fator de EAD passa de 1** nos contratos longos que quebram
  cedo: deve-se mais do que se pegou emprestado.
- **LGD** (*loss given default*) é a fração do EAD que não volta depois de retomar e vender o
  veículo, descontados os custos do processo. No varejo de veículos brasileiro, LGD entre 0,40 e
  0,90 é o território usual; a tabela do desafio vai de **0,412** (carro novo, entrada alta) a
  **0,908** (carro velho, quase sem entrada).
- **LTV** (*loan to value*) é o quanto se financia sobre o valor do bem. LTV de 90% significa 10%
  de entrada. É a variável que aparece nas duas tabelas, porque governa as duas pontas: quanto se
  deve e quanto o bem cobre.

## Decisões, com a alternativa descartada

### Decisão 1 — a fronteira das faixas de LTV foi decidida por evidência, não pelo rótulo

As duas tabelas são indexadas por faixas de LTV escritas assim: `até 60%`, `60% a 70%`, `70% a 80%`,
`80% a 90%`, `acima de 90%`. A leitura natural de "até 60%" é `ltv <= 0,60`, e ninguém perguntaria
duas vezes — exceto que a planilha não diz onde cai um LTV de exatamente 0,80.

A pergunta parece irrelevante e não é, por um motivo específico do desafio: **a entrada é alavanca
de política**. Vamos exigir percentuais de entrada de propósito, e é tentador mirar exatamente em
80% de LTV para cair na faixa melhor. Se a convenção for a outra, essa exigência não compra nada.

Como a tabela é a média dos realizados da própria Base A, dá para descobrir a convenção
reproduzindo as 20 células nas duas hipóteses e vendo qual fecha:

| convenção testada | erro máximo nas 20 células |
|---|---|
| limite **superior** fechado — `até 60%` = `ltv <= 0,60` | 0,00338 |
| limite **inferior** fechado — `até 60%` = `ltv < 0,60` | **0,00048** |

0,00048 é o arredondamento da própria tabela, que tem três casas decimais. A convenção é a segunda:
as faixas são `[0; 0,60)`, `[0,60; 0,70)`, `[0,70; 0,80)`, `[0,80; 0,90)`, `[0,90; ∞)`. **LTV de
exatamente 80% cai na faixa pior, não na melhor.** A política tem de furar o corte, não encostar
nele.

O que decidiu foram seis contratos da Base A que caem exatamente em 0,80 e 0,90 — evidência magra
em número, mas é a única que existe, e o custo de errar é assimétrico: exigir 20% de entrada
achando que muda de faixa quando não muda é perder aceite sem comprar nada em troca.

### Decisão 2 — o EAD é calculado pela fórmula fechada, avaliada na taxa que *nós* vamos cobrar

A aba `Leia-me` descreve o EAD em uma linha: *saldo devedor pela Tabela Price no mês do default,
somado às 3 parcelas vencidas que caracterizam o atraso de 90 dias*. Isso é uma fórmula, não uma
tabela — e vale a pena reconstruí-la, porque quem quebra no mês `m` parou de pagar em `m − 3`:

```
EAD = saldo_Price(após m − 3 parcelas pagas)  +  3 × parcela
```

Reconstruída, ela reproduz o campo `ead_realizado` dos 826 defaults da Base A com **erro máximo de
meio centavo** — 100% dos contratos dentro de um centavo. Não é aproximação: é a mesma fórmula que
gerou a base, e o resíduo é o arredondamento do campo.

Isso muda o que o EAD é. O lookup trata o fator como função de `(prazo, LTV)`. A fórmula mostra que
ele é função de `(taxa, prazo, mês do default)` e **não depende de LTV** — LTV não aparece nela em
lugar nenhum. As duas consequências:

**(a) A coluna de LTV da tabela de EAD é ruído, não risco.** A amplitude do fator dentro de cada
linha de prazo é de 0,005 a 0,033, e o desvio de cada célula em relação à média da sua linha tem
correlação de **−0,896** com o desvio do mês médio do default daquela célula. Ou seja: o que separa
uma coluna da outra é qual delas sorteou defaults mais cedo — e mês do default é informação que não
existe na concessão. As células de 24 meses têm entre 11 e 28 contratos cada.

**(b) A tabela está congelada na taxa da carteira antiga.** Ela foi medida em contratos que cobravam
1,59% a.m. de mediana (p10 1,43%, p90 1,76% — ver [03 — Features](03-features.md)). Juro alto
amortiza devagar, e saldo devedor maior é exposição maior:

| taxa a.m. | 24 meses | 36 meses | 48 meses | 60 meses |
|---|---|---|---|---|
| 1,59% (a taxa da tabela) | 1,0092 | 1,0245 | 1,0320 | 1,0365 |
| 2,50% | 1,0377 | 1,0539 | 1,0617 | 1,0661 |
| 3,00% | 1,0534 | 1,0701 | 1,0779 | 1,0823 |
| 3,50% (teto de CET do desafio) | 1,0692 | 1,0863 | 1,0941 | 1,0983 |
| *lookup oficial (média das colunas)* | *0,9986* | *1,0196* | *1,0322* | *1,0400* |

Na linha de 1,59% a fórmula e o lookup coincidem — é a prova de que são a mesma coisa. No teto de
CET, o fator de 48 meses sobe de 1,0322 para 1,0941: **+6,0% de exposição** que o lookup não vê.

Por isso `ead()` aceita a taxa ofertada e, quando ela é informada, usa a fórmula. A alternativa —
aplicar o lookup e seguir — é otimista exatamente onde a política vai operar, e o erro é
sistemático: quanto mais caro cobrarmos, mais o lookup subestima a exposição. Há um laço aqui
(o preço muda o EAD, que muda a perda esperada, que muda o preço) e ele se resolve sem iteração no
capítulo 07, onde cada taxa candidata é avaliada com o EAD que ela mesma produz.

### Decisão 3 — o ajuste de avalista é aplicado recentrado, com o efeito medido dentro da célula

A instrução oficial cabe numa linha: *some −0,061 à LGD da tabela quando o contrato tem avalista*.
Aplicá-la ao pé da letra é a coisa mais natural do mundo, e é o que estava escrito na primeira
versão deste módulo. Está errado, e o erro tem duas partes que se disfarçam uma à outra.

**Primeira parte — o −0,061 é uma diferença *bruta* de médias.** Entre os 826 defaults, quem tinha
avalista realizou LGD média de 0,6468 contra 0,7078 de quem não tinha: diferença de −0,0610, que é
exatamente o número oficial. Mas avalista não se distribui por igual pela tabela: é 19,7% da
carteira e **32,5%** da célula de LTV acima de 90% em veículo de 0 a 2 anos, onde a LGD já é alta.
Medido *dentro* da mesma célula, o efeito é **−0,0790**, com IC de 95% de [−0,1009; −0,0571]. Os
dois números não se contradizem — o oficial cabe no intervalo. A média bruta é menor porque
contamina o efeito do avalista com a composição de células.

**Segunda parte — a tabela não é a LGD de quem não tem avalista.** Ela é a média da carteira
inteira, com os 19,7% de avalistas já dentro. Somar o ajuste sobre ela conta o efeito duas vezes
para um grupo e nenhuma vez para o outro.

Os dois erros têm sinais opostos e se cancelam — mas só para a minoria com avalista:

| regra aplicada | resíduo, sem avalista | resíduo, com avalista | LGD média |
|---|---|---|---|
| tabela crua, sem ajuste nenhum | +0,0157 | −0,0634 | 0,6957 |
| oficial: `tabela + (−0,061)` se avalista | +0,0157 | −0,0024 | 0,6837 |
| **em uso:** `tabela − 0,079 × (avalista − 0,197)` | **+0,0001** | **+0,0000** | **0,6957** |
| *LGD realizada* | | | *0,6958* |

(resíduo = LGD realizada − LGD aplicada; positivo significa perda não provisionada)

A regra oficial acerta o grupo com avalista por cancelamento de dois erros e deixa **+0,016 de perda
não provisionada em 84% da carteira**. A versão em uso é a mesma coisa escrita com os dois números
no lugar certo: o efeito onde ele foi medido, e a centragem explícita. Na prática ela soma +0,0156
a quem não tem avalista e −0,0634 a quem tem — preservando a média da tabela, que é o que o
patrocinador do parâmetro de fato mediu.

Isso importa mais na Base C do que na A: a proporção de avalistas sobe de 16,0% para **25,3%**, e a
maioria sem avalista — a que a regra literal subestima — continua sendo a maioria.

`lgd(..., oficial=True)` reproduz a instrução literal a qualquer momento, e o capítulo cita as duas.

### Decisão 4 — EAD e LGD não são modelados, mesmo havendo 826 observações realizadas

A Base A traz `ead_realizado`, `lgd_realizado` e `perda_financeira` para todos os defaults. Com 826
linhas dá para ajustar uma regressão de LGD e provavelmente ganhar alguma coisa sobre um lookup de
20 células. Não foi feito, por três razões em ordem de peso:

1. **O enunciado é explícito**: "estes parâmetros são dados. Neste desafio os grupos modelam apenas
   a PD". Otimizar o que o patrocinador declarou como dado é otimizar contra a régua de avaliação.
2. **A tabela já é a resposta certa para essa amostra.** Reproduzimos as 20 células da LGD com erro
   máximo de 0,00049 e as 20 do fator de EAD com 0,00048. Não há nada a calibrar: qualquer modelo
   teria as mesmas 826 linhas e uma variância a mais.
3. **Um modelo de LGD ajustado em 826 linhas herdaria o viés de aprovados** da mesma forma que o
   modelo de PD, só que sem o contrapeso de um teste out-of-time.

O que **foi** feito é diferente de modelar: ajustar *como o parâmetro é usado* — a fronteira da
faixa (decisão 1), o regime de taxa em que ele foi medido (decisão 2) e a centragem do ajuste
(decisão 3). Nenhuma das três troca o número entregue por um número nosso.

### Decisão 5 — o horizonte é o da PD: doze meses, sem trazer a perda a valor presente

A LGD da tabela vem de um *workout* de 24 meses: o dinheiro que volta, volta ao longo de dois anos
depois do default. A rigor, uma perda que se materializa no mês 30 vale menos hoje do que o mesmo
valor no mês 7, e um cálculo de provisão traria tudo a valor presente.

Não é o que está feito aqui, e a razão é de coerência, não de preguiça: o desafio apura ROI sobre
uma janela de doze meses e a PD modelada é `default_90_12`. Descontar a perda e não descontar a
receita inclinaria a conta para um lado só. Contrato de 48 meses tem risco depois do 12º mês — ele
não entra nesta conta, e não deveria: o que está sendo precificado é a janela que a competição mede.
Fica registrado como limitação, não como decisão silenciosa.

## O código que importa

A conversão de escala inteira mora em três funções curtas. A primeira é a fórmula fechada do EAD,
que é o que permite sair do lookup:

```python
def ead_no_mes(valor_financiado, taxa_am, prazo_meses, mes_default, atraso=ATRASO_MESES):
    """EAD exato de um contrato que quebra no mês `mes_default`."""
    pagas = np.asarray(mes_default, dtype="float64") - atraso   # parou de pagar 3 meses antes
    saldo = saldo_price(valor_financiado, taxa_am, prazo_meses, pagas)
    return saldo + atraso * parcela_price(valor_financiado, taxa_am, prazo_meses)
```

Na concessão o mês do default é desconhecido, então o fator é a média sobre a distribuição oficial
de `Distribuicao_Mes_Default` (média 6,89 meses) — avaliada na taxa que a política ofertar:

```python
def fator_ead_exato(taxa_am, prazo_meses, atraso=ATRASO_MESES):
    parcela_unitaria = parcela_price(1.0, i, n)          # por R$ 1 financiado
    total = 0.0
    for mes, frequencia in distribuicao_mes_default().items():
        pagas = max(int(mes) - atraso, 0)
        saldo = parcela_unitaria * (1 - (1 + i) ** -(n - pagas)) / i
        total = total + frequencia * (saldo + atraso * parcela_unitaria)
    return total
```

E a LGD, onde o ajuste de avalista aparece como uma expressão só — a centragem e o efeito lado a
lado, para que a decisão 3 seja legível no código e não só no documento:

```python
AJUSTE_AVALISTA_OFICIAL = -0.061   # a instrução, ao pé da letra
EFEITO_AVALISTA = -0.079           # o mesmo efeito medido dentro da célula
SHARE_AVALISTA_TABELA = 0.1973     # o que a tabela já embute

ajuste = (
    AJUSTE_AVALISTA_OFICIAL * tem            # oficial=True
    if oficial
    else EFEITO_AVALISTA * (tem - SHARE_AVALISTA_TABELA)
)
```

A fronteira de LTV da decisão 1 é um `side="right"` num único ponto do módulo, pelo mesmo motivo
que a inversão da escala de score é única em `score.py`: convenção duplicada é convenção que um dia
diverge de si mesma.

```python
def indice_ltv(ltv):
    """Posição da faixa de LTV, 0 a 4. Limite **inferior** fechado."""
    return np.searchsorted(np.asarray(CORTES_LTV), np.asarray(ltv), side="right")
```

## Os números que saíram

### A cadeia inteira contra o que de fato aconteceu

É o único teste que fecha as três peças de uma vez, e o que autoriza usar a perda esperada como
piso de preço. A PD usada é a *out-of-fold* de [`src/score.py`](../src/score.py) — a PD do modelo
final sobre as próprias linhas de treino acertaria o total por memória.

| peça | esperado | realizado | razão |
|---|---|---|---|
| PD: soma das probabilidades | 828 | 826 defaults | 1,0019 |
| EAD: exposição nos defaults | R$ 27.669.442 | R$ 27.662.361 | 1,0003 |
| LGD: perda sobre o EAD real | R$ 19.336.648 | R$ 19.057.787 | 1,0146 |
| **PD × EAD × LGD (em uso)** | **R$ 19.292.829** | **R$ 19.057.787** | **1,0123** |
| PD × EAD × LGD (regra oficial) | R$ 18.956.205 | R$ 19.057.787 | 0,9947 |

Sobre R$ 346.684.813 de volume financiado, a perda realizada foi de **5,50% do volume**.

O total sozinho não arbitra convenção nenhuma — erro de 1% em qualquer das três peças mexe 1% no
produto, e elas se compensam. Por isso o teste vem aberto. PD e EAD fecham em 0,2% e 0,03%. A folga
de 1,2% é inteira da LGD, e **não é viés de nível**: por contrato o resíduo médio é +0,0001.
Ponderado pelo EAD ele vira −0,0101, porque o quinto mais caro dos defaults realiza LGD de 0,664
contra 0,702 de tabela — a tabela não tem dimensão de valor, e perda é ponderada por dinheiro.
Provisionamos 1,2% a mais do que aconteceu. É o lado certo de errar quando o número vira preço.

### O que a política recebe

Perda esperada das 5.000 propostas da Base C, nas condições desejadas pelo cliente e à taxa de
referência — a primeira passada, antes de qualquer decisão nossa:

| faixa | n | PD média | LGD média | volume (R$) | perda esperada (R$) | % do volume | ÷ 12 |
|---|---|---|---|---|---|---|---|
| 10 | 629 | 3,12% | 0,665 | 24.896.232 | 527.613 | 2,12% | 0,18% |
| 9 | 456 | 4,07% | 0,676 | 16.825.095 | 477.457 | 2,84% | 0,24% |
| 8 | 436 | 4,94% | 0,685 | 15.199.575 | 529.988 | 3,49% | 0,29% |
| 7 | 380 | 6,02% | 0,701 | 14.094.910 | 614.094 | 4,36% | 0,36% |
| 6 | 421 | 7,47% | 0,701 | 15.011.709 | 815.802 | 5,43% | 0,45% |
| 5 | 320 | 9,50% | 0,710 | 11.162.234 | 771.384 | 6,91% | 0,58% |
| 4 | 364 | 12,38% | 0,713 | 11.936.211 | 1.091.325 | 9,14% | 0,76% |
| 3 | 567 | 17,61% | 0,720 | 18.043.190 | 2.339.088 | 12,96% | 1,08% |
| 2 | 714 | 25,28% | 0,709 | 20.950.713 | 3.868.067 | 18,46% | 1,54% |
| 1 | 713 | 43,10% | 0,729 | 18.935.640 | 6.194.068 | **32,71%** | **2,73%** |

Carteira inteira, sem política nenhuma: **10,31% do volume** de perda esperada.

Três leituras que o capítulo 07 herda:

1. **A LGD quase não separa as faixas** — vai de 0,665 na faixa 10 a 0,729 na faixa 1, uma variação
   de 10%. Quem separa é a PD, que varia 14 vezes. A perda esperada é a PD com um multiplicador
   quase constante: é a PD que precifica.
2. **A última coluna é um piso otimista.** Dividir a perda de 12 meses por 12 supõe que os juros
   correm sobre o valor financiado inteiro; correm sobre o saldo devedor, que cai a cada parcela. O
   preço de verdade sai do capítulo 07, e será maior que esta coluna.
3. **A faixa 1 já está decidida, e não por preço.** Mesmo pelo piso otimista, são 2,73% a.m. só de
   perda esperada contra um teto de CET de 3,50% a.m. — não sobra espaço para funding, operação e
   margem. Somado ao que o capítulo 05 já havia registrado (713 propostas cuja PD prevista média de
   43,1% é extrapolação de árvore, não medição), a faixa 1 é decisão de **regra**: negar, ou exigir
   entrada que a mova de faixa. Precificá-la seria fingir que o número é conhecido.

## O que deu errado

**A correção do avalista nasceu errada, e a auditoria da própria sessão a derrubou.** A primeira
versão deste módulo aplicava `tabela + (−0,061) × (avalista − 0,197)`: identificou corretamente que
a tabela é uma média de mistura e recentrou o ajuste, mas manteve o −0,061, que é uma média bruta.
As duas metades do erro precisavam ser corrigidas juntas. Corrigir só a centragem piorou o grupo
com avalista — o resíduo saiu de −0,0024 para −0,0144 — e a cadeia inteira passou a superestimar
1,4% em vez de 1,2%.

O que expôs isso foi decompor a cadeia peça por peça em vez de olhar o total. O total comparava
1,012 contra 0,995 e sugeria que a regra literal era *melhor*; a decomposição mostrou que PD e EAD
fechavam em 0,2% e que toda a discussão estava na LGD, onde o teste certo é o resíduo por grupo, e
não o agregado. **Agregado que fecha esconde dois erros que se cancelam** — foi o caso aqui, na
regra oficial, e quase foi o caso na correção.

**Duas armadilhas menores de ferramenta**, registradas porque custaram tempo:

- `\n` dentro de *heredoc* multilinha no shell deste ambiente vira quebra de linha real antes de o
  Python ver o arquivo, produzindo `SyntaxError: unterminated string literal`. Editar Python via
  heredoc só é seguro sem sequências de escape; quando forem necessárias, monte-as com
  `chr(92) + "n"` ou escreva o arquivo direto.
- O primeiro teste da fórmula do EAD usou `parcela_mensal` da base, que vem arredondada em
  centavos, e deu erro máximo de R$ 0,20 — bom o bastante para parecer certo e ruim o bastante para
  parecer aproximação. Recalculando a parcela pela Price, o erro cai para meio centavo e a conclusão
  muda de "reproduz bem" para "é a mesma fórmula". Quando o resíduo de uma reconstrução tem a cara
  do arredondamento de um campo, vale a pena remover o arredondamento antes de concluir.

## Como reproduzir

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python src/risco.py
```

Todos os números deste capítulo saem dessa única execução, nas seções 1 a 8 do relatório. Ela
depende de `artefatos/pd_base_a.csv` (gerado por `src/score.py`) e de `artefatos/modelo_pd.joblib`
(gerado por `src/modelo.py`); se algum faltar, rode-os antes.

**O que conferir para saber que deu certo:**

1. Seção 1: erro máximo da fórmula do EAD abaixo de um centavo, em 100% dos 826 defaults. Se subir
   para dezenas de centavos, a parcela está vindo arredondada da base em vez de recalculada.
2. Seção 2: `side=right` com erro menor que `side=left`. Se inverter, a convenção de fronteira
   mudou e a alavanca de entrada da política precisa ser revista.
3. Seção 5: a linha "em uso" com resíduo de +0,0001 e +0,0000 nos dois grupos, e LGD média de
   0,6957 contra 0,6958 realizada. Resíduo assimétrico entre os grupos significa que a centragem e
   o efeito saíram de sincronia.
4. Seção 7: razões de 1,0019 (PD), 1,0003 (EAD) e 1,0123 (cadeia). Razão fora de ±3% em qualquer
   peça é problema a montante, não aqui.
5. `artefatos/perda_esperada_base_c.csv` com 5.000 linhas e as colunas `id_proposta, faixa,
   valor_financiado, pd, fator_ead, ead, lgd, perda_esperada, perda_pct`, mais `artefatos/risco.json` com as constantes e
   as versões do run.

O CSV de perda por proposta é o insumo direto do próximo módulo, `src/politica.py` — é sobre ele
que as alavancas de taxa, prazo e entrada vão operar no capítulo 07.
