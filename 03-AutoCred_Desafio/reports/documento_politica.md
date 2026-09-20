# Política de Crédito — AutoCred

Grupo ___ · Desafio de Risco de Crédito · setembro de 2026

> Gerado por `src/relatorios.py`. Nenhum número deste documento foi digitado: todos vêm
> de `artefatos/` ou são recalculados a partir de lá. O `.docx` entregue ao conselho é
> este mesmo conteúdo no template oficial do desafio.

## 1. Resumo executivo

Propomos aprovar as faixas de score 5 a 10 — 2.642 das 5.000 propostas, 52,8% — com taxa de 2,27% a 2,82% ao mês, o prazo que o cliente pediu e entrada mínima de 21% nas faixas 5 e 6. A carteira projetada origina R$ 67,4 mi, com inadimplência de 5,93% e ROI anualizado de 15,7%.

Ela não foi escolhida por maximizar esse ROI, e sim por sobreviver ao cenário com que decidimos — aceite pessimista e PD 20% acima da prevista ao mesmo tempo —, onde ainda cumpre os quatro guardrails: R$ 42,8 mi, 7,67% de inadimplência e ROI de 14,8%. A regra de maior ROI da nossa busca projeta 21,6% e quebra guardrail nesse teste.

## 2. O modelo de probabilidade de default

| Item | O que fizemos |
|---|---|
| Modelo escolhido | Gradient boosting em árvores (HistGradientBoosting) com regularização forte: 4 folhas por árvore, aprendizado 0,03, mínimo de 50 casos por folha, L2 = 1,0. Calibração: sigmoid (Platt) cv=5. Seed 42. |
| Variáveis utilizadas | 17: doze do proponente e do bem (idade, ocupação, renda, tempo de emprego, residência, score de bureau, restrições, consultas, avalista, canal, idade do veículo, valor do bem), quatro da operação (valor financiado, entrada, LTV, prazo) e o comprometimento de renda (parcela ÷ renda), que sozinho vale +0,013 de AuROC out-of-time. Outras sete derivadas foram testadas; nenhuma entrou. |
| Variáveis descartadas, e por quê | As seis marcadas como indisponíveis na concessão pelo dicionário são vazamento: descrevem o que aconteceu depois de conceder. id_contrato e data_originacao são identificação. ano_modelo saiu por PSI de 1,39 entre A e C — artefato de calendário, com 31,8% da Base C fora do domínio do treino; remover não muda o AuROC. taxa_juros_am e parcela_mensal são decisão nossa na Base C, não informação do cliente. |
| Tratamento de valores ausentes | Nenhuma imputação. Ausentes estáveis nas três bases: tempo de emprego 11,7%, renda 7,6%, score de bureau 3,4%. O modelo aprende em cada corte para que lado mandar o ausente, e faltar renda já é informação. Imputar pela mediana custou 0,0012 de AuROC. Todo o pré-processamento vive num Pipeline ajustado só no treino. |
| Estratégia de validação | Separação temporal, nunca aleatória: treino em 2022-2023 (6.670 contratos), teste out-of-time em 2024 (3.330). Cinco candidatos sob o mesmo corte. A validação cruzada de 5 folds roda dentro do treino; o out-of-time não participa de escolha nenhuma. |
| AuROC em treino / validação / teste out-of-time | 0,812 / 0,725 ± 0,020 / 0,741 |
| KS no teste out-of-time | 0,376 |

*Out-of-time* é o teste no futuro: o modelo aprende em 2022-2023 e é medido em 2024, uma safra que não existia quando ele foi treinado — é o que acontece em produção, e é o que uma amostra aleatória esconderia ao misturar 2024 no treino. A Random Forest empatou nesse teste (0,735), mas marcava 0,921 no treino — queda de 0,186 contra 0,071 do escolhido. Escolhemos o de menor queda, não o de maior AuROC: a distância entre treino e out-of-time é a única medida de quanto da performance é real. O mesmo algoritmo sem regularização faz 0,998 no treino e 0,710 fora dele.

## 3. Construção do score de 1 a 10

Por cortes fixos de PD, congelados no código e calculados uma única vez sobre a PD out-of-fold da Base A. Não por quantis recalculados na aplicação: quantil reaplicado à Base C poria 20% das propostas na faixa 10 por construção, mesmo que a carteira inteira fosse pior. A faixa deixaria de significar risco e passaria a significar posição na fila — e a tabela, que promete uma taxa por faixa, viraria promessa sobre a fila.

Os percentis são desiguais de propósito (20, 36, 50, 62, 72, 80, 87, 93 e 97): a decisão acontece na cauda ruim, e abrir faixas no meio da distribuição não muda decisão nenhuma. As faixas 1 a 4 são 20% da base de desenvolvimento e 47,2% das propostas da Base C — a diferença entre carteira aprovada e mar aberto, já visível no score. Discretizar custa 0,0029 de AuROC (0,7326 na PD contínua contra 0,7297 na faixa), com 0 inversões materiais e 7 pares de faixas vizinhas cujos intervalos de confiança se tocam.

## 4. A tabela de política

A faixa de PD é a **regra** que atribui o score, não uma descrição do que saiu: aplicá-la à coluna pd de submissao_politica.csv reproduz score_1a10 linha a linha. O intervalo é fechado embaixo — PD igual a um corte cai na faixa pior.

| Score | Faixa de PD | Decisão | Taxa a.m. | Prazo máx. | Entrada mín. | Perda esperada | ROI esperado |
|---|---|---|---|---|---|---|---|
| 10 | < 3,69% | APROVAR | 2,27% | o pedido | a do cliente | 2,1% | 15,1% |
| 9 | 3,69%–4,48% | APROVAR | 2,36% | o pedido | a do cliente | 2,8% | 15,4% |
| 8 | 4,48%–5,42% | APROVAR | 2,47% | o pedido | a do cliente | 3,5% | 15,8% |
| 7 | 5,42%–6,63% | APROVAR | 2,56% | o pedido | a do cliente | 4,4% | 16,0% |
| 6 | 6,63%–8,39% | APROVAR | 2,65% | o pedido | 21% | 5,4% | 16,3% |
| 5 | 8,39%–10,67% | APROVAR | 2,82% | o pedido | 21% | 6,9% | 16,7% |
| 4 | 10,67%–14,28% | NEGAR | — | — | — | 9,1% | — |
| 3 | 14,28%–20,96% | NEGAR | — | — | — | 13,0% | — |
| 2 | 20,96%–30,17% | NEGAR | — | — | — | 18,5% | — |
| 1 | ≥ 30,17% | NEGAR | — | — | — | 32,7% | — |

Perda esperada = PD × EAD × LGD **nas condições que o cliente pediu**, em percentual do valor financiado: é a régua que compara faixa aprovada com faixa negada na mesma coluna. O ROI é o da faixa no cenário central e reproduz-se da própria linha. O prazo ofertado é o que o cliente pediu, até o teto de 60 meses.

## 5. Racional da precificação

A cobertura, ao longo de todo o contrato e em percentual do volume financiado: a faixa 10 recebe 55,8% de juros esperados contra 2,4% de perda; a faixa 5, 65,3% contra 7,6%. Toda faixa aprovada cobre a própria perda com folga larga — o que aperta não é a perda, é o prazo: o ROI divide essa margem pelo prazo médio de 41,8 meses, e é aí que 53,5% viram 15,1% ao ano.

Sobre o aceite, a parte mais frágil deste documento: modelamos a probabilidade de o cliente fechar por dois canais que ele de fato sente — o aumento da parcela e a entrada adicional em meses de renda —, em três cenários. O aceite médio projetado é 70,7% no central e 44,8% no pessimista. **Nenhuma das três bases contém uma única proposta recusada pelo cliente.** A direção vem do enunciado; a intensidade é construção nossa. Por isso decidimos no cenário pessimista.

| Alavanca | Decisão do grupo | Justificativa |
|---|---|---|
| Ponto de corte | Aprovar da faixa 5 para cima — PD até 10,67% | As faixas 1 e 2 não têm preço viável: mesmo no teto de CET a faixa 1 entrega 9,4% de ROI, porque o termo (1 − PD) corta 43% dos juros antes de qualquer taxa. As faixas 3 e 4 têm preço e ainda assim foram negadas: incluir a faixa 4 leva a inadimplência a 8,55% no cenário adverso. Subir o corte até a faixa 6 deixa o volume em R$ 39,7 mi, abaixo do piso. A faixa 5 é o único corte que sobrevive aos dois lados. |
| Taxa por faixa | De 2,27% a 2,82% ao mês, resolvida por bisseção para um alvo de ROI de 15% mais 4% de inclinação em direção às faixas piores | A taxa não foi escolhida, foi resolvida: buscamos a que entrega o alvo sobre o risco já reduzido pelas alavancas anteriores. Há realimentação — taxa maior desacelera a amortização, aumenta o saldo no mês do default e aumenta a perda —, por isso a conta é uma bisseção e não uma margem somada à perda. A inclinação faz quem é mais arriscado pagar o próprio custo e ainda um prêmio de entrada. |
| Prazo máximo | 60 meses, mas o prazo ofertado é sempre o pedido — nunca alongado | A fórmula de ROI premia prazo longo duas vezes: mais juros no numerador e diluição de uma perda única por um denominador maior. Como a PD é medida em 12 meses fixos, a fórmula cobra zero pelo risco de alongar. Alongar compraria ROI na planilha e risco na carteira: na Base A o default vai de 6,44% em 24 meses a 11,62% em 60. Encurtar segue disponível. |
| Entrada mínima | 21% nas faixas 5 e 6; nenhuma exigência adicional da faixa 7 para cima | 21% e não 20% porque a fronteira das tabelas de EAD e LGD é fechada por baixo: LTV de exatamente 0,80 cai na faixa pior. Exigir 21% garante LTV abaixo de 80% e derruba EAD e LGD nas duas faixas aprovadas em que a perda pesa. Da faixa 7 para cima custaria aceite sem comprar redução que se pagasse. A entrada mediana pedida nas faixas 5 e 6 é 18,6%: a exigência morde em mais da metade delas. |

## 6. Resultado projetado

| Indicador | Projeção do grupo | Guard-rail |
|---|---|---|
| Taxa de aprovação | 52,8% — 2.642 de 5.000 propostas | mínimo de 35% |
| Volume originado | R$ 67,4 mi no cenário central; R$ 42,8 mi no adverso | mínimo de R$ 40 milhões |
| Inadimplência da carteira | 5,93% no cenário central; 7,67% no adverso | máximo de 8% |
| Taxa média ao mês | 2,46% — máxima de 2,82%, na faixa 5 | teto de 3,5% |
| ROI anualizado | 15,7% no cenário central; 14,8% no adverso | meta acima de 15% |

Uma ressalva, dita com todas as letras: no cenário adverso o ROI fica em 14,8%, **abaixo dos 15%** pedidos pelo conselho. Aceitamos isso porque a distância entre 15,7% e 14,8% é menor que o erro do modelo de aceite que produziu os dois, e porque três dos quatro guardrails cortam a nota pela metade quando quebram. Preferimos a política que cumpre os quatro limites no pior caso à que projeta mais no caso bom.

## 7. Riscos e limitações

Quatro, em ordem de gravidade.

- **O nível da PD em mar aberto é o que pode derrubar esta política.** Se a PD real vier 40% acima da prevista, a inadimplência vai a 8,30% no cenário central e 8,95% no pessimista, e o guardrail de 8% quebra nos dois — só o otimista, com 7,72%, aguenta. A 20% acima ainda cabe, e foi para ×1,2 que dimensionamos a margem. Nenhum dado do projeto identifica o nível verdadeiro: a recomendação é recalibrar a PD na primeira safra fechada, antes de descer o corte.
- **Viés de aprovados.** As Bases A e B só contêm contratos que a política antiga aprovou; a Base C é mar aberto. O PSI da PD entre A e C é 0,473, deslocamento severo pelo critério usual de 0,25. Parte é composição real — a Base C traz perfis que a AutoCred recusava —, parte pode ser extrapolação do modelo, e essa parte não conseguimos separar. Não aplicamos inferência de rejeitados: sem uma proposta recusada rotulada, qualquer método seria suposição vestida de técnica.
- **O modelo de aceite é nosso.** Conhecemos a direção dos três efeitos — taxa maior, entrada maior e prazo menor reduzem o aceite — e não a intensidade. Os três cenários cobrem uma faixa ampla de propósito, e decidimos no pior deles.
- **Deriva de safra.** O default na Base A é 8,67% em 2022, 8,94% em 2023 e 7,18% em 2024. A queda de 2024 não tem explicação nos dados: melhora da política antiga ou mudança de mix. Se for mix, 2025 não herda a melhora. Validamos fora do tempo e perdemos 0,071 de AuROC na travessia — a melhor evidência que temos não cobre 2025.

## 8. Divisão do trabalho

| Papel | Integrante |
|---|---|
| Modelagem (PD) | ___ |
| Política e precificação | ___ |
| Negócio e defesa | ___ |

---

### Anexo — teste de estresse completo

*Nove combinações de cenário de aceite × nível de PD, recalculadas sobre a oferta*
*publicada em `artefatos/politica_base_c.csv`. Não cabe no `.docx` de 2 a 3 páginas;*
*existe para a defesa.*

| Cenário de aceite | PD | Volume | Inadimplência | ROI | Guardrails |
|---|---|---|---|---|---|
| otimista | ×1,0 | R$ 80,4 mi | 5,51% | 16,0% | todos ok |
| otimista | ×1,2 | R$ 80,4 mi | 6,62% | 15,6% | todos ok |
| otimista | ×1,4 | R$ 80,4 mi | 7,72% | 15,2% | todos ok |
| central | ×1,0 | R$ 67,4 mi | 5,93% | 15,7% | todos ok |
| central | ×1,2 | R$ 67,4 mi | 7,12% | 15,3% | todos ok |
| central | ×1,4 | R$ 67,4 mi | 8,30% | 14,9% | **quebra inadimplência** |
| pessimista | ×1,0 | R$ 42,8 mi | 6,40% | 15,3% | todos ok |
| pessimista | ×1,2 | R$ 42,8 mi | 7,67% | 14,8% | todos ok |
| pessimista | ×1,4 | R$ 42,8 mi | 8,95% | 14,4% | **quebra inadimplência** |

