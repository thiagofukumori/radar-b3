"""Fatos relevantes e comunicados ao mercado — dados abertos oficiais da CVM (IPE)."""
import io
import unicodedata
import zipfile
from datetime import date, timedelta

import pandas as pd
import requests

from .config import EMPRESAS

URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip"
CATEGORIAS = {"Fato Relevante", "Comunicado ao Mercado"}
DIAS = 30


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.upper()


def _baixar(ano: int) -> pd.DataFrame:
    r = requests.get(URL.format(ano=ano), timeout=180)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    return pd.read_csv(z.open(z.namelist()[0]), sep=";", encoding="latin-1", dtype=str)


def mapear_empresas(df: pd.DataFrame) -> dict:
    """ticker -> conjunto de nomes CVM que começam pelo trecho configurado."""
    nomes = pd.Series(df["Nome_Companhia"].dropna().unique())
    norm = nomes.map(_norm)
    return {t: set(nomes[norm.str.startswith(_norm(frag))]) for t, (_, frag) in EMPRESAS.items()}


def coletar_fatos(con, dias=DIAS):
    hoje = date.today()
    df = _baixar(hoje.year)
    if (hoje - timedelta(days=dias)).year < hoje.year:
        df = pd.concat([_baixar(hoje.year - 1), df])

    mapa = mapear_empresas(df)  # no arquivo inteiro: empresa sem documento recente não é "ambígua"
    df = df[df["Categoria"].isin(CATEGORIAS)]
    df = df[df["Data_Entrega"] >= (hoje - timedelta(days=dias)).isoformat()]

    linhas = []
    for ticker, nomes in mapa.items():
        sub = df[df["Nome_Companhia"].isin(nomes)]
        for _, r in sub.iterrows():
            linhas.append((ticker, r["Data_Entrega"], r["Categoria"], r["Assunto"], r["Link_Download"]))
    sem_nome = [t for t, n in mapa.items() if len(n) != 1]  # trecho do nome não achou exatamente 1 empresa

    con.executemany("INSERT OR IGNORE INTO fatos_relevantes VALUES (?,?,?,?,?)", linhas)
    return len(linhas), sem_nome
