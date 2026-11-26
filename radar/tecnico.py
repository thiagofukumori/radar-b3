"""Indicadores técnicos de curto prazo calculados a partir da tabela `precos`.

Todos os cálculos usam só dados até `data_ref`, para que o mesmo código sirva ao backtest.
"""
import numpy as np
import pandas as pd

from .config import INDICE_REFERENCIA, NAO_ACOES


def carregar_precos(con, data_ref=None) -> pd.DataFrame:
    sql = "SELECT * FROM precos" + (" WHERE data <= ?" if data_ref else "")
    df = pd.read_sql(sql, con, params=(data_ref,) if data_ref else None, parse_dates=["data"])
    return df.sort_values(["ticker", "data"])


def _rsi(close: pd.Series, n=14) -> float:
    delta = close.diff()
    ganho = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    perda = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = ganho.iloc[-1] / perda.iloc[-1] if perda.iloc[-1] else np.inf
    return float(100 - 100 / (1 + rs))


def _atr_pct(d: pd.DataFrame, n=14) -> float:
    prev = d["fechamento"].shift()
    tr = pd.concat([
        d["maxima"] - d["minima"],
        (d["maxima"] - prev).abs(),
        (d["minima"] - prev).abs(),
    ], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1] / d["fechamento"].iloc[-1] * 100)


def _ret(close: pd.Series, n: int) -> float:
    return float(close.iloc[-1] / close.iloc[-1 - n] - 1) * 100 if len(close) > n else np.nan


def indicadores(con, data_ref=None) -> pd.DataFrame:
    precos = carregar_precos(con, data_ref)
    ibov = precos[precos.ticker == INDICE_REFERENCIA].set_index("data")["fechamento"]
    ib5, ib21, ib63 = (_ret(ibov, n) for n in (5, 21, 63))

    linhas = []
    for ticker, d in precos[~precos.ticker.isin(NAO_ACOES)].groupby("ticker"):
        if len(d) < 70:
            continue
        c = d["fechamento"]
        mm9, mm21 = c.rolling(9).mean(), c.rolling(21).mean()
        vol_fin = (c * d["volume"])
        linhas.append({
            "ticker": ticker,
            "data_preco": d["data"].iloc[-1].strftime("%Y-%m-%d"),
            "preco": float(c.iloc[-1]),
            "ret5_vs_ibov": _ret(c, 5) - ib5,
            "ret21_vs_ibov": _ret(c, 21) - ib21,
            "ret63_vs_ibov": _ret(c, 63) - ib63,
            "rsi14": _rsi(c),
            "acima_mm21_pct": float(c.iloc[-1] / mm21.iloc[-1] - 1) * 100,
            "mm9_acima_mm21": bool(mm9.iloc[-1] > mm21.iloc[-1]),
            "inclinacao_mm21_pct": float(mm21.iloc[-1] / mm21.iloc[-6] - 1) * 100,
            "volume_relativo": float(d["volume"].tail(5).mean() / d["volume"].tail(21).mean()),
            "atr_pct": _atr_pct(d),
            "liquidez_media_rs": float(vol_fin.tail(21).mean()),
        })
    return pd.DataFrame(linhas)
