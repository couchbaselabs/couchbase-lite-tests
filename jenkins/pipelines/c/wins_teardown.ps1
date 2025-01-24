Write-Host "Shutdown Environment"
Push-Location "$PSScriptRoot\..\..\..\environment"
docker compose logs cbl-test-sg | Out-File -FilePath "cbl-test-sg.log" -Force
docker compose down
Pop-Location