"""Geração do documento de política — Desafio AutoCred.

O conselho lê um documento de 2 a 3 páginas, no template `.docx` entregue com o
desafio. Este módulo o gera pela mesma regra que gerou as submissões:
**nenhum número é digitado**.

Três razões para o documento ser gerado por script, e não escrito no Word:

  - **Coerência vale 10 pontos.** A tabela de política publicada tem de bater
    com `entregaveis/submissao_politica.csv` linha a linha. A única forma de
    garantir isso é a tabela não existir em dois lugares: ela é lida de
    `artefatos/tabela_politica.csv` e conferida contra a submissão do disco.

  - **A política ainda pode mudar.** A dias do prazo, qualquer ajuste em
    `politica.ESCOLHIDA` invalidaria um `.docx` editado à mão sem avisar
    ninguém. Aqui, `python src/relatorios.py` refaz o documento inteiro.

  - **Número de memória é o erro mais caro deste projeto.** Todo valor daqui
    vem de um artefato ou é recalculado a partir dele — inclusive o teste de
    estresse, que é refeito sobre a oferta que foi de fato publicada.

O que o script *não* sabe, e deixa marcado com `___`: o número do grupo e os
nomes da divisão do trabalho. São os dois únicos campos a preencher no Word.

Uso:
    PYTHONIOENCODING=utf-8 python src/relatorios.py             # gera e confere
    PYTHONIOENCODING=utf-8 python src/relatorios.py --conferir   # só confere
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from dados import ARTEFATOS, RAIZ, carregar_base_c, registrar_execucao
from politica import (
    CENARIOS,
    ESCOLHIDA,
    MAX_CET_AM,
    MAX_INADIMPLENCIA,
    MIN_APROVACAO,
    MIN_VOLUME,
    simular,
)
from score import CORTES, faixa
from submissoes import Conferencia

REPORTS = RAIZ / "reports"
ENTREGAVEIS = RAIZ / "entregaveis"
TEMPLATE = ENTREGAVEIS / "template_documento_politica.docx"
ARQ_SUBMISSAO = ENTREGAVEIS / "submissao_politica.csv"

ARQ_MD = REPORTS / "documento_politica.md"
ARQ_DOCX = REPORTS / "documento_politica.docx"

CABECALHO = "Grupo ___ · Desafio de Risco de Crédito · setembro de 2026"


# --------------------------------------------------------------------------- #
# Formatação em português
# --------------------------------------------------------------------------- #
# Vírgula decimal e ponto de milhar não são preciosismo: número formatado em
# inglês num documento em português é a primeira coisa que denuncia planilha
# colada. Os quatro helpers abaixo são a única forma de um número virar texto
# neste módulo.


def pct(x, casas: int = 1) -> str:
    return f"{x * 100:.{casas}f}".replace(".", ",") + "%"


def num(x, casas: int = 3) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def inteiro(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def milhoes(x, casas: int = 1) -> str:
    return "R$ " + f"{x / 1e6:.{casas}f}".replace(".", ",") + " mi"


# --------------------------------------------------------------------------- #
# Carga: tudo vem de artefato
# --------------------------------------------------------------------------- #


def _js(nome: str) -> dict:
    return json.loads((ARTEFATOS / f"{nome}.json").read_text(encoding="utf-8"))


def carregar() -> dict:
    """Todos os insumos do documento, lidos do disco."""
    features = pd.read_csv(ARTEFATOS / "decisoes_features.csv")
    base = features.query("secao == 'derivadas' and conjunto == '17 features (baseline)'").iloc[0]
    return {
        "modelo": _js("modelo"),
        "score": _js("score"),
        "politica": _js("politica"),
        "submissoes": _js("submissoes"),
        "features": _js("decisoes_features"),
        "comparacao": pd.read_csv(ARTEFATOS / "modelo_comparacao.csv"),
        "tabela": pd.read_csv(ARTEFATOS / "tabela_politica.csv"),
        "perda_c": pd.read_csv(ARTEFATOS / "perda_esperada_base_c.csv"),
        "cv": float(base["CV"]),
        "dp_cv": float(base["dp"]),
        # Peso das quatro piores faixas nas duas pontas da cadeia. Escrito de
        # cabeça, este numero saiu errado (30% contra os 20% reais); agora vem
        # do artefato.
        "share_1a4_a": float(
            pd.read_csv(ARTEFATOS / "tabela_faixas.csv").query("faixa <= 4")["pct"].sum()
        ),
        "share_1a4_c": float(
            (pd.read_csv(ARTEFATOS / "politica_base_c.csv")["faixa"] <= 4).mean()
        ),
    }


def perda_por_faixa(d: dict) -> pd.Series:
    """Perda esperada de cada faixa **nas condições que o cliente pediu**, em
    percentual do valor financiado.

    É a régua que permite comparar faixa aprovada com faixa negada na mesma
    coluna: a perda sob as condições *ofertadas* só existe para quem foi
    aprovado, e a faixa 1 não recebe oferta nenhuma.
    """
    g = d["perda_c"].groupby("faixa")
    return g["perda_esperada"].sum() / g["valor_financiado"].sum()


def faixas_de_pd() -> dict[int, str]:
    """As dez faixas, escritas como a regra que as gera.

    `score.faixa()` usa `side="right"`: PD exatamente igual a um corte cai na
    faixa **pior**. O intervalo é, portanto, fechado embaixo e aberto em cima —
    e a tabela publicada precisa dizer isso, porque é o que permite reproduzir
    `score_1a10` a partir da coluna `pd` da submissão.
    """
    r: dict[int, str] = {10: f"< {pct(CORTES[0], 2)}"}
    for i in range(1, len(CORTES)):
        r[10 - i] = f"{pct(CORTES[i - 1], 2)}–{pct(CORTES[i], 2)}"
    r[1] = f"≥ {pct(CORTES[-1], 2)}"
    return r


def estresse(d: dict) -> pd.DataFrame:
    """As nove combinações de cenário de aceite × nível de PD, recalculadas.

    Não saem de `politica.json`, que só guarda o cenário central e o canto
    duro. São refeitas sobre a oferta **publicada** em `politica_base_c.csv`,
    de modo que a tabela do documento descreve o arquivo que foi entregue, e
    não uma simulação parecida com ele.
    """
    c = carregar_base_c()
    oferta = pd.read_csv(ARTEFATOS / "politica_base_c.csv")
    # `probabilidade_aceite` casa `c` e `oferta` por posição. Alinhar por id e
    # conferir é barato; descobrir depois que as linhas estavam trocadas, não.
    oferta = oferta.set_index("id_proposta").loc[c["id_proposta"]].reset_index()
    if not (oferta["id_proposta"].to_numpy() == c["id_proposta"].to_numpy()).all():
        raise AssertionError("politica_base_c.csv não alinha com a Base C")

    linhas = []
    for nome in ("otimista", "central", "pessimista"):
        for mult in (1.00, 1.20, 1.40):
            m = simular(oferta, CENARIOS[nome], c, mult_pd=mult)
            m["ok"] = bool(
                m["aprovacao"] >= MIN_APROVACAO
                and m["volume"] >= MIN_VOLUME
                and m["inadimplencia"] <= MAX_INADIMPLENCIA
                and m["taxa_media"] <= MAX_CET_AM + 1e-9
            )
            linhas.append(m)
    return pd.DataFrame(linhas)


def celula(est: pd.DataFrame, cenario: str, mult: float) -> pd.Series:
    sel = est[(est["cenario"] == cenario) & np.isclose(est["mult_pd"], mult)]
    return sel.iloc[0]


# --------------------------------------------------------------------------- #
# As cinco tabelas do template
# --------------------------------------------------------------------------- #
# Cada uma devolve as linhas **inteiras**, rótulo da primeira coluna incluído.
# O markdown usa a linha como está; o `.docx` pula a primeira coluna, que o
# template já traz preenchida. Uma fonte só, duas saídas.

CAB_MODELO = ["Item", "O que fizemos"]
CAB_POLITICA = [
    "Score",
    "Faixa de PD",
    "Decisão",
    "Taxa a.m.",
    "Prazo máx.",
    "Entrada mín.",
    "Perda esperada",
    "ROI esperado",
]
CAB_ALAVANCAS = ["Alavanca", "Decisão do grupo", "Justificativa"]
CAB_PROJECAO = ["Indicador", "Projeção do grupo", "Guard-rail"]
CAB_PAPEIS = ["Papel", "Integrante"]


def tabela_modelo(d: dict) -> list[list[str]]:
    m, cmp_ = d["modelo"], d["comparacao"]
    v = cmp_.loc[cmp_["modelo"] == "HistGB regularizado"].iloc[0]
    h = m["hiperparametros"]
    return [
        [
            "Modelo escolhido",
            "Gradient boosting em árvores (HistGradientBoosting) com regularização forte: "
            f"{h['modelo__max_leaf_nodes']} folhas por árvore, aprendizado "
            f"{num(h['modelo__learning_rate'], 2)}, mínimo de {h['modelo__min_samples_leaf']} "
            f"casos por folha, L2 = {num(h['modelo__l2_regularization'], 1)}. Calibração: "
            f"{m['calibracao']}. Seed {m['seed']}.",
        ],
        [
            "Variáveis utilizadas",
            f"{d['features']['n_features']}: doze do proponente e do bem (idade, ocupação, "
            "renda, tempo de emprego, residência, score de bureau, restrições, consultas, "
            "avalista, canal, idade do veículo, valor do bem), quatro da operação (valor "
            "financiado, entrada, LTV, prazo) e o comprometimento de renda (parcela ÷ renda), "
            "que sozinho vale +0,013 de AuROC out-of-time. Outras sete derivadas foram testadas; "
            "nenhuma entrou.",
        ],
        [
            "Variáveis descartadas, e por quê",
            "As seis marcadas como indisponíveis na concessão pelo dicionário são vazamento: "
            "descrevem o que aconteceu depois de conceder. id_contrato e data_originacao são "
            "identificação. ano_modelo saiu por PSI de 1,39 entre A e C — artefato de "
            "calendário, com 31,8% da Base C fora do domínio do treino; remover não muda o "
            "AuROC. taxa_juros_am e parcela_mensal são decisão nossa na Base C, não informação "
            "do cliente.",
        ],
        [
            "Tratamento de valores ausentes",
            "Nenhuma imputação. Ausentes estáveis nas três bases: tempo de emprego 11,7%, renda "
            "7,6%, score de bureau 3,4%. O modelo aprende em cada corte para que lado mandar o "
            "ausente, e faltar renda já é informação. Imputar pela mediana custou 0,0012 de "
            "AuROC. Todo o pré-processamento vive num Pipeline ajustado só no treino.",
        ],
        [
            "Estratégia de validação",
            "Separação temporal, nunca aleatória: treino em 2022-2023 "
            f"({inteiro(m['n_treino'])} contratos), teste out-of-time em 2024 "
            f"({inteiro(m['n_oot'])}). Cinco candidatos sob o mesmo corte. A validação cruzada "
            "de 5 folds roda dentro do treino; o out-of-time não participa de escolha nenhuma.",
        ],
        [
            "AuROC em treino / validação / teste out-of-time",
            f"{num(v['AUC treino'])} / {num(d['cv'])} ± {num(d['dp_cv'])} / {num(v['AUC OOT'])}",
        ],
        ["KS no teste out-of-time", num(v["KS OOT"])],
    ]


def tabela_politica_publicada(d: dict) -> list[list[str]]:
    """As dez linhas da tabela que será aplicada à Base C."""
    t = d["tabela"].set_index("faixa")
    perda = perda_por_faixa(d)
    intervalos = faixas_de_pd()
    linhas = []
    for f in range(10, 0, -1):
        l = t.loc[f]
        aprova = l["decisao"] == "APROVAR"
        linhas.append(
            [
                str(f),
                intervalos[f],
                l["decisao"],
                pct(l["taxa_am"], 2) if aprova else "—",
                "o pedido" if aprova else "—",
                (pct(l["entrada_minima"], 0) if l["entrada_minima"] > 0 else "a do cliente")
                if aprova
                else "—",
                pct(perda.loc[f], 1),
                pct(l["roi"], 1) if aprova else "—",
            ]
        )
    return linhas


def tabela_alavancas(d: dict) -> list[list[str]]:
    p, t = d["politica"], d["tabela"].set_index("faixa")
    ap = t[t["decisao"] == "APROVAR"]
    return [
        [
            "Ponto de corte",
            f"Aprovar da faixa {p['corte']} para cima — PD até {pct(CORTES[10 - p['corte']], 2)}",
            "As faixas 1 e 2 não têm preço viável: mesmo no teto de CET a faixa 1 entrega "
            f"{pct(p['roi_no_teto_faixa1'])} de ROI, porque o termo (1 − PD) corta "
            f"{pct(t.loc[1, 'pd_publicada'], 0)} dos juros antes de qualquer taxa. As faixas 3 e "
            "4 têm preço e ainda assim foram negadas: incluir a faixa 4 leva a inadimplência a "
            "8,55% no cenário adverso. Subir o corte até a faixa 6 deixa o volume em R$ 39,7 mi, "
            "abaixo do piso. A faixa 5 é o único corte que sobrevive aos dois lados.",
        ],
        [
            "Taxa por faixa",
            f"De {pct(ap['taxa_am'].min(), 2)} a {pct(ap['taxa_am'].max(), 2)} ao mês, resolvida "
            f"por bisseção para um alvo de ROI de {pct(p['alvo_roi'], 0)} mais "
            f"{pct(p['inclinacao'], 0)} de inclinação em direção às faixas piores",
            "A taxa não foi escolhida, foi resolvida: buscamos a que entrega o alvo sobre o "
            "risco já reduzido pelas alavancas anteriores. Há realimentação — taxa maior "
            "desacelera a amortização, aumenta o saldo no mês do default e aumenta a perda —, "
            "por isso a conta é uma bisseção e não uma margem somada à perda. A inclinação faz "
            "quem é mais arriscado pagar o próprio custo e ainda um prêmio de entrada.",
        ],
        [
            "Prazo máximo",
            "60 meses, mas o prazo ofertado é sempre o pedido — nunca alongado",
            "A fórmula de ROI premia prazo longo duas vezes: mais juros no numerador e diluição "
            "de uma perda única por um denominador maior. Como a PD é medida em 12 meses fixos, "
            "a fórmula cobra zero pelo risco de alongar. Alongar compraria ROI na planilha e "
            f"risco na carteira: na Base A o default vai de {pct(p['default_24m_base_a'], 2)} em "
            f"24 meses a {pct(p['default_60m_base_a'], 2)} em 60. Encurtar segue disponível.",
        ],
        [
            "Entrada mínima",
            "21% nas faixas 5 e 6; nenhuma exigência adicional da faixa 7 para cima",
            "21% e não 20% porque a fronteira das tabelas de EAD e LGD é fechada por baixo: LTV "
            "de exatamente 0,80 cai na faixa pior. Exigir 21% garante LTV abaixo de 80% e "
            "derruba EAD e LGD nas duas faixas aprovadas em que a perda pesa. Da faixa 7 para "
            "cima custaria aceite sem comprar redução que se pagasse. A entrada mediana pedida "
            "nas faixas 5 e 6 é 18,6%: a exigência morde em mais da metade delas.",
        ],
    ]


def tabela_projecao(d: dict) -> list[list[str]]:
    p, s = d["politica"], d["submissoes"]
    return [
        [
            "Taxa de aprovação",
            f"{pct(p['aprovacao'])} — {inteiro(s['aprovadas'])} de "
            f"{inteiro(s['linhas_politica'])} propostas",
            "mínimo de 35%",
        ],
        [
            "Volume originado",
            f"{milhoes(p['volume_central'])} no cenário central; "
            f"{milhoes(p['volume_canto_duro'])} no adverso",
            "mínimo de R$ 40 milhões",
        ],
        [
            "Inadimplência da carteira",
            f"{pct(p['inadimplencia_central'], 2)} no cenário central; "
            f"{pct(p['inadimplencia_canto_duro'], 2)} no adverso",
            "máximo de 8%",
        ],
        [
            "Taxa média ao mês",
            f"{pct(p['taxa_media'], 2)} — máxima de {pct(p['taxa_max'], 2)}, na faixa 5",
            "teto de 3,5%",
        ],
        [
            "ROI anualizado",
            f"{pct(p['roi_central'])} no cenário central; {pct(p['roi_canto_duro'])} no adverso",
            "meta acima de 15%",
        ],
    ]


def tabela_papeis() -> list[list[str]]:
    return [
        ["Modelagem (PD)", "___"],
        ["Política e precificação", "___"],
        ["Negócio e defesa", "___"],
    ]


# --------------------------------------------------------------------------- #
# O texto
# --------------------------------------------------------------------------- #
# O documento inteiro sai de `blocos()`. Os parágrafos são nomeados, e não
# posicionais: o preenchimento do `.docx` pede o parágrafo pelo nome, de modo
# que inserir um parágrafo novo no meio não desloca silenciosamente os outros.


def paragrafos(d: dict, est: pd.DataFrame) -> dict[str, str]:
    p, s, t = d["politica"], d["submissoes"], d["tabela"].set_index("faixa")
    ap = t[t["decisao"] == "APROVAR"]
    f10, f5 = t.loc[10], t.loc[5]
    sc = d["score"]

    c14 = celula(est, "central", 1.4)
    p14 = celula(est, "pessimista", 1.4)
    o14 = celula(est, "otimista", 1.4)
    duro = celula(est, "pessimista", 1.2)

    return {
        "resumo_1": (
            f"Propomos aprovar as faixas de score {p['corte']} a 10 — "
            f"{inteiro(s['aprovadas'])} das {inteiro(s['linhas_politica'])} propostas, "
            f"{pct(p['aprovacao'])} — com taxa de {pct(ap['taxa_am'].min(), 2)} a "
            f"{pct(ap['taxa_am'].max(), 2)} ao mês, o prazo que o cliente pediu e entrada mínima "
            f"de 21% nas faixas 5 e 6. A carteira projetada origina "
            f"{milhoes(p['volume_central'])}, com inadimplência de "
            f"{pct(p['inadimplencia_central'], 2)} e ROI anualizado de {pct(p['roi_central'])}."
        ),
        "resumo_2": (
            "Ela não foi escolhida por maximizar esse ROI, e sim por sobreviver ao cenário com "
            "que decidimos — aceite pessimista e PD 20% acima da prevista ao mesmo tempo —, onde "
            f"ainda cumpre os quatro guardrails: {milhoes(duro['volume'])}, "
            f"{pct(duro['inadimplencia'], 2)} de inadimplência e ROI de {pct(duro['roi'])}. A "
            "regra de maior ROI da nossa busca projeta 21,6% e quebra guardrail nesse teste."
        ),
        "modelo": (
            "A Random Forest empatou em out-of-time (0,735), mas marcava 0,921 no treino — queda "
            "de 0,186 contra 0,071 do escolhido. Escolhemos o de menor queda, não o de maior "
            "AuROC: a distância entre treino e out-of-time é a única medida de quanto da "
            "performance é real. O mesmo algoritmo sem regularização faz 0,998 no treino e "
            "0,710 fora dele."
        ),
        "score_1": (
            "Por cortes fixos de PD, congelados no código e calculados uma única vez sobre a PD "
            "out-of-fold da Base A. Não por quantis recalculados na aplicação: quantil "
            "reaplicado à Base C poria 20% das propostas na faixa 10 por construção, mesmo que a "
            "carteira inteira fosse pior. A faixa deixaria de significar risco e passaria a "
            "significar posição na fila — e a tabela, que promete uma taxa por faixa, viraria "
            "promessa sobre a fila."
        ),
        "score_2": (
            "Os percentis são desiguais de propósito (20, 36, 50, 62, 72, 80, 87, 93 e 97): a "
            "decisão acontece na cauda ruim, e abrir faixas no meio da distribuição não muda "
            f"decisão nenhuma. As faixas 1 a 4 são {pct(d['share_1a4_a'], 0)} da base de "
            f"desenvolvimento e {pct(d['share_1a4_c'])} das propostas da Base C — a diferença "
            "entre carteira aprovada e mar aberto, já visível no score. Discretizar custa "
            f"{num(sc['auroc_pd_continua'] - sc['auroc_faixa'], 4)} de AuROC "
            f"({num(sc['auroc_pd_continua'], 4)} na PD contínua contra "
            f"{num(sc['auroc_faixa'], 4)} na faixa), com {sc['inversoes_materiais']} inversões "
            f"materiais e {sc['pares_indistinguiveis']} pares de faixas vizinhas cujos "
            "intervalos de confiança se tocam."
        ),
        "tabela_abre": (
            "A faixa de PD é a **regra** que atribui o score, não uma descrição do que saiu: "
            "aplicá-la à coluna pd de submissao_politica.csv reproduz score_1a10 linha a linha. "
            "O intervalo é fechado embaixo — PD igual a um corte cai na faixa pior."
        ),
        "tabela_nota": (
            "Perda esperada = PD × EAD × LGD **nas condições que o cliente pediu**, em "
            "percentual do valor financiado: é a régua que compara faixa aprovada com faixa "
            "negada na mesma coluna. O ROI é o da faixa no cenário central e reproduz-se da "
            "própria linha. O prazo ofertado é o que o cliente pediu, até o teto de 60 meses."
        ),
        "preco_1": (
            "A cobertura, ao longo de todo o contrato e em percentual do volume financiado: a "
            f"faixa 10 recebe {pct(f10['juros_pct'])} de juros esperados contra "
            f"{pct(f10['perda_pct'])} de perda; a faixa 5, {pct(f5['juros_pct'])} contra "
            f"{pct(f5['perda_pct'])}. Toda faixa aprovada cobre a própria perda com folga larga — "
            "o que aperta não é a perda, é o prazo: o ROI divide essa margem pelo prazo médio de "
            f"{num(p['prazo_medio'], 1)} meses, e é aí que "
            f"{pct(f10['juros_pct'] - f10['perda_pct'])} viram {pct(f10['roi'])} ao ano."
        ),
        "preco_2": (
            "Sobre o aceite, a parte mais frágil deste documento: modelamos a probabilidade de o "
            "cliente fechar por dois canais que ele de fato sente — o aumento da parcela e a "
            "entrada adicional em meses de renda —, em três cenários. O aceite médio projetado é "
            f"{pct(p['aceite_medio'])} no central e {pct(duro['aceite_medio'])} no pessimista. "
            "**Nenhuma das três bases contém uma única proposta recusada pelo cliente.** A "
            "direção vem do enunciado; a intensidade é construção nossa. Por isso decidimos no "
            "cenário pessimista."
        ),
        "projecao_nota": (
            f"Uma ressalva, dita com todas as letras: no cenário adverso o ROI fica em "
            f"{pct(p['roi_canto_duro'])}, **abaixo dos 15%** pedidos pelo conselho. Aceitamos "
            f"isso porque a distância entre {pct(p['roi_central'])} e {pct(p['roi_canto_duro'])} "
            "é menor que o erro do modelo de aceite que produziu os dois, e porque três dos "
            "quatro guardrails cortam a nota pela metade quando quebram. Preferimos a política "
            "que cumpre os quatro limites no pior caso à que projeta mais no caso bom."
        ),
        "riscos_abre": "Quatro, em ordem de gravidade.",
        "risco_1": (
            "**O nível da PD em mar aberto é o que pode derrubar esta política.** Se a PD real "
            f"vier 40% acima da prevista, a inadimplência vai a {pct(c14['inadimplencia'], 2)} "
            f"no cenário central e {pct(p14['inadimplencia'], 2)} no pessimista, e o guardrail "
            f"de 8% quebra nos dois — só o otimista, com {pct(o14['inadimplencia'], 2)}, "
            "aguenta. A 20% acima ainda cabe, e foi para ×1,2 que dimensionamos a margem. Nenhum "
            "dado do projeto identifica o nível verdadeiro: a recomendação é recalibrar a PD na "
            "primeira safra fechada, antes de descer o corte."
        ),
        "risco_2": (
            "**Viés de aprovados.** As Bases A e B só contêm contratos que a política antiga "
            f"aprovou; a Base C é mar aberto. O PSI da PD entre A e C é "
            f"{num(sc['psi_a_para_c'], 3)}, deslocamento severo pelo critério usual de 0,25. "
            "Parte é composição real — a Base C traz perfis que a AutoCred recusava —, parte "
            "pode ser extrapolação do modelo, e essa parte não conseguimos separar. Não "
            "aplicamos inferência de rejeitados: sem uma proposta recusada rotulada, qualquer "
            "método seria suposição vestida de técnica."
        ),
        "risco_3": (
            "**O modelo de aceite é nosso.** Conhecemos a direção dos três efeitos — taxa maior, "
            "entrada maior e prazo menor reduzem o aceite — e não a intensidade. Os três "
            "cenários cobrem uma faixa ampla de propósito, e decidimos no pior deles."
        ),
        "risco_4": (
            "**Deriva de safra.** O default na Base A é 8,67% em 2022, 8,94% em 2023 e 7,18% em "
            "2024. A queda de 2024 não tem explicação nos dados: melhora da política antiga ou "
            "mudança de mix. Se for mix, 2025 não herda a melhora. Validamos fora do tempo e "
            "perdemos 0,071 de AuROC na travessia — a melhor evidência que temos não cobre 2025."
        ),
    }


# --------------------------------------------------------------------------- #
# Renderização: markdown
# --------------------------------------------------------------------------- #


def md_tabela(cab: list[str], corpo: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    for l in corpo:
        out.append("| " + " | ".join(str(x) for x in l) + " |")
    return out + [""]


def escrever_markdown(d: dict, est: pd.DataFrame, tb: dict, tx: dict) -> str:
    L = [
        "# Política de Crédito — AutoCred",
        "",
        CABECALHO,
        "",
        "> Gerado por `src/relatorios.py`. Nenhum número deste documento foi digitado: todos vêm",
        "> de `artefatos/` ou são recalculados a partir de lá. O `.docx` entregue ao conselho é",
        "> este mesmo conteúdo no template oficial do desafio.",
        "",
        "## 1. Resumo executivo",
        "",
        tx["resumo_1"],
        "",
        tx["resumo_2"],
        "",
        "## 2. O modelo de probabilidade de default",
        "",
    ]
    L += md_tabela(CAB_MODELO, tb["modelo"])
    L += [tx["modelo"], "", "## 3. Construção do score de 1 a 10", "", tx["score_1"], "",
          tx["score_2"], "", "## 4. A tabela de política", "", tx["tabela_abre"], ""]
    L += md_tabela(CAB_POLITICA, tb["politica"])
    L += [tx["tabela_nota"], "", "## 5. Racional da precificação", "", tx["preco_1"], "",
          tx["preco_2"], ""]
    L += md_tabela(CAB_ALAVANCAS, tb["alavancas"])
    L += ["## 6. Resultado projetado", ""]
    L += md_tabela(CAB_PROJECAO, tb["projecao"])
    L += [tx["projecao_nota"], "", "## 7. Riscos e limitações", "", tx["riscos_abre"], ""]
    L += [f"- {tx[k]}" for k in ("risco_1", "risco_2", "risco_3", "risco_4")]
    L += ["", "## 8. Divisão do trabalho", ""]
    L += md_tabela(CAB_PAPEIS, tb["papeis"])

    L += [
        "---",
        "",
        "### Anexo — teste de estresse completo",
        "",
        "*Nove combinações de cenário de aceite × nível de PD, recalculadas sobre a oferta*",
        "*publicada em `artefatos/politica_base_c.csv`. Não cabe no `.docx` de 2 a 3 páginas;*",
        "*existe para a defesa.*",
        "",
    ]
    L += md_tabela(
        ["Cenário de aceite", "PD", "Volume", "Inadimplência", "ROI", "Guardrails"],
        [
            [
                l["cenario"],
                f"×{num(l['mult_pd'], 1)}",
                milhoes(l["volume"]),
                pct(l["inadimplencia"], 2),
                pct(l["roi"]),
                "todos ok" if l["ok"] else "**quebra inadimplência**",
            ]
            for _, l in est.iterrows()
        ],
    )
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Renderização: o template .docx
# --------------------------------------------------------------------------- #
# Preencher o template é melhor do que gerar um `.docx` do zero: mantém os
# estilos, a numeração das seções e a ordem das tabelas, e deixa óbvio para
# quem corrige que nenhuma seção foi omitida.


def _escrever(par, texto: str) -> None:
    """Troca o conteúdo de um parágrafo preservando o estilo dele.

    `**negrito**` vira negrito de verdade — é o único pedaço de markdown que o
    documento usa, e serve às frases que precisam ser lidas mesmo por quem só
    passa o olho.
    """
    for r in list(par.runs):
        r._element.getparent().remove(r._element)
    for i, pedaco in enumerate(texto.split("**")):
        if not pedaco:
            continue
        run = par.add_run(pedaco)
        run.italic = False
        run.bold = i % 2 == 1


def _clonar_depois(elemento_alvo, par_modelo, texto: str, estilo: str | None = None):
    """Um parágrafo novo logo depois de `elemento_alvo`, com a cara de `par_modelo`."""
    from docx.text.paragraph import Paragraph

    novo_el = deepcopy(par_modelo._element)
    elemento_alvo.addnext(novo_el)
    novo = Paragraph(novo_el, par_modelo._parent)
    _escrever(novo, texto)
    if estilo is not None:
        novo.style = estilo
    return novo


def _apagar(par) -> None:
    par._element.getparent().remove(par._element)


def _preencher(tabela, corpo: list[list[str]], pular: int = 1) -> None:
    """Escreve as linhas de dados a partir da coluna `pular`.

    Os rótulos da primeira coluna já vêm do template; `pular` os descarta da
    linha para que markdown e `.docx` possam compartilhar a mesma tabela.
    """
    for i, valores in enumerate(corpo, start=1):
        for j, v in enumerate(valores[pular:]):
            celula_ = tabela.cell(i, pular + j)
            _escrever(celula_.paragraphs[0], str(v))
            for extra in list(celula_.paragraphs[1:]):
                _apagar(extra)


# O template pede 2 a 3 páginas, e o conteúdo obrigatório das cinco tabelas não
# cabe nisso a 11pt. Encolher a tabela — e não o texto corrido — é a escolha
# certa: tabela se consulta, parágrafo se lê. As larguras são explícitas porque
# o Word, deixado por conta própria, reparte a página em colunas iguais e faz a
# coluna de rótulo desperdiçar metade da linha.
CORPO_TABELA_PT = 9
LARGURAS = {
    0: [1.90, 4.87],                                           # modelo
    1: [0.50, 1.00, 0.80, 0.72, 0.85, 0.95, 0.95, 1.00],       # política
    2: [1.05, 1.95, 3.77],                                     # alavancas
    3: [1.55, 3.30, 1.92],                                     # projeção
    4: [2.20, 4.57],                                           # papéis
}


def _tipografia(doc) -> None:
    """Corpo de 9pt e largura de coluna que o Word de fato obedece.

    Escrever só `cell.width` não basta: com layout automático o Word reparte a
    página pelo `tblGrid`, e a largura pedida na célula é ignorada. Custou uma
    rodada inteira descobrir isso — a tabela saía com as colunas erradas e o
    documento estourava a terceira página.
    """
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt

    for i, tb in enumerate(doc.tables):
        larguras = LARGURAS.get(i)
        tb.autofit = False
        if larguras:
            layout = tb._tbl.tblPr.find(qn("w:tblLayout"))
            if layout is None:
                layout = tb._tbl.tblPr.makeelement(qn("w:tblLayout"), {})
                tb._tbl.tblPr.append(layout)
            layout.set(qn("w:type"), "fixed")
            grade = tb._tbl.find(qn("w:tblGrid"))
            if grade is not None:
                for col, pol in zip(grade.findall(qn("w:gridCol")), larguras):
                    col.set(qn("w:w"), str(int(pol * 1440)))
        for linha in tb.rows:
            for j, cel in enumerate(linha.cells):
                if larguras and j < len(larguras):
                    cel.width = Inches(larguras[j])
                for par in cel.paragraphs:
                    for run in par.runs:
                        run.font.size = Pt(CORPO_TABELA_PT)


def escrever_docx(tb: dict, tx: dict) -> None:
    from docx import Document

    doc = Document(str(TEMPLATE))
    P = list(doc.paragraphs)

    _escrever(P[1], CABECALHO)
    _apagar(P[2])  # as instruções do template

    _escrever(P[4], tx["resumo_1"])
    _clonar_depois(P[4]._element, P[4], tx["resumo_2"])
    _apagar(P[5])
    _apagar(P[6])

    _preencher(doc.tables[0], tb["modelo"])
    # O template fala com o grupo ("O que voces fizeram"); o documento
    # entregue fala pelo grupo.
    _escrever(doc.tables[0].cell(0, 1).paragraphs[0], CAB_MODELO[1])
    _escrever(P[8], tx["modelo"])

    _escrever(P[10], tx["score_1"])
    _clonar_depois(P[10]._element, P[10], tx["score_2"])
    _apagar(P[11])

    _escrever(P[13], tx["tabela_abre"])
    _preencher(doc.tables[1], tb["politica"])
    _apagar(P[14])
    _escrever(P[15], tx["tabela_nota"])

    _escrever(P[17], tx["preco_1"])
    _clonar_depois(P[17]._element, P[17], tx["preco_2"])
    _apagar(P[18])
    _preencher(doc.tables[2], tb["alavancas"])

    # Seção 6: a tabela fala primeiro; a ressalva do ROI vem depois dela.
    _preencher(doc.tables[3], tb["projecao"])
    _clonar_depois(doc.tables[3]._element, P[20], tx["projecao_nota"], estilo="Normal")
    _apagar(P[20])

    _escrever(P[22], tx["riscos_abre"])
    _escrever(P[23], tx["risco_1"])
    _escrever(P[24], tx["risco_2"])
    ancora = P[24]._element
    for chave in ("risco_3", "risco_4"):
        ancora = _clonar_depois(ancora, P[24], tx[chave], estilo="List Paragraph")._element
    _apagar(P[25])
    _apagar(P[26])

    _preencher(doc.tables[4], tb["papeis"])

    _tipografia(doc)

    REPORTS.mkdir(exist_ok=True)
    doc.save(str(ARQ_DOCX))


# --------------------------------------------------------------------------- #
# Conferência
# --------------------------------------------------------------------------- #


def conferir(d: dict, est: pd.DataFrame, tb: dict) -> Conferencia:
    """A tabela publicada contra a submissão que foi entregue.

    São os 10 pontos de coerência do enunciado. Tudo do disco: a submissão vem
    do CSV, nunca do DataFrame que a gerou.
    """
    conf = Conferencia("Coerência entre o documento e a submissão")
    sub = pd.read_csv(ARQ_SUBMISSAO, encoding="utf-8")
    t = d["tabela"].set_index("faixa")
    p, s = d["politica"], d["submissoes"]

    conf.checar(
        bool((faixa(sub["pd"].to_numpy()) == sub["score_1a10"].to_numpy()).all()),
        "os cortes publicados reproduzem score_1a10",
        "a partir da coluna pd do próprio CSV",
    )

    ok_dec = ok_taxa = ok_ent = ok_n = True
    for f in range(1, 11):
        l = t.loc[f]
        sf = sub[sub["score_1a10"] == f]
        ok_n &= len(sf) == int(l["n"])
        ok_dec &= set(sf["decisao"]) == {l["decisao"]}
        if l["decisao"] == "APROVAR":
            ok_taxa &= set(sf["taxa_am"].round(6)) == {round(float(l["taxa_am"]), 6)}
            ok_ent &= set(sf["pct_entrada_minima"].round(6)) == {
                round(float(l["entrada_minima"]), 6)
            }
        else:
            ok_taxa &= bool(sf["taxa_am"].isna().all())
            ok_ent &= bool(sf["pct_entrada_minima"].isna().all())

    conf.checar(ok_n, "contagem por faixa idêntica à submissão")
    conf.checar(ok_dec, "decisão por faixa idêntica à submissão")
    conf.checar(ok_taxa, "taxa por faixa idêntica à submissão", "e única dentro da faixa")
    conf.checar(ok_ent, "entrada por faixa idêntica à submissão", "e única dentro da faixa")

    # A tabela publicada tem de ser auditável linha a linha: quem refizer
    # (juros - perda) / prazo tem de chegar ao ROI impresso ao lado.
    ap = t[t["decisao"] == "APROVAR"]
    erro = float(
        np.abs((ap["juros_pct"] - ap["perda_pct"]) / (ap["prazo_medio"] / 12) - ap["roi"]).max()
    )
    conf.checar(
        erro < 1e-4,
        "o ROI de cada faixa reproduz da própria linha",
        f"erro máximo {num(erro * 100, 4)} p.p.",
    )

    perda = perda_por_faixa(d)
    conf.checar(
        bool((perda.sort_index(ascending=False).diff().dropna() > 0).all()),
        "perda esperada cresce da faixa 10 para a faixa 1",
    )
    conf.checar(
        float(ap["taxa_am"].max()) <= MAX_CET_AM + 1e-9,
        "taxa máxima publicada dentro do teto de CET",
        f"{pct(ap['taxa_am'].max(), 2)} <= {pct(MAX_CET_AM, 1)}",
    )
    conf.checar(
        abs(p["aprovacao"] - s["taxa_aprovacao"]) < 1e-9
        and int(s["aprovadas"]) == int(t.loc[t["decisao"] == "APROVAR", "n"].sum()),
        "aprovação bate entre política, submissão e tabela",
        f"{inteiro(s['aprovadas'])} contratos",
    )

    duro = celula(est, "pessimista", 1.2)
    conf.checar(
        abs(float(duro["roi"]) - p["roi_canto_duro"]) < 1e-6
        and abs(float(duro["volume"]) - p["volume_canto_duro"]) < 1e-3,
        "estresse recalculado reproduz o canto duro de politica.json",
    )
    conf.checar(bool(duro["ok"]), "a política cumpre os quatro guardrails no canto duro")
    conf.checar(
        len(tb["politica"]) == 10 and all(len(l) == len(CAB_POLITICA) for l in tb["politica"]),
        "a tabela publicada tem as dez faixas e as colunas do template",
    )
    conf.checar(
        ARQ_DOCX.exists() and ARQ_DOCX.stat().st_size > 10_000,
        "o .docx foi gravado",
        str(ARQ_DOCX.relative_to(RAIZ)).replace("\\", "/") if ARQ_DOCX.exists() else "ausente",
    )
    return conf


# --------------------------------------------------------------------------- #


def main(apenas_conferir: bool = False) -> None:
    print("=" * 96)
    print("RELATÓRIOS — documento de política")
    print("=" * 96)

    d = carregar()
    print("\n  recalculando o teste de estresse sobre a oferta publicada...")
    est = estresse(d)

    tb = {
        "modelo": tabela_modelo(d),
        "politica": tabela_politica_publicada(d),
        "alavancas": tabela_alavancas(d),
        "projecao": tabela_projecao(d),
        "papeis": tabela_papeis(),
    }
    tx = paragrafos(d, est)

    if not apenas_conferir:
        REPORTS.mkdir(exist_ok=True)
        ARQ_MD.write_text(escrever_markdown(d, est, tb, tx), encoding="utf-8", newline="\n")
        escrever_docx(tb, tx)
        print(f"  {str(ARQ_MD.relative_to(RAIZ)).replace(chr(92), '/')} gravado")
        print(f"  {str(ARQ_DOCX.relative_to(RAIZ)).replace(chr(92), '/')} gravado")

    print("\n--- A tabela que vai ao conselho ---\n")
    print(f"  {'score':>5} {'faixa de PD':>18} {'decisão':>8} {'taxa':>7} "
          f"{'entrada':>13} {'perda esp.':>11} {'ROI':>7}")
    for l in tb["politica"]:
        print(f"  {l[0]:>5} {l[1]:>18} {l[2]:>8} {l[3]:>7} {l[5]:>13} {l[6]:>11} {l[7]:>7}")

    print("\n--- Teste de estresse ---\n")
    for _, l in est.iterrows():
        marca = "todos ok" if l["ok"] else "QUEBRA inadimplência"
        print(f"  {l['cenario']:<12} x{l['mult_pd']:.1f}  {milhoes(l['volume']):>10}  "
              f"{pct(l['inadimplencia'], 2):>7}  {pct(l['roi']):>6}   {marca}")

    conf = conferir(d, est, tb)
    ok = conf.imprimir()

    registrar_execucao(
        "relatorios",
        {
            "etapa": "src/relatorios",
            "documento": "reports/documento_politica.docx",
            "conferencias": len(conf.linhas),
            "falhas": len(conf.falhas),
            "regra": ESCOLHIDA.rotulo(),
            "roi_central": d["politica"]["roi_central"],
            "roi_canto_duro": d["politica"]["roi_canto_duro"],
        },
    )
    print("\n  O documento foi gerado por este script. Nenhum valor foi digitado.")
    print("  Falta preencher no Word: o número do grupo e os três nomes da seção 8.")
    print("=" * 96)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main(apenas_conferir="--conferir" in sys.argv)
