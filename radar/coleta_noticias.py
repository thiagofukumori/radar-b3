"""Manchetes recentes via RSS do Google News (pt-BR), por empresa e por tema macro.

Uso pessoal e de baixo volume: ~50 requisições por execução, com pausa entre elas.
"""
import hashlib
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from .config import BUSCAS_MACRO, DIAS_NOTICIAS, EMPRESAS, PAUSA_NOTICIAS_S

URL = "https://news.google.com/rss/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (radar-b3 pessoal)"}


def _buscar(consulta: str, dias: int):
    params = {"q": f"{consulta} when:{dias}d", "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
    for espera in (0, 10, 30):  # limite de requisições do Google: espera e tenta de novo
        time.sleep(espera)
        r = requests.get(URL, params=params, headers=HEADERS, timeout=30)
        if r.status_code not in (429, 503):
            break
    r.raise_for_status()
    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    for item in ET.fromstring(r.content).iter("item"):
        try:
            pub = parsedate_to_datetime(item.findtext("pubDate"))
        except (TypeError, ValueError):
            continue
        if pub < limite:
            continue
        titulo = item.findtext("title") or ""
        fonte = item.findtext("source") or ""
        # O Google acrescenta " - Fonte" ao título
        if fonte and titulo.endswith(f" - {fonte}"):
            titulo = titulo[: -len(fonte) - 3]
        link = item.findtext("link") or ""
        yield titulo.strip(), fonte, link, pub.strftime("%Y-%m-%d %H:%M")


def coletar_noticias(con, dias=DIAS_NOTICIAS):
    hoje = date.today().isoformat()
    # O código da ação (ex.: VALE3) é o filtro mais preciso e com mais resultados em testes
    consultas = [(t, t) for t in EMPRESAS]
    consultas += [(None, b) for b in BUSCAS_MACRO]

    novas, falhas = 0, []
    for ticker, consulta in consultas:
        try:
            itens = list(_buscar(consulta, dias))
        except Exception as e:
            falhas.append(f"{ticker or consulta} ({type(e).__name__})")
            time.sleep(PAUSA_NOTICIAS_S)
            continue
        for titulo, fonte, link, pub in itens[:40]:
            nid = hashlib.sha1(f"{ticker}|{link}".encode()).hexdigest()
            cur = con.execute(
                "INSERT OR IGNORE INTO noticias (id,ticker,consulta,titulo,fonte,link,data_pub,data_coleta)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (nid, ticker, consulta, titulo, fonte, link, pub, hoje),
            )
            novas += cur.rowcount
        time.sleep(PAUSA_NOTICIAS_S)
    return novas, falhas
