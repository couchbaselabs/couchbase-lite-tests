param (
    [Parameter()][string]$Edition = "enterprise",
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$Build
)

$ErrorActionPreference = "Stop" 

$nugetPackageVersion = "$Version-b$($Build.PadLeft(4, '0'))"
Write-Host "Using NuGet package version $nugetPackageVersion"
dotnet add $PSScriptRoot\..\..\..\servers\dotnet\testserver.logic\testserver.logic.csproj package couchbase.lite.enterprise --version $nugetPackageVersion

& $PSScriptRoot\build_winui.ps1
& $PSScriptRoot\run_winui.ps1

Write-Host "Start Environment..."
Push-Location $PSScriptRoot\..\..\..\environment
docker compose down # Just in case it didn't get shut down cleanly
python start_environment.py
Pop-Location

Push-Location $PSScriptRoot\..\..\..\tests
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
Copy-Item $PSScriptRoot\config.json .
pytest -v --no-header --config config.json
deactivate
Pop-Location