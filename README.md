# Radar B3 — curto prazo

Ferramenta pessoal que agrega dados públicos (preços, consenso de analistas, macro) para ranquear ações da B3.
**Não é recomendação de investimento.**

## Fase 1 — coleta (pronta)

```powershell
.\.venv\Scripts\python.exe coletar.py              # tudo
.\.venv\Scripts\python.exe coletar.py --sem-analistas
```

| Tabela | Conteúdo | Fonte |
|---|---|---|
| `precos` | OHLCV diário ajustado, 1 ano, + Ibovespa (`^BVSP`) | Yahoo Finance |
| `consenso_analistas` | Snapshot diário: recomendação, nº analistas, preço-alvo, upside, setor | Yahoo Finance |
| `macro` | Selic meta, IPCA 12m, dólar | Banco Central (SGS) |
| `log_coleta` | Resultado de cada execução | — |

Banco: `dados/radar.db`. Universo de ações em `radar/config.py`.
Rode **todo dia útil** (após o fechamento) para acumular histórico de revisões dos analistas.

## Fase 2 — ranking (pronta)

```powershell
.\.venv\Scripts\python.exe ranking.py              # hoje
.\.venv\Scripts\python.exe ranking.py 2026-11-20   # data passada (usa só dados até ela)
```

Gera `dados/ranking_AAAA-MM-DD.csv` (abre no Excel) e grava na tabela `ranking`.
Sub-notas são percentis dentro do universo (0–100). Filtros: liquidez ≥ R$ 20 mi/dia, ≥ 3 analistas.
Alertas: consenso inconsistente, analistas rebaixando, RSI > 75 / < 30, ATR > 5%.
`ref_stop_2atr` = preço − 2×ATR (referência técnica de volatilidade).
Revisões de analistas só passam a contar após 5 dias de coleta diária.

## Fase 3 — notícias e eventos (pronta)

`coletar.py` agora também coleta:

| Tabela | Conteúdo | Fonte |
|---|---|---|
| `noticias` | Manchetes dos últimos 7 dias por código da ação + 10 temas macro, com sentimento e eventos | Google News RSS (pt-BR) |
| `fatos_relevantes` | Fatos relevantes e comunicados ao mercado (30 dias) | Dados abertos CVM (IPE) |
| `precos` (+) | Dólar (`BRL=X`), Brent (`BZ=F`), S&P 500 (`^GSPC`) | Yahoo Finance |

**Classificação das manchetes** (`radar/sentimento.py`):
- Com credencial da Anthropic (`ANTHROPIC_API_KEY` ou `ant auth login`): Claude (`claude-opus-5-5`, effort baixo,
  fallback de recusa ligado) julga relevância, sentimento e eventos — bem mais preciso.
- Sem credencial: palavras-chave. Descarta manchetes que não citam a empresa no título e erra ironias/contexto.

**Nota de eventos** (`radar/eventos.py` + `radar/setores.py`):
- Regime macro: sinais quantitativos (dólar ±3%, Brent ±8%, Ibovespa vs S&P < −7 p.p., direção da Selic)
  com intensidade 1.0, e temas com ≥ 3 manchetes na semana com intensidade 0.5.
- Cada regime soma/subtrai pontos por grupo setorial (mapa em `setores.py`, editável).
- 50% regime macro + 50% sentimento das notícias da empresa (peso maior para as recentes).
- Fato relevante nos últimos 7 dias vira alerta no ranking.

## Indicação do dia

`radar/selecao.py` aplica filtros de risco ao ranking e o resultado aparece no topo do painel, no terminal e na
tabela `selecao` (para medir depois se as escolhas funcionaram).

1. **Risco do mercado** (baixo/moderado/alto): risco fiscal/político, tensão geopolítica, guerra comercial e queda do
   Ibovespa em 21 pregões.
2. **Regras por nível** (`SELECAO_POR_RISCO` em `config.py`): máximo de ações, nota mínima, máximo por setor.
3. **Filtros por ação:** momento ≥ 55 e preço acima da média de 21 dias, RSI ≤ 72, ATR ≤ 5%/dia, sem consenso
   inconsistente/rebaixamento; em risco alto, só setores não prejudicados pelo cenário.
4. Cada escolhida mostra preço, stop de referência (preço − 2×ATR), risco até o stop, motivos e riscos.
   Também lista as barradas pelos filtros e as 3 piores ("evitar"). Se nada passar, a indicação é ficar de fora.

## Agendamento (nuvem)

GitHub Actions (`.github/workflows/coleta.yml`) roda seg–sex às 19:00 (Brasília), mesmo com o PC desligado:
coleta → ranking → painel, grava o banco de volta no repositório e publica o painel em
**https://thiagofukumori.github.io/radar-b3/**.

```powershell
gh workflow run coleta.yml       # rodar agora
git pull                         # trazer o banco atualizado para o PC
```

A tarefa local do Windows ("Radar B3 - coleta diaria", `rodar_diario.ps1`) ficou desativada para não divergir do
banco da nuvem. Para voltar a usá-la: `Enable-ScheduledTask "Radar B3 - coleta diaria"`.

## Painel

`ranking.py` também gera `dados/painel.html` — arquivo único, abre direto no navegador (sem servidor, sem internet).
Indicadores (Ibovespa, dólar, Brent, S&P, Selic, IPCA), regime macro e efeito por setor, ranking ordenável e
filtrável, e o detalhe da ação clicada: sub-notas, gráfico de preço com média de 21 dias e stop de referência,
consenso, alertas, fatos relevantes da CVM e notícias da semana. Tema claro/escuro.
Layout em `radar/painel_template.html`.

## Pesos para curto prazo

| Componente | Peso |
|---|---|
| Momento/técnico (RSI, médias 9/21, volume relativo, força vs. Ibovespa) | 40% |
| Notícias e eventos (sentimento, fatos relevantes CVM, mapa evento→setor) | 25% |
| Revisões de analistas (mudança de recomendação/preço-alvo) | 20% |
| Fundamentos (filtro de qualidade) | 15% |
