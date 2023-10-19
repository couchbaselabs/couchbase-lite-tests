#!/bin/bash
# Clean up after running Java Web Services tests

echo "Shutdown Test Server"
Push-Location servers\jak\desktop
& .\gradlew.bat --no-daemon appStop
Pop-Location

echo "Shutdown Environment"
Push-Location environment
& docker compose down

