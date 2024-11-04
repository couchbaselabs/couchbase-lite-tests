
Write-Host "Shutdown Test Server"
Push-Location servers\jak\desktop
if (Test-Path -Path .\server.pid){
    $serverId = Get-Content .\server.pid
    Stop-Process -Id $serverId
}
Pop-Location

Write-Host "Shutdown Environment"
Push-Location environment
& docker compose down

