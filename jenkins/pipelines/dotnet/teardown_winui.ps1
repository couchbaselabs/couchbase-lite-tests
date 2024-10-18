Import-Module $PSScriptRoot/prepare_env.psm1 -Force

Banner "Shutdown Test Server for WinUI..."
& $PSScriptRoot\stop_winui.ps1

Banner "Shutdown Environment..."
Push-Location $PSScriptRoot\..\..\..\environment
docker compose down
Pop-Location