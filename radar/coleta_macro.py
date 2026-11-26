"""Séries macro do Banco Central (API pública SGS)."""
from datetime import date, datetime, timedelta

import requests

from .config import DIAS_MACRO, SERIES_BCB

URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"


def coletar_macro(con, dias=DIAS_MACRO):
    fim = date.today()
    ini = fim - timedelta(days=dias)
    params = {
        "formato": "json",
        "dataInicial": ini.strftime("%d/%m/%Y"),
        "dataFinal": fim.strftime("%d/%m/%Y"),
    }

    total, falhas = 0, []
    for codigo, nome in SERIES_BCB.items():
        try:
            r = requests.get(URL.format(codigo=codigo), params=params, timeout=30)
            r.raise_for_status()
            dados = r.json()
        except Exception as e:
            falhas.append(f"{nome} ({type(e).__name__})")
            continue
        linhas = [
            (nome, datetime.strptime(p["data"], "%d/%m/%Y").strftime("%Y-%m-%d"), float(p["valor"]))
            for p in dados if p.get("valor") not in (None, "")
        ]
        con.executemany("INSERT OR REPLACE INTO macro VALUES (?,?,?)", linhas)
        total += len(linhas)
    return total, falhas
