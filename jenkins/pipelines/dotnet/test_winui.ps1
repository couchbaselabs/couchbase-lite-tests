param (
    [Parameter()][string]$Edition = "enterprise",
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$Build,
    [Parameter()][string]$SgwUrl = ""
)

Import-Module $PSScriptRoot/prepare_env.psm1 -Force
$ErrorActionPreference = "Stop" 

$nugetPackageVersion = "$Version-b$($Build.PadLeft(4, '0'))"
Write-Host "Using NuGet package version $nugetPackageVersion"
& $env:LOCALAPPDATA\Microsoft\dotnet\dotnet add $PSScriptRoot\..\..\..\servers\dotnet\testserver.logic\testserver.logic.csproj package couchbase.lite.enterprise --version $nugetPackageVersion

& $PSScriptRoot\build_winui.ps1
& $PSScriptRoot\run_winui.ps1

Banner "Stopping existing environment"
Push-Location $PSScriptRoot\..\..\..\environment
docker compose down # Just in case it didn't get shut down cleanly
if($SgwUrl -ne "") {
    Banner "Building SGW environment"
    docker compose build cbl-test-sg --build-arg SG_DEB="$SgwUrl"
}

Banner "Starting new environment"
python start_environment.py
Pop-Location

Push-Location $PSScriptRoot\..\..\..\tests
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
Copy-Item $PSScriptRoot\config.json .
pytest -v --no-header --config .\config.json .\test_basic_replication.py -k "test_replicate_non_existing_sg_collections"
deactivate
Pop-Location