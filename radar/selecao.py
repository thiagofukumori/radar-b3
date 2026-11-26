"""Indicação do dia: aplica filtros de risco ao ranking e explica cada escolha.

É a saída das regras do modelo (configuráveis em config.py), não uma recomendação personalizada.
"""
import math

from .config import (
    ATR_ALTO_PCT, INDICE_REFERENCIA, SELECAO_MOMENTO_MIN, SELECAO_POR_RISCO, SELECAO_RSI_MAX,
)
from .eventos import _ret21
from .setores import GRUPO_DO_TICKER, IMPACTOS

EVENTO_NOME = {
    "juros_subindo": "juros subindo", "juros_caindo": "juros caindo", "dolar_forte": "dólar forte",
    "dolar_fraco": "dólar fraco", "petroleo_alta": "petróleo em alta", "petroleo_baixa": "petróleo em baixa",
    "china_estimulo": "estímulo na China", "china_desaceleracao": "China desacelerando",
    "risco_fiscal_politico": "risco fiscal/político", "alivio_fiscal_politico": "alívio fiscal/político",
    "tensao_geopolitica": "tensão geopolítica", "guerra_comercial": "guerra comercial",
}
REC = {"strong_buy": "compra forte", "buy": "compra", "hold": "neutro", "underperform": "abaixo do mercado",
       "sell": "venda"}


def br(v, d=1, sinal=False):
    s = f"{v:+,.{d}f}" if sinal else f"{v:,.{d}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _ok(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def nivel_risco_mercado(con, data_ref, regimes):
    pontos, motivos = 0.0, []
    for ev, peso in (("risco_fiscal_politico", 2.0), ("tensao_geopolitica", 1.0), ("guerra_comercial", 0.5)):
        if ev in regimes:
            inten = regimes[ev][0]
            pontos += peso * inten
            motivos.append(f"{EVENTO_NOME[ev]} (intensidade {br(inten, 1)})")
    ib = _ret21(con, INDICE_REFERENCIA, data_ref)
    if _ok(ib) and ib < -10:
        pontos += 2; motivos.append(f"Ibovespa {br(ib, 1)}% em 21 pregões")
    elif _ok(ib) and ib < -5:
        pontos += 1; motivos.append(f"Ibovespa {br(ib, 1)}% em 21 pregões")
    nivel = "alto" if pontos >= 3 else "moderado" if pontos >= 1.5 else "baixo"
    return nivel, motivos


def _efeito_regime(ticker, regimes):
    g = GRUPO_DO_TICKER.get(ticker)
    pos, neg = [], []
    for ev, (inten, _) in regimes.items():
        imp = IMPACTOS.get(ev, {}).get(g, 0)
        (pos if imp > 0 else neg if imp < 0 else []).append(EVENTO_NOME.get(ev, ev))
    return pos, neg


def _por_que(r, regimes):
    motivos = []
    if r["nota_momento"] >= 65:
        motivos.append(f"Tendência forte: {br(r['ret21_vs_ibov'], 1, True)} p.p. vs Ibovespa em 21 pregões, acima da média de 21 dias")
    pos, _ = _efeito_regime(r["ticker"], regimes)
    if pos:
        motivos.append("Setor favorecido pelo cenário: " + ", ".join(pos))
    if _ok(r.get("nota_noticias")) and r["nota_noticias"] >= 55:
        motivos.append(f"Notícias da semana positivas ({int(r['n_noticias'])} manchetes)")
    if _ok(r.get("nota_analistas")) and r["nota_analistas"] >= 60:
        rec = REC.get(r.get("recomendacao"), r.get("recomendacao") or "–")
        up = f", potencial de {br(r['upside_pct'], 0, True)}% até o alvo" if _ok(r.get("upside_pct")) else ""
        motivos.append(f"Analistas: {rec} ({int(r['num_analistas'])} casas){up}")
    if _ok(r.get("nota_fundamentos")) and r["nota_fundamentos"] >= 65:
        motivos.append("Fundamentos acima da média do grupo acompanhado")
    return motivos


def _riscos(r, regimes):
    riscos = [f"Oscila em média {br(r['atr_pct'], 1)}% ao dia; stop de referência R$ {br(r['ref_stop_2atr'], 2)} "
              f"({br(-2 * r['atr_pct'], 1)}% do preço atual)"]
    if r["rsi14"] > 65:
        riscos.append(f"RSI {r['rsi14']:.0f}: perto da zona de sobrecompra, pode corrigir")
    _, neg = _efeito_regime(r["ticker"], regimes)
    if neg:
        riscos.append("Parte do cenário pesa contra o setor: " + ", ".join(neg))
    if _ok(r.get("nota_noticias")) and r["nota_noticias"] < 45:
        riscos.append("Notícias da semana negativas")
    if _ok(r.get("nota_fundamentos")) and r["nota_fundamentos"] < 35:
        riscos.append("Fundamentos fracos comparados ao grupo")
    for a in (r.get("alertas") or "").split("; "):
        if a.startswith("FATO RELEVANTE"):
            riscos.append(a.replace("FATO RELEVANTE: ", "Fato relevante recente: "))
    return riscos


def _motivo_exclusao(r, regra, nivel):
    al = r.get("alertas") or ""
    if r["nota"] < regra["nota_min"]: return f"nota abaixo de {regra['nota_min']}"
    if r["nota_momento"] < SELECAO_MOMENTO_MIN or r["acima_mm21_pct"] <= 0: return "sem tendência de alta"
    if r["rsi14"] > SELECAO_RSI_MAX: return f"RSI acima de {SELECAO_RSI_MAX} (esticada)"
    if r["atr_pct"] > ATR_ALTO_PCT: return "volatilidade alta"
    if "inconsistente" in al or "rebaixando" in al: return "alerta dos analistas"
    if not _ok(r.get("nota_analistas")): return "sem consenso de analistas válido"
    if nivel == "alto" and r.get("nota_macro", 50) < 50: return "setor prejudicado pelo cenário de risco alto"
    return None


def selecionar(con, df, regimes):
    data_ref = df["data"].iloc[0]
    nivel, motivos_risco = nivel_risco_mercado(con, data_ref, regimes)
    regra = SELECAO_POR_RISCO[nivel]

    escolhidas, por_setor, barradas = [], {}, []
    for r in df.sort_values("nota", ascending=False).to_dict("records"):
        if len(escolhidas) >= regra["max_acoes"]:
            break
        motivo = _motivo_exclusao(r, regra, nivel)
        g = GRUPO_DO_TICKER.get(r["ticker"], "?")
        if not motivo and por_setor.get(g, 0) >= regra["max_por_setor"]:
            motivo = "limite de ações do mesmo setor"
        if motivo:
            if r["nota"] >= regra["nota_min"]:
                barradas.append({"ticker": r["ticker"], "nota": r["nota"], "motivo": motivo})
            continue
        por_setor[g] = por_setor.get(g, 0) + 1
        escolhidas.append({
            "ticker": r["ticker"], "nota": r["nota"], "posicao": r["posicao"], "preco": r["preco"],
            "stop": r["ref_stop_2atr"], "risco_pct": 2 * r["atr_pct"], "grupo": g,
            "risco": "baixo" if r["atr_pct"] < 2.5 else "médio" if r["atr_pct"] < 4 else "alto",
            "por_que": _por_que(r, regimes), "riscos": _riscos(r, regimes),
        })

    evitar = []
    for r in df.sort_values("nota").head(3).to_dict("records"):
        pior = min(("momento", r["nota_momento"]), ("eventos", r.get("nota_eventos")),
                   ("analistas", r.get("nota_analistas")), ("fundamentos", r.get("nota_fundamentos")),
                   key=lambda x: x[1] if _ok(x[1]) else 999)
        al = [a for a in (r.get("alertas") or "").split("; ") if a]
        evitar.append({"ticker": r["ticker"], "nota": r["nota"],
                       "motivo": f"pior nota em {pior[0]} ({br(pior[1], 0)})" + (f"; {al[0]}" if al else "")})

    if escolhidas:
        resumo = (f"Mercado em risco {nivel}: o modelo seleciona até {regra['max_acoes']} ações com nota ≥ "
                  f"{regra['nota_min']}, tendência de alta e sem alertas graves. "
                  + (f"{len(escolhidas)} passaram hoje." if len(escolhidas) > 1 else "Só 1 passou hoje."))
    else:
        resumo = (f"Mercado em risco {nivel} e nenhuma ação passou em todos os filtros hoje: "
                  "o modelo indica ficar de fora.")
    return {"data": data_ref, "nivel_risco": nivel, "motivos_risco": motivos_risco, "regra": regra,
            "resumo": resumo, "escolhidas": escolhidas, "barradas": barradas[:6], "evitar": evitar}
