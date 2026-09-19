"""Carga, validação de schema e defesa contra vazamento — Desafio AutoCred.

Este é o único módulo que lê `bases/`. Todo o resto do pipeline recebe DataFrames
já validados, para que exista um lugar só onde a regra antivazamento é aplicada.

Princípio central: a lista de colunas proibidas **não é digitada aqui**. Ela é lida
do dicionário de dados oficial (coluna `Disponível na concessão?`). Lista manual
sai de sincronia em silêncio; dicionário, não.

Uso:
    PYTHONIOENCODING=utf-8 python src/dados.py     # roda a auditoria completa
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Caminhos e constantes de reprodutibilidade
# --------------------------------------------------------------------------- #

RAIZ = Path(__file__).resolve().parent.parent
BASES = RAIZ / "bases"
ARTEFATOS = RAIZ / "artefatos"

SEED = 42

ARQ_A = BASES / "base_A_autocred_base_desenvolvimento.csv"
ARQ_B = BASES / "base_B_autocred_base_teste_modelo.csv"
ARQ_C = BASES / "base_C_autocred_base_politica.csv"
ARQ_DICIONARIO = BASES / "AutoCred_Dicionario_de_Dados.xlsx"

ALVO = "default_90_12"

# --------------------------------------------------------------------------- #
# Conjunto de variáveis do modelo
# --------------------------------------------------------------------------- #
# A separação abaixo não é estética: ela responde à pergunta "esta coluna existe
# na Base C?". A Base C traz as condições *desejadas* pelo cliente, não as
# contratadas — quem contrata as condições somos nós, via política.

# Atributos do proponente e do bem. Existem em C exatamente com o mesmo nome e
# não dependem de nenhuma decisão nossa.
COLS_CLIENTE = [
    "idade_cliente",
    "ocupacao",
    "renda_mensal_declarada",
    "tempo_emprego_meses",
    "tipo_residencia",
    "score_bureau",
    "qtd_restricoes_ativas",
    "qtd_consultas_bureau_3m",
    "possui_avalista",
    "canal_originacao",
    "idade_veiculo_anos",
    "ano_modelo",
    "valor_bem",
]

# Estrutura da operação. Em C chegam como `*_desejado`; viram estas colunas
# depois que a política decide as condições ofertadas (ver `mapear_base_c`).
COLS_NEGOCIO = [
    "valor_financiado",
    "valor_entrada",
    "ltv",
    "prazo_meses",
]

# Comprometimento de renda = parcela / renda declarada. Não existe em C, mas é
# *recalculável* a partir das condições que ofertarmos. Vale +0,0132 de AuROC
# out-of-time (0,7245 -> 0,7377), o maior ganho marginal de uma única variável.
COLS_DERIVADAS = ["comprometimento_renda"]

# Tudo que a exploração examina. `notebooks/01-exploracao.py` usa esta lista:
# diagnosticar uma variável é o que permite descartá-la com evidência, então ela
# precisa ser medida mesmo quando a conclusão é "não entra".
CANDIDATAS = COLS_CLIENTE + COLS_NEGOCIO + COLS_DERIVADAS

# Reprovadas pela exploração (ver `docs/02-exploracao.md`):
#   ano_modelo -> IV 0,013 com PSI 1,394. O PSI alto é artefato de calendário:
#   proposta de 2025 traz modelo 2025, que o treino (máximo 2022) nunca viu —
#   31,8% da Base C fica acima do domínio, e árvore não extrapola. Contribuição
#   medida: zero. Removê-la não altera o AuROC em nenhuma casa decimal (0,7434
#   out-of-time com e sem), e elimina uma variável fora de domínio.
EXCLUIDAS = ["ano_modelo"]

FEATURES = [c for c in CANDIDATAS if c not in EXCLUIDAS]

# Permitidas pelo dicionário, mas fora até da exploração como preditoras:
#   taxa_juros_am, parcela_mensal -> são *decisão nossa* na Base C, e medidas
#   isoladamente pioram o AuROC out-of-time (0,7245 -> 0,7155 e 0,7171).
COLS_DESCARTADAS = ["taxa_juros_am", "parcela_mensal"]

CATEGORICAS = [
    "ocupacao",
    "tipo_residencia",
    "possui_avalista",
    "canal_originacao",
]


# --------------------------------------------------------------------------- #
# Dicionário de dados: a fonte da verdade sobre vazamento
# --------------------------------------------------------------------------- #


def carregar_dicionario() -> pd.DataFrame:
    """Aba `Bases A e B` do dicionário oficial, com as colunas de papel e
    disponibilidade na concessão."""
    return pd.read_excel(ARQ_DICIONARIO, sheet_name="Bases A e B")


def colunas_proibidas() -> list[str]:
    """Colunas marcadas com `NÃO` em `Disponível na concessão?`.

    Derivado do dicionário a cada execução, de propósito: se o material for
    atualizado, a defesa acompanha sem ninguém precisar lembrar de editar código.
    """
    dic = carregar_dicionario()
    marca = dic["Disponível na concessão?"].astype(str).str.strip().str.upper()
    return dic.loc[marca == "NÃO", "Coluna"].tolist()


class VazamentoDetectado(Exception):
    """Erguida quando uma coluna pós-concessão entra na lista de preditoras."""


def validar_features(features: list[str] | None = None) -> list[str]:
    """Falha alto e cedo se qualquer preditora for indisponível na concessão.

    Chamada por `features.py` e `modelo.py` antes de qualquer `fit`. Um modelo
    que treina com vazamento é pior que um modelo que não treina.
    """
    features = list(FEATURES if features is None else features)
    proibidas = set(colunas_proibidas())
    invasoras = sorted(set(features) & proibidas)
    if invasoras:
        raise VazamentoDetectado(
            "Coluna pós-concessão na lista de preditoras: "
            + ", ".join(invasoras)
            + ". O dicionário marca essas colunas como indisponíveis na concessão."
        )
    return features


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #


def _ler(caminho: Path, coluna_data: str) -> pd.DataFrame:
    df = pd.read_csv(caminho, encoding="utf-8")
    df[coluna_data] = pd.to_datetime(df[coluna_data])
    return df


def carregar_base_a() -> pd.DataFrame:
    """10.000 contratos de 2022-2024, com alvo e realizados. Acrescenta `safra`
    (o mês de originação) e `ano`, usados no split out-of-time."""
    df = _ler(ARQ_A, "data_originacao")
    df["safra"] = df["data_originacao"].dt.to_period("M")
    df["ano"] = df["data_originacao"].dt.year
    return df


def carregar_base_b() -> pd.DataFrame:
    """3.000 contratos de jan-jun/2025, sem alvo. É o teste oficial de AuROC."""
    df = _ler(ARQ_B, "data_originacao")
    df["safra"] = df["data_originacao"].dt.to_period("M")
    df["ano"] = df["data_originacao"].dt.year
    return df


def carregar_base_c() -> pd.DataFrame:
    """5.000 propostas do 2º semestre de 2025, em condições *desejadas*."""
    df = _ler(ARQ_C, "data_proposta")
    df["safra"] = df["data_proposta"].dt.to_period("M")
    df["ano"] = df["data_proposta"].dt.year
    return df


def mapear_base_c(
    base_c: pd.DataFrame,
    prazo_meses: pd.Series | None = None,
    valor_entrada: pd.Series | None = None,
    parcela_mensal: pd.Series | None = None,
) -> pd.DataFrame:
    """Traduz a Base C para o vocabulário do modelo.

    Sem argumentos, assume as condições **desejadas** pelo cliente — é a primeira
    passada, usada para dar um score inicial e enquadrar a proposta numa faixa.
    Com as condições ofertadas, devolve a versão a ser usada na decisão final.

    O `comprometimento_renda` só pode ser calculado quando `parcela_mensal` é
    conhecida; sem ela fica `NaN`, e o imputador do pipeline assume — que é
    exatamente o tratamento que a Base A dá aos 7,7% de renda ausente.
    """
    df = base_c.copy()
    df["prazo_meses"] = base_c["prazo_desejado_meses"] if prazo_meses is None else prazo_meses
    df["valor_entrada"] = (
        base_c["valor_entrada_desejada"] if valor_entrada is None else valor_entrada
    )
    df["valor_financiado"] = base_c["valor_bem"] - df["valor_entrada"]
    df["ltv"] = df["valor_financiado"] / base_c["valor_bem"]
    df["comprometimento_renda"] = (
        pd.Series(float("nan"), index=df.index, dtype="float64")
        if parcela_mensal is None
        else parcela_mensal / base_c["renda_mensal_declarada"]
    )
    return df


# --------------------------------------------------------------------------- #
# Auditoria
# --------------------------------------------------------------------------- #


def auditar() -> None:
    """Relatório de sanidade das três bases. Não escreve nada: só imprime."""
    a, b, c = carregar_base_a(), carregar_base_b(), carregar_base_c()

    print("=" * 78)
    print("AUDITORIA DAS BASES — Desafio AutoCred")
    print("=" * 78)

    for nome, df, chave in [("A", a, "id_contrato"), ("B", b, "id_contrato"), ("C", c, "id_proposta")]:
        print(
            f"\nBase {nome}: {len(df):>6,} linhas | {df.shape[1]:>2} colunas | "
            f"{df['safra'].min()} a {df['safra'].max()}"
        )
        print(f"  ids duplicados .......... {df[chave].duplicated().sum()}")
        print(f"  linhas duplicadas ....... {df.drop(columns=[chave]).duplicated().sum()}")

    print("\n--- Alvo (Base A) ---")
    print(f"  PD 90/12 global ......... {a[ALVO].mean():.4f}  ({int(a[ALVO].sum())} defaults)")
    por_ano = a.groupby("ano")[ALVO].agg(["size", "mean"])
    for ano, linha in por_ano.iterrows():
        print(f"  safra {ano} ............. {linha['mean']:.4f}  (n={int(linha['size'])})")
    print(f"  nulos no alvo ........... {a[ALVO].isna().sum()}")

    print("\n--- Defesa antivazamento ---")
    proibidas = colunas_proibidas()
    print(f"  proibidas pelo dicionário ({len(proibidas)}): {', '.join(proibidas)}")
    presentes_em_c = [col for col in proibidas if col in c.columns]
    print(f"  proibidas presentes na Base C: {', '.join(presentes_em_c) or 'nenhuma'}")
    validar_features()
    print(f"  FEATURES ({len(FEATURES)}) passou na validação: OK")

    print("\n--- Cobertura das features na Base C ---")
    faltantes = [f for f in FEATURES if f not in c.columns]
    print(f"  ausentes em C, resolvidas por mapear_base_c(): {', '.join(faltantes)}")
    mapeada = mapear_base_c(c)
    restantes = [f for f in FEATURES if f not in mapeada.columns]
    print(f"  ainda ausentes após o mapeamento: {', '.join(restantes) or 'nenhuma'}")

    print("\n--- Valores ausentes (% por base) ---")
    com_nulos = [f for f in FEATURES if a[f].isna().any() if f in a.columns]
    print(f"  {'coluna':<26}{'A':>8}{'B':>8}{'C':>8}")
    for col in com_nulos:
        pc = mapeada[col].isna().mean() if col in mapeada.columns else float("nan")
        print(f"  {col:<26}{a[col].isna().mean():>8.3%}{b[col].isna().mean():>8.3%}{pc:>8.3%}")

    print("\n--- Deslocamento de população A -> C (viés de aprovados) ---")
    cortes = [
        ("score_bureau < 500", lambda d: d["score_bureau"] < 500),
        ("alguma restrição ativa", lambda d: d["qtd_restricoes_ativas"] > 0),
        ("LTV > 90%", lambda d: d["ltv"] > 0.90),
        ("prazo 60 meses", lambda d: d["prazo_meses"] == 60),
    ]
    print(f"  {'corte':<26}{'A':>8}{'C':>8}{'razão':>8}")
    for rotulo, teste in cortes:
        pa, pc = teste(a).mean(), teste(mapeada).mean()
        print(f"  {rotulo:<26}{pa:>8.1%}{pc:>8.1%}{pc / pa:>8.2f}x")

    print("\n" + "=" * 78)


def registrar_execucao(nome: str, metadados: dict) -> Path:
    """Grava `artefatos/<nome>.json` com seed, data e versões das bibliotecas.

    Todo script que produz artefato chama isto. É o que sustenta a parte de
    reprodutibilidade dos 10 pontos de qualidade técnica.
    """
    import sklearn

    ARTEFATOS.mkdir(exist_ok=True)
    registro = {
        "executado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "seed": SEED,
        "python": sys.version.split()[0],
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        **metadados,
    }
    destino = ARTEFATOS / f"{nome}.json"
    destino.write_text(json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")
    return destino


if __name__ == "__main__":
    auditar()
