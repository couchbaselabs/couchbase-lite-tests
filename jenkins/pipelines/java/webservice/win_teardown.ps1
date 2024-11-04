
Write-Host "Shutdown Test Server"
Push-Location servers\jak\desktop
& .\gradlew.bat --no-daemon appStop
Remove-Item app\server.url
Pop-Location

Write-Host "Shutdown Environment"
Push-Location environment
& docker compose down

