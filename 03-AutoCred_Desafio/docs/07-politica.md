# 07 — Política: de perda esperada para decisão

> Capítulo anterior: [06 — Risco](06-risco.md) · Próximo: [08 — Submissões](08-submissoes.md)
> Código: [`src/politica.py`](../src/politica.py) · Saída: [`artefatos/tabela_politica.csv`](../artefatos/tabela_politica.csv)

## O que este passo resolve

Os seis capítulos anteriores produziram um número por proposta: quanto a AutoCred espera perder se
emprestar àquela pessoa. É uma informação, não uma decisão. Este capítulo transforma o número em
quatro respostas que um analista pode executar amanhã de manhã:

**aprovo? a que taxa? por quanto tempo? com quanta entrada?**

São as únicas quatro alavancas que o desafio permite, e elas se contradizem. Cobrar mais caro
cobre mais perda e afasta o cliente. Exigir mais entrada reduz o risco e reduz o tamanho do
negócio. Encurtar o prazo diminui a exposição e engorda a parcela até inviabilizá-la. Não existe
combinação que seja boa em tudo; existe a combinação que a AutoCred consegue defender.

E há quatro **guardrails** — limites que o desafio impõe e cuja violação corta a nota de política
pela metade:

| Restrição | Limite | O que acontece se quebrar |
|---|---|---|
| Taxa de aprovação | ≥ 35% das 5.000 propostas | nota pela metade |
| CET (custo efetivo total) | ≤ 3,5% ao mês | taxa truncada automaticamente |
| Inadimplência | ≤ 8% dos contratos fechados | nota pela metade |
| Volume originado | ≥ R$ 40 milhões contratados | nota pela metade |

## Três fatos que precisam ser ditos antes de qualquer número

### 1. O ROI do enunciado é uma margem, não um lucro

A fórmula que avalia a política é:

```
ROI anual = [(juros recebidos − perda realizada) / volume financiado] / prazo médio em anos
```

Repare que é um **quociente**. Dobrar a carteira não muda o quociente. Isso tem uma consequência
desconfortável: sem os guardrails, a política ótima seria aprovar o mínimo exigido, cobrar o teto e
deixar a originação secar — o resultado seria excelente por linha e desastroso para a empresa.

O próprio enunciado reconhece isso ao justificar o piso de R$ 40 milhões: ele existe "para evitar
uma solução degenerada que preserve ROI aprovando formalmente muitas propostas, mas imponha preço
e entrada que reduzam drasticamente a contratação efetiva". **É esse piso, e não a margem
desejada, que dita o preço desta política.**

### 2. A mesma fórmula premia prazo longo duas vezes, e cobra zero pelo risco de prazo

O numerador cresce com o prazo, porque numa Tabela Price o saldo devedor amortiza devagar e o juro
incide sobre ele:

| taxa a.m. | 24 meses | 36 meses | 48 meses | 60 meses |
|---|---|---|---|---|
| 1,59% | 10,54% | 10,70% | 10,93% | 11,18% |
| 2,50% | 17,10% | 17,61% | 18,21% | 18,82% |
| 3,50% | 24,73% | 25,81% | 26,97% | 28,11% |

*(juros totais sobre o valor financiado, já anualizados pela divisão por prazo/12)*

E o denominador dilui a perda, que acontece uma vez só, por um prazo maior:

| perda / volume | 24 meses | 36 meses | 48 meses | 60 meses |
|---|---|---|---|---|
| 5,0% | 2,50% | 1,67% | 1,25% | 1,00% |
| 10,0% | 5,00% | 3,33% | 2,50% | 2,00% |

Os dois efeitos apontam para o mesmo lado. Um contrato de 60 meses ganha mais juros por ano *e*
espalha a mesma perda por cinco anos em vez de dois. Como a PD é medida numa janela fixa de 12
meses e não é anualizada, **a fórmula cobra zero pelo risco de alongar o prazo**.

O histórico cobra caro:

| prazo | contratos | default 90/12 | renda mediana |
|---|---|---|---|
| 24 meses | 1.553 | 6,44% | R$ 6.125 |
| 36 meses | 2.572 | 6,42% | R$ 5.305 |
| 48 meses | 3.267 | 7,90% | R$ 5.023 |
| 60 meses | 2.608 | **11,62%** | R$ 4.882 |

Alongar toda a Base C para 60 meses subiria o ROI simulado e levaria a PD média prevista de 0,1432
para 0,1926 (+35%). A decisão está na seção seguinte.

### 3. A intensidade do aceite é desconhecida, e não existe dado para medi-la

O enunciado diz a direção de cada efeito — taxa maior reduz aceite, entrada maior reduz aceite,
prazo menor reduz aceite — e omite a magnitude. Pior: **não há uma única proposta recusada por
cliente em nenhuma das três bases.** As Bases A e B contêm contratos, ou seja, ofertas que já foram
aceitas. A Base C contém propostas, sem desfecho. O dado que mediria a elasticidade não existe.

Como a submissão é única e o simulador é determinístico, também não há como calibrar por tentativa
e erro. A saída adotada aqui é declarar o modelo de aceite de forma explícita, com parâmetros
nomeados, e escolher a política pelo **cenário ruim** em vez do cenário provável.

---

## Decisões, com a alternativa descartada

### Decisão 1 — O prazo ofertado nunca é maior que o pedido

**Alternativa descartada:** alongar todo mundo para 60 meses, que é o que a fórmula de ROI premia.

Três razões, em ordem de força:

1. **É extrapolação do modelo.** Na Base A, quem escolhe 60 meses ganha R$ 4.882 de mediana contra
   R$ 6.125 de quem escolhe 24. O prazo que a pessoa pede carrega informação sobre ela. Quando o
   modelo vê "60 meses" e prevê PD mais alta, boa parte disso é composição, não causa. Impor 60
   meses a quem pediu 24 leva o modelo a uma região que ele nunca observou: gente de renda alta em
   contrato longo é rara na base porque essa combinação não ocorria, não porque fosse segura.
2. **O guardrail de inadimplência não é anualizado.** Ele conta contratos que quebram, e não os
   divide por prazo nenhum. É exatamente o freio que a fórmula de ROI não tem.
3. **Não se defende diante de um conselho.** "Alongamos o prazo de todos os clientes porque o
   denominador da métrica cresce" é a descrição de uma métrica sendo explorada, não de uma
   política de crédito.

A regra implementada permite *encurtar* o prazo por faixa, como alavanca de risco. Na política
escolhida esse recurso acabou não sendo usado: o prazo ofertado é idêntico ao desejado nas 5.000
propostas, e o prazo médio da carteira contratada é de 41,8 meses (ponderado por volume,
que é a convenção usada no denominador do ROI). A alavanca existe no código e
foi testada na grade — simplesmente perdeu para as outras.

### Decisão 2 — O preço é o que entrega um alvo de ROI, resolvido no laço preço-risco

**Alternativa descartada:** taxa única no teto de CET para todo mundo.

A taxa de cada faixa não é escolhida: é **resolvida**. Para cada faixa, o código procura por
bisseção a menor taxa que entrega um alvo de ROI anualizado. Isso é necessário porque a taxa entra
nos dois lados da conta — ela é a receita e, pelo [capítulo 06](06-risco.md), também empurra o EAD
para cima, já que juro alto amortiza devagar e o saldo no mês do default fica maior. O laço
preço-risco é resolvido numericamente em vez de ignorado.

O resultado é uma escada de preço, não um preço:

| faixa | PD média | taxa a.m. | ROI que a faixa entrega |
|---|---|---|---|
| 10 | 3,1% | 2,27% | 15,1% |
| 9 | 4,1% | 2,36% | 15,4% |
| 8 | 4,9% | 2,47% | 15,8% |
| 7 | 6,0% | 2,56% | 16,0% |
| 6 | 6,9% | 2,65% | 16,3% |
| 5 | 8,8% | 2,82% | 16,7% |

A coluna da direita é quase plana de propósito: é isso que significa precificar a risco. Cada faixa
paga pelo próprio risco e entrega aproximadamente o mesmo retorno. A taxa máxima ofertada é de
**2,82% a.m., 24% abaixo do teto de CET** — sobra espaço, e a razão de não usá-lo é a decisão 5.

### Decisão 3 — Preço também é seleção, e isso vale 0,8 ponto de ROI

Precificar só a custo já cobra mais caro de quem é mais arriscado. A política vai um passo além:
cobra das faixas piores um prêmio *acima* do custo, de +4 pontos percentuais de alvo de ROI
descendo da faixa 10 para a faixa 1. Isso não serve para cobrir a perda delas — serve para que
menos gente dessas faixas aceite. Como o ROI é um quociente, mudar a composição da carteira move o
resultado tanto quanto mudar o preço:

| inclinação | ROI central | inadimplência | volume | faixas 8-10 | faixa de taxas |
|---|---|---|---|---|---|
| 0% | 14,88% | 5,87% | R$ 69,6 mi | 59,1% dos contratos | 2,27% – 2,52% |
| +4% | **15,71%** | 5,93% | R$ 67,4 mi | 60,4% dos contratos | 2,27% – 2,82% |

Custa R$ 2,2 milhões de volume e 0,06 p.p. de inadimplência; rende 0,83 p.p. de ROI. Vale registrar
que **a composição explica pouco desse ganho** — a participação das melhores faixas sobe apenas 1,3
ponto. A maior parte vem simplesmente de cobrar mais onde o risco é maior, com uma queda de aceite
que o piso de volume ainda absorve. A leitura honesta é "prêmio de risco mais inclinado", não
"engenharia de composição".

### Decisão 4 — Entrada mínima só onde ela muda a faixa de LGD, e o número é 21%

**Alternativa descartada:** exigir 20% de entrada, ou exigir entrada de toda a carteira.

O [capítulo 06](06-risco.md) provou que a fronteira das faixas de LTV é de **limite inferior
fechado**: um LTV de exatamente 0,80 cai na faixa *pior*, não na melhor. Exigir 20% de entrada,
portanto, não muda nada — a entrada tem de furar o corte, não encostar nele. Daí os 21%, que é um
número feio de propósito: é o que a evidência pediu, não o que ficaria bonito num slide.

A exigência vale só para as faixas 5 e 6, as duas piores aprovadas. Elevou a entrada de 412
propostas aprovadas (183 na faixa 5, 229 na faixa 6) e trouxe o LTV médio dessas faixas para 0,734
e 0,729.

Nas faixas 7 a 10 vale a entrada que o cliente propôs, e **199 contratos aprovados saem com LTV
acima de 90%** — 7,5% da carteira. É uma escolha consciente: nessas faixas a PD é baixa o
suficiente para que o preço já carregue a LGD alta, e uma exigência de entrada ali custaria volume
exatamente onde a carteira é mais rentável. Se o guardrail de volume fosse mais folgado, a decisão
provavelmente seria outra.

### Decisão 5 — A política é escolhida pelo cenário ruim, e isso custa 5,9 pontos de ROI

Esta é a decisão que define o capítulo.

O código testou 384 regras. Cada uma é avaliada no cenário central e no que o módulo chama de
**canto duro**: aceite pessimista *e* PD 20% acima da prevista, ao mesmo tempo — é o mesmo que o
documento de política chama de **cenário adverso**, o nome que um banco dá a um teste de estresse.
Aqui fica o apelido do código, porque é ele que aparece no `stdout` e nas chaves de
`artefatos/politica.json`. Dessas 384:

- **22** cumprem os quatro guardrails no canto duro;
- **10** ainda têm pelo menos 4% de folga em todos eles.

A regra escolhida é a de maior ROI entre essas 10. A fronteira que ela deixa para trás:

| regra | ROI central | folga mínima no canto duro | guardrail que aperta |
|---|---|---|---|
| **escolhida** | **15,7%** | **+4,2%** | inadimplência |
| tentação A | 16,5% | +1,3% | volume |
| tentação B | 15,8% | +1,7% | inadimplência |
| máximo da grade | 21,6% | **−53,1%** | volume |

O máximo da grade entrega 21,6% — quase 6 pontos a mais. Vale a troca? A conta é explícita. Uma
regra que entrega 21,6% com probabilidade *q* de passar no guardrail, e metade disso se quebrar,
só bate os 15,7% garantidos quando:

```
q · 0,216 + (1 − q) · 0,108 > 0,157    ⟹    q > 45%
```

Ou seja: só faz sentido apostar se houver mais de 45% de chance de o guardrail segurar. E a folga
dessa regra é de −53%: ela precisa que o volume contratado venha **53% acima** do que o nosso
próprio modelo projeta. Essa probabilidade não chega perto de 45%.

*(A conta supõe que a nota de política é proporcional ao ROI. Ela é relativa ao melhor grupo, o que
muda a escala e não muda o sinal.)*

### Decisão 6 — Negar tem dois motivos diferentes, e misturá-los seria um erro

A política nega as faixas 1 a 4. Mas por razões distintas, e a distinção importa:

**Faixas 1 e 2 — não existe preço.** Nem cobrando o teto de 3,5% a.m. elas alcançam o alvo. A faixa
1 entrega 9,4% ao ano no teto; a faixa 2, 16,3%, abaixo do alvo de 19,0% que a inclinação lhe
atribui. O motivo não é o preço ser baixo — é o termo `(1 − PD)` dos juros. Cobrando 3,5% a.m. em 48
meses, a faixa 1 acumularia 108% do valor financiado em juros (os 26,97% ao ano da tabela da
seção 2, por quatro anos) contra os 32,7% de perda que o [capítulo 06](06-risco.md) apurou. Parece
folgado. Mas com PD de 40,7%, quase metade dos contratos nunca chega ao fim para pagar o juro que
deveria ter precificado o risco da outra metade. **Preço só funciona onde há quem sobreviva para pagá-lo.**

Isso encerra uma pendência aberta no [capítulo 06](06-risco.md), que havia concluído que a faixa 1
era "decisão de regra, não de preço" comparando a perda esperada dividida por 12 com o teto de CET.
O capítulo 06 dizia, com razão, que aquilo era um piso otimista. A conta correta — juros de Price
sobre saldo decrescente, com a perda no mês do default, tudo anualizado pela fórmula do enunciado —
confirma a conclusão e muda o número: não é que a perda coma a taxa, é que não sobra gente pagando.

**Faixas 3 e 4 — existe preço, mas não cabe no portfólio.** Elas precisariam de 3,36% e 3,03% a.m.,
ambas abaixo do teto. São negadas porque a inadimplência é uma métrica de carteira, não de proposta:

| aprova a partir de | aprovação | ROI | volume central | inadimpl. central | volume no canto duro | inadimpl. no canto duro | guardrails no canto duro |
|---|---|---|---|---|---|---|---|
| faixa 3 | 71,5% | 15,8% | R$ 81,4 mi | 8,45% | R$ 48,1 mi | 10,12% | quebra inadimplência |
| faixa 4 | 60,1% | 15,8% | R$ 73,5 mi | 6,75% | R$ 45,4 mi | 8,55% | quebra inadimplência |
| **faixa 5** | **52,8%** | **15,7%** | **R$ 67,4 mi** | **5,93%** | **R$ 42,8 mi** | **7,67%** | **ok, folga 4%** |
| faixa 6 | 46,4% | 15,6% | R$ 61,1 mi | 5,39% | R$ 39,7 mi | 7,04% | quebra volume |
| faixa 7 | 38,0% | 15,5% | R$ 52,0 mi | 4,85% | R$ 34,7 mi | 6,38% | quebra volume |

A faixa 5 é o **único** corte que sobrevive ao canto duro: a faixa 4 estoura a inadimplência por
0,55 ponto, a faixa 6 fura o piso de volume por R$ 270 mil. Não é uma escolha de gosto — é a única
região admissível, e ela tem exatamente uma faixa de largura.

Um documento de política que não separa os dois motivos não sabe o que fazer quando o guardrail
mudar. Se o limite de inadimplência subisse para 10%, as faixas 3 e 4 voltariam para a mesa
imediatamente; as faixas 1 e 2, não.

---

## O modelo de aceite

Um cliente sente duas coisas numa oferta: quanto vai pagar por mês e quanto tem de tirar do bolso
hoje. Taxa e prazo chegam a ele pelo primeiro canal; a entrada exigida, pelo segundo. Daí a forma:

```python
logit(aceite) = logit(a0)
                − b_parcela × (aumento % da parcela sobre a esperada)
                − b_caixa   × (entrada extra exigida, em meses de renda)
```

A **parcela de referência** é a que o cliente teria na taxa da carteira antiga (1,587% a.m., a
mediana da janela de treino), com o prazo e a entrada que ele mesmo pediu. É a oferta que ele
esperava receber, e por isso o ponto onde o aceite vale `a0`.

Encaixar o prazo dentro da parcela, em vez de dar a ele um termo próprio, não é economia de
parâmetro — é o mecanismo certo. Encurtar o prazo reduz o aceite *porque* engorda a parcela, e o
quanto depende da taxa. Um termo separado contaria o mesmo efeito duas vezes.

Converter a entrada extra em **meses de renda** também é deliberado: a mesma exigência de R$ 5 mil
é trivial para quem ganha R$ 12 mil e proibitiva para quem ganha R$ 2 mil. É o que torna a alavanca
de entrada autolimitada no lugar certo.

Os três cenários:

| | `a0` | `b_parcela` | `b_caixa` | seleção adversa |
|---|---|---|---|---|
| otimista | 0,90 | 0,027 | 0,51 | +5% de PD por p.p. de prêmio |
| **central** | **0,85** | **0,045** | **0,85** | **+15% de PD por p.p.** |
| pessimista | 0,75 | 0,072 | 1,36 | +30% de PD por p.p. |

### De onde vem a calibração — e por que ela é fraca

Não há dado. Há uma única âncora, e ela é indireta: o enunciado afirma que o piso de R$ 40 milhões
existe para impedir a solução degenerada. Se essa afirmação é verdadeira, o piso tem de de fato
derrubá-la. Testando a degenerada — aprovar só o topo, cobrar o teto, exigir entrada alta:

| cenário de aceite | aceite médio | volume contratado | passa no piso? |
|---|---|---|---|
| otimista | 75,1% | R$ 50,9 mi | **passa** |
| central | 49,0% | R$ 32,9 mi | quebra |
| pessimista | 17,5% | R$ 11,6 mi | quebra |

**Se o enunciado diz a verdade sobre a função do guardrail, a elasticidade real é pelo menos a do
nosso cenário central** — porque no otimista a degenerada passaria folgada e o piso não faria o que
o enunciado diz que ele faz. É inferência fraca, e é toda a que há. Está escrita aqui em vez de
escondida porque é o ponto onde este capítulo é mais vulnerável a uma pergunta do conselho.

A **seleção adversa** entra como aumento relativo da PD proporcional ao prêmio de preço, em pontos
percentuais ao mês sobre a taxa de referência. Vale notar que o canal *mecânico* — parcela maior,
comprometimento de renda maior — já está dentro do modelo de PD e responde por cerca de +4,3% de PD
relativa por p.p. de taxa. O parâmetro `k_selecao` é o que vem **além** disso: o fato de que quem
aceita um preço acima do mercado é quem não tem para onde ir. Esse é o pedaço que nenhum dado deste
projeto consegue ver.

---

## O código que importa

O termo que decide toda a política de aprovação é o `(1 − PD)` dos juros esperados:

```python
def juros_esperados(valor_financiado, taxa_am, prazo_meses, pd_12m, atraso=3):
    """(1 − PD) · juros do contrato inteiro + PD · juros até o mês do default."""
    inteiro = n * parcela_price(v, i, n) - v
    parcial = np.zeros(...)
    for mes, frequencia in distribuicao_mes_default().items():
        pagas = max(int(mes) - atraso, 0)
        parcial = parcial + frequencia * juros_ate(v, i, n, pagas)
    return (1 - p) * inteiro + p * parcial
```

Sem o `(1 − PD)`, a faixa 1 pareceria rentável ao teto: 108% de juros acumulados contra 32,7% de
perda. Com ele, só 59,3% dos contratos chegam ao fim, e a conta vira 9,4% ao ano — o número que a
seção 3 imprime.

Os juros do contrato que quebra saem da decomposição da Price — cada parcela carrega juro e
principal, e o juro acumulado é o total pago menos o principal devolvido:

```python
def juros_ate(valor_financiado, taxa_am, prazo_meses, parcelas_pagas):
    pago = k * parcela_price(v, taxa_am, prazo_meses)
    principal = v - saldo_price(v, taxa_am, prazo_meses, k)
    return pago - principal
```

A taxa é resolvida, não escolhida:

```python
def taxa_para_roi(alvo, ...):
    """Menor taxa que entrega `alvo` de ROI anualizado, por bisseção.

    Não tem forma fechada porque a taxa entra dos dois lados: ela é a receita e,
    pelo capítulo 06, também empurra o EAD para cima.
    """
    for _ in range(40):
        meio = (baixo + alto) / 2
        perda = pd_12m * fator_ead_exato(meio, prazo_meses) * valor_financiado * g
        r = roi_do_contrato(valor_financiado, meio, prazo_meses, pd_12m, perda)
        baixo = np.where(r < alvo, meio, baixo)
        alto = np.where(r < alvo, alto, meio)
    return np.clip(alto, lo, hi)
```

E a ordem em que as alavancas são aplicadas importa:

```python
# 1. Entrada mínima, por faixa.   -> muda valor financiado, LTV e portanto a LGD
# 2. Prazo. Só encurta.           -> muda a parcela e o comprometimento de renda
# 3. PD e LGD nas condições ofertadas, antes do preço.
# 4. Taxa: a que entrega o alvo de ROI sobre o risco JÁ REDUZIDO pelas duas primeiras.
```

Precificar antes de exigir a entrada cobraria do cliente um risco que a própria política acabou de
tirar da mesa.

Por fim, **taxa, prazo e entrada são função da faixa, nunca da proposta individual**. Não é
simplificação: é o que torna a tabela do documento de política idêntica à submissão linha a linha —
os 10 pontos de coerência do enunciado. Uma taxa contínua por proposta seria melhor no papel e
indefensável num comitê.

---

## Os números que saíram

### A política

| faixa | propostas | decisão | taxa a.m. | prazo | entrada mínima | PD precificada | aceite | volume |
|---|---|---|---|---|---|---|---|---|
| 10 | 629 | APROVAR | 2,27% | 42m | a do cliente | 3,1% | 76% | R$ 18,77 mi |
| 9 | 456 | APROVAR | 2,36% | 42m | a do cliente | 4,1% | 74% | R$ 12,43 mi |
| 8 | 436 | APROVAR | 2,47% | 41m | a do cliente | 4,9% | 72% | R$ 10,96 mi |
| 7 | 380 | APROVAR | 2,56% | 42m | a do cliente | 6,0% | 70% | R$ 9,88 mi |
| 6 | 421 | APROVAR | 2,65% | 41m | 21% | 6,9% | 66% | R$ 9,05 mi |
| 5 | 320 | APROVAR | 2,82% | 41m | 21% | 8,8% | 62% | R$ 6,33 mi |
| 4 | 364 | NEGAR | — | — | — | 11,7% | — | — |
| 3 | 567 | NEGAR | — | — | — | 16,8% | — | — |
| 2 | 714 | NEGAR | — | — | — | 24,0% | — | — |
| 1 | 713 | NEGAR | — | — | — | 40,7% | — | — |

Duas convenções desta tabela, ambas aprendidas por erro. A coluna de PD é a **precificada** —
depois de a entrada exigida derrubar o LTV —, e não a que a submissão publica, que é a de
enquadramento; a distinção está no [capítulo 08](08-submissoes.md). E o prazo é ponderado por
volume e aceite, o mesmo que entra no ROI: a média simples publicava um prazo que **não
reproduzia o ROI da própria linha**, com erro de até 0,59 p.p. na faixa 5.

### Os guardrails

| guardrail | carteira central | limite | folga central | folga no canto duro |
|---|---|---|---|---|
| taxa de aprovação | 52,8% | ≥ 35% | +51,0% | +51,0% |
| volume originado | R$ 67.421.502 | ≥ R$ 40.000.000 | +68,6% | +7,0% |
| inadimplência | 5,93% | ≤ 8% | +34,9% | +4,2% |
| CET máximo | 2,82% a.m. | ≤ 3,5% a.m. | +24,1% | — |

**ROI anualizado projetado: 15,7% no cenário central, 14,8% no canto duro.** O conselho pediu acima
de 15%: o cenário central entrega, o canto duro fica 0,2 ponto percentual abaixo. Está escrito
assim porque a distância entre os dois é menor que o erro do modelo de aceite que produziu ambos.

### O teste de estresse completo

| cenário de aceite | PD | volume | inadimplência | ROI | guardrails |
|---|---|---|---|---|---|
| otimista | ×1,0 | R$ 80,4 mi | 5,51% | 16,0% | todos ok |
| otimista | ×1,2 | R$ 80,4 mi | 6,62% | 15,6% | todos ok |
| otimista | ×1,4 | R$ 80,4 mi | 7,72% | 15,2% | todos ok |
| central | ×1,0 | R$ 67,4 mi | 5,93% | 15,7% | todos ok |
| central | ×1,2 | R$ 67,4 mi | 7,12% | 15,3% | todos ok |
| central | ×1,4 | R$ 67,4 mi | 8,30% | 14,9% | **quebra inadimplência** |
| pessimista | ×1,0 | R$ 42,8 mi | 6,40% | 15,3% | todos ok |
| **pessimista** | **×1,2** | **R$ 42,8 mi** | **7,67%** | **14,8%** | **todos ok ← o canto duro** |
| pessimista | ×1,4 | R$ 42,8 mi | 8,95% | 14,4% | **quebra inadimplência** |

A fragilidade da política está exposta nesta tabela e tem nome: **se a PD real da Base C vier 40%
acima da prevista, o guardrail de inadimplência quebra em qualquer cenário de aceite.** E o nível
da PD em mar aberto é justamente o que a Base A não consegue medir, pelo viés de aprovados descrito
no [capítulo 01](01-dados.md) e pelo PSI de 0,473 entre A e C registrado no
[capítulo 05](05-score.md).

### A carteira, decomposta

| faixa | volume | juros esperados | perda esperada | juros / volume | perda / volume | ROI |
|---|---|---|---|---|---|---|
| 10 | R$ 18,77 mi | R$ 10,48 mi | R$ 0,45 mi | 55,8% | 2,4% | 15,1% |
| 9 | R$ 12,43 mi | R$ 7,11 mi | R$ 0,40 mi | 57,2% | 3,2% | 15,4% |
| 8 | R$ 10,96 mi | R$ 6,38 mi | R$ 0,44 mi | 58,3% | 4,1% | 15,8% |
| 7 | R$ 9,88 mi | R$ 6,02 mi | R$ 0,51 mi | 60,9% | 5,2% | 16,0% |
| 6 | R$ 9,05 mi | R$ 5,57 mi | R$ 0,52 mi | 61,6% | 5,8% | 16,3% |
| 5 | R$ 6,33 mi | R$ 4,13 mi | R$ 0,48 mi | 65,3% | 7,6% | 16,7% |
| **total** | **R$ 67,42 mi** | **R$ 39,69 mi** | **R$ 2,81 mi** | **58,9%** | **4,2%** | **15,7%** |

---

## O que deu errado

### O primeiro alvo de ROI colapsou a escada de preço

A primeira versão do módulo levava um alvo de 24% de ROI, escolhido por parecer "ambicioso mas
razoável". O resultado: todas as faixas precisavam de 3,4% a 3,5% a.m., ou seja, a precificação a
risco degenerou numa taxa única no teto de CET. O aceite médio caiu para 48,8% no cenário central e
17,5% no pessimista, e o volume contratado no pessimista ficou em R$ 18,4 milhões — menos da metade
do piso.

O erro de raciocínio foi tratar o alvo de ROI como uma *aspiração* em vez de um *parâmetro de
busca*. O alvo correto não se escolhe: ele é o maior valor para o qual a carteira resultante ainda
cumpre os guardrails no cenário ruim. Congelá-lo antes de rodar a grade inverteu a ordem.

### Um veredito que testava a coisa errada

A tabela da seção 3 marcava cada faixa como "cabe" ou "não cabe" no teto de CET comparando a
*mediana da taxa necessária* com 3,5%. Como a bisseção satura no teto, a mediana de uma faixa em
que metade das propostas satura vale exatamente 3,5% — e o teste `< 3,5%` dava "não cabe" para
faixas que cabiam e "cabe" para faixas adjacentes que não cabiam. A tabela publicada chegou a
mostrar a faixa 8 como inviável e a faixa 7 como viável, o que é impossível por monotonicidade.

A correção foi trocar o teste: uma faixa cabe quando o ROI que ela entrega **cobrando o teto**
alcança o alvo. O sintoma que denunciou o bug foi a quebra de monotonicidade entre faixas
adjacentes — vale guardar como checagem: numa tabela ordenada por risco, um veredito que alterna
está errado antes de ser interessante.

### Uma afirmação falsa no próprio relatório

A primeira versão do fechamento imprimia "o conselho pediu acima de 15%, e é acima de 15% nos dois"
enquanto o canto duro entregava 14,8%. O texto tinha sido escrito quando os números eram outros e
não foi reavaliado quando a política mudou. É o modo de falha mais perigoso deste projeto, porque
uma frase em português não quebra teste nenhum — ela só fica errada em silêncio. A correção passou
a derivar a frase dos próprios valores, e o mesmo vale para os três números que estavam digitados à
mão no meio de mensagens explicativas.

### A conta da aposta estava frouxa

O relatório justificava a escolha conservadora dizendo que "um ganho de ROI só compensa se a
probabilidade de quebrar o guardrail for menor que o ganho relativo". Isso não é a conta certa — é
uma paráfrase que soa razoável e não decide nada. A versão correta resolve a indiferença: com
penalidade de metade da nota, apostar em `r_b` só bate `r_a` garantido quando `q > 2·r_a/r_b − 1`,
que aqui dá 45%. O argumento só passou a valer alguma coisa quando virou um número.

---

## Como reproduzir

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python src/politica.py              # auditoria + política escolhida
PYTHONIOENCODING=utf-8 python src/politica.py --fronteira  # + a grade de 384 regras (~7 min)
```

O que conferir para saber que deu certo:

1. A seção 1 reproduz a tabela de juros anualizados por prazo e o default por prazo da Base A
   (6,44% em 24 meses contra 11,62% em 60).
2. A seção 3 marca as faixas 1 e 2 como sem preço viável, com a faixa 1 entregando 9,4% ao ano no
   teto de CET.
3. A seção 4 mostra a faixa 5 como o único corte que passa no canto duro, entre a faixa 4 que
   estoura a inadimplência (8,55%) e a faixa 6 que fura o volume (R$ 39,7 mi).
4. As seções 5b a 5d reproduzem a decomposição por faixa, o efeito de cada alavanca (412
   entradas elevadas, 199 contratos com LTV acima de 90%, prazo inalterado nas 5.000) e o ganho
   de 0,83 ponto que vem da inclinação do preço.
5. A seção 7 fecha com os quatro guardrails cumpridos e folga mínima de 4,2% no canto duro.
6. `artefatos/politica_base_c.csv` com 5.000 linhas e uma oferta por proposta;
   `artefatos/tabela_politica.csv` com as 10 faixas; `artefatos/politica.json` com as constantes,
   os parâmetros dos cenários e as versões do run.

Com `--fronteira`, a busca deve encontrar 22 regras robustas ao canto duro, 10 delas com folga
mínima de 4%, e a primeira da lista tem de ser exatamente
`corte>=5 alvo=15%+4% entrada<7/0 prazo<0:60m` — a regra congelada em `ESCOLHIDA`. Se a busca
apontar outra, a constante está desatualizada em relação à grade e precisa ser reajustada antes de
gerar a submissão.

O CSV de oferta por proposta é o insumo direto do próximo módulo: o [capítulo 08](08-submissoes.md)
transforma essas 5.000 linhas no arquivo `submissao_politica.csv` no formato exato que o desafio
exige, e faz o mesmo com a Base B do lado do modelo.
