"""EDA dirigida — Desafio AutoCred (versão script).

Não é varredura: são três perguntas cujas respostas mudam o que `features.py` e
`score.py` vão fazer.

  1. WoE/IV por variável      -> quais features ficam e como agrupar em faixas
  2. O faltante é informativo? -> se for, a ausência vira feature
  3. Monotonicidade            -> relação que sobe e desce vira faixa indefensável

Regra que este script respeita e que é fácil de violar: **tudo é calculado na
janela de treino (2022-2023)**. Escolher variável olhando 2024 contamina a
validação out-of-time — é o vazamento do slide 5 da mentoria 02, na versão sutil.
A safra de 2024 aparece só para conferir estabilidade, nunca para decidir.

A lógica de binning, WoE, IV e PSI mora em `src/exploracao.py`; aqui só há
orquestração e impressão. O notebook `01-exploracao.ipynb` consome exatamente as
mesmas funções, então os dois não podem divergir.

Uso:
    PYTHONIOENCODING=utf-8 python notebooks/01-exploracao.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from dados import (  # noqa: E402
    ALVO,
    CATEGORICAS,
    CANDIDATAS,
    carregar_base_a,
    carregar_base_c,
    mapear_base_c,
    registrar_execucao,
)
from exploracao import (  # noqa: E402
    AUSENTE,
    classificar_psi,
    pd_com_ic,
    resumo_variaveis,
)

ANO_CORTE = 2024  # treino: < 2024 | conferência de estabilidade: == 2024


def main() -> None:
    a = carregar_base_a()
    treino = a[a["ano"] < ANO_CORTE]
    conferencia = a[a["ano"] == ANO_CORTE]
    base_c = mapear_base_c(carregar_base_c())

    print("=" * 92)
    print("EDA DIRIGIDA — decisões calculadas em 2022-2023; 2024 só confere estabilidade")
    print(
        f"treino n={len(treino):,} (PD={treino[ALVO].mean():.4f}) | "
        f"conferência n={len(conferencia):,} (PD={conferencia[ALVO].mean():.4f})"
    )
    print("=" * 92)

    resumo, tabelas = resumo_variaveis(
        treino, conferencia, base_c, CANDIDATAS, CATEGORICAS, ALVO
    )

    print("\n### 1. PODER PREDITIVO (IV) — ordenado\n")
    print(
        resumo[["variável", "IV_treino", "IV_conferencia", "força", "rho", "inversões", "PSI_aplicacao"]]
        .round({"IV_treino": 4, "IV_conferencia": 4, "rho": 2, "PSI_aplicacao": 3})
        .to_string(index=False)
    )
    fracas = resumo.loc[resumo.IV_treino < 0.02, "variável"].tolist()
    print(f"\nCandidatas a descarte (IV < 0,02): {', '.join(fracas) or 'nenhuma'}")
    print(f"IV total somado: {resumo.IV_treino.sum():.4f}")

    print("\n### 2. O FALTANTE É INFORMATIVO?\n")
    print(f"{'coluna':<26}{'% ausente':>10}{'PD ausente':>12}{'PD presente':>13}{'razão':>8}")
    for feat in ["renda_mensal_declarada", "tempo_emprego_meses", "score_bureau"]:
        m = treino[feat].isna()
        pd_aus, pd_pres = treino.loc[m, ALVO].mean(), treino.loc[~m, ALVO].mean()
        print(
            f"{feat:<26}{m.mean():>10.2%}{pd_aus:>12.2%}{pd_pres:>13.2%}{pd_aus / pd_pres:>8.2f}x"
        )
    print("\n(regra: razão longe de 1,00 = a ausência carrega sinal e deve virar indicador)")

    print("\n### 3. MONOTONICIDADE (numéricas)\n")
    num = resumo[~resumo["variável"].isin(CATEGORICAS)].sort_values(
        "rho", key=abs, ascending=False
    )
    print(f"{'variável':<26}{'rho':>7}{'inversões':>11}  veredito")
    for _, r in num.iterrows():
        print(f"{r['variável']:<26}{r.rho:>7.2f}{r.inversões:>11d}  {r.monotonicidade}")

    print("\n### 4. WoE DAS TRÊS VARIÁVEIS MAIS FORTES\n")
    for feat in resumo["variável"].head(3):
        iv_feat = resumo.set_index("variável").loc[feat, "IV_treino"]
        print(f"--- {feat} (IV={iv_feat:.4f}) ---")
        t = tabelas[feat]
        print(
            t.assign(pd=lambda d: (d["pd"] * 100).round(2), woe=lambda d: d.woe.round(3))[
                ["n", "maus", "pd", "woe"]
            ].to_string()
        )
        print()

    print("### 5. ESTABILIDADE DE POPULAÇÃO A -> C (PSI)\n")
    for _, r in resumo.sort_values("PSI_aplicacao", ascending=False).head(8).iterrows():
        print(f"  {r['variável']:<26}{r.PSI_aplicacao:>7.3f}  {classificar_psi(r.PSI_aplicacao)}")

    print("\n### 6. SUPORTE AMOSTRAL: domínio de cada variável, treino vs aplicação\n")
    print(
        f"  {'variável':<26}{'min A':>11}{'max A':>11}{'min C':>11}{'max C':>11}"
        f"{'% de C fora':>13}"
    )
    fora_por_var = {}
    for feat in CANDIDATAS:
        if feat in CATEGORICAS or base_c[feat].notna().sum() == 0:
            continue
        lo, hi = treino[feat].min(), treino[feat].max()
        marca = (base_c[feat] < lo) | (base_c[feat] > hi)
        fora_por_var[feat] = marca
        if marca.mean() > 0.01:
            print(
                f"  {feat:<26}{lo:>11.5g}{hi:>11.5g}"
                f"{base_c[feat].min():>11.5g}{base_c[feat].max():>11.5g}{marca.mean():>12.1%}"
            )

    # Os cortes que a política antiga aplicava não estão escritos em lugar nenhum
    # do material — estão no domínio das variáveis. `ano_modelo` fica de fora do
    # perímetro por ser deslocamento de calendário, não regra de crédito.
    perimetro = [f for f in fora_por_var if f != "ano_modelo"]
    combinado = pd.concat([fora_por_var[f] for f in perimetro], axis=1).any(axis=1)
    print(
        f"\n  Propostas de C fora do domínio em ao menos uma variável de crédito: "
        f"{combinado.mean():.1%} ({int(combinado.sum())} de {len(base_c)})"
    )
    print(f"  (perímetro considerado: {', '.join(perimetro)})")

    destino = RAIZ / "artefatos" / "eda_iv_psi.csv"
    resumo.to_csv(destino, index=False, encoding="utf-8")
    registrar_execucao(
        "eda_exploracao",
        {
            "etapa": "notebooks/01-exploracao",
            "janela_treino": f"< {ANO_CORTE}",
            "n_treino": int(len(treino)),
            "iv_total": round(float(resumo.IV_treino.sum()), 4),
            "saida": destino.name,
        },
    )
    print(f"\nTabela completa gravada em artefatos/{destino.name}")


if __name__ == "__main__":
    main()
