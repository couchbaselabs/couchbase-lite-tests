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

& $PSScriptRoot\..\shared\setup_backend.ps1 -SgwUrl $SgwUrl

Push-Location $PSScriptRoot\..\..\..\tests
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
Copy-Item $PSScriptRoot\config.json .
pytest -v --no-header --config config.json
deactivate
Pop-Location