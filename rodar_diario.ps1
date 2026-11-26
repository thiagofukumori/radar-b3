# Coleta diaria + ranking + painel. Chamado pelo Agendador de Tarefas do Windows ("Radar B3 - coleta diaria").
# (Sem acentos neste arquivo: o PowerShell 5.1 le scripts sem BOM como ANSI.)
$ErrorActionPreference = "Continue"
$raiz = $PSScriptRoot
Set-Location $raiz
$py = Join-Path $raiz ".venv\Scripts\python.exe"
$logs = Join-Path $raiz "dados\logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs ("{0:yyyy-MM-dd}.log" -f (Get-Date))
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

"=== Inicio $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss') ===" | Out-File $log -Append -Encoding utf8
& $py coletar.py *>&1 | Out-File $log -Append -Encoding utf8
$okColeta = $LASTEXITCODE -eq 0
& $py ranking.py *>&1 | Out-File $log -Append -Encoding utf8
$okRanking = $LASTEXITCODE -eq 0
"=== Fim $(Get-Date -Format 'HH:mm:ss') | coleta=$okColeta ranking=$okRanking ===" | Out-File $log -Append -Encoding utf8

# Mantém só os últimos 60 logs
Get-ChildItem $logs -Filter *.log | Sort-Object Name -Descending | Select-Object -Skip 60 | Remove-Item -Force
if (-not ($okColeta -and $okRanking)) { exit 1 }
