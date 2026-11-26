"""Gera o painel HTML (arquivo único, abre offline no navegador) a partir do banco e do ranking."""
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import EMPRESAS, GLOBAIS, INDICE_REFERENCIA, PESOS, RAIZ
from .setores import GRUPO_DO_TICKER, GRUPOS, IMPACTOS

TEMPLATE = Path(__file__).with_name("painel_template.html")
NOME_GLOBAL = {v: k for k, v in GLOBAIS.items()}
DIAS_GRAFICO = 130


def _limpo(v):
    if isinstance(v, (float, np.floating)):
        return None if math.isnan(v) or math.isinf(v) else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _registros(df: pd.DataFrame):
    return [{k: _limpo(v) for k, v in r.items()} for r in df.to_dict("records")]


def _serie(con, ticker, data_ref, dias=DIAS_GRAFICO):
    s = pd.read_sql("SELECT data, fechamento FROM precos WHERE ticker=? AND data<=? ORDER BY data DESC LIMIT ?",
                    con, params=(ticker, data_ref, dias))
    return s.iloc[::-1]


def _kpi(con, ticker, data_ref, nome, formato):
    s = _serie(con, ticker, data_ref, 64)["fechamento"]
    if s.empty:
        return None
    var = lambda n: float(s.iloc[-1] / s.iloc[-1 - n] - 1) * 100 if len(s) > n else None
    return {"nome": nome, "valor": float(s.iloc[-1]), "var1": var(1), "var21": var(21),
            "formato": formato, "serie": [round(float(x), 4) for x in s]}


def _macro(con, serie, data_ref):
    r = con.execute("SELECT valor, data FROM macro WHERE serie=? AND data<=? ORDER BY data DESC LIMIT 1",
                    (serie, data_ref)).fetchone()
    return r


def montar_dados(con, df: pd.DataFrame) -> dict:
    data_ref = df["data"].iloc[0]
    ini7 = (date.fromisoformat(data_ref) - timedelta(days=7)).isoformat()
    ini30 = (date.fromisoformat(data_ref) - timedelta(days=30)).isoformat()

    kpis = [k for k in [
        _kpi(con, INDICE_REFERENCIA, data_ref, "Ibovespa", "pts"),
        _kpi(con, NOME_GLOBAL["dolar"], data_ref, "Dólar", "brl"),
        _kpi(con, NOME_GLOBAL["brent"], data_ref, "Petróleo Brent", "usd"),
        _kpi(con, NOME_GLOBAL["sp500"], data_ref, "S&P 500", "pts"),
    ] if k]
    for serie, nome in [("selic_meta", "Selic"), ("ipca_12m", "IPCA 12 meses")]:
        r = _macro(con, serie, data_ref)
        if r:
            kpis.append({"nome": nome, "valor": r[0], "formato": "pct", "ref": r[1]})

    regimes = df.attrs.get("regimes", {})
    impacto_grupo = []
    for g in GRUPOS:
        soma = sum(inten * IMPACTOS.get(ev, {}).get(g, 0) for ev, (inten, _) in regimes.items())
        impacto_grupo.append({"grupo": g, "impacto": round(soma, 2)})

    ranking = df.copy()
    ranking["grupo"] = ranking["ticker"].map(GRUPO_DO_TICKER)
    ranking["empresa"] = ranking["ticker"].map(lambda t: EMPRESAS.get(t, ("",))[0])

    detalhes = {}
    for t in ranking["ticker"]:
        s = _serie(con, t, data_ref)
        noticias = pd.read_sql(
            "SELECT data_pub, fonte, titulo, sentimento, link FROM noticias WHERE ticker=? "
            "AND eventos IS NOT 'irrelevante' AND substr(data_pub,1,10) >= ? ORDER BY data_pub DESC LIMIT 15",
            con, params=(t, ini7))
        fatos = pd.read_sql(
            "SELECT data_entrega, categoria, assunto, link FROM fatos_relevantes WHERE ticker=? "
            "AND data_entrega >= ? ORDER BY data_entrega DESC LIMIT 8", con, params=(t, ini30))
        detalhes[t] = {
            "datas": s["data"].tolist(),
            "precos": [round(float(x), 2) for x in s["fechamento"]],
            "noticias": _registros(noticias),
            "fatos": _registros(fatos),
        }

    macro_news = pd.read_sql(
        "SELECT data_pub, fonte, titulo, sentimento, eventos, link FROM noticias WHERE ticker IS NULL "
        "AND eventos NOT IN ('', 'irrelevante') AND substr(data_pub,1,10) >= ? ORDER BY data_pub DESC LIMIT 25",
        con, params=(ini7,))
    classificador = con.execute(
        "SELECT classificador, COUNT(*) FROM noticias GROUP BY classificador ORDER BY 2 DESC LIMIT 1").fetchone()

    return {
        "data": data_ref,
        "gerado_em": pd.Timestamp.now().strftime("%d/%m/%Y %H:%M"),
        "pesos": PESOS,
        "classificador": classificador[0] if classificador else None,
        "kpis": kpis,
        "regimes": [{"evento": e, "intensidade": i, "motivo": m} for e, (i, m) in
                    sorted(regimes.items(), key=lambda x: -x[1][0])],
        "impacto_grupo": impacto_grupo,
        "ranking": _registros(ranking),
        "detalhes": detalhes,
        "noticias_macro": _registros(macro_news),
        "excluidas": df.attrs.get("excluidas_liquidez", []),
    }


def gerar_painel(con, df: pd.DataFrame, selecao: dict | None = None) -> Path:
    dados = montar_dados(con, df)
    dados["selecao"] = json.loads(json.dumps(selecao or {}, default=_limpo))
    js = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DADOS__*/null", js)
    saida = RAIZ / "dados" / "painel.html"
    saida.write_text(html, encoding="utf-8")
    return saida
