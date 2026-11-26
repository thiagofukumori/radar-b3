"""Nota de eventos (0–100): regime macro detectado + sentimento das notícias da empresa.

Regime macro vem de duas fontes:
  * sinais quantitativos (preços e Banco Central) — intensidade 1.0
  * manchetes macro classificadas (>= 3 menções na semana) — intensidade 0.5
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import GLOBAIS, INDICE_REFERENCIA
from .setores import ESTATAIS, GRUPO_DO_TICKER, IMPACTOS

NOME = {v: k for k, v in GLOBAIS.items()}  # "dolar" -> "BRL=X"
JANELA_NOTICIAS = 7
MEIA_VIDA_DIAS = 3.0


def _ret21(con, ticker, data_ref):
    s = pd.read_sql("SELECT fechamento FROM precos WHERE ticker=? AND data<=? ORDER BY data DESC LIMIT 22",
                    con, params=(ticker, data_ref))["fechamento"]
    return float(s.iloc[0] / s.iloc[-1] - 1) * 100 if len(s) == 22 else np.nan


def regimes(con, data_ref) -> dict:
    """evento -> (intensidade 0..1, motivo)"""
    ativos = {}

    def marca(ev, inten, motivo):
        if inten > ativos.get(ev, (0, ""))[0]:
            ativos[ev] = (inten, motivo)

    dol = _ret21(con, NOME["dolar"], data_ref)
    if dol > 3: marca("dolar_forte", 1.0, f"dólar +{dol:.1f}% em 21 pregões")
    if dol < -3: marca("dolar_fraco", 1.0, f"dólar {dol:.1f}% em 21 pregões")

    brent = _ret21(con, NOME["brent"], data_ref)
    if brent > 8: marca("petroleo_alta", 1.0, f"Brent +{brent:.1f}%")
    if brent < -8: marca("petroleo_baixa", 1.0, f"Brent {brent:.1f}%")

    ib, sp = _ret21(con, INDICE_REFERENCIA, data_ref), _ret21(con, NOME["sp500"], data_ref)
    if ib - sp < -7:
        marca("risco_fiscal_politico", 1.0, f"Ibovespa {ib:.1f}% vs S&P {sp:.1f}% (estresse local)")

    selic = pd.read_sql("SELECT data, valor FROM macro WHERE serie='selic_meta' AND data<=? ORDER BY data",
                        con, params=(data_ref,))
    if len(selic) > 60:
        antes, agora = selic["valor"].iloc[-61], selic["valor"].iloc[-1]
        if agora > antes: marca("juros_subindo", 1.0, f"Selic {antes}% -> {agora}%")
        if agora < antes: marca("juros_caindo", 1.0, f"Selic {antes}% -> {agora}%")

    ini = (date.fromisoformat(data_ref) - timedelta(days=JANELA_NOTICIAS)).isoformat()
    ev = pd.read_sql("SELECT eventos FROM noticias WHERE ticker IS NULL AND eventos NOT IN ('', 'irrelevante') "
                     "AND substr(data_pub,1,10) BETWEEN ? AND ?", con, params=(ini, data_ref))["eventos"]
    contagem = ev.str.split(",").explode().value_counts()
    for nome, n in contagem.items():
        if n >= 3:
            marca(nome, 0.5, f"{n} manchetes na semana")

    # sinais opostos se anulam
    for a, b in [("juros_subindo", "juros_caindo"), ("dolar_forte", "dolar_fraco"),
                 ("petroleo_alta", "petroleo_baixa"), ("risco_fiscal_politico", "alivio_fiscal_politico"),
                 ("china_estimulo", "china_desaceleracao")]:
        if a in ativos and b in ativos:
            ia, ib_ = ativos[a][0], ativos[b][0]
            if ia == ib_:
                ativos.pop(a), ativos.pop(b)
            else:
                ativos.pop(b if ia > ib_ else a)
    return ativos


def nota_macro(ticker, ativos) -> float:
    grupo = GRUPO_DO_TICKER.get(ticker)
    soma = 0.0
    for ev, (inten, _) in ativos.items():
        imp = IMPACTOS.get(ev, {})
        soma += inten * imp.get(grupo, 0)
        if ticker in ESTATAIS:
            soma += inten * imp.get("_estatal", 0)
    return float(np.clip(50 + 12.5 * soma, 0, 100))


def nota_noticias(con, data_ref) -> pd.DataFrame:
    ini = (date.fromisoformat(data_ref) - timedelta(days=JANELA_NOTICIAS)).isoformat()
    n = pd.read_sql("SELECT ticker, data_pub, sentimento FROM noticias WHERE ticker IS NOT NULL "
                    "AND sentimento IS NOT NULL AND eventos IS NOT 'irrelevante' "
                    "AND substr(data_pub,1,10) BETWEEN ? AND ?", con, params=(ini, data_ref))
    if n.empty:
        return pd.DataFrame(columns=["ticker", "nota_noticias", "n_noticias", "sent_medio"])
    idade = (pd.Timestamp(data_ref) - pd.to_datetime(n["data_pub"])).dt.total_seconds() / 86400
    n["peso"] = 0.5 ** (idade.clip(lower=0) / MEIA_VIDA_DIAS)
    g = n.groupby("ticker").apply(
        lambda d: pd.Series({
            "sent_medio": np.average(d["sentimento"], weights=d["peso"]),
            "n_noticias": len(d),
        }), include_groups=False,
    ).reset_index()
    # poucas notícias -> puxa para neutro
    g["sent_ajust"] = g["sent_medio"] * g["n_noticias"] / (g["n_noticias"] + 3)
    g["nota_noticias"] = 50 + 50 * g["sent_ajust"]
    return g[["ticker", "nota_noticias", "n_noticias", "sent_medio"]]


def fatos_recentes(con, data_ref, dias=7) -> dict:
    ini = (date.fromisoformat(data_ref) - timedelta(days=dias)).isoformat()
    f = pd.read_sql("SELECT ticker, data_entrega, assunto FROM fatos_relevantes "
                    "WHERE categoria='Fato Relevante' AND data_entrega BETWEEN ? AND ?", con, params=(ini, data_ref))
    return f.groupby("ticker").apply(
        lambda d: "; ".join(f"{r.data_entrega[5:]} {str(r.assunto)[:60]}" for r in d.itertuples()),
        include_groups=False,
    ).to_dict()


def nota_eventos(con, tickers, data_ref):
    ativos = regimes(con, data_ref)
    df = pd.DataFrame({"ticker": list(tickers)})
    df["nota_macro"] = df["ticker"].map(lambda t: nota_macro(t, ativos))
    df = df.merge(nota_noticias(con, data_ref), on="ticker", how="left")
    df["nota_eventos"] = np.where(df["nota_noticias"].notna(),
                                  0.5 * df["nota_macro"] + 0.5 * df["nota_noticias"], df["nota_macro"])
    df["fato_relevante"] = df["ticker"].map(fatos_recentes(con, data_ref))
    return df, ativos
