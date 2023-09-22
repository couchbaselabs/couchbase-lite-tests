Write-Host "Shutdown Test Server for WinUI..."
Push-Location $PSScriptRoot\..\..\..\servers\dotnet
scripts\stop_winui.ps1
Pop-Location

Write-Host "Shutdown Environment..."
Push-Location $PSScriptRoot\..\..\..\environment
docker compose down
Pop-Location