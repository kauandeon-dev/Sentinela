# Registra o Sentinela para iniciar junto com o Windows (Agendador de Tarefas),
# rodando como SYSTEM, mesmo sem ninguém logado.
# Uso (PowerShell como Administrador, na pasta do Sentinela):
#   powershell -ExecutionPolicy Bypass -File deploy\windows\instalar-tarefa.ps1
# Remover: Unregister-ScheduledTask -TaskName Sentinela -Confirm:$false
param(
    [string]$Dados   = "$env:ProgramData\Sentinela\dados",
    [string]$Backups = "$env:ProgramData\Sentinela\backups",
    [int]$Porta = 8080
)
$ErrorActionPreference = "Stop"
$raiz = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Crie o ambiente antes: py -m venv .venv; .venv\Scripts\pip install -r requirements.txt" }
New-Item -ItemType Directory -Force -Path $Dados, $Backups | Out-Null

# Script que a tarefa executa (define as variáveis e inicia o painel)
$cmd = Join-Path $Dados "iniciar-servico.cmd"
@"
@echo off
set SENTINELA_HOME=$Dados
set SENTINELA_BACKUP_DIR=$Backups
set SENTINELA_PORT=$Porta
set PYTHONUTF8=1
cd /d "$raiz"
"$python" -m sentinela serve >> "$Dados\servico.log" 2>&1
"@ | Set-Content -Encoding ASCII $cmd

$acao = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$cmd`""
$gatilho = New-ScheduledTaskTrigger -AtStartup
$conta = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$config = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 0) -RestartCount 3 `
          -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
Register-ScheduledTask -TaskName "Sentinela" -Action $acao -Trigger $gatilho -Principal $conta `
                       -Settings $config -Force | Out-Null
Start-ScheduledTask -TaskName "Sentinela"
Start-Sleep -Seconds 8
Write-Host "Sentinela registrado e iniciado. Painel: http://127.0.0.1:$Porta"
Write-Host "Senha do primeiro acesso (se for a primeira vez):"
Select-String -Path "$Dados\servico.log" -Pattern "Primeiro acesso" | Select-Object -Last 1 | ForEach-Object { $_.Line }
