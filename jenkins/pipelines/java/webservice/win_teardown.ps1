#!/bin/bash
# Clean up after running Java Web Services tests

echo "Shutdown Test Server"
Push-Location servers\jak\desktop
& .\gradlew.bat --no-daemon appStop
Remove-Item app\server.url
Pop-Location

echo "Shutdown Environment"
Push-Location environment
& docker compose down

