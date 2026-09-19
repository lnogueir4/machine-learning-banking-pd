# 05 — Score: da PD contínua para dez faixas

> Capítulo anterior: [04 — Modelo](04-modelo.md) · Próximo: [06 — Risco](06-risco.md)
> Código: [`src/score.py`](../src/score.py) · Evidência: [`notebooks/03-decisoes-score.py`](../notebooks/03-decisoes-score.py)
> Figuras: [`notebooks/04-modelagem.ipynb`](../notebooks/04-modelagem.ipynb)

## O que este passo resolve

O capítulo anterior terminou com um modelo que devolve, para cada proposta, um número entre 0 e 1:
a probabilidade de o contrato atingir 90 dias de atraso nos doze meses seguintes. Para a submissão
do modelo isso basta — o AuROC só lê a ordem dos números.

A política de crédito não funciona assim. Ninguém aprova um comitê de crédito com a frase "a taxa
sobe continuamente com a PD"; e o desafio é explícito: a política **opera sobre faixas de score de
1 a 10**, onde 1 é o pior risco e 10 o melhor. Alguém tem de decidir onde termina a faixa 7 e
começa a faixa 8.

Essa decisão parece administrativa e não é. Agrupar joga informação fora — dois contratos com PD de
4,5% e 5,4% passam a receber o mesmo tratamento. A pergunta deste capítulo é **quanto se perde,
onde cortar e o que a tabela resultante realmente prova**.

### Três conceitos, para quem chega agora

- **Faixa de score (ou *rating*)**: um agrupamento de clientes com risco parecido, que recebem o
  mesmo tratamento comercial. É como um banco consegue ter uma política escrita em uma página em
  vez de uma fórmula por cliente.
- **Monotonicidade**: a exigência de que a inadimplência realizada caia sem tropeços da faixa 1 até
  a faixa 10. Se a faixa 9 quebra mais que a faixa 8, a tabela está cobrando mais caro de quem
  paga melhor — e o comitê perde a confiança na régua inteira.
- **PSI (*population stability index*)**: mede o quanto a distribuição de uma população mudou em
  relação a outra. Abaixo de 0,10 é estável; acima de 0,25, população trocada. Ver
  [02 — Exploração](02-exploracao.md).

## Decisões, com a alternativa descartada

### Decisão 1 — os cortes saem da PD *out-of-fold*, não da PD que o modelo dá a quem o treinou

O modelo final foi reajustado em toda a Base A (capítulo 04, decisão 4). Se pedirmos a ele a PD dos
10.000 contratos que o treinaram, ele acerta demais: são linhas que ele já viu.

A alternativa é a **PD out-of-fold**: dividir a Base A em cinco partes, treinar em quatro e prever a
quinta, cinco vezes. Cada contrato recebe uma PD de um modelo que não o conhecia. São 25 ajustes no
total (cinco dobras externas vezes as cinco internas da calibração) e custa cerca de um minuto.

O resultado surpreende em metade e assusta na outra:

| percentil | PD out-of-fold | PD dentro da amostra | razão |
|---|---|---|---|
| p10 | 0,0315 | 0,0313 | 0,993 |
| p30 | 0,0418 | 0,0406 | 0,972 |
| p50 | 0,0542 | 0,0531 | 0,980 |
| p70 | 0,0797 | 0,0788 | 0,988 |
| p90 | 0,1680 | 0,1721 | 1,025 |

A **distribuição** de PD é praticamente a mesma — os cortes mudariam na terceira casa decimal. O
modelo é regularizado (4 folhas por árvore) e a calibração faz média de cinco dobras; ele não
consegue inflar as próprias previsões.

O que muda é a **atribuição**. Cada contrato cai numa faixa diferente, e o efeito na tabela é brutal:

| PD usada | AuROC | PD observada na faixa 1 | PD observada na faixa 10 | separação 1/10 |
|---|---|---|---|---|
| out-of-fold | 0,7326 | 0,2960 | 0,0370 | **8,0x** |
| dentro da amostra | 0,8088 | 0,3500 | 0,0060 | **58,3x** |

Uma tabela construída com a PD de dentro da amostra prometeria ao conselho uma faixa 10 com **0,6%
de inadimplência**. A realidade fora da amostra é **3,7%** — seis vezes mais. A política precificaria
a faixa 10 quase de graça e descobriria o erro só na apuração do ROI.

> Este é o mesmo mecanismo do capítulo 04: número medido no dado que o modelo já viu não é
> estimativa, é memória. Aqui ele aparece numa forma nova — não no AuROC, mas na promessa de nível
> de cada faixa.

### Decisão 2 — faixas desiguais, largas no risco baixo e estreitas no risco alto

A escolha óbvia é o decil: dez faixas de 1.000 contratos cada. Foi a primeira tentativa, e ela
**falhou**. Com decis, a inadimplência observada da Base A ficou assim nas faixas boas:

| faixa | 7 | 8 | 9 | 10 |
|---|---|---|---|---|
| PD observada | 3,2% | 3,3% | 3,0% | **3,7%** |

A faixa 10 — a melhor da tabela — quebrou mais que as faixas 7, 8 e 9. Não por erro de código: o
modelo simplesmente **não distingue risco abaixo de 6% de PD**. Seis faixas inteiras — da 5 à 10 —
caíam num intervalo de PD prevista entre 2,72% e 5,86%, e com 1.000 contratos e 30 a 37 defaults em
cada uma a diferença entre 3,0% e 3,7% desaparece no erro amostral.

A correção vem de uma observação simples: **separar duas faixas exige população proporcional à
dificuldade da separação**. Distinguir 42% de 25% de PD é fácil e cabe em 300 contratos; distinguir
3,3% de 3,4% não cabe em 2.000. Logo, as faixas boas têm de ser grandes e as ruins pequenas — o
inverso do decil, que trata todas igual.

Os cortes escolhidos são os percentis `20, 36, 50, 62, 72, 80, 87, 93, 97` da PD out-of-fold, o que
dá faixas de 300 a 2.000 contratos. Cinco estratégias foram comparadas na mesma régua:

| estratégia | AuROC da faixa | rho | inversões | pares indistintos | menor faixa em A | menor faixa em C | PSI A→C |
|---|---|---|---|---|---|---|---|
| quantis (decis) | 0,7276 | −0,915 | 3 | 8 | 1.000 | 266 | 0,455 |
| largura igual em log-odds | 0,7218 | −1,000 | 0 | 6 | **7** | **8** | 0,468 |
| caudas finas | 0,7289 | −0,927 | 1 | **5** | 200 | 141 | 0,466 |
| **progressiva (escolhida)** | **0,7297** | **−0,988** | 1 | 7 | 300 | 320 | 0,464 |
| PD fixa de negócio | 0,7297 | −0,964 | 2 | 6 | 40 | **8** | 0,462 |

Duas armadilhas nessa tabela merecem leitura explícita:

- **"largura igual em log-odds" é perfeitamente monotônica** — rho de −1,000, zero inversões. E é
  inútil: consegue isso porque a faixa 1 tem **sete contratos**. Monotonicidade num grupo de sete
  pessoas não é propriedade do modelo, é sorte. Foi o candidato mais bonito na métrica e o primeiro
  a ser descartado.
- **"PD fixa de negócio"** — cortes redondos escolhidos a priori (2%, 3%, 4%, 5,5%…) — empata em
  AuROC com a escolhida e tem o atrativo de dar significado absoluto à faixa. Cai pelo mesmo
  motivo: a faixa 10 (PD < 2%) tem 40 contratos na Base A e 8 na Base C. Não dá para escrever uma
  política para oito propostas.

A progressiva vence por não ter nenhum ponto fraco: melhor AuROC, rho quase perfeito, e nenhuma
faixa com menos de 300 contratos em A ou 320 em C.

### Decisão 3 — os cortes são números fixos, não quantis recalculados por base

Os cortes são congelados no código como nove valores absolutos de PD:

```
0,0369  0,0448  0,0542  0,0663  0,0839  0,1067  0,1428  0,2096  0,3017
```

A alternativa — recalcular os percentis dentro de cada base — é tentadora porque garante faixas
sempre bem povoadas. E é errada por dois motivos:

1. **Destruiria o alarme.** Se a faixa 10 contém por definição os 20% melhores de qualquer
   população, o PSI entre Base A e Base C mede zero — exatamente quando a população trocou. O
   indicador que existe para avisar passaria a ser incapaz de avisar.
2. **Quebraria a coerência do preço.** A faixa 8 precisa significar a mesma PD em 2025 e em 2026.
   Com cortes móveis, "faixa 8" vira "o percentil 80 da safra", e a taxa cobrada deixa de ter
   relação com o risco.

Os valores foram arredondados na quarta casa decimal para que a tabela do documento de política
seja legível. O custo é nulo: as faixas 8, 9 e 10 ficam com 1.406, 1.588 e 2.006 contratos em vez
de 1.400, 1.600 e 2.000.

### Decisão 4 — dez faixas na tabela, mas a política decide sobre grupos de faixas

Dez faixas é exigência do desafio, e o custo de agrupar foi medido:

| granularidade | AuROC | inversões | pares indistintos | menor faixa em C |
|---|---|---|---|---|
| 5 faixas | 0,7154 | 1 | 1 de 4 | 568 |
| **10 faixas** | **0,7297** | 1 | 7 de 9 | 320 |
| 20 faixas | 0,7311 | 9 | 17 de 19 | 131 |
| PD contínua | 0,7326 | — | — | — |

Agrupar em dez custa **0,0029 de AuROC** — 0,4% do poder de ordenação. É barato, e vale a pena pelo
que se ganha em comunicabilidade.

Mas a coluna **"pares indistintos"** carrega o achado desconfortável do capítulo: são os pares de
faixas vizinhas cujos intervalos de confiança de 95% da inadimplência observada se sobrepõem. Com
dez faixas, **sete dos nove pares não se separam estatisticamente**. Só (1,2) e (3,4) se separam.

Isso não invalida a tabela: a ordenação geral está correta (rho −0,988, e nenhuma inversão fora do
intervalo de confiança). O que invalida é a **pretensão de dez preços distintos**. Com 10.000
contratos e PD média de 8,26%, a Base A não sustenta dez níveis de risco distinguíveis — sustenta
uns quatro ou cinco.

A consequência prática, que o capítulo 07 vai herdar: **a política agrupa faixas vizinhas para
definir taxa, prazo e entrada.** A tabela reporta dez faixas porque a submissão exige `score_1a10`;
o tratamento diferenciado tem menos degraus do que isso, e é honesto que tenha.

### Decisão 5 — a PD que representa a faixa é a média prevista na população decidida

Na hora de precificar, a faixa 8 precisa de um número. Há três candidatos:

| candidato | o que é | por que não |
|---|---|---|
| PD observada na Base A | inadimplência realizada dos contratos daquela faixa | é a mistura de perfis da carteira **antiga**, aprovada por outra política |
| ponto médio do intervalo | média entre os dois cortes | ignora onde dentro do intervalo a população se concentra |
| **PD média prevista na população decidida** | média das PDs dos contratos da Base C naquela faixa | **escolhido** |

A razão é que a faixa é um *intervalo* de PD, e dentro dele a mistura muda de uma base para outra. A
faixa 10 da Base A tem PD prevista média de 3,07%; a faixa 10 da Base C, 3,12%. A diferença é
pequena aqui e não será em faixas mais deslocadas. Como o modelo está calibrado (capítulo 04,
decisão 3), a média prevista dentro do intervalo é a melhor estimativa disponível para aquela
população.

Fica registrada a ressalva que o capítulo 07 terá de resolver: o **nível** da PD carrega duas derivas
em sentidos opostos — a inadimplência cai entre safras na Base A (9,57% em 2023-S1 para 6,51% em
2024-S2, o que faz superestimar 2025) e o viés de aprovados faz subestimar o mar aberto da Base C.
As duas não se cancelam por decreto.

## O código que importa

A conversão inteira cabe em duas linhas, e a inversão da escala acontece em **um único lugar do
projeto**:

```python
def faixa(pd_continua, cortes=CORTES) -> np.ndarray:
    """PD -> faixa 1-10, com 1 = pior risco e 10 = melhor."""
    pos = np.searchsorted(np.asarray(cortes, dtype="float64"),
                          np.asarray(pd_continua), side="right")
    return (len(cortes) + 1) - pos
```

`searchsorted` devolve 0 para a PD mais baixa e 9 para a mais alta; a subtração inverte. Score
invertido é o erro mais caro desta etapa porque é silencioso: não levanta exceção, atravessa a
política inteira e só aparece no ROI final, quando não há mais o que corrigir. Por isso a inversão
está isolada aqui e não é repetida em lugar nenhum.

O teste que decide se uma faixa é faixa de verdade:

```python
def pares_indistinguiveis(tab):
    """Pares vizinhos cujos intervalos de confiança se tocam."""
    t = tab.dropna(subset=["pd_observada"])
    indices = list(t.index)
    return [(k, prox) for k, prox in zip(indices, indices[1:])
            if not t.loc[k, "ic_lo"] > t.loc[prox, "ic_hi"]]
```

E a distinção entre uma inversão que condena a tabela e uma que é ruído amostral:

```python
def inversoes_materiais(tab):
    """Faixa melhor com PD comprovadamente maior que a pior — fora do IC de 95%."""
    ...
    return [(k, prox) for k, prox in zip(indices, indices[1:])
            if t.loc[prox, "ic_lo"] > t.loc[k, "ic_hi"]]
```

A tabela escolhida tem **uma** inversão de direção e **nenhuma** inversão material. A inversão está
entre as faixas 9 e 10: 3,3375% contra 3,3400%, dois milésimos de ponto percentual — 53 defaults em
1.588 contratos contra 67 em 2.006. A diferença entre os dois conceitos é o que separa rejeitar uma
tabela boa de aceitar uma ruim.

## Os números que saíram

### A tabela de faixas — Base A, PD out-of-fold

| faixa | n | % | PD de | PD até | PD prevista | PD observada | IC 95% |
|---|---|---|---|---|---|---|---|
| 1 | 300 | 3,0% | 30,22% | 79,93% | 41,10% | **42,00%** | 36,4% – 47,6% |
| 2 | 400 | 4,0% | 21,01% | 30,17% | 24,70% | 24,75% | 20,5% – 29,0% |
| 3 | 600 | 6,0% | 14,28% | 20,95% | 17,13% | 19,00% | 15,9% – 22,1% |
| 4 | 700 | 7,0% | 10,67% | 14,28% | 12,25% | 12,00% | 9,6% – 14,4% |
| 5 | 800 | 8,0% | 8,39% | 10,67% | 9,43% | 8,88% | 6,9% – 10,9% |
| 6 | 1.000 | 10,0% | 6,63% | 8,39% | 7,44% | 8,60% | 6,9% – 10,3% |
| 7 | 1.200 | 12,0% | 5,42% | 6,63% | 5,96% | 5,67% | 4,4% – 7,0% |
| 8 | 1.406 | 14,1% | 4,48% | 5,42% | 4,92% | 4,13% | 3,1% – 5,2% |
| 9 | 1.588 | 15,9% | 3,69% | 4,48% | 4,08% | 3,34% | 2,5% – 4,2% |
| 10 | 2.006 | 20,1% | 1,14% | 3,69% | 3,07% | **3,34%** | 2,6% – 4,1% |

A faixa 1 quebra **12,6 vezes mais** que a faixa 10 (42,0% contra 3,34%). Esse é o número que
justifica o modelo existir.

- rho de Spearman faixa × PD observada: **−0,988** (monotônica)
- inversões de direção: **1** · inversões materiais: **nenhuma**
- pares que o dado não separa: **7 de 9**

### Estabilidade

| população | n | faixa média | % faixas 1-3 | % faixas 8-10 | PSI vs 2022 |
|---|---|---|---|---|---|
| Base A 2022 (ref.) | 3.380 | 6,99 | 12,5% | 50,3% | 0,000 |
| Base A 2023 | 3.290 | 6,96 | 13,7% | 49,7% | 0,005 |
| Base A 2024 | 3.330 | 6,97 | 12,8% | 50,0% | 0,002 |
| Base B (2025-S1) | 3.000 | 7,13 | 11,8% | 52,1% | 0,006 |
| **Base C (2025-S2)** | 5.000 | **5,19** | **39,9%** | 30,4% | **0,473** |

Dentro do universo de contratos aprovados, a régua é notavelmente estável: PSI de 0,005 e 0,002
entre as safras da Base A, e 0,006 na Base B, que é meio ano posterior a tudo que o modelo viu. A
faixa média mal se move (6,99 → 7,13).

A Base C é outro planeta. **PSI de 0,473** — a régua do PSI chama isso de população trocada — com
39,9% das propostas nas três piores faixas contra 12,5% na Base A. Não é deterioração do modelo: é
o viés de aprovados medido em um número. As bases A e B só contêm quem a política antiga aprovou; a
Base C é mar aberto.

Essa é a primeira vez no projeto que o viés de aprovados aparece como uma grandeza única em vez de
uma coleção de cortes marginais ([01 — Dados](01-dados.md)). E ela impõe o limite de honestidade da
defesa: **a tabela acima foi validada em contratos aprovados; a faixa 1 da Base C contém perfis que
nunca receberam crédito nesta casa, e a PD deles é extrapolação, não medição.**

### O que a política vai encontrar na Base C

| faixa | n | % | % acumulado (de cima) | PD prevista |
|---|---|---|---|---|
| 1 | 713 | 14,3% | 100,0% | 43,10% |
| 2 | 714 | 14,3% | 85,7% | 25,28% |
| 3 | 567 | 11,3% | 71,5% | 17,61% |
| 4 | 364 | 7,3% | 60,1% | 12,38% |
| 5 | 320 | 6,4% | 52,8% | 9,50% |
| 6 | 421 | 8,4% | 46,4% | 7,47% |
| 7 | 380 | 7,6% | **38,0%** | 6,02% |
| 8 | 436 | 8,7% | 30,4% | 4,94% |
| 9 | 456 | 9,1% | 21,7% | 4,07% |
| 10 | 629 | 12,6% | 12,6% | 3,12% |

Esta tabela já restringe a política antes de ela ser escrita. O guardrail de aprovação exige **≥ 35%
das 5.000 propostas**, e as faixas 8, 9 e 10 somam apenas 30,4%. **Aprovar só as três melhores
faixas reprova no guardrail.** É preciso descer até a faixa 7 (38,0% acumulado) — ou aprovar parte
da faixa 6 sob condições mais duras.

E aprovar até a faixa 7 traz a PD prevista média para perto de 4,6%, o que deixa folga contra o
guardrail de inadimplência (≤ 8%) — mas o volume de R$ 40 milhões e o CET de 3,5% a.m. ainda não
foram testados contra isso. É o trabalho dos capítulos 06 e 07.

### Sobre o AuROC de 0,7326

O número out-of-fold deste capítulo (0,7326) é mais baixo que o out-of-time do capítulo 04 (0,7434)
e mede coisa diferente: aqui o modelo treina em 8.000 contratos sorteados de todo o período e prevê
2.000 do mesmo período; lá ele treina em 2022-2023 e prevê 2024.

Curiosamente o sorteado é **pior** que o temporal, apesar de treinar com mais dados. A explicação é
que a safra de 2024 é mais separável que a média do período, não que prever o futuro seja mais
fácil. É a terceira medição independente do mesmo modelo, e as três caem no mesmo lugar:

| medição | AuROC |
|---|---|
| validação encadeada em janelas anteriores a 2024 (cap. 04) | 0,7226 |
| out-of-fold sobre toda a Base A (este capítulo) | 0,7326 |
| out-of-time na safra de 2024 (cap. 04) | 0,7434 |

A defesa reporta a **faixa de 0,72 a 0,74**, não o melhor dos três.

## O que deu errado

1. **A primeira tabela usou decis e a faixa 10 quebrou mais que a faixa 9.** O reflexo foi procurar
   bug no código de inversão da escala. Não havia bug: a diferença era ruído amostral numa região
   onde o modelo não resolve. Foi o que originou o teste de `pares_indistinguiveis` — e, por
   consequência, a decisão 4, que é o achado mais útil do capítulo.
2. **A estratégia de log-odds foi quase escolhida por ter rho de −1,000.** Métrica de monotonicidade
   não olha o tamanho da faixa; faltava a coluna "menor faixa", e com ela a estratégia caiu na
   hora. Toda métrica de qualidade de agrupamento precisa de uma métrica de população ao lado.
3. **A PD de dentro da amostra parecia segura** porque os percentis batiam com os out-of-fold na
   terceira casa. A conclusão "tanto faz" só não foi registrada porque a tabela de faixas foi
   montada com as duas: os cortes empatam, a promessa de nível difere seis vezes.

## Como reproduzir

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python notebooks/03-decisoes-score.py  # as cinco estratégias comparadas
PYTHONIOENCODING=utf-8 python src/score.py                    # tabela de faixas e testes
PYTHONIOENCODING=utf-8 python src/score.py --refazer          # recalcula a PD out-of-fold e os cortes
```

A primeira execução do `src/score.py` calcula a PD out-of-fold (cerca de um minuto, 25 ajustes) e a
grava em `artefatos/pd_base_a.csv`; as seguintes reaproveitam o arquivo. `--refazer` força o
recálculo.

**O que conferir para saber que deu certo:**

1. `--refazer` imprime `OK` ao comparar os cortes recalculados com os nove valores congelados em
   `CORTES`. Se imprimir `DIVERGE do código`, alguma coisa mudou a montante — modelo, features ou
   seed — e a tabela de faixas precisa ser reemitida junto com o documento de política.
2. A faixa 1 tem PD observada de 42,0% e a faixa 10, de 3,34%. Se a ordem aparecer invertida, a
   escala foi invertida duas vezes.
3. `inversões materiais: nenhuma`. Qualquer inversão material invalida a tabela para precificação.
4. PSI da Base B contra 2022 abaixo de 0,01 e da Base C acima de 0,40. Se a Base C vier estável, a
   Base C não passou por `preparar_aplicacao()` e está sendo pontuada com `comprometimento_renda`
   ausente.
5. `artefatos/tabela_faixas.csv` e `artefatos/score.json` com seed, cortes e versões.

A tabela de faixas em `artefatos/tabela_faixas.csv` é a mesma que irá para o documento de política
e a mesma que a submissão tem de reproduzir linha a linha — são 10 pontos de coerência no desafio,
e a única forma de garanti-los é nenhuma das três cópias ser digitada à mão.
