# 01 — Dados: as três bases, o vazamento e o viés de aprovados

Módulo: [`src/dados.py`](../src/dados.py) · Reproduz com `PYTHONIOENCODING=utf-8 python src/dados.py`

## O que este passo resolve

Antes de treinar qualquer modelo, três perguntas precisam de resposta em código, não em memória:

1. **O que existe nas bases?** Volume, período, duplicidades, valores ausentes.
2. **Quais colunas eu posso usar?** Em crédito, usar uma informação que só existiu *depois* da
   concessão produz um modelo que parece excelente e é inútil. Isso se chama **vazamento**
   (*data leakage*).
3. **A população onde vou aplicar o modelo é a mesma onde ele aprendeu?** Se não for, o modelo
   extrapola — e extrapolação em crédito custa dinheiro.

Este módulo é o **único lugar do projeto que lê `bases/`**. Todo o resto recebe DataFrames já
validados. Concentrar a leitura num ponto só é o que permite ter uma defesa antivazamento única,
em vez de espalhar checagens por vários arquivos e torcer para nenhuma ficar desatualizada.

## As três bases

| Base | Linhas | Período | Papel |
|---|---:|---|---|
| A — desenvolvimento | 10.000 | 2022-01 a 2024-12 | treino; tem o alvo e os valores realizados |
| B — teste do modelo | 3.000 | 2025-01 a 2025-06 | teste *out-of-time*; **sem alvo** |
| C — política | 5.000 | 2025-07 a 2025-12 | propostas que recebem a política |

*Out-of-time* significa que o teste vem de um período **posterior** ao treino, e não de uma amostra
sorteada aleatoriamente dentro do mesmo período. É o padrão em crédito, porque o modelo será usado
no futuro, não no passado.

Um detalhe com consequência prática: **a Base B não tem a coluna do alvo.** Não existe "conferir o
AuROC na B antes de enviar" — o resultado só aparece na apuração. A disciplina de validação interna
é tudo o que temos.

## Decisão 1 — a lista de colunas proibidas sai do dicionário, não do código

O dicionário de dados oficial (`AutoCred_Dicionario_de_Dados.xlsx`, aba `Bases A e B`) tem uma
coluna chamada `Disponível na concessão?`. Seis colunas estão marcadas com `NÃO`.

**Alternativa descartada:** escrever essas seis colunas como uma lista literal no código. É o que
quase todo projeto faz, e funciona — até o material ser atualizado e ninguém lembrar de editar a
lista. A falha é silenciosa: o modelo treina normalmente e ninguém percebe.

**O que foi feito:** a lista é lida do dicionário a cada execução.

```python
def colunas_proibidas() -> list[str]:
    dic = carregar_dicionario()
    marca = dic["Disponível na concessão?"].astype(str).str.strip().str.upper()
    return dic.loc[marca == "NÃO", "Coluna"].tolist()
```

E a validação falha, antes de qualquer `fit`:

```python
class VazamentoDetectado(Exception):
    """Erguida quando uma coluna pós-concessão entra na lista de preditoras."""


def validar_features(features=None) -> list[str]:
    features = list(FEATURES if features is None else features)
    invasoras = sorted(set(features) & set(colunas_proibidas()))
    if invasoras:
        raise VazamentoDetectado(
            "Coluna pós-concessão na lista de preditoras: " + ", ".join(invasoras) + ...
        )
    return features
```

Um modelo que não treina é melhor que um modelo que treina com vazamento.

## Decisão 2 — as features precisam existir na Base C, e cinco não existiam

Esta foi a descoberta que mudou o desenho do pipeline, e ela não é óbvia lendo o enunciado.

O dicionário lista 15 colunas com papel `Preditora`, todas disponíveis na concessão. Mas quando se
comparam as colunas que a Base C **de fato tem** com as que as bases A e B têm, nove somem:

```
Permitidas pelo dicionário e ausentes na Base C:
  comprometimento_renda, ltv, prazo_meses, valor_entrada, valor_financiado,
  parcela_mensal, taxa_juros_am, data_originacao, id_contrato
```

O motivo é conceitual, não um defeito dos dados. A Base A descreve **contratos fechados**: as
condições já foram negociadas. A Base C descreve **propostas**, e traz o que o cliente *deseja*
(`ltv_desejado`, `prazo_desejado_meses`, `valor_financiado_desejado`). Quem define as condições
efetivas somos nós, via política. Um modelo que dependa de `taxa_juros_am` simplesmente **não
consegue pontuar a Base C**, porque essa coluna é uma decisão nossa que ainda não foi tomada.

As colunas se dividem em três grupos, e é assim que estão organizadas no código:

```python
COLS_CLIENTE  = [...]   # proponente, veículo e bureau: existem em C, mesmo nome
COLS_NEGOCIO  = [...]   # estrutura da operação: chegam em C como *_desejado
COLS_DERIVADAS = ["comprometimento_renda"]   # recalculável a partir da oferta
COLS_DESCARTADAS = ["taxa_juros_am", "parcela_mensal"]   # decisão nossa, ficam de fora
```

**Quanto custou descartar?** Medido com validação out-of-time dentro da Base A (treino 2022-23,
teste 2024, gradient boosting regularizado, seed 42):

| Conjunto de features | n | AuROC out-of-time | Pontua a Base C? |
|---|---:|---:|---|
| Só cliente + veículo + bureau | 13 | 0,6771 | sim |
| **+ estrutura do negócio (escolhido)** | **18** | **0,7377** | **sim** |
| + preço da política antiga | 20 | 0,7390 | **não** |

O conjunto completo vale 0,0013 de AuROC a mais e é inutilizável na metade do desafio que vale
40 pontos. A escolha não é difícil.

Essas 18 são as **candidatas** (`CANDIDATAS` em `dados.py`), que é o que a exploração mede. O
capítulo [02](02-exploracao.md) reprova `ano_modelo`, e o modelo treina com as 17 restantes
(`FEATURES`). A separação entre os dois nomes é deliberada: medir uma variável é o que permite
descartá-la com evidência.

O ganho real está em `comprometimento_renda` (parcela dividida pela renda declarada): sozinho ele
leva o modelo de 0,7245 para 0,7377, o maior ganho marginal de uma variável única. Vale a
complexidade de recalculá-lo na Base C. Já `taxa_juros_am` e `parcela_mensal`, medidos
individualmente, **pioram** o resultado (0,7155 e 0,7171 contra a base de 0,7245) — são ruído caro.

### A circularidade, e como ela se resolve

`comprometimento_renda` depende da parcela, que depende da taxa e do prazo que vamos ofertar, que
dependem da faixa de score, que depende da PD. Isso é circular só na aparência: resolve-se em duas
passadas, e a função `mapear_base_c` existe para isso.

```python
def mapear_base_c(base_c, prazo_meses=None, valor_entrada=None, parcela_mensal=None):
    """Sem argumentos, assume as condições DESEJADAS pelo cliente — primeira passada.
    Com as condições ofertadas, devolve a versão usada na decisão final."""
```

Primeira passada: pontua com o que o cliente pediu, para enquadrar a proposta numa faixa. Segunda
passada: com as condições que a política ofertou, recalcula e decide. Determinístico, sem iteração
infinita.

## Os números que saíram

Saída de `python src/dados.py`:

**Integridade** — nenhuma das três bases tem id duplicado nem linha inteiramente repetida. O alvo
não tem nulos.

**O alvo.** PD 90/12 global de **8,26%** (826 defaults em 10.000 contratos):

| Safra | Contratos | PD |
|---|---:|---:|
| 2022 | 3.380 | 8,67% |
| 2023 | 3.290 | 8,94% |
| 2024 | 3.330 | 7,18% |

Estável o suficiente para treinar sem reponderar por safra. A queda em 2024 merece explicação na
defesa — pode ser melhora de política ou mudança de mix.

**Valores ausentes**, consistentes nas três bases (o que é bom sinal: não há tratamento diferente
entre desenvolvimento e aplicação):

| Coluna | A | B | C |
|---|---:|---:|---:|
| `renda_mensal_declarada` | 7,70% | 8,60% | 7,90% |
| `tempo_emprego_meses` | 12,07% | 11,87% | 11,60% |
| `score_bureau` | 3,27% | 3,07% | 3,50% |

**Viés de aprovados.** As bases A e B só contêm contratos que a política antiga **aprovou**. A Base
C é mar aberto: inclui perfis que a AutoCred recusava. O deslocamento é grande:

| Corte | Base A | Base C | Razão |
|---|---:|---:|---:|
| `score_bureau` < 500 | 8,7% | 36,1% | **4,16x** |
| Alguma restrição ativa | 47,5% | 66,2% | 1,39x |
| LTV > 90% | 11,9% | 20,9% | 1,75x |
| Prazo de 60 meses | 26,1% | 25,9% | 0,99x |

Mais de um terço da Base C vive numa região onde existem ~870 contratos históricos — e todos eles
passaram por um filtro que já os julgava aceitáveis. A PD estimada ali é **extrapolação otimista**:
o histórico daquela faixa é o dos sobreviventes da seleção. A consequência prática é que qualquer
corte de score calibrado só na Base A tende a aprovar demais no fundo da distribuição.

Repare na última linha: o prazo praticamente não se desloca. O viés não é uniforme — ele está
concentrado em risco de crédito do proponente, não na estrutura da operação.

## O que deu errado

Primeira versão de `mapear_base_c` criava a coluna vazia com `pd.Series(pd.NA, dtype="float64")`,
que estoura com `TypeError: float() argument must be ... not 'NAType'`. O sentinela correto para
uma série float é `float("nan")`; `pd.NA` pertence aos dtypes nullable do pandas. Erro barato
porque a auditoria roda de ponta a ponta e falhou na hora — que é justamente o motivo de o módulo
ter um `__main__` que executa tudo.

## Como reproduzir

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python src/dados.py
```

Confira que a saída traz, nesta ordem: as três bases com 10.000 / 3.000 / 5.000 linhas e zero
duplicidades; PD global de 0,0826; as 6 colunas proibidas lidas do dicionário; `FEATURES (17) passou
na validação: OK`; e `ainda ausentes após o mapeamento: nenhuma`.

Para confirmar que a guarda antivazamento realmente dispara:

```python
from dados import validar_features, FEATURES
validar_features(FEATURES + ["qtd_parcelas_em_atraso_12m"])   # deve erguer VazamentoDetectado
```

---

**Por que `qtd_parcelas_em_atraso_12m` é a armadilha mais perigosa da base** — ela parece informação
de bureau, está presente nas três bases e sozinha dá AuROC de 0,96 — está registrado em
[`aprendizado.md`](../../aprendizado.md), na entrada *"A variável mais preditiva da base é a que
está proibida"*.

**Próximo capítulo:** [02 — Exploração](02-exploracao.md), onde essas 18 candidatas são medidas uma a
uma; depois, [03 — Features](03-features.md), onde as 17 aprovadas viram um `Pipeline` que só
aprende com o treino.
