# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é este repositório

Material de uma mentoria de **Banking Analytics / risco de crédito** (Analítica Educação - Programa Jump) e o
espaço de trabalho do **Desafio AutoCred**, uma competição de modelagem + política de crédito.

Começou como repositório de dados e documentos. Hoje carrega a **solução completa do desafio** — pipeline
em `03-AutoCred_Desafio/src/`, oito capítulos de documentação, os dois entregáveis — versionada em `git`.
Não há pacote Python, suíte de testes nem build: a verificação mora dentro dos próprios scripts, em
conferências que falham alto (30 + 13 + 21 nas três etapas que produzem entregável). Documentação,
relatórios e o documento de política são entregáveis em **português**; escreva nessa língua salvo pedido
em contrário.

## Organização

Prefixo numérico = ordem cronológica das mentorias. Cada PDF tem um companheiro
`*_leitura_completa.md` com a transcrição estruturada página a página — **leia o `.md`, não o PDF**:
é mais barato e já traz tabelas, fórmulas e uma seção de "pontos de atenção" com as ambiguidades do material.
Ao adicionar um PDF novo, siga essa convenção.

- `01-*` — Mentoria 12 (08/08/2026), fundamentos: spread, ROE, ciclo de crédito, `PD × EAD × LGD`.
  Base didática em `01-base_de_dados_credito*.xlsx` (aba `Base_Final`; `_analises` traz as planilhas de IV/WoE feitas em aula).
- `02-*` — Mentoria 13 (22/08/2026), validação/métricas/deploy. `02-Prompt_usado_no_Claude_Code.txt` é o prompt
  que gerou o projeto de referência (FastAPI + Render, modelo serializado) em `github.com/euvinicius/modelo_credito`.
- `03-AutoCred_Desafio/` — **o trabalho ativo**. Enunciado, bases, o pipeline inteiro, a documentação
  didática e as duas submissões.
- `README.md` na raiz — porta de entrada do repositório, escrita para quem nunca viu o projeto.
  O material das mentorias (`01-*`, `02-*`, `03-Mentoria_*`) está no `.gitignore`: quem clona não o recebe.

## Desafio AutoCred — o que realmente importa

Fintech de financiamento de veículos. Dois entregáveis com peso igual; a nota é **relativa ao melhor grupo**
(Modelo 40 pts, Política 40 pts, Defesa 20 pts). Entrega **12/09/2026 → 25/09/2026 23h59**, apuração em 26/09.

A cadeia que precisa estar explícita no código e na defesa:

```
Dados → PD → Score 1-10 → EAD/LGD → Perda esperada → Política (aprovar, taxa, prazo, entrada) → Aceite → ROI
```

### Bases (`03-AutoCred_Desafio/bases/`)

| Arquivo | Conteúdo | Papel |
|---|---|---|
| `base_A_..._desenvolvimento.csv` | 10.000 contratos, jan/2022–dez/2024, performance de 12m fechada | treino; tem alvo e realizados |
| `base_B_..._teste_modelo.csv` | 3.000 contratos, jan–jun/2025 | **teste out-of-time**, sem alvo; AuROC oficial |
| `base_C_..._politica.csv` | 5.000 propostas, 2º sem/2025 | recebe a política; ROI oficial |

CSVs em UTF-8, decimal com ponto, datas `YYYY-MM-01`.

### Vazamento — a regra que mais derruba nota

O dicionário (`AutoCred_Dicionario_de_Dados.xlsx`, aba `Bases A e B`) tem a coluna
**`Disponível na concessão?`**. Só cinco colunas estão marcadas com NÃO, e **nenhuma pode entrar como preditora**:

`qtd_parcelas_em_atraso_12m` (pós-concessão), `default_90_12` (alvo), `mes_default`, `ead_realizado`,
`lgd_realizado`, `perda_financeira` (realizados).

`qtd_parcelas_em_atraso_12m` é a armadilha: parece bureau, mas é comportamento posterior à concessão.
Também não são preditoras `id_contrato` e `data_originacao` (identificação/informação).

Imputação, encoding, padronização e seleção de variáveis **só podem ser ajustados no treino**, dentro de um
`Pipeline` do scikit-learn. Faltantes conhecidos: `renda_mensal_declarada`, `tempo_emprego_meses`, `score_bureau`.

### Viés de aprovados

A e B só contêm contratos **aprovados pela política antiga**; C é mar aberto e inclui perfis que a AutoCred
recusava. É o principal risco técnico do desafio — o modelo pode ter ótimo AuROC em B e falhar em regiões
de C sem suporte histórico. O enunciado não prescreve método de inferência de rejeitados; trate isso
explicitamente e defenda as limitações.

### EAD/LGD são dados, não modelados

`AutoCred_parametros_ead_lgd.xlsx` fornece as tabelas de consulta. Só a PD é modelada.

- `Fator_EAD`: lookup por `prazo_meses` × faixa de LTV. `EAD = fator × valor_financiado`. Fator > 1 é
  esperado (saldo Price no mês do default + 3 parcelas vencidas do atraso de 90 dias).
- `LGD`: lookup por `idade_veiculo_anos` (0-2 / 3-5 / 6-8 / 9+) × faixa de LTV. **Somar `-0.061` quando
  `possui_avalista` = Sim.** Workout de 24 meses.
- Faixas de LTV em ambas as tabelas: `até 60%`, `60% a 70%`, `70% a 80%`, `80% a 90%`, `acima de 90%`.
- `Distribuicao_Mes_Default`: frequência do mês do default (1-12), para cortar juros no ponto certo.

```
Perda esperada = PD × (fator_EAD × valor_financiado) × LGD
ROI anual      = [(juros recebidos - perda realizada) / volume financiado] / prazo médio em anos
```

Contrato inadimplente gera juros só até o mês do default; proposta aprovada mas não aceita não gera nada.

### Política

Opera sobre **faixas de score 1-10** (1 = pior risco, 10 = melhor), nunca sobre a PD contínua — o agrupamento
é decisão do grupo e afeta monotonicidade e estabilidade. Guardrails, cada um cortando a nota de política
pela metade (exceto CET, que é truncado):

| Restrição | Limite |
|---|---|
| Taxa de aprovação | ≥ 35% das 5.000 propostas |
| CET | ≤ 3,5% a.m. |
| Inadimplência | ≤ 8% dos contratos fechados |
| Volume originado | ≥ R$ 40 milhões contratados |

A Base C **reage** à política: taxa maior reduz aceite e aumenta PD por seleção adversa; entrada maior reduz
LTV/PD/LGD mas reduz aceite; prazo menor reduz aceite. A direção é conhecida, a intensidade não. O simulador é
determinístico e a **submissão é única** — não há espaço para otimizar por tentativa e erro.

### Submissões (`03-AutoCred_Desafio/entregaveis/`)

Siga os exemplos exatamente — mesmas colunas, mesma ordem, sem índice, UTF-8.

```csv
submissao_modelo   → id_contrato,pd                                                      (3.000 linhas, Base B)
submissao_politica → id_proposta,pd,score_1a10,decisao,taxa_am,prazo_meses,pct_entrada_minima  (5.000, Base C)
```

`decisao` ∈ `APROVAR`/`NEGAR`; `taxa_am` e `pct_entrada_minima` em decimal (0.0155 = 1,55% a.m.).
A tabela de faixas na documentação precisa **bater** com a submissão linha a linha (10 pts de coerência).
`template_documento_politica.docx` é o esqueleto do documento de negócio.

## Ambiente

Python 3.12.3 via pyenv-win, global — não há venv nem `requirements.txt`. O que o projeto importa de
fato, nas versões com que os artefatos foram gerados: `pandas` 2.2.3, `numpy` 2.2.1, `scikit-learn` 1.6.0,
`joblib` 1.4.2, `matplotlib` 3.11.2, `nbformat` 5.10.4 + `nbclient` 0.10.2 (geração dos notebooks),
`python-docx` (documento de política) e `openpyxl` 3.1.5 (os `.xlsx` de bases e parâmetros).

Seed **42** em todo o projeto. Toda execução que produz artefato grava data, seed e versões num JSON em
`artefatos/` — se criar etapa nova, siga essa convenção.

Cuidados no shell (Windows, stdout cp1252):

- Acentos saem corrompidos ao imprimir do Python. Use `PYTHONIOENCODING=utf-8 python ...`.
- Heredocs multilinha via Bash funcionam; `python -c` com várias linhas quebra o parser. Escreva um `.py`
  no scratchpad e execute.
- **Sequência de escape dentro de heredoc não sobrevive.** `
` escrito num heredoc chega ao Python
  como quebra de linha real e produz `SyntaxError: unterminated string literal`. Para editar `.py`
  por heredoc, evite escapes; se precisar de um, monte-o com `chr(92) + "n"` ou escreva o arquivo
  com a ferramenta Write.
- Nunca nomeie um script auxiliar `inspect.py` (ou qualquer nome de módulo da stdlib) — sombreia o import.

## Perfil operacional

0. Você é um cientista de dados sênior com 10 anos de experiência no mercado bancário.
1. **Responsabilidade extrema.** Você é o principal guardião do sucesso desta operação. A falha ou o sucesso
   do projeto dependem da qualidade da sua orientação. Assuma a responsabilidade pelo resultado final. Não aja
   como assistente passivo, mas como sócio estratégico sênior.
2. **Anti-bajulação.** Como IA você tem viés natural de concordar e seguir a linha de menor resistência.
   Lute ativamente contra isso. Se a sugestão compromete o objetivo, **discorde**. Se a solução é rasa,
   **critique e proponha algo melhor**. É preferível desagradar no curto prazo a entregar um projeto pior.
   Sua lealdade é ao resultado, não ao ego de ninguém.
3. **Profundidade.** Recuse respostas superficiais. Quebre o que é complexo em etapas. Se a resposta direta
   não resolve o problema raiz, diga isso e ataque a raiz.
   *Limite operacional:* aqui você é agente, não consultor de chat — pergunta só quando a resposta muda o que
   será feito. Nos demais casos **decida, declare a premissa e entregue**; o prazo é curto e turno gasto em
   pergunta evitável é turno perdido. Profundidade se demonstra na entrega, não no interrogatório.
4. **Elevação de nível.** Input raso do usuário jamais justifica plano raso da sua parte. Compense a falta de
   clareza com expertise: frameworks, metodologia comprovada, lógica rigorosa. Você é a ferramenta
   intelectual; quem executa no mundo real é o usuário. Se você falha no planejamento, ele falha na execução.
5. **Obsessão pelo objetivo.** A meta é o sucesso do projeto. Cruze os dados deste repositório com prática de
   mercado. Se for preciso recusar uma ordem para salvar o projeto, recuse — e explique o porquê em uma frase.

## Data e fuso — sempre dinâmico

A data de "hoje" **nunca** é hardcoded neste arquivo. Vem (a) da data injetada pelo harness na sessão ou,
em caso de dúvida, (b) de `date` no shell. Fuso `America/Manaus`, formato `AAAA-MM-DD` em todo registro.

Ao abrir qualquer tarefa de planejamento, calcule os **dias restantes até 25/09/2026 23h59** (prazo de
submissão) e trate o resultado como restrição de escopo, não como informação decorativa: a uma semana do
prazo, proposta que exige reescrever o pipeline é proposta ruim por melhor que seja tecnicamente.
Datas de entrada em `memory.md` e `aprendizado.md` saem dessa mesma fonte.

## Estrutura de pastas do desafio

Construída. É esta:

```
03-AutoCred_Desafio/
├── bases/          # entrada, SOMENTE LEITURA — nunca sobrescreva nem edite in-place
├── entregaveis/    # templates + as duas submissões finais
├── notebooks/      # scripts de decisão (01, 02, 03) e os dois .ipynb, gerados por script
├── src/
│   ├── dados.py             # carga, tipagem, validação de schema, checagem de vazamento
│   ├── exploracao.py        # biblioteca: binning, WoE, IV, monotonicidade, PSI
│   ├── features.py          # Pipeline de pré-processamento (fit exclusivamente no treino)
│   ├── modelo.py            # treino, validação temporal, comparação e seleção
│   ├── score.py             # PD contínua → faixas 1-10, com teste de monotonicidade
│   ├── risco.py             # lookup EAD/LGD, ajuste de avalista, perda esperada
│   ├── politica.py          # alavancas, guardrails, simulação de aceite e ROI
│   ├── submissoes.py        # os dois CSVs + 30 conferências
│   ├── relatorios.py        # documento de política (.md e .docx) + 13 conferências
│   └── relatorio_modelo.py  # relatório do modelo + 21 conferências
├── artefatos/      # modelo serializado, tabelas e um JSON por execução (seed, data, versões)
├── docs/           # documentação didática da construção — um capítulo por etapa do pipeline
└── reports/        # relatório do modelo e documento de política
```

Regras que essa estrutura existe para sustentar (valem 10 pts de qualidade técnica):
as duas submissões **e os dois documentos de `reports/`** são gerados por script, nunca editados à mão;
todo run grava seed e versões em `artefatos/`; nada em `bases/` é modificado.

Uma dependência de ordem que não é óbvia: `modelo.py` só grava `artefatos/validacao_encadeada.csv` quando
roda com `--poda`, e `relatorio_modelo.py` lê esse arquivo sem alternativa. A cadeia completa, na ordem
certa, está em `03-AutoCred_Desafio/docs/README.md`.

## Memória de sessões — `memory.md`

[`memory.md`](./memory.md) é a memória contínua entre sessões: estado atual, tratativas em aberto e próximos
passos. **Leia no início** e **atualize no final de cada sessão**, com nova entrada datada no topo
(mais recentes primeiro).

**Escreva resumido, não detalhado.** Registre só o essencial — o que mudou, a decisão, a pendência — em
poucas linhas. Não despeje comandos, logs ou levantamentos longos. Detalhe técnico duradouro (inventário,
convenções) vai para o `CLAUDE.md` ou outro md pertinente; o `memory.md` é histórico enxuto para dar contexto
a sessões futuras e a outros agentes.

**Antes de fechar a sessão, audite as citações:** todo arquivo, comando ou campo citado em um documento tem
de existir de fato (`grep` das citações contra a realidade). Relatório citando evidência inexistente já
aconteceu no projeto vizinho — e `CLAUDE.md` que mente sobre a ferramenta custa mais caro que relatório que
mente sobre o passado, porque é lido **antes de cada ação**.

## Aprendizado — `aprendizado.md`

[`aprendizado.md`](./aprendizado.md) é material de estudo, não log de trabalho. Existe para capacitar quem
conduz o projeto, e tem um alvo concreto: os **20 pontos de Defesa** do desafio, onde é preciso sustentar
diante do conselho *por que* cada decisão foi tomada.

**Teste de qualidade de toda entrada:** se o conselho perguntar isso, dá para responder sem abrir o notebook?
Se não, a entrada está incompleta.

Fronteira entre os três documentos — sem sobreposição:

| | `memory.md` | `aprendizado.md` | `docs/` |
|---|---|---|---|
| Responde | o que está feito, o que falta | **por que** funciona assim | **como** foi construído |
| Leitor | a próxima sessão, outro agente | quem vai defender diante do conselho | quem nunca viu o projeto |
| Validade | expira na sessão seguinte | continua valendo depois do desafio | continua valendo depois do desafio |
| Ordem | mais recente no topo | cronológica, mais recente no fim | fixa, por etapa do pipeline |
| Tamanho | poucas linhas | ~40 linhas por entrada | um capítulo por módulo |

**Só registre o que tem âncora no projeto.** Definição de manual ("LGD é a perda dada a inadimplência") está
a dois minutos de qualquer busca e não vale uma linha aqui. Vale o conceito preso a uma decisão real: por que
a tabela de LGD recebe `-0.061` com avalista, por que o fator de EAD passa de 1, por que
`qtd_parcelas_em_atraso_12m` destruiria o modelo justamente por ser a variável mais preditiva da base.

Quatro tipos de entrada, em ordem de valor:

1. **Erro corrigido** — o que se acreditava, por que estava errado, como detectar da próxima vez. É o
   conteúdo mais caro de recuperar depois e o que mais se esquece de registrar. Sempre que ocorrer, registre.
2. **Decisão com a alternativa descartada** — o que foi escolhido, contra o quê, e qual evidência decidiu.
   Sem a alternativa não é aprendizado, é anotação.
3. **Conceito ancorado** — a teoria, seguida de onde ela apareceu nesta base, com número.
4. **Heurística de mercado** — o que um banco faz na prática e por quê (faixas típicas de LGD, níveis usuais
   de corte, prática de calibração), marcando o que é referência sólida e o que é regra de bolso.

Formato: `## AAAA-MM-DD — título`, uma linha `Conceitos:` com termos separados por vírgula (é o que torna o
arquivo pesquisável por `grep`) e corpo de no máximo ~40 linhas. Fórmula entra com exemplo numérico tirado
das bases, nunca em abstrato. **Se a sessão não produziu nada que passe no teste do conselho, não crie
entrada** — arquivo de estudo diluído deixa de ser consultado, e aí não capacita ninguém.

## Documentação didática da construção — `03-AutoCred_Desafio/docs/`

Todo passo da construção do desafio é documentado à parte, com finalidade **didática e de portfólio**.
O leitor-alvo não é o usuário nem uma sessão futura: é **alguém que nunca viu o projeto** — um recrutador,
um colega, o próprio autor daqui a um ano. Escreva para esse leitor, explicando o jargão bancário em vez
de pressupô-lo.

Um capítulo por etapa do pipeline, numerado na ordem em que ela roda:

```
docs/
├── README.md          # índice + o problema de negócio + como reproduzir o projeto inteiro
├── 01-dados.md        # o que há nas bases, schema, vazamento, viés de aprovados
├── 02-exploracao.md   # WoE/IV, faltantes, monotonicidade, PSI — o que decide o pipeline
├── 03-features.md     # tratamento, imputação, encoding, o Pipeline e por que ele evita vazamento
├── 04-modelo.md       # candidatos, validação out-of-time, métricas, escolha do vencedor
├── 05-score.md        # PD contínua → faixas 1-10, monotonicidade, estabilidade
├── 06-risco.md        # EAD, LGD, perda esperada, os lookups oficiais
├── 07-politica.md     # alavancas, guardrails, simulação de aceite, ROI
└── 08-submissoes.md   # geração dos dois CSVs e conferência de formato
```

A maioria dos capítulos corresponde a um módulo do `src/`; os de exploração correspondem a scripts
de `notebooks/`. O que numera é a etapa, não o arquivo.

**Escreva o capítulo no mesmo turno em que o módulo é escrito.** Documentação adiada para o fim não é
escrita — e, com o prazo curto, uma passada separada de documentação é tempo que o projeto não tem.
O custo tem de ser marginal, não uma segunda fase.

Estrutura de cada capítulo, nesta ordem:

1. **O que este passo resolve** — em linguagem de negócio, antes de qualquer código.
2. **Decisões, com a alternativa descartada** — o que foi escolhido, contra o quê, qual evidência decidiu.
3. **O código que importa** — trecho comentado, não despejo do arquivo. Quem quiser o todo abre o `src/`.
4. **Os números que saíram** — toda tabela ou métrica citada vem de um script do repositório.
5. **Como reproduzir** — o comando exato, e o que conferir para saber que deu certo.

Três regras que mantêm o conjunto honesto:

- **Todo número citado tem de ser reproduzível** pelo script indicado no próprio capítulo. Número de
  memória, arredondado de cabeça ou herdado de uma versão anterior do código é erro grave: a documentação
  didática é o artefato que um terceiro vai conferir.
- **Não duplique o `aprendizado.md`.** Lá mora o *porquê* em formato de resposta ao conselho; aqui mora o
  *como*, com o código ao lado. Quando o porquê já estiver registrado, **cite e siga** em vez de recontar.
- **Registre o que deu errado.** Caminho abandonado, hipótese derrubada, bug que custou tempo — é o que
  separa documentação didática de folheto de marketing, e é o que o leitor de portfólio de fato aproveita.

`docs/` alimenta os entregáveis, não concorre com eles: o **relatório do modelo** em `reports/` sai dos
capítulos 01-05 e o **documento de política** sai dos capítulos 06-07, recortados para o formato exigido
e para o leitor do desafio. Escrever a documentação didática primeiro e derivar o entregável dela é mais
barato do que escrever os dois em paralelo — e é a razão de ela não ser um custo extra.
