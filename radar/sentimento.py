"""Classificação de manchetes: sentimento (-1 a +1) e categorias de evento macro.

Usa Claude quando há credencial da Anthropic (ANTHROPIC_API_KEY ou `ant auth login`);
senão cai num classificador por palavras-chave, mais grosseiro mas gratuito.
"""
import re
from typing import List, Literal

from pydantic import BaseModel, Field

from .config import EMPRESAS, MODELO_CLAUDE

EVENTOS = (
    "juros_subindo", "juros_caindo", "dolar_forte", "dolar_fraco",
    "petroleo_alta", "petroleo_baixa", "china_estimulo", "china_desaceleracao",
    "risco_fiscal_politico", "alivio_fiscal_politico", "tensao_geopolitica", "guerra_comercial",
)

# ------------------------------------------------------------ palavras-chave
POSITIVAS = r"lucro (cresce|sobe|recorde)|alta|sobe|dispara|salta|avança|recorde|supera|eleva|upgrade|" \
            r"recomenda(ção de)? compra|dividendos?|recompra|aprova|expansão|otimis|ganho|valoriza|melhora"
NEGATIVAS = r"prejuízo|queda|cai|despenca|recua|tomba|rebaixa|downgrade|recomenda(ção de)? venda|" \
            r"investiga|multa|processo|fraude|recuperação judicial|crise|pessimis|perda|desvaloriza|piora|" \
            r"greve|rombo|calote|demite|corte de|suspende"
REGRAS_EVENTO = {
    "juros_subindo": r"(selic|juros|copom|fed).{0,40}(alta|sobe|eleva|aument|aperto)|aperto monetário",
    "juros_caindo": r"(selic|juros|copom|fed).{0,40}(corte|cai|reduz|queda|afrouxa)|afrouxamento",
    "dolar_forte": r"d[oó]lar.{0,30}(sobe|alta|dispara|avança|bate|recorde|r\$ ?6)",
    "dolar_fraco": r"d[oó]lar.{0,30}(cai|queda|recua|despenca)|real se valoriza",
    "petroleo_alta": r"(petr[oó]leo|brent|wti).{0,30}(sobe|alta|dispara|avança)",
    "petroleo_baixa": r"(petr[oó]leo|brent|wti).{0,30}(cai|queda|recua|despenca)",
    "china_estimulo": r"china.{0,40}(est[ií]mulo|pacote|corta juros|acelera)",
    "china_desaceleracao": r"china.{0,40}(desacelera|fraco|deflação|crise imobiliária)",
    "risco_fiscal_politico": r"risco fiscal|rombo|déficit|gastos públicos|pec|arcabouço|incerteza política|"
                             r"intervenção|furo do teto",
    "alivio_fiscal_politico": r"superávit|corte de gastos|ajuste fiscal|reforma aprovada",
    "tensao_geopolitica": r"guerra|ataque|míssil|conflito|sanç(ão|ões)|tensão geopolítica",
    "guerra_comercial": r"tarifa|taxação|protecionis|guerra comercial",
}


def _palavras(titulo: str, ticker: str | None):
    t = titulo.lower()
    if ticker:
        nome = EMPRESAS[ticker][0].lower()
        if nome not in t and ticker.lower() not in t:
            return 0.0, "irrelevante"
    pos = len(re.findall(POSITIVAS, t))
    neg = len(re.findall(NEGATIVAS, t))
    sent = 0.0 if pos == neg else max(-1.0, min(1.0, (pos - neg) * 0.5))
    eventos = [e for e, rx in REGRAS_EVENTO.items() if re.search(rx, t)]
    return sent, ",".join(eventos)


# ------------------------------------------------------------ Claude
class Classificacao(BaseModel):
    indice: int
    relevante: bool = Field(description="A manchete trata do negócio/ação da empresa (ou de mercado/economia, se macro)?")
    sentimento: float = Field(description="-1 muito negativo ... 0 neutro ... +1 muito positivo para o preço da ação/mercado BR")
    eventos: List[Literal[EVENTOS]]


class Lote(BaseModel):
    itens: List[Classificacao]


INSTRUCOES = (
    "Você classifica manchetes do mercado financeiro brasileiro. Para cada manchete numerada, diga se é "
    "relevante para o preço da ação indicada (ou para o mercado brasileiro, quando o alvo é MACRO), o "
    "sentimento de curto prazo para esse preço (-1 a +1) e quais categorias de evento macro ela indica "
    "(lista vazia se nenhuma). Homônimos (ex.: time esportivo com nome da empresa) são irrelevantes. "
    "Responda um item por manchete, usando o mesmo índice."
)


def _cliente_claude():
    try:
        import anthropic
        cliente = anthropic.Anthropic()
        cliente.models.retrieve(MODELO_CLAUDE)  # valida credencial
        return cliente
    except Exception:
        return None


def _claude_lote(cliente, linhas):
    texto = "\n".join(
        f"[{i}] alvo={tk or 'MACRO'}{' (' + EMPRESAS[tk][0] + ')' if tk else ''} | {titulo}"
        for i, (_, tk, titulo) in enumerate(linhas)
    )
    resp = cliente.beta.messages.parse(
        model=MODELO_CLAUDE,
        max_tokens=16000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=INSTRUCOES,
        messages=[{"role": "user", "content": texto}],
        output_format=Lote,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        return {}
    return {c.indice: c for c in resp.parsed_output.itens}


# ------------------------------------------------------------ orquestração
def classificar_pendentes(con, tamanho_lote=60):
    pend = con.execute("SELECT id, ticker, titulo FROM noticias WHERE sentimento IS NULL").fetchall()
    if not pend:
        return 0, "nada pendente"
    cliente = _cliente_claude()
    modo = f"claude:{MODELO_CLAUDE}" if cliente else "palavras-chave"

    feitos = 0
    for k in range(0, len(pend), tamanho_lote):
        lote = pend[k:k + tamanho_lote]
        res = {}
        if cliente:
            try:
                res = _claude_lote(cliente, lote)
            except Exception as e:
                print(f"  aviso: Claude falhou ({type(e).__name__}); usando palavras-chave neste lote")
        upd = []
        for i, (nid, tk, titulo) in enumerate(lote):
            c = res.get(i)
            if c:
                ev = "irrelevante" if not c.relevante else ",".join(c.eventos)
                upd.append((max(-1.0, min(1.0, c.sentimento)) if c.relevante else 0.0, ev, modo, nid))
            else:
                s, ev = _palavras(titulo, tk)
                upd.append((s, ev, "palavras-chave", nid))
        con.executemany("UPDATE noticias SET sentimento=?, eventos=?, classificador=? WHERE id=?", upd)
        feitos += len(upd)
    return feitos, modo
