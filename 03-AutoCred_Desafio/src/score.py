"""PD contínua -> faixa de score 1 a 10 — Desafio AutoCred.

A política de crédito não decide sobre a PD contínua: decide sobre **faixas**,
de 1 (pior risco) a 10 (melhor). Agrupar é jogar informação fora de propósito —
custa 0,0029 de AuROC (0,7326 na PD contínua, 0,7297 na faixa). Paga-se isso
para ter uma tabela que cabe num documento de política, que o comitê aprova e
que a submissão reproduz linha a linha.

Três disciplinas que este módulo existe para impor:

  - **Os cortes são números fixos**, congelados abaixo, não quantis recalculados
    em cada base. Recalcular faria a faixa 10 conter sempre 20% de qualquer
    população — e o PSI, que é o alarme de deslocamento, mediria zero por
    construção justamente quando a população troca.
  - **Os cortes saem da PD out-of-fold**, nunca da PD que o modelo prevê para as
    linhas que o treinaram. A diferença aparece na tabela: dentro da amostra a
    faixa 10 promete 0,6% de inadimplência; fora, entrega 3,4%.
  - **Faixa 1 é o pior risco.** A inversão está num único ponto do código, em
    `faixa()`. Score invertido é o erro silencioso mais caro desta etapa: passa
    por toda a política sem erguer exceção e só aparece no ROI final.

Uso:
    PYTHONIOENCODING=utf-8 python src/score.py            # tabela de faixas e testes
    PYTHONIOENCODING=utf-8 python src/score.py --refazer  # recalcula a PD out-of-fold e os cortes
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from dados import (
    ALVO,
    ARTEFATOS,
    SEED,
    carregar_base_a,
    carregar_base_b,
    carregar_base_c,
    registrar_execucao,
)
from exploracao import monotonicidade, pd_com_ic, psi, veredito_monotonicidade
from features import matriz, montar_pipeline, preparar_aplicacao
from modelo import MELHORES

N_FAIXAS = 10
ARQ_PD_A = ARTEFATOS / "pd_base_a.csv"
ARQ_TABELA = ARTEFATOS / "tabela_faixas.csv"

# Percentis da PD out-of-fold que geram os cortes. Desiguais de propósito:
# faixas largas no risco baixo, estreitas no risco alto. Separar 3,0% de 3,7% de
# PD exige muita gente — a diferença cabe dentro do erro amostral de mil
# contratos; separar 42% de 25% exige pouca. Massa vai para o lado bom,
# granularidade para o lado ruim. Ver `docs/05-score.md`, decisão 2.
PERCENTIS = (0.20, 0.36, 0.50, 0.62, 0.72, 0.80, 0.87, 0.93, 0.97)

# Os nove cortes, em PD ascendente, arredondados na quarta casa para que a tabela
# do documento de política seja legível. `--refazer` recalcula e acusa divergência.
CORTES = (0.0369, 0.0448, 0.0542, 0.0663, 0.0839, 0.1067, 0.1428, 0.2096, 0.3017)


# --------------------------------------------------------------------------- #
# A conversão
# --------------------------------------------------------------------------- #


def faixa(pd_continua, cortes=CORTES) -> np.ndarray:
    """PD -> faixa 1-10, com **1 = pior risco** e 10 = melhor.

    `searchsorted` devolve 0 para a PD mais baixa e 9 para a mais alta; a
    subtração inverte a escala. Esta é a única inversão do projeto inteiro.
    """
    pos = np.searchsorted(np.asarray(cortes, dtype="float64"), np.asarray(pd_continua), side="right")
    return (len(cortes) + 1) - pos


def calcular_cortes(p, percentis=PERCENTIS, casas: int = 4) -> np.ndarray:
    """Os cortes a partir de uma distribuição de PD. Só `--refazer` chama isto."""
    return np.round(np.quantile(np.asarray(p), percentis), casas)


# --------------------------------------------------------------------------- #
# A PD honesta da base de desenvolvimento
# --------------------------------------------------------------------------- #


def _modelo():
    estimador = HistGradientBoostingClassifier(
        random_state=SEED, **{k.replace("modelo__", ""): v for k, v in MELHORES.items()}
    )
    return CalibratedClassifierCV(montar_pipeline(estimador), method="sigmoid", cv=5)


def pd_base_a(refazer: bool = False) -> pd.DataFrame:
    """`id_contrato, pd_oof, pd_final` da Base A, com cache em `artefatos/`.

    `pd_oof` é a previsão de um modelo que não viu aquela linha — 25 ajustes (5
    dobras externas vezes as 5 internas da calibração). É a única PD comparável
    à que a Base B receberá, e por isso é ela que define os cortes e a tabela.

    `pd_final` é a do modelo de produção sobre as mesmas linhas, guardada só para
    a comparação da decisão 1: ela ordena com AuROC 0,8088 contra 0,7326 da
    out-of-fold, e a diferença é memória, não capacidade.
    """
    if ARQ_PD_A.exists() and not refazer:
        return pd.read_csv(ARQ_PD_A)
    a = carregar_base_a()
    x, y = matriz(a), a[ALVO]
    oof = cross_val_predict(
        _modelo(), x, y, cv=StratifiedKFold(5, shuffle=True, random_state=SEED),
        method="predict_proba", n_jobs=-1,
    )[:, 1]
    final = _modelo().fit(x, y).predict_proba(x)[:, 1]
    out = pd.DataFrame({"id_contrato": a["id_contrato"], "pd_oof": oof, "pd_final": final})
    ARTEFATOS.mkdir(exist_ok=True)
    out.to_csv(ARQ_PD_A, index=False, encoding="utf-8")
    return out


# --------------------------------------------------------------------------- #
# A tabela de faixas
# --------------------------------------------------------------------------- #


def tabela_faixas(p, y=None, cortes=CORTES) -> pd.DataFrame:
    """Uma linha por faixa: população, intervalo de PD, PD prevista e observada.

    Com `y`, acrescenta a inadimplência realizada e o intervalo de confiança de
    95% dela — é o que separa faixa de verdade de faixa decorativa.
    """
    d = pd.DataFrame({"faixa": faixa(p, cortes), "p": np.asarray(p)})
    t = d.groupby("faixa").agg(n=("p", "size"), pd_prevista=("p", "mean"))
    t["pd_de"] = d.groupby("faixa")["p"].min()
    t["pd_ate"] = d.groupby("faixa")["p"].max()
    t["pct"] = t["n"] / len(d)
    if y is not None:
        d["y"] = np.asarray(y)
        t["pd"] = d.groupby("faixa")["y"].mean()
        t = pd_com_ic(t).rename(columns={"pd": "pd_observada"})
    return t.reindex(range(1, len(cortes) + 2)).sort_index()


def inversoes_materiais(tab: pd.DataFrame) -> list[tuple[int, int]]:
    """Pares vizinhos em que a faixa melhor tem PD observada **comprovadamente**
    maior que a pior — inversão fora do intervalo de confiança.

    Inversão dentro do IC é ruído amostral e não condena a tabela; inversão fora
    dele significa que a faixa está ordenando ao contrário, e aí a política
    cobraria mais barato de quem é mais arriscado.
    """
    t = tab.dropna(subset=["pd_observada"])
    indices = list(t.index)
    return [
        (k, prox)
        for k, prox in zip(indices, indices[1:])
        if t.loc[prox, "ic_lo"] > t.loc[k, "ic_hi"]
    ]


def pares_indistinguiveis(tab: pd.DataFrame) -> list[tuple[int, int]]:
    """Pares vizinhos cujos intervalos de confiança se tocam.

    Não é defeito da tabela: é o limite do dado. Com 10.000 contratos e PD média
    de 8%, só os extremos se separam com 95% de confiança. A leitura correta é
    que **tratar dez faixas com dez preços distintos é fingir uma resolução que
    o modelo não tem** — a política agrupa faixas vizinhas para decidir.
    """
    t = tab.dropna(subset=["pd_observada"])
    indices = list(t.index)
    return [
        (k, prox)
        for k, prox in zip(indices, indices[1:])
        if not t.loc[k, "ic_lo"] > t.loc[prox, "ic_hi"]
    ]


def pd_referencia(p, cortes=CORTES) -> pd.Series:
    """PD média prevista por faixa **na população que está sendo decidida**.

    É este número que a política usa para precificar, e não a PD observada na
    Base A: a faixa é um intervalo de PD, e dentro dele a mistura de perfis da
    Base C não é a da Base A. O modelo está calibrado, então a média prevista
    dentro do intervalo é a melhor estimativa para aquela população.

    A ressalva fica registrada: o nível da PD da Base A traz duas derivas em
    sentidos opostos — a queda de inadimplência entre safras (que faz
    superestimar 2025) e o viés de aprovados (que faz subestimar o mar aberto da
    Base C). A resolução é decisão do capítulo 07.
    """
    d = pd.DataFrame({"faixa": faixa(p, cortes), "p": np.asarray(p)})
    return d.groupby("faixa")["p"].mean()


def estabilidade(f_referencia, f_observada) -> float:
    """PSI entre duas distribuições de faixa. Régua em `exploracao.REGUA_PSI`."""
    return psi(pd.Series(f_referencia), pd.Series(f_observada), None, True)


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #


def main(refazer: bool = False) -> None:
    a, b, c = carregar_base_a(), carregar_base_b(), carregar_base_c()
    pds = pd_base_a(refazer=refazer)
    p_oof = pds["pd_oof"].to_numpy()
    y = a[ALVO].to_numpy()

    print("=" * 98)
    print("FAIXAS DE SCORE 1-10 — Desafio AutoCred")
    print("=" * 98)
    print(
        f"PD out-of-fold da Base A: AuROC {roc_auc_score(y, p_oof):.4f} | "
        f"média {p_oof.mean():.4f} | observada {y.mean():.4f}"
    )

    if refazer:
        recalculados = calcular_cortes(p_oof)
        marca = "OK" if np.allclose(recalculados, CORTES) else f"DIVERGE do código ({list(CORTES)})"
        print(f"\ncortes recalculados: {list(recalculados)} -> {marca}")

    print(f"\ncortes em uso (PD ascendente): {', '.join(f'{v:.4f}' for v in CORTES)}")
    print(f"faixa 1 = pior risco (PD > {CORTES[-1]:.2%}) | faixa 10 = melhor (PD <= {CORTES[0]:.2%})")

    print("\n--- Tabela de faixas (Base A, PD out-of-fold) ---\n")
    tab = tabela_faixas(p_oof, y)
    print(
        tab[["n", "pct", "pd_de", "pd_ate", "pd_prevista", "pd_observada", "ic_lo", "ic_hi"]]
        .round(4)
        .to_string()
    )

    print("\n--- Monotonicidade ---\n")
    rho, inv = monotonicidade(tab.rename(columns={"pd_observada": "pd"}))
    print(f"  rho de Spearman faixa x PD observada: {rho:+.3f}  ({veredito_monotonicidade(rho, inv)})")
    print(f"  inversões de direção: {inv}")
    materiais = inversoes_materiais(tab)
    print(f"  inversões materiais (fora do IC de 95%): {materiais or 'nenhuma'}")
    indistintos = pares_indistinguiveis(tab)
    print(f"  pares vizinhos que o dado não separa: {len(indistintos)} de {N_FAIXAS - 1}  {indistintos}")
    print(
        "\n  Leitura: a ordenação é correta em todo o intervalo, mas a resolução\n"
        "  estatística não chega a dez níveis. A política precifica grupos de faixas,\n"
        "  não dez preços distintos — ver docs/05-score.md, decisão 4."
    )

    print("\n--- Discriminação: PD contínua x faixa ---\n")
    f_oof = faixa(p_oof)
    print(f"  AuROC na PD contínua ... {roc_auc_score(y, p_oof):.4f}")
    print(f"  AuROC na faixa 1-10 .... {roc_auc_score(y, -f_oof):.4f}")
    print(f"  custo do agrupamento ... {roc_auc_score(y, p_oof) - roc_auc_score(y, -f_oof):.4f}")

    print("\n--- Estabilidade da distribuição de faixas ---\n")
    modelo = _modelo().fit(matriz(a), a[ALVO])
    f_b = faixa(modelo.predict_proba(matriz(b))[:, 1])
    f_c = faixa(modelo.predict_proba(matriz(preparar_aplicacao(c)))[:, 1])
    ref = f_oof[a["ano"].to_numpy() == 2022]
    print(f"  {'população':<22}{'n':>7}{'faixa média':>14}{'% 1-3':>9}{'% 8-10':>9}{'PSI vs 2022':>13}")
    for rotulo, f in [
        ("Base A 2022 (ref.)", ref),
        ("Base A 2023", f_oof[a["ano"].to_numpy() == 2023]),
        ("Base A 2024", f_oof[a["ano"].to_numpy() == 2024]),
        ("Base B (2025-S1)", f_b),
        ("Base C (2025-S2)", f_c),
    ]:
        s = pd.Series(f)
        print(
            f"  {rotulo:<22}{len(s):>7,}{s.mean():>14.2f}{(s <= 3).mean():>9.1%}"
            f"{(s >= 8).mean():>9.1%}{estabilidade(ref, s):>13.3f}"
        )

    print("\n--- Base C por faixa: o que a política terá para decidir ---\n")
    tab_c = tabela_faixas(modelo.predict_proba(matriz(preparar_aplicacao(c)))[:, 1])
    tab_c["pct_acum_de_cima"] = tab_c.sort_index(ascending=False)["pct"].cumsum()
    print(tab_c[["n", "pct", "pct_acum_de_cima", "pd_prevista"]].round(4).to_string())
    aprovaveis = tab_c["pct_acum_de_cima"]
    minimo = aprovaveis[aprovaveis >= 0.35].index.max()
    print(
        f"\n  O guardrail de aprovação (>= 35% das 5.000) obriga a descer até a faixa {minimo}:\n"
        f"  faixas {minimo} a 10 somam {aprovaveis.loc[minimo]:.1%} das propostas."
    )

    ARTEFATOS.mkdir(exist_ok=True)
    tab.round(6).to_csv(ARQ_TABELA, encoding="utf-8")
    registrar_execucao(
        "score",
        {
            "etapa": "src/score",
            "n_faixas": N_FAIXAS,
            "percentis": list(PERCENTIS),
            "cortes": list(CORTES),
            "auroc_pd_continua": round(float(roc_auc_score(y, p_oof)), 4),
            "auroc_faixa": round(float(roc_auc_score(y, -f_oof)), 4),
            "inversoes_materiais": len(materiais),
            "pares_indistinguiveis": len(indistintos),
            "psi_a_para_c": round(float(estabilidade(ref, pd.Series(f_c))), 4),
            "faixa_minima_para_35pct": int(minimo),
            "saida": ARQ_TABELA.name,
        },
    )
    print(f"\n  tabela gravada em artefatos/{ARQ_TABELA.name}")
    print("=" * 98)


if __name__ == "__main__":
    main(refazer="--refazer" in sys.argv)
