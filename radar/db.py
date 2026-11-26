"""Armazenamento em SQLite. Toda informação é datada para permitir backtest sem look-ahead."""
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS precos (
    ticker TEXT NOT NULL,
    data   TEXT NOT NULL,
    abertura REAL, maxima REAL, minima REAL, fechamento REAL, volume REAL,
    PRIMARY KEY (ticker, data)
);

-- Snapshot do consenso de analistas na data da coleta (o histórico vem de coletar todo dia)
CREATE TABLE IF NOT EXISTS consenso_analistas (
    ticker TEXT NOT NULL,
    data_coleta TEXT NOT NULL,
    recomendacao TEXT,          -- strong_buy, buy, hold, underperform, sell
    nota_media REAL,            -- 1 = compra forte ... 5 = venda
    num_analistas INTEGER,
    preco_alvo_medio REAL, preco_alvo_max REAL, preco_alvo_min REAL,
    preco_atual REAL,
    upside_pct REAL,
    setor TEXT, industria TEXT,
    fonte TEXT,
    PRIMARY KEY (ticker, data_coleta, fonte)
);

CREATE TABLE IF NOT EXISTS fundamentos (
    ticker TEXT NOT NULL,
    data_coleta TEXT NOT NULL,
    pl REAL, pvp REAL, roe REAL, divida_patrimonio REAL,
    margem_liquida REAL, dividend_yield REAL, crescimento_lucro REAL,
    volume_medio REAL,
    PRIMARY KEY (ticker, data_coleta)
);

-- Ranking gerado em cada data (base para backtest sem look-ahead)
CREATE TABLE IF NOT EXISTS ranking (
    data TEXT NOT NULL,
    ticker TEXT NOT NULL,
    posicao INTEGER,
    nota REAL, nota_momento REAL, nota_analistas REAL, nota_fundamentos REAL,
    preco REAL, alertas TEXT,
    PRIMARY KEY (data, ticker)
);

-- Indicação do dia (para medir depois se as escolhas funcionaram)
CREATE TABLE IF NOT EXISTS selecao (
    data TEXT NOT NULL,
    ticker TEXT NOT NULL,
    ordem INTEGER, nota REAL, preco REAL, stop REAL, nivel_risco TEXT,
    PRIMARY KEY (data, ticker)
);

CREATE TABLE IF NOT EXISTS noticias (
    id TEXT PRIMARY KEY,            -- hash do link
    ticker TEXT,                    -- NULL = notícia macro
    consulta TEXT, titulo TEXT, fonte TEXT, link TEXT,
    data_pub TEXT, data_coleta TEXT,
    sentimento REAL,                -- -1 (muito negativo) a +1 (muito positivo); NULL = não classificada
    eventos TEXT,                   -- categorias de evento separadas por vírgula
    classificador TEXT
);

CREATE TABLE IF NOT EXISTS fatos_relevantes (
    ticker TEXT NOT NULL,
    data_entrega TEXT NOT NULL,
    categoria TEXT, assunto TEXT, link TEXT,
    PRIMARY KEY (ticker, data_entrega, assunto)
);

CREATE TABLE IF NOT EXISTS macro (
    serie TEXT NOT NULL,
    data  TEXT NOT NULL,
    valor REAL,
    PRIMARY KEY (serie, data)
);

CREATE TABLE IF NOT EXISTS log_coleta (
    momento TEXT NOT NULL,
    etapa TEXT NOT NULL,
    ok INTEGER, falhas INTEGER, detalhe TEXT
);
"""


@contextmanager
def conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()
