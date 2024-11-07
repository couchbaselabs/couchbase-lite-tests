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

$config_json = $(Get-Content $PSScriptRoot\config.json)
$config_json = $config_json.Replace("{{test-server-ip}}", "localhost").Replace("{{test-client-ip}}", "localhost")
Set-Content .\config.json $config_json

pytest -v --no-header --config config.json
deactivate
Pop-Location