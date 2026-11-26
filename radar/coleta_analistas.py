"""Snapshot diário do consenso de analistas (Yahoo Finance agrega casas como BTG, XP, Itaú BBA etc.).

Coletar todo dia é o que permite medir *revisões* (mudança de recomendação/preço-alvo),
que no curto prazo carregam mais informação que o nível do consenso.
"""
import time
from datetime import date

import yfinance as yf

from .config import PAUSA_YAHOO_S, TICKERS

FONTE = "yahoo"


def coletar_consenso(con, tickers=None):
    hoje = date.today().isoformat()
    linhas, fund, falhas = [], [], []

    for ticker in tickers or TICKERS:
        try:
            info = yf.Ticker(f"{ticker}.SA").info or {}
        except Exception as e:  # rede, bloqueio temporário, ticker inexistente
            falhas.append(f"{ticker} ({type(e).__name__})")
            time.sleep(PAUSA_YAHOO_S)
            continue

        preco = info.get("currentPrice") or info.get("regularMarketPrice")
        alvo = info.get("targetMeanPrice")
        n = info.get("numberOfAnalystOpinions")
        if not preco:
            falhas.append(f"{ticker} (sem dados)")
        else:
            upside = (alvo / preco - 1) * 100 if alvo else None
            linhas.append((
                ticker, hoje, info.get("recommendationKey"), info.get("recommendationMean"),
                n, alvo, info.get("targetHighPrice"), info.get("targetLowPrice"),
                preco, upside, info.get("sector"), info.get("industry"), FONTE,
            ))
            # Fundamentos vêm na mesma resposta: nenhuma requisição extra
            fund.append((
                ticker, hoje, info.get("trailingPE"), info.get("priceToBook"),
                info.get("returnOnEquity"), info.get("debtToEquity"),
                info.get("profitMargins"), info.get("dividendYield"),
                info.get("earningsGrowth"), info.get("averageVolume"),
            ))
        time.sleep(PAUSA_YAHOO_S)

    con.executemany(
        "INSERT OR REPLACE INTO consenso_analistas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", linhas
    )
    con.executemany(
        "INSERT OR REPLACE INTO fundamentos VALUES (?,?,?,?,?,?,?,?,?,?)", fund
    )
    return len(linhas), falhas
