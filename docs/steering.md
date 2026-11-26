# Steering — Radar B3 (curto prazo)

Documento de orientação para quem for mexer no projeto: pessoas ou agentes de IA.
Descreve o que o sistema faz, do dado bruto até o painel, e as regras que não podem ser quebradas.

## 1. Produto

- **O que é:** ferramenta pessoal que junta dados públicos sobre ações da B3 e gera um ranking de curto prazo.
  O ranking considera preço, consenso de analistas, fundamentos, notícias, fatos relevantes da CVM e cenário macro.
  A partir dele, o sistema gera uma **indicação do dia** ajustada ao risco do mercado.
- **Saídas:**
  - o painel HTML `dados/painel.html`;
  - o texto no terminal;
  - o CSV `dados/ranking_AAAA-MM-DD.csv`;
  - as tabelas `ranking` e `selecao` no SQLite.
- **Limite de escopo:** a indicação é a saída de regras fixas. Não conhece a situação financeira de quem lê.
  Todo texto voltado ao usuário (painel, terminal, README) deve manter o aviso
  **"não é recomendação de investimento"**.
- **Horizonte:** curto prazo, de dias a poucas semanas.
- **Universo:** 40 ações líquidas, listadas em `TICKERS` em `radar/config.py`.

## 2. Pipeline de ponta a ponta

```
Agendador do Windows (seg–sex 19:00)
  └─ rodar_diario.ps1
       ├─ coletar.py   → grava dados brutos datados em dados/radar.db
       └─ ranking.py   → indicadores → notas → ranking → seleção → painel / CSV / terminal
```

### 2.1 Coleta (`coletar.py`)

As etapas rodam nesta ordem. Cada uma grava uma linha em `log_coleta`.

| # | Módulo | O que coleta | Fonte | Tabela |
|---|---|---|---|---|
| 1 | `coleta_precos.py` | Preço diário (OHLCV) das ações, do Ibovespa (`^BVSP`), do S&P 500 (`^GSPC`), do dólar (`BRL=X`) e do Brent (`BZ=F`) | Yahoo Finance (yfinance), sufixo `.SA` | `precos` |
| 2 | `coleta_analistas.py` | Consenso dos analistas: recomendação, nota média de 1 a 5, nº de analistas, preço-alvo, upside e setor. Também coleta fundamentos: P/L, P/VP, ROE, dívida/patrimônio, margem e DY | Yahoo `.info` | `consenso_analistas`, `fundamentos` |
| 3 | `coleta_macro.py` | Selic meta (série 432), IPCA 12 meses (13522) e dólar (1) | API SGS do Banco Central | `macro` |
| 4 | `coleta_noticias.py` | Manchetes dos últimos 7 dias, buscadas pelo **código da ação**, mais 10 temas macro (`BUSCAS_MACRO`) | Google News RSS pt-BR | `noticias` |
| 5 | `sentimento.py` | Classifica as manchetes pendentes: relevância, sentimento de −1 a +1 e eventos | Claude ou palavras-chave | `noticias` (atualiza) |
| 6 | `coleta_cvm.py` | Fatos relevantes e comunicados ao mercado | Dados abertos CVM (zip IPE) | `fatos_relevantes` |

- `--sem-analistas` pula a etapa 2.
- A etapa CVM roda em `try/except`. Se falhar, o resto da coleta continua.
- Notícias:
  - Há retentativa com espera de 0, 10 e 30 s em respostas 429/503, e pausa de 2 s entre buscas.
  - Cada busca guarda no máximo 40 itens.
- CVM:
  - O ticker é encontrado pelo **prefixo** do nome da empresa na CVM (`EMPRESAS` em `config.py`), usando `startswith` em nomes normalizados.
  - O mapeamento é calculado sobre o arquivo inteiro, antes do filtro de datas.
- Sentimento:
  - Com credencial da Anthropic, usa Claude: `client.beta.messages.parse` com modelo `claude-opus-5-5`, effort baixo e saída estruturada em pydantic.
  - Sem credencial, usa regex de palavras-chave. Nesse modo, uma manchete só é relevante se citar a empresa ou o ticker no título.
  - Hoje **não há credencial** na máquina: o caminho do Claude nunca foi testado de verdade.

### 2.2 Indicadores técnicos (`radar/tecnico.py` → `indicadores(con, data_ref)`)

- Usa só os preços com `data <= data_ref`.
- Exige pelo menos 70 pregões por ação e ignora os ativos que não são ações (`NAO_ACOES`).
- Calcula, para cada ação:
  - retornos de 5, 21 e 63 pregões **descontado o retorno do Ibovespa** no mesmo período;
  - RSI de 14 períodos;
  - distância do preço até a média de 21 dias;
  - se a média de 9 está acima da de 21;
  - inclinação da média de 21 em 5 pregões;
  - volume relativo (média de 5 dias sobre média de 21 dias);
  - ATR de 14 dias em % do preço;
  - liquidez média em R$ nos últimos 21 dias.

### 2.3 Notas (`radar/pontuacao.py` → `gerar_ranking(con, data_ref)`)

- **Filtro de liquidez:** ações abaixo de `LIQUIDEZ_MIN_RS` (R$ 20 mi/dia) são excluídas e listadas em `df.attrs["excluidas_liquidez"]`.
- **Escala:** as sub-notas vão de 0 a 100. A maioria usa **percentil dentro do universo**, ou seja, mede a posição relativa entre as ações acompanhadas, não um valor absoluto.
- **Componentes faltantes:** a média ponderada ignora o componente que falta e redistribui o peso entre os outros (`_media_ponderada`).

| Sub-nota | Composição | Peso na nota final (`PESOS`) |
|---|---|---|
| **Momento** | Retorno em 21 pregões vs Ibov (0,30), em 63 (0,20), em 5 (0,10); tendência das médias 9/21 e inclinação (0,20); RSI com ideal em 60 (0,10); volume relativo (0,10) | 0,40 |
| **Eventos** | Ver 2.4 | 0,25 |
| **Analistas** | Nível do consenso (0,30); upside (0,25); revisão do preço-alvo (0,25); revisão da nota (0,20). Fica vazia se houver menos de 3 analistas (`MIN_ANALISTAS`) | 0,20 |
| **Fundamentos** | ROE (0,30), margem (0,20), P/L menor é melhor e prejuízo vale 0 (0,30), dívida/patrimônio menor é melhor (0,20) | 0,15 |

- **Revisões dos analistas:** comparam a coleta de hoje com o snapshot mais antigo entre 5 e 30 dias atrás (`JANELA_REVISAO_DIAS`).
  Por isso só passam a pesar depois de algumas semanas de coleta diária.
- **Consenso inconsistente:** acontece quando a recomendação é de venda com upside acima de 30%, ou quando o upside passa de 120% ou fica abaixo de −50%.
  Nesses casos o upside é descartado e a ação recebe um alerta.
- **Alertas gerados no ranking:**
  - consenso inconsistente;
  - analistas rebaixando (nota piorou 0,3 ou mais);
  - RSI acima de 75 ou abaixo de 30;
  - ATR acima de 5%;
  - sem consenso válido;
  - `FATO RELEVANTE: …` (nos últimos 7 dias).
- **Stop de referência:** `ref_stop_2atr = preço × (1 − 2 × ATR%)`.
- **Atributos do DataFrame:**
  - `df.attrs["regimes"]`: regimes macro ativos;
  - `df.attrs["excluidas_liquidez"]`: ações cortadas pela liquidez.

### 2.4 Eventos (`radar/eventos.py` + `radar/setores.py`)

1. **Regimes macro** (`regimes`) — dicionário `evento → (intensidade, motivo)`:
   - **Sinais quantitativos, com intensidade 1,0:**
     - dólar variou mais de 3% para cima ou para baixo em 21 pregões;
     - Brent variou mais de 8% para cima ou para baixo;
     - Ibovespa ficou mais de 7 p.p. abaixo do S&P 500, o que indica risco fiscal/político;
     - Selic subiu ou caiu em relação a cerca de 60 observações atrás.
   - **Temas das manchetes macro, com intensidade 0,5:** temas com 3 ou mais manchetes na semana.
   - **Sinais opostos se anulam:** quando os dois têm a mesma intensidade, saem os dois; senão, fica o mais forte.
2. **Nota macro da ação:**
   - fórmula: `50 + 12,5 × Σ(intensidade × impacto)`, limitada entre 0 e 100;
   - o impacto vai de −2 a +2 por grupo setorial e está em `IMPACTOS` em `setores.py`;
   - há um ajuste extra para estatais (`_estatal`).
3. **Nota de notícias:**
   - média do sentimento ponderada pela idade da manchete, com meia-vida de 3 dias;
   - encolhida para o neutro com o fator `n/(n+3)`;
   - fórmula final: `50 + 50 × sentimento`.
4. **Nota de eventos:** 50% macro + 50% notícias. Sem notícias, vale só a macro.

### 2.5 Indicação do dia (`radar/selecao.py` → `selecionar(con, df, regimes)`)

1. **Nível de risco do mercado** (`nivel_risco_mercado`):

   | Condição | Pontos |
   |---|---|
   | Risco fiscal/político | 2 × intensidade |
   | Tensão geopolítica | 1 × intensidade |
   | Guerra comercial | 0,5 × intensidade |
   | Ibovespa em 21 pregões abaixo de −10% | 2 |
   | Ibovespa em 21 pregões abaixo de −5% | 1 |

   Com 3 pontos ou mais, o risco é **alto**. Com 1,5 ou mais, **moderado**. Abaixo disso, **baixo**.
2. **Regra por nível** (`SELECAO_POR_RISCO`):

   | Nível | Máximo de ações | Nota mínima | Máximo por setor |
   |---|---|---|---|
   | Baixo | 5 | 60 | 2 |
   | Moderado | 4 | 62 | 2 |
   | Alto | 3 | 65 | 1 |

3. **Filtros por ação**, em ordem; o primeiro que falhar vira o motivo da exclusão:
   - nota mínima do nível;
   - momento de pelo menos 55 (`SELECAO_MOMENTO_MIN`) **e** preço acima da média de 21 dias;
   - RSI de no máximo 72 (`SELECAO_RSI_MAX`);
   - ATR de no máximo 5%;
   - sem alerta de consenso inconsistente ou de rebaixamento;
   - com nota de analistas válida;
   - em risco alto, nota macro de pelo menos 50 (o setor não pode ser prejudicado pelo cenário);
   - limite de ações por setor.
4. **Retorno da função:** um dicionário com os campos abaixo. Se `escolhidas` vier vazia, o resumo diz que a indicação é **ficar de fora**.

   | Campo | Conteúdo |
   |---|---|
   | `data`, `nivel_risco`, `motivos_risco`, `regra`, `resumo` | Contexto do dia |
   | `escolhidas` | Para cada ação: preço, stop, risco até o stop, risco baixo/médio/alto, "por que entrou" e "riscos" |
   | `barradas` | Até 6 ações com nota suficiente que caíram em algum filtro |
   | `evitar` | As 3 piores notas |

### 2.6 Saídas (`ranking.py`)

1. Calcula `gerar_ranking`.
2. Grava a tabela `ranking`, apagando antes as linhas da mesma data.
3. Roda `selecionar` e grava a tabela `selecao`.
4. Gera o painel com `gerar_painel(con, df, sel)`.
5. Grava o CSV com `;` como separador, vírgula decimal e codificação utf-8-sig, para abrir no Excel.
6. Imprime o resumo no terminal, incluindo o bloco `=== INDICAÇÃO DO DIA ===`.

Com `ranking.py AAAA-MM-DD`, o processo é refeito para uma data passada, usando só os dados até aquela data.

### 2.7 Painel (`radar/painel.py` + `radar/painel_template.html`)

- **Montagem dos dados:** `montar_dados` junta:
  - os indicadores (KPIs) com séries de 64 pregões;
  - Selic e IPCA;
  - os regimes e o impacto por grupo setorial;
  - o ranking com grupo e empresa;
  - o detalhe de cada ação: 130 dias de preço, notícias da semana e fatos da CVM dos últimos 30 dias;
  - as notícias macro;
  - o classificador usado.
- **Geração do HTML:** `gerar_painel` serializa os dados em JSON e os injeta no lugar de `/*__DADOS__*/null` no template.
  O resultado é **um único arquivo HTML** que funciona offline, sem dependências externas.
- **Template:** JS puro com gráficos em SVG. Seções, de cima para baixo:
  1. indicação do dia (`renderHero`): selo de risco, cartões das escolhidas, barradas, evitar, regras usadas e aviso;
  2. indicadores com sparklines;
  3. chips de regime;
  4. efeito por setor (gráfico divergente);
  5. ranking ordenável e filtrável;
  6. detalhe da ação;
  7. notícias macro.
- **Tema:** claro ou escuro. A preferência fica em `localStorage`, sempre dentro de `try/catch`.
- **Publicação:** também foi publicado como artifact privado em https://claude.ai/artifact/D5FCERfNetqeJKnhvPWyU1.
  Esse link **não** se atualiza sozinho. É preciso republicar o mesmo arquivo depois de cada coleta.

### 2.8 Agendamento

- **Tarefa do Windows:** "Radar B3 - coleta diaria".
  - Roda de segunda a sexta às 19:00.
  - Se o PC estiver desligado no horário, roda assim que ligar.
  - O limite de execução é 1 h, e uma nova execução é ignorada se a anterior ainda estiver rodando.
- **`rodar_diario.ps1`:**
  - roda `coletar.py` e depois `ranking.py`;
  - grava o log em `dados/logs/AAAA-MM-DD.log` e mantém os últimos 60;
  - sai com código 1 se algo falhar.

## 3. Invariantes (não quebrar)

1. **Sem look-ahead.** Todo cálculo recebe `data_ref` e só lê dados com data até ela.
   Os dados brutos são sempre gravados datados (`data`, `data_coleta`, `data_pub`, `data_entrega`).
   Isso permite fazer o backtest com o mesmo código.
2. **Snapshots diários são insubstituíveis.** O histórico de revisões dos analistas só existe porque a coleta roda todo dia.
   Não apague nem sobrescreva linhas de dias anteriores em `consenso_analistas` e `fundamentos`.
3. **Pesos e limites ficam só em `config.py`.** Não coloque números de regra direto no código.
   Isso vale para `PESOS`, `SELECAO_*`, `LIQUIDEZ_MIN_RS` e `ATR_ALTO_PCT`.
4. **Textos em pt-BR usam `br()`** (`radar/selecao.py`) para números com vírgula decimal. Nunca use `f"{x:.1f}"` em texto para o usuário.
5. **`rodar_diario.ps1` só pode ter caracteres ASCII.** O PowerShell 5.1 lê arquivo sem BOM como ANSI.
   O script também força UTF-8 no console e em `PYTHONIOENCODING`.
6. **O painel é autocontido.** Não adicione CDN, fontes externas nem chamadas de rede ao template.
   Ele precisa abrir com duplo clique e funcionar como artifact.
7. **Regras de cor do painel:**
   - azul sequencial para as notas;
   - azul/vermelho divergente para sentimento e efeito por setor;
   - cores de status sempre acompanhadas de ícone e texto;
   - tokens de cor definidos para os temas claro e escuro.
8. **Aviso obrigatório:** "não é recomendação de investimento" no painel, no terminal e no README.

## 4. Onde mexer para…

| Objetivo | Arquivo |
|---|---|
| Adicionar ou remover ações | `TICKERS` e `EMPRESAS` (termo de busca e prefixo do nome na CVM) em `config.py`; grupo setorial em `setores.py` |
| Mudar pesos das notas | `PESOS` em `config.py` |
| Deixar a indicação mais ou menos exigente | `SELECAO_POR_RISCO`, `SELECAO_MOMENTO_MIN`, `SELECAO_RSI_MAX` em `config.py` |
| Mudar como o risco do mercado é medido | `nivel_risco_mercado` em `selecao.py` |
| Mudar o efeito de um evento num setor | `IMPACTOS` em `setores.py` |
| Novo tema de notícia macro | `BUSCAS_MACRO` em `config.py` e o nome do evento em `sentimento.py` e `setores.py` |
| Layout do painel | `radar/painel_template.html`; os dados vêm de `montar_dados` |
| Ligar a classificação por Claude | Definir `ANTHROPIC_API_KEY` ou rodar `ant auth login` (nenhum código muda) |

## 5. Comandos

```powershell
.\.venv\Scripts\python.exe coletar.py                 # coleta completa
.\.venv\Scripts\python.exe ranking.py                 # ranking, seleção e painel de hoje
.\.venv\Scripts\python.exe ranking.py 2026-11-20      # refaz uma data passada
Start-ScheduledTask "Radar B3 - coleta diaria"         # roda o agendamento agora
```

## 6. Problemas conhecidos

- O Google News limita requisições: execuções seguidas podem falhar com 429. A retentativa resolve a maioria dos casos.
- O caminho de classificação por Claude não foi testado sem credencial. As palavras-chave erram ironia e contexto.
- Preços-alvo do Yahoo podem estar desatualizados; a regra de consenso inconsistente é a proteção para isso.
- EMBR3 passou a ser EMBJ3 no Yahoo. Mudanças de código de ação quebram a coleta em silêncio, então confira o `log_coleta`.
- As regras da indicação ainda **não foram validadas com backtest**. A tabela `selecao` acumula o histórico para essa validação (fase 4, pendente).
