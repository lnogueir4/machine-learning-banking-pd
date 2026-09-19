# 08 — Submissões: os dois arquivos que valem a nota

> Capítulo anterior: [07 — Política](07-politica.md) · Índice: [README](README.md)
> Código: [`src/submissoes.py`](../src/submissoes.py) · Saída: [`entregaveis/`](../entregaveis/)

## O que este passo resolve

Sete capítulos de trabalho terminam em dois arquivos CSV. Um traz a probabilidade de inadimplência
de 3.000 contratos que o modelo nunca viu; o outro traz a decisão de crédito para 5.000 propostas.
Tudo o que a banca avalia — o AuROC do modelo e o ROI da política — sai desses dois arquivos. Se o
formato estiver errado, o trabalho anterior não existe.

Este é o capítulo mais curto e o de maior risco por linha de código. Gerar os arquivos é trivial: o
modelo está serializado, a política está congelada, e o que sobra é escrever duas tabelas. O
trabalho de verdade está na outra metade, **conferir**, e a razão é simples: um erro de formato não
dá erro. Ele produz um arquivo perfeitamente legível com o número errado dentro.

```csv
submissao_modelo.csv    → id_contrato,pd                                                 (3.000 linhas, Base B)
submissao_politica.csv  → id_proposta,pd,score_1a10,decisao,taxa_am,prazo_meses,pct_entrada_minima   (5.000, Base C)
```

---

## Decisões, com a alternativa descartada

### Decisão 1 — A `pd` publicada na política é a do enquadramento, não a do preço

**Alternativa descartada:** publicar a PD sob as condições ofertadas, que é a que de fato precifica
o contrato.

Este projeto calcula a PD duas vezes para cada proposta da Base C, e as duas são legítimas:

- **PD de enquadramento** — nas condições que o cliente pediu. É dela que a faixa de score sai, e é
  ela que organiza a política.
- **PD de oferta** — depois de a entrada mínima exigida derrubar o LTV. É menor nas faixas 5 e 6, e
  é ela que a taxa cobre e que a simulação de ROI usa.

A diferença não é decorativa. Na faixa 6 são 7,47% contra 6,93%; na faixa 5, 9,50% contra 8,82%.

A submissão publica a **de enquadramento**, por um motivo de coerência e não de precisão: o arquivo
tem uma coluna `pd` e uma coluna `score_1a10` lado a lado. Se a `pd` publicada fosse a de oferta,
`faixa(pd)` deixaria de reproduzir `score_1a10` e o arquivo se contradiria sozinho — num desafio
que reserva 10 pontos para a coerência entre a tabela da documentação e a submissão. **O número que
vai no arquivo é o que sustenta a coluna ao lado dele.**

A consequência é que `artefatos/tabela_politica.csv` precisou passar a publicar as duas colunas,
`pd_publicada` e `pd_precificada`. Publicar só uma faria a tabela do documento divergir da
submissão sem que ninguém soubesse por quê — e essa é exatamente a espécie de incoerência que custa
pontos sem aparecer em lugar nenhum.

### Decisão 2 — Seis casas decimais na PD, e não pelo motivo que eu imaginava

**Alternativa descartada:** as quatro casas do arquivo de exemplo.

A hipótese inicial era que arredondar criaria empates e empate destruiria AuROC. Medido contra a PD
out-of-fold da Base A, a hipótese não se sustenta:

| casas decimais | valores empatados | AuROC | perda de AuROC | propostas que trocam de faixa |
|---|---|---|---|---|
| 2 | 99,3% | 0,73202 | 0,00055 | 339 |
| 3 | 95,3% | 0,73263 | −0,00006 | 83 |
| 4 | 78,3% | 0,73255 | 0,00002 | **19** |
| 5 | 34,2% | 0,73257 | 0,00000 | 1 |
| 6 | 5,3% | 0,73257 | 0,00000 | **0** |
| sem arredondar | 0,0% | 0,73257 | — | 0 |

Quatro casas empatam 78% dos valores e custam **0,00002 de AuROC**. Praticamente nada, porque um
AuROC bem implementado pontua par empatado como 0,5 e não como erro — o empate não é ignorância, é
indiferença, e a métrica trata as duas coisas certo.

Então a razão de usar seis casas **não é AuROC**, e dizer que é seria inventar um ganho que a
medição nega. A razão é outra, e é específica da política: **a quatro casas, 19 das 5.000 propostas
caem do outro lado de um corte de faixa.** Quem reconferir `faixa(pd)` a partir do CSV encontraria
uma faixa diferente da que a política usou, em 19 linhas. A seis casas, zero — e há uma checagem no
módulo que prova isso a cada execução.

Relacionado: a faixa é calculada **a partir da `pd` já arredondada**, não antes. Classificar e
depois arredondar reintroduziria exatamente as 19 divergências que arredondar antes elimina.

### Decisão 3 — Linha negada não leva preço

O arquivo de exemplo do desafio deixa `taxa_am`, `prazo_meses` e `pct_entrada_minima` **vazios**
quando a decisão é `NEGAR`. Seguimos isso, e ele está certo: proposta negada não tem preço, prazo
nem entrada. Preencher esses campos numa linha negada publicaria uma oferta que a política decidiu
não fazer.

Na prática isso exigiu um detalhe de implementação que vale registrar. A coluna `prazo_meses`
precisa aceitar ausente *e* gravar inteiro. Com o tipo `float` padrão do pandas, o `NaN` das linhas
negadas força as aprovadas a gravarem `48.0` — que não é o que o exemplo faz. A solução é o tipo
`Int64` do pandas (com I maiúsculo), o inteiro que aceita nulo. E há uma checagem que lê o arquivo
do disco e exige que o campo de prazo seja composto só de dígitos.

### Decisão 4 — A conferência lê o arquivo do disco, nunca o DataFrame que o gerou

Esta é a decisão que define o módulo. Toda checagem acontece depois de `pd.read_csv()` sobre o
arquivo gravado, e não sobre o objeto em memória que o escreveu.

O motivo: a classe inteira de erros que mais assusta aqui só existe **na escrita**. Um BOM no
início do arquivo, o índice vazando para uma primeira coluna sem nome, o separador errado, `48.0`
onde se esperava `48`, um float em notação científica. Nada disso aparece no DataFrame de origem —
ele está perfeito. Conferir o objeto que gerou o arquivo é conferir a própria intenção, não o
resultado.

---

## O código que importa

A geração é curta. O que merece leitura é a coluna que precisa ser inteira e nula ao mesmo tempo:

```python
"taxa_am": np.where(aprovado, oferta["taxa_am"].to_numpy(), np.nan),
# `Int64` (com I maiúsculo) é o inteiro que aceita ausente. Sem ele,
# o `NaN` das linhas negadas viraria float e gravaria `48.0` nas
# aprovadas — o que o exemplo do desafio não faz.
"prazo_meses": pd.Series(
    np.where(aprovado, oferta["prazo_meses"].to_numpy(), np.nan)
).astype("Int64"),
```

A conferência acumula em vez de abortar:

```python
class Conferencia:
    """Acumula checagens e falha no fim, com todas as falhas de uma vez.

    Falhar na primeira checagem economiza uma linha de código e custa três
    rodadas de depuração: corrige-se um problema, roda de novo, aparece o
    seguinte. Aqui todas aparecem juntas.
    """
```

Com uma exceção deliberada — quando o cabeçalho está errado, não adianta continuar:

```python
if not conf.checar(list(df.columns) == esperado, "colunas e ordem idênticas ao exemplo", ...):
    # Sem as colunas certas, toda checagem seguinte estoura em `KeyError` e
    # o traceback esconde a causa. Falha limpo aqui: o problema é um só.
    conf.checar(False, "demais checagens não rodaram", "corrija o cabeçalho primeiro")
    return conf
```

E a checagem que vale os 10 pontos de coerência — a submissão contra a tabela publicada, faixa a
faixa, mais a prova de que taxa e entrada são constantes dentro de cada faixa:

```python
por_faixa = df.loc[aprova].groupby("score_1a10")
conf.checar(int(por_faixa["taxa_am"].nunique().max()) == 1, "uma só taxa por faixa")
conf.checar(int(por_faixa["pct_entrada_minima"].nunique().max()) == 1, "uma só entrada mínima por faixa")
```

Isso só é verificável porque a política decidiu, no [capítulo 07](07-politica.md), que taxa, prazo e
entrada são função **da faixa** e nunca da proposta individual. Uma taxa contínua por proposta seria
melhor no papel e tornaria essa checagem impossível.

---

## Os números que saíram

### `submissao_modelo.csv`

| | |
|---|---|
| linhas | 3.000, uma por contrato da Base B |
| PD mínima / máxima | 0,0188 / 0,7791 |
| PD média | 0,0793 |
| valores distintos | 2.954 de 3.000 |

A PD média prevista para a Base B (7,93%) fica abaixo da inadimplência realizada da Base A (8,26%),
o que é coerente com o que o [capítulo 05](05-score.md) registrou sobre a queda entre safras.

### `submissao_politica.csv`

A tabela de faixas, extraída **do próprio arquivo de submissão** — não da política que o gerou:

| faixa | propostas | decisão | taxa a.m. | entrada mínima | PD média |
|---|---|---|---|---|---|
| 10 | 629 | APROVAR | 2,27% | 0% | 3,12% |
| 9 | 456 | APROVAR | 2,36% | 0% | 4,07% |
| 8 | 436 | APROVAR | 2,47% | 0% | 4,94% |
| 7 | 380 | APROVAR | 2,56% | 0% | 6,02% |
| 6 | 421 | APROVAR | 2,65% | 21% | 7,47% |
| 5 | 320 | APROVAR | 2,82% | 21% | 9,50% |
| 4 | 364 | NEGAR | — | — | 12,38% |
| 3 | 567 | NEGAR | — | — | 17,61% |
| 2 | 714 | NEGAR | — | — | 25,28% |
| 1 | 713 | NEGAR | — | — | 43,10% |

**2.642 APROVAR e 2.358 NEGAR** — taxa de aprovação de 52,8%, contra o mínimo de 35%.

O prazo ofertado é sempre o que o cliente pediu, então a coluna `prazo_meses` reproduz a
distribuição da própria Base C entre 24, 36, 48 e 60 meses.

### As 30 checagens

O módulo confere, relendo os arquivos do disco:

**Formato** — colunas e ordem idênticas ao exemplo; sem BOM; contagem de linhas; ids iguais aos da
base e na mesma ordem; ids sem repetição; prazo gravado como inteiro e não como `48.0`.

**Domínios** — PD dentro de (0, 1); score inteiro de 1 a 10; decisão só `APROVAR` ou `NEGAR`; taxa
entre o piso de 1,59% e o teto de CET de 3,5%; prazo entre os quatro valores válidos; entrada em
decimal dentro de [0, 1].

**A regra do exemplo** — linhas `NEGAR` com as três colunas de oferta vazias, linhas `APROVAR` com
as três preenchidas.

**Coerência** — `faixa(pd)` reproduz `score_1a10` a partir do CSV; uma só decisão, uma só taxa e uma
só entrada por faixa; taxa monotônica na faixa (2,27% na 10 subindo até 2,82% na 5); a submissão
bate com `artefatos/tabela_politica.csv` faixa a faixa; a PD média por faixa no CSV é igual à coluna
`pd_publicada` da tabela — não à `pd_precificada`.

**Guardrail** — a taxa de aprovação que o próprio arquivo prova: 52,8%.

### E a pergunta que faltava: essas 30 checagens checam alguma coisa?

Uma bateria que sempre diz "ok" não prova nada — pode estar checando o vazio. O módulo termina
estragando o próprio arquivo de nove formas diferentes e exigindo que a conferência pegue todas:

| sabotagem | o que a conferência acusou |
|---|---|
| BOM no início do arquivo | sem BOM no início do arquivo |
| nome de coluna trocado | colunas e ordem idênticas ao exemplo |
| duas colunas fora de ordem | colunas e ordem idênticas ao exemplo |
| uma linha a menos | 5.000 linhas |
| taxa acima do teto de CET | taxa entre 1,59% e o teto de CET de 3,5% |
| taxa diferente do resto da faixa | uma só taxa por faixa |
| prazo gravado como `48.0` | prazo gravado como inteiro, não como `48.0` |
| linha `NEGAR` com preço preenchido | linhas NEGAR com taxa, prazo e entrada vazios |
| score que não bate com `faixa(pd)` | score reproduzível por faixa(pd) a partir do CSV |

Nove de nove. A bateria diz "ok" depois de provar que sabe dizer "falha".

---

## O que deu errado

### Eu ia justificar as seis casas decimais com um ganho que não existe

A decisão de publicar a PD com seis casas em vez das quatro do exemplo estava tomada antes de ser
medida, e a justificativa pronta era "empates destroem AuROC". Medido, o custo de quatro casas é de
0,00002 — ruído. A decisão continuou de pé, mas por outro motivo, que é o das 19 propostas que
trocam de faixa.

O que fica: uma decisão pode estar certa e a razão dela estar errada, e isso é pior do que parece —
porque a razão errada é o que se leva para a defesa. Se o conselho perguntasse "quanto isso vale de
AuROC?", a resposta honesta seria "nada, e não é por isso que eu faço".

### A tabela da política e a submissão publicavam PDs diferentes

A primeira versão da submissão passou nas checagens e estava incoerente com a documentação: a
tabela do [capítulo 07](07-politica.md) publicava a PD de oferta (6,93% na faixa 6) e o CSV
publicava a de enquadramento (7,47%). As duas corretas, a mesma faixa, números diferentes, e nenhuma
checagem existia para notar.

O sintoma apareceu por acaso, ao comparar duas saídas impressas lado a lado. A correção foi fazer
`tabela_politica.csv` publicar as duas colunas com nomes que dizem o que são, e criar a checagem
que estava faltando. O caso é instrutivo porque a incoerência não era um erro de cálculo em lugar
nenhum — era a mesma grandeza medida em dois pontos da cadeia, e cada metade do projeto escolhendo
um ponto diferente sem dizer qual.

### O cabeçalho errado estourava em `KeyError`

Descoberto pelo próprio autoteste: sabotar o nome de uma coluna fazia a conferência abortar com um
traceback em vez de acusar a falha. Tecnicamente o erro *era* detectado — mas a mensagem apontava
para uma linha interna qualquer em vez de dizer "o cabeçalho está errado". Corrigido com uma saída
antecipada quando o cabeçalho não confere.

O detalhe importante é que essa falha só apareceu porque existe um teste que quebra o arquivo de
propósito. As 30 checagens sozinhas jamais a teriam mostrado.

### A armadilha de ferramenta, pela quarta vez nesta semana

Editar este módulo por heredoc corrompeu duas linhas: `chr(10).join(...)` virou uma quebra de linha
literal dentro de uma string, e `"﻿"` virou um BOM invisível no código-fonte. O `CLAUDE.md`
já documenta o problema desde o capítulo 06 e ele voltou a acontecer mesmo assim. As duas linhas
foram reescritas com `chr(10)` e `chr(65279)` — que, no caso do BOM, é melhor de qualquer jeito: o
caractere literal é invisível no editor, que é exatamente o problema que ele causa no CSV.

---

## Como reproduzir

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python src/submissoes.py             # gera os dois CSVs e confere
PYTHONIOENCODING=utf-8 python src/submissoes.py --conferir  # só confere o que já está gravado
```

O que conferir para saber que deu certo:

1. `30 checagens, 0 falhas` no fim da saída.
2. `as nove sabotagens foram pegas` no autoteste.
3. `entregaveis/submissao_modelo.csv` com 3.001 linhas (cabeçalho mais 3.000) e
   `entregaveis/submissao_politica.csv` com 5.001.
4. A tabela de faixas impressa ao final bate com a do [capítulo 07](07-politica.md): 2,27% na faixa
   10 até 2,82% na faixa 5, `NEGAR` das faixas 1 a 4.
5. `artefatos/submissoes.json` com a regra congelada, as contagens e as versões do run.

O comando é idempotente: rodar duas vezes produz arquivos byte a byte idênticos. Se não produzir,
alguma coisa na cadeia depende de estado que não deveria.

**A cadeia inteira, do zero:**

```bash
PYTHONIOENCODING=utf-8 python src/dados.py       # auditoria das bases
PYTHONIOENCODING=utf-8 python src/features.py    # matriz e pré-processadores
PYTHONIOENCODING=utf-8 python src/modelo.py      # treino e serialização
PYTHONIOENCODING=utf-8 python src/score.py       # faixas 1-10
PYTHONIOENCODING=utf-8 python src/risco.py       # EAD, LGD, perda esperada
PYTHONIOENCODING=utf-8 python src/politica.py    # alavancas, guardrails, ROI
PYTHONIOENCODING=utf-8 python src/submissoes.py  # os dois CSVs
```

---

## O que ainda não está pronto

A documentação didática termina aqui, mas o desafio não. Falta o **documento de política** em
`reports/`, derivado dos capítulos 06 e 07 e recortado para o
`entregaveis/template_documento_politica.docx`, e o **relatório do modelo**, derivado dos capítulos
01 a 05.

E fica registrada a fragilidade que o [capítulo 07](07-politica.md) já nomeou, porque ela sobrevive
à submissão: **se a PD real da Base C vier 40% acima da prevista, o guardrail de inadimplência
quebra em qualquer cenário de aceite.** Não há dado no projeto que permita medir esse nível. A
política comprou folga em vez de corrigir, e essa é a primeira pergunta que o conselho deveria
fazer.
