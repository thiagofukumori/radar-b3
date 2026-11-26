"""Gera o ranking de curto prazo. Uso:  .venv\\Scripts\\python.exe ranking.py [AAAA-MM-DD]"""
import sys

import pandas as pd

from radar.config import PESOS, RAIZ, TOP_N
from radar.db import conectar
from radar.painel import gerar_painel
from radar.pontuacao import gerar_ranking
from radar.selecao import selecionar

COLS_TELA = ["posicao", "ticker", "nota", "nota_momento", "nota_eventos", "nota_analistas",
             "nota_fundamentos", "preco", "ret21_vs_ibov", "rsi14", "n_noticias", "ref_stop_2atr", "alertas"]


def main():
    data_ref = sys.argv[1] if len(sys.argv) > 1 else None
    with conectar() as con:
        df = gerar_ranking(con, data_ref)
        data = df["data"].iloc[0]

        con.execute("DELETE FROM ranking WHERE data = ?", (data,))
        con.executemany(
            "INSERT INTO ranking VALUES (?,?,?,?,?,?,?,?,?)",
            df[["data", "ticker", "posicao", "nota", "nota_momento", "nota_analistas",
                "nota_fundamentos", "preco", "alertas"]].astype(object).where(df.notna(), None).values.tolist(),
        )

        sel = selecionar(con, df, df.attrs["regimes"])
        con.execute("DELETE FROM selecao WHERE data = ?", (data,))
        con.executemany("INSERT INTO selecao VALUES (?,?,?,?,?,?,?)", [
            (data, e["ticker"], i + 1, e["nota"], e["preco"], e["stop"], sel["nivel_risco"])
            for i, e in enumerate(sel["escolhidas"])])

        painel = gerar_painel(con, df, sel)

    saida = RAIZ / "dados" / f"ranking_{data}.csv"
    df.round(2).to_csv(saida, index=False, sep=";", decimal=",", encoding="utf-8-sig")

    print(f"Ranking curto prazo B3 — {data}  pesos {PESOS}")
    print("Regime macro detectado:")
    for ev, (inten, motivo) in sorted(df.attrs["regimes"].items(), key=lambda x: -x[1][0]):
        print(f"  - {ev:<24} intensidade {inten:.1f}  ({motivo})")
    if not df.attrs["regimes"]:
        print("  (nenhum)")
    if df.attrs.get("excluidas_liquidez"):
        print("Excluídas por liquidez:", ", ".join(df.attrs["excluidas_liquidez"]))
    with pd.option_context("display.width", 200, "display.max_colwidth", 60):
        print(df[COLS_TELA].head(TOP_N).round(1).to_string(index=False))
    print(f"\n=== INDICAÇÃO DO DIA (modelo) — risco do mercado: {sel['nivel_risco'].upper()} ===")
    if sel["motivos_risco"]:
        print("Por quê:", "; ".join(sel["motivos_risco"]))
    print(sel["resumo"])
    for i, e in enumerate(sel["escolhidas"], 1):
        print(f"\n {i}. {e['ticker']}  nota {e['nota']:.1f}  preço R$ {e['preco']:.2f}  "
              f"stop ref. R$ {e['stop']:.2f} (-{e['risco_pct']:.1f}%)  risco {e['risco']}")
        for m in e["por_que"]:
            print(f"    + {m}")
        for m in e["riscos"]:
            print(f"    ! {m}")
    if sel["barradas"]:
        print("\nBarradas pelos filtros de risco:", ", ".join(f"{b['ticker']} ({b['motivo']})" for b in sel["barradas"]))
    print("Evitar:", ", ".join(f"{e['ticker']} ({e['motivo']})" for e in sel["evitar"]))

    print(f"\nCSV completo: {saida}")
    print(f"Painel: {painel}")
    print("Ferramenta de apoio — não é recomendação de investimento.")


if __name__ == "__main__":
    main()
