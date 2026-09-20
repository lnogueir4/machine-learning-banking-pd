"""Treino, validação out-of-time e escolha do modelo — Desafio AutoCred.

A disciplina que este módulo existe para impor:

  - **Hiperparâmetro é escolhido por validação cruzada dentro do treino**
    (2022-2023). A safra de 2024 é tocada uma vez, no fim, para estimar o que
    acontecerá na Base B. Buscar parâmetro olhando 2024 transforma o
    out-of-time em mais um conjunto de treino e a estimativa vira propaganda.
  - **Toda comparação usa o mesmo split e a mesma seed.** Diferença de 0,003 de
    AuROC entre dois modelos é ruído; diferença que muda com a seed não é
    resultado.
  - **Calibração é medida, não presumida.** O AuROC não enxerga se a PD prevista
    vale 3% ou 30% — e a política de crédito precisa exatamente disso.

Uso:
    PYTHONIOENCODING=utf-8 python src/modelo.py           # comparação + modelo final
    PYTHONIOENCODING=utf-8 python src/modelo.py --busca   # refaz a busca de hiperparâmetros
    PYTHONIOENCODING=utf-8 python src/modelo.py --poda    # julga a poda em janelas anteriores a 2024
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score, roc_curve
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.tree import DecisionTreeClassifier

from dados import ALVO, ARTEFATOS, CANDIDATAS, CATEGORICAS, SEED, carregar_base_a, registrar_execucao
from features import ANO_CORTE, FEATURES, matriz, montar_pipeline

ARQ_MODELO = ARTEFATOS / "modelo_pd.joblib"

# Encontrados por `buscar_hiperparametros()` — validação cruzada de 5 dobras na
# janela 2022-2023, métrica AuROC. Ficam escritos aqui para que o treino seja
# reprodutível sem repetir a busca; `--busca` refaz e mostra se algo mudou.
MELHORES = {
    "modelo__learning_rate": 0.03,
    "modelo__max_leaf_nodes": 4,
    "modelo__min_samples_leaf": 50,
    "modelo__l2_regularization": 1.0,
    "modelo__max_iter": 400,
}


# --------------------------------------------------------------------------- #
# Divisão temporal
# --------------------------------------------------------------------------- #


def dividir(a: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Treino = safras anteriores a 2024; validação out-of-time = safra de 2024.

    Divisão por tempo, não aleatória: a Base B é jan-jun/2025, posterior a tudo
    que temos. Um split aleatório mediria a capacidade de interpolar dentro do
    período — pergunta diferente, e mais fácil, do que a que a nota faz.
    """
    return a[a["ano"] < ANO_CORTE].copy(), a[a["ano"] == ANO_CORTE].copy()


# --------------------------------------------------------------------------- #
# Métricas
# --------------------------------------------------------------------------- #


def ks(y: np.ndarray, p: np.ndarray) -> float:
    """Kolmogorov-Smirnov: maior distância entre as acumuladas de bons e maus.

    AuROC resume a ordenação inteira; o KS diz onde ela é mais forte, que é o
    ponto natural para pensar um corte de aprovação.
    """
    fpr, tpr, _ = roc_curve(y, p)
    return float((tpr - fpr).max())


def metricas(y, p) -> dict[str, float]:
    """AuROC, Gini, KS, Brier e a comparação PD prevista × PD observada.

    As três primeiras medem **ordenação** — se o modelo põe os piores na frente.
    As duas últimas medem **nível**: um modelo pode ordenar perfeitamente e
    ainda assim prever 3% onde a realidade é 8%, o que arruinaria a precificação
    sem aparecer no AuROC.
    """
    y = np.asarray(y)
    p = np.asarray(p)
    auc = roc_auc_score(y, p)
    return {
        "auroc": float(auc),
        "gini": float(2 * auc - 1),
        "ks": ks(y, p),
        "brier": float(brier_score_loss(y, p)),
        "pd_prevista": float(p.mean()),
        "pd_observada": float(y.mean()),
        "vies": float(p.mean() - y.mean()),
    }


def tabela_calibracao(y, p, n_faixas: int = 10) -> pd.DataFrame:
    """PD prevista × observada por decil de risco. É o teste que o AuROC não faz."""
    d = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
    d["decil"] = pd.qcut(d["p"], n_faixas, labels=False, duplicates="drop") + 1
    t = d.groupby("decil").agg(n=("y", "size"), prevista=("p", "mean"), observada=("y", "mean"))
    t["razão"] = t["prevista"] / t["observada"]
    return t


# --------------------------------------------------------------------------- #
# Candidatos
# --------------------------------------------------------------------------- #


# Grade de busca de **cada** candidato. Buscar só para o favorito e deixar os
# concorrentes com parâmetro de fábrica produz uma comparação arranjada: o
# vencedor ganharia por ter sido ajustado, não por ser melhor. Todos passam pela
# mesma validação cruzada, na mesma janela, com a mesma métrica.
GRADES: dict[str, dict] = {
    "Regressão logística": {
        # C é o inverso da força da regularização: C pequeno encolhe os
        # coeficientes, C grande deixa o modelo seguir os dados.
        "modelo__C": [0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0],
    },
    "Árvore de decisão": {
        "modelo__max_depth": [2, 3, 4, 5, 6, 8],
        "modelo__min_samples_leaf": [20, 50, 100, 200],
        "modelo__criterion": ["gini", "entropy"],
    },
    "Random Forest": {
        "modelo__max_depth": [None, 4, 6, 8, 12],
        "modelo__min_samples_leaf": [5, 20, 50, 100],
        "modelo__max_features": ["sqrt", 0.5],
    },
    "HistGB regularizado": {
        "modelo__learning_rate": [0.03, 0.05, 0.10],
        "modelo__max_leaf_nodes": [4, 8, 16],
        "modelo__min_samples_leaf": [20, 50, 100],
        "modelo__l2_regularization": [0.0, 1.0],
        "modelo__max_iter": [400],
    },
}

# Vencedores de cada grade, preenchidos por `--busca`. Escritos aqui para que o
# treino seja reprodutível sem repetir a busca inteira.
MELHORES_BASELINES: dict[str, dict] = {
    "Regressão logística": {"C": 0.01},
    "Árvore de decisão": {"criterion": "entropy", "max_depth": 6, "min_samples_leaf": 200},
    "Random Forest": {"max_depth": 12, "max_features": 0.5, "min_samples_leaf": 20},
}


def _estimador_base(nome: str):
    """O estimador sem hiperparâmetro ajustado — o que entra na busca."""
    return {
        "Regressão logística": LogisticRegression(max_iter=2000, random_state=SEED),
        "Árvore de decisão": DecisionTreeClassifier(random_state=SEED),
        "Random Forest": RandomForestClassifier(n_estimators=300, n_jobs=1, random_state=SEED),
        "HistGB regularizado": HistGradientBoostingClassifier(random_state=SEED),
    }[nome]


def candidatos() -> dict[str, tuple[object, bool]]:
    """Os cinco modelos comparados, cada um respondendo a uma pergunta.

    Os quatro primeiros saem da busca de hiperparâmetros; o `HistGB padrão` é o
    único deliberadamente não ajustado, porque o papel dele é exibir o tamanho do
    overfit que a regularização evita.

    Logística e árvore são **referências**, não apostas: se um modelo complexo
    não superar com folga uma logística ajustada, ele não paga a própria
    opacidade diante do conselho.
    """
    return {
        "Regressão logística": (
            LogisticRegression(max_iter=2000, random_state=SEED, **MELHORES_BASELINES["Regressão logística"]),
            True,
        ),
        "Árvore de decisão": (
            DecisionTreeClassifier(random_state=SEED, **MELHORES_BASELINES["Árvore de decisão"]),
            False,
        ),
        "Random Forest": (
            RandomForestClassifier(
                n_estimators=300, n_jobs=-1, random_state=SEED, **MELHORES_BASELINES["Random Forest"]
            ),
            False,
        ),
        "HistGB padrão": (
            HistGradientBoostingClassifier(random_state=SEED),
            False,
        ),
        "HistGB regularizado": (
            HistGradientBoostingClassifier(
                random_state=SEED,
                **{k.replace("modelo__", ""): v for k, v in MELHORES.items()},
            ),
            False,
        ),
    }


def buscar_hiperparametros(treino: pd.DataFrame, nome: str, verboso: bool = True) -> dict:
    """Grid search de um candidato, 5 dobras, **só na janela de treino**.

    A safra de 2024 não aparece nesta função. Avaliar a grade contra ela faria do
    número reportado o melhor de N tentativas na própria régua — otimista por
    construção, e sem aviso.
    """
    linear = nome == "Regressão logística"
    busca = GridSearchCV(
        montar_pipeline(_estimador_base(nome), linear=linear),
        GRADES[nome],
        scoring="roc_auc",
        cv=StratifiedKFold(5, shuffle=True, random_state=SEED),
        n_jobs=-1,
    )
    busca.fit(matriz(treino), treino[ALVO])
    limpos = {k.replace("modelo__", ""): v for k, v in busca.best_params_.items()}
    if verboso:
        r = pd.DataFrame(busca.cv_results_).nlargest(3, "mean_test_score")
        print(f"\n  {nome} — {len(pd.DataFrame(busca.cv_results_))} combinações")
        for _, linha in r.iterrows():
            p = {k.replace("modelo__", ""): v for k, v in linha["params"].items() if k != "modelo__max_iter"}
            print(f"    {linha['mean_test_score']:.4f} ±{linha['std_test_score']:.4f}  {p}")
    return limpos


def buscar_todos(treino: pd.DataFrame) -> dict[str, dict]:
    """Roda a grade de todos os candidatos e confere contra o que está no código."""
    print("\n--- Busca de hiperparâmetros (top 3 por modelo, AuROC de validação cruzada) ---")
    achados = {nome: buscar_hiperparametros(treino, nome) for nome in GRADES}
    print("\n  vencedores:")
    for nome, params in achados.items():
        gravado = (
            {k.replace("modelo__", ""): v for k, v in MELHORES.items()}
            if nome == "HistGB regularizado"
            else MELHORES_BASELINES[nome]
        )
        marca = "OK" if params == gravado else f"DIVERGE do código ({gravado})"
        print(f"    {nome:<24}{params}  -> {marca}")
    return achados


# --------------------------------------------------------------------------- #
# Comparação e treino final
# --------------------------------------------------------------------------- #


def comparar(treino: pd.DataFrame, oot: pd.DataFrame) -> pd.DataFrame:
    """Treina cada candidato no treino e mede treino × out-of-time."""
    x_tr, y_tr = matriz(treino), treino[ALVO]
    x_oo, y_oo = matriz(oot), oot[ALVO]
    linhas = []
    for nome, (estimador, linear) in candidatos().items():
        pipe = montar_pipeline(estimador, linear=linear).fit(x_tr, y_tr)
        m_tr = metricas(y_tr, pipe.predict_proba(x_tr)[:, 1])
        m_oo = metricas(y_oo, pipe.predict_proba(x_oo)[:, 1])
        linhas.append(
            {
                "modelo": nome,
                "AUC treino": m_tr["auroc"],
                "AUC OOT": m_oo["auroc"],
                "queda": m_tr["auroc"] - m_oo["auroc"],
                "Gini OOT": m_oo["gini"],
                "KS OOT": m_oo["ks"],
                "Brier OOT": m_oo["brier"],
                "viés OOT": m_oo["vies"],
            }
        )
    return pd.DataFrame(linhas)


def treinar_final(a: pd.DataFrame, calibrar: bool = True):
    """Modelo de produção: reajustado em **toda** a Base A, com calibração.

    Depois que a validação out-of-time já respondeu "esta configuração
    generaliza?", segurar 2024 fora do treino só joga fora um terço dos dados —
    e é justamente o terço mais próximo, no tempo, da Base B que será pontuada.
    A configuração está congelada; nenhuma decisão é tomada a partir daqui.

    `CalibratedClassifierCV` com `cv=5` ajusta a curva prevista→observada em
    dobras internas e ainda agrega as cinco dobras, o que sozinho vale +0,0075
    de AuROC out-of-time (0,7361 -> 0,7436).

    Método **sigmoide (Platt)**, não isotônico. Os dois empatam em discriminação
    (0,7436 contra 0,7437) e o isotônico é ligeiramente pior no Brier, mas o que
    decide é o extremo: por ser uma escada, o isotônico devolve `PD = 1,0000`
    para 2 contratos da Base A. PD de exatamente 1 é indefensável como
    estimativa e envenena a perda esperada e o preço. A sigmoide vai no máximo
    a 0,8556.
    """
    estimador = HistGradientBoostingClassifier(
        random_state=SEED, **{k.replace("modelo__", ""): v for k, v in MELHORES.items()}
    )
    pipe = montar_pipeline(estimador)
    if calibrar:
        pipe = CalibratedClassifierCV(pipe, method="sigmoid", cv=5)
    return pipe.fit(matriz(a), a[ALVO])


def importancias(treino: pd.DataFrame, oot: pd.DataFrame, repeticoes: int = 10) -> pd.DataFrame:
    """Queda de AuROC ao embaralhar cada variável, medida no out-of-time.

    Leitura correta: isto **sugere** hipótese, não a confirma. Importância
    negativa (a variável embaralhada melhora o modelo) significa que naquela
    janela ela atrapalhava — não que deva sair. Ver `validacao_encadeada()`,
    que é o teste que de fato decide.
    """
    from sklearn.inspection import permutation_importance

    pipe = montar_pipeline(
        HistGradientBoostingClassifier(
            random_state=SEED, **{k.replace("modelo__", ""): v for k, v in MELHORES.items()}
        )
    ).fit(matriz(treino), treino[ALVO])
    r = permutation_importance(
        pipe, matriz(oot), oot[ALVO], scoring="roc_auc",
        n_repeats=repeticoes, random_state=SEED, n_jobs=-1,
    )
    return pd.DataFrame(
        {"variável": matriz(oot).columns, "queda_auc": r.importances_mean, "dp": r.importances_std}
    ).sort_values("queda_auc", ascending=False)


def validacao_encadeada(a: pd.DataFrame, conjuntos: dict[str, list[str]]) -> pd.DataFrame:
    """Compara conjuntos de variáveis em janelas temporais **anteriores** a 2024.

    Existe porque o out-of-time de 2024 já foi consultado muitas vezes e, por
    isso, deixou de ser imparcial para decidir algo novo. Estas três janelas
    nunca foram usadas para nada, e é nelas que a poda de variáveis é julgada.
    """
    mes = a["data_originacao"].dt.month
    janelas = [
        ("2022 -> 2023-S1", a["ano"] == 2022, (a["ano"] == 2023) & (mes <= 6)),
        ("2022 -> 2023", a["ano"] == 2022, a["ano"] == 2023),
        ("2022+23-S1 -> 2023-S2", (a["ano"] == 2022) | ((a["ano"] == 2023) & (mes <= 6)),
         (a["ano"] == 2023) & (mes > 6)),
    ]
    linhas = []
    for nome, feats in conjuntos.items():
        linha = {"conjunto": nome, "n": len(feats)}
        for rotulo, marca_treino, marca_val in janelas:
            t, v = a[marca_treino], a[marca_val]
            modelo_cal = CalibratedClassifierCV(
                _pipeline_para(feats), method="sigmoid", cv=5
            ).fit(t[feats], t[ALVO])
            linha[rotulo] = roc_auc_score(v[ALVO], modelo_cal.predict_proba(v[feats])[:, 1])
        linha["média"] = float(np.mean([linha[j[0]] for j in janelas]))
        # A coluna que **não** decide nada, mostrada para o contraste: é nela que
        # a poda parece boa, e é ela que já foi consultada dezenas de vezes.
        treino, oot = dividir(a)
        cal = CalibratedClassifierCV(_pipeline_para(feats), method="sigmoid", cv=5).fit(
            treino[feats], treino[ALVO]
        )
        linha["OOT 2024"] = roc_auc_score(oot[ALVO], cal.predict_proba(oot[feats])[:, 1])
        linhas.append(linha)
    return pd.DataFrame(linhas)


def _pipeline_para(feats: list[str]):
    """Pipeline de árvore restrito a um subconjunto de variáveis."""
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder

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
            (
                "modelo",
                HistGradientBoostingClassifier(
                    random_state=SEED, **{k.replace("modelo__", ""): v for k, v in MELHORES.items()}
                ),
            ),
        ]
    )


def prever(modelo, df: pd.DataFrame) -> np.ndarray:
    """PD de cada linha. Único ponto de entrada para pontuar qualquer base."""
    return modelo.predict_proba(matriz(df))[:, 1]


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #


def main(refazer_busca: bool = False, podar: bool = False) -> None:
    import joblib

    a = carregar_base_a()
    treino, oot = dividir(a)

    print("=" * 96)
    print("MODELAGEM DA PD — Desafio AutoCred")
    print("=" * 96)
    print(
        f"treino {treino['safra'].min()}–{treino['safra'].max()}: n={len(treino):,} "
        f"(PD={treino[ALVO].mean():.4f}) | OOT {oot['safra'].min()}–{oot['safra'].max()}: "
        f"n={len(oot):,} (PD={oot[ALVO].mean():.4f})"
    )

    if refazer_busca:
        buscar_todos(treino)

    print("\n--- Comparação de candidatos (treinados em 2022-2023) ---\n")
    tabela = comparar(treino, oot)
    print(
        tabela.round(
            {"AUC treino": 4, "AUC OOT": 4, "queda": 4, "Gini OOT": 3, "KS OOT": 3,
             "Brier OOT": 4, "viés OOT": 4}
        ).to_string(index=False)
    )

    vencedor = tabela.loc[tabela["AUC OOT"].idxmax(), "modelo"]
    print(f"\n  Vencedor por AuROC out-of-time: {vencedor}")

    print("\n--- Calibração do vencedor no out-of-time ---\n")
    estimador, linear = candidatos()[vencedor]
    pipe = montar_pipeline(estimador, linear=linear).fit(matriz(treino), treino[ALVO])
    p_oot = pipe.predict_proba(matriz(oot))[:, 1]
    print(tabela_calibracao(oot[ALVO], p_oot).round({"prevista": 4, "observada": 4, "razão": 2}).to_string())

    m_sem = metricas(oot[ALVO], p_oot)
    calibrado = CalibratedClassifierCV(
        montar_pipeline(estimador, linear=linear), method="sigmoid", cv=5
    ).fit(matriz(treino), treino[ALVO])
    m_com = metricas(oot[ALVO], calibrado.predict_proba(matriz(oot))[:, 1])
    print(f"\n  {'':<14}{'AuROC':>9}{'Brier':>9}{'PD prevista':>13}{'PD observada':>14}")
    for rotulo, m in [("sem calibrar", m_sem), ("calibrado", m_com)]:
        print(
            f"  {rotulo:<14}{m['auroc']:>9.4f}{m['brier']:>9.4f}"
            f"{m['pd_prevista']:>13.4f}{m['pd_observada']:>14.4f}"
        )

    print("\n--- Importância por permutação no out-of-time ---\n")
    imp = importancias(treino, oot)
    print(imp.round(4).to_string(index=False))
    ARTEFATOS.mkdir(exist_ok=True)
    imp.to_csv(ARTEFATOS / "importancias.csv", index=False, encoding="utf-8")
    print(
        "\n  Importância negativa não manda remover a variável: significa apenas que,\n"
        "  nesta janela, embaralhá-la ajudou. Quem decide poda é --poda, abaixo."
    )

    if podar:
        print("\n--- Poda de variáveis julgada em janelas anteriores a 2024 ---\n")
        principais = imp.nlargest(7, "queda_auc")["variável"].tolist()
        quase_nulas = imp.nsmallest(6, "queda_auc")["variável"].tolist()
        conjuntos = {
            f"{len(FEATURES)} (atual)": FEATURES,
            f"{len(CANDIDATAS)} (com ano_modelo)": CANDIDATAS,
            f"{len(FEATURES) - 2} sem valor_bem e ltv": [
                f for f in FEATURES if f not in ("valor_bem", "ltv")
            ],
            f"{len(FEATURES) - 6} sem as de importância ~0": [
                f for f in FEATURES if f not in quase_nulas
            ],
            "7 principais": principais,
        }
        enc = validacao_encadeada(a, conjuntos)
        print(enc.round(4).to_string(index=False))
        # O relatório do modelo cita esta tabela — é a evidência de que a poda
        # que parecia boa no out-of-time de 2024 não se sustenta em janelas
        # independentes. Fica no disco para o relatório não depender de quem
        # copiou o terminal.
        enc.to_csv(ARTEFATOS / "validacao_encadeada.csv", index=False, encoding="utf-8")
        print(
            "\n  Se a ordem aqui divergir da ordem no out-of-time de 2024, a vantagem em 2024\n"
            "  era coincidência de janela. Ver docs/04-modelo.md, decisão 5."
        )

    print("\n--- Deriva do nível da PD entre safras ---\n")
    semestre = a["data_originacao"].dt.year.astype(str) + "-S" + (
        (a["data_originacao"].dt.month > 6).astype(int) + 1
    ).astype(str)
    for s, g in a.groupby(semestre):
        print(f"  {s}   n={len(g):5,}   PD={g[ALVO].mean():.4f}")
    print(
        "\n  A PD cai de 9,57% (2023-S1) para 6,51% (2024-S2). Base B é 2025-S1 e Base C é\n"
        "  2025-S2: o nível calibrado na Base A tende a superestimar a PD dessas safras.\n"
        "  Na submissão do modelo isso é irrelevante (AuROC só lê ordenação); na política,\n"
        "  não — e empurra em sentido contrário ao viés de aprovados. Ver docs/04-modelo.md."
    )

    print("\n--- Modelo final: reajustado em toda a Base A ---")
    final = treinar_final(a)
    ARTEFATOS.mkdir(exist_ok=True)
    joblib.dump(final, ARQ_MODELO)
    pd_a = prever(final, a)
    print(f"  serializado em artefatos/{ARQ_MODELO.name} ({ARQ_MODELO.stat().st_size / 1024:.0f} KB)")
    print(f"  PD média na Base A: {pd_a.mean():.4f} | observada: {a[ALVO].mean():.4f}")
    print(f"  faixa de PD: {pd_a.min():.4f} a {pd_a.max():.4f}")

    destino = ARTEFATOS / "modelo_comparacao.csv"
    tabela.to_csv(destino, index=False, encoding="utf-8")
    registrar_execucao(
        "modelo",
        {
            "etapa": "src/modelo",
            "janela_treino": f"< {ANO_CORTE}",
            "n_treino": int(len(treino)),
            "n_oot": int(len(oot)),
            "vencedor": vencedor,
            "hiperparametros": MELHORES,
            "hiperparametros_baselines": MELHORES_BASELINES,
            "auc_oot": round(float(tabela["AUC OOT"].max()), 4),
            "calibracao": "sigmoid (Platt) cv=5",
            "modelo": ARQ_MODELO.name,
            "saida": destino.name,
        },
    )
    print(f"  comparação gravada em artefatos/{destino.name}")
    print("\n" + "=" * 96)


if __name__ == "__main__":
    main(refazer_busca="--busca" in sys.argv, podar="--poda" in sys.argv)
