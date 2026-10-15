<#
.SYNOPSIS
  Para o Automateum e remove a tarefa de início com o Windows criada por instalar-inicio.ps1.
#>
$ErrorActionPreference = "Stop"
$nome = "Automateum"

if (-not (Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue)) {
    Write-Host "A tarefa '$nome' não está registrada. Nada a remover."
    return
}
Stop-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $nome -Confirm:$false
Write-Host "Tarefa '$nome' removida. O Automateum não sobe mais com o Windows."
