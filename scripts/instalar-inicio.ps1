<#
.SYNOPSIS
  Registra uma tarefa no Agendador de Tarefas do Windows que sobe o Automateum no logon, sem janela.
.DESCRIPTION
  Roda .venv\Scripts\pythonw.exe -m automateum com a pasta do projeto como diretório de trabalho.
  Para tirar: scripts\desinstalar-inicio.ps1. Log em dados\automateum.log.
.PARAMETER SemIniciar
  Só registra a tarefa; não sobe o Automateum agora.
#>
param([switch]$SemIniciar)

$ErrorActionPreference = "Stop"
$nome = "Automateum"
$raiz = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $raiz ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $pythonw)) {
    throw "Não achei $pythonw. Crie o ambiente antes: python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt"
}
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Warning "O comando 'claude' não está no PATH desta sessão. A tarefa usa o PATH do seu usuário; sem ele, as rotinas com Claude falham."
}

$acao = New-ScheduledTaskAction -Execute $pythonw -Argument "-m automateum" -WorkingDirectory $raiz
$gatilho = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $config -Principal $principal `
    -Description "Sobe o painel e o agendador do Automateum no logon." -Force | Out-Null
Write-Host "Tarefa '$nome' registrada: o Automateum sobe sozinho no próximo logon."

if (-not $SemIniciar) {
    Start-ScheduledTask -TaskName $nome
    Write-Host "Iniciado agora. Painel em http://127.0.0.1:8765 (log em dados\automateum.log)."
}
Write-Host "Para parar: Stop-ScheduledTask -TaskName $nome   |   Para remover: scripts\desinstalar-inicio.ps1"
