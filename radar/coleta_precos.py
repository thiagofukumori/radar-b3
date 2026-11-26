"""Coleta de preços diários (OHLCV ajustados) da B3 via Yahoo Finance."""
import pandas as pd
import yfinance as yf

from .config import NAO_ACOES, PERIODO_PRECOS, TICKERS


def _simbolo(ticker: str) -> str:
    return ticker if ticker in NAO_ACOES else f"{ticker}.SA"


def coletar_precos(con, tickers=None, periodo=PERIODO_PRECOS):
    tickers = list(tickers or TICKERS) + sorted(NAO_ACOES)
    simbolos = {_simbolo(t): t for t in tickers}

    df = yf.download(
        list(simbolos), period=periodo, interval="1d",
        auto_adjust=True, group_by="ticker", progress=False, threads=True,
    )

    linhas, falhas = [], []
    for simb, ticker in simbolos.items():
        try:
            d = df[simb].dropna(subset=["Close"])
        except KeyError:
            d = pd.DataFrame()
        if d.empty:
            falhas.append(ticker)
            continue
        for data, r in d.iterrows():
            linhas.append((
                ticker, data.strftime("%Y-%m-%d"),
                float(r["Open"]), float(r["High"]), float(r["Low"]),
                float(r["Close"]), float(r["Volume"]),
            ))

    con.executemany(
        "INSERT OR REPLACE INTO precos VALUES (?,?,?,?,?,?,?)", linhas
    )
    return len(simbolos) - len(falhas), falhas, len(linhas)
