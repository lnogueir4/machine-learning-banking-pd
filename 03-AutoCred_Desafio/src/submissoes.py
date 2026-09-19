"""Geração e conferência dos dois arquivos de submissão — Desafio AutoCred.

Este módulo é curto de propósito. Gerar os CSVs é trivial: o modelo já está
treinado, a política já está decidida, e o que sobra é escrever duas tabelas.
O valor está na outra metade — **conferir**.

Três disciplinas que este módulo existe para impor:

  - **Nada é digitado à mão.** As duas submissões saem daqui, do modelo
    serializado e da regra congelada em `politica.ESCOLHIDA`. Um número
    corrigido manualmente num CSV é indetectável e invalida a cadeia inteira.

  - **A conferência lê o arquivo do disco, não o DataFrame da memória.** Erro
    de escrita — BOM, separador, `48.0` onde se esperava `48`, índice vazado
    para a primeira coluna — não aparece no objeto que gerou o arquivo. Só
    aparece relendo. `conferir()` relê.

  - **A tabela de faixas da documentação bate com a submissão linha a linha.**
    São 10 pontos de coerência no enunciado, e a única forma de garanti-los é
    nenhuma das cópias existir em dois lugares: a submissão é derivada da mesma
    `Regra`, e a conferência prova que taxa e entrada são constantes dentro de
    cada faixa e iguais às de `artefatos/tabela_politica.csv`.

Uso:
    PYTHONIOENCODING=utf-8 python src/submissoes.py            # gera e confere
    PYTHONIOENCODING=utf-8 python src/submissoes.py --conferir  # só confere o que já existe
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from dados import ARTEFATOS, RAIZ, carregar_base_b, carregar_base_c, registrar_execucao
from features import matriz
from politica import (
    ESCOLHIDA,
    MAX_CET_AM,
    MIN_APROVACAO,
    PRAZOS_VALIDOS,
    TAXA_MINIMA,
    aplicar,
    enquadrar,
)
from score import CORTES, faixa

ENTREGAVEIS = RAIZ / "entregaveis"

ARQ_MODELO_SAIDA = ENTREGAVEIS / "submissao_modelo.csv"
ARQ_POLITICA_SAIDA = ENTREGAVEIS / "submissao_politica.csv"
ARQ_MODELO_EXEMPLO = ENTREGAVEIS / "submissao_modelo_EXEMPLO.csv"
ARQ_POLITICA_EXEMPLO = ENTREGAVEIS / "submissao_politica_EXEMPLO.csv"

COLUNAS_MODELO = ["id_contrato", "pd"]
COLUNAS_POLITICA = [
    "id_proposta", "pd", "score_1a10", "decisao",
    "taxa_am", "prazo_meses", "pct_entrada_minima",
]

# Casas decimais da PD publicada.
#
# O exemplo do desafio usa 4. Medido contra a PD out-of-fold da Base A, 4 casas
# empatam 78% dos valores e custam 0,00002 de AuROC — praticamente nada, porque
# um AuROC bem implementado pontua par empatado como 0,5 e não como erro.
# Então a razão de usar 6 **não** é AuROC, e dizer que é seria inventar um
# ganho que a medição nega.
#
# A razão é outra e é específica da política: a 4 casas, 19 das 5.000 propostas
# caem do outro lado de um corte de faixa. Quem reconferir `faixa(pd)` a partir
# do CSV encontraria uma faixa diferente da que a política usou, em 19 linhas —
# e são 10 pontos de coerência. A 6 casas, zero. `conferir()` prova isso.
CASAS_PD = 6

# Colunas que ficam **vazias** quando a decisão é NEGAR. É o que o arquivo de
# exemplo faz, e faz sentido: proposta negada não tem preço, prazo nem entrada.
COLUNAS_SO_DE_APROVADO = ["taxa_am", "prazo_meses", "pct_entrada_minima"]


# --------------------------------------------------------------------------- #
# Geração
# --------------------------------------------------------------------------- #


def _modelo():
    import joblib

    from modelo import ARQ_MODELO

    return joblib.load(ARQ_MODELO)


def submissao_modelo() -> pd.DataFrame:
    """`id_contrato, pd` para os 3.000 contratos da Base B.

    A Base B vem com as mesmas colunas da A, então não precisa da tradução que
    a Base C exige — `matriz()` já resolve, e é ela que refaz a checagem
    antivazamento antes de qualquer previsão.
    """
    b = carregar_base_b()
    p = _modelo().predict_proba(matriz(b))[:, 1]
    return pd.DataFrame(
        {"id_contrato": b["id_contrato"].to_numpy(), "pd": np.round(p, CASAS_PD)}
    )


def submissao_politica() -> pd.DataFrame:
    """As sete colunas da política para as 5.000 propostas da Base C.

    Duas escolhas de coerência, ambas deliberadas:

    **A `pd` publicada é a do enquadramento**, calculada nas condições que o
    cliente pediu — a mesma de que a faixa saiu. Poderia ser a PD sob as
    condições ofertadas, que é a que de fato precifica o contrato e a que a
    simulação usa internamente. Não é, porque aí `faixa(pd)` deixaria de
    reproduzir `score_1a10` e a submissão se contradiria sozinha. O número que
    vai no arquivo é o que sustenta a coluna ao lado dele.

    **A faixa é calculada a partir da `pd` já arredondada.** Arredondar depois
    de classificar deixaria 19 linhas em que um terceiro, recalculando
    `faixa(pd)` a partir do CSV, chegaria a outra faixa.
    """
    c = carregar_base_c()
    quadro = enquadrar(c)
    oferta = aplicar(ESCOLHIDA, c, quadro)

    pd_publicada = np.round(quadro["pd_enquadramento"].to_numpy(), CASAS_PD)
    aprovado = oferta["decisao"].to_numpy() == "APROVAR"

    sub = pd.DataFrame(
        {
            "id_proposta": c["id_proposta"].to_numpy(),
            "pd": pd_publicada,
            "score_1a10": faixa(pd_publicada).astype("int64"),
            "decisao": oferta["decisao"].to_numpy(),
            "taxa_am": np.where(aprovado, oferta["taxa_am"].to_numpy(), np.nan),
            # `Int64` (com I maiúsculo) é o inteiro que aceita ausente. Sem ele,
            # o `NaN` das linhas negadas viraria float e gravaria `48.0` nas
            # aprovadas — o que o exemplo do desafio não faz.
            "prazo_meses": pd.Series(
                np.where(aprovado, oferta["prazo_meses"].to_numpy(), np.nan)
            ).astype("Int64"),
            "pct_entrada_minima": np.where(
                aprovado, oferta["pct_entrada_minima"].to_numpy(), np.nan
            ),
        }
    )
    return sub[COLUNAS_POLITICA]


def gravar(df: pd.DataFrame, destino: Path) -> Path:
    """Escreve o CSV no formato do desafio: sem índice, UTF-8, decimal com ponto."""
    ENTREGAVEIS.mkdir(exist_ok=True)
    df.to_csv(destino, index=False, encoding="utf-8", lineterminator="\n")
    return destino


# --------------------------------------------------------------------------- #
# Conferência
# --------------------------------------------------------------------------- #


class Conferencia:
    """Acumula checagens e falha no fim, com todas as falhas de uma vez.

    Falhar na primeira checagem economiza uma linha de código e custa três
    rodadas de depuração: corrige-se um problema, roda de novo, aparece o
    seguinte. Aqui todas aparecem juntas.
    """

    def __init__(self, titulo: str) -> None:
        self.titulo = titulo
        self.linhas: list[tuple[bool, str, str]] = []

    def checar(self, ok: bool, nome: str, detalhe: str = "") -> bool:
        self.linhas.append((bool(ok), nome, detalhe))
        return bool(ok)

    @property
    def falhas(self) -> list[tuple[bool, str, str]]:
        return [l for l in self.linhas if not l[0]]

    def imprimir(self) -> bool:
        print(f"{chr(10)}--- {self.titulo} ---{chr(10)}")
        for ok, nome, detalhe in self.linhas:
            marca = "ok  " if ok else "FALHA"
            print(f"  [{marca}] {nome:<46}{detalhe}")
        if self.falhas:
            print(f"{chr(10)}  {len(self.falhas)} checagem(ns) falharam.")
        return not self.falhas


def _cabecalho_do_exemplo(arquivo: Path) -> list[str]:
    return arquivo.read_text(encoding="utf-8").splitlines()[0].split(",")


def conferir_modelo(arquivo: Path = ARQ_MODELO_SAIDA) -> Conferencia:
    """Relê o arquivo do disco e confere contra a Base B e contra o exemplo."""
    conf = Conferencia(f"Conferência de {arquivo.name}")
    bruto = arquivo.read_text(encoding="utf-8")
    df = pd.read_csv(arquivo, encoding="utf-8")
    b = carregar_base_b()

    esperado = _cabecalho_do_exemplo(ARQ_MODELO_EXEMPLO)
    conf.checar(
        list(df.columns) == esperado,
        "colunas e ordem idênticas ao exemplo",
        ", ".join(df.columns),
    )
    conf.checar(not bruto.startswith(chr(65279)), "sem BOM no início do arquivo")
    conf.checar(len(df) == len(b), "3.000 linhas", f"{len(df):,}")
    conf.checar(
        list(df["id_contrato"]) == list(b["id_contrato"]),
        "ids iguais aos da Base B, na mesma ordem",
    )
    conf.checar(df["id_contrato"].is_unique, "ids sem repetição")
    conf.checar(df["pd"].notna().all(), "nenhuma PD vazia")
    conf.checar(
        bool(((df["pd"] > 0) & (df["pd"] < 1)).all()),
        "PD dentro de (0, 1)",
        f"{df['pd'].min():.6f} a {df['pd'].max():.6f}",
    )
    conf.checar(
        df["pd"].nunique() > 0.9 * len(df),
        "PD com granularidade suficiente",
        f"{df['pd'].nunique():,} valores distintos em {len(df):,}",
    )
    return conf


def conferir_politica(arquivo: Path = ARQ_POLITICA_SAIDA) -> Conferencia:
    """Relê o arquivo do disco e confere formato, domínios e coerência interna."""
    conf = Conferencia(f"Conferência de {arquivo.name}")
    bruto = arquivo.read_text(encoding="utf-8")
    df = pd.read_csv(arquivo, encoding="utf-8")
    c = carregar_base_c()

    esperado = _cabecalho_do_exemplo(ARQ_POLITICA_EXEMPLO)
    if not conf.checar(
        list(df.columns) == esperado,
        "colunas e ordem idênticas ao exemplo",
        ", ".join(df.columns),
    ):
        # Sem as colunas certas, toda checagem seguinte estoura em `KeyError` e
        # o traceback esconde a causa. Falha limpo aqui: o problema é um só.
        conf.checar(False, "demais checagens não rodaram", "corrija o cabeçalho primeiro")
        return conf
    conf.checar(not bruto.startswith(chr(65279)), "sem BOM no início do arquivo")
    conf.checar(len(df) == len(c), "5.000 linhas", f"{len(df):,}")
    conf.checar(
        list(df["id_proposta"]) == list(c["id_proposta"]),
        "ids iguais aos da Base C, na mesma ordem",
    )
    conf.checar(df["id_proposta"].is_unique, "ids sem repetição")

    # --- domínios ---------------------------------------------------------- #
    conf.checar(
        bool(((df["pd"] > 0) & (df["pd"] < 1)).all()),
        "PD dentro de (0, 1)",
        f"{df['pd'].min():.6f} a {df['pd'].max():.6f}",
    )
    conf.checar(
        bool(df["score_1a10"].between(1, 10).all()) and df["score_1a10"].dtype.kind == "i",
        "score inteiro de 1 a 10",
        f"{df['score_1a10'].min()} a {df['score_1a10'].max()}",
    )
    conf.checar(
        set(df["decisao"]) <= {"APROVAR", "NEGAR"},
        "decisão só APROVAR ou NEGAR",
        ", ".join(sorted(set(df["decisao"]))),
    )

    aprova = df["decisao"] == "APROVAR"
    nega = ~aprova

    # --- a checagem que o exemplo define ----------------------------------- #
    vazias_ok = all(df.loc[nega, col].isna().all() for col in COLUNAS_SO_DE_APROVADO)
    conf.checar(
        vazias_ok,
        "linhas NEGAR com taxa, prazo e entrada vazios",
        f"{int(nega.sum()):,} linhas negadas",
    )
    preenchidas_ok = all(df.loc[aprova, col].notna().all() for col in COLUNAS_SO_DE_APROVADO)
    conf.checar(preenchidas_ok, "linhas APROVAR com as três colunas preenchidas")

    conf.checar(
        bool(df.loc[aprova, "taxa_am"].between(TAXA_MINIMA, MAX_CET_AM).all()),
        f"taxa entre {TAXA_MINIMA:.2%} e o teto de CET de {MAX_CET_AM:.1%}",
        f"{df.loc[aprova, 'taxa_am'].min():.4f} a {df.loc[aprova, 'taxa_am'].max():.4f}",
    )
    conf.checar(
        set(df.loc[aprova, "prazo_meses"].astype("int64")) <= set(PRAZOS_VALIDOS),
        "prazo entre os quatro valores válidos",
        ", ".join(str(int(v)) for v in sorted(set(df.loc[aprova, "prazo_meses"]))),
    )
    conf.checar(
        bool(df.loc[aprova, "pct_entrada_minima"].between(0, 1).all()),
        "entrada mínima em decimal, dentro de [0, 1]",
        f"{df.loc[aprova, 'pct_entrada_minima'].min():.4f} a "
        f"{df.loc[aprova, 'pct_entrada_minima'].max():.4f}",
    )
    inteiro_no_arquivo = all(
        campo.isdigit()
        for campo in (
            linha.split(",")[COLUNAS_POLITICA.index("prazo_meses")]
            for linha in bruto.splitlines()[1:]
        )
        if campo
    )
    conf.checar(inteiro_no_arquivo, "prazo gravado como inteiro, não como 48.0")

    # --- coerência interna -------------------------------------------------- #
    conf.checar(
        bool((faixa(df["pd"].to_numpy()) == df["score_1a10"].to_numpy()).all()),
        "score reproduzível por faixa(pd) a partir do CSV",
        f"cortes {CORTES}",
    )
    conf.checar(
        bool(df.groupby("score_1a10")["decisao"].nunique().max() == 1),
        "uma só decisão por faixa",
    )
    por_faixa = df.loc[aprova].groupby("score_1a10")
    conf.checar(
        int(por_faixa["taxa_am"].nunique().max()) == 1,
        "uma só taxa por faixa",
    )
    conf.checar(
        int(por_faixa["pct_entrada_minima"].nunique().max()) == 1,
        "uma só entrada mínima por faixa",
    )
    monot = df.loc[aprova].groupby("score_1a10")["taxa_am"].first().sort_index()
    conf.checar(
        bool((monot.diff().dropna() <= 0).all()),
        "taxa não aumenta conforme a faixa melhora",
        " > ".join(f"{v:.2%}" for v in monot.sort_index(ascending=False)),
    )

    # --- contra a tabela publicada ------------------------------------------ #
    tabela = pd.read_csv(ARTEFATOS / "tabela_politica.csv")
    bate = True
    for _, linha in tabela.iterrows():
        f = int(linha["faixa"])
        no_csv = df.loc[df["score_1a10"] == f]
        if no_csv.empty:
            continue
        if linha["decisao"] != no_csv["decisao"].iloc[0]:
            bate = False
        elif linha["decisao"] == "APROVAR":
            bate &= bool(np.isclose(linha["taxa_am"], no_csv["taxa_am"].iloc[0]))
            bate &= bool(
                np.isclose(linha["entrada_minima"], no_csv["pct_entrada_minima"].iloc[0])
            )
    conf.checar(bate, "bate com artefatos/tabela_politica.csv, faixa a faixa")

    # A coluna `pd` da submissão é a do enquadramento. A tabela publicada traz
    # duas PDs por faixa — `pd_publicada` e `pd_precificada` — justamente porque
    # elas diferem depois que a entrada exigida derruba o LTV. Esta checagem
    # garante que o documento cita a que está no arquivo, não a outra.
    medias = df.groupby("score_1a10")["pd"].mean()
    bate_pd = all(
        np.isclose(linha["pd_publicada"], medias[int(linha["faixa"])], atol=5e-5)
        for _, linha in tabela.iterrows()
        if int(linha["faixa"]) in medias.index
    )
    conf.checar(
        bate_pd,
        "PD média por faixa igual à `pd_publicada` da tabela",
        "a `pd_precificada` é outra coluna, e é maior",
    )

    # --- o guardrail que o próprio arquivo já prova ------------------------- #
    conf.checar(
        float(aprova.mean()) >= MIN_APROVACAO,
        f"taxa de aprovação >= {MIN_APROVACAO:.0%}",
        f"{aprova.mean():.1%} ({int(aprova.sum()):,} de {len(df):,})",
    )
    return conf


# --------------------------------------------------------------------------- #
# O teste da conferência
# --------------------------------------------------------------------------- #
# Uma bateria de checagens que sempre passa não prova nada: pode estar checando
# o vazio. Este autoteste estraga o arquivo de propósito, de nove formas
# diferentes, e exige que a conferência pegue todas. É o único jeito de saber
# que as 22 linhas de "ok" acima significam alguma coisa.


def _sabotagens() -> list[tuple[str, object]]:
    """Cada entrada é (descrição, função que corrompe as linhas do CSV)."""

    def bom(l):
        # chr(65279) é o BOM. Escrito como literal ele fica invisível no
        # código-fonte, que é exatamente o problema que ele causa no CSV.
        l[0] = chr(65279) + l[0]

    def coluna_renomeada(l):
        l[0] = l[0].replace("pct_entrada_minima", "entrada_minima")

    def colunas_trocadas(l):
        c = l[0].split(",")
        c[1], c[2] = c[2], c[1]
        l[0] = ",".join(c)

    def linha_a_menos(l):
        del l[500]

    def _primeira(l, decisao, muda):
        for k, linha in enumerate(l[1:], 1):
            campos = linha.split(",")
            if campos[3] == decisao:
                muda(campos)
                l[k] = ",".join(campos)
                return

    return [
        ("BOM no início do arquivo", bom),
        ("nome de coluna trocado", coluna_renomeada),
        ("duas colunas fora de ordem", colunas_trocadas),
        ("uma linha a menos", linha_a_menos),
        ("taxa acima do teto de CET",
         lambda l: _primeira(l, "APROVAR", lambda c: c.__setitem__(4, "0.0400"))),
        ("taxa diferente do resto da faixa",
         lambda l: _primeira(l, "APROVAR", lambda c: c.__setitem__(4, "0.0260"))),
        ("prazo gravado como 48.0",
         lambda l: _primeira(l, "APROVAR", lambda c: c.__setitem__(5, "48.0"))),
        ("linha NEGAR com preço preenchido",
         lambda l: _primeira(l, "NEGAR",
                             lambda c: c.__setitem__(slice(4, 7), ["0.0300", "48", "0.21"]))),
        ("score que não bate com faixa(pd)",
         lambda l: l.__setitem__(1, ",".join(
             c if k != 2 else ("10" if c != "10" else "1")
             for k, c in enumerate(l[1].split(","))))),
    ]


def autoteste() -> bool:
    """Estraga o arquivo de nove formas e confere que a conferência pega todas."""
    import tempfile

    print(f"{chr(10)}--- Autoteste: a conferência de fato morde? ---{chr(10)}")
    original = ARQ_POLITICA_SAIDA.read_text(encoding="utf-8").splitlines()
    todas_pegas = True
    with tempfile.TemporaryDirectory() as tmp:
        alvo = Path(tmp) / "sabotado.csv"
        for nome, estragar in _sabotagens():
            linhas = list(original)
            estragar(linhas)
            alvo.write_text(
                chr(10).join(linhas) + chr(10), encoding="utf-8", newline=""
            )
            try:
                falhas = [l[1] for l in conferir_politica(alvo).falhas]
            except Exception as erro:  # nenhuma sabotagem deveria chegar aqui
                falhas = [f"exceção não tratada: {type(erro).__name__}"]
            pegou = bool(falhas)
            todas_pegas &= pegou
            print(
                f"  [{('pegou' if pegou else 'PASSOU BATIDO'):>13}] {nome:<40}"
                f"{falhas[0] if falhas else ''}"
            )
    print(
        f"{chr(10)}  -> {'as nove sabotagens foram pegas' if todas_pegas else 'ALGUMA PASSOU'}."
        f" Uma bateria que só diz 'ok' não prova{chr(10)}"
        f"     nada; esta diz 'ok' depois de provar que sabe dizer 'falha'."
    )
    return todas_pegas


def custo_do_arredondamento() -> dict:
    """Quanto custa publicar a PD com poucas casas — medido, não suposto.

    A hipótese de partida era que empate destrói AuROC, e ela está errada: um
    AuROC bem implementado pontua par empatado como 0,5, que é o tratamento
    certo para "o modelo não distingue estes dois". O custo real é outro e
    aparece na segunda coluna da direita.
    """
    from sklearn.metrics import roc_auc_score

    from dados import carregar_base_a

    oof = pd.read_csv(ARTEFATOS / "pd_base_a.csv")
    a = carregar_base_a().set_index("id_contrato")
    y = a.loc[oof["id_contrato"], "default_90_12"].to_numpy()
    p = oof["pd_oof"].to_numpy()
    cru = roc_auc_score(y, p)

    faixas_c = pd.read_csv(ARQ_POLITICA_SAIDA, encoding="utf-8")["score_1a10"].to_numpy()
    pd_c = pd.read_csv(ARTEFATOS / "politica_base_c.csv")["pd_enquadramento"].to_numpy()

    print(f"{chr(10)}--- Quantas casas decimais publicar na PD ---{chr(10)}")
    print(
        f"  {'casas':>7}{'empatados':>12}{'AuROC (Base A oof)':>21}{'perda':>10}"
        f"{'trocam de faixa (C)':>22}"
    )
    achados = {}
    for casas in (2, 3, 4, 5, 6):
        r = np.round(p, casas)
        empates = (len(r) - len(np.unique(r))) / len(r)
        auc = roc_auc_score(y, r)
        trocam = int((faixa(np.round(pd_c, casas)) != faixas_c).sum())
        print(
            f"  {casas:>7}{empates:>12.1%}{auc:>21.5f}{cru - auc:>10.5f}{trocam:>22,}"
        )
        achados[f"trocam_faixa_{casas}_casas"] = trocam
        achados[f"auroc_{casas}_casas"] = float(auc)
    print(f"  {'cru':>7}{0.0:>12.1%}{cru:>21.5f}{0.0:>10.5f}{0:>22,}")
    print(
        f"{chr(10)}  -> quatro casas custam {cru - roc_auc_score(y, np.round(p, 4)):.5f} de AuROC, "
        f"que é ruído. A razão de publicar{chr(10)}"
        f"     com {CASAS_PD} não é AuROC — seria inventar um ganho que a medição nega. É a"
        f"{chr(10)}     última coluna: a 4 casas, "
        f"{achados['trocam_faixa_4_casas']} das 5.000 propostas caem do outro lado de um{chr(10)}"
        f"     corte de faixa, e quem reconferir `faixa(pd)` pelo CSV acharia outra faixa."
    )
    achados["auroc_oof_cru"] = float(cru)
    return achados


# --------------------------------------------------------------------------- #
# Relatório
# --------------------------------------------------------------------------- #


def resumir(arq_modelo: Path, arq_politica: Path) -> dict:
    m = pd.read_csv(arq_modelo, encoding="utf-8")
    p = pd.read_csv(arq_politica, encoding="utf-8")
    aprova = p["decisao"] == "APROVAR"

    print(f"{chr(10)}--- O que vai nos dois arquivos ---{chr(10)}")
    print(
        f"  {arq_modelo.name:<26}{len(m):>7,} linhas   "
        f"PD de {m['pd'].min():.4f} a {m['pd'].max():.4f}, média {m['pd'].mean():.4f}"
    )
    print(
        f"  {arq_politica.name:<26}{len(p):>7,} linhas   "
        f"{int(aprova.sum()):,} APROVAR, {int((~aprova).sum()):,} NEGAR"
    )

    print(f"{chr(10)}  A tabela de faixas, como ela sai do próprio CSV de submissão:{chr(10)}")
    print(
        f"  {'faixa':>6}{'propostas':>11}{'decisão':>10}{'taxa a.m.':>11}"
        f"{'entrada mín.':>14}{'PD média':>11}"
    )
    for f in range(10, 0, -1):
        sub = p.loc[p["score_1a10"] == f]
        if sub.empty:
            continue
        ap = sub["decisao"].iloc[0] == "APROVAR"
        print(
            f"  {f:>6}{len(sub):>11,}{sub['decisao'].iloc[0]:>10}"
            f"{(f'{sub.taxa_am.iloc[0]:.2%}' if ap else '—'):>11}"
            f"{(f'{sub.pct_entrada_minima.iloc[0]:.0%}' if ap else '—'):>14}"
            f"{sub['pd'].mean():>11.2%}"
        )
    return {
        "linhas_modelo": len(m),
        "linhas_politica": len(p),
        "aprovadas": int(aprova.sum()),
        "taxa_aprovacao": float(aprova.mean()),
        "pd_media_base_b": float(m["pd"].mean()),
        "pd_media_base_c": float(p["pd"].mean()),
        "casas_pd": CASAS_PD,
    }


def main(apenas_conferir: bool = False) -> None:
    print("=" * 96)
    print("  SUBMISSÕES — Base B (modelo) e Base C (política)")
    print("=" * 96)

    if not apenas_conferir:
        gravar(submissao_modelo(), ARQ_MODELO_SAIDA)
        gravar(submissao_politica(), ARQ_POLITICA_SAIDA)
        print(
            f"{chr(10)}  gravado entregaveis/{ARQ_MODELO_SAIDA.name}{chr(10)}"
            f"  gravado entregaveis/{ARQ_POLITICA_SAIDA.name}"
        )

    conf_m = conferir_modelo()
    conf_p = conferir_politica()
    ok = conf_m.imprimir() & conf_p.imprimir()
    ok &= autoteste()

    resumo = resumir(ARQ_MODELO_SAIDA, ARQ_POLITICA_SAIDA)
    resumo.update(custo_do_arredondamento())
    resumo["conferencias"] = len(conf_m.linhas) + len(conf_p.linhas)
    resumo["falhas"] = len(conf_m.falhas) + len(conf_p.falhas)

    print(
        f"{chr(10)}  {resumo['conferencias']} checagens, {resumo['falhas']} falhas."
        f"{chr(10)}  As duas submissões foram geradas por este script. Nenhum valor foi digitado."
    )
    registrar_execucao("submissoes", {"etapa": "src/submissoes", **resumo,
                                      "regra": ESCOLHIDA.rotulo()})
    print("=" * 96)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main(apenas_conferir="--conferir" in sys.argv)
