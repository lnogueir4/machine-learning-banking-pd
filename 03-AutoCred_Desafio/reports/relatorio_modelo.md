# Relatório do Modelo de PD — AutoCred

Grupo ___ · Desafio de Risco de Crédito · setembro de 2026

> Gerado por `src/relatorio_modelo.py`. **Regra de procedência:** todo número deste
> relatório é lido de `artefatos/` ou recalculado aqui, a cada execução, a partir de
> `bases/` e dos arquivos entregues. Nenhum foi digitado. Medição que exigiria
> retreinar o modelo não aparece aqui como número: é descrita e remetida ao capítulo
> de `docs/` que a reproduz.

---

## Resumo

Entregamos `entregaveis/submissao_modelo.csv` — 3.000 linhas, uma por contrato da Base B, com a probabilidade de o contrato atingir 90 dias de atraso nos 12 meses seguintes à concessão (PD 90/12), em 6 casas decimais.

O modelo é um **gradient boosting em árvores** (`HistGradientBoostingClassifier`) com regularização forte — 4 folhas por árvore, taxa de aprendizado 0,03, mínimo de 50 casos por folha, L2 = 1,0 — treinado sobre 17 variáveis e envelopado em calibração sigmoid (Platt) cv=5. Seed 42, Python 3.12.3, scikit-learn 1.6.0.

**O desempenho que reportamos é uma faixa, não um número:** três medições independentes da configuração entregue dão AuROC de 0,7226, 0,7326 e 0,7434. Reportamos **0,72 a 0,74** e não o melhor dos três, porque escolher o maior é escolher a janela mais favorável depois de ver as três.

Em termos de negócio: a faixa 1 da tabela de score quebra **12,6 vezes mais** que a faixa 10 (42,0% contra 3,34%, fora da amostra). É esse número que justifica o modelo existir.

E a limitação que atravessa o relatório inteiro, dita já aqui porque muda a leitura de tudo o que vem depois: **as bases A e B só contêm contratos que a política antiga aprovou**, e a Base C é mar aberto. O PSI entre A e C é 0,473 — a régua chama isso de população trocada. Para o AuROC da Base B isso é irrelevante, porque B tem o mesmo filtro de A. Para a política, não.

---

## 1. O alvo e as três bases

O alvo é `default_90_12`: 1 se o contrato atingiu 90 dias de atraso na janela de 12 meses posterior à concessão. É binário, fechado e sem nulos.

| Base | Linhas | Período | Papel | Tem o alvo? |
|---|---|---|---|---|
| A — desenvolvimento | 10.000 | 01/2022 a 12/2024 | treino e validação | sim |
| B — teste do modelo | 3.000 | 01/2025 a 06/2025 | AuROC oficial, out-of-time | **não** |
| C — política | 5.000 | 07/2025 a 12/2025 | recebe a política; ROI oficial | **não** |

A PD global da Base A é **8,26%** (826 defaults em 10.000 contratos). Por semestre:

| Safra | Contratos | PD observada |
|---|---|---|
| 2022-S1 | 1.702 | 8,58% |
| 2022-S2 | 1.678 | 8,76% |
| 2023-S1 | 1.683 | 9,57% |
| 2023-S2 | 1.607 | 8,28% |
| 2024-S1 | 1.717 | 7,80% |
| 2024-S2 | 1.613 | 6,51% |

A série **cai**, e a queda não é ruído de um semestre: vai de 9,57% no pico a 6,51% no último semestre observado. A Base B é 2025-S1 e a Base C é 2025-S2 — as duas **depois do fim da série**. Um modelo calibrado na Base A inteira carrega o nível médio de 2022-2024 e tende a superestimar a PD dessas safras. Para a submissão do modelo isso não importa: o AuROC lê ordenação, não nível. Para a política, importa, e empurra em sentido contrário ao viés de aprovados — as duas derivas não se cancelam por decreto.

**A Base B não tem o alvo.** Não existe conferir o AuROC antes de enviar; o resultado só aparece na apuração. Tudo o que temos é disciplina de validação interna, e é disso que trata a seção 6.

---

## 2. Vazamento: a defesa é código, não disciplina

O dicionário oficial tem a coluna `Disponível na concessão?`. As colunas marcadas com `NÃO` descrevem o que aconteceu **depois** de conceder:

| Coluna | O que é |
|---|---|
| `qtd_parcelas_em_atraso_12m` | comportamento posterior à concessão; parece bureau e não é |
| `default_90_12` | o próprio alvo |
| `mes_default` | quando o default aconteceu — existe só depois dele |
| `ead_realizado` | exposição apurada no default |
| `lgd_realizado` | perda apurada no workout, 24 meses depois |
| `perda_financeira` | o prejuízo já contabilizado |

A lista não está escrita no código. É **lida do dicionário a cada execução**, e a validação roda antes de qualquer `fit`:

```python
def validar_features(features=None) -> list[str]:
    invasoras = sorted(set(features or FEATURES) & set(colunas_proibidas()))
    if invasoras:
        raise VazamentoDetectado(...)
    return features
```

A alternativa — a lista literal no código — funciona até o material ser atualizado e ninguém lembrar de editá-la. A falha seria silenciosa: o modelo treinaria normalmente. Um modelo que não treina é melhor que um modelo que treina com vazamento.

O tamanho da tentação, medido: `qtd_parcelas_em_atraso_12m` sozinha, como variável única, dá AuROC de **0,9644** na Base A. Ela parece informação de bureau, está presente nas três bases, e é a armadilha mais cara do desafio — qualquer modelo que a use vence qualquer modelo honesto, e não vale nada.

### As nove colunas que a Base C não tem

Há um segundo filtro, que não é vazamento e derruba o mesmo tanto de gente. Comparando as colunas que a Base C **de fato traz** com as permitidas pelo dicionário, nove somem — entre elas `taxa_juros_am` e `parcela_mensal`.

O motivo é conceitual. As bases A e B descrevem **contratos fechados**: taxa e parcela já foram negociadas. A Base C descreve **propostas**, e traz o que o cliente deseja (`ltv_desejado`, `prazo_desejado_meses`, `valor_financiado_desejado`). Quem define as condições efetivas somos nós, pela política. Um modelo que dependa de `taxa_juros_am` **não consegue pontuar a Base C** — a coluna é uma decisão nossa que ainda não foi tomada.

Medido no análogo out-of-time dentro da Base A, o conjunto com preço vale cerca de um milésimo de AuROC a mais e é inutilizável na metade do desafio que vale 40 pontos. A medição está em [`docs/01-dados.md`](../docs/01-dados.md), decisão 2.

---

## 3. Exploração: o sinal é fraco e distribuído

Todas as decisões desta seção foram calculadas na janela de treino (anterior a 2024, 6.670 contratos). A safra de 2024 aparece só para conferir estabilidade, nunca para decidir — escolher variável olhando o conjunto inteiro contamina a validação out-of-time na sua versão mais discreta.

| Variável | IV no treino | Força | PSI A→C | Monotônica? |
|---|---|---|---|---|
| `score_bureau` | 0,1731 | médio | 0,488 | sim |
| `qtd_restricoes_ativas` | 0,1328 | médio | 2,335 | sim |
| `idade_cliente` | 0,1171 | médio | 0,003 | não |
| `renda_mensal_declarada` | 0,1125 | médio | 0,141 | não |
| `prazo_meses` | 0,0773 | fraco | 0,003 | sim |
| `valor_entrada` | 0,0590 | fraco | 0,111 | não |
| `valor_bem` | 0,0545 | fraco | 0,040 | não |
| `comprometimento_renda` | 0,0503 | fraco | — | não |
| `valor_financiado` | 0,0486 | fraco | 0,009 | não |
| `ocupacao` | 0,0469 | fraco | 0,002 | aceitável |
| `tempo_emprego_meses` | 0,0361 | fraco | 0,001 | não |
| `ltv` | 0,0173 | inútil | 0,082 | não |
| `idade_veiculo_anos` | 0,0137 | inútil | 0,022 | aceitável |
| `ano_modelo` | 0,0130 | inútil | 1,394 | aceitável |
| `tipo_residencia` | 0,0118 | inútil | 0,003 | não |
| `qtd_consultas_bureau_3m` | 0,0109 | inútil | 0,076 | sim |
| `possui_avalista` | 0,0093 | inútil | 0,056 | — |
| `canal_originacao` | 0,0080 | inútil | 0,004 | não |

O IV somado é 0,9923 e **nenhuma variável isolada chega a 0,18**. Este é um problema de sinal fraco e distribuído, não um problema com uma variável dominante — o que explica o teto de AuROC em torno de 0,74 e confirma que não há nada escondido esperando ser descoberto. A régua de mercado para IV (abaixo de 0,02 inútil, até 0,10 fraco, até 0,30 médio) é convenção difundida, não norma; acima de 0,50 ela manda suspeitar de vazamento em vez de comemorar.

Duas leituras que mudam decisão:

- **`ltv` com IV de 0,017** é contraintuitivo em financiamento de veículo, onde LTV é *a* variável de garantia. A explicação é o viés de aprovados: a política antiga truncava o LTV, e o que sobrou na base tem pouca variação. `ltv` continua indispensável **fora** do modelo — as tabelas oficiais de EAD e LGD são indexadas por faixa de LTV.
- **`ano_modelo` junta IV inútil com PSI de 1,39.** O PSI alto é artefato de calendário: propostas de 2025 têm veículos mais novos que contratos de 2022. Variável que não prediz e não é estável sai do modelo — é a única que saiu, e é a diferença entre as 18 candidatas e as 17 do modelo.

### O faltante quase não informa

A hipótese de partida era a do mercado: quem não declara renda tem perfil pior, e a ausência viraria indicador.

| Coluna | % ausente em A | em B | em C | n ausente no treino | PD se ausente | PD se presente | Razão |
|---|---|---|---|---|---|---|---|
| `renda_mensal_declarada` | 7,70% | 8,60% | 7,90% | 509 | 9,23% | 8,76% | 1,05x |
| `tempo_emprego_meses` | 12,07% | 11,87% | 11,60% | 780 | 9,74% | 8,68% | 1,12x |
| `score_bureau` | 3,27% | 3,07% | 3,50% | 228 | 10,09% | 8,76% | 1,15x |

**A hipótese não se sustentou.** As razões ficam perto de 1, e o caso mais forte tem n pequeno demais para o intervalo de confiança descolar da média geral. Decisão: **não criar indicadores de ausência**; imputação simples pela mediana, dentro do pipeline. Registrar a hipótese testada e descartada vale mais que o indicador que ela teria gerado — é exatamente a pergunta que a banca faz.

Repare que os percentuais são praticamente iguais nas três bases. Isso é bom sinal: não há tratamento diferente entre desenvolvimento e aplicação.

---

## 4. O achado mais grave: a Base C sai do domínio do treino

Esta seção é a que mais condiciona a política, e ela não aparece em nenhuma métrica de modelo.

| Variável | mín. em A | máx. em A | mín. em C | máx. em C | % de C fora |
|---|---|---|---|---|---|
| `score_bureau` | 460 | 1.000 | 0 | 1.000 | 27,7% |
| `qtd_restricoes_ativas` | 0 | 2 | 0 | 5 | 28,1% |
| `comprometimento_renda` | 0,02 | 0,45 | 0,02 | 1,63 | 11,4% |
| `ltv` | 0,25 | 0,95 | 0,25 | 0,98 | 7,1% |
| `valor_entrada` | 1.107 | 92.223 | 440 | 116.781 | 3,7% |

Os limites são de **toda a Base A** — dez mil contratos. Que nenhum deles tenha mais de duas restrições ativas, ou score de bureau abaixo do piso, não é acaso amostral: é uma **regra da política de 2022**, recuperada dos dados e não de documento algum. O mesmo vale para o teto de comprometimento de renda.

Somando o perímetro das três variáveis de crédito, **42,6% das propostas da Base C caem fora do domínio em ao menos uma delas.** E a consequência é específica: **modelos baseados em árvore não extrapolam.** Um proponente com cinco restrições cai na mesma folha de um com duas e recebe a mesma PD. Como duas restrições já multiplicam a PD em relação a uma, supor que cinco equivalem a duas erra na direção perigosa — o modelo **subestima sistematicamente** o risco de mais de um quarto da Base C.

Repare nas duas últimas linhas da tabela: `ltv` e `valor_entrada` mal se deslocam. **O viés não é uniforme** — está concentrado no risco de crédito do proponente, não na estrutura da operação. E há uma boa notícia nisso, que o capítulo de política herda: comprometimento de renda é consequência da **oferta**, e oferta é a alavanca que controlamos. Score de bureau e restrições ativas, não.

Isto é o problema de inferência de rejeitados que o enunciado antecipa, agora localizado em variáveis específicas e medido. Ele **não se resolve com modelagem melhor**: não existe informação na base sobre como se comporta quem tem cinco restrições. A solução tem de ser uma regra de política explícita, defendida como decisão de risco e não como saída de modelo.

---

## 5. Pré-processamento: um `Pipeline`, e nenhuma decisão fora dele

Imputação, encoding e padronização vivem dentro de um `Pipeline` do scikit-learn. Não é cerimônia: é o que transforma a promessa de "ajustar só no treino" em propriedade do objeto. Calcular a mediana da renda na base inteira e só depois separar treino e teste contamina a validação sem produzir mensagem de erro alguma.

### Decisão 1 — nenhuma variável derivada entrou

Testamos 7 candidatas, todas calculáveis também na Base C, por validação cruzada de 5 dobras **dentro da janela de treino**:

| Conjunto | AuROC CV | dp | AuROC OOT 2024 | ΔCV |
|---|---|---|---|---|
| 17 features (baseline) | 0,7249 | ±0,0197 | 0,7410 | — |
| + `entrada_sobre_renda` | 0,7210 | ±0,0211 | 0,7366 | −0,0039 |
| + `financiado_sobre_renda` | 0,7186 | ±0,0259 | 0,7395 | −0,0064 |
| + `bem_sobre_renda` | 0,7214 | ±0,0221 | 0,7397 | −0,0035 |
| + `score_por_restricao` | 0,7195 | ±0,0198 | 0,7387 | −0,0054 |
| + `pressao_bureau` | 0,7240 | ±0,0197 | 0,7427 | −0,0009 |
| + `estabilidade_emprego` | 0,7192 | ±0,0223 | 0,7376 | −0,0057 |
| + `idade_veiculo_no_fim` | 0,7254 | ±0,0211 | 0,7439 | +0,0005 |
| + todas as sete | 0,7170 | ±0,0196 | 0,7368 | −0,0080 |

Nenhuma entrou. Seis das sete pioram a validação cruzada; a sétima melhora por uma fração do desvio padrão da própria medida — não é ganho, é o segundo decimal do ruído. A leitura não é "engenharia de atributos não funciona": é que o sinal desta base já foi medido na seção 3, e gradient boosting constrói interações por conta própria. Cada variável a mais é uma a justificar, monitorar e calcular na Base C; variável que não paga o próprio custo sai.

### Decisão 2 — `NaN` preservado para a árvore

| Modelo | Tratamento | AuROC CV | dp | AuROC OOT 2024 |
|---|---|---|---|---|
| HistGB | NaN preservado + ordinal | 0,7249 | ±0,0197 | 0,7410 |
| HistGB | imputação mediana + ordinal | 0,7238 | ±0,0241 | 0,7398 |
| Logística | mediana + one-hot + padronização | 0,6520 | ±0,0312 | 0,6553 |

O `HistGradientBoostingClassifier` aprende, em cada corte, para que lado mandar o ausente. Isso é estritamente mais informativo que substituir pela mediana, que apaga a distinção entre "renda de R$ 5.222" e "renda não declarada". A vantagem é pequena e sozinha não decidiria nada — mas as duas réguas apontam para o mesmo lado, e preservar o ausente é também a opção que não inventa dado. A logística não aceita `NaN` e recebe o tratamento clássico; ela não é candidata a vencer, é o referencial interpretável.

### Decisão 3 — a parcela da Base C é reconstruída pela Price

`comprometimento_renda` (parcela ÷ renda) é a variável de maior ganho marginal isolado do modelo, e **a Base C não tem parcela**. Deixá-la vazia custa mais AuROC do que qualquer ganho que a engenharia de atributos ofereceu — a coluna tem 0% de ausentes no treino, então o modelo não tem folha de ausente treinada para ela.

A reconstrução usa a fórmula da tabela Price com a taxa mediana da janela de treino, **1,587% a.m.**, lida da Base A a cada execução e nunca digitada. Ela funciona porque a Base A foi gerada por Price — a fórmula reproduz a `parcela_mensal` registrada com erro relativo da ordem de 10⁻⁶ — e porque a carteira antiga mal diferenciava preço.

O laço é circular só na aparência: para pontuar é preciso a parcela, para a parcela é preciso a taxa, e a taxa depende da faixa. Resolve-se em **duas passadas** — a primeira com as condições desejadas e a taxa de referência, para enquadrar; a segunda com as condições ofertadas, para decidir. É o que qualquer banco que pratica preço por risco faz.

---

## 6. Seleção do modelo

O split é temporal: treino em 2022-2023 (6.670 contratos), validação em 2024 (3.330). Imita a situação real — a Base B é posterior a tudo que temos. Um split aleatório mediria a capacidade de interpolar dentro do mesmo período, que é pergunta mais fácil e diferente da que a nota faz.

**O ponto fino é onde a maioria escorrega:** os hiperparâmetros saíram de validação cruzada de 5 dobras dentro de 2022-2023, nunca olhando 2024. E não só os do vencedor — **todos os candidatos ajustáveis passam pela mesma busca**, na mesma janela, com a mesma métrica:

| Candidato | Combinações | Vencedor da grade |
|---|---|---|
| Regressão logística | 7 | `C=0.01` |
| Árvore de decisão | 48 | `criterion=entropy`, `max_depth=6`, `min_samples_leaf=200` |
| Random Forest | 40 | `max_depth=12`, `max_features=0.5`, `min_samples_leaf=20` |
| HistGB regularizado | 54 | `learning_rate=0.03`, `max_leaf_nodes=4`, `min_samples_leaf=50`, `l2_regularization=1.0` |

Buscar só para o favorito e deixar os concorrentes com parâmetro de fábrica produz uma comparação arranjada: o vencedor ganharia por ter sido ajustado, não por ser melhor. Foi assim que a primeira versão desta tabela foi montada, e a correção mudou números de verdade.

A comparação abaixo é **anterior à calibração** — os cinco candidatos crus, para que a disputa entre eles seja justa. O modelo entregue é o vencedor já calibrado, e por isso o AuROC desta tabela não é o mesmo da seção 10.

| Modelo | AUC treino | AUC OOT 2024 | queda | KS | Brier | viés |
|---|---|---|---|---|---|---|
| Regressão logística | 0,6658 | 0,6521 | 0,0137 | 0,244 | 0,0648 | +0,0149 |
| Árvore de decisão | 0,7351 | 0,7044 | 0,0307 | 0,305 | 0,0644 | +0,0138 |
| Random Forest | 0,9212 | 0,7353 | 0,1860 | 0,374 | 0,0619 | +0,0152 |
| HistGB padrão | 0,9982 | 0,7097 | 0,2886 | 0,333 | 0,0645 | −0,0007 |
| **HistGB regularizado** | 0,8117 | 0,7410 | 0,0707 | 0,376 | 0,0616 | +0,0151 |

Três leituras:

**O overfit é visível a olho nu.** `HistGB padrão` e `HistGB regularizado` são o *mesmo algoritmo*: 0,9982 contra 0,8117 no treino. O de cima decorou a base contrato a contrato e generalizou **pior** (0,7097 contra 0,7410). Pôr o freio derruba o treino em 0,19 e **sobe** o teste. Regularizar não é conservadorismo; é a diferença entre um modelo que sabe e um que decorou.

**A vitória do boosting sobre a floresta não é estatisticamente decisiva.** São 0,0057 de AuROC contra um desvio de validação de cerca de 0,02. Escolher pela terceira casa decimal seria o erro que a seção 7 descreve. O que decide são os outros critérios, e todos apontam para o mesmo lado: Brier melhor, KS melhor e, sobretudo, uma queda treino→teste de 0,07 contra 0,19. Entre dois modelos equivalentes, fica o que depende menos de ter decorado.

**A logística é o piso honesto.** Ela custa 0,089 de AuROC, caro demais para ser o modelo final, mas é o referencial: se o boosting não superasse com folga, não pagaria a própria opacidade. A árvore ajustada é o melhor modelo **legível** que temos — seis perguntas encadeadas chegam a 0,7044. A diferença entre o que se explica num quadro branco e o que se explica num gráfico de importâncias tem preço, e ele está medido.

### Calibração sigmoide, não isotônica

O AuROC ignora calibração. A política, não: a perda esperada é `PD × EAD × LGD`, e erro de nível na PD vira erro de preço direto. Calibrar em dobras internas do treino agrega as cinco dobras e, de brinde, sobe o AuROC out-of-time de 0,7410 para 0,7434.

As duas calibrações disponíveis empatam em discriminação e em Brier, então o critério é o comportamento no extremo: por ser função escada, a **isotônica devolve PD exatamente igual a 1,0000** para alguns contratos. Probabilidade de 1 é indefensável como estimativa e, multiplicada por EAD e LGD, produz perda esperada igual à exposição inteira. Ficamos com a sigmoide de Platt.

O modelo de produção é **reajustado em toda a Base A** depois de validado o desenho. Segurar 2024 fora do treino, depois que a pergunta "isto generaliza?" já foi respondida, joga fora um terço dos dados — e justamente o terço mais próximo, no tempo, da Base B. A configuração está congelada antes disso; nenhuma decisão sai do reajuste.

---

## 7. A poda que parecia boa e não era

Esta é a decisão mais importante do relatório, e ela foi de **não fazer** nada.

A importância por permutação no out-of-time de 2024 sugeria cortar muita coisa — duas variáveis com contribuição negativa e várias em torno de zero:

| Variável | queda de AuROC ao embaralhar | dp |
|---|---|---|
| `idade_cliente` | +0,0816 | ±0,0047 |
| `score_bureau` | +0,0683 | ±0,0063 |
| `prazo_meses` | +0,0608 | ±0,0090 |
| `comprometimento_renda` | +0,0283 | ±0,0046 |
| `qtd_restricoes_ativas` | +0,0247 | ±0,0050 |
| `ocupacao` | +0,0184 | ±0,0061 |
| `tempo_emprego_meses` | +0,0126 | ±0,0051 |
| `valor_entrada` | +0,0049 | ±0,0031 |
| `idade_veiculo_anos` | +0,0037 | ±0,0037 |
| `renda_mensal_declarada` | +0,0016 | ±0,0018 |
| `canal_originacao` | +0,0007 | ±0,0007 |
| `tipo_residencia` | +0,0006 | ±0,0008 |
| `qtd_consultas_bureau_3m` | +0,0003 | ±0,0006 |
| `valor_financiado` | +0,0001 | ±0,0021 |
| `possui_avalista` | 0,0000 | ±0,0000 |
| `valor_bem` | −0,0018 | ±0,0013 |
| `ltv` | −0,0044 | ±0,0038 |

E a poda parecia confirmada pelo próprio out-of-time: quanto mais se cortava, melhor ficava. Não podamos. O out-of-time de 2024 já vinha sendo consultado muitas vezes; escolher o conjunto de variáveis por ele é transformá-lo em conjunto de treino.

Montamos então uma validação **encadeada**, em três janelas que nunca haviam sido usadas para nada e todas anteriores a 2024:

| Conjunto | 2022 -> 2023-S1 | 2022 -> 2023 | 2022+23-S1 -> 2023-S2 | média | *OOT 2024* |
|---|---|---|---|---|---|
| 17 (atual) | 0,7171 | 0,7228 | 0,7279 | **0,7226** | *0,7434* |
| 18 (com ano_modelo) | 0,7171 | 0,7228 | 0,7279 | **0,7226** | *0,7434* |
| 15 sem valor_bem e ltv | 0,7142 | 0,7210 | 0,7299 | **0,7217** | *0,7486* |
| 11 sem as de importância ~0 | 0,7134 | 0,7200 | 0,7303 | **0,7212** | *0,7518* |
| 7 principais | 0,7205 | 0,7127 | 0,7149 | **0,7160** | *0,7546* |

**As duas últimas colunas são a mesma lista lida por duas réguas, e elas discordam de ponta a ponta.** No out-of-time a qualidade sobe monotonicamente conforme se poda (0,7434 → 0,7546); nas janelas independentes, **desce** (0,7226 → 0,7160). Os 0,011 de vantagem das sete variáveis eram coincidência de janela — e teriam sido apresentados à banca como melhoria se a única régua fosse aquela.

Repare na segunda linha: o conjunto com `ano_modelo` devolve **exatamente os mesmos** quatro números do conjunto sem ela. A variável entra e sai sem mexer em nenhuma casa decimal. Foi removida por isso somado ao PSI de calendário e ao domínio estourado — nunca por ter perdido uma disputa de métrica.

> **Erro de processo que vale registrar:** a remoção de `ano_modelo` estava decidida e
> escrita em `docs/02-exploracao.md` desde a sessão anterior, mas nunca havia chegado ao
> código. Foi a importância por permutação, medida por outro motivo, que denunciou.
> Decisão documentada não é decisão implementada, e só o código sabe a diferença. Os dois
> nomes — `CANDIDATAS` (18) e `FEATURES` (17) — existem hoje
> para que a diferença seja explícita e auditável.

---

## 8. O score de 1 a 10

A política opera sobre faixas, não sobre a PD contínua. Agrupar joga informação fora de propósito; a pergunta é quanto, onde cortar, e o que a tabela resultante realmente prova.

### Os cortes saem da PD out-of-fold

O modelo final foi reajustado em toda a Base A. Pedir a ele a PD dos contratos que o treinaram devolve memória, não estimativa. A alternativa é a PD **out-of-fold**: cinco dobras, cada contrato pontuado por um modelo que não o conhecia.

A distribuição de PD é quase a mesma nas duas — os cortes mudariam na terceira casa. **O que muda é a promessa de nível.** Medido pela PD de dentro da amostra, o AuROC aparente salta de 0,7326 para 0,8088, e a tabela prometeria à política uma faixa 10 quase sem inadimplência. A realidade fora da amostra é várias vezes pior. A política precificaria de graça e descobriria o erro na apuração do ROI.

### Faixas desiguais, largas no risco baixo

A escolha óbvia é o decil. Ela falhou: com dez faixas de mil contratos, a faixa 10 — a melhor da tabela — quebrou mais que as faixas 7, 8 e 9. Não por bug. O modelo simplesmente não distingue risco abaixo de 6% de PD, e a diferença entre 3,0% e 3,7% desaparece no erro amostral.

A correção vem de uma observação simples: **separar duas faixas exige população proporcional à dificuldade da separação.** Distinguir 42% de 25% cabe em 300 contratos; distinguir 3,3% de 3,4% não cabe em 2.000. Logo as faixas boas têm de ser grandes e as ruins pequenas — o inverso do decil.

| Estratégia | AuROC da faixa | rho | inversões | pares indistintos | menor faixa em A | menor faixa em C |
|---|---|---|---|---|---|---|
| quantis (decis) | 0,7276 | −0,915 | 3 | 8 de 9 | 1.000 | 266 |
| largura igual em log-odds | 0,7218 | −1,000 | 0 | 6 de 9 | 7 | 8 |
| caudas finas | 0,7289 | −0,927 | 1 | 5 de 9 | 200 | 141 |
| **progressiva** | 0,7297 | −0,988 | 1 | 7 de 9 | 300 | 320 |
| PD fixa de negócio | 0,7297 | −0,964 | 2 | 6 de 9 | 40 | 8 |

Duas armadilhas merecem leitura explícita. **"Largura igual em log-odds" é perfeitamente monotônica** — rho de −1,000, zero inversões — e é inútil: consegue isso porque a faixa 1 tem sete contratos. Monotonicidade num grupo de sete pessoas não é propriedade do modelo, é sorte. Foi o candidato mais bonito na métrica e o primeiro a ser descartado. **"PD fixa de negócio"** empata em AuROC e tem o atrativo de dar significado absoluto à faixa; cai pelo mesmo motivo, com oito propostas na faixa 10 da Base C.

A granularidade foi medida à parte, variando **só o número de faixas** e mantendo a estratégia de corte fixa em quantis:

| Granularidade (quantis) | AuROC | inversões | pares indistintos | menor faixa em C |
|---|---|---|---|---|
| 5 faixas | 0,7154 | 1 | 1 de 4 | 568 |
| 10 faixas | 0,7276 | 3 | 8 de 9 | 266 |
| 20 faixas | 0,7311 | 9 | 17 de 19 | 131 |
| PD contínua | 0,7326 | — | — | — |

Vinte faixas devolvem pouco AuROC e triplicam as inversões. A tabela que de fato usamos é a progressiva de dez faixas, que entrega 0,7297 — melhor que os decis de mesma granularidade e a 0,0029 da PD contínua. Agrupar custa 0,4% do poder de ordenação.

### Os cortes são números fixos, não quantis recalculados

Os nove cortes estão congelados no código como valores absolutos de PD:

```
  0,0369  0,0448  0,0542  0,0663  0,0839  0,1067  0,1428  0,2096  0,3017
```

Recalcular os percentis dentro de cada base garantiria faixas sempre bem povoadas, e é errado por dois motivos. **Destruiria o alarme:** se a faixa 10 contém por definição os 20% melhores de qualquer população, o PSI entre A e C mede zero — exatamente quando a população trocou. E **quebraria a coerência do preço:** a faixa 8 precisa significar a mesma PD em 2025 e em 2026.

A regra é fechada embaixo e aberta em cima: PD exatamente igual a um corte cai na faixa **pior**. É `searchsorted(..., side="right")`, e é o que permite reproduzir `score_1a10` a partir da coluna `pd` da submissão.

### A tabela de faixas — Base A, PD out-of-fold

| Faixa | n | PD de | PD até | PD prevista | PD observada | IC 95% |
|---|---|---|---|---|---|---|
| 1 | 300 | 30,22% | 79,93% | 41,10% | **42,00%** | 36,4% – 47,6% |
| 2 | 400 | 21,01% | 30,17% | 24,70% | 24,75% | 20,5% – 29,0% |
| 3 | 600 | 14,28% | 20,95% | 17,13% | 19,00% | 15,9% – 22,1% |
| 4 | 700 | 10,67% | 14,28% | 12,25% | 12,00% | 9,6% – 14,4% |
| 5 | 800 | 8,39% | 10,67% | 9,43% | 8,88% | 6,9% – 10,8% |
| 6 | 1.000 | 6,63% | 8,39% | 7,44% | 8,60% | 6,9% – 10,3% |
| 7 | 1.200 | 5,42% | 6,63% | 5,96% | 5,67% | 4,4% – 7,0% |
| 8 | 1.406 | 4,48% | 5,42% | 4,92% | 4,13% | 3,1% – 5,2% |
| 9 | 1.588 | 3,69% | 4,48% | 4,08% | 3,34% | 2,5% – 4,2% |
| 10 | 2.006 | 1,14% | 3,69% | 3,07% | **3,34%** | 2,6% – 4,1% |

- rho de Spearman faixa × PD observada: **−0,988**
- inversões materiais: **nenhuma**
- pares que o dado não separa: **7 de 9**

A última linha é o achado desconfortável, e preferimos publicá-lo a escondê-lo. **Pares indistintos** são faixas vizinhas cujos intervalos de confiança de 95% se sobrepõem. Isso não invalida a tabela — a ordenação geral está correta e não há nenhuma inversão material, isto é, nenhuma faixa melhor com PD comprovadamente maior que a pior. O que invalida é a **pretensão de dez preços distintos**. Com dez mil contratos e PD média de 8,26%, a Base A não sustenta dez níveis de risco distinguíveis — sustenta uns quatro ou cinco. A consequência prática é que a política agrupa faixas vizinhas para definir taxa, prazo e entrada: a tabela reporta dez porque a submissão exige `score_1a10`, e o tratamento diferenciado tem menos degraus do que isso.

A única inversão de direção está entre as faixas 9 e 10, e vale dois milésimos de ponto percentual. A diferença entre inversão material e ruído amostral é o que separa rejeitar uma tabela boa de aceitar uma ruim.

---

## 9. Estabilidade, e o viés de aprovados em um número

| Faixa | Base A | Base B (submissão) | Base C |
|---|---|---|---|
| 10 | 20,1% | 21,9% | 12,6% |
| 9 | 15,9% | 16,5% | 9,1% |
| 8 | 14,1% | 13,6% | 8,7% |
| 7 | 12,0% | 12,5% | 7,6% |
| 6 | 10,0% | 9,6% | 8,4% |
| 5 | 8,0% | 8,0% | 6,4% |
| 4 | 7,0% | 6,0% | 7,3% |
| 3 | 6,0% | 5,5% | 11,3% |
| 2 | 4,0% | 3,6% | 14,3% |
| 1 | 3,0% | 2,6% | 14,3% |

Dentro do universo de contratos aprovados a régua é notavelmente estável. Tomando a safra de 2022 como referência, o PSI da **Base B** é **0,0062** — e ela é meio ano posterior a tudo que o modelo viu. **A Base C é outro planeta:** PSI de **0,473**, que a régua chama de população trocada (abaixo de 0,10 estável, 0,10 a 0,25 atenção, acima de 0,25 trocada).

| Base | PD média prevista | mediana | p90 | acima de 20% |
|---|---|---|---|---|
| A — 2022-2024, aprovados | 8,30% | 5,31% | 17,21% | 7,8% |
| B — 2025-S1, aprovados | 7,93% | 5,25% | 16,04% | 7,0% |
| **C — 2025-S2, mar aberto** | **15,54%** | 9,60% | 34,22% | **30,1%** |

Não é deterioração do modelo — é o viés de aprovados aparecendo em número. A Base C contém os perfis que a política antiga recusava, e o modelo corretamente os pontua como piores. Aqui está o limite de honestidade da defesa: **a tabela de faixas foi validada em contratos aprovados; a faixa 1 da Base C contém perfis que nunca receberam crédito nesta casa, e a PD deles é extrapolação, não medição.**

---

## 10. O desempenho que reportamos, e por que é uma faixa

O mesmo modelo foi medido três vezes, de formas independentes:

| Medição | AuROC | O que ela mede |
|---|---|---|
| Validação encadeada em janelas anteriores a 2024 | 0,7226 | três janelas nunca usadas para decidir nada; a mais conservadora |
| Out-of-fold sobre toda a Base A | 0,7326 | cinco dobras sorteadas; é a PD que define os cortes de faixa |
| Out-of-time na safra de 2024 | 0,7434 | treino em 2022-23, teste em 2024; imita a Base B |

As três caem no mesmo lugar, e a dispersão entre elas (0,0208) é da ordem do desvio padrão da própria validação cruzada. Curiosamente a medição out-of-fold é **pior** que a out-of-time, apesar de treinar com mais dados: a explicação é que a safra de 2024 é mais separável que a média do período, não que prever o futuro seja mais fácil.

**Reportamos 0,72 a 0,74.** Reportar o melhor dos três seria escolher a janela mais favorável depois de ver as três — a mesma falha que a seção 7 descreve, em outra roupa. O KS out-of-time do modelo escolhido é 0,376 e o Gini, 0,482.

---

## 11. Limitações conhecidas

Em ordem de gravidade, e nenhuma delas se resolve com mais modelagem:

1. **Viés de aprovados.** 42,6% da Base C está fora do domínio histórico em ao menos uma variável de crédito. Árvore não extrapola: nessa região a PD é o valor do extremo conhecido, o que **subestima** o risco. Não há na base informação sobre quem a política antiga recusava.
2. **Deriva de safra.** A PD cai ao longo da Base A e as bases B e C são posteriores ao fim da série. O nível calibrado tende a **superestimar** 2025. Esta deriva e a anterior empurram em sentidos opostos e não se cancelam por decreto — o que este relatório entrega é o tamanho de cada uma, medido.
3. **Dez faixas, 7 pares indistintos.** A tabela ordena bem e não sustenta dez preços distintos. A política precisa agrupar, e o relatório de política diz como.
4. **Sem alvo na Base B.** Nenhuma conferência do AuROC é possível antes da apuração. A faixa reportada na seção 10 é a melhor estimativa que a disciplina de validação permite, e não uma medição do que será apurado.

---

## 12. A submissão

`entregaveis/submissao_modelo.csv`, 3.000 linhas, colunas `id_contrato,pd`, UTF-8, sem índice, decimal com ponto. PD média de 7,93%.

As PDs são gravadas com **6 casas decimais**, e a escolha foi medida em vez de arbitrada. Arredondar move contratos de faixa, e contrato que troca de faixa troca de preço:

| Arredondamento | Contratos que trocam de faixa | AuROC | Δ vs. PD crua |
|---|---|---|---|
| 2 casas | 339 | 0,732020 | −0,000551 |
| 3 casas | 83 | 0,732628 | +0,000057 |
| 4 casas | 19 | 0,732553 | −0,000017 |
| 5 casas | 1 | 0,732572 | +0,000001 |
| 6 casas | 0 | 0,732570 | −0,000000 |

Com 6 casas, **nenhum** contrato troca de faixa e o AuROC é o da PD crua. Duas casas já moveriam centenas. O custo de gravar quatro dígitos a mais é zero; o custo de descobrir o contrário depois da apuração, não.

A geração das duas submissões passa por 30 conferências automáticas (0 falhas na última execução), todas lendo os CSVs do disco e não o DataFrame que os gerou.

---

## 13. Como reproduzir

```bash
cd 03-AutoCred_Desafio
PYTHONIOENCODING=utf-8 python src/dados.py                     # auditoria e antivazamento
PYTHONIOENCODING=utf-8 python notebooks/01-exploracao.py       # IV, WoE, PSI, domínio
PYTHONIOENCODING=utf-8 python notebooks/02-decisoes-features.py
PYTHONIOENCODING=utf-8 python src/features.py                  # diagnóstico do pipeline
PYTHONIOENCODING=utf-8 python src/modelo.py --busca --poda     # grades, poda, modelo final
PYTHONIOENCODING=utf-8 python notebooks/03-decisoes-score.py   # as cinco estratégias
PYTHONIOENCODING=utf-8 python src/score.py                     # tabela de faixas
PYTHONIOENCODING=utf-8 python src/submissoes.py                # os dois CSVs entregues
PYTHONIOENCODING=utf-8 python src/relatorio_modelo.py          # este relatório
```

Seed 42 em todo o pipeline. Cada execução grava versões e metadados em `artefatos/*.json`. O modelo serializado é `artefatos/modelo_pd.joblib`; a construção capítulo a capítulo está em [`docs/`](../docs/README.md), de `01-dados.md` a `05-score.md`.

**O que confere que deu certo:** o vencedor da comparação é o `HistGB regularizado` com AuROC out-of-time de 0,7410 e queda de treino para teste abaixo de 0,08; os cortes recalculados por `src/score.py --refazer` coincidem com os nove valores congelados em `CORTES`; a faixa 1 tem PD observada de 42,0% e a faixa 10, de 3,34%; e `src/submissoes.py` fecha com 30 checagens e nenhuma falha.

