"""EAD, LGD e perda esperada — Desafio AutoCred.

A PD responde "qual a chance de quebrar". Este módulo responde as outras duas
perguntas que a política precisa antes de decidir preço:

    quanto ainda se deve quando quebra?   -> EAD (exposure at default)
    quanto disso se perde de fato?        -> LGD (loss given default)

    Perda esperada = PD x EAD x LGD

Nenhuma das duas é modelada: o enunciado entrega as tabelas em
`bases/AutoCred_parametros_ead_lgd.xlsx` e o desafio é só de PD. Isso **não**
significa aplicar o lookup sem olhar. As três disciplinas deste módulo:

  - **A fronteira de faixa de LTV foi decidida por evidência, não por leitura do
    rótulo.** "até 60%" sugere `ltv <= 0,60`; os realizados dizem o contrário.
    Reproduzindo as células da tabela contra a Base A, a convenção que fecha é
    `[0; 0,60) [0,60; 0,70) [0,70; 0,80) [0,80; 0,90) [0,90; inf)` — limite
    **inferior** fechado. O erro máximo cai de 0,0034 para 0,0005 (arredondamento
    da própria tabela). Importa na política: LTV de exatamente 80% cai na faixa
    pior, e a entrada tem de furar o corte, não encostar nele.
  - **O fator de EAD depende da taxa que *nós* cobrarmos.** A fórmula fechada do
    enunciado foi reconstruída e reproduz `ead_realizado` com erro máximo de
    meio centavo nos 826 defaults — que é o arredondamento do próprio campo. Ela mostra que o fator é função de (taxa, prazo,
    mês do default) e **não** de LTV. A tabela foi medida numa carteira que
    cobrava 1,59% a.m.; a 3,0% a.m. o fator verdadeiro sobe de 1,032 para 1,078.
    Precificar caro aumenta a exposição — e o lookup não enxerga isso.
  - **O ajuste de avalista oficial acerta a minoria e erra a maioria.** A
    instrução é somar -0,061 quando há avalista. Esse -0,061 é a diferença
    *bruta* de médias; dentro da mesma célula da tabela o efeito é -0,079, porque
    avalista se concentra nas células de LTV alto, que já têm LGD maior. E a
    tabela não é a LGD de quem não tem avalista: é a média da carteira inteira,
    com 19,7% de avalistas dentro. Os dois erros se cancelam para quem tem
    avalista (resíduo -0,002) e sobram inteiros para os outros 84% (+0,016).
    Aqui a LGD é aplicada com o efeito estimado e a centragem explícita. Ver
    `docs/06-risco.md`, decisão 3.

Uso:
    PYTHONIOENCODING=utf-8 python src/risco.py
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from dados import ALVO, ARTEFATOS, BASES, carregar_base_a, carregar_base_c, registrar_execucao
from features import parcela_price, preparar_aplicacao

ARQ_PARAMETROS = BASES / "AutoCred_parametros_ead_lgd.xlsx"
ARQ_PERDA_C = ARTEFATOS / "perda_esperada_base_c.csv"

# --------------------------------------------------------------------------- #
# Convenções de faixa
# --------------------------------------------------------------------------- #
# As duas tabelas usam a mesma régua de LTV. O `side="right"` do searchsorted é
# o que implementa o limite inferior fechado validado contra os realizados.

CORTES_LTV = (0.60, 0.70, 0.80, 0.90)
ROTULOS_LTV = ("até 60%", "60% a 70%", "70% a 80%", "80% a 90%", "acima de 90%")

CORTES_IDADE = (2, 5, 8)
ROTULOS_IDADE = ("0 a 2 anos", "3 a 5 anos", "6 a 8 anos", "9 anos ou mais")

# Atraso que caracteriza o default 90/12: três parcelas vencidas.
ATRASO_MESES = 3

# Ajuste de LGD para contrato com avalista, como a aba `Leia-me` o prescreve.
AJUSTE_AVALISTA_OFICIAL = -0.061

# O mesmo efeito medido *dentro* da célula da tabela, que é onde ele de fato se
# aplica. IC de 95%: [-0,101; -0,057] sobre 163 defaults com avalista. Contém o
# -0,061 oficial — a diferença entre os dois números não é discordância
# estatística, é o que a composição de células faz com uma média bruta.
EFEITO_AVALISTA = -0.079

# Fração de contratos com avalista entre os 826 defaults que geraram a tabela de
# LGD. A tabela é a média *da mistura*, então ela já embute 19,7% do efeito; sem
# descontar isso, quem não tem avalista recebe uma LGD baixa demais.
SHARE_AVALISTA_TABELA = 0.1973

# Taxa mensal mediana da carteira antiga, que é a taxa em que a tabela de fator
# de EAD foi medida. Serve de referência para medir o quanto a nossa oferta se
# afasta do regime em que o parâmetro foi calibrado.
TAXA_DA_TABELA = 0.0159


# --------------------------------------------------------------------------- #
# Os parâmetros oficiais
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def tabela_ead() -> pd.DataFrame:
    """Fator de EAD por prazo (linhas) x faixa de LTV (colunas)."""
    t = pd.read_excel(ARQ_PARAMETROS, sheet_name="Fator_EAD").set_index("Prazo (meses)")
    return t[list(ROTULOS_LTV)]


@lru_cache(maxsize=1)
def tabela_lgd() -> pd.DataFrame:
    """LGD por idade do veículo (linhas) x faixa de LTV (colunas)."""
    t = pd.read_excel(ARQ_PARAMETROS, sheet_name="LGD").set_index(
        "Idade do veículo na originação"
    )
    return t.reindex(list(ROTULOS_IDADE))[list(ROTULOS_LTV)]


@lru_cache(maxsize=1)
def distribuicao_mes_default() -> pd.Series:
    """Frequência do mês do default (1 a 12). Soma 1,0; média 6,89.

    É o que permite transformar "vai quebrar" em "vai quebrar no mês 6,89 em
    média" — e sem o mês não há saldo devedor, nem juros recebidos até lá.
    """
    t = pd.read_excel(ARQ_PARAMETROS, sheet_name="Distribuicao_Mes_Default")
    return t.set_index("Mês do default")["Frequência"]


# --------------------------------------------------------------------------- #
# Enquadramento
# --------------------------------------------------------------------------- #


def indice_ltv(ltv) -> np.ndarray:
    """Posição da faixa de LTV, 0 a 4. Limite **inferior** fechado."""
    return np.searchsorted(np.asarray(CORTES_LTV), np.asarray(ltv, dtype="float64"), side="right")


def indice_idade(idade_veiculo_anos) -> np.ndarray:
    """Posição da faixa de idade do veículo, 0 a 3."""
    return np.searchsorted(
        np.asarray(CORTES_IDADE), np.asarray(idade_veiculo_anos, dtype="float64"), side="left"
    )


def faixa_ltv(ltv) -> np.ndarray:
    """Rótulo da faixa de LTV, como aparece na tabela."""
    return np.take(np.asarray(ROTULOS_LTV), indice_ltv(ltv))


def faixa_idade(idade_veiculo_anos) -> np.ndarray:
    """Rótulo da faixa de idade do veículo, como aparece na tabela."""
    return np.take(np.asarray(ROTULOS_IDADE), indice_idade(idade_veiculo_anos))


def _indice_prazo(prazo_meses) -> np.ndarray:
    prazos = np.asarray(prazo_meses).astype("int64").ravel()
    pos = tabela_ead().index.get_indexer(prazos)
    if (pos < 0).any():
        fora = sorted(set(prazos[pos < 0].tolist()))
        raise ValueError(
            f"Prazo sem linha na tabela de EAD: {fora}. "
            f"A tabela só cobre {list(tabela_ead().index)} meses."
        )
    return pos


def _tem_avalista(possui_avalista) -> np.ndarray:
    """Aceita 'Sim'/'Não' (como vem das bases) ou booleano."""
    v = np.asarray(possui_avalista)
    if v.dtype.kind in "bif":
        return v.astype("float64")
    return (pd.Series(v.ravel()).astype(str).str.strip().str.lower() == "sim").to_numpy(
        dtype="float64"
    ).reshape(v.shape)


# --------------------------------------------------------------------------- #
# EAD
# --------------------------------------------------------------------------- #


def fator_ead(prazo_meses, ltv) -> np.ndarray:
    """Fator de EAD pelo lookup oficial. `EAD = fator x valor_financiado`.

    Fator acima de 1 é esperado e não é erro: no mês do default o contrato ainda
    tem saldo devedor pela Price *mais* as três parcelas vencidas do atraso de
    90 dias. Em contratos de 60 meses com default precoce o total passa do
    principal emprestado.
    """
    return tabela_ead().to_numpy()[_indice_prazo(prazo_meses), indice_ltv(ltv)]


def saldo_price(valor_financiado, taxa_am, prazo_meses, parcelas_pagas):
    """Saldo devedor pela Tabela Price após `parcelas_pagas` pagamentos."""
    i = np.asarray(taxa_am, dtype="float64")
    n = np.asarray(prazo_meses, dtype="float64")
    k = np.clip(np.asarray(parcelas_pagas, dtype="float64"), 0, None)
    return parcela_price(valor_financiado, i, n) * (1 - (1 + i) ** -(n - k)) / i


def ead_no_mes(valor_financiado, taxa_am, prazo_meses, mes_default, atraso: int = ATRASO_MESES):
    """EAD exato de um contrato que quebra no mês `mes_default`.

    É a fórmula fechada da aba `Leia-me`, explicitada: quem quebra no mês `m`
    parou de pagar em `m - 3`, então deve o saldo daquele ponto **mais** as três
    parcelas vencidas. Reproduz `ead_realizado` da Base A com erro máximo de
    R$ 0,005 nos 826 defaults: os dois números são o mesmo, e o resíduo é o
    arredondamento do campo em centavos. Ver `auditar()`, seção 1.
    """
    pagas = np.asarray(mes_default, dtype="float64") - atraso
    saldo = saldo_price(valor_financiado, taxa_am, prazo_meses, pagas)
    return saldo + atraso * parcela_price(valor_financiado, taxa_am, prazo_meses)


def fator_ead_exato(taxa_am, prazo_meses, atraso: int = ATRASO_MESES):
    """Fator de EAD esperado pela fórmula fechada, à taxa que vamos cobrar.

    Média do fator sobre a distribuição do mês do default. Diferente do lookup
    em dois pontos que importam:

      - **não depende de LTV** — a fórmula não tem LTV dentro. As cinco colunas
        da tabela oficial são a mesma quantidade medida em cinco amostras
        diferentes, e a variação entre elas é ruído (ver `auditar()`);
      - **depende da taxa**, que na tabela está congelada em 1,59% a.m. Cobrar
        3,0% a.m. leva o fator de 48 meses de 1,032 para 1,078: juro alto
        amortiza devagar, e saldo devedor maior é exposição maior.
    """
    i = np.asarray(taxa_am, dtype="float64")
    n = np.asarray(prazo_meses, dtype="float64")
    parcela_unitaria = parcela_price(1.0, i, n)
    total = np.zeros(np.broadcast(i, n).shape, dtype="float64")
    for mes, frequencia in distribuicao_mes_default().items():
        pagas = max(int(mes) - atraso, 0)
        saldo = parcela_unitaria * (1 - (1 + i) ** -(n - pagas)) / i
        total = total + frequencia * (saldo + atraso * parcela_unitaria)
    return total


def ead(valor_financiado, prazo_meses, ltv, taxa_am=None):
    """Exposição no default, em reais.

    Sem `taxa_am`, usa o lookup oficial. Com a taxa ofertada, usa a fórmula
    fechada avaliada nela — que é o número correto quando o preço se afasta dos
    1,59% a.m. em que a tabela foi medida.
    """
    fator = fator_ead(prazo_meses, ltv) if taxa_am is None else fator_ead_exato(taxa_am, prazo_meses)
    return np.asarray(valor_financiado, dtype="float64") * fator


# --------------------------------------------------------------------------- #
# LGD
# --------------------------------------------------------------------------- #


def lgd(idade_veiculo_anos, ltv, possui_avalista, oficial: bool = False):
    """Perda dada a inadimplência, entre 0 e 1.

    `oficial=True` reproduz a instrução ao pé da letra — tabela + (-0,061) se há
    avalista. O padrão aplica a versão que fecha contra os realizados:

        LGD = tabela + (-0,079) x (tem_avalista - 0,1973)

    ou seja, **+0,0156 para quem não tem avalista** e **-0,0634 para quem tem**.
    Os dois números não são invenção: são o que zera o resíduo médio nos dois
    grupos, e a aritmética que os produz está em `auditar()`, seção 5.

    A escolha importa mais na Base C do que na A: a proporção de avalistas sobe
    de 16,0% para 25,3%, e é justamente a maioria sem avalista que a regra
    literal subestima.
    """
    base = tabela_lgd().to_numpy()[indice_idade(idade_veiculo_anos), indice_ltv(ltv)]
    tem = _tem_avalista(possui_avalista)
    ajuste = (
        AJUSTE_AVALISTA_OFICIAL * tem
        if oficial
        else EFEITO_AVALISTA * (tem - SHARE_AVALISTA_TABELA)
    )
    return np.clip(base + ajuste, 0.0, 1.0)


# --------------------------------------------------------------------------- #
# Perda esperada
# --------------------------------------------------------------------------- #


def perda_esperada(
    pd_12m,
    valor_financiado,
    prazo_meses,
    ltv,
    idade_veiculo_anos,
    possui_avalista,
    taxa_am=None,
    oficial: bool = False,
):
    """`PD x EAD x LGD`, em reais, no horizonte de 12 meses.

    O horizonte é o da PD: `default_90_12` é inadimplência nos primeiros 12 meses
    e é sobre essa janela que o desafio apura ROI. Contrato de 48 meses tem risco
    depois do 12º mês; ele não entra aqui, e não deveria — o que está sendo
    precificado é a janela que a competição mede.
    """
    return (
        np.asarray(pd_12m, dtype="float64")
        * ead(valor_financiado, prazo_meses, ltv, taxa_am)
        * lgd(idade_veiculo_anos, ltv, possui_avalista, oficial)
    )


def componentes(df: pd.DataFrame, pd_12m, taxa_am=None, oficial: bool = False) -> pd.DataFrame:
    """Abre a perda esperada em suas parcelas, linha a linha.

    Espera as colunas do vocabulário do modelo (`valor_financiado`, `prazo_meses`,
    `ltv`, `idade_veiculo_anos`, `possui_avalista`) — ou seja, a Base A direto ou
    a Base C depois de `preparar_aplicacao()`. É a entrada de `politica.py`.
    """
    e = ead(df["valor_financiado"], df["prazo_meses"], df["ltv"], taxa_am)
    g = lgd(df["idade_veiculo_anos"], df["ltv"], df["possui_avalista"], oficial)
    p = np.asarray(pd_12m, dtype="float64")
    return pd.DataFrame(
        {
            "valor_financiado": df["valor_financiado"].to_numpy(),
            "pd": p,
            "fator_ead": e / df["valor_financiado"].to_numpy(),
            "ead": e,
            "lgd": g,
            "perda_esperada": p * e * g,
            "perda_pct": p * e * g / df["valor_financiado"].to_numpy(),
        },
        index=df.index,
    )


# --------------------------------------------------------------------------- #
# Auditoria dos parâmetros contra os realizados
# --------------------------------------------------------------------------- #


def defaults_base_a() -> pd.DataFrame:
    """Os 826 contratos da Base A que quebraram, com EAD e LGD realizados.

    Estas colunas são **proibidas como preditoras** (são pós-concessão) e por
    isso nunca passam por `features.matriz`. Aqui o uso é outro: conferir os
    parâmetros que o enunciado entregou. É a mesma amostra que os gerou, então o
    teste é de reprodução, não de validação fora da amostra.
    """
    a = carregar_base_a()
    return a[a[ALVO] == 1].copy()


def _celulas(d: pd.DataFrame, valor: str, linhas: str) -> pd.DataFrame:
    return d.pivot_table(
        index=linhas, columns=faixa_ltv(d["ltv"]), values=valor, aggfunc="mean"
    ).reindex(columns=list(ROTULOS_LTV))


def auditar() -> dict:
    """Confere os parâmetros oficiais contra os realizados e devolve os números."""
    d = defaults_base_a()
    achados: dict[str, float] = {}

    print("=" * 96)
    print("EAD, LGD E PERDA ESPERADA — Desafio AutoCred")
    print("=" * 96)
    print(f"Parâmetros: bases/{ARQ_PARAMETROS.name}")
    print(f"Amostra de conferência: {len(d)} defaults da Base A (2022-2024)")

    # 1. A fórmula fechada do EAD ------------------------------------------- #
    exato = ead_no_mes(d["valor_financiado"], d["taxa_juros_am"], d["prazo_meses"], d["mes_default"])
    erro = np.abs(exato - d["ead_realizado"])
    achados["erro_max_formula_ead"] = float(erro.max())
    print("\n--- 1. A fórmula fechada do EAD, reconstruída ---\n")
    print("  EAD = saldo Price após (mês do default - 3) parcelas + 3 parcelas vencidas")
    print(
        f"  erro contra ead_realizado: mediana R$ {erro.median():.4f} | "
        f"máximo R$ {erro.max():.4f} | dentro de 1 centavo: {(erro < 0.005).mean():.1%}"
    )
    print(
        "  -> não é aproximação: é a mesma fórmula que gerou a base. Meio centavo é\n"
        "     o arredondamento do campo. Com ela o EAD deixa de ser lookup e passa a\n"
        "     ser função da taxa e do prazo que a política ofertar — ver seção 6."
    )

    # 2. A fronteira de LTV -------------------------------------------------- #
    print("\n--- 2. A fronteira das faixas de LTV, decidida por evidência ---\n")
    d["fator_real"] = d["ead_realizado"] / d["valor_financiado"]
    oficial = tabela_ead()
    for lado, descricao in [("left", "limite superior fechado"), ("right", "limite inferior fechado")]:
        rot = np.take(
            np.asarray(ROTULOS_LTV),
            np.searchsorted(np.asarray(CORTES_LTV), d["ltv"].to_numpy(), side=lado),
        )
        obs = d.pivot_table(
            index="prazo_meses", columns=rot, values="fator_real", aggfunc="mean"
        ).reindex(columns=list(ROTULOS_LTV))
        dif = float(np.abs(obs.to_numpy() - oficial.to_numpy()).max())
        achados[f"erro_max_ltv_{lado}"] = dif
        marca = "  <- em uso" if lado == "right" else ""
        print(f"  side={lado:<6} ({descricao:<24}) erro máximo nas 20 células: {dif:.5f}{marca}")
    print(
        "  -> `até 60%` significa LTV < 60%, não <= 60%. Contratos exatamente em\n"
        "     0,80 e 0,90 caem na faixa de cima. Consequência para a política:\n"
        "     exigir entrada que deixe o LTV em 80,0% não muda de faixa; 79,9% muda."
    )

    # 3. As duas tabelas contra os realizados -------------------------------- #
    print("\n--- 3. As tabelas oficiais são médias de célula da própria Base A ---\n")
    obs_ead = _celulas(d, "fator_real", "prazo_meses")
    erro_ead = float(np.abs(obs_ead.to_numpy() - oficial.to_numpy()).max())
    d["idade_fx"] = faixa_idade(d["idade_veiculo_anos"])
    obs_lgd = _celulas(d, "lgd_realizado", "idade_fx").reindex(list(ROTULOS_IDADE))
    erro_lgd = float(np.abs(obs_lgd.to_numpy() - tabela_lgd().to_numpy()).max())
    achados["erro_max_celula_ead"] = erro_ead
    achados["erro_max_celula_lgd"] = erro_lgd
    print(f"  fator de EAD: erro máximo célula a célula .... {erro_ead:.5f}")
    print(f"  LGD:          erro máximo célula a célula .... {erro_lgd:.5f}")
    print("  -> nada a calibrar: reproduzimos as tabelas. O que resta é decidir como usá-las.")

    # 4. A coluna de LTV do fator de EAD é ruído ----------------------------- #
    print("\n--- 4. A dimensão de LTV do fator de EAD não é risco, é ruído ---\n")
    mes = _celulas(d, "mes_default", "prazo_meses")
    desvio_fator = (obs_ead.sub(obs_ead.mean(axis=1), axis=0)).to_numpy().ravel()
    desvio_mes = (mes.sub(mes.mean(axis=1), axis=0)).to_numpy().ravel()
    correlacao = float(np.corrcoef(desvio_fator, desvio_mes)[0, 1])
    tamanhos_celula = d.pivot_table(
        index="prazo_meses", columns=faixa_ltv(d["ltv"]), values="fator_real", aggfunc="size"
    )
    menor_linha = int(oficial.index[0])
    n_min = int(tamanhos_celula.loc[menor_linha].min())
    n_max = int(tamanhos_celula.loc[menor_linha].max())
    achados["corr_fator_mes"] = correlacao
    amplitude = (oficial.max(axis=1) - oficial.min(axis=1))
    print("  amplitude do fator dentro de cada linha de prazo:")
    for prazo, valor in amplitude.items():
        print(f"    {prazo:>2} meses ... {valor:.3f}")
    print(
        f"\n  correlação (desvio do fator na linha x desvio do mês do default): {correlacao:+.3f}"
    )
    print(
        "  -> a fórmula fechada não tem LTV dentro. O que varia entre colunas é qual\n"
        "     célula sorteou defaults mais cedo — e mês do default não se conhece na\n"
        f"     concessão. As células de {menor_linha} meses têm de {n_min} a {n_max} contratos cada."
    )

    # 5. O avalista ---------------------------------------------------------- #
    print("\n--- 5. O ajuste de avalista: por que o -0,061 acerta só um dos dois grupos ---\n")
    d["lgd_tabela"] = tabela_lgd().to_numpy()[
        indice_idade(d["idade_veiculo_anos"]), indice_ltv(d["ltv"])
    ]
    d["aval"] = _tem_avalista(d["possui_avalista"])
    bruto = float(
        d.loc[d["aval"] == 1, "lgd_realizado"].mean() - d.loc[d["aval"] == 0, "lgd_realizado"].mean()
    )
    residuo = d["lgd_realizado"] - d["lgd_tabela"]
    medias = residuo.groupby(d["aval"]).mean()
    desvios = residuo.groupby(d["aval"]).std()
    tamanhos = d.groupby("aval").size()
    efeito = float(medias[1] - medias[0])
    ep = float(np.sqrt(desvios[1] ** 2 / tamanhos[1] + desvios[0] ** 2 / tamanhos[0]))
    share = float(d["aval"].mean())
    achados.update(
        {
            "efeito_avalista_bruto": bruto,
            "efeito_avalista_controlado": efeito,
            "share_avalista_defaults": share,
        }
    )
    print(
        f"  LGD média realizada: {d.loc[d['aval'] == 1, 'lgd_realizado'].mean():.4f} com avalista "
        f"contra {d.loc[d['aval'] == 0, 'lgd_realizado'].mean():.4f} sem"
    )
    print(f"  diferença bruta de médias ......... {bruto:+.4f}   (é daqui que sai o -0,061 oficial)")
    print(
        f"  medida dentro da célula ........... {efeito:+.4f}   "
        f"IC 95% [{efeito - 1.96 * ep:+.4f}; {efeito + 1.96 * ep:+.4f}]  "
        f"n={int(tamanhos[1])} com avalista"
    )
    alta = float(
        d.loc[(indice_ltv(d["ltv"]) == 4) & (indice_idade(d["idade_veiculo_anos"]) == 0), "aval"].mean()
    )
    print(
        "  -> os dois números não se contradizem: o oficial cabe no intervalo. A bruta é\n"
        f"     menor porque avalista não se distribui por igual — é {share:.1%} da carteira\n"
        f"     e {alta:.1%} da célula de LTV acima de 90% em veículo de 0 a 2 anos, onde a"
        f" LGD já é alta."
    )
    print(
        f"\n  E a tabela é a média da mistura: {share:.1%} dos contratos que a formaram já\n"
        "  tinham avalista. Somar o ajuste sobre ela conta o efeito duas vezes para uns\n"
        "  e nenhuma vez para outros. O resíduo médio por grupo mostra o estrago:\n"
    )
    print(f"  {'regra aplicada':<38}{'sem avalista':>14}{'com avalista':>14}{'LGD média':>12}")
    for rotulo, kwargs in [
        ("tabela crua, sem ajuste nenhum", None),
        ("oficial: tabela + (-0,061) se avalista", {"oficial": True}),
        (f"em uso: tabela {EFEITO_AVALISTA:+.3f} x (av - {SHARE_AVALISTA_TABELA:.3f})", {}),
    ]:
        aplicada = (
            d["lgd_tabela"].to_numpy()
            if kwargs is None
            else lgd(d["idade_veiculo_anos"], d["ltv"], d["possui_avalista"], **kwargs)
        )
        r = pd.Series(d["lgd_realizado"].to_numpy() - aplicada).groupby(d["aval"].to_numpy()).mean()
        print(f"  {rotulo:<38}{r[0]:>+14.4f}{r[1]:>+14.4f}{float(np.mean(aplicada)):>12.4f}")
    print(f"  {'LGD realizada':<38}{'':>14}{'':>14}{d['lgd_realizado'].mean():>12.4f}")
    print(
        "\n  -> a regra oficial deixa +0,016 de perda não provisionada em 84% da carteira\n"
        "     e acerta o grupo com avalista por cancelamento de dois erros. O ajuste em\n"
        "     uso zera o resíduo dos dois grupos e preserva a média da tabela."
    )

    # 6. O fator de EAD depende da taxa que vamos cobrar --------------------- #
    print("\n--- 6. O fator de EAD à taxa que a política cobrar ---\n")
    prazos = list(tabela_ead().index)
    print("  " + f"{'taxa a.m.':>12}" + "".join(f"{p:>10} m" for p in prazos))
    for taxa in (TAXA_DA_TABELA, 0.020, 0.025, 0.030, 0.035):
        marca = "  <- taxa da tabela" if taxa == TAXA_DA_TABELA else ""
        print(
            f"  {taxa:>12.2%}"
            + "".join(f"{float(fator_ead_exato(taxa, p)):>12.4f}" for p in prazos)
            + marca
        )
    print("  " + f"{'lookup oficial':>12}" + "".join(f"{oficial.loc[p].mean():>12.4f}" for p in prazos))
    achados["fator_48m_a_3pct"] = float(fator_ead_exato(0.030, 48))
    print(
        "\n  -> o lookup está certo para a carteira antiga e otimista para a nossa. O\n"
        "     teto de CET do desafio é 3,5% a.m.; nesse extremo o fator de 48 meses\n"
        f"     sobe de {oficial.loc[48].mean():.4f} para {float(fator_ead_exato(0.035, 48)):.4f}, +{(float(fator_ead_exato(0.035, 48)) / oficial.loc[48].mean() - 1):.1%} de exposição."
    )
    return achados


# --------------------------------------------------------------------------- #
# Fechamento da cadeia
# --------------------------------------------------------------------------- #


def conferir_cadeia() -> dict:
    """`Soma(PD x EAD x LGD)` na Base A contra a perda que de fato aconteceu.

    É o único teste que fecha as três peças de uma vez, e o que autoriza usar a
    perda esperada como piso de preço. Usa a PD out-of-fold de `score.py` — a PD
    do modelo final sobre as próprias linhas de treino acertaria o total por
    memória, não por acerto.

    O total sozinho não arbitra convenção nenhuma: erro de 1% em qualquer das
    três peças mexe 1% no produto, e elas se compensam. Por isso o teste vem
    aberto peça por peça.
    """
    from score import pd_base_a

    a = carregar_base_a()
    p = pd_base_a().set_index("id_contrato").loc[a["id_contrato"], "pd_oof"].to_numpy()
    d = a[a[ALVO] == 1]
    comp = componentes(a, p)
    realizada = float(a["perda_financeira"].sum())

    print("\n--- 7. A cadeia inteira contra o realizado (Base A) ---\n")
    print(f"  {'peça':<32}{'esperado':>16}{'realizado':>16}{'razão':>9}")
    e_tabela = float(np.sum(ead(d["valor_financiado"], d["prazo_meses"], d["ltv"])))
    g = lgd(d["idade_veiculo_anos"], d["ltv"], d["possui_avalista"])
    for rotulo, esperado, observado in [
        ("PD: soma das probabilidades", float(p.sum()), float(len(d))),
        ("EAD: exposição nos defaults", e_tabela, float(d["ead_realizado"].sum())),
        ("LGD: perda sobre o EAD real", float(np.sum(g * d["ead_realizado"])), realizada),
    ]:
        print(f"  {rotulo:<32}{esperado:>16,.0f}{observado:>16,.0f}{esperado / observado:>9.4f}")

    print(f"\n  {'cadeia completa':<32}{'esperado':>16}{'realizado':>16}{'razão':>9}")
    for rotulo, esperada in [
        ("PD x EAD x LGD (em uso)", float(comp["perda_esperada"].sum())),
        (
            "PD x EAD x LGD (regra oficial)",
            float(
                perda_esperada(
                    p, a["valor_financiado"], a["prazo_meses"], a["ltv"],
                    a["idade_veiculo_anos"], a["possui_avalista"], oficial=True,
                ).sum()
            ),
        ),
    ]:
        print(f"  {rotulo:<32}{esperada:>16,.0f}{realizada:>16,.0f}{esperada / realizada:>9.4f}")
    print(
        f"\n  volume financiado R$ {a['valor_financiado'].sum():,.0f} | "
        f"perda realizada {realizada / a['valor_financiado'].sum():.2%} do volume"
    )
    residuo = d["lgd_realizado"].to_numpy() - g
    print(
        f"\n  resíduo médio da LGD: {residuo.mean():+.4f} por contrato, "
        f"{np.average(residuo, weights=d['ead_realizado']):+.4f} ponderado pelo EAD"
    )
    print(
        "  -> PD e EAD fecham em 0,2% e 0,03%; a folga de 1,2% vem inteira da LGD, e\n"
        "     não é viés de nível: por contrato o resíduo é +0,0001. É tamanho. O\n"
        "     quinto mais caro dos defaults realiza LGD de 0,664 contra 0,702 de\n"
        "     tabela, e a tabela não tem dimensão de valor. Como a perda é ponderada\n"
        "     por dinheiro, provisionamos 1,2% a mais — o lado certo de errar quando\n"
        "     o número vira preço."
    )
    return {
        "perda_esperada_a": float(comp["perda_esperada"].sum()),
        "perda_realizada_a": realizada,
        "razao_cadeia": float(comp["perda_esperada"].sum()) / realizada,
        "razao_pd": float(p.sum()) / len(d),
        "razao_ead": e_tabela / float(d["ead_realizado"].sum()),
    }


def perda_base_c() -> pd.DataFrame:
    """Perda esperada de cada uma das 5.000 propostas, nas condições desejadas.

    Primeira passada: taxa de referência, prazo e entrada como o cliente pediu.
    É o insumo do capítulo 07 — a política vai mexer exatamente nessas alavancas
    e recalcular tudo.
    """
    import joblib

    from features import matriz
    from modelo import ARQ_MODELO
    from score import faixa

    c = carregar_base_c()
    preparada = preparar_aplicacao(c)
    modelo = joblib.load(ARQ_MODELO)
    p = modelo.predict_proba(matriz(preparada))[:, 1]
    comp = componentes(preparada, p)
    comp.insert(0, "id_proposta", c["id_proposta"].to_numpy())
    comp.insert(1, "faixa", faixa(p))
    return comp


def main() -> None:
    achados = auditar()
    achados.update(conferir_cadeia())

    comp = perda_base_c()
    c = carregar_base_c()
    print(
        f"{chr(10)}  Base C: {(c['possui_avalista'] == 'Sim').mean():.1%} das propostas têm avalista, "
        f"contra {(carregar_base_a()['possui_avalista'] == 'Sim').mean():.1%} na Base A —"
        f"{chr(10)}  é sobre a maioria sem avalista que a regra literal erraria, e ela é maior aqui."
    )
    print("\n--- 8. O que a política recebe: perda esperada por faixa na Base C ---\n")
    por_faixa = comp.groupby("faixa").agg(
        n=("pd", "size"),
        pd_media=("pd", "mean"),
        lgd_media=("lgd", "mean"),
        volume=("valor_financiado", "sum"),
        perda=("perda_esperada", "sum"),
    )
    por_faixa["perda_pct"] = por_faixa["perda"] / por_faixa["volume"]
    por_faixa["perda_am"] = por_faixa["perda_pct"] / 12
    print(
        f"  {'faixa':>5}{'n':>7}{'PD média':>11}{'LGD média':>11}"
        f"{'volume (R$)':>16}{'perda (R$)':>14}{'perda % vol.':>14}{'a.m.':>8}"
    )
    for f, linha in por_faixa.sort_index(ascending=False).iterrows():
        print(
            f"  {int(f):>5}{int(linha['n']):>7,}{linha['pd_media']:>11.2%}{linha['lgd_media']:>11.3f}"
            f"{linha['volume']:>16,.0f}{linha['perda']:>14,.0f}{linha['perda_pct']:>14.2%}"
            f"{linha['perda_am']:>8.2%}"
        )
    total = comp["perda_esperada"].sum() / comp["valor_financiado"].sum()
    print(
        f"\n  carteira inteira, sem política nenhuma: perda esperada {total:.2%} do volume.\n"
        f"\n  A coluna `a.m.` divide a perda por 12 e é um **piso otimista**: juros correm\n"
        f"  sobre o saldo devedor, que cai a cada parcela, e não sobre o valor financiado\n"
        f"  inteiro. O preço de verdade sai do capítulo 07, junto com aceite e ROI. O que\n"
        f"  esta tabela já decide é a faixa 1: {float(por_faixa.loc[1, 'perda_pct']) / 12:.2%} a.m. só de perda esperada,\n"
        f"  contra um teto de CET de 3,50% a.m. Não sobra espaço para funding, operação e\n"
        f"  margem — faixa 1 é decisão de regra, não de preço."
    )
    achados["perda_pct_base_c"] = float(total)

    ARTEFATOS.mkdir(exist_ok=True)
    comp.round(6).to_csv(ARQ_PERDA_C, index=False, encoding="utf-8")
    registrar_execucao(
        "risco",
        {
            "etapa": "src/risco",
            "ajuste_avalista_oficial": AJUSTE_AVALISTA_OFICIAL,
            "efeito_avalista_em_uso": EFEITO_AVALISTA,
            "share_avalista_tabela": SHARE_AVALISTA_TABELA,
            "fronteira_ltv": "limite inferior fechado (side=right)",
            **{k: round(v, 6) for k, v in achados.items()},
            "saida": ARQ_PERDA_C.name,
        },
    )
    print(f"\n  perda por proposta gravada em artefatos/{ARQ_PERDA_C.name}")
    print("=" * 96)


if __name__ == "__main__":
    main()
