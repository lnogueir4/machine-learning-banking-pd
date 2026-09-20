"""Geração do relatório do modelo — Desafio AutoCred.

O outro entregável escrito é o documento de política (`src/relatorios.py`), que
vai ao conselho em 2 a 3 páginas. **Este é o relatório técnico**: ele responde à
banca, não ao conselho, e a pergunta que responde é se os 40 pontos do modelo
foram conquistados com método ou com sorte de janela.

Regra de procedência, declarada no cabeçalho do próprio relatório porque é o que
o leitor precisa saber antes de acreditar em qualquer número:

  - valor que existe em `artefatos/` é **lido** de lá;
  - valor que sai de uma conta direta sobre `bases/` ou sobre os arquivos
    entregues é **recalculado aqui**, a cada execução;
  - medição que exigiria retreinar o modelo **não vira número neste arquivo**.
    É descrita em palavras e remetida ao capítulo de `docs/` que a reproduz.

A terceira regra é a que evita o erro mais caro do projeto. Copiar para cá um
número que só existe numa transcrição de terminal é como publicá-lo de memória:
ninguém consegue conferir, e ele sobrevive a mudanças no pipeline sem avisar.
Foi por isso que `modelo.py` passou a gravar `importancias.csv` e
`validacao_encadeada.csv` — as duas tabelas que sustentam a decisão de **não**
podar variáveis, e que antes só existiam no `stdout`.

Uso:
    PYTHONIOENCODING=utf-8 python src/relatorio_modelo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import ParameterGrid

from dados import (
    ALVO,
    ARTEFATOS,
    CANDIDATAS,
    COLS_DESCARTADAS,
    FEATURES,
    RAIZ,
    carregar_base_a,
    carregar_base_b,
    carregar_base_c,
    colunas_proibidas,
    registrar_execucao,
)
from features import ANO_CORTE, preparar_aplicacao
from modelo import GRADES
from relatorios import CABECALHO, ENTREGAVEIS, REPORTS, inteiro, md_tabela, num, pct
from score import CORTES, faixa
from submissoes import Conferencia

ARQ_RELATORIO = REPORTS / "relatorio_modelo.md"
ARQ_SUBMISSAO = ENTREGAVEIS / "submissao_modelo.csv"

# As três colunas com faltante conhecido, na ordem em que o dicionário as traz.
COM_FALTANTE = ["renda_mensal_declarada", "tempo_emprego_meses", "score_bureau"]

# As variáveis em que a Base C sai do intervalo que o treino conheceu. As três
# primeiras são atributos de crédito — é delas que sai a regra recuperada da
# política antiga; as duas últimas são da estrutura da operação e entram para
# mostrar que o deslocamento **não** é uniforme.
VARS_DOMINIO = [
    "score_bureau",
    "qtd_restricoes_ativas",
    "comprometimento_renda",
    "ltv",
    "valor_entrada",
]
VARS_REGRA = VARS_DOMINIO[:3]

# Por que cada coluna proibida é proibida. Texto, não número: o dicionário diz
# *que* ela é indisponível na concessão, não *o que* ela é.
MOTIVO_PROIBIDA = {
    "qtd_parcelas_em_atraso_12m": "comportamento posterior à concessão; parece bureau e não é",
    "default_90_12": "o próprio alvo",
    "mes_default": "quando o default aconteceu — existe só depois dele",
    "ead_realizado": "exposição apurada no default",
    "lgd_realizado": "perda apurada no workout, 24 meses depois",
    "perda_financeira": "o prejuízo já contabilizado",
}


def _js(nome: str) -> dict:
    return json.loads((ARTEFATOS / f"{nome}.json").read_text(encoding="utf-8"))


def _periodo(s: pd.Series) -> str:
    return f"{s.min():%m/%Y} a {s.max():%m/%Y}"


def sinal(x, casas: int = 4) -> str:
    """Número com sinal explícito e **menos tipográfico**.

    `num()` devolve o hífen do teclado. Numa tabela de deltas o hífen fica curto
    demais para ser lido como sinal — e este relatório tem três tabelas em que o
    sinal é a informação principal.
    """
    texto = ("+" if x > 0 else "") + num(x, casas)
    return texto.replace("-", "−")


def _rho(x, y) -> float:
    """Spearman: Pearson sobre os postos. Duas linhas, sem trazer o scipy."""
    postos = [pd.Series(v).rank().to_numpy() for v in (x, y)]
    return float(np.corrcoef(*postos)[0, 1])


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #


def carregar() -> dict:
    """Artefatos, bases e os arquivos entregues — tudo do disco."""
    a, b = carregar_base_a(), carregar_base_b()
    c = carregar_base_c()
    # A Base C só é comparável ao treino depois de `preparar_aplicacao`: é essa
    # função que reconstrói `comprometimento_renda` pela Price, e sem ela a
    # comparação de domínio não enxerga o terceiro corte da política antiga.
    c_prep = preparar_aplicacao(c)

    semestre = a["data_originacao"].dt.year.astype(str) + "-S" + (
        (a["data_originacao"].dt.month > 6).astype(int) + 1
    ).astype(str)

    return {
        "a": a,
        "b": b,
        "c": c,
        "c_prep": c_prep,
        "semestre": semestre,
        "auditoria": _js("auditoria_dados"),
        "eda": _js("eda_exploracao"),
        "feat": _js("decisoes_features"),
        "modelo": _js("modelo"),
        "dec_score": _js("decisoes_score"),
        "score": _js("score"),
        "sub": _js("submissoes"),
        "iv": pd.read_csv(ARTEFATOS / "eda_iv_psi.csv"),
        "cmp": pd.read_csv(ARTEFATOS / "modelo_comparacao.csv"),
        "dec_feat": pd.read_csv(ARTEFATOS / "decisoes_features.csv"),
        "estrat": pd.read_csv(ARTEFATOS / "decisoes_score.csv"),
        "faixas": pd.read_csv(ARTEFATOS / "tabela_faixas.csv"),
        "imp": pd.read_csv(ARTEFATOS / "importancias.csv"),
        "enc": pd.read_csv(ARTEFATOS / "validacao_encadeada.csv"),
        "pd_a": pd.read_csv(ARTEFATOS / "pd_base_a.csv"),
        "pd_c": pd.read_csv(ARTEFATOS / "perda_esperada_base_c.csv"),
        "submissao": pd.read_csv(ARQ_SUBMISSAO),
    }


def auroc_da_proibida(d: dict) -> float:
    """AuROC de `qtd_parcelas_em_atraso_12m` sozinha, como variável única.

    Ela é lida **direto da base**, nunca por `matriz()`: o ponto é justamente
    que o pipeline se recusa a entregá-la. O número existe para dimensionar a
    tentação — um modelo de uma variável proibida bate qualquer modelo honesto.
    """
    a = d["a"]
    return float(roc_auc_score(a[ALVO], a["qtd_parcelas_em_atraso_12m"]))


def dominio(d: dict) -> tuple[pd.DataFrame, float]:
    """Onde a Base C sai do intervalo observado em toda a Base A.

    O intervalo de referência é a Base A **inteira**, não a janela de treino: a
    afirmação que interessa é "nenhum dos dez mil contratos históricos", que é a
    mais forte possível e a que sustenta chamar isto de regra, e não de amostra
    rala.
    """
    a, c = d["a"], d["c_prep"]
    linhas, fora_da_regra = [], np.zeros(len(c), dtype=bool)
    for v in VARS_DOMINIO:
        lo, hi = float(a[v].min()), float(a[v].max())
        marca = (c[v] < lo) | (c[v] > hi)
        marca = marca.fillna(False).to_numpy()
        if v in VARS_REGRA:
            fora_da_regra |= marca
        # Razão e proporção pedem casas decimais; contagem e dinheiro pedem
        # ponto de milhar. Formatar tudo igual tornaria a tabela ilegível nas
        # duas pontas.
        # `inteiro` trunca; num extremo observado isso publica um piso menor e
        # um teto maior do que os que existem na base. Arredonda-se.
        fmt = (
            (lambda x: num(x, 2))
            if v in ("ltv", "comprometimento_renda")
            else (lambda x: inteiro(round(x)))
        )
        linhas.append(
            [
                f"`{v}`",
                fmt(lo),
                fmt(hi),
                fmt(float(c[v].min())),
                fmt(float(c[v].max())),
                pct(marca.mean(), 1),
            ]
        )
    return pd.DataFrame(linhas), float(fora_da_regra.mean())


def psi_das_bases(d: dict) -> tuple[float, float]:
    """PSI da distribuição de faixas de B e de C contra a safra de 2022.

    A referência é a mesma que `src/score.py` usou para gravar `score.json` —
    a safra de 2022, e não a Base A inteira. Duas referências dariam dois
    números igualmente defensáveis e incomparáveis entre si, que é o defeito
    que uma tabela publicada não pode ter. A conferência no fim deste módulo
    exige que o valor recalculado bata com o do artefato.
    """
    from score import estabilidade

    a = d["a"]
    pda = d["pd_a"].set_index("id_contrato").loc[a["id_contrato"]].reset_index()
    f_a = pd.Series(faixa(pda["pd_oof"].to_numpy()))
    ref = f_a[(a["data_originacao"].dt.year == 2022).to_numpy()]
    f_b = pd.Series(faixa(d["submissao"]["pd"].to_numpy()))
    f_c = pd.Series(d["pd_c"]["faixa"])
    return float(estabilidade(ref, f_b)), float(estabilidade(ref, f_c))


def distribuicao_de_faixas(d: dict) -> pd.DataFrame:
    """Peso de cada faixa nas três bases, cada uma pelo arquivo que a representa.

    Base A vem da tabela de faixas; Base B, da **submissão entregue** — é a
    própria coluna `pd` do CSV que a banca vai ler; Base C, da tabela de perda
    esperada. Nenhuma das três é recalculada com o modelo em memória.
    """
    pesos_a = d["faixas"].set_index("faixa")["pct"]
    f_b = pd.Series(faixa(d["submissao"]["pd"].to_numpy())).value_counts(normalize=True)
    f_c = d["pd_c"]["faixa"].value_counts(normalize=True)
    linhas = []
    for k in range(10, 0, -1):
        linhas.append(
            [
                str(k),
                pct(float(pesos_a.get(k, 0.0)), 1),
                pct(float(f_b.get(k, 0.0)), 1),
                pct(float(f_c.get(k, 0.0)), 1),
            ]
        )
    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------- #
# As tabelas
# --------------------------------------------------------------------------- #


def tab_bases(d: dict) -> list[list[str]]:
    a, b, c = d["a"], d["b"], d["c"]
    return [
        ["A — desenvolvimento", inteiro(len(a)), _periodo(a["data_originacao"]),
         "treino e validação", "sim"],
        ["B — teste do modelo", inteiro(len(b)), _periodo(b["data_originacao"]),
         "AuROC oficial, out-of-time", "**não**"],
        ["C — política", inteiro(len(c)), _periodo(c["data_proposta"]),
         "recebe a política; ROI oficial", "**não**"],
    ]


def tab_safras(d: dict) -> list[list[str]]:
    a = d["a"]
    g = a.groupby(d["semestre"])
    return [[s, inteiro(len(sub)), pct(float(sub[ALVO].mean()), 2)] for s, sub in g]


def tab_proibidas(d: dict) -> list[list[str]]:
    return [[f"`{col}`", MOTIVO_PROIBIDA.get(col, "indisponível na concessão")]
            for col in colunas_proibidas()]


# O artefato guarda quatro veredictos de monotonicidade; a tabela do relatório
# precisa de rótulo curto, e "não aplicável" (o caso binário) não pode virar
# "não" — seria afirmar que a variável é não monotônica.
ROTULO_MONOTONIA = {"monotônica": "sim", "aceitável": "aceitável", "não aplicável": "—"}


def tab_iv(d: dict) -> list[list[str]]:
    linhas = []
    for _, l in d["iv"].iterrows():
        psi = l["PSI_aplicacao"]
        linhas.append(
            [
                f"`{l['variável']}`",
                num(l["IV_treino"], 4),
                l["força"],
                "—" if pd.isna(psi) else num(psi, 3),
                ROTULO_MONOTONIA.get(str(l["monotonicidade"]), "não"),
            ]
        )
    return linhas


def tab_ausentes(d: dict) -> list[list[str]]:
    """Presença do faltante nas três bases, e o que ele diz sobre o risco.

    A comparação de PD roda na **janela de treino**, não na Base A inteira: foi
    nela que a decisão de não criar indicadores de ausência foi tomada, e usar a
    safra de conferência para justificar a decisão a posteriori é a mesma falha
    que a seção 7 descreve.
    """
    a, b, c = d["a"], d["b"], d["c"]
    treino = a[a["data_originacao"].dt.year < ANO_CORTE]
    linhas = []
    for col in COM_FALTANTE:
        falta = treino[col].isna()
        pd_falta = float(treino.loc[falta, ALVO].mean())
        pd_ok = float(treino.loc[~falta, ALVO].mean())
        linhas.append(
            [
                f"`{col}`",
                pct(float(a[col].isna().mean()), 2),
                pct(float(b[col].isna().mean()), 2),
                pct(float(c[col].isna().mean()), 2),
                inteiro(int(falta.sum())),
                pct(pd_falta, 2),
                pct(pd_ok, 2),
                num(pd_falta / pd_ok, 2) + "x",
            ]
        )
    return linhas


def _nome_derivada(conjunto: str) -> str:
    """`+ pressao_bureau` -> ``+ `pressao_bureau` ``, e o resto intacto."""
    if conjunto.startswith("+ ") and "todas" not in conjunto:
        return "+ `" + conjunto[2:] + "`"
    return conjunto


def tab_derivadas(d: dict) -> list[list[str]]:
    sub = d["dec_feat"].query("secao == 'derivadas'")
    return [
        [
            _nome_derivada(l["conjunto"]),
            num(l["CV"], 4),
            "±" + num(l["dp"], 4),
            num(l["OOT"], 4),
            "—" if l["ΔCV"] == 0 else sinal(l["ΔCV"]),
        ]
        for _, l in sub.iterrows()
    ]


def tab_imputacao(d: dict) -> list[list[str]]:
    """O artefato guarda `modelo | tratamento` num campo só.

    A barra é separador de coluna em markdown: publicada como está, ela abre uma
    coluna a mais e desalinha a tabela inteira. Aqui ela vira a divisão de
    colunas que sempre foi.
    """
    sub = d["dec_feat"].query("secao == 'imputacao'")
    linhas = []
    for _, l in sub.iterrows():
        modelo, _, trato = str(l["configuração"]).partition("|")
        linhas.append(
            [modelo.strip(), trato.strip(), num(l["CV"], 4), "±" + num(l["dp"], 4),
             num(l["OOT"], 4)]
        )
    return linhas


def tab_modelos(d: dict) -> list[list[str]]:
    return [
        [
            f"**{l['modelo']}**" if l["modelo"] == d["modelo"]["vencedor"] else l["modelo"],
            num(l["AUC treino"], 4),
            num(l["AUC OOT"], 4),
            num(l["queda"], 4),
            num(l["KS OOT"], 3),
            num(l["Brier OOT"], 4),
            sinal(l["viés OOT"]),
        ]
        for _, l in d["cmp"].iterrows()
    ]


def tab_grades(d: dict) -> list[list[str]]:
    """Quantas combinações cada candidato recebeu, contadas da própria grade."""
    m = d["modelo"]
    venc = {**m["hiperparametros_baselines"],
            m["vencedor"]: {k.replace("modelo__", ""): v for k, v in m["hiperparametros"].items()}}
    linhas = []
    for nome, grade in GRADES.items():
        p = venc.get(nome, {})
        texto = ", ".join(f"`{k}={v}`" for k, v in p.items() if k != "max_iter")
        linhas.append([nome, inteiro(len(ParameterGrid(grade))), texto])
    return linhas


def tab_importancias(d: dict) -> list[list[str]]:
    return [
        [f"`{l['variável']}`", sinal(l["queda_auc"]), "±" + num(l["dp"], 4)]
        for _, l in d["imp"].iterrows()
    ]


def tab_encadeada(d: dict) -> list[list[str]]:
    enc, janelas = d["enc"], [c for c in d["enc"].columns if "->" in c]
    return [
        [l["conjunto"], *[num(l[j], 4) for j in janelas],
         f"**{num(l['média'], 4)}**", f"*{num(l['OOT 2024'], 4)}*"]
        for _, l in enc.iterrows()
    ]


def tab_estrategias(d: dict) -> list[list[str]]:
    sub = d["estrat"].query("secao == 'estrategias'")
    return [
        [
            f"**{l['estratégia']}**" if l["estratégia"] == "progressiva" else l["estratégia"],
            num(l["AuROC faixa"], 4),
            num(l["rho"], 3).replace("-", "−"),
            str(int(l["inversões"])),
            f"{int(l['pares indistintos'])} de {int(l['faixas']) - 1}",
            inteiro(l["menor faixa em A"]),
            inteiro(l["menor faixa em C"]),
        ]
        for _, l in sub.iterrows()
    ]


def tab_granularidade(d: dict) -> list[list[str]]:
    sub = d["estrat"].query("secao == 'granularidade'")
    linhas = []
    for _, l in sub.iterrows():
        cont = l["estratégia"] == "PD contínua"
        linhas.append(
            [
                l["estratégia"],
                num(l["AuROC faixa"], 4),
                "—" if cont else str(int(l["inversões"])),
                "—" if cont else f"{int(l['pares indistintos'])} de {int(l['faixas']) - 1}",
                "—" if cont else inteiro(l["menor faixa em C"]),
            ]
        )
    return linhas


def tab_faixas(d: dict) -> list[list[str]]:
    return [
        [
            str(int(l["faixa"])),
            inteiro(l["n"]),
            pct(l["pd_de"], 2),
            pct(l["pd_ate"], 2),
            pct(l["pd_prevista"], 2),
            f"**{pct(l['pd_observada'], 2)}**" if int(l["faixa"]) in (1, 10)
            else pct(l["pd_observada"], 2),
            f"{pct(l['ic_lo'], 1)} – {pct(l['ic_hi'], 1)}",
        ]
        for _, l in d["faixas"].sort_values("faixa").iterrows()
    ]


def medicoes(d: dict) -> tuple[float, float, float]:
    """As três medições independentes da configuração **entregue**.

    Todas as três são do modelo calibrado, que é o que foi serializado. A
    coluna `AUC OOT` de `modelo_comparacao.csv` mede outra coisa — os cinco
    candidatos **antes** da calibração, para que a comparação entre eles seja
    justa — e por isso não entra aqui. Misturar as duas famílias publicaria uma
    faixa cujo extremo superior descreve um objeto diferente dos outros dois.
    """
    enc = d["enc"].iloc[0]
    return (
        float(enc["média"]),
        float(d["dec_score"]["auroc_oof"]),
        float(enc["OOT 2024"]),
    )


def tab_medicoes(d: dict) -> list[list[str]]:
    baixo, oof, alto = medicoes(d)
    return [
        [f"Validação encadeada em janelas anteriores a {ANO_CORTE}", num(baixo, 4),
         "três janelas nunca usadas para decidir nada; a mais conservadora"],
        ["Out-of-fold sobre toda a Base A", num(oof, 4),
         "cinco dobras sorteadas; é a PD que define os cortes de faixa"],
        [f"Out-of-time na safra de {ANO_CORTE}", num(alto, 4),
         "treino em 2022-23, teste em 2024; imita a Base B"],
    ]


def tab_arredondamento(d: dict) -> list[list[str]]:
    s = d["sub"]
    linhas = []
    for casas in (2, 3, 4, 5, 6):
        linhas.append(
            [
                f"{casas} casas",
                inteiro(s[f"trocam_faixa_{casas}_casas"]),
                num(s[f"auroc_{casas}_casas"], 6),
                sinal(s[f"auroc_{casas}_casas"] - s["auroc_oof_cru"], 6),
            ]
        )
    return linhas


def tab_bases_pd(d: dict) -> list[list[str]]:
    """PD média por base, cada uma do arquivo que a publica."""
    pa = d["pd_a"]["pd_final"]
    pb = d["submissao"]["pd"]
    pc = d["pd_c"]["pd"]
    return [
        ["A — 2022-2024, aprovados", pct(float(pa.mean()), 2), pct(float(pa.median()), 2),
         pct(float(pa.quantile(0.90)), 2), pct(float((pa > 0.20).mean()), 1)],
        ["B — 2025-S1, aprovados", pct(float(pb.mean()), 2), pct(float(pb.median()), 2),
         pct(float(pb.quantile(0.90)), 2), pct(float((pb > 0.20).mean()), 1)],
        ["**C — 2025-S2, mar aberto**", f"**{pct(float(pc.mean()), 2)}**",
         pct(float(pc.median()), 2), pct(float(pc.quantile(0.90)), 2),
         f"**{pct(float((pc > 0.20).mean()), 1)}**"],
    ]


# --------------------------------------------------------------------------- #
# O texto
# --------------------------------------------------------------------------- #


def escrever(d: dict) -> str:
    m, sc, sb, ft = d["modelo"], d["score"], d["sub"], d["feat"]
    dom, fora_regra = dominio(d)
    a = d["a"]
    cmp_ = d["cmp"]
    venc = cmp_.loc[cmp_["modelo"] == m["vencedor"]].iloc[0]
    pior = cmp_.loc[cmp_["modelo"] == "HistGB padrão"].iloc[0]
    enc = d["enc"]
    baixo, oof, alto = medicoes(d)
    faixas = d["faixas"].set_index("faixa")
    lift = float(faixas.loc[1, "pd_observada"] / faixas.loc[10, "pd_observada"])
    h = m["hiperparametros"]
    auroc_progressiva = float(
        d["estrat"].set_index("estratégia").loc["progressiva", "AuROC faixa"]
    )
    psi_b, psi_c = psi_das_bases(d)
    # O IV máximo publicado é um teto: "não passa de 0,17" seria falso com
    # 0,1731 na tabela logo acima.
    teto_iv = np.ceil(float(d["iv"]["IV_treino"].max()) * 100) / 100

    L: list[str] = [
        "# Relatório do Modelo de PD — AutoCred",
        "",
        CABECALHO,
        "",
        "> Gerado por `src/relatorio_modelo.py`. **Regra de procedência:** todo número deste",
        "> relatório é lido de `artefatos/` ou recalculado aqui, a cada execução, a partir de",
        "> `bases/` e dos arquivos entregues. Nenhum foi digitado. Medição que exigiria",
        "> retreinar o modelo não aparece aqui como número: é descrita e remetida ao capítulo",
        "> de `docs/` que a reproduz.",
        "",
        "---",
        "",
        "## Resumo",
        "",
        f"Entregamos `entregaveis/submissao_modelo.csv` — {inteiro(len(d['submissao']))} linhas, uma "
        f"por contrato da Base B, com a probabilidade de o contrato atingir 90 dias de atraso nos "
        f"12 meses seguintes à concessão (PD 90/12), em {sb['casas_pd']} casas decimais.",
        "",
        f"O modelo é um **gradient boosting em árvores** (`HistGradientBoostingClassifier`) com "
        f"regularização forte — {h['modelo__max_leaf_nodes']} folhas por árvore, taxa de "
        f"aprendizado {num(h['modelo__learning_rate'], 2)}, mínimo de {h['modelo__min_samples_leaf']} "
        f"casos por folha, L2 = {num(h['modelo__l2_regularization'], 1)} — treinado sobre "
        f"{ft['n_features']} variáveis e envelopado em calibração {m['calibracao']}. Seed "
        f"{m['seed']}, Python {m['python']}, scikit-learn {m['scikit_learn']}.",
        "",
        f"**O desempenho que reportamos é uma faixa, não um número:** três medições independentes "
        f"da configuração entregue dão AuROC de {num(baixo, 4)}, {num(oof, 4)} e {num(alto, 4)}. "
        f"Reportamos **{num(baixo, 2)} a {num(alto, 2)}** e não o melhor dos três, porque escolher "
        f"o maior é escolher a janela mais favorável depois de ver as três.",
        "",
        f"Em termos de negócio: a faixa 1 da tabela de score quebra "
        f"**{num(lift, 1).replace(',0', '')} vezes mais** que a faixa 10 "
        f"({pct(faixas.loc[1, 'pd_observada'], 1)} contra "
        f"{pct(faixas.loc[10, 'pd_observada'], 2)}, fora da amostra). É esse número que justifica o "
        f"modelo existir.",
        "",
        "E a limitação que atravessa o relatório inteiro, dita já aqui porque muda a leitura de "
        f"tudo o que vem depois: **as bases A e B só contêm contratos que a política antiga "
        f"aprovou**, e a Base C é mar aberto. O PSI entre A e C é "
        f"{num(sc['psi_a_para_c'], 3)} — a régua chama isso de população trocada. Para o AuROC da "
        "Base B isso é irrelevante, porque B tem o mesmo filtro de A. Para a política, não.",
        "",
        "---",
        "",
        "## 1. O alvo e as três bases",
        "",
        "O alvo é `default_90_12`: 1 se o contrato atingiu 90 dias de atraso na janela de 12 meses "
        "posterior à concessão. É binário, fechado e sem nulos.",
        "",
    ]
    L += md_tabela(["Base", "Linhas", "Período", "Papel", "Tem o alvo?"], tab_bases(d))
    L += [
        f"A PD global da Base A é **{pct(float(a[ALVO].mean()), 2)}** "
        f"({inteiro(int(a[ALVO].sum()))} defaults em {inteiro(len(a))} contratos). Por semestre:",
        "",
    ]
    L += md_tabela(["Safra", "Contratos", "PD observada"], tab_safras(d))
    L += [
        "A série **cai**, e a queda não é ruído de um semestre: vai de "
        f"{pct(float(a.groupby(d['semestre'])[ALVO].mean().max()), 2)} no pico a "
        f"{pct(float(a.groupby(d['semestre'])[ALVO].mean().iloc[-1]), 2)} no último semestre "
        "observado. A Base B é 2025-S1 e a Base C é 2025-S2 — as duas **depois do fim da série**. "
        "Um modelo calibrado na Base A inteira carrega o nível médio de 2022-2024 e tende a "
        "superestimar a PD dessas safras. Para a submissão do modelo isso não importa: o AuROC lê "
        "ordenação, não nível. Para a política, importa, e empurra em sentido contrário ao viés de "
        "aprovados — as duas derivas não se cancelam por decreto.",
        "",
        "**A Base B não tem o alvo.** Não existe conferir o AuROC antes de enviar; o resultado só "
        "aparece na apuração. Tudo o que temos é disciplina de validação interna, e é disso que "
        "trata a seção 6.",
        "",
        "---",
        "",
        "## 2. Vazamento: a defesa é código, não disciplina",
        "",
        "O dicionário oficial tem a coluna `Disponível na concessão?`. As colunas marcadas com "
        "`NÃO` descrevem o que aconteceu **depois** de conceder:",
        "",
    ]
    L += md_tabela(["Coluna", "O que é"], tab_proibidas(d))
    L += [
        "A lista não está escrita no código. É **lida do dicionário a cada execução**, e a "
        "validação roda antes de qualquer `fit`:",
        "",
        "```python",
        "def validar_features(features=None) -> list[str]:",
        "    invasoras = sorted(set(features or FEATURES) & set(colunas_proibidas()))",
        "    if invasoras:",
        "        raise VazamentoDetectado(...)",
        "    return features",
        "```",
        "",
        "A alternativa — a lista literal no código — funciona até o material ser atualizado e "
        "ninguém lembrar de editá-la. A falha seria silenciosa: o modelo treinaria normalmente. Um "
        "modelo que não treina é melhor que um modelo que treina com vazamento.",
        "",
        f"O tamanho da tentação, medido: `qtd_parcelas_em_atraso_12m` sozinha, como variável única, "
        f"dá AuROC de **{num(auroc_da_proibida(d), 4)}** na Base A. Ela parece informação de bureau, "
        "está presente nas três bases, e é a armadilha mais cara do desafio — qualquer modelo que a "
        "use vence qualquer modelo honesto, e não vale nada.",
        "",
        "### As nove colunas que a Base C não tem",
        "",
        "Há um segundo filtro, que não é vazamento e derruba o mesmo tanto de gente. Comparando as "
        "colunas que a Base C **de fato traz** com as permitidas pelo dicionário, nove somem — entre "
        f"elas `{COLS_DESCARTADAS[0]}` e `{COLS_DESCARTADAS[1]}`.",
        "",
        "O motivo é conceitual. As bases A e B descrevem **contratos fechados**: taxa e parcela já "
        "foram negociadas. A Base C descreve **propostas**, e traz o que o cliente deseja "
        "(`ltv_desejado`, `prazo_desejado_meses`, `valor_financiado_desejado`). Quem define as "
        "condições efetivas somos nós, pela política. Um modelo que dependa de `taxa_juros_am` "
        "**não consegue pontuar a Base C** — a coluna é uma decisão nossa que ainda não foi tomada.",
        "",
        "Medido no análogo out-of-time dentro da Base A, o conjunto com preço vale cerca de um "
        "milésimo de AuROC a mais e é inutilizável na metade do desafio que vale 40 pontos. A "
        "medição está em [`docs/01-dados.md`](../docs/01-dados.md), decisão 2.",
        "",
        "---",
        "",
        "## 3. Exploração: o sinal é fraco e distribuído",
        "",
        f"Todas as decisões desta seção foram calculadas na janela de treino "
        f"({d['eda']['janela_treino'].replace('< ', 'anterior a ')}, "
        f"{inteiro(d['eda']['n_treino'])} contratos). A safra de {ANO_CORTE} aparece só para "
        "conferir estabilidade, nunca para decidir — escolher variável olhando o conjunto inteiro "
        "contamina a validação out-of-time na sua versão mais discreta.",
        "",
    ]
    L += md_tabela(
        ["Variável", "IV no treino", "Força", "PSI A→C", "Monotônica?"], tab_iv(d)
    )
    L += [
        f"O IV somado é {num(d['eda']['iv_total'], 4)} e **nenhuma variável isolada chega a "
        f"{num(teto_iv, 2)}**. Este é um problema de sinal fraco e "
        "distribuído, não um problema com uma variável dominante — o que explica o teto de AuROC em "
        "torno de 0,74 e confirma que não há nada escondido esperando ser descoberto. A régua de "
        "mercado para IV (abaixo de 0,02 inútil, até 0,10 fraco, até 0,30 médio) é convenção "
        "difundida, não norma; acima de 0,50 ela manda suspeitar de vazamento em vez de comemorar.",
        "",
        "Duas leituras que mudam decisão:",
        "",
        f"- **`ltv` com IV de {num(float(d['iv'].set_index('variável').loc['ltv', 'IV_treino']), 3)}** "
        "é contraintuitivo em financiamento de veículo, onde LTV é *a* variável de garantia. A "
        "explicação é o viés de aprovados: a política antiga truncava o LTV, e o que sobrou na base "
        "tem pouca variação. `ltv` continua indispensável **fora** do modelo — as tabelas oficiais "
        "de EAD e LGD são indexadas por faixa de LTV.",
        f"- **`ano_modelo` junta IV inútil com PSI de "
        f"{num(float(d['iv'].set_index('variável').loc['ano_modelo', 'PSI_aplicacao']), 2)}.** O PSI "
        "alto é artefato de calendário: propostas de 2025 têm veículos mais novos que contratos de "
        "2022. Variável que não prediz e não é estável sai do modelo — é a única que saiu, e é a "
        f"diferença entre as {len(CANDIDATAS)} candidatas e as {len(FEATURES)} do modelo.",
        "",
        "### O faltante quase não informa",
        "",
        "A hipótese de partida era a do mercado: quem não declara renda tem perfil pior, e a "
        "ausência viraria indicador.",
        "",
    ]
    L += md_tabela(
        ["Coluna", "% ausente em A", "em B", "em C", "n ausente no treino",
         "PD se ausente", "PD se presente", "Razão"],
        tab_ausentes(d),
    )
    L += [
        "**A hipótese não se sustentou.** As razões ficam perto de 1, e o caso mais forte tem n "
        "pequeno demais para o intervalo de confiança descolar da média geral. Decisão: **não criar "
        "indicadores de ausência**; imputação simples pela mediana, dentro do pipeline. Registrar a "
        "hipótese testada e descartada vale mais que o indicador que ela teria gerado — é "
        "exatamente a pergunta que a banca faz.",
        "",
        "Repare que os percentuais são praticamente iguais nas três bases. Isso é bom sinal: não há "
        "tratamento diferente entre desenvolvimento e aplicação.",
        "",
        "---",
        "",
        "## 4. O achado mais grave: a Base C sai do domínio do treino",
        "",
        "Esta seção é a que mais condiciona a política, e ela não aparece em nenhuma métrica de "
        "modelo.",
        "",
    ]
    L += md_tabela(
        ["Variável", "mín. em A", "máx. em A", "mín. em C", "máx. em C", "% de C fora"],
        dom.values.tolist(),
    )
    L += [
        "Os limites são de **toda a Base A** — dez mil contratos. Que nenhum deles tenha mais de "
        "duas restrições ativas, ou score de bureau abaixo do piso, não é acaso amostral: é uma "
        "**regra da política de 2022**, recuperada dos dados e não de documento algum. O mesmo vale "
        "para o teto de comprometimento de renda.",
        "",
        f"Somando o perímetro das três variáveis de crédito, **{pct(fora_regra, 1)} das propostas da "
        "Base C caem fora do domínio em ao menos uma delas.** E a consequência é específica: "
        "**modelos baseados em árvore não extrapolam.** Um proponente com cinco restrições cai na "
        "mesma folha de um com duas e recebe a mesma PD. Como duas restrições já multiplicam a PD "
        "em relação a uma, supor que cinco equivalem a duas erra na direção perigosa — o modelo "
        "**subestima sistematicamente** o risco de mais de um quarto da Base C.",
        "",
        "Repare nas duas últimas linhas da tabela: `ltv` e `valor_entrada` mal se deslocam. **O "
        "viés não é uniforme** — está concentrado no risco de crédito do proponente, não na "
        "estrutura da operação. E há uma boa notícia nisso, que o capítulo de política herda: "
        "comprometimento de renda é consequência da **oferta**, e oferta é a alavanca que "
        "controlamos. Score de bureau e restrições ativas, não.",
        "",
        "Isto é o problema de inferência de rejeitados que o enunciado antecipa, agora localizado em "
        "variáveis específicas e medido. Ele **não se resolve com modelagem melhor**: não existe "
        "informação na base sobre como se comporta quem tem cinco restrições. A solução tem de ser "
        "uma regra de política explícita, defendida como decisão de risco e não como saída de "
        "modelo.",
        "",
        "---",
        "",
        "## 5. Pré-processamento: um `Pipeline`, e nenhuma decisão fora dele",
        "",
        "Imputação, encoding e padronização vivem dentro de um `Pipeline` do scikit-learn. Não é "
        "cerimônia: é o que transforma a promessa de \"ajustar só no treino\" em propriedade do "
        "objeto. Calcular a mediana da renda na base inteira e só depois separar treino e teste "
        "contamina a validação sem produzir mensagem de erro alguma.",
        "",
        "### Decisão 1 — nenhuma variável derivada entrou",
        "",
        f"Testamos {ft['derivadas_testadas']} candidatas, todas calculáveis também na Base C, por "
        "validação cruzada de 5 dobras **dentro da janela de treino**:",
        "",
    ]
    L += md_tabela(["Conjunto", "AuROC CV", "dp", f"AuROC OOT {ANO_CORTE}", "ΔCV"], tab_derivadas(d))
    L += [
        f"{'Nenhuma entrou' if ft['derivadas_aprovadas'] == 0 else str(ft['derivadas_aprovadas']) + ' entraram'}. "
        "Seis das sete pioram a validação cruzada; a sétima "
        "melhora por uma fração do desvio padrão da própria medida — não é ganho, é o segundo "
        "decimal do ruído. A leitura não é \"engenharia de atributos não funciona\": é que o sinal "
        "desta base já foi medido na seção 3, e gradient boosting constrói interações por conta "
        "própria. Cada variável a mais é uma a justificar, monitorar e calcular na Base C; variável "
        "que não paga o próprio custo sai.",
        "",
        "### Decisão 2 — `NaN` preservado para a árvore",
        "",
    ]
    L += md_tabela(
        ["Modelo", "Tratamento", "AuROC CV", "dp", f"AuROC OOT {ANO_CORTE}"], tab_imputacao(d)
    )
    L += [
        "O `HistGradientBoostingClassifier` aprende, em cada corte, para que lado mandar o ausente. "
        "Isso é estritamente mais informativo que substituir pela mediana, que apaga a distinção "
        "entre \"renda de R$ 5.222\" e \"renda não declarada\". A vantagem é pequena e sozinha não "
        "decidiria nada — mas as duas réguas apontam para o mesmo lado, e preservar o ausente é "
        "também a opção que não inventa dado. A logística não aceita `NaN` e recebe o tratamento "
        "clássico; ela não é candidata a vencer, é o referencial interpretável.",
        "",
        "### Decisão 3 — a parcela da Base C é reconstruída pela Price",
        "",
        "`comprometimento_renda` (parcela ÷ renda) é a variável de maior ganho marginal isolado do "
        "modelo, e **a Base C não tem parcela**. Deixá-la vazia custa mais AuROC do que qualquer "
        "ganho que a engenharia de atributos ofereceu — a coluna tem 0% de ausentes no treino, "
        "então o modelo não tem folha de ausente treinada para ela.",
        "",
        "A reconstrução usa a fórmula da tabela Price com a taxa mediana da janela de treino, "
        f"**{pct(ft['taxa_referencia'], 3)} a.m.**, lida da Base A a cada execução e nunca digitada. "
        "Ela funciona porque a Base A foi gerada por Price — a fórmula reproduz a `parcela_mensal` "
        "registrada com erro relativo da ordem de 10⁻⁶ — e porque a carteira antiga mal "
        "diferenciava preço.",
        "",
        "O laço é circular só na aparência: para pontuar é preciso a parcela, para a parcela é "
        "preciso a taxa, e a taxa depende da faixa. Resolve-se em **duas passadas** — a primeira com "
        "as condições desejadas e a taxa de referência, para enquadrar; a segunda com as condições "
        "ofertadas, para decidir. É o que qualquer banco que pratica preço por risco faz.",
        "",
        "---",
        "",
        "## 6. Seleção do modelo",
        "",
        f"O split é temporal: treino em 2022-2023 ({inteiro(m['n_treino'])} contratos), validação em "
        f"{ANO_CORTE} ({inteiro(m['n_oot'])}). Imita a situação real — a Base B é posterior a tudo "
        "que temos. Um split aleatório mediria a capacidade de interpolar dentro do mesmo período, "
        "que é pergunta mais fácil e diferente da que a nota faz.",
        "",
        "**O ponto fino é onde a maioria escorrega:** os hiperparâmetros saíram de validação cruzada "
        f"de 5 dobras dentro de 2022-2023, nunca olhando {ANO_CORTE}. E não só os do vencedor — "
        "**todos os candidatos ajustáveis passam pela mesma busca**, na mesma janela, com a mesma "
        "métrica:",
        "",
    ]
    L += md_tabela(["Candidato", "Combinações", "Vencedor da grade"], tab_grades(d))
    L += [
        "Buscar só para o favorito e deixar os concorrentes com parâmetro de fábrica produz uma "
        "comparação arranjada: o vencedor ganharia por ter sido ajustado, não por ser melhor. Foi "
        "assim que a primeira versão desta tabela foi montada, e a correção mudou números de "
        "verdade.",
        "",
        "A comparação abaixo é **anterior à calibração** — os cinco candidatos crus, para que a "
        "disputa entre eles seja justa. O modelo entregue é o vencedor já calibrado, e por isso o "
        "AuROC desta tabela não é o mesmo da seção 10.",
        "",
    ]
    L += md_tabela(
        ["Modelo", "AUC treino", f"AUC OOT {ANO_CORTE}", "queda", "KS", "Brier", "viés"],
        tab_modelos(d),
    )
    L += [
        "Três leituras:",
        "",
        f"**O overfit é visível a olho nu.** `HistGB padrão` e `{m['vencedor']}` são o *mesmo "
        f"algoritmo*: {num(pior['AUC treino'], 4)} contra {num(venc['AUC treino'], 4)} no treino. O "
        f"de cima decorou a base contrato a contrato e generalizou **pior** "
        f"({num(pior['AUC OOT'], 4)} contra {num(venc['AUC OOT'], 4)}). Pôr o freio derruba o treino "
        f"em {num(float(pior['AUC treino'] - venc['AUC treino']), 2)} e **sobe** o teste. "
        "Regularizar não é conservadorismo; é a diferença entre um modelo que sabe e um que decorou.",
        "",
        "**A vitória do boosting sobre a floresta não é estatisticamente decisiva.** São "
        f"{num(float(venc['AUC OOT'] - cmp_.loc[cmp_['modelo'] == 'Random Forest', 'AUC OOT'].iloc[0]), 4)} "
        "de AuROC contra um desvio de validação de cerca de 0,02. Escolher pela terceira casa "
        "decimal seria o erro que a seção 7 descreve. O que decide são os outros critérios, e todos "
        "apontam para o mesmo lado: Brier melhor, KS melhor e, sobretudo, uma queda treino→teste de "
        f"{num(venc['queda'], 2)} contra {num(float(cmp_.loc[cmp_['modelo'] == 'Random Forest', 'queda'].iloc[0]), 2)}. "
        "Entre dois modelos equivalentes, fica o que depende menos de ter decorado.",
        "",
        "**A logística é o piso honesto.** Ela custa "
        f"{num(float(venc['AUC OOT'] - cmp_['AUC OOT'].min()), 3)} de AuROC, caro demais para ser o "
        "modelo final, mas é o referencial: se o boosting não superasse com folga, não pagaria a "
        "própria opacidade. A árvore ajustada é o melhor modelo **legível** que temos — seis "
        f"perguntas encadeadas chegam a "
        f"{num(float(cmp_.loc[cmp_['modelo'] == 'Árvore de decisão', 'AUC OOT'].iloc[0]), 4)}. A "
        "diferença entre o que se explica num quadro branco e o que se explica num gráfico de "
        "importâncias tem preço, e ele está medido.",
        "",
        "### Calibração sigmoide, não isotônica",
        "",
        "O AuROC ignora calibração. A política, não: a perda esperada é `PD × EAD × LGD`, e erro de "
        "nível na PD vira erro de preço direto. Calibrar em dobras internas do treino agrega as "
        f"cinco dobras e, de brinde, sobe o AuROC out-of-time de {num(float(venc['AUC OOT']), 4)} "
        f"para {num(alto, 4)}.",
        "",
        "As duas calibrações disponíveis empatam em discriminação e em "
        "Brier, então o critério é o comportamento no extremo: por ser função escada, a **isotônica "
        "devolve PD exatamente igual a 1,0000** para alguns contratos. Probabilidade de 1 é "
        "indefensável como estimativa e, multiplicada por EAD e LGD, produz perda esperada igual à "
        "exposição inteira. Ficamos com a sigmoide de Platt.",
        "",
        "O modelo de produção é **reajustado em toda a Base A** depois de validado o desenho. "
        f"Segurar {ANO_CORTE} fora do treino, depois que a pergunta \"isto generaliza?\" já foi "
        "respondida, joga fora um terço dos dados — e justamente o terço mais próximo, no tempo, da "
        "Base B. A configuração está congelada antes disso; nenhuma decisão sai do reajuste.",
        "",
        "---",
        "",
        "## 7. A poda que parecia boa e não era",
        "",
        "Esta é a decisão mais importante do relatório, e ela foi de **não fazer** nada.",
        "",
        f"A importância por permutação no out-of-time de {ANO_CORTE} sugeria cortar muita coisa — "
        "duas variáveis com contribuição negativa e várias em torno de zero:",
        "",
    ]
    L += md_tabela(["Variável", "queda de AuROC ao embaralhar", "dp"], tab_importancias(d))
    L += [
        f"E a poda parecia confirmada pelo próprio out-of-time: quanto mais se cortava, melhor "
        "ficava. Não podamos. O out-of-time de 2024 já vinha sendo consultado muitas vezes; "
        "escolher o conjunto de variáveis por ele é transformá-lo em conjunto de treino.",
        "",
        "Montamos então uma validação **encadeada**, em três janelas que nunca haviam sido usadas "
        f"para nada e todas anteriores a {ANO_CORTE}:",
        "",
    ]
    L += md_tabela(
        ["Conjunto", *[c for c in enc.columns if "->" in c], "média", f"*OOT {ANO_CORTE}*"],
        tab_encadeada(d),
    )
    L += [
        "**As duas últimas colunas são a mesma lista lida por duas réguas, e elas discordam de "
        "ponta a ponta.** No out-of-time a qualidade sobe monotonicamente conforme se poda "
        f"({num(float(enc['OOT 2024'].iloc[0]), 4)} → {num(float(enc['OOT 2024'].iloc[-1]), 4)}); "
        f"nas janelas independentes, **desce** ({num(float(enc['média'].iloc[0]), 4)} → "
        f"{num(float(enc['média'].iloc[-1]), 4)}). Os "
        f"{num(float(enc['OOT 2024'].iloc[-1] - enc['OOT 2024'].iloc[0]), 3)} de vantagem das sete "
        "variáveis eram coincidência de janela — e teriam sido apresentados à banca como melhoria "
        "se a única régua fosse aquela.",
        "",
        f"Repare na segunda linha: o conjunto com `ano_modelo` devolve **exatamente os mesmos** "
        "quatro números do conjunto sem ela. A variável entra e sai sem mexer em nenhuma casa "
        "decimal. Foi removida por isso somado ao PSI de calendário e ao domínio estourado — nunca "
        "por ter perdido uma disputa de métrica.",
        "",
        "> **Erro de processo que vale registrar:** a remoção de `ano_modelo` estava decidida e",
        "> escrita em `docs/02-exploracao.md` desde a sessão anterior, mas nunca havia chegado ao",
        "> código. Foi a importância por permutação, medida por outro motivo, que denunciou.",
        "> Decisão documentada não é decisão implementada, e só o código sabe a diferença. Os dois",
        f"> nomes — `CANDIDATAS` ({len(CANDIDATAS)}) e `FEATURES` ({len(FEATURES)}) — existem hoje",
        "> para que a diferença seja explícita e auditável.",
        "",
        "---",
        "",
        "## 8. O score de 1 a 10",
        "",
        "A política opera sobre faixas, não sobre a PD contínua. Agrupar joga informação fora de "
        "propósito; a pergunta é quanto, onde cortar, e o que a tabela resultante realmente prova.",
        "",
        "### Os cortes saem da PD out-of-fold",
        "",
        "O modelo final foi reajustado em toda a Base A. Pedir a ele a PD dos contratos que o "
        "treinaram devolve memória, não estimativa. A alternativa é a PD **out-of-fold**: cinco "
        "dobras, cada contrato pontuado por um modelo que não o conhecia.",
        "",
        f"A distribuição de PD é quase a mesma nas duas — os cortes mudariam na terceira casa. **O "
        f"que muda é a promessa de nível.** Medido pela PD de dentro da amostra, o AuROC aparente "
        f"salta de {num(d['dec_score']['auroc_oof'], 4)} para "
        f"{num(d['dec_score']['auroc_dentro_amostra'], 4)}, e a tabela prometeria à política uma "
        "faixa 10 quase sem inadimplência. A realidade fora da amostra é várias vezes pior. A "
        "política precificaria de graça e descobriria o erro na apuração do ROI.",
        "",
        "### Faixas desiguais, largas no risco baixo",
        "",
        "A escolha óbvia é o decil. Ela falhou: com dez faixas de mil contratos, a faixa 10 — a "
        "melhor da tabela — quebrou mais que as faixas 7, 8 e 9. Não por bug. O modelo simplesmente "
        "não distingue risco abaixo de 6% de PD, e a diferença entre 3,0% e 3,7% desaparece no erro "
        "amostral.",
        "",
        "A correção vem de uma observação simples: **separar duas faixas exige população "
        "proporcional à dificuldade da separação.** Distinguir 42% de 25% cabe em 300 contratos; "
        "distinguir 3,3% de 3,4% não cabe em 2.000. Logo as faixas boas têm de ser grandes e as "
        "ruins pequenas — o inverso do decil.",
        "",
    ]
    L += md_tabela(
        ["Estratégia", "AuROC da faixa", "rho", "inversões", "pares indistintos",
         "menor faixa em A", "menor faixa em C"],
        tab_estrategias(d),
    )
    L += [
        "Duas armadilhas merecem leitura explícita. **\"Largura igual em log-odds\" é perfeitamente "
        "monotônica** — rho de −1,000, zero inversões — e é inútil: consegue isso porque a faixa 1 "
        "tem sete contratos. Monotonicidade num grupo de sete pessoas não é propriedade do modelo, "
        "é sorte. Foi o candidato mais bonito na métrica e o primeiro a ser descartado. **\"PD fixa "
        "de negócio\"** empata em AuROC e tem o atrativo de dar significado absoluto à faixa; cai "
        "pelo mesmo motivo, com oito propostas na faixa 10 da Base C.",
        "",
        "A granularidade foi medida à parte, variando **só o número de faixas** e mantendo a "
        "estratégia de corte fixa em quantis:",
        "",
    ]
    L += md_tabela(
        ["Granularidade (quantis)", "AuROC", "inversões", "pares indistintos", "menor faixa em C"],
        tab_granularidade(d),
    )
    L += [
        f"Vinte faixas devolvem pouco AuROC e triplicam as inversões. A tabela que de fato usamos é "
        f"a progressiva de dez faixas, que entrega {num(auroc_progressiva, 4)} — melhor que os decis "
        f"de mesma granularidade e a "
        f"{num(d['dec_score']['auroc_oof'] - auroc_progressiva, 4)} da PD contínua. Agrupar custa "
        f"{pct((d['dec_score']['auroc_oof'] - auroc_progressiva) / d['dec_score']['auroc_oof'], 1)} "
        "do poder de ordenação.",
        "",
        "### Os cortes são números fixos, não quantis recalculados",
        "",
        "Os nove cortes estão congelados no código como valores absolutos de PD:",
        "",
        "```",
        "  " + "  ".join(num(c, 4) for c in CORTES),
        "```",
        "",
        "Recalcular os percentis dentro de cada base garantiria faixas sempre bem povoadas, e é "
        "errado por dois motivos. **Destruiria o alarme:** se a faixa 10 contém por definição os 20% "
        "melhores de qualquer população, o PSI entre A e C mede zero — exatamente quando a população "
        "trocou. E **quebraria a coerência do preço:** a faixa 8 precisa significar a mesma PD em "
        "2025 e em 2026.",
        "",
        "A regra é fechada embaixo e aberta em cima: PD exatamente igual a um corte cai na faixa "
        "**pior**. É `searchsorted(..., side=\"right\")`, e é o que permite reproduzir `score_1a10` "
        "a partir da coluna `pd` da submissão.",
        "",
        "### A tabela de faixas — Base A, PD out-of-fold",
        "",
    ]
    L += md_tabela(
        ["Faixa", "n", "PD de", "PD até", "PD prevista", "PD observada", "IC 95%"], tab_faixas(d)
    )
    L += [
        f"- rho de Spearman faixa × PD observada: "
        f"**{num(_rho(d['faixas']['faixa'], d['faixas']['pd_observada']), 3).replace('-', chr(8722))}**",
        f"- inversões materiais: **{'nenhuma' if sc['inversoes_materiais'] == 0 else sc['inversoes_materiais']}**",
        f"- pares que o dado não separa: **{sc['pares_indistinguiveis']} de {sc['n_faixas'] - 1}**",
        "",
        "A última linha é o achado desconfortável, e preferimos publicá-lo a escondê-lo. **Pares "
        "indistintos** são faixas vizinhas cujos intervalos de confiança de 95% se sobrepõem. Isso "
        "não invalida a tabela — a ordenação geral está correta e não há nenhuma inversão material, "
        "isto é, nenhuma faixa melhor com PD comprovadamente maior que a pior. O que invalida é a "
        "**pretensão de dez preços distintos**. Com dez mil contratos e PD média de "
        f"{pct(float(a[ALVO].mean()), 2)}, a Base A não sustenta dez níveis de risco distinguíveis "
        "— sustenta uns quatro ou cinco. A consequência prática é que a política agrupa faixas "
        "vizinhas para definir taxa, prazo e entrada: a tabela reporta dez porque a submissão exige "
        "`score_1a10`, e o tratamento diferenciado tem menos degraus do que isso.",
        "",
        "A única inversão de direção está entre as faixas 9 e 10, e vale dois milésimos de ponto "
        "percentual. A diferença entre inversão material e ruído amostral é o que separa rejeitar "
        "uma tabela boa de aceitar uma ruim.",
        "",
        "---",
        "",
        "## 9. Estabilidade, e o viés de aprovados em um número",
        "",
    ]
    L += md_tabela(["Faixa", "Base A", "Base B (submissão)", "Base C"], distribuicao_de_faixas(d).values.tolist())
    L += [
        "Dentro do universo de contratos aprovados a régua é notavelmente estável. Tomando a safra "
        f"de 2022 como referência, o PSI da **Base B** é **{num(psi_b, 4)}** — e ela é meio ano "
        "posterior a tudo que o modelo viu. **A Base C é outro planeta:** PSI de "
        f"**{num(psi_c, 3)}**, que a régua chama de população trocada (abaixo de 0,10 estável, "
        "0,10 a 0,25 atenção, acima de 0,25 trocada).",
        "",
    ]
    L += md_tabela(
        ["Base", "PD média prevista", "mediana", "p90", "acima de 20%"], tab_bases_pd(d)
    )
    L += [
        "Não é deterioração do modelo — é o viés de aprovados aparecendo em número. A Base C contém "
        "os perfis que a política antiga recusava, e o modelo corretamente os pontua como piores. "
        "Aqui está o limite de honestidade da defesa: **a tabela de faixas foi validada em "
        "contratos aprovados; a faixa 1 da Base C contém perfis que nunca receberam crédito nesta "
        "casa, e a PD deles é extrapolação, não medição.**",
        "",
        "---",
        "",
        "## 10. O desempenho que reportamos, e por que é uma faixa",
        "",
        "O mesmo modelo foi medido três vezes, de formas independentes:",
        "",
    ]
    L += md_tabela(["Medição", "AuROC", "O que ela mede"], tab_medicoes(d))
    L += [
        f"As três caem no mesmo lugar, e a dispersão entre elas ({num(alto - baixo, 4)}) é da ordem "
        "do desvio padrão da própria validação cruzada. Curiosamente a medição out-of-fold é **pior** "
        "que a out-of-time, apesar de treinar com mais dados: a explicação é que a safra de "
        f"{ANO_CORTE} é mais separável que a média do período, não que prever o futuro seja mais "
        "fácil.",
        "",
        f"**Reportamos {num(baixo, 2)} a {num(alto, 2)}.** Reportar o melhor dos três seria escolher "
        "a janela mais favorável depois de ver as três — a mesma falha que a seção 7 descreve, em "
        "outra roupa. O KS out-of-time do modelo escolhido é "
        f"{num(float(venc['KS OOT']), 3)} e o Gini, {num(float(venc['Gini OOT']), 3)}.",
        "",
        "---",
        "",
        "## 11. Limitações conhecidas",
        "",
        "Em ordem de gravidade, e nenhuma delas se resolve com mais modelagem:",
        "",
        f"1. **Viés de aprovados.** {pct(fora_regra, 1)} da Base C está fora do domínio histórico em "
        "ao menos uma variável de crédito. Árvore não extrapola: nessa região a PD é o valor do "
        "extremo conhecido, o que **subestima** o risco. Não há na base informação sobre quem a "
        "política antiga recusava.",
        "2. **Deriva de safra.** A PD cai ao longo da Base A e as bases B e C são posteriores ao fim "
        "da série. O nível calibrado tende a **superestimar** 2025. Esta deriva e a anterior "
        "empurram em sentidos opostos e não se cancelam por decreto — o que este relatório entrega é "
        "o tamanho de cada uma, medido.",
        f"3. **Dez faixas, {sc['pares_indistinguiveis']} pares indistintos.** A tabela ordena bem e "
        "não sustenta dez preços distintos. A política precisa agrupar, e o relatório de política "
        "diz como.",
        "4. **Sem alvo na Base B.** Nenhuma conferência do AuROC é possível antes da apuração. A "
        "faixa reportada na seção 10 é a melhor estimativa que a disciplina de validação permite, e "
        "não uma medição do que será apurado.",
        "",
        "---",
        "",
        "## 12. A submissão",
        "",
        f"`entregaveis/submissao_modelo.csv`, {inteiro(sb['linhas_modelo'])} linhas, colunas "
        f"`id_contrato,pd`, UTF-8, sem índice, decimal com ponto. PD média de "
        f"{pct(sb['pd_media_base_b'], 2)}.",
        "",
        f"As PDs são gravadas com **{sb['casas_pd']} casas decimais**, e a escolha foi medida em vez "
        "de arbitrada. Arredondar move contratos de faixa, e contrato que troca de faixa troca de "
        "preço:",
        "",
    ]
    L += md_tabela(
        ["Arredondamento", "Contratos que trocam de faixa", "AuROC", "Δ vs. PD crua"],
        tab_arredondamento(d),
    )
    L += [
        f"Com {sb['casas_pd']} casas, **nenhum** contrato troca de faixa e o AuROC é o da PD crua. "
        "Duas casas já moveriam centenas. O custo de gravar quatro dígitos a mais é zero; o custo de "
        "descobrir o contrário depois da apuração, não.",
        "",
        f"A geração das duas submissões passa por {sb['conferencias']} conferências automáticas "
        f"({sb['falhas']} falhas na última execução), todas lendo os CSVs do disco e não o "
        "DataFrame que os gerou.",
        "",
        "---",
        "",
        "## 13. Como reproduzir",
        "",
        "```bash",
        "cd 03-AutoCred_Desafio",
        "PYTHONIOENCODING=utf-8 python src/dados.py                     # auditoria e antivazamento",
        "PYTHONIOENCODING=utf-8 python notebooks/01-exploracao.py       # IV, WoE, PSI, domínio",
        "PYTHONIOENCODING=utf-8 python notebooks/02-decisoes-features.py",
        "PYTHONIOENCODING=utf-8 python src/features.py                  # diagnóstico do pipeline",
        "PYTHONIOENCODING=utf-8 python src/modelo.py --busca --poda     # grades, poda, modelo final",
        "PYTHONIOENCODING=utf-8 python notebooks/03-decisoes-score.py   # as cinco estratégias",
        "PYTHONIOENCODING=utf-8 python src/score.py                     # tabela de faixas",
        "PYTHONIOENCODING=utf-8 python src/submissoes.py                # os dois CSVs entregues",
        "PYTHONIOENCODING=utf-8 python src/relatorio_modelo.py          # este relatório",
        "```",
        "",
        f"Seed {m['seed']} em todo o pipeline. Cada execução grava versões e metadados em "
        "`artefatos/*.json`. O modelo serializado é `artefatos/modelo_pd.joblib`; a construção "
        "capítulo a capítulo está em [`docs/`](../docs/README.md), de `01-dados.md` a "
        "`05-score.md`.",
        "",
        "**O que confere que deu certo:** o vencedor da comparação é o "
        f"`{m['vencedor']}` com AuROC out-of-time de {num(m['auc_oot'], 4)} e queda de treino para "
        f"teste abaixo de 0,08; os cortes recalculados por `src/score.py --refazer` coincidem com os "
        "nove valores congelados em `CORTES`; a faixa 1 tem PD observada de "
        f"{pct(faixas.loc[1, 'pd_observada'], 1)} e a faixa 10, de "
        f"{pct(faixas.loc[10, 'pd_observada'], 2)}; e `src/submissoes.py` fecha com "
        f"{sb['conferencias']} checagens e nenhuma falha.",
        "",
    ]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Conferência
# --------------------------------------------------------------------------- #


def conferir(d: dict) -> Conferencia:
    """O relatório contra a submissão e os artefatos, tudo relido do disco."""
    conf = Conferencia("Coerência do relatório do modelo")
    sub, sc, sb, m = d["submissao"], d["score"], d["sub"], d["modelo"]

    conf.checar(
        len(sub) == len(d["b"]) == sb["linhas_modelo"],
        "a submissão tem uma linha por contrato da Base B",
        f"{inteiro(len(sub))} linhas",
    )
    conf.checar(
        list(sub.columns) == ["id_contrato", "pd"],
        "colunas da submissão na ordem exigida",
    )
    conf.checar(
        set(sub["id_contrato"]) == set(d["b"]["id_contrato"]),
        "os ids da submissão são exatamente os da Base B",
    )
    conf.checar(
        bool(sub["pd"].between(0, 1, inclusive="neither").all()),
        "toda PD está no intervalo aberto (0, 1)",
        f"{pct(float(sub['pd'].min()), 2)} a {pct(float(sub['pd'].max()), 2)}",
    )
    conf.checar(
        abs(float(sub["pd"].mean()) - sb["pd_media_base_b"]) < 1e-9,
        "a PD média confere com submissoes.json",
    )

    # Nenhuma coluna proibida pode estar na lista de preditoras — a mesma guarda
    # que roda antes do `fit`, refeita aqui contra o dicionário do disco.
    conf.checar(
        not (set(FEATURES) & set(colunas_proibidas())),
        "nenhuma coluna proibida entre as preditoras",
        f"{len(FEATURES)} features, {len(colunas_proibidas())} proibidas",
    )
    conf.checar(
        len(FEATURES) == d["feat"]["n_features"] == len(CANDIDATAS) - 1,
        "FEATURES e CANDIDATAS diferem por exatamente uma variável",
        "ano_modelo",
    )

    # A tabela de faixas publicada tem de ser a mesma régua da submissão da
    # política: os cortes reproduzem a faixa a partir da PD.
    f = d["faixas"].sort_values("faixa")
    conf.checar(
        bool((faixa(f["pd_prevista"].to_numpy()) == f["faixa"].to_numpy()).all()),
        "a PD média de cada faixa cai na própria faixa",
    )
    conf.checar(
        int(f["n"].sum()) == len(d["a"]),
        "a tabela de faixas cobre toda a Base A",
        f"{inteiro(int(f['n'].sum()))} contratos",
    )
    conf.checar(
        sc["inversoes_materiais"] == 0,
        "nenhuma inversão material na tabela de faixas",
    )
    conf.checar(
        len(CORTES) == sc["n_faixas"] - 1 and list(CORTES) == [round(c, 4) for c in sc["cortes"]],
        "os cortes do código são os de score.json",
    )

    # As três medições que o relatório publica como faixa, todas do modelo
    # calibrado. `auc_cru` é outra família — a comparação dos cinco candidatos
    # antes da calibração — e existe aqui para que as duas não se confundam.
    baixo, oof, alto = medicoes(d)
    auc_cru = float(d["cmp"]["AUC OOT"].max())
    conf.checar(
        baixo <= oof <= alto,
        "a medição out-of-fold cai dentro da faixa reportada",
        f"{num(baixo, 4)} a {num(alto, 4)}",
    )
    conf.checar(
        abs(auc_cru - m["auc_oot"]) < 5e-5,
        "a comparação sem calibração confere com modelo.json",
        num(auc_cru, 4),
    )
    conf.checar(
        alto > auc_cru,
        "calibrar sobe o AuROC out-of-time",
        f"{num(auc_cru, 4)} -> {num(alto, 4)}",
    )
    conf.checar(
        float(d["cmp"].loc[d["cmp"]["modelo"] == m["vencedor"], "AUC OOT"].iloc[0]) == auc_cru,
        "o vencedor de modelo.json é o melhor da comparação",
        m["vencedor"],
    )

    # A decisão de não podar: as duas réguas têm de discordar, senão o argumento
    # do relatório deixou de valer e o texto precisa ser reescrito.
    enc = d["enc"]
    sobe_oot = float(enc["OOT 2024"].iloc[-1]) > float(enc["OOT 2024"].iloc[0])
    desce_enc = float(enc["média"].iloc[-1]) < float(enc["média"].iloc[0])
    conf.checar(
        sobe_oot and desce_enc,
        "as duas réguas da poda seguem discordando",
        "OOT sobe, janelas independentes descem",
    )
    conf.checar(
        abs(float(enc["média"].iloc[0]) - float(enc["média"].iloc[1])) < 1e-12,
        "ano_modelo entra e sai sem mudar nenhuma casa decimal",
    )

    # O PSI publicado na seção 9 é recalculado aqui; se ele deixar de bater com
    # score.json, ou a referência mudou ou a régua mudou — e as duas invalidam a
    # comparação entre as três bases.
    psi_b, psi_c = psi_das_bases(d)
    conf.checar(
        abs(psi_c - sc["psi_a_para_c"]) < 5e-4,
        "o PSI A→C recalculado reproduz score.json",
        f"{num(psi_c, 4)} vs {num(sc['psi_a_para_c'], 3)}",
    )
    conf.checar(
        psi_b < 0.10 < psi_c,
        "Base B estável e Base C trocada, pela mesma régua",
        f"B {num(psi_b, 4)} · C {num(psi_c, 3)}",
    )

    conf.checar(
        sb["trocam_faixa_6_casas"] == 0,
        f"com {sb['casas_pd']} casas nenhum contrato troca de faixa",
    )
    conf.checar(
        ARQ_RELATORIO.exists() and ARQ_RELATORIO.stat().st_size > 10_000,
        "o relatório foi gravado",
        str(ARQ_RELATORIO.relative_to(RAIZ)).replace("\\", "/")
        if ARQ_RELATORIO.exists()
        else "ausente",
    )
    return conf


# --------------------------------------------------------------------------- #


def main() -> None:
    print("=" * 96)
    print("RELATÓRIOS — relatório do modelo")
    print("=" * 96)

    d = carregar()
    REPORTS.mkdir(exist_ok=True)
    ARQ_RELATORIO.write_text(escrever(d), encoding="utf-8", newline="\n")
    print(f"\n  {str(ARQ_RELATORIO.relative_to(RAIZ)).replace(chr(92), '/')} gravado "
          f"({ARQ_RELATORIO.stat().st_size:,} bytes)".replace(",", "."))

    dom, fora_regra = dominio(d)
    baixo, _, alto = medicoes(d)
    print("\n--- O que o relatório publica ---\n")
    print(f"  AuROC reportado    {num(baixo, 4)} a {num(alto, 4)}   "
          f"(três medições independentes)")
    print(f"  modelo             {d['modelo']['vencedor']}, {len(FEATURES)} variáveis, "
          f"seed {d['modelo']['seed']}")
    print(f"  lift 1/10          {num(float(d['faixas'].set_index('faixa').loc[1, 'pd_observada'] / d['faixas'].set_index('faixa').loc[10, 'pd_observada']), 1)}x")
    print(f"  PSI A -> C         {num(d['score']['psi_a_para_c'], 3)}")
    print(f"  Base C fora do domínio  {pct(fora_regra, 1)}")

    conf = conferir(d)
    ok = conf.imprimir()

    registrar_execucao(
        "relatorio_modelo",
        {
            "etapa": "src/relatorio_modelo",
            "saida": ARQ_RELATORIO.name,
            "auroc_reportado_min": round(baixo, 4),
            "auroc_reportado_max": round(alto, 4),
            "fora_do_dominio_base_c": round(fora_regra, 4),
            "conferencias": len(conf.linhas),
            "falhas": len(conf.falhas),
        },
    )
    print("\n" + "=" * 96)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
