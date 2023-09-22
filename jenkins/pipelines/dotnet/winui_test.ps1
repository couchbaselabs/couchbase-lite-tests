param (
    [Parameter()][string]$Edition = "enterprise",
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$Build
)

Write-Host "Build TestServer for WinUI..."
Push-Location $PSScriptRoot\..\..\..\servers\dotnet

$nugetPackageVersion = "$Version-b$($Build.PadLeft(4, '0'))"
Write-Host "Using NuGet package version $nugetPackageVersion"
dotnet add .\testserver.csproj package couchbase.lite.enterprise --version $nugetPackageVersion -s https://proget.sc.couchbase.com/nuget/Internal/v3/index.json
scripts\build_winui.ps1

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