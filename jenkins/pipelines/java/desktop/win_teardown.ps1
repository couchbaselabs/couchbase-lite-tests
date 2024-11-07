Write-Host "Windows Desktop: Shutdown the Test Server"

Push-Location servers\jak\desktop
if (Test-Path -Path .\server.pid)
{
    $serverId = Get-Content .\server.pid
    Stop-Process -Id $serverId -ErrorAction SilentlyContinue
}
Pop-Location

Write-Host "Windows Desktop: Shutdown the environment"
Push-Location environment
& docker compose down
