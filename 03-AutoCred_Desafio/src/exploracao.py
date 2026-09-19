"""Ferramentas de análise por faixas: binning, WoE, IV, monotonicidade e PSI.

Biblioteca, não script. Vive em `src/` porque é usada em três lugares:

  - `notebooks/01-exploracao.py` e o notebook equivalente (diagnóstico);
  - `score.py`, para agrupar a PD contínua nas faixas de 1 a 10;
  - monitoramento de estabilidade, onde o PSI vira checagem recorrente.

Regra que atravessa o módulo: **todo bin carrega a sua ordem**. Rótulo de faixa
que vira texto perde a ordem em silêncio — `"(1000.0, 1500.0]"` ordena antes de
`"(400.0, 450.0]"` — e a leitura de monotonicidade sai errada sem dar erro.
Por isso `binar` devolve categórica ordenada, nunca string solta.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

N_BINS = 10
AUSENTE = "AUSENTE"

# Régua de IV usada no mercado de crédito. Convenção difundida, não norma — e o
# topo funciona como alarme: IV muito alto costuma ser vazamento, não sorte.
REGUA_IV = [
    (0.02, "inútil"),
    (0.10, "fraco"),
    (0.30, "médio"),
    (0.50, "forte"),
    (float("inf"), "SUSPEITO (verificar vazamento)"),
]

# Convenção de mercado para PSI.
REGUA_PSI = [(0.10, "estável"), (0.25, "atenção"), (float("inf"), "POPULAÇÃO TROCADA")]


def _classificar(valor: float, regua: list[tuple[float, str]]) -> str:
    if pd.isna(valor):
        return "—"
    for limite, rotulo in regua:
        if valor < limite:
            return rotulo
    return "?"


def classificar_iv(iv: float) -> str:
    return _classificar(iv, REGUA_IV)


def classificar_psi(valor: float) -> str:
    return _classificar(valor, REGUA_PSI)


def binar(serie: pd.Series, categorica: bool, cortes=None):
    """Devolve `(bins, cortes)`. Ausentes viram a categoria `AUSENTE`.

    Tratar o faltante como bin em vez de imputá-lo antes é o que permite medir se
    a ausência carrega sinal: basta olhar o WoE do bin `AUSENTE`.

    `cortes` reaproveita o binning de outra amostra — é assim que a safra de
    conferência e a base de aplicação recebem exatamente as faixas do treino.
    """
    if categorica:
        return serie.fillna(AUSENTE).astype(str), None
    if cortes is None:
        # Inteiro de baixa cardinalidade (qtd_restricoes_ativas, prazo_meses) não
        # sobrevive ao corte por quantil: os decis colapsam em 2 ou 3 bins e a
        # monotonicidade fica indefinida. Nesse caso cada valor vira seu bin.
        if serie.dropna().nunique() <= N_BINS:
            cortes = "valores"
        else:
            cortes = np.unique(np.nanquantile(serie.dropna(), np.linspace(0, 1, N_BINS + 1)))
            cortes[0], cortes[-1] = -np.inf, np.inf
    if isinstance(cortes, str):  # binning por valor exato
        ordem = [f"{v:g}" for v in sorted(serie.dropna().unique())]
        rotulos = serie.map(lambda v: f"{v:g}" if pd.notna(v) else AUSENTE)
    else:
        recortada = pd.cut(serie, bins=cortes, duplicates="drop")
        ordem = [str(c) for c in recortada.cat.categories]
        rotulos = recortada.astype(str).where(serie.notna(), AUSENTE)
    return pd.Categorical(rotulos, categories=ordem + [AUSENTE], ordered=True), cortes


def tabela_woe(bins, alvo: pd.Series) -> pd.DataFrame:
    """WoE = ln(%bons / %maus) por bin; IV do bin = (%bons − %maus) × WoE.

    Suavização de 0,5 evita divisão por zero em bin sem nenhum default — o que
    acontece nas faixas de score alto, justamente as mais populosas.
    """
    tab = (
        pd.DataFrame({"bin": bins, "y": np.asarray(alvo)})
        .groupby("bin", observed=True)["y"]
        .agg(n="size", maus="sum")
    )
    tab["bons"] = tab["n"] - tab["maus"]
    tab["pd"] = tab["maus"] / tab["n"]
    p_bons = (tab["bons"] + 0.5) / (tab["bons"].sum() + 0.5 * len(tab))
    p_maus = (tab["maus"] + 0.5) / (tab["maus"].sum() + 0.5 * len(tab))
    tab["woe"] = np.log(p_bons / p_maus)
    tab["iv_bin"] = (p_bons - p_maus) * tab["woe"]
    return tab


def iv(bins, alvo: pd.Series) -> float:
    return float(tabela_woe(bins, alvo)["iv_bin"].sum())


def monotonicidade(tab: pd.DataFrame) -> tuple[float, int]:
    """`(rho de Spearman entre ordem do bin e PD, nº de inversões de direção)`.

    Ignora o bin `AUSENTE`, que não tem posição na ordem natural da variável.
    """
    ordenada = tab.drop(index=AUSENTE, errors="ignore")
    if len(ordenada) < 3:
        return float("nan"), 0
    pds = ordenada["pd"].to_numpy()
    rho = pd.Series(pds).corr(pd.Series(range(len(pds))), method="spearman")
    sinais = np.sign(np.diff(pds))
    sinais = sinais[sinais != 0]
    inversoes = int((np.diff(sinais) != 0).sum()) if len(sinais) > 1 else 0
    return float(rho), inversoes


def veredito_monotonicidade(rho: float, inversoes: int) -> str:
    if pd.isna(rho):
        return "não aplicável"
    if inversoes <= 1 and abs(rho) >= 0.7:
        return "monotônica"
    if inversoes <= 3 and abs(rho) >= 0.5:
        return "aceitável"
    return "NÃO monotônica — agrupar por WoE"


def psi(esperado: pd.Series, observado: pd.Series, cortes, categorica: bool) -> float:
    """Population Stability Index entre duas populações, nos bins do esperado.

    Devolve NaN quando a coluna ainda não existe do lado observado — o caso de
    `comprometimento_renda` na primeira passada da Base C, que só é calculável
    depois que a política define a parcela. Comparar contra 100% de ausentes
    daria um número enorme e sem significado.
    """
    if observado.notna().sum() == 0:
        return float("nan")
    be, _ = binar(esperado, categorica, cortes)
    bo, _ = binar(observado, categorica, cortes)
    de = pd.Series(be).value_counts(normalize=True)
    do = pd.Series(bo).value_counts(normalize=True)
    # Valor observado fora do domínio do treino (uma quantidade de restrições que
    # nunca apareceu na Base A) é agregado ao bin extremo, em vez de virar bin
    # próprio com esperado ~0 — senão o log explode e o PSI passa a medir a
    # granularidade do binning em vez do deslocamento real.
    fora = do.index.difference(de.index)
    if len(fora):
        do.loc[de.index[-1]] = do.reindex(de.index[-1:]).fillna(0).iloc[0] + do[fora].sum()
        do = do.drop(index=fora)
    de = de.reindex(de.index).fillna(0) + 1e-4
    do = do.reindex(de.index).fillna(0) + 1e-4
    return float(((do - de) * np.log(do / de)).sum())


def resumo_variaveis(
    treino: pd.DataFrame,
    conferencia: pd.DataFrame,
    aplicacao: pd.DataFrame,
    features: list[str],
    categoricas: list[str],
    alvo: str,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Tabela-resumo por variável e o dicionário de tabelas de WoE do treino.

    Os cortes saem **sempre** do treino e são reaplicados na conferência e na
    aplicação. Recalcular faixas em cada amostra tornaria IV e PSI incomparáveis.
    """
    linhas, tabelas = [], {}
    for feat in features:
        cat = feat in categoricas
        bins_tr, cortes = binar(treino[feat], cat)
        tab = tabela_woe(bins_tr, treino[alvo])
        tabelas[feat] = tab

        bins_cf, _ = binar(conferencia[feat], cat, cortes)
        rho, inversoes = monotonicidade(tab)
        linhas.append(
            {
                "variável": feat,
                "IV_treino": tab["iv_bin"].sum(),
                "IV_conferencia": iv(bins_cf, conferencia[alvo]),
                "força": classificar_iv(tab["iv_bin"].sum()),
                "rho": rho,
                "inversões": inversoes,
                "monotonicidade": veredito_monotonicidade(rho, inversoes),
                "PSI_aplicacao": psi(treino[feat], aplicacao[feat], cortes, cat),
            }
        )
    resumo = pd.DataFrame(linhas).sort_values("IV_treino", ascending=False).reset_index(drop=True)
    return resumo, tabelas


def pd_com_ic(tab: pd.DataFrame, z: float = 1.96) -> pd.DataFrame:
    """Acrescenta intervalo de confiança normal à PD de cada bin.

    Serve para não confundir irregularidade amostral com achado: uma faixa cuja
    PD parece fora da tendência, mas cujo IC cobre a das vizinhas, não é achado.
    """
    out = tab.copy()
    erro = z * np.sqrt(out["pd"] * (1 - out["pd"]) / out["n"])
    out["ic_lo"] = (out["pd"] - erro).clip(lower=0)
    out["ic_hi"] = (out["pd"] + erro).clip(upper=1)
    return out
