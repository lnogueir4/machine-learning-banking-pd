"""As decisões do agrupamento em faixas 1-10, com a evidência que as sustenta.

Toda tabela de `docs/05-score.md` sai daqui. A PD contínua do modelo não é o
entregável da política: o desafio exige decidir por **faixa de score de 1 a 10**
(1 = pior risco, 10 = melhor), e o agrupamento é decisão do grupo. Agrupar joga
informação fora de propósito — a pergunta é quanto, e em troca do quê.

  1. A PD que define os cortes é a de dentro da amostra ou a out-of-fold?
  2. Como cortar: quantis, largura igual em log-odds, PD fixa de negócio?
  3. Quantas faixas? 5, 10 ou 20 — quanto custa cada granularidade.
  4. As faixas são estáveis no tempo e da Base A para a Base C?
  5. Qual PD representa a faixa na hora de precificar?

Uso:
    PYTHONIOENCODING=utf-8 python notebooks/03-decisoes-score.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_predict  # noqa: E402

from dados import (  # noqa: E402
    ALVO,
    SEED,
    carregar_base_a,
    carregar_base_b,
    carregar_base_c,
    registrar_execucao,
)
from exploracao import monotonicidade, pd_com_ic, psi, veredito_monotonicidade  # noqa: E402
from features import matriz, montar_pipeline, preparar_aplicacao  # noqa: E402
from modelo import MELHORES  # noqa: E402

CV = StratifiedKFold(5, shuffle=True, random_state=SEED)

# Estratégia de corte vencedora da seção 2. Fica isolada aqui porque as seções 4
# e 5 mostram a tabela escolhida — trocar a escolha é trocar esta linha, e o
# resto do script continua sendo a comparação imparcial que a sustenta.
ESCOLHIDA = "progressiva"


# --------------------------------------------------------------------------- #
# A PD que define os cortes
# --------------------------------------------------------------------------- #


def _modelo():
    estimador = HistGradientBoostingClassifier(
        random_state=SEED, **{k.replace("modelo__", ""): v for k, v in MELHORES.items()}
    )
    return CalibratedClassifierCV(montar_pipeline(estimador), method="sigmoid", cv=5)


def pd_out_of_fold(a: pd.DataFrame) -> np.ndarray:
    """PD de cada contrato da Base A prevista por um modelo que não o viu.

    São 25 ajustes (5 dobras externas x 5 internas da calibração). É o preço de
    ter, para cada linha, uma previsão com o mesmo grau de ignorância que a
    Base B receberá.
    """
    return cross_val_predict(
        _modelo(), matriz(a), a[ALVO], cv=CV, method="predict_proba", n_jobs=-1
    )[:, 1]


def pd_dentro_da_amostra(a: pd.DataFrame) -> np.ndarray:
    """PD prevista pelo modelo final para as mesmas linhas que o treinaram."""
    return _modelo().fit(matriz(a), a[ALVO]).predict_proba(matriz(a))[:, 1]


# --------------------------------------------------------------------------- #
# Estratégias de corte
# --------------------------------------------------------------------------- #


def cortes_quantis(p: np.ndarray, n: int = 10) -> np.ndarray:
    """Faixas de mesmo tamanho na base de desenvolvimento."""
    return np.quantile(p, np.linspace(0, 1, n + 1)[1:-1])


def cortes_logodds(p: np.ndarray, n: int = 10) -> np.ndarray:
    """Largura igual na escala de log-odds — a escala em que o modelo soma."""
    lo = np.log(p / (1 - p))
    pontos = np.linspace(lo.min(), lo.max(), n + 1)[1:-1]
    return 1 / (1 + np.exp(-pontos))


def cortes_caudas_finas(p: np.ndarray) -> np.ndarray:
    """Faixas desiguais: finas nos extremos, largas no miolo.

    É o desenho clássico de tabela de score em banco — a granularidade vai para
    onde a decisão muda, e o miolo, que recebe o mesmo tratamento, fica largo.
    """
    return np.quantile(p, [0.05, 0.15, 0.30, 0.50, 0.68, 0.82, 0.90, 0.95, 0.98])


def cortes_progressivos(p: np.ndarray) -> np.ndarray:
    """Faixas largas no risco baixo, estreitas no risco alto.

    A régua não é estética: é onde o dado consegue distinguir. Separar duas
    faixas de PD ~3% exige muita gente (a diferença entre 3,0% e 3,7% some no
    erro amostral de 1.000 contratos); separar 30% de 13% exige pouca. Massa vai
    para o lado bom, granularidade para o lado ruim.
    """
    return np.quantile(p, [0.20, 0.36, 0.50, 0.62, 0.72, 0.80, 0.87, 0.93, 0.97])


CORTES_NEGOCIO = np.array([0.020, 0.030, 0.040, 0.055, 0.075, 0.100, 0.140, 0.200, 0.300])


def faixa(p, cortes) -> np.ndarray:
    """PD contínua -> faixa 1-10, com **1 = pior risco**.

    `searchsorted` devolve 0 para a PD mais baixa; a subtração inverte, de modo
    que a menor PD vira a faixa mais alta. A inversão é explícita aqui e em
    lugar nenhum mais: score invertido é o erro silencioso mais caro desta etapa.
    """
    pos = np.searchsorted(np.asarray(cortes), np.asarray(p), side="right")
    return (len(cortes) + 1) - pos


# --------------------------------------------------------------------------- #
# Avaliação de uma estratégia
# --------------------------------------------------------------------------- #


def tabela(p, y, cortes) -> pd.DataFrame:
    f = faixa(p, cortes)
    d = pd.DataFrame({"faixa": f, "p": np.asarray(p), "y": np.asarray(y)})
    t = d.groupby("faixa").agg(n=("y", "size"), prevista=("p", "mean"), pd=("y", "mean"))
    return t.reindex(range(1, len(cortes) + 2)).sort_index()


def pares_indistinguiveis(t: pd.DataFrame) -> int:
    """Quantos pares de faixas vizinhas o dado **não** separa.

    Duas faixas contíguas só são faixas diferentes se a PD observada de uma
    estiver fora do intervalo de confiança de 95% da outra. Faixa que existe na
    tabela mas não existe na estatística é decoração: precifica diferente um
    risco que é o mesmo, e a diferença desaparece na safra seguinte.
    """
    ic = pd_com_ic(t.dropna(subset=["pd"]).rename(columns={"pd": "pd"}))
    indices = list(ic.index)
    return sum(
        1
        for k, prox in zip(indices, indices[1:])
        if not ic.loc[k, "ic_lo"] > ic.loc[prox, "ic_hi"]
    )


def avaliar(nome, p_a, y_a, p_c, cortes) -> dict:
    t = tabela(p_a, y_a, cortes)
    rho, inv = monotonicidade(t.dropna(subset=["pd"]))
    f_a, f_c = faixa(p_a, cortes), faixa(p_c, cortes)
    vivas = t["n"].dropna()
    n_c = pd.Series(f_c).value_counts().reindex(range(1, len(cortes) + 2)).fillna(0)
    return {
        "estratégia": nome,
        "faixas": int((vivas > 0).sum()),
        "AuROC faixa": roc_auc_score(y_a, -f_a),
        "rho": rho,
        "inversões": inv,
        "veredito": veredito_monotonicidade(rho, inv),
        "pares indistintos": pares_indistinguiveis(t),
        "PD f1": t.loc[1, "pd"],
        "PD f10": t.loc[len(cortes) + 1, "pd"],
        "lift": t.loc[1, "pd"] / max(t.loc[len(cortes) + 1, "pd"], 1e-9),
        "menor faixa em A": int(vivas.min()),
        "menor faixa em C": int(n_c.min()),
        "PSI A->C": psi(pd.Series(f_a), pd.Series(f_c), None, True),
    }


# --------------------------------------------------------------------------- #
# Seções
# --------------------------------------------------------------------------- #


def secao_1_oof(p_oof, p_ins, y) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A PD de dentro da amostra move pouco os cortes e muito a tabela.

    Os percentis quase coincidem — o modelo é regularizado e a calibração média
    cinco dobras, então a *distribuição* de PD não infla. O que infla é a
    **atribuição**: com a PD de dentro da amostra, cada contrato tende a cair na
    faixa que o próprio alvo dele ajudou a definir, e a separação entre extremos
    aparece maior do que será na Base B.
    """
    q = np.linspace(0, 1, 11)[1:-1]
    cortes_tab = pd.DataFrame(
        {
            "percentil": [f"p{int(v * 100)}" for v in q],
            "PD out-of-fold": np.quantile(p_oof, q),
            "PD dentro da amostra": np.quantile(p_ins, q),
            "razão": np.quantile(p_ins, q) / np.quantile(p_oof, q),
        }
    )
    linhas = []
    for rotulo, p in [("out-of-fold", p_oof), ("dentro da amostra", p_ins)]:
        t = tabela(p, y, cortes_quantis(p))
        linhas.append(
            {
                "PD usada": rotulo,
                "AuROC": roc_auc_score(y, p),
                "PD obs. faixa 1": t.loc[1, "pd"],
                "PD obs. faixa 10": t.loc[10, "pd"],
                "lift 1/10": t.loc[1, "pd"] / t.loc[10, "pd"],
                "pares indistintos": pares_indistinguiveis(t),
            }
        )
    return cortes_tab, pd.DataFrame(linhas)


def estrategias(p_oof) -> dict[str, np.ndarray]:
    return {
        "quantis (decis)": cortes_quantis(p_oof),
        "largura igual em log-odds": cortes_logodds(p_oof),
        "caudas finas": cortes_caudas_finas(p_oof),
        "progressiva": cortes_progressivos(p_oof),
        "PD fixa de negócio": CORTES_NEGOCIO,
    }


def secao_2_estrategias(p_oof, y, p_c) -> pd.DataFrame:
    return pd.DataFrame(
        [avaliar(n, p_oof, y, p_c, c) for n, c in estrategias(p_oof).items()]
    )


def secao_3_granularidade(p_oof, y, p_c) -> pd.DataFrame:
    linhas = []
    for n in (5, 10, 20):
        linhas.append(avaliar(f"{n} faixas", p_oof, y, p_c, cortes_quantis(p_oof, n)))
    cont = {
        "estratégia": "PD contínua",
        "faixas": int(len(np.unique(p_oof))),
        "AuROC faixa": roc_auc_score(y, p_oof),
    }
    return pd.DataFrame(linhas + [cont])[
        [
            "estratégia",
            "faixas",
            "AuROC faixa",
            "rho",
            "inversões",
            "pares indistintos",
            "menor faixa em C",
            "PSI A->C",
        ]
    ]


def secao_4_estabilidade(a, p_oof, p_b, p_c, cortes) -> pd.DataFrame:
    f_a = pd.Series(faixa(p_oof, cortes), index=a.index)
    ref = f_a[a["ano"] == 2022]
    linhas = []
    for rotulo, serie in [
        ("Base A 2022 (ref.)", ref),
        ("Base A 2023", f_a[a["ano"] == 2023]),
        ("Base A 2024", f_a[a["ano"] == 2024]),
        ("Base B (2025-S1)", pd.Series(faixa(p_b, cortes))),
        ("Base C (2025-S2)", pd.Series(faixa(p_c, cortes))),
    ]:
        linhas.append(
            {
                "população": rotulo,
                "n": len(serie),
                "faixa média": serie.mean(),
                "% faixas 1-3": float((serie <= 3).mean()),
                "% faixas 8-10": float((serie >= 8).mean()),
                "PSI vs 2022": psi(ref, serie, None, True),
            }
        )
    return pd.DataFrame(linhas)


def secao_5_tabela_final(a, p_oof, p_b, p_c, cortes) -> pd.DataFrame:
    """A tabela de faixas como ela irá para a documentação e para a política."""
    f = faixa(p_oof, cortes)
    d = pd.DataFrame({"faixa": f, "p": p_oof, "y": a[ALVO].to_numpy()})
    t = d.groupby("faixa").agg(n=("y", "size"), prevista=("p", "mean"), pd=("y", "mean"))
    t = pd_com_ic(t).rename(columns={"pd": "observada"})
    t["PD de"] = d.groupby("faixa")["p"].min()
    t["PD até"] = d.groupby("faixa")["p"].max()
    t["% A"] = t["n"] / len(d)
    t["% B"] = pd.Series(faixa(p_b, cortes)).value_counts(normalize=True)
    t["% C"] = pd.Series(faixa(p_c, cortes)).value_counts(normalize=True)
    t["% C acum."] = t.sort_index(ascending=False)["% C"].cumsum()
    return t[
        ["n", "PD de", "PD até", "prevista", "observada", "ic_lo", "ic_hi", "% A", "% B", "% C", "% C acum."]
    ].sort_index()


# --------------------------------------------------------------------------- #


def main() -> None:
    a, b, c = carregar_base_a(), carregar_base_b(), carregar_base_c()
    print("=" * 100)
    print("DECISÕES DO AGRUPAMENTO EM FAIXAS — Desafio AutoCred")
    print("=" * 100)

    print("\ncalculando a PD out-of-fold da Base A (25 ajustes)...", flush=True)
    p_oof = pd_out_of_fold(a)
    p_ins = pd_dentro_da_amostra(a)
    y = a[ALVO].to_numpy()
    modelo_final = _modelo().fit(matriz(a), a[ALVO])
    p_b = modelo_final.predict_proba(matriz(b))[:, 1]
    p_c = modelo_final.predict_proba(matriz(preparar_aplicacao(c)))[:, 1]
    print(
        f"  AuROC out-of-fold na Base A: {roc_auc_score(y, p_oof):.4f} | "
        f"dentro da amostra: {roc_auc_score(y, p_ins):.4f}"
    )

    print("\n### 1. A PD QUE DEFINE OS CORTES: OUT-OF-FOLD OU DENTRO DA AMOSTRA?\n")
    t1_cortes, t1_faixas = secao_1_oof(p_oof, p_ins, y)
    print(
        t1_cortes.round({"PD out-of-fold": 4, "PD dentro da amostra": 4, "razão": 3}).to_string(
            index=False
        )
    )
    print()
    print(
        t1_faixas.round(
            {"AuROC": 4, "PD obs. faixa 1": 4, "PD obs. faixa 10": 4, "lift 1/10": 1}
        ).to_string(index=False)
    )

    print("\n### 2. COMO CORTAR AS FAIXAS\n")
    t2 = secao_2_estrategias(p_oof, y, p_c)
    print(
        t2.round(
            {"AuROC faixa": 4, "rho": 3, "PD f1": 4, "PD f10": 4, "lift": 1, "PSI A->C": 3}
        ).to_string(index=False)
    )

    print("\n  A estratégia descartada, em detalhe — decis, onde a faixa 10 falha:\n")
    t2b = tabela(p_oof, y, cortes_quantis(p_oof))
    print(t2b.round(5).to_string())

    print("\n### 3. QUANTAS FAIXAS\n")
    t3 = secao_3_granularidade(p_oof, y, p_c)
    print(t3.round({"AuROC faixa": 4, "rho": 3, "PSI A->C": 3}).to_string(index=False))

    cortes = estrategias(p_oof)[ESCOLHIDA]
    print(f"\n### 4. ESTABILIDADE DAS FAIXAS NO TEMPO E ENTRE BASES — estratégia '{ESCOLHIDA}'\n")
    t4 = secao_4_estabilidade(a, p_oof, p_b, p_c, cortes)
    print(
        t4.round(
            {"faixa média": 2, "% faixas 1-3": 4, "% faixas 8-10": 4, "PSI vs 2022": 3}
        ).to_string(index=False)
    )

    print(f"\n### 5. A TABELA DE FAIXAS — estratégia '{ESCOLHIDA}'\n")
    t5 = secao_5_tabela_final(a, p_oof, p_b, p_c, cortes)
    print(t5.round(4).to_string())

    print("\n  cortes escolhidos (PD ascendente, 9 pontos):")
    print("  " + ", ".join(f"{v:.6f}" for v in cortes))

    destino = RAIZ / "artefatos" / "decisoes_score.csv"
    pd.concat(
        [t2.assign(secao="estrategias"), t3.assign(secao="granularidade")], ignore_index=True
    ).to_csv(destino, index=False, encoding="utf-8")
    registrar_execucao(
        "decisoes_score",
        {
            "etapa": "notebooks/03-decisoes-score",
            "auroc_oof": round(float(roc_auc_score(y, p_oof)), 4),
            "auroc_dentro_amostra": round(float(roc_auc_score(y, p_ins)), 4),
            "cortes_escolhidos": [round(float(v), 6) for v in cortes],
            "saida": destino.name,
        },
    )
    print(f"\nTabelas gravadas em artefatos/{destino.name}")
    print("=" * 100)


if __name__ == "__main__":
    main()
