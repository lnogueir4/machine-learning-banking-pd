"""As quatro decisões de pré-processamento, com a evidência que as sustenta.

Toda tabela de `docs/03-features.md` sai daqui. O script existe porque a regra do
projeto é que número citado em documentação tem de ser reproduzível por um
comando — e porque essas decisões serão questionadas na defesa uma a uma:

  1. Criar variáveis derivadas compensa?          -> ablação com validação cruzada
  2. `comprometimento_renda` ausente na Base C    -> quatro reconstruções comparadas
  3. Imputar ou preservar `NaN`?                  -> árvore contra modelo linear
  4. Degradar o treino para igualar a aplicação?  -> coerência formal vale o preço?

Todas as medidas de seleção usam validação cruzada **dentro do treino**
(2022-2023). A safra de 2024 aparece como confirmação out-of-time, nunca como
critério de escolha.

Uso:
    PYTHONIOENCODING=utf-8 python notebooks/02-decisoes-features.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_score  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler  # noqa: E402

from dados import (  # noqa: E402
    ALVO,
    CATEGORICAS,
    FEATURES,
    SEED,
    carregar_base_a,
    carregar_base_c,
    registrar_execucao,
)
from features import (  # noqa: E402
    NUMERICAS,
    montar_pipeline,
    parcela_price,
    preparar_aplicacao,
    taxa_referencia,
)
from modelo import MELHORES, dividir  # noqa: E402

CV = StratifiedKFold(5, shuffle=True, random_state=SEED)


def estimador():
    return HistGradientBoostingClassifier(
        random_state=SEED, **{k.replace("modelo__", ""): v for k, v in MELHORES.items()}
    )


def derivar(d: pd.DataFrame) -> pd.DataFrame:
    """As sete candidatas testadas — todas calculáveis também na Base C."""
    d = d.copy()
    renda = d["renda_mensal_declarada"]
    d["entrada_sobre_renda"] = d["valor_entrada"] / renda
    d["financiado_sobre_renda"] = d["valor_financiado"] / renda
    d["bem_sobre_renda"] = d["valor_bem"] / renda
    d["score_por_restricao"] = d["score_bureau"] / (1 + d["qtd_restricoes_ativas"])
    d["pressao_bureau"] = d["qtd_restricoes_ativas"] + d["qtd_consultas_bureau_3m"]
    d["estabilidade_emprego"] = d["tempo_emprego_meses"] / (d["idade_cliente"] * 12)
    d["idade_veiculo_no_fim"] = d["idade_veiculo_anos"] + d["prazo_meses"] / 12
    return d


DERIVADAS = [
    "entrada_sobre_renda",
    "financiado_sobre_renda",
    "bem_sobre_renda",
    "score_por_restricao",
    "pressao_bureau",
    "estabilidade_emprego",
    "idade_veiculo_no_fim",
]


def _pipe(feats: list[str]) -> Pipeline:
    cats = [c for c in CATEGORICAS if c in feats]
    nums = [c for c in feats if c not in cats]
    return Pipeline(
        [
            (
                "preparar",
                ColumnTransformer(
                    [
                        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), cats),
                        ("num", "passthrough", nums),
                    ]
                ),
            ),
            ("modelo", estimador()),
        ]
    )


def secao_1_derivadas(treino: pd.DataFrame, oot: pd.DataFrame) -> pd.DataFrame:
    tr, oo = derivar(treino), derivar(oot)

    def medir(feats):
        s = cross_val_score(_pipe(feats), tr[feats], tr[ALVO], cv=CV, scoring="roc_auc")
        m = _pipe(feats).fit(tr[feats], tr[ALVO])
        return s.mean(), s.std(), roc_auc_score(oo[ALVO], m.predict_proba(oo[feats])[:, 1])

    base = medir(FEATURES)
    linhas = [{"conjunto": f"{len(FEATURES)} features (baseline)", "CV": base[0], "dp": base[1],
               "OOT": base[2], "ΔCV": 0.0}]
    for c in DERIVADAS:
        cv_, dp, oot_ = medir(FEATURES + [c])
        linhas.append({"conjunto": f"+ {c}", "CV": cv_, "dp": dp, "OOT": oot_, "ΔCV": cv_ - base[0]})
    cv_, dp, oot_ = medir(FEATURES + DERIVADAS)
    linhas.append({"conjunto": "+ todas as sete", "CV": cv_, "dp": dp, "OOT": oot_, "ΔCV": cv_ - base[0]})
    return pd.DataFrame(linhas)


def secao_2_comprometimento(treino: pd.DataFrame, oot: pd.DataFrame) -> pd.DataFrame:
    """Quatro formas de preencher a coluna que a Base C não traz."""
    m = _pipe(FEATURES).fit(treino[FEATURES], treino[ALVO])
    tx_med = taxa_referencia()
    tx_p90 = float(treino["taxa_juros_am"].quantile(0.9))
    renda = oot["renda_mensal_declarada"]
    cenarios = {
        "real (parcela contratada)": oot["comprometimento_renda"],
        "NaN (deixar o imputador assumir)": pd.Series(np.nan, index=oot.index),
        f"Price à taxa mediana do treino ({tx_med:.4f})":
            parcela_price(oot["valor_financiado"], tx_med, oot["prazo_meses"]) / renda,
        f"Price à taxa do p90 ({tx_p90:.4f})":
            parcela_price(oot["valor_financiado"], tx_p90, oot["prazo_meses"]) / renda,
        "sem juros (financiado / prazo)": (oot["valor_financiado"] / oot["prazo_meses"]) / renda,
    }
    linhas = []
    for nome, serie in cenarios.items():
        x = oot.copy()
        x["comprometimento_renda"] = np.asarray(serie, dtype="float64")
        p = m.predict_proba(x[FEATURES])[:, 1]
        linhas.append({"cenário": nome, "AuROC OOT": roc_auc_score(oot[ALVO], p), "PD prevista": p.mean()})
    return pd.DataFrame(linhas)


def secao_3_imputacao(treino: pd.DataFrame, oot: pd.DataFrame) -> pd.DataFrame:
    configs = {
        "HistGB | NaN preservado + ordinal": montar_pipeline(estimador()),
        "HistGB | imputação mediana + ordinal": Pipeline(
            [
                (
                    "preparar",
                    ColumnTransformer(
                        [
                            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CATEGORICAS),
                            ("num", SimpleImputer(strategy="median"), NUMERICAS),
                        ]
                    ),
                ),
                ("modelo", estimador()),
            ]
        ),
        "Logística | mediana + one-hot + padronização": Pipeline(
            [
                (
                    "preparar",
                    ColumnTransformer(
                        [
                            ("cat", OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False), CATEGORICAS),
                            ("num", Pipeline([("i", SimpleImputer(strategy="median")), ("s", StandardScaler())]), NUMERICAS),
                        ]
                    ),
                ),
                ("modelo", LogisticRegression(max_iter=2000, random_state=SEED)),
            ]
        ),
    }
    linhas = []
    for nome, pipe in configs.items():
        s = cross_val_score(pipe, treino[FEATURES], treino[ALVO], cv=CV, scoring="roc_auc")
        pipe.fit(treino[FEATURES], treino[ALVO])
        linhas.append(
            {
                "configuração": nome,
                "CV": s.mean(),
                "dp": s.std(),
                "OOT": roc_auc_score(oot[ALVO], pipe.predict_proba(oot[FEATURES])[:, 1]),
            }
        )
    return pd.DataFrame(linhas)


def secao_4_coerencia(treino: pd.DataFrame, oot: pd.DataFrame) -> pd.DataFrame:
    """Vale degradar o treino para que ele tenha a mesma forma da Base C?"""
    tx = taxa_referencia()
    med_renda = float(treino["renda_mensal_declarada"].median())

    def como_em_c(d, renda=None):
        x = d.copy()
        r = x["renda_mensal_declarada"] if renda is None else renda
        x["comprometimento_renda"] = parcela_price(x["valor_financiado"], tx, x["prazo_meses"]) / r
        return x

    tr_degradado = como_em_c(treino)
    oo_c = como_em_c(oot)
    oo_imputado = como_em_c(oot, oot["renda_mensal_declarada"].fillna(med_renda))
    combinacoes = [
        ("treino completo -> aplicação completa (irreal em C)", treino, oot),
        ("treino completo -> aplicação como C (NaN onde falta renda)", treino, oo_c),
        ("treino completo -> aplicação com renda imputada", treino, oo_imputado),
        ("treino degradado para imitar C -> aplicação como C", tr_degradado, oo_c),
    ]
    linhas = []
    for nome, t, v in combinacoes:
        m = _pipe(FEATURES).fit(t[FEATURES], t[ALVO])
        linhas.append(
            {"estratégia": nome, "AuROC OOT": roc_auc_score(v[ALVO], m.predict_proba(v[FEATURES])[:, 1])}
        )
    return pd.DataFrame(linhas)


def secao_5_teto_comprometimento(treino: pd.DataFrame) -> None:
    """O terceiro corte da política antiga, e o quanto dele é negociável."""
    bruta = carregar_base_c()
    c = preparar_aplicacao(bruta)
    teto = float(treino["comprometimento_renda"].max())
    print(f"\n  teto de comprometimento observado no treino: {teto:.4f}")
    print(f"  {'faixa':<22}{'treino':>10}{'Base C':>10}")
    for q in (0.30, 0.35, 0.40, 0.45):
        print(
            f"  {'acima de ' + format(q, '.0%'):<22}"
            f"{(treino['comprometimento_renda'] > q).mean():>10.2%}"
            f"{(c['comprometimento_renda'] > q).mean():>10.2%}"
        )
    print(f"  {'máximo':<22}{treino['comprometimento_renda'].max():>10.4f}{c['comprometimento_renda'].max():>10.4f}")

    cortes = {
        "score_bureau < 460": c["score_bureau"] < 460,
        "qtd_restricoes_ativas > 2": c["qtd_restricoes_ativas"] > 2,
        f"comprometimento > {teto:.3f}": c["comprometimento_renda"] > teto,
    }
    print(f"\n  {'corte da política antiga':<32}{'propostas de C':>16}")
    for nome, marca in cortes.items():
        print(f"  {nome:<32}{marca.mean():>11.1%} ({int(marca.sum())})")
    combinado = np.logical_or.reduce([m.fillna(False).to_numpy() for m in cortes.values()])
    print(f"  {'ao menos um dos três':<32}{combinado.mean():>11.1%} ({int(combinado.sum())})")

    acima = c["comprometimento_renda"] > teto
    prazo60 = pd.Series(60, index=bruta.index)
    entrada30 = np.maximum(c["valor_entrada"], 0.30 * c["valor_bem"])
    variantes = [
        ("condições desejadas pelo cliente", c),
        ("prazo esticado para 60 meses", preparar_aplicacao(bruta, prazo_meses=prazo60)),
        ("prazo 60m + entrada mínima de 30%", preparar_aplicacao(bruta, prazo_meses=prazo60, valor_entrada=entrada30)),
    ]
    print(f"\n  {'oferta às ' + str(int(acima.sum())) + ' propostas acima do teto':<40}{'ainda acima':>12}")
    for nome, df in variantes:
        print(f"  {nome:<40}{int((df['comprometimento_renda'] > teto).sum()):>12}")


def main() -> None:
    a = carregar_base_a()
    treino, oot = dividir(a)

    print("=" * 92)
    print("DECISÕES DE PRÉ-PROCESSAMENTO — evidência por trás de docs/03-features.md")
    print("=" * 92)
    print(
        f"treino n={len(treino):,} (PD={treino[ALVO].mean():.4f}) | "
        f"OOT 2024 n={len(oot):,} (PD={oot[ALVO].mean():.4f}) | {len(FEATURES)} features"
    )

    print("\n### 1. CRIAR VARIÁVEIS DERIVADAS COMPENSA?\n")
    t1 = secao_1_derivadas(treino, oot)
    print(t1.round({"CV": 4, "dp": 4, "OOT": 4, "ΔCV": 4}).to_string(index=False))
    print("\n(critério: ganho tem de superar o desvio padrão da validação, não o zero)")

    print("\n### 2. COMO PREENCHER comprometimento_renda NA BASE C\n")
    t2 = secao_2_comprometimento(treino, oot)
    print(t2.round({"AuROC OOT": 4, "PD prevista": 4}).to_string(index=False))
    print(f"(PD observada em 2024: {oot[ALVO].mean():.4f})")
    erro = ((parcela_price(a["valor_financiado"], a["taxa_juros_am"], a["prazo_meses"]) - a["parcela_mensal"]).abs() / a["parcela_mensal"]).median()
    print(f"(Price reproduz a parcela registrada na Base A com erro relativo mediano de {erro:.2e})")

    print("\n### 3. IMPUTAR OU PRESERVAR O AUSENTE\n")
    t3 = secao_3_imputacao(treino, oot)
    print(t3.round({"CV": 4, "dp": 4, "OOT": 4}).to_string(index=False))
    ausentes = {c: f"{treino[c].isna().mean():.2%}" for c in FEATURES if treino[c].isna().any()}
    print(f"\nausentes no treino: {ausentes}")

    print("\n### 4. DEGRADAR O TREINO PARA IGUALAR A APLICAÇÃO?\n")
    t4 = secao_4_coerencia(treino, oot)
    print(t4.round({"AuROC OOT": 4}).to_string(index=False))

    print("\n### 5. O TETO DE COMPROMETIMENTO — TERCEIRO CORTE DA POLÍTICA ANTIGA")
    secao_5_teto_comprometimento(treino)

    destino = RAIZ / "artefatos" / "decisoes_features.csv"
    pd.concat(
        [t1.assign(secao="derivadas"), t3.assign(secao="imputacao")], ignore_index=True
    ).to_csv(destino, index=False, encoding="utf-8")
    registrar_execucao(
        "decisoes_features",
        {
            "etapa": "notebooks/02-decisoes-features",
            "n_features": len(FEATURES),
            "derivadas_testadas": len(DERIVADAS),
            "derivadas_aprovadas": 0,
            "taxa_referencia": round(taxa_referencia(), 6),
            "saida": destino.name,
        },
    )
    print(f"\nTabelas gravadas em artefatos/{destino.name}")
    print("=" * 92)


if __name__ == "__main__":
    main()
