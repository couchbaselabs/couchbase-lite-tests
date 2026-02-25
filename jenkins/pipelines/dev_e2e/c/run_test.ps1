param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter][string]$DatasetVersion = "4.0"
)

$ErrorActionPreference = "Stop" 

Import-Module $PSScriptRoot\..\..\shared\config.psm1 -Force
uv run $PSScriptRoot\setup_test.py "windows" $Version $SgwVersion
if($LASTEXITCODE -ne 0) {
    throw "Setup failed!"
}

Push-Location $DEV_E2E_TESTS_DIR
try {
    uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json --dataset-version $DatasetVersion
    $saved_exit = $LASTEXITCODE
} finally {
    Pop-Location
}

if($saved_exit -ne 0) {
    throw "Testing failed!"
}