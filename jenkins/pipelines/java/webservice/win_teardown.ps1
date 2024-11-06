
$ErrorActionPreference = "Stop"

Write-Host "Windows Web Service: Shutdown the Test Server"
Push-Location servers\jak\desktop
& .\gradlew.bat --no-daemon appStop
Pop-Location

Write-Host "Windows Web Service: Shutdown the environment"
Push-Location environment
& docker compose down

