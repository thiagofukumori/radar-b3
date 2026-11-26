"""Grupos setoriais e o mapa de impacto evento -> grupo (escala -2 a +2).

São regras de bolso da análise macro; ajuste conforme sua leitura e valide no backtest.
"""

GRUPOS = {
    "commodity_exportadora": ["VALE3", "SUZB3", "KLBN11", "GGBR4", "CSNA3", "USIM5"],
    "petroleo": ["PETR4", "PRIO3"],
    "industrial_exportadora": ["WEGE3", "EMBJ3"],
    "banco": ["ITUB4", "BBDC4", "BBAS3", "SANB11", "BPAC11", "ITSA4"],
    "seguradora": ["BBSE3", "CXSE3"],
    "bolsa": ["B3SA3"],
    "varejo": ["LREN3", "MGLU3", "AZZA3", "ASAI3", "RADL3"],
    "construcao": ["CYRE3", "MRVE3"],
    "locacao": ["RENT3"],
    "utilidade": ["EQTL3", "SBSP3", "CMIG4"],
    "telecom": ["TIMS3", "VIVT3"],
    "saude": ["HAPV3", "RDOR3"],
    "consumo_basico": ["ABEV3"],
    "combustivel_distrib": ["VBBR3", "UGPA3", "CSAN3"],
    "logistica": ["RAIL3"],
    "tecnologia": ["TOTS3"],
}
ESTATAIS = {"PETR4", "BBAS3", "CMIG4"}  # sensíveis a risco político

GRUPO_DO_TICKER = {t: g for g, ts in GRUPOS.items() for t in ts}

IMPACTOS = {
    "juros_subindo": {"banco": 1, "seguradora": 2, "bolsa": -1, "varejo": -2, "construcao": -2,
                      "locacao": -1, "utilidade": -1, "saude": -1, "tecnologia": -1},
    "juros_caindo": {"seguradora": -1, "bolsa": 1, "varejo": 2, "construcao": 2, "locacao": 1,
                     "utilidade": 1, "saude": 1, "tecnologia": 1},
    "dolar_forte": {"commodity_exportadora": 2, "industrial_exportadora": 2, "petroleo": 1,
                    "varejo": -1, "combustivel_distrib": -1, "consumo_basico": -1, "locacao": -1},
    "dolar_fraco": {"commodity_exportadora": -1, "industrial_exportadora": -1, "varejo": 1,
                    "combustivel_distrib": 1, "locacao": 1},
    "petroleo_alta": {"petroleo": 2, "combustivel_distrib": -1, "logistica": -1},
    "petroleo_baixa": {"petroleo": -2, "combustivel_distrib": 1, "logistica": 1},
    "china_estimulo": {"commodity_exportadora": 2},
    "china_desaceleracao": {"commodity_exportadora": -2},
    "risco_fiscal_politico": {"commodity_exportadora": 1, "industrial_exportadora": 1, "banco": -1,
                              "bolsa": -1, "varejo": -2, "construcao": -2, "locacao": -2, "saude": -1,
                              "_estatal": -2},
    "alivio_fiscal_politico": {"banco": 1, "bolsa": 1, "varejo": 2, "construcao": 2, "locacao": 1,
                               "_estatal": 1},
    "tensao_geopolitica": {"petroleo": 1, "bolsa": -1, "varejo": -1},
    "guerra_comercial": {"commodity_exportadora": -1, "industrial_exportadora": -1},
}
