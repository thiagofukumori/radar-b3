"""Configuração do radar de ações B3 (curto prazo)."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "dados" / "radar.db"

# Universo inicial: ações líquidas do Ibovespa. Ajuste à vontade.
# Tickers inválidos/renomeados são reportados na coleta e podem ser removidos.
TICKERS = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3", "B3SA3", "ABEV3", "WEGE3",
    "RENT3", "SUZB3", "ITSA4", "PRIO3", "RADL3", "EQTL3", "GGBR4", "RDOR3",
    "BPAC11", "VBBR3", "UGPA3", "CSAN3", "LREN3", "MGLU3", "SBSP3", "CMIG4",
    "HAPV3", "TOTS3", "KLBN11", "CSNA3", "USIM5", "CYRE3", "MRVE3", "AZZA3",
    "ASAI3", "BBSE3", "CXSE3", "TIMS3", "VIVT3", "SANB11", "RAIL3", "EMBJ3",
]

INDICE_REFERENCIA = "^BVSP"  # Ibovespa
# Referências globais para detectar regimes de mercado (fase 3)
GLOBAIS = {"^GSPC": "sp500", "BRL=X": "dolar", "BZ=F": "brent"}
NAO_ACOES = {INDICE_REFERENCIA, *GLOBAIS}

# Histórico de preços: curto prazo usa ~1 ano para médias, RSI, volatilidade.
PERIODO_PRECOS = "1y"

# Séries do Banco Central (SGS): código -> nome
SERIES_BCB = {
    432: "selic_meta",        # Selic meta (% a.a.)
    13522: "ipca_12m",        # IPCA acumulado 12 meses (%)
    1: "dolar_venda",         # Dólar comercial venda (R$)
}
DIAS_MACRO = 365

# --- Fase 2: pontuação de curto prazo ---
# "eventos" entra na fase 3; até lá os pesos são renormalizados entre os componentes disponíveis.
PESOS = {"momento": 0.40, "eventos": 0.25, "analistas": 0.20, "fundamentos": 0.15}

LIQUIDEZ_MIN_RS = 20_000_000   # volume financeiro médio diário (21 pregões)
MIN_ANALISTAS = 3
ATR_ALTO_PCT = 5.0             # alerta de volatilidade
JANELA_REVISAO_DIAS = (5, 30)  # compara consenso atual com snapshot de 5 a 30 dias atrás
TOP_N = 15

# --- Indicação do dia: regras de risco (ajuste aqui) ---
# Por nível de risco do mercado: máximo de ações, nota mínima, máximo por setor
SELECAO_POR_RISCO = {
    "baixo":    {"max_acoes": 5, "nota_min": 60, "max_por_setor": 2},
    "moderado": {"max_acoes": 4, "nota_min": 62, "max_por_setor": 2},
    "alto":     {"max_acoes": 3, "nota_min": 65, "max_por_setor": 1},
}
SELECAO_MOMENTO_MIN = 55   # nota de momento mínima
SELECAO_RSI_MAX = 72       # evita ação esticada

# --- Fase 3: notícias e eventos ---
# ticker -> (termo de busca nas notícias, trecho do nome na CVM)
EMPRESAS = {
    "PETR4": ("Petrobras", "PETROLEO BRASILEIRO"), "VALE3": ("Vale", "VALE S.A"),
    "ITUB4": ("Itaú Unibanco", "ITAU UNIBANCO HOLDING"), "BBDC4": ("Bradesco", "BANCO BRADESCO S"),
    "BBAS3": ("Banco do Brasil", "BANCO DO BRASIL S"), "B3SA3": ("B3", "B3 S.A"),
    "ABEV3": ("Ambev", "AMBEV"), "WEGE3": ("WEG", "WEG S"),
    "RENT3": ("Localiza", "LOCALIZA RENT A CAR"), "SUZB3": ("Suzano", "SUZANO S.A"),
    "ITSA4": ("Itaúsa", "ITAUSA"), "PRIO3": ("PRIO", "PRIO S.A"),
    "RADL3": ("Raia Drogasil", "RAIA DROGASIL"), "EQTL3": ("Equatorial Energia", "EQUATORIAL S.A"),
    "GGBR4": ("Gerdau", "GERDAU S.A"), "RDOR3": ("Rede D'Or", "REDE D'OR"),
    "BPAC11": ("BTG Pactual", "BANCO BTG PACTUAL"), "VBBR3": ("Vibra Energia", "VIBRA ENERGIA"),
    "UGPA3": ("Ultrapar", "ULTRAPAR"), "CSAN3": ("Cosan", "COSAN S"),
    "LREN3": ("Lojas Renner", "LOJAS RENNER"), "MGLU3": ("Magazine Luiza", "MAGAZINE LUIZA"),
    "SBSP3": ("Sabesp", "CIA SANEAMENTO BASICO ESTADO SAO PAULO"), "CMIG4": ("Cemig", "CIA ENERG MINAS GERAIS"),
    "HAPV3": ("Hapvida", "HAPVIDA"), "TOTS3": ("Totvs", "TOTVS"),
    "KLBN11": ("Klabin", "KLABIN"), "CSNA3": ("CSN", "CIA SIDERURGICA NACIONAL"),
    "USIM5": ("Usiminas", "USINAS SID"), "CYRE3": ("Cyrela", "CYRELA"),
    "MRVE3": ("MRV Engenharia", "MRV ENGENHARIA"), "AZZA3": ("Azzas", "AZZAS"),
    "ASAI3": ("Assaí Atacadista", "SENDAS DISTRIBUIDORA"), "BBSE3": ("BB Seguridade", "BB SEGURIDADE"),
    "CXSE3": ("Caixa Seguridade", "CAIXA SEGURIDADE"), "TIMS3": ("TIM", "TIM S.A"),
    "VIVT3": ("Vivo", "TELEFONICA BRASIL"), "SANB11": ("Santander Brasil", "BANCO SANTANDER (BRASIL)"),
    "RAIL3": ("Rumo", "RUMO S"), "EMBJ3": ("Embraer", "EMBRAER"),
}

# Buscas de contexto macro/global
BUSCAS_MACRO = [
    "Ibovespa", "Copom Selic", "dólar real câmbio", "petróleo Brent", "minério de ferro China",
    "Federal Reserve juros", "risco fiscal Brasil", "tarifas comércio exterior",
    "eleições Brasil mercado", "guerra conflito mercados",
]
DIAS_NOTICIAS = 7
PAUSA_NOTICIAS_S = 2.0

# Classificação de notícias com Claude (opcional). Sem credencial -> classificador por palavras-chave.
MODELO_CLAUDE = "claude-opus-5-5"

# Pausa entre requisições ao Yahoo (evita bloqueio por excesso de chamadas)
PAUSA_YAHOO_S = 0.6
