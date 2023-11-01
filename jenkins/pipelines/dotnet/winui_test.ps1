param (
    [Parameter()][string]$Edition = "enterprise",
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$Build
)

Write-Host "Build TestServer for WinUI..."
Push-Location $PSScriptRoot\..\..\..\servers\dotnet

$nugetPackageVersion = "$Version-b$($Build.PadLeft(4, '0'))"
Write-Host "Using NuGet package version $nugetPackageVersion"
dotnet add .\testserver.csproj package couchbase.lite.enterprise --version $nugetPackageVersion
dotnet publish .\testserver.csproj -c Release -f net7.0-windows10.0.19041.0

Write-Host "Run TestServer..."
scripts\run_winui.ps1
Pop-Location

Write-Host "Start Environment..."
Push-Location $PSScriptRoot\..\..\..\environment
docker compose down # Just in case it didn't get shut down cleanly
python start_environment.py
Pop-Location

Push-Location $PSScriptRoot\..\..\..\tests
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
pytest -v --no-header --config config.example.json
deactivate
Pop-Location