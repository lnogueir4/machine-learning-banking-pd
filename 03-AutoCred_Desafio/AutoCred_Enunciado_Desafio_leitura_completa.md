# Desafio AutoCred - Enunciado

## Extração estruturada e leitura visual do PDF

**Documento de origem:** `AutoCred_Enunciado_Desafio.pdf`  
**Extensão:** 4 páginas  
**Título registrado nos metadados:** *Desafio AutoCred - Enunciado*  
**Autoria indicada nos metadados:** Analítica Educação - Programa Jump

> Nota de tratamento: o PDF possui camada de texto nativa. O conteúdo foi normalizado e reorganizado para Markdown, com leitura complementar das quatro páginas renderizadas, incluindo tabelas, caixas de destaque, fórmulas e estrutura visual. Não há dados pessoais repetidos em rodapé neste documento.

## Visão geral

Este documento é a especificação operacional do Desafio AutoCred. Ele complementa os slides de lançamento ao detalhar:

- contexto da fintech e objetivo do conselho;
- entregáveis de modelagem e política de crédito;
- bases A, B e C;
- parâmetros fornecidos de EAD e LGD;
- cálculo do ROI;
- alavancas e guardrails da política;
- comportamento dinâmico da Base C;
- divisão de responsabilidades;
- cronograma e regras metodológicas iniciais.

O objetivo não é apenas construir um classificador. O grupo precisa integrar modelagem, risco e resultado econômico:

`Dados → PD → Score → EAD/LGD → Perda esperada → Política → Aceite → Carteira → ROI`

---

## Leitura página a página

### Página 1 - Caso, entregáveis e início das bases

#### Contexto da AutoCred

A AutoCred é apresentada como fintech de financiamento de veículos leves, operando desde janeiro de 2022 por quatro canais:

- concessionárias;
- revendas multimarcas;
- canal digital próprio;
- correspondentes bancários.

O crescimento de volume não foi acompanhado pela qualidade da carteira. A inadimplência de 2024 superou o planejamento e o conselho atribuiu o problema à concessão. A política original priorizava crescimento e não havia sido revisada desde 2022.

Dois fatores ampliam a perda:

1. **LTV elevado:** média de 74%, com contratos chegando a 95% do valor do veículo.
2. **Recuperação imatura:** LGD aproximada de 70%, comparada no enunciado a uma faixa de 45% a 55% em instituições mais estabelecidas.

#### Objetivo do conselho

Construir uma política de concessão para 2026 que entregue ROI anualizado superior a 15%, preserve a originação e respeite o apetite ao risco.

#### Dois desafios

| Entregável | Objetivo | Métrica oficial |
|---|---|---|
| Modelo de PD | estimar a probabilidade de atingir 90 dias de atraso nos 12 meses posteriores à concessão | AuROC na Base B out-of-time; KS como métrica secundária |
| Política de crédito | decidir aprovação, taxa, prazo e entrada | ROI anualizado na Base C, condicionado aos guardrails |

#### Base A

A primeira linha da tabela de dados informa que a Base A contém 10.000 contratos originados entre janeiro de 2022 e dezembro de 2024, todos com janela de performance de 12 meses encerrada. Inclui target e valores realizados de EAD e LGD.

**Leitura visual:** documento em formato A4, com títulos azul-escuros e uma caixa destacada para o pedido do conselho. A página termina no meio da tabela das bases, que continua na página seguinte.

### Página 2 - Bases, EAD/LGD, ROI e início da política

#### Bases B e C

| Base | Período e volume | Finalidade |
|---|---|---|
| B - Teste | 3.000 contratos de janeiro a junho de 2025 | mesmas variáveis, sem alvo visível; usada para AuROC out-of-time |
| C - Propostas | 5.000 propostas do segundo semestre de 2025 | recebe a política; taxa e prazo serão definidos pelo grupo |

O dicionário de dados deve indicar se cada campo estava disponível no momento da concessão. Essa informação é decisiva para excluir variáveis futuras.

#### Inferência de rejeitados

As bases A e B contêm apenas contratos aprovados pela política anterior, enquanto C inclui proponentes antes recusados. Portanto, a população em que o modelo será aplicado é mais ampla que a população de desenvolvimento.

Esse descasamento cria risco de seleção amostral e de inferência de rejeitados. O modelo pode apresentar boa discriminação entre aprovados históricos e ainda falhar em regiões do perfil de clientes que não estavam representadas no treino.

#### EAD e LGD fornecidos

Os participantes modelam somente a PD. O arquivo citado `autocred_parametros_ead_lgd.xlsx` deve fornecer:

- **EAD:** fator por prazo e faixa de LTV, complementado por uma fórmula baseada no saldo devedor pela Tabela Price no mês do default e nas três parcelas vencidas que caracterizam o atraso de 90 dias;
- **LGD:** tabela por idade do veículo e faixa de LTV, com ajuste para existência de avalista e workout de 24 meses.

A perda esperada é:

`Perda esperada = PD × (Fator EAD × Valor financiado) × LGD`

Os parâmetros podem ser comparados aos valores realizados disponíveis na Base A.

#### Cálculo do ROI

`ROI anual = [(Juros recebidos - Perda realizada) / Volume financiado] / Prazo médio em anos`

Duas regras são explicitadas:

1. contratos inadimplentes geram juros apenas até o mês do default;
2. somente propostas efetivamente contratadas entram no resultado; uma aprovação recusada pelo cliente não gera receita nem perda.

#### Início da política

A página inicia a tabela das quatro alavancas:

- **Aprovar ou negar:** define o corte de score e o perfil da carteira; restrição excessiva reduz originação.
- **Taxa de juros:** precisa cobrir perda e margem; preço excessivo reduz aceite e intensifica seleção adversa.

**Leitura visual:** há duas caixas de destaque: uma vermelha para o problema de inferência de rejeitados e fórmulas centralizadas em azul para perda esperada e ROI. A tabela de política é dividida entre as páginas 2 e 3.

### Página 3 - Política, guardrails e dinâmica da Base C

#### Continuação das alavancas

| Alavanca | Efeito | Custo do excesso |
|---|---|---|
| Prazo máximo | prazo longo reduz a parcela, mas prolonga exposição ao risco | prazo muito curto pode tornar a prestação inviável |
| Entrada mínima | reduz LTV e, no simulador, PD e LGD | entrada alta reduz aceitação |

#### Score de 1 a 10

A política deve operar sobre faixas de score, e não diretamente sobre a PD contínua:

- score 1 = maior risco e maior PD;
- score 10 = menor risco e menor PD.

Os próprios participantes definem como agrupar as probabilidades em dez faixas. Essa escolha afeta monotonicidade, volume por faixa, estabilidade e granularidade da política.

#### Guardrails

| Restrição | Limite | Penalidade |
|---|---:|---|
| Taxa de aprovação | pelo menos 35% das 5.000 propostas | nota de política reduzida pela metade |
| CET | no máximo 3,5% ao mês | taxa truncada automaticamente |
| Inadimplência | no máximo 8% dos contratos fechados | nota de política reduzida pela metade |
| Volume originado | pelo menos R$ 40 milhões contratados | nota de política reduzida pela metade |

O limite de volume evita uma solução degenerada que preserve ROI aprovando formalmente muitas propostas, mas imponha preço e entrada que reduzam drasticamente a contratação efetiva.

#### Comportamento da Base C

A Base C não possui resultados fixos independentes da política. As condições ofertadas alteram o comportamento dos proponentes:

- taxa maior reduz aceite;
- taxa maior aumenta a PD por seleção adversa;
- entrada maior reduz LTV, PD e LGD, mas também reduz aceite;
- prazo menor eleva parcela e comprometimento de renda, reduzindo aceite.

A direção dos efeitos é conhecida; a intensidade não é informada. Como existe apenas uma submissão, o enunciado desencoraja otimização por tentativa e erro.

#### Determinismo

Os sorteios do simulador são fixos: políticas idênticas produzem o mesmo resultado. Diferenças entre grupos decorrem das decisões, não de variação aleatória entre execuções.

**Leitura visual:** a tabela de guardrails ocupa o centro da página. O bloco de determinismo aparece em uma caixa verde, diferenciando uma garantia do simulador dos alertas e restrições anteriores.

### Página 4 - Organização, cronograma e lembretes metodológicos

#### Papéis do grupo

| Papel | Responsabilidades |
|---|---|
| Modelagem de PD | análise exploratória, pipeline, seleção de variáveis, validação out-of-time e modelo final |
| Política e precificação | faixas de score, corte, taxa, prazo, entrada e simulação interna |
| Negócio | documento de política, projeção e defesa perante o conselho |

A divisão existe para reproduzir uma estrutura real de risco de crédito e evitar concentração de todo o trabalho em uma pessoa.

#### Cronograma

| Data | Marco |
|---|---|
| 12/09/2026 | lançamento e entrega das Bases A e B, dicionário, parâmetros de EAD/LGD e modelos de submissão |
| 25/09/2026 às 23h59 | entrega do scoring da Base B e das decisões de política para a Base C |
| 26/09/2026 | apuração, leaderboard, apresentações e debrief durante a mentoria |

#### Regras metodológicas antes de começar

- excluir informações que não existiam no momento da concessão;
- respeitar a ordem temporal e usar avaliação no período seguinte;
- ajustar imputação, padronização, encoding e seleção de variáveis apenas no treino, preferencialmente dentro de um pipeline.

O documento remete as regras completas de submissão e a rubrica a outro arquivo, denominado *AutoCred - Regras da Competição*.

**Leitura visual:** três tabelas ou blocos principais organizam papéis, cronograma e lembretes. Há bastante espaço em branco na metade inferior da página, indicando encerramento do enunciado.

---

## Requisitos consolidados do desafio

### Modelo

- Target: PD 90/12.
- Base de desenvolvimento: A.
- Teste oficial: B, out-of-time e sem target visível.
- Métrica primária: AuROC.
- Métrica secundária: KS.
- Restrições: ausência de vazamento, variáveis disponíveis na concessão e pipeline reprodutível.

### Política

- Aplicação sobre a Base C.
- Regras por faixa de score.
- Decisões: aprovar, taxa, prazo e entrada.
- Resultado: ROI anualizado.
- Restrições: aprovação mínima, CET máximo, inadimplência máxima e volume mínimo.
- Submissão única e simulador determinístico.

### Negócio

- Explicar o encadeamento de PD, EAD, LGD, perda, preço e ROI.
- Projetar o resultado da carteira.
- Defender as decisões diante do conselho.

## Dependências citadas, mas não contidas neste PDF

Para executar o desafio, ainda são necessários:

1. Base A.
2. Base B.
3. Base C ou modelo/formato de decisão sobre suas propostas.
4. Dicionário de dados com a coluna “Disponível na concessão?”.
5. `autocred_parametros_ead_lgd.xlsx`.
6. Modelos de submissão.
7. Documento *AutoCred - Regras da Competição*.
8. Rubrica completa de avaliação.

Sem esses itens, o enunciado pode ser analisado, mas a solução não é reproduzível.

## Pontos de atenção e ambiguidades

1. **Numeração incorreta dos lembretes:** a seção “Três lembretes” apresenta os itens 3, 4 e 5, em vez de 1, 2 e 3.
2. **Base C não é descrita como arquivo entregue no lançamento:** o cronograma menciona Bases A e B e modelos de submissão, embora a política seja aplicada a 5.000 propostas da Base C. É necessário esclarecer se C será disponibilizada diretamente ou acessada apenas por um formato de submissão/simulador.
3. **Inferência de rejeitados sem método definido:** o problema é reconhecido, mas o enunciado não informa observações adicionais, amostra de exploração, estratégia de ponderação ou tratamento esperado.
4. **Funções do simulador são ocultas:** direção dos efeitos é fornecida, mas não sua intensidade. Isso transforma a política em decisão sob incerteza e limita a validação interna do ROI.
5. **EAD pode exigir revisão de dupla contagem:** deve-se confirmar se o saldo devedor no mês do default já incorpora o principal das parcelas vencidas antes de somá-las novamente.
6. **Fórmula de ROI é simplificada:** não considera cronologia completa dos fluxos, custo de funding, impostos, despesas operacionais, capital econômico, pré-pagamento ou recuperações distribuídas no tempo.
7. **CET máximo precisa de convenção matemática:** é necessário definir se a taxa de 3,5% ao mês é efetiva, nominal ou CET completo e como deve ser convertida para o cálculo dos contratos.
8. **AuROC não garante PD calibrada:** a política usa a PD numericamente na perda esperada; portanto, calibração deveria ser validada, mesmo que não seja a métrica oficial.
9. **Métrica de inadimplência precisa de denominador formal:** o texto usa contratos fechados, mas deve esclarecer se a contagem é por contrato, exposição, saldo ou safra e como lida com contratos não maturados.
10. **Comparação de LGD externa sem fonte:** a faixa de 45% a 55% atribuída a bancos estabelecidos é contextual, mas não possui referência no documento.
11. **Critério dos cinco pontos de bônus não aparece aqui:** ele foi anunciado nos slides, mas não é explicado no enunciado; pode estar no documento de regras citado.
12. **Entrega em duas semanas versus datas:** o período entre 12/09 e 25/09 corresponde a 13 dias completos até 23h59, coerente como aproximação, mas o prazo oficial deve prevalecer sobre a expressão informal.

## Diferenças em relação aos slides do Desafio AutoCred

| Tema | Slides | Enunciado |
|---|---|---|
| Contexto | indicadores resumidos | canais de originação, histórico da política e comparação de LGD |
| Métricas | AuROC e ROI | adiciona KS como métrica secundária |
| Base A | volume e período | confirma janela de performance de 12 meses fechada |
| Base B | 3.000 contratos de 2025 | restringe o período a janeiro-junho de 2025 |
| Base C | 5.000 propostas | informa segundo semestre de 2025 e detalha comportamento dinâmico |
| EAD/LGD | fornecidos | identifica arquivo, tabelas, Tabela Price, avalista e workout |
| ROI | fórmula resumida | esclarece juros até o default e exclusão de ofertas não aceitas |
| Política | quatro alavancas | explicita custos do exagero e regra do score 1-10 |
| Simulação | efeitos gerais | acrescenta intensidade oculta, submissão única e determinismo |
| Execução | avaliação resumida | define papéis, cronograma e documentos auxiliares |

O enunciado é mais autoritativo para execução porque contém detalhes ausentes nos slides. Os slides são melhores como visão executiva; este documento deve orientar implementação e submissão.

## Relação com a trilha completa

| Documento | Papel |
|---|---|
| Mentoria 1 | fundamentos econômicos, riscos, ROE, PD, EAD e LGD |
| Mentoria 2 | split, vazamento, métricas, ROC/AUC e deploy |
| Mentoria 3 - Slides | visão executiva do Desafio AutoCred |
| Enunciado AutoCred | especificação operacional do desafio |

A sequência consolidada é:

`Economia do crédito → Dados históricos → Validação temporal → Modelo de PD → Calibração → Score → EAD/LGD → Perda esperada → Política → Simulação de aceite e risco → Guardrails → ROI → Defesa`

## Síntese crítica

O enunciado acerta ao impedir que o desafio seja reduzido a uma competição de AuROC. Ele exige que previsão, precificação, risco, volume e comportamento do cliente sejam tratados como partes de uma única decisão.

O maior risco técnico é treinar a PD em contratos aprovados pela política antiga e aplicá-la a propostas de mar aberto. O maior risco econômico é maximizar o ROI simplificado criando uma carteira pequena ou frágil. Os guardrails corrigem parcialmente o segundo problema; o primeiro depende de diagnóstico, prudência nas regiões sem suporte histórico e defesa explícita das limitações.

Uma solução forte precisa demonstrar não apenas “qual modelo ganhou”, mas por que as faixas são estáveis, por que a PD é utilizável como probabilidade, como cada alavanca altera risco e aceitação e por que a carteira permanece viável em cenários menos favoráveis.
