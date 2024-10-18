Import-Module $PSScriptRoot/prepare_env.psm1 -Force

$childPID = Get-Process -ProcessName testserver -ErrorAction Ignore | Select-Object -Expand Id
if($null -eq $childPID) {
    Write-Error "No running testserver found!"
    exit 1
}

Banner "Stopping testserver ($childPID)"
Stop-Process $childPID