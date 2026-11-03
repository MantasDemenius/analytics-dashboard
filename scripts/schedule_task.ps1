param(
    [string]$TaskName = 'Analytics Dashboard Weekly Report'
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogFile = Join-Path $RepoRoot 'logs\scheduled-run.log'

function New-ReportTrigger {
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At '11:00'
}

function New-ReportSettings {
    New-ScheduledTaskSettingsSet -StartWhenAvailable
}

function New-ReportPrincipal {
    New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
}

function New-ReportAction([string]$Uv) {
    $command = "`"`"$Uv`" run weekly-report --email >> `"$LogFile`" 2>&1`""
    New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c $command" -WorkingDirectory $RepoRoot
}

function Register-ReportTask {
    $uv = (Get-Command uv -CommandType Application).Source
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogFile) | Out-Null
    $task = New-ScheduledTask `
        -Action (New-ReportAction $uv) `
        -Trigger (New-ReportTrigger) `
        -Settings (New-ReportSettings) `
        -Principal (New-ReportPrincipal)
    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
    Write-Output "Registered '$TaskName': Mondays 11:00, output appended to $LogFile"
}

if ($MyInvocation.InvocationName -ne '.') {
    Register-ReportTask
}
