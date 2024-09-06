$server_pid = $(Get-Process | Where-Object { $_.ProcessName -eq "testserver.cli" } | Select-Object -ExpandProperty Id)
if($null -eq $server_pid) {
    Write-Error "No process found to stop"
    exit 1
}

Write-Host "Stopping PID $server_pid..."
Stop-Process $server_pid