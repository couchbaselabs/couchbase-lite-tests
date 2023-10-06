#!/bin/bash
# Clean up after running Java Web Services tests

echo "Shutdown Test Server"
Push-Location servers\jak\desktop
if (Test-Path -Path .\server.pid){
    $serverId = Get-Content .\server.pid
    Stop-Process -Id $serverId
}
Pop-Location

echo "Shutdown Environment"
Push-Location environment
& docker compose down

