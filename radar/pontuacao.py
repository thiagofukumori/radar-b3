"""Motor de notas (0–100) para curto prazo.

Cada sub-nota usa ranking percentual dentro do universo, então mede *posição relativa*
entre as ações acompanhadas, não um valor absoluto.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import (
    ATR_ALTO_PCT, JANELA_REVISAO_DIAS, LIQUIDEZ_MIN_RS, MIN_ANALISTAS, PESOS,
)
from .eventos import nota_eventos
from .tecnico import indicadores


def _pct(s: pd.Series, maior_melhor=True) -> pd.Series:
    return s.rank(pct=True, ascending=maior_melhor) * 100


def _media_ponderada(df: pd.DataFrame, pesos: dict) -> pd.Series:
    """Média ponderada ignorando NaN (renormaliza pesos por linha)."""
    cols = list(pesos)
    w = pd.DataFrame({c: np.where(df[c].notna(), pesos[c], 0.0) for c in cols}, index=df.index)
    soma = w.sum(axis=1).replace(0, np.nan)
    return (df[cols].fillna(0) * w).sum(axis=1) / soma


def _snapshot(con, tabela, data_ref):
    return pd.read_sql(
        f"""SELECT t.* FROM {tabela} t
            JOIN (SELECT ticker, MAX(data_coleta) d FROM {tabela}
                  WHERE data_coleta <= ? GROUP BY ticker) u
              ON t.ticker = u.ticker AND t.data_coleta = u.d""",
        con, params=(data_ref,),
    )


# ---------------------------------------------------------------- momento
def nota_momento(t: pd.DataFrame) -> pd.Series:
    tendencia = t["mm9_acima_mm21"].astype(int) * 50 + (t["inclinacao_mm21_pct"] > 0).astype(int) * 50
    # RSI ideal ~60 para curto prazo: força sem estar esticado
    rsi = (100 - (t["rsi14"] - 60).abs() * 2.5).clip(0, 100)
    partes = pd.DataFrame({
        "r21": _pct(t["ret21_vs_ibov"]),
        "r63": _pct(t["ret63_vs_ibov"]),
        "r5": _pct(t["ret5_vs_ibov"]),
        "tend": tendencia,
        "rsi": rsi,
        "vol": _pct(t["volume_relativo"]),
    })
    return _media_ponderada(partes, {"r21": .30, "r63": .20, "r5": .10, "tend": .20, "rsi": .10, "vol": .10})


# ---------------------------------------------------------------- analistas
def _revisoes(con, data_ref) -> pd.DataFrame:
    d = date.fromisoformat(data_ref)
    ini = (d - timedelta(days=JANELA_REVISAO_DIAS[1])).isoformat()
    fim = (d - timedelta(days=JANELA_REVISAO_DIAS[0])).isoformat()
    antigo = pd.read_sql(
        """SELECT t.ticker, t.preco_alvo_medio alvo_ant, t.nota_media nota_ant
           FROM consenso_analistas t
           JOIN (SELECT ticker, MIN(data_coleta) d FROM consenso_analistas
                 WHERE data_coleta BETWEEN ? AND ? GROUP BY ticker) u
             ON t.ticker = u.ticker AND t.data_coleta = u.d""",
        con, params=(ini, fim),
    )
    return antigo


def nota_analistas(a: pd.DataFrame, antigo: pd.DataFrame):
    a = a.merge(antigo, on="ticker", how="left")
    alertas = pd.Series("", index=a.index)

    venda = a["recomendacao"].isin(["sell", "underperform", "strong_sell"])
    inconsistente = (venda & (a["upside_pct"] > 30)) | (a["upside_pct"] > 120) | (a["upside_pct"] < -50)
    alertas[inconsistente] += "consenso inconsistente (alvo provavelmente desatualizado); "
    upside = a["upside_pct"].where(~inconsistente)

    a["delta_alvo_pct"] = (a["preco_alvo_medio"] / a["alvo_ant"] - 1) * 100
    a["delta_nota"] = a["nota_ant"] - a["nota_media"]  # >0 = melhorou (escala 1=compra ... 5=venda)
    alertas[a["delta_nota"] <= -0.3] += "analistas rebaixando; "

    partes = pd.DataFrame({
        "nivel": ((5 - a["nota_media"]) / 4 * 100).clip(0, 100),
        "upside": _pct(upside),
        "rev_alvo": _pct(a["delta_alvo_pct"]),
        "rev_nota": _pct(a["delta_nota"]),
    })
    nota = _media_ponderada(partes, {"nivel": .30, "upside": .25, "rev_alvo": .25, "rev_nota": .20})
    nota[a["num_analistas"].fillna(0) < MIN_ANALISTAS] = np.nan
    return a.assign(nota_analistas=nota, alertas_analistas=alertas)


# ---------------------------------------------------------------- fundamentos
def nota_fundamentos(f: pd.DataFrame) -> pd.Series:
    pl_valido = f["pl"].where(f["pl"] > 0)
    partes = pd.DataFrame({
        "roe": _pct(f["roe"]),
        "margem": _pct(f["margem_liquida"]),
        "pl": _pct(pl_valido, maior_melhor=False).fillna(0),  # prejuízo -> 0
        "divida": _pct(f["divida_patrimonio"], maior_melhor=False),
    })
    return _media_ponderada(partes, {"roe": .30, "margem": .20, "pl": .30, "divida": .20})


# ---------------------------------------------------------------- composição
def gerar_ranking(con, data_ref=None) -> pd.DataFrame:
    data_ref = data_ref or date.today().isoformat()
    t = indicadores(con, data_ref)
    if t.empty:
        raise RuntimeError("Sem preços suficientes. Rode coletar.py primeiro.")

    excluidas = t[t["liquidez_media_rs"] < LIQUIDEZ_MIN_RS]["ticker"].tolist()
    t = t[t["liquidez_media_rs"] >= LIQUIDEZ_MIN_RS].reset_index(drop=True)
    t["nota_momento"] = nota_momento(t)

    a = nota_analistas(_snapshot(con, "consenso_analistas", data_ref), _revisoes(con, data_ref))
    f = _snapshot(con, "fundamentos", data_ref)
    if not f.empty:
        f["nota_fundamentos"] = nota_fundamentos(f)
    else:
        f = pd.DataFrame(columns=["ticker", "nota_fundamentos"])

    df = (t.merge(a[["ticker", "setor", "recomendacao", "num_analistas", "preco_alvo_medio", "upside_pct",
                     "delta_alvo_pct", "nota_analistas", "alertas_analistas"]], on="ticker", how="left")
           .merge(f[["ticker", "nota_fundamentos", "pl", "roe"]], on="ticker", how="left"))

    ev, ativos = nota_eventos(con, df["ticker"], data_ref)
    df = df.merge(ev, on="ticker", how="left")
    df["nota"] = _media_ponderada(
        df.rename(columns={"nota_momento": "momento", "nota_eventos": "eventos",
                           "nota_analistas": "analistas", "nota_fundamentos": "fundamentos"}),
        PESOS,
    )

    alertas = df["alertas_analistas"].fillna("")
    alertas[df["rsi14"] > 75] += "RSI sobrecomprado; "
    alertas[df["rsi14"] < 30] += "RSI sobrevendido; "
    alertas[df["atr_pct"] > ATR_ALTO_PCT] += "volatilidade alta; "
    alertas[df["nota_analistas"].isna()] += "sem consenso válido; "
    alertas[df["fato_relevante"].notna()] += "FATO RELEVANTE: " + df["fato_relevante"].fillna("") + "; "
    df["alertas"] = alertas.str.rstrip("; ")
    df["ref_stop_2atr"] = df["preco"] * (1 - 2 * df["atr_pct"] / 100)

    df = df.sort_values("nota", ascending=False).reset_index(drop=True)
    df.insert(0, "posicao", df.index + 1)
    df.insert(1, "data", data_ref)
    df.attrs["excluidas_liquidez"] = excluidas
    df.attrs["regimes"] = ativos
    return df.drop(columns=["alertas_analistas", "fato_relevante"])
