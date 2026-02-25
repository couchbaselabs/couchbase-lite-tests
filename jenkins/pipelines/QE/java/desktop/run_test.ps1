param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion
)
$ErrorActionPreference = "Stop" 
Import-Module $PSScriptRoot\..\..\..\shared\config.psm1 -Force

uv run $PSScriptRoot\setup_test.py $Version $SgwVersion
if($LASTEXITCODE -ne 0) {
    throw "Setup failed!"
}

Push-Location $QE_TESTS_DIR
try {
    uv run pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json -m cbl
    $saved_exit = $LASTEXITCODE
} finally {
    Pop-Location
}

if($saved_exit -ne 0) {
    throw "Testing failed!"
}