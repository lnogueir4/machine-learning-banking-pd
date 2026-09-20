"""Política de crédito: alavancas, aceite, guardrails e ROI — Desafio AutoCred.

Este é o módulo que transforma risco em decisão. Ele recebe a perda esperada por
proposta (capítulo 06) e devolve, para cada uma das 5.000 propostas da Base C,
quatro números: aprovar ou negar, a taxa, o prazo e a entrada mínima.

Três coisas precisam ficar explícitas antes do primeiro número, porque mudam
tudo o que vem depois:

  - **O ROI do enunciado é uma margem, não um lucro.** A fórmula é
    `[(juros - perda) / volume] / prazo médio em anos`: um *quociente*. Dobrar a
    carteira não muda o quociente. Isso significa que, sem os guardrails, a
    política ótima seria aprovar o mínimo exigido, cobrar o teto e deixar a
    originação secar. O piso de R$ 40 milhões existe exatamente para impedir
    isso, e é ele — não a margem — que dita o preço desta política.

  - **A mesma fórmula premia prazo longo duas vezes.** O numerador cresce (juros
    sobre saldo que amortiza devagar) e o denominador anualiza a perda por um
    prazo maior. Um contrato de 60 meses dilui a perda por 5 anos; um de 24, por
    2. Mas a PD é medida em 12 meses e não é anualizada, então a fórmula cobra
    zero pelo risco de prazo. O histórico cobra: na Base A o default vai de 6,4%
    em 24 meses para 11,6% em 60. Esta política **nunca alonga** o prazo que o
    cliente pediu. A defesa do porquê está em `docs/07-politica.md`.

  - **A intensidade do aceite é desconhecida.** O enunciado dá a direção dos
    efeitos e esconde a magnitude, e a submissão é única. Não há como calibrar
    por tentativa e erro. A saída é declarar um modelo de aceite explícito,
    parametrizado, e escolher a política que **sobrevive ao cenário pessimista**
    em vez da que maximiza o cenário central.

Uso:
    PYTHONIOENCODING=utf-8 python src/politica.py            # auditoria + política escolhida
    PYTHONIOENCODING=utf-8 python src/politica.py --fronteira # grade completa de políticas
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from dados import ARTEFATOS, carregar_base_a, carregar_base_c, registrar_execucao
from features import matriz, parcela_price, preparar_aplicacao, taxa_referencia
from risco import distribuicao_mes_default, fator_ead_exato, lgd, saldo_price
from score import faixa

ARQ_POLITICA = ARTEFATOS / "politica_base_c.csv"
ARQ_TABELA = ARTEFATOS / "tabela_politica.csv"

# --------------------------------------------------------------------------- #
# Guardrails — os quatro limites do enunciado
# --------------------------------------------------------------------------- #
# Três deles cortam a nota de política pela metade; o CET é truncado. Tratamos
# os três primeiros como restrições duras e o CET como teto na hora de precificar.

MIN_APROVACAO = 0.35          # das 5.000 propostas, formalmente aprovadas
MAX_CET_AM = 0.035            # ao mês
MAX_INADIMPLENCIA = 0.08      # dos contratos fechados
MIN_VOLUME = 40_000_000.0     # reais efetivamente contratados

# Convenção de CET. O enunciado não define se os 3,5% a.m. são efetivos,
# nominais ou CET completo (ambiguidade 7 da leitura do enunciado). Não há
# tarifa, seguro nem IOF nas bases, então o custo total do crédito é o próprio
# juro. Adotamos **taxa efetiva mensal**, que é a mesma base em que a Base A
# registra `taxa_juros_am` e a mesma que a Tabela Price consome. É a leitura
# mais conservadora: se o simulador usasse nominal, nossa taxa estaria abaixo
# do teto, nunca acima. Sem tarifa, CET e taxa são o mesmo número, e por isso
# não existe uma constante separada para o CET neste módulo.

# Piso de preço. Não existe razão para emprestar abaixo do que a carteira antiga
# já cobrava: seria dar dinheiro de graça e ainda perder a âncora do aceite.
TAXA_MINIMA = 0.0159

PRAZOS_VALIDOS = (24, 36, 48, 60)

# Entrada que muda a faixa de LGD. O capítulo 06 provou que a fronteira é de
# limite inferior fechado: LTV de exatamente 0,80 cai na faixa **pior**. Exigir
# 20% de entrada não muda nada; 21% muda. O número é feio de propósito — é o
# corte que a evidência pediu, não um número redondo de apresentação.
ENTRADA_FURA_80 = 0.21
ENTRADA_FURA_70 = 0.31

# --------------------------------------------------------------------------- #
# O modelo de aceite
# --------------------------------------------------------------------------- #
# O cliente sente duas coisas numa oferta: quanto vai pagar por mês e quanto
# tem de tirar do bolso hoje. Tudo o mais — taxa, prazo — chega a ele por esses
# dois canais. Daí a forma:
#
#   logit(aceite) = logit(a0)
#                   - b_parcela x (aumento % da parcela sobre a esperada)
#                   - b_caixa   x (entrada extra exigida, em meses de renda)
#
# A parcela de referência é a que o cliente teria na **taxa da carteira antiga,
# com o prazo e a entrada que ele mesmo pediu**. É a oferta que ele esperava
# receber, e por isso o ponto onde o aceite vale `a0`.
#
# Encaixar o prazo dentro da parcela, em vez de dar a ele um termo próprio,
# não é economia de parâmetro: é o mecanismo certo. Encurtar o prazo reduz o
# aceite *porque* engorda a parcela, e o quanto depende da taxa. Um termo
# separado para o prazo contaria o mesmo efeito duas vezes.


@dataclass(frozen=True)
class Aceite:
    """Elasticidades do aceite. A direção vem do enunciado; a magnitude, não."""

    nome: str
    a0: float           # aceite na oferta de referência
    b_parcela: float    # por 1% de aumento da parcela
    b_caixa: float      # por mês de renda de entrada extra
    k_selecao: float    # seleção adversa: aumento relativo da PD por p.p. de prêmio


# Os três cenários. O central não é um palpite solto: ele é o único que reproduz
# a intenção declarada do enunciado — que o piso de R$ 40 milhões seja capaz de
# derrubar a "solução degenerada" de aprovar pouco, cobrar o teto e exigir
# entrada alta. `auditar()` mostra essa checagem, seção 2.
CENARIOS = {
    "otimista": Aceite("otimista", a0=0.90, b_parcela=0.027, b_caixa=0.51, k_selecao=0.05),
    "central": Aceite("central", a0=0.85, b_parcela=0.045, b_caixa=0.85, k_selecao=0.15),
    "pessimista": Aceite("pessimista", a0=0.75, b_parcela=0.072, b_caixa=1.36, k_selecao=0.30),
}

# Multiplicadores de PD para o teste de estresse. A Base C é mar aberto e o PSI
# da Base A para ela é 0,473 — deslocamento grande. Não dá para identificar o
# nível verdadeiro da PD em C com os dados que temos (a discussão está no
# capítulo 05). Em vez de corrigir um nível que não se pode medir, testamos a
# política contra o nível estar errado.
ESTRESSE_PD = (1.00, 1.20, 1.40)


# --------------------------------------------------------------------------- #
# A regra: o que a política decide, por faixa
# --------------------------------------------------------------------------- #
# Taxa, prazo e entrada são função **da faixa**, nunca da proposta individual.
# Não é simplificação: é o que torna a tabela do documento de política idêntica
# à submissão linha a linha — os 10 pontos de coerência do enunciado. Uma taxa
# contínua por proposta seria melhor no papel e indefensável no comitê.


@dataclass(frozen=True)
class Regra:
    """Uma política completa, em seis números."""

    corte: int            # menor faixa aprovada
    alvo_roi: float       # ROI anualizado que o preço de cada faixa persegue
    faixa_entrada: int    # faixas abaixo desta exigem entrada que fure o corte de 80%
    faixa_entrada_forte: int  # ... e abaixo desta, o corte de 70%
    faixa_prazo: int      # faixas abaixo desta têm o prazo limitado
    prazo_cap: int        # ao quanto
    inclinacao: float = 0.0   # prêmio de ROI adicional cobrado das faixas piores

    def alvo_da_faixa(self, f) -> np.ndarray:
        """Alvo de ROI por faixa: o alvo base mais a inclinação.

        Precificar só a custo (`inclinacao = 0`) já cobra mais caro de quem é
        mais arriscado — é o que a bisseção faz. A inclinação vai além disso e
        usa o preço como **seleção**: encarecer a pior faixa aprovada não serve
        para cobrir a perda dela, e sim para que menos gente dessa faixa aceite.
        Como o ROI do enunciado é um quociente, mudar a composição da carteira
        move o resultado tanto quanto mudar o preço.
        """
        return self.alvo_roi + self.inclinacao * (10 - np.asarray(f)) / 9.0

    def rotulo(self) -> str:
        return (
            f"corte>={self.corte} alvo={self.alvo_roi:.0%}+{self.inclinacao:.0%} "
            f"entrada<{self.faixa_entrada}/{self.faixa_entrada_forte} "
            f"prazo<{self.faixa_prazo}:{self.prazo_cap}m"
        )


# --------------------------------------------------------------------------- #
# Matemática financeira da oferta
# --------------------------------------------------------------------------- #


def juros_ate(valor_financiado, taxa_am, prazo_meses, parcelas_pagas):
    """Juros efetivamente recebidos em `k` parcelas.

    Numa Price cada parcela carrega juro e principal. O juro acumulado é o total
    pago menos o principal devolvido: `k·PMT − (V − saldo_k)`. É esta a conta que
    o enunciado pede quando diz que *contrato inadimplente gera juros só até o
    mês do default*.
    """
    v = np.asarray(valor_financiado, dtype="float64")
    k = np.asarray(parcelas_pagas, dtype="float64")
    pago = k * parcela_price(v, taxa_am, prazo_meses)
    principal = v - saldo_price(v, taxa_am, prazo_meses, k)
    return pago - principal


def juros_esperados(valor_financiado, taxa_am, prazo_meses, pd_12m, atraso: int = 3):
    """Juros esperados do contrato, separando quem paga de quem quebra.

    `(1 − PD) · juros do contrato inteiro + PD · juros até o mês do default`.

    O `(1 − PD)` é o termo que decide a política. Sem ele, a faixa 1 pareceria
    rentável ao teto de CET: 108% de juros sobre 33% de perda. Com ele, só 57%
    dos contratos chegam ao fim, e a conta vira 8% ao ano — abaixo de qualquer
    faixa que se aprove. Ver `auditar()`, seção 3.
    """
    v = np.asarray(valor_financiado, dtype="float64")
    i = np.asarray(taxa_am, dtype="float64")
    n = np.asarray(prazo_meses, dtype="float64")
    p = np.asarray(pd_12m, dtype="float64")

    inteiro = n * parcela_price(v, i, n) - v
    parcial = np.zeros(np.broadcast(v, i, n).shape, dtype="float64")
    for mes, frequencia in distribuicao_mes_default().items():
        pagas = max(int(mes) - atraso, 0)
        parcial = parcial + frequencia * juros_ate(v, i, n, pagas)
    return (1 - p) * inteiro + p * parcial


def roi_anualizado(juros, perda, volume, prazo_medio_meses) -> float:
    """A fórmula do enunciado, literal: `[(juros − perda) / volume] / (prazo/12)`."""
    if volume <= 0:
        return float("nan")
    return (float(juros) - float(perda)) / float(volume) / (float(prazo_medio_meses) / 12.0)


def roi_do_contrato(valor_financiado, taxa_am, prazo_meses, pd_12m, perda_esperada):
    """ROI anualizado de um contrato isolado — a base do preço por faixa."""
    j = juros_esperados(valor_financiado, taxa_am, prazo_meses, pd_12m)
    v = np.asarray(valor_financiado, dtype="float64")
    n = np.asarray(prazo_meses, dtype="float64")
    return (j - np.asarray(perda_esperada, dtype="float64")) / v / (n / 12.0)


def taxa_para_roi(alvo, valor_financiado, prazo_meses, pd_12m, idade, ltv, avalista,
                  lo: float = TAXA_MINIMA, hi: float = MAX_CET_AM, passos: int = 40):
    """Menor taxa que entrega `alvo` de ROI anualizado, por bisseção.

    Não tem forma fechada porque a taxa entra dos dois lados: ela é a receita e,
    pelo capítulo 06, também empurra o EAD para cima (juro alto amortiza devagar,
    o saldo no mês do default é maior). O laço preço-risco é resolvido aqui,
    numericamente, em vez de ignorado.

    Devolve `hi` quando nem o teto entrega o alvo — é esse o sinal de que a faixa
    não cabe na política.
    """
    g = lgd(idade, ltv, avalista)
    baixo = np.full(np.shape(valor_financiado), float(lo), dtype="float64")
    alto = np.full(np.shape(valor_financiado), float(hi), dtype="float64")
    for _ in range(passos):
        meio = (baixo + alto) / 2
        perda = np.asarray(pd_12m) * fator_ead_exato(meio, prazo_meses) * np.asarray(
            valor_financiado
        ) * g
        r = roi_do_contrato(valor_financiado, meio, prazo_meses, pd_12m, perda)
        baixo = np.where(r < alvo, meio, baixo)
        alto = np.where(r < alvo, alto, meio)
    return np.clip(alto, lo, hi)


# --------------------------------------------------------------------------- #
# Aceite e seleção adversa
# --------------------------------------------------------------------------- #


def parcela_referencia(c: pd.DataFrame) -> np.ndarray:
    """A parcela que o cliente esperava: prazo e entrada dele, taxa da carteira antiga."""
    return parcela_price(
        c["valor_financiado_desejado"], taxa_referencia(), c["prazo_desejado_meses"]
    )


def probabilidade_aceite(c: pd.DataFrame, oferta: pd.DataFrame, cen: Aceite) -> np.ndarray:
    """Probabilidade de o cliente fechar o contrato na oferta que fizemos.

    Renda ausente (7,9% da Base C) usa a mediana da própria base para converter a
    entrada extra em meses de renda — deixar `NaN` propagaria e mataria a linha.
    """
    ref = parcela_referencia(c)
    nova = parcela_price(oferta["valor_financiado"], oferta["taxa_am"], oferta["prazo_meses"])
    aumento_pct = (np.asarray(nova) / np.asarray(ref) - 1.0) * 100.0

    renda = c["renda_mensal_declarada"].fillna(c["renda_mensal_declarada"].median())
    extra = np.maximum(oferta["valor_entrada"].to_numpy() - c["valor_entrada_desejada"].to_numpy(), 0.0)
    meses_de_renda = extra / renda.to_numpy()

    z = (
        np.log(cen.a0 / (1 - cen.a0))
        - cen.b_parcela * aumento_pct
        - cen.b_caixa * meses_de_renda
    )
    return 1.0 / (1.0 + np.exp(-z))


def pd_com_selecao(pd_12m, taxa_am, cen: Aceite) -> np.ndarray:
    """PD dos contratos que **aceitam**, não dos que recebem a oferta.

    Quem aceita um preço acima do mercado é quem não tem para onde ir. O
    enunciado declara o efeito e omite a força; aqui ele é linear no prêmio de
    preço, em pontos percentuais ao mês sobre a taxa de referência.

    O canal mecânico — parcela maior, comprometimento de renda maior — já está no
    modelo de PD e responde por cerca de +4,3% de PD relativa por p.p. de taxa.
    O `k_selecao` é o que vem **além** disso, e é o que não se pode medir nos
    dados que temos: não há uma única proposta recusada por cliente na Base A.
    """
    premio_pp = (np.asarray(taxa_am, dtype="float64") - taxa_referencia()) * 100.0
    return np.asarray(pd_12m, dtype="float64") * (1.0 + cen.k_selecao * np.maximum(premio_pp, 0.0))


# --------------------------------------------------------------------------- #
# Aplicar a regra à Base C
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def _modelo():
    import joblib

    from modelo import ARQ_MODELO

    return joblib.load(ARQ_MODELO)


def enquadrar(c: pd.DataFrame | None = None) -> pd.DataFrame:
    """Primeira passada: PD e faixa nas condições que o cliente pediu.

    É o enquadramento, não o preço. A faixa sai daqui e não se mexe mais: ela
    descreve a proposta que chegou, e é sobre ela que a política se organiza.
    Se a faixa dependesse da oferta, a tabela de política seria circular — a
    oferta sai da faixa que sairia da oferta.
    """
    c = carregar_base_c() if c is None else c
    preparada = preparar_aplicacao(c)
    p = _modelo().predict_proba(matriz(preparada))[:, 1]
    return pd.DataFrame(
        {
            "id_proposta": c["id_proposta"].to_numpy(),
            "pd_enquadramento": p,
            "faixa": faixa(p),
        }
    )


def aplicar(regra: Regra, c: pd.DataFrame | None = None,
            quadro: pd.DataFrame | None = None) -> pd.DataFrame:
    """A regra vira uma oferta concreta por proposta.

    Ordem das alavancas, e ela importa: entrada primeiro (muda o valor
    financiado, o LTV e portanto a LGD), depois prazo, e só então a taxa — que
    é precificada sobre o risco **já reduzido** pelas duas primeiras. Precificar
    antes de exigir entrada cobraria do cliente um risco que a própria política
    acabou de tirar da mesa.
    """
    c = carregar_base_c() if c is None else c
    quadro = enquadrar(c) if quadro is None else quadro
    f = quadro["faixa"].to_numpy()

    # 1. Entrada mínima, por faixa.
    exigida = np.where(
        f < regra.faixa_entrada_forte,
        ENTRADA_FURA_70,
        np.where(f < regra.faixa_entrada, ENTRADA_FURA_80, 0.0),
    )
    pct_entrada = np.maximum(c["pct_entrada_desejada"].to_numpy(), exigida)
    valor_entrada = pct_entrada * c["valor_bem"].to_numpy()

    # 2. Prazo. Só encurta; nunca alonga o que o cliente pediu.
    desejado = c["prazo_desejado_meses"].to_numpy()
    prazo = np.where(f < regra.faixa_prazo, np.minimum(desejado, regra.prazo_cap), desejado)

    # 3. PD e LGD nas condições ofertadas, antes do preço.
    preparada = preparar_aplicacao(
        c,
        taxa_am=taxa_referencia(),
        prazo_meses=pd.Series(prazo, index=c.index),
        valor_entrada=pd.Series(valor_entrada, index=c.index),
    )
    p_oferta = _modelo().predict_proba(matriz(preparada))[:, 1]

    # 4. Taxa: a que entrega o alvo de ROI, por faixa, truncada no teto de CET.
    taxa_proposta = taxa_para_roi(
        regra.alvo_da_faixa(f),
        preparada["valor_financiado"].to_numpy(),
        prazo,
        p_oferta,
        preparada["idade_veiculo_anos"].to_numpy(),
        preparada["ltv"].to_numpy(),
        preparada["possui_avalista"].to_numpy(),
    )
    # Uma taxa por faixa, não por proposta: a mediana da faixa. É o que a tabela
    # do documento publica e o que a submissão repete linha a linha.
    tabela_taxa = pd.Series(taxa_proposta).groupby(f).median()
    taxa = np.round(pd.Series(f).map(tabela_taxa).to_numpy(), 4)
    taxa = np.clip(taxa, TAXA_MINIMA, MAX_CET_AM)

    aprovado = f >= regra.corte

    oferta = pd.DataFrame(
        {
            "id_proposta": c["id_proposta"].to_numpy(),
            "faixa": f,
            "pd_enquadramento": quadro["pd_enquadramento"].to_numpy(),
            "decisao": np.where(aprovado, "APROVAR", "NEGAR"),
            "taxa_am": taxa,
            "prazo_meses": prazo.astype("int64"),
            "pct_entrada_minima": np.round(exigida, 4),
            "pct_entrada_efetiva": pct_entrada,
            "valor_entrada": valor_entrada,
            "valor_financiado": preparada["valor_financiado"].to_numpy(),
            "ltv": preparada["ltv"].to_numpy(),
            "idade_veiculo_anos": preparada["idade_veiculo_anos"].to_numpy(),
            "possui_avalista": preparada["possui_avalista"].to_numpy(),
            "pd_oferta": p_oferta,
        }
    )
    return oferta


# --------------------------------------------------------------------------- #
# Simular a carteira
# --------------------------------------------------------------------------- #


def simular(oferta: pd.DataFrame, cen: Aceite, c: pd.DataFrame | None = None,
            mult_pd: float = 1.0) -> dict:
    """Carteira esperada sob um cenário de aceite e um nível de PD.

    O aceite entra como **peso**, não como sorteio: cada proposta contribui com
    a sua probabilidade de fechar. O simulador oficial é determinístico, mas nós
    não conhecemos o sorteio dele; a esperança é o único resumo honesto, e é
    estável, que é o que importa para escolher entre políticas.
    """
    c = carregar_base_c() if c is None else c
    aprovado = oferta["decisao"].to_numpy() == "APROVAR"

    aceite = probabilidade_aceite(c, oferta, cen)
    peso = np.where(aprovado, aceite, 0.0)

    pd_final = np.clip(pd_com_selecao(oferta["pd_oferta"], oferta["taxa_am"], cen) * mult_pd, 0, 1)
    v = oferta["valor_financiado"].to_numpy()
    n = oferta["prazo_meses"].to_numpy()
    i = oferta["taxa_am"].to_numpy()

    g = lgd(oferta["idade_veiculo_anos"], oferta["ltv"], oferta["possui_avalista"])
    perda = pd_final * fator_ead_exato(i, n) * v * g
    juros = juros_esperados(v, i, n, pd_final)

    volume = float(np.sum(peso * v))
    contratos = float(np.sum(peso))
    prazo_medio = float(np.sum(peso * v * n) / np.sum(peso * v)) if volume > 0 else float("nan")

    return {
        "cenario": cen.nome,
        "mult_pd": mult_pd,
        "aprovacao": float(aprovado.mean()),
        "aceite_medio": float(np.sum(peso) / max(aprovado.sum(), 1)),
        "contratos": contratos,
        "volume": volume,
        "prazo_medio": prazo_medio,
        "juros": float(np.sum(peso * juros)),
        "perda": float(np.sum(peso * perda)),
        "inadimplencia": float(np.sum(peso * pd_final) / contratos) if contratos > 0 else float("nan"),
        "taxa_media": float(np.sum(peso * v * i) / volume) if volume > 0 else float("nan"),
        "roi": roi_anualizado(
            np.sum(peso * juros), np.sum(peso * perda), volume, prazo_medio
        ),
    }


def guardrails(m: dict) -> dict:
    """Quais dos quatro limites a carteira cumpre."""
    return {
        "aprovacao": m["aprovacao"] >= MIN_APROVACAO,
        "volume": m["volume"] >= MIN_VOLUME,
        "inadimplencia": m["inadimplencia"] <= MAX_INADIMPLENCIA,
        "cet": m["taxa_media"] <= MAX_CET_AM + 1e-9,
    }


def todos_ok(m: dict) -> bool:
    return all(guardrails(m).values())


def folgas(m: dict) -> dict:
    """Quanto sobra em cada guardrail, em termos relativos.

    Positivo é folga. Medir em relativo, e não em reais ou pontos percentuais,
    é o que permite comparar R$ 43 milhões contra 7,5% de inadimplência: os dois
    viram "quanto a carteira pode piorar antes de a nota ser cortada pela metade".
    """
    return {
        "aprovacao": m["aprovacao"] / MIN_APROVACAO - 1,
        "volume": m["volume"] / MIN_VOLUME - 1,
        "inadimplencia": MAX_INADIMPLENCIA / m["inadimplencia"] - 1,
    }


# O canto duro: aceite pessimista **e** PD 20% acima da prevista, ao mesmo tempo.
# É contra ele que a política é escolhida, não contra o cenário central.
CANTO_DURO = ("pessimista", 1.20)

# Folga mínima exigida em todo guardrail, no canto duro. O número é uma decisão,
# não um resultado: 4% é aproximadamente o quanto a carteira pode encolher sem
# que o erro de um único parâmetro do modelo de aceite derrube um guardrail.
# Acima disso, sobra ROI na mesa; abaixo, a nota vira aposta.
MARGEM_MINIMA = 0.04


def no_canto_duro(oferta: pd.DataFrame, c: pd.DataFrame) -> dict:
    nome, mult = CANTO_DURO
    return simular(oferta, CENARIOS[nome], c, mult_pd=mult)


# --------------------------------------------------------------------------- #
# A busca
# --------------------------------------------------------------------------- #


def grade() -> list[Regra]:
    """A família de políticas candidatas.

    Pequena de propósito. Uma otimização livre sobre 40 parâmetros encontraria
    um ótimo melhor no cenário central e indefensável em qualquer outro — e o
    enunciado avisa que a submissão é única. Cada eixo aqui é uma decisão que
    cabe numa frase de documento de política.
    """
    regras = []
    for corte in (4, 5, 6, 7):
        for alvo in (0.15, 0.16, 0.17, 0.20):
            for inclinacao in (0.0, 0.04, 0.08, 0.16):
                for f_ent, f_forte in ((0, 0), (7, 0), (11, 5)):
                    for f_prazo, cap in ((0, 60), (5, 48)):
                        regras.append(
                            Regra(corte, alvo, f_ent, f_forte, f_prazo, cap, inclinacao)
                        )
    return regras


def avaliar(regra: Regra, c: pd.DataFrame, quadro: pd.DataFrame) -> dict:
    """Uma regra, avaliada no cenário central e no canto duro."""
    oferta = aplicar(regra, c, quadro)
    central = simular(oferta, CENARIOS["central"], c)
    duro = no_canto_duro(oferta, c)
    f = folgas(duro)
    return {
        "regra": regra,
        "oferta": oferta,
        "central": central,
        "duro": duro,
        "roi_central": central["roi"],
        "roi_duro": duro["roi"],
        "folga_min": min(f.values()),
        "folga_de": min(f, key=f.get),
        "ok_duro": todos_ok(duro),
    }


def buscar(c: pd.DataFrame, quadro: pd.DataFrame, verbose: bool = False) -> list[dict]:
    """Avalia a grade e ordena pelo critério de escolha.

    O critério, em uma frase: **entre as regras que cumprem os quatro guardrails
    no canto duro com pelo menos `MARGEM_MINIMA` de folga em todos, a de maior
    ROI.** Não é "a de maior ROI" nem "a mais segura" — é a de maior ROI dentro
    do que ainda é seguro, e a fronteira entre as duas coisas fica publicada.
    """
    saida = []
    for k, regra in enumerate(grade()):
        saida.append(avaliar(regra, c, quadro))
        if verbose and k % 64 == 0:
            print(f"    ... {k + 1} de {len(grade())} regras avaliadas")
    saida.sort(
        key=lambda r: (
            r["ok_duro"] and r["folga_min"] >= MARGEM_MINIMA,
            r["roi_central"],
        ),
        reverse=True,
    )
    return saida


# --------------------------------------------------------------------------- #
# A política escolhida
# --------------------------------------------------------------------------- #
# Preenchida por `--fronteira` e congelada aqui. Congelar é deliberado: o
# artefato de submissão não pode depender de uma busca que mude de resultado
# quando a grade for editada.

ESCOLHIDA = Regra(
    corte=5,             # faixas 1 a 4 são negadas
    alvo_roi=0.15,       # ROI anualizado que a faixa 10 persegue
    inclinacao=0.04,     # +4 p.p. de alvo descendo até a faixa 1 — preço como seleção
    faixa_entrada=7,     # faixas 5 e 6 precisam furar o corte de LTV de 80%
    faixa_entrada_forte=0,   # nenhuma faixa aprovada precisa furar o de 70%
    faixa_prazo=0,       # nenhum prazo é encurtado: vale o que o cliente pediu
    prazo_cap=60,
)


# --------------------------------------------------------------------------- #
# Auditoria
# --------------------------------------------------------------------------- #


def _cab(titulo: str) -> None:
    print(f"{chr(10)}--- {titulo} ---{chr(10)}")


def auditar(c: pd.DataFrame, quadro: pd.DataFrame) -> dict:
    achados: dict = {}

    # 1. O que a fórmula de ROI premia ------------------------------------- #
    _cab("1. A fórmula de ROI cobra zero pelo prazo, e o histórico cobra caro")
    print("  juros totais / valor financiado, já anualizados por (prazo/12):")
    print(f"  {'taxa a.m.':>11}" + "".join(f"{n:>11}" for n in PRAZOS_VALIDOS))
    for i in (0.0159, 0.025, 0.035):
        linha = f"  {i:>11.2%}"
        for n in PRAZOS_VALIDOS:
            j = n * i / (1 - (1 + i) ** -n) - 1
            linha += f"{j * 12 / n:>11.2%}"
        print(linha)
    print(f"{chr(10)}  e a perda, que é única, é dividida pelo mesmo prazo:")
    print(f"  {'perda/volume':>14}" + "".join(f"{n:>11}" for n in PRAZOS_VALIDOS))
    for pp in (0.05, 0.10):
        print(f"  {pp:>14.1%}" + "".join(f"{pp * 12 / n:>11.2%}" for n in PRAZOS_VALIDOS))

    a = carregar_base_a()
    g = a.groupby("prazo_meses").agg(
        n=("default_90_12", "size"), taxa=("default_90_12", "mean"),
        renda=("renda_mensal_declarada", "median"),
    )
    print(f"{chr(10)}  o que o histórico diz do mesmo prazo (Base A):")
    print(f"  {'prazo':>7}{'n':>8}{'default':>10}{'renda mediana':>16}")
    for prazo, linha in g.iterrows():
        print(
            f"  {int(prazo):>7}{int(linha['n']):>8,}{linha['taxa']:>10.2%}"
            f"{linha['renda']:>16,.0f}"
        )
    achados["default_24m_base_a"] = float(g.loc[24, "taxa"])
    achados["default_60m_base_a"] = float(g.loc[60, "taxa"])

    preparada60 = preparar_aplicacao(c, prazo_meses=pd.Series(60, index=c.index))
    preparada24 = preparar_aplicacao(c, prazo_meses=pd.Series(24, index=c.index))
    modelo = _modelo()
    pd60 = float(modelo.predict_proba(matriz(preparada60))[:, 1].mean())
    pd24 = float(modelo.predict_proba(matriz(preparada24))[:, 1].mean())
    achados["pd_media_c_24m"] = pd24
    achados["pd_media_c_60m"] = pd60
    print(
        f"{chr(10)}  -> alongar todo mundo para 60 meses subiria o ROI simulado e a PD média{chr(10)}"
        f"     da Base C de {pd24:.4f} para {pd60:.4f} (+{pd60 / pd24 - 1:.0%}). Mas parte desse salto{chr(10)}"
        f"     é composição, não causa: quem escolhe 60 meses na Base A ganha R$ "
        f"{g.loc[60, 'renda']:,.0f}{chr(10)}"
        f"     contra R$ {g.loc[24, 'renda']:,.0f} de quem escolhe 24. Impor 60 meses a quem pediu 24 é{chr(10)}"
        f"     extrapolar o modelo para fora do que ele viu. Esta política só encurta prazo."
    )

    # 2. O modelo de aceite reproduz a intenção do piso de volume ---------- #
    _cab("2. O piso de R$ 40 milhões, e por que ele calibra o modelo de aceite")
    volume_desejado = float(c["valor_financiado_desejado"].sum())
    achados["volume_desejado_c"] = volume_desejado
    print(
        f"  volume que a Base C pede ......... R$ {volume_desejado:,.0f}{chr(10)}"
        f"  piso do guardrail ................ R$ {MIN_VOLUME:,.0f}  "
        f"({MIN_VOLUME / volume_desejado:.1%} do pedido)"
    )
    degenerada = Regra(corte=7, alvo_roi=0.60, faixa_entrada=11, faixa_entrada_forte=5,
                       faixa_prazo=0, prazo_cap=60)
    oferta_deg = aplicar(degenerada, c, quadro)
    print(
        f"{chr(10)}  a 'solução degenerada' que o enunciado diz querer impedir — aprovar só o{chr(10)}"
        f"  topo, cobrar o teto, exigir entrada alta:"
    )
    print(f"  {'cenário de aceite':<20}{'aceite':>9}{'volume':>16}{'piso?':>8}")
    for nome, cen in CENARIOS.items():
        m = simular(oferta_deg, cen, c)
        print(
            f"  {nome:<20}{m['aceite_medio']:>9.1%}{m['volume']:>16,.0f}"
            f"{('passa' if m['volume'] >= MIN_VOLUME else 'QUEBRA'):>8}"
        )
        achados[f"volume_degenerada_{nome}"] = m["volume"]
    print(
        f"{chr(10)}  -> e aqui está a única âncora que este projeto tem para calibrar o aceite.{chr(10)}"
        f"     Não há uma só proposta recusada por cliente em nenhuma das três bases: o{chr(10)}"
        f"     dado que mediria a elasticidade não existe. O que existe é a afirmação do{chr(10)}"
        f"     enunciado de que o piso de volume serve para impedir a degenerada. Ela só{chr(10)}"
        f"     é verdade a partir do nosso cenário central — no otimista a degenerada{chr(10)}"
        f"     passa, com R$ {achados['volume_degenerada_otimista']:,.0f}. Ou seja: **se o enunciado diz a verdade{chr(10)}"
        f"     sobre a função do guardrail, a elasticidade real é pelo menos a do nosso{chr(10)}"
        f"     cenário central.** É inferência fraca, e é toda a que há."
    )

    # 3. Preço por faixa ---------------------------------------------------- #
    _cab("3. Quanto cada faixa precisa cobrar, e onde o teto de CET corta")
    base = aplicar(replace(ESCOLHIDA, corte=1), c, quadro)
    cen = CENARIOS["central"]
    por_faixa = []
    for f in range(1, 11):
        sel = base["faixa"].to_numpy() == f
        sub = base.loc[sel]
        alvo_f = float(ESCOLHIDA.alvo_da_faixa(f))
        necessaria = taxa_para_roi(
            alvo_f, sub["valor_financiado"].to_numpy(), sub["prazo_meses"].to_numpy(),
            sub["pd_oferta"].to_numpy(), sub["idade_veiculo_anos"].to_numpy(),
            sub["ltv"].to_numpy(), sub["possui_avalista"].to_numpy(),
        )
        no_teto = np.full(len(sub), MAX_CET_AM)  # o ROI que a faixa entrega cobrando 3,5%
        gl = lgd(sub["idade_veiculo_anos"], sub["ltv"], sub["possui_avalista"])
        perda_teto = (
            sub["pd_oferta"].to_numpy()
            * fator_ead_exato(no_teto, sub["prazo_meses"].to_numpy())
            * sub["valor_financiado"].to_numpy()
            * gl
        )
        roi_teto = float(
            np.average(
                roi_do_contrato(
                    sub["valor_financiado"].to_numpy(), no_teto, sub["prazo_meses"].to_numpy(),
                    sub["pd_oferta"].to_numpy(), perda_teto,
                ),
                weights=sub["valor_financiado"].to_numpy(),
            )
        )
        por_faixa.append(
            {
                "faixa": f, "n": int(sel.sum()), "pd": float(sub["pd_oferta"].mean()),
                "alvo": alvo_f, "taxa_necessaria": float(np.median(necessaria)),
                "roi_no_teto": roi_teto,
            }
        )
    print(
        f"  {'faixa':>6}{'n':>7}{'PD':>9}{'alvo de ROI':>13}{'taxa necessária':>17}"
        f"{'ROI a 3,5%':>13}{'veredito':>12}"
    )
    for linha in reversed(por_faixa):
        cabe = linha["roi_no_teto"] >= linha["alvo"]
        print(
            f"  {linha['faixa']:>6}{linha['n']:>7,}{linha['pd']:>9.2%}{linha['alvo']:>13.1%}"
            f"{linha['taxa_necessaria']:>17.2%}{linha['roi_no_teto']:>13.1%}"
            f"{('cabe' if cabe else 'não cabe'):>12}"
        )
    achados["roi_no_teto_faixa1"] = por_faixa[0]["roi_no_teto"]
    achados["roi_no_teto_faixa2"] = por_faixa[1]["roi_no_teto"]
    nao_cabem = [l["faixa"] for l in por_faixa if l["roi_no_teto"] < l["alvo"]]
    achados["faixas_sem_preco_viavel"] = max(nao_cabem)
    print(
        f"{chr(10)}  -> as faixas {min(nao_cabem)} e {max(nao_cabem)} não têm preço viável: nem cobrando o teto de{chr(10)}"
        f"     {MAX_CET_AM:.1%} a.m. elas alcançam o alvo. A faixa 1 fica em "
        f"{por_faixa[0]['roi_no_teto']:.1%} ao ano.{chr(10)}"
        f"     Não é preço que resolve, é o (1 − PD) dos juros: com PD de "
        f"{por_faixa[0]['pd']:.0%}, quase{chr(10)}"
        f"     metade dos contratos nunca chega ao fim para pagar o juro que deveria{chr(10)}"
        f"     ter precificado o risco da outra metade. Preço só funciona onde há{chr(10)}"
        f"     quem sobreviva para pagá-lo.{chr(10)}"
        f"{chr(10)}     Repare que esta seção **não** decide o corte da política. Ela só diz{chr(10)}"
        f"     onde o preço deixa de existir. Onde ele existe mas não cabe no{chr(10)}"
        f"     portfólio é a seção 4 que resolve."
    )

    # 4. A fronteira: onde cada guardrail morde ---------------------------- #
    _cab("4. Onde cada guardrail morde — o corte de faixa")
    print(
        f"  {'aprova de':<12}{'aprov.':>8}{'ROI':>8}"
        f"{'volume central':>17}{'inadimpl.':>11}{'  |':>3}"
        f"{'volume duro':>15}{'inadimpl.':>11}{'guardrails no duro':>21}"
    )
    corte_viavel = None
    for corte in range(1, 9):
        r = replace(ESCOLHIDA, corte=corte)
        oferta_c = aplicar(r, c, quadro)
        m = simular(oferta_c, cen, c)
        d = no_canto_duro(oferta_c, c)
        falhas = [k for k, v in guardrails(d).items() if not v]
        fmin = min(folgas(d).values())
        if not falhas and fmin >= MARGEM_MINIMA and corte_viavel is None:
            corte_viavel = corte
        print(
            f"  {'faixa ' + str(corte):<12}{m['aprovacao']:>8.1%}{m['roi']:>8.1%}"
            f"{m['volume']:>17,.0f}{m['inadimplencia']:>11.2%}{'  |':>3}"
            f"{d['volume']:>15,.0f}{d['inadimplencia']:>11.2%}"
            f"{(', '.join(falhas) if falhas else f'ok, folga {fmin:.0%}'):>21}"
        )
    achados["corte_viavel"] = corte_viavel
    quantas = int((quadro["faixa"] < corte_viavel).sum() - (quadro["faixa"] < 4).sum())
    print(
        f"{chr(10)}  -> os guardrails se opõem: subir o corte melhora inadimplência e ROI e mata{chr(10)}"
        f"     aprovação e volume. No cenário central a política caberia a partir da{chr(10)}"
        f"     faixa 4; no canto duro, só a partir da faixa {corte_viavel}. A diferença são{chr(10)}"
        f"     {quantas} propostas, e é toda ela margem de segurança.{chr(10)}"
        f"{chr(10)}     Note que isso dá **dois motivos diferentes** para negar. As faixas 1 e 2{chr(10)}"
        f"     são negadas porque nenhum preço abaixo do teto de CET as torna viáveis{chr(10)}"
        f"     (seção 3). As faixas 3 e 4 têm preço viável e são negadas assim mesmo,{chr(10)}"
        f"     porque entram na conta da inadimplência e ela é do portfólio, não da{chr(10)}"
        f"     proposta. Um documento de política que não separa os dois casos não{chr(10)}"
        f"     sabe o que fazer quando o guardrail mudar."
    )
    return achados


def relatar(regra: Regra, c: pd.DataFrame, quadro: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """A política escolhida, aberta por faixa, com estresse."""
    oferta = aplicar(regra, c, quadro)
    cen = CENARIOS["central"]

    central = simular(oferta, cen, c)
    duro = no_canto_duro(oferta, c)

    _cab("5. A política: o que cada faixa recebe")
    aceite = probabilidade_aceite(c, oferta, cen)
    oferta = oferta.assign(aceite=aceite)

    # Receita e perda esperadas por contrato, nas condições ofertadas e com a
    # seleção adversa do cenário — os mesmos números que `simular()` agrega.
    pd_final = pd_com_selecao(oferta["pd_oferta"], oferta["taxa_am"], cen)
    v = oferta["valor_financiado"].to_numpy()
    n = oferta["prazo_meses"].to_numpy()
    i = oferta["taxa_am"].to_numpy()
    g = lgd(oferta["idade_veiculo_anos"], oferta["ltv"], oferta["possui_avalista"])
    oferta = oferta.assign(
        juros_esp=juros_esperados(v, i, n, pd_final),
        perda_esp=pd_final * fator_ead_exato(i, n) * v * g,
    )

    linhas = []
    for f in range(10, 0, -1):
        sub = oferta.loc[oferta["faixa"] == f]
        if sub.empty:
            continue
        aprova = sub["decisao"].iloc[0] == "APROVAR"
        peso = sub["aceite"].to_numpy() if aprova else np.zeros(len(sub))
        volume = float(np.sum(peso * sub["valor_financiado"].to_numpy()))
        juros = float(np.sum(peso * sub["juros_esp"].to_numpy()))
        perda = float(np.sum(peso * sub["perda_esp"].to_numpy()))
        prazo_v = (
            float(np.sum(peso * sub["valor_financiado"].to_numpy() * sub["prazo_meses"].to_numpy())
                  / volume) if volume > 0 else float("nan")
        )
        linhas.append(
            {
                "faixa": f,
                "n": len(sub),
                "decisao": sub["decisao"].iloc[0],
                "taxa_am": float(sub["taxa_am"].iloc[0]),
                # Ponderado por volume e aceite, igual ao que alimenta o ROI
                # logo abaixo. A media simples publicava um prazo que NAO
                # reproduz o `roi` da propria linha: quem refizesse a conta
                # (juros_pct - perda_pct) / (prazo_medio/12) errava por ate
                # 0,59 p.p. na faixa 5, e o erro crescia em direcao as faixas
                # piores, onde o prazo longo tem menos aceite.
                "prazo_medio": prazo_v,
                "entrada_minima": float(sub["pct_entrada_minima"].iloc[0]),
                # Duas PDs, e a distinção precisa estar na tabela publicada.
                # `pd_publicada` é a do enquadramento, nas condições que o
                # cliente pediu — é ela que vai na coluna `pd` da submissão, e
                # é dela que a faixa saiu. `pd_precificada` é a PD depois de a
                # entrada exigida derrubar o LTV, e é ela que a taxa cobre.
                # Publicar só uma faria a tabela do documento divergir da
                # submissão sem que ninguém soubesse por quê.
                "pd_publicada": float(sub["pd_enquadramento"].mean()),
                "pd_precificada": float(sub["pd_oferta"].mean()),
                "aceite": float(np.mean(sub["aceite"])) if aprova else 0.0,
                "volume": volume,
                "juros": juros,
                "perda": perda,
                "juros_pct": juros / volume if volume > 0 else float("nan"),
                "perda_pct": perda / volume if volume > 0 else float("nan"),
                "roi": roi_anualizado(juros, perda, volume, prazo_v) if volume > 0 else float("nan"),
            }
        )
    tabela = pd.DataFrame(linhas)
    # Faixa negada não tem preço, prazo nem entrada: publicar os números que ela
    # *teria* ao lado de um NEGAR é o tipo de tabela que confunde o comitê.
    negadas = tabela["decisao"] == "NEGAR"
    tabela.loc[
        negadas,
        ["taxa_am", "prazo_medio", "entrada_minima", "aceite", "volume",
         "juros", "perda", "juros_pct", "perda_pct", "roi"],
    ] = np.nan
    print(
        f"  {'faixa':>6}{'n':>7}{'decisão':>10}{'taxa a.m.':>11}{'prazo':>8}"
        f"{'entrada mín.':>14}{'PD publ.':>10}{'PD prec.':>10}{'aceite':>9}{'volume (R$)':>16}"
    )
    for _, l in tabela.iterrows():
        aprova = l["decisao"] == "APROVAR"
        entrada = f"{l['entrada_minima']:.0%}" if aprova and l["entrada_minima"] > 0 else "a do cliente"
        print(
            f"  {int(l['faixa']):>6}{int(l['n']):>7,}{l['decisao']:>10}"
            f"{(f'{l.taxa_am:.2%}' if aprova else '—'):>11}"
            f"{(f'{l.prazo_medio:.0f}m' if aprova else '—'):>8}"
            f"{(entrada if aprova else '—'):>14}"
            f"{l['pd_publicada']:>10.1%}{l['pd_precificada']:>10.1%}"
            f"{(f'{l.aceite:.0%}' if aprova else '—'):>9}"
            f"{(f'{l.volume:,.0f}' if aprova else '—'):>16}"
        )

    _cab("5b. A carteira decomposta: de onde vem cada ponto de ROI")
    aprov = tabela["decisao"] == "APROVAR"
    print(
        f"  {'faixa':>6}{'volume (R$)':>16}{'juros esp.':>14}{'perda esp.':>13}"
        f"{'juros/vol':>11}{'perda/vol':>11}{'ROI':>8}"
    )
    for _, l in tabela.loc[aprov].iterrows():
        print(
            f"  {int(l['faixa']):>6}{l['volume']:>16,.0f}{l['juros']:>14,.0f}{l['perda']:>13,.0f}"
            f"{l['juros_pct']:>11.1%}{l['perda_pct']:>11.1%}{l['roi']:>8.1%}"
        )
    tv, tj, tp = tabela.loc[aprov, ["volume", "juros", "perda"]].sum()
    print(
        f"  {'total':>6}{tv:>16,.0f}{tj:>14,.0f}{tp:>13,.0f}"
        f"{tj / tv:>11.1%}{tp / tv:>11.1%}{central['roi']:>8.1%}"
    )
    print(
        f"{chr(10)}  -> a coluna de ROI é quase plana, e isso é o que significa precificar a{chr(10)}"
        f"     risco: cada faixa paga pelo próprio risco e entrega mais ou menos o mesmo{chr(10)}"
        f"     retorno. Se ela fosse inclinada, alguma faixa estaria subsidiando outra."
    )

    _cab("5c. O que cada alavanca de fato fez")
    ap = oferta["decisao"].to_numpy() == "APROVAR"
    subiu = oferta["pct_entrada_efetiva"].to_numpy() > c["pct_entrada_desejada"].to_numpy()
    igual_desejado = bool(
        (oferta["prazo_meses"].to_numpy() == c["prazo_desejado_meses"].to_numpy()).all()
    )
    ltv_alto = int(((oferta["ltv"].to_numpy() > 0.90) & ap).sum())
    print(
        f"  prazo ofertado igual ao desejado nas 5.000 propostas .... {igual_desejado}{chr(10)}"
        f"  prazo médio da carteira contratada ...................... "
        f"{central['prazo_medio']:.1f} meses{chr(10)}"
        f"  entrada elevada acima da desejada ....................... "
        f"{int((subiu & ap).sum()):,} propostas aprovadas"
    )
    for f in sorted({int(x) for x in oferta.loc[ap, "faixa"]}):
        sel = (oferta["faixa"].to_numpy() == f) & ap
        if oferta.loc[sel, "pct_entrada_minima"].iloc[0] == 0:
            continue
        print(
            f"    faixa {f}: {int((subiu & sel).sum()):,} de {int(sel.sum()):,} "
            f"({(subiu & sel).sum() / sel.sum():.0%}), LTV médio {oferta.loc[sel, 'ltv'].mean():.4f}"
        )
    print(
        f"  contratos aprovados com LTV acima de 90% ................ "
        f"{ltv_alto:,} ({ltv_alto / ap.sum():.1%}){chr(10)}"
        f"{chr(10)}  -> os {ltv_alto} contratos de LTV alto estão todos nas faixas sem exigência de{chr(10)}"
        f"     entrada. É escolha, não descuido: ali a PD é baixa o bastante para o preço{chr(10)}"
        f"     carregar a LGD alta, e exigir entrada custaria volume exatamente onde a{chr(10)}"
        f"     carteira é mais rentável. Com piso de volume mais folgado, a decisão mudaria."
    )

    _cab("5d. Quanto vale a inclinação do preço")
    print(
        f"  {'inclinação':>11}{'ROI':>8}{'inadimpl.':>11}{'volume':>16}"
        f"{'faixas 8-10':>13}{'taxas ofertadas':>19}"
    )
    for incl in (0.0, regra.inclinacao):
        r = replace(regra, inclinacao=incl)
        of = aplicar(r, c, quadro)
        m = simular(of, cen, c)
        ac = probabilidade_aceite(c, of, cen)
        w = np.where(of["decisao"].to_numpy() == "APROVAR", ac, 0.0)
        topo = float(np.sum(w[(of["faixa"] >= 8).to_numpy()]) / np.sum(w))
        aprovadas = of.loc[of["decisao"] == "APROVAR", "taxa_am"]
        print(
            f"  {incl:>11.0%}{m['roi']:>8.2%}{m['inadimplencia']:>11.2%}{m['volume']:>16,.0f}"
            f"{topo:>13.1%}{f'{aprovadas.min():.2%} a {aprovadas.max():.2%}':>19}"
        )
    print(
        f"{chr(10)}  -> a inclinação rende ROI e quase não mexe na inadimplência. Mas repare que a{chr(10)}"
        f"     participação das melhores faixas sobe pouco: a maior parte do ganho vem de{chr(10)}"
        f"     cobrar mais onde o risco é maior, e só uma fração de mudar a composição.{chr(10)}"
        f"     A leitura honesta é 'prêmio de risco mais inclinado', não 'engenharia de{chr(10)}"
        f"     composição' — que soaria mais esperto e descreveria pior o que acontece."
    )

    _cab("6. Teste de estresse: aceite x nível da PD")
    print(f"  {'cenário':<12}{'PD':>6}{'aprov.':>9}{'aceite':>9}{'volume':>15}{'inadimpl.':>11}{'ROI':>9}{'guardrails':>16}")
    estresse = []
    for nome, cenario in CENARIOS.items():
        for mult in ESTRESSE_PD:
            m = simular(oferta, cenario, c, mult_pd=mult)
            falhas = [k for k, v in guardrails(m).items() if not v]
            estresse.append(m)
            print(
                f"  {nome:<12}{f'x{mult:.1f}':>6}{m['aprovacao']:>9.1%}{m['aceite_medio']:>9.1%}"
                f"{m['volume']:>15,.0f}{m['inadimplencia']:>11.2%}{m['roi']:>9.1%}"
                f"{(', '.join(falhas) if falhas else 'todos ok'):>16}"
            )

    print(
        f"{chr(10)}  -> a linha que decidiu a política é a do canto duro — aceite "
        f"{CANTO_DURO[0]} com PD{chr(10)}"
        f"     x{CANTO_DURO[1]:.1f} —, não a do cenário central. Três dos quatro guardrails cortam a{chr(10)}"
        f"     nota pela metade: nenhum ganho de ROI compensa uma nota dividida por dois.{chr(10)}"
        f"     Abaixo dele, com PD x{ESTRESSE_PD[-1]:.1f}, a inadimplência estoura — e isso é o que{chr(10)}"
        f"     há de mais frágil nesta política, porque o nível da PD em mar aberto é{chr(10)}"
        f"     justamente o que a Base A não consegue medir (capítulo 05)."
    )

    _cab("7. Os quatro guardrails: carteira, limite e folga no canto duro")
    f_central = folgas(central)
    f_duro = folgas(duro)
    taxa_max = float(oferta.loc[oferta["decisao"] == "APROVAR", "taxa_am"].max())
    checagens = [
        ("taxa de aprovação", f"{central['aprovacao']:.1%}", f">= {MIN_APROVACAO:.0%}",
         f_central["aprovacao"], f_duro["aprovacao"]),
        ("volume originado", f"R$ {central['volume']:,.0f}", f">= R$ {MIN_VOLUME:,.0f}",
         f_central["volume"], f_duro["volume"]),
        ("inadimplência", f"{central['inadimplencia']:.2%}", f"<= {MAX_INADIMPLENCIA:.0%}",
         f_central["inadimplencia"], f_duro["inadimplencia"]),
    ]
    print(f"  {'guardrail':<20}{'central':>18}{'limite':>20}{'folga central':>15}{'folga dura':>13}")
    for nome, valor, limite, fc, fd in checagens:
        print(f"  {nome:<20}{valor:>18}{limite:>20}{fc:>15.1%}{fd:>13.1%}")
    print(
        f"  {'CET máximo':<20}{f'{taxa_max:.2%} a.m.':>18}{f'<= {MAX_CET_AM:.1%} a.m.':>20}"
        f"{MAX_CET_AM / taxa_max - 1:>15.1%}{'—':>13}"
    )

    print(
        f"{chr(10)}  ROI anualizado projetado: {central['roi']:.1%} no cenário central, "
        f"{duro['roi']:.1%} no canto duro.{chr(10)}"
        f"  O conselho pediu acima de 15%: o cenário central entrega, o canto duro fica{chr(10)}"
        f"  {(0.15 - duro['roi']) * 100:.1f} ponto percentual abaixo. Dito com todas as letras, porque a{chr(10)}"
        f"  distância entre {central['roi']:.1%} e {duro['roi']:.1%} é menor que o erro do modelo de aceite{chr(10)}"
        f"  que produziu os dois."
    )

    resumo = {
        "regra": regra.rotulo(),
        "corte": regra.corte,
        "alvo_roi": regra.alvo_roi,
        "inclinacao": regra.inclinacao,
        "roi_central": central["roi"],
        "roi_canto_duro": duro["roi"],
        "aprovacao": central["aprovacao"],
        "volume_central": central["volume"],
        "volume_canto_duro": duro["volume"],
        "inadimplencia_central": central["inadimplencia"],
        "inadimplencia_canto_duro": duro["inadimplencia"],
        "folga_minima_canto_duro": min(f_duro.values()),
        "aceite_medio": central["aceite_medio"],
        "prazo_medio": central["prazo_medio"],
        "taxa_media": central["taxa_media"],
        "taxa_max": taxa_max,
        "guardrails_no_canto_duro": todos_ok(duro),
    }
    return tabela, resumo


def main(fronteira: bool = False) -> None:
    print("=" * 96)
    print("  POLÍTICA DE CRÉDITO — Base C, 5.000 propostas")
    print("=" * 96)

    c = carregar_base_c()
    quadro = enquadrar(c)
    achados = auditar(c, quadro)

    if fronteira:
        _cab("4b. A grade inteira, e a fronteira entre ROI e folga")
        resultados = buscar(c, quadro, verbose=True)
        robustas = [r for r in resultados if r["ok_duro"]]
        admissiveis = [r for r in robustas if r["folga_min"] >= MARGEM_MINIMA]
        print(
            f"{chr(10)}  {len(resultados)} regras testadas.{chr(10)}"
            f"  {len(robustas)} cumprem os quatro guardrails no canto duro "
            f"(aceite {CANTO_DURO[0]} com PD x{CANTO_DURO[1]:.1f}).{chr(10)}"
            f"  {len(admissiveis)} ainda têm {MARGEM_MINIMA:.0%} de folga em todos eles.{chr(10)}"
        )
        print(f"  {'regra':<56}{'ROI centr.':>12}{'ROI duro':>10}{'folga mín.':>12}{'onde':>16}")
        for r in admissiveis[:8]:
            print(
                f"  {r['regra'].rotulo():<56}{r['roi_central']:>12.1%}"
                f"{r['roi_duro']:>10.1%}{r['folga_min']:>12.1%}{r['folga_de']:>16}"
            )
        print(f"{chr(10)}  e o que se compra abaixo da barra de folga — a tentação:")
        tentacao = sorted(
            [r for r in robustas if r["folga_min"] < MARGEM_MINIMA],
            key=lambda r: r["roi_central"], reverse=True,
        )
        for r in tentacao[:4]:
            print(
                f"  {r['regra'].rotulo():<56}{r['roi_central']:>12.1%}"
                f"{r['roi_duro']:>10.1%}{r['folga_min']:>12.1%}{r['folga_de']:>16}"
            )
        melhor = sorted(resultados, key=lambda r: r["roi_central"], reverse=True)[0]
        print(
            f"{chr(10)}  e o máximo absoluto da grade, ignorando robustez:{chr(10)}"
            f"  {melhor['regra'].rotulo():<56}{melhor['roi_central']:>12.1%}"
            f"{melhor['roi_duro']:>10.1%}{melhor['folga_min']:>12.1%}{melhor['folga_de']:>16}"
        )
        # Probabilidade de indiferença. Se a regra arriscada entrega `r_b` com
        # probabilidade `q` de cumprir o guardrail e nota pela metade se quebrar,
        # ela só bate a segura quando  q·r_b + (1−q)·r_b/2 > r_a,  isto é,
        # q > 2·r_a/r_b − 1.
        r_a, r_b = admissiveis[0]["roi_central"], melhor["roi_central"]
        q = 2 * r_a / r_b - 1
        achados["prob_indiferenca"] = q
        print(
            f"{chr(10)}  -> a diferença entre a regra escolhida e o máximo da grade é de"
            f" {r_b - r_a:+.1%} de ROI.{chr(10)}"
            f"     Vale a troca? Três dos quatro guardrails cortam a nota de política pela{chr(10)}"
            f"     metade. Uma regra que entrega {r_b:.1%} com probabilidade q de passar, e{chr(10)}"
            f"     metade disso se quebrar, só bate os {r_a:.1%} garantidos quando{chr(10)}"
            f"     q·{r_b:.3f} + (1−q)·{r_b / 2:.3f} > {r_a:.3f}, ou seja **q > {q:.0%}**.{chr(10)}"
            f"     Com {melhor['folga_min']:.0%} de folga no canto duro — quer dizer, precisando que o{chr(10)}"
            f"     volume venha {-melhor['folga_min']:.0%} acima do que nosso próprio modelo projeta —,{chr(10)}"
            f"     essa probabilidade não chega perto de {q:.0%}. A regra escolhida é a primeira{chr(10)}"
            f"     da lista de admissíveis.{chr(10)}"
            f"{chr(10)}     (A conta supõe que a nota de política é proporcional ao ROI. Ela é{chr(10)}"
            f"     relativa ao melhor grupo, o que muda a escala e não muda o sinal.)"
        )
        achados["regras_testadas"] = len(resultados)
        achados["regras_robustas"] = len(robustas)
        achados["regras_admissiveis"] = len(admissiveis)
        achados["roi_maximo_da_grade"] = melhor["roi_central"]

    tabela, resumo = relatar(ESCOLHIDA, c, quadro)

    oferta = aplicar(ESCOLHIDA, c, quadro)
    ARTEFATOS.mkdir(exist_ok=True)
    oferta.round(6).to_csv(ARQ_POLITICA, index=False, encoding="utf-8")
    tabela.round(6).to_csv(ARQ_TABELA, index=False, encoding="utf-8")
    registrar_execucao("politica", {"etapa": "src/politica", **achados, **resumo,
                                    "saida": ARQ_POLITICA.name})
    print(
        f"{chr(10)}  oferta por proposta gravada em artefatos/{ARQ_POLITICA.name}{chr(10)}"
        f"  tabela de faixas gravada em artefatos/{ARQ_TABELA.name}"
    )
    print("=" * 96)


if __name__ == "__main__":
    main(fronteira="--fronteira" in sys.argv)
