"""Pré-processamento — Desafio AutoCred.

Duas responsabilidades, e nenhuma a mais:

  1. **Montar a matriz de entrada** igual nas três bases. A Base C não traz
     `parcela_mensal` (quem decide a parcela somos nós), então o
     `comprometimento_renda` é *reconstruído* pela Tabela Price. Sem isso, a
     variável chegaria `NaN` em 100% da Base C — e o modelo nunca viu `NaN` ali.
  2. **Devolver o `Pipeline` do scikit-learn** que faz imputação, encoding e
     padronização. Estar dentro do `Pipeline` é o que garante que esses ajustes
     sejam aprendidos só no treino: o `fit` vê a janela de treino e nada mais.

O que este módulo deliberadamente **não** faz: criar variáveis novas. Sete razões
candidatas (entrada/renda, financiado/renda, score por restrição, pressão de
bureau, estabilidade no emprego, idade do veículo no fim do contrato) foram
testadas em validação cruzada e nenhuma sobreviveu — ver `docs/03-features.md`.

Uso:
    PYTHONIOENCODING=utf-8 python src/features.py     # diagnóstico do pré-processamento
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from dados import (
    ALVO,
    CATEGORICAS,
    FEATURES,
    carregar_base_a,
    mapear_base_c,
    validar_features,
)

NUMERICAS = [f for f in FEATURES if f not in CATEGORICAS]

# Janela de treino. Fica aqui porque `taxa_referencia()` precisa dela e porque
# qualquer estatística usada no pré-processamento tem de sair desta janela.
ANO_CORTE = 2024


# --------------------------------------------------------------------------- #
# Matemática financeira: a parcela que a Base C não traz
# --------------------------------------------------------------------------- #


def parcela_price(valor_financiado, taxa_am, prazo_meses):
    """Parcela do sistema Price: `PV · i / (1 − (1+i)^−n)`.

    Conferido contra a Base A: a `parcela_mensal` registrada bate com esta
    fórmula com erro relativo mediano de 2,3e-06 — ou seja, as bases foram
    geradas por Price e podemos reconstruir a parcela de qualquer oferta.

    Exemplo: R$ 40.000 a 1,59% a.m. em 48 meses -> R$ 1.190,55.
    """
    i = np.asarray(taxa_am, dtype="float64")
    n = np.asarray(prazo_meses, dtype="float64")
    return np.asarray(valor_financiado, dtype="float64") * i / (1 - (1 + i) ** -n)


@lru_cache(maxsize=1)
def taxa_referencia() -> float:
    """Taxa mensal mediana da janela de treino — 1,59% a.m.

    Serve à **primeira passada** sobre a Base C: para dar um score inicial é
    preciso uma parcela, e para ter uma parcela é preciso uma taxa, que por sua
    vez depende do score. O laço se rompe com uma taxa de referência; depois que
    a política define a taxa ofertada, a segunda passada recalcula tudo.

    O erro que isso introduz é pequeno porque a carteira antiga praticamente não
    diferenciava preço: p10 = 1,43% e p90 = 1,76% a.m. Trocar a mediana pelo p90
    move o AuROC out-of-time de 0,7382 para 0,7390.
    """
    a = carregar_base_a()
    return float(a.loc[a["ano"] < ANO_CORTE, "taxa_juros_am"].median())


# --------------------------------------------------------------------------- #
# Montagem da matriz
# --------------------------------------------------------------------------- #


def matriz(df: pd.DataFrame) -> pd.DataFrame:
    """`df[FEATURES]`, na ordem canônica, após a checagem antivazamento.

    Toda entrada de modelo passa por aqui. É barato e fecha a porta para o erro
    mais caro do desafio — ver `aprendizado.md`, "A variável mais preditiva da
    base é a que está proibida".
    """
    faltando = [f for f in FEATURES if f not in df.columns]
    if faltando:
        raise KeyError(
            "Colunas ausentes para montar a matriz: "
            + ", ".join(faltando)
            + ". Base C precisa passar por `preparar_aplicacao()` antes."
        )
    return df[validar_features()].copy()


def preparar_aplicacao(
    base_c: pd.DataFrame,
    taxa_am: pd.Series | float | None = None,
    prazo_meses: pd.Series | None = None,
    valor_entrada: pd.Series | None = None,
) -> pd.DataFrame:
    """Base C no vocabulário do modelo, com `comprometimento_renda` preenchido.

    Sem argumentos: condições **desejadas** pelo cliente à taxa de referência —
    é a primeira passada, que produz o score usado para enquadrar a proposta.
    Com as condições ofertadas: a versão que decide aprovação e preço.

    Por que reconstruir em vez de deixar `NaN`: a coluna é 0% ausente na Base A,
    então o modelo não tem uma folha de `NaN` treinada para ela. Deixá-la vazia
    derruba o AuROC do análogo out-of-time de 0,7382 para 0,7094 e subestima a
    PD média. Reconstruída por Price, o resultado é indistinguível da parcela
    contratada de verdade (0,7382 contra 0,7368).

    O `NaN` sobra apenas onde a renda declarada é ausente (7,9% da Base C, contra
    7,7% da Base A) — proporção que o modelo já encontra no treino em outras
    colunas e que, medida, não custa AuROC.
    """
    taxa = taxa_referencia() if taxa_am is None else taxa_am
    df = mapear_base_c(base_c, prazo_meses=prazo_meses, valor_entrada=valor_entrada)
    parcela = parcela_price(df["valor_financiado"], taxa, df["prazo_meses"])
    df["parcela_mensal"] = parcela
    df["taxa_juros_am"] = taxa
    df["comprometimento_renda"] = parcela / df["renda_mensal_declarada"]
    return df


# --------------------------------------------------------------------------- #
# Os dois pré-processadores
# --------------------------------------------------------------------------- #
# Modelos diferentes querem tratamentos diferentes, e forçar um só empobrece a
# comparação de `modelo.py`. Ambos são `ColumnTransformer` com as colunas
# nomeadas explicitamente — sem `remainder`, para que a ordem de saída seja
# conhecida e as importâncias possam ser lidas por nome.


def preparador_arvore() -> ColumnTransformer:
    """Para modelos baseados em árvore: encoding ordinal e **`NaN` preservado**.

    `HistGradientBoostingClassifier` trata ausente como direção própria em cada
    split — aprende para que lado mandar o faltante em vez de receber a mediana
    de presente. Medido: manter `NaN` dá 0,7368 out-of-time contra 0,7258 com
    imputação pela mediana. Imputar aqui destruiria informação.

    Ordinal (e não one-hot) porque a árvore não lê a ordem do código como
    grandeza; ela só precisa conseguir separar as categorias.
    """
    return ColumnTransformer(
        [
            (
                "cat",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                CATEGORICAS,
            ),
            ("num", "passthrough", NUMERICAS),
        ]
    )


def preparador_linear() -> ColumnTransformer:
    """Para modelos lineares: mediana, one-hot e padronização.

    Nenhuma das três etapas é opcional aqui — a regressão logística não aceita
    `NaN`, lê código ordinal como grandeza e tem coeficientes incomparáveis sem
    escala comum. A mediana (não a média) porque renda e valor do bem têm cauda
    longa à direita.

    `drop="first"` evita a colinearidade perfeita entre as dummies; ela não
    impede o ajuste com regularização, mas embaralha a leitura dos coeficientes,
    que é a única razão de manter um modelo linear na comparação.
    """
    return ColumnTransformer(
        [
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False),
                CATEGORICAS,
            ),
            (
                "num",
                Pipeline(
                    [
                        ("imputar", SimpleImputer(strategy="median")),
                        ("padronizar", StandardScaler()),
                    ]
                ),
                NUMERICAS,
            ),
        ]
    )


def montar_pipeline(estimador, linear: bool = False) -> Pipeline:
    """`Pipeline(pré-processador, estimador)` — a única forma de treinar aqui.

    O `Pipeline` não é organização: é a garantia contra vazamento de
    pré-processamento. Mediana, categorias vistas e média/desvio da padronização
    são aprendidas dentro do `fit`, que só enxerga a partição de treino. Imputar
    antes do split contamina o treino com a distribuição do teste e infla a
    métrica sem que nada acuse.
    """
    preparador = preparador_linear() if linear else preparador_arvore()
    return Pipeline([("preparar", preparador), ("modelo", estimador)])


def nomes_saida(preparador: ColumnTransformer) -> list[str]:
    """Nomes das colunas depois do pré-processamento, para ler importâncias."""
    return [n.split("__", 1)[-1] for n in preparador.get_feature_names_out()]


# --------------------------------------------------------------------------- #
# Diagnóstico
# --------------------------------------------------------------------------- #


def diagnosticar() -> None:
    """Confere que o pré-processamento produz a mesma matriz nas três bases."""
    from dados import carregar_base_b, carregar_base_c

    a, b, c = carregar_base_a(), carregar_base_b(), carregar_base_c()
    treino = a[a["ano"] < ANO_CORTE]
    aplicacao = preparar_aplicacao(c)

    print("=" * 84)
    print("PRÉ-PROCESSAMENTO — Desafio AutoCred")
    print("=" * 84)
    print(f"\n{len(FEATURES)} features | {len(CATEGORICAS)} categóricas | {len(NUMERICAS)} numéricas")
    print(f"taxa de referência da 1ª passada: {taxa_referencia():.4%} a.m.")

    print("\n--- A matriz monta nas três bases? ---")
    for nome, df in [("A", a), ("B", b), ("C (preparada)", aplicacao)]:
        x = matriz(df)
        print(f"  Base {nome:<14} {x.shape[0]:>6,} x {x.shape[1]:<3} colunas  OK")

    print("\n--- Ausentes por coluna, depois do preparo (%) ---")
    print(f"  {'coluna':<26}{'treino':>9}{'B':>9}{'C':>9}")
    for col in FEATURES:
        pa, pb, pc = (treino[col].isna().mean(), b[col].isna().mean(), aplicacao[col].isna().mean())
        if max(pa, pb, pc) > 0:
            print(f"  {col:<26}{pa:>9.2%}{pb:>9.2%}{pc:>9.2%}")

    print("\n--- comprometimento_renda: reconstruído x contratado ---")
    conferencia = parcela_price(a["valor_financiado"], a["taxa_juros_am"], a["prazo_meses"])
    erro = ((conferencia - a["parcela_mensal"]).abs() / a["parcela_mensal"]).median()
    print(f"  Price reproduz a parcela da Base A com erro relativo mediano de {erro:.2e}")
    print(
        f"  distribuição em C: min {aplicacao['comprometimento_renda'].min():.3f} | "
        f"mediana {aplicacao['comprometimento_renda'].median():.3f} | "
        f"máx {aplicacao['comprometimento_renda'].max():.3f}"
    )
    print(
        f"  distribuição no treino: min {treino['comprometimento_renda'].min():.3f} | "
        f"mediana {treino['comprometimento_renda'].median():.3f} | "
        f"máx {treino['comprometimento_renda'].max():.3f}"
    )

    print("\n--- Saída dos dois pré-processadores (ajustados só no treino) ---")
    for rotulo, linear in [("árvore ", False), ("linear ", True)]:
        prep = preparador_linear() if linear else preparador_arvore()
        saida = prep.fit_transform(matriz(treino), treino[ALVO])
        nans = int(np.isnan(np.asarray(saida, dtype="float64")).sum())
        print(f"  {rotulo}: {saida.shape[1]:>2} colunas | NaN remanescentes: {nans}")

    print("\n" + "=" * 84)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    diagnosticar()
