param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion
)

$ErrorActionPreference = "Stop"

Import-Module $PSScriptRoot\..\..\shared\config.psm1 -Force
uv run $PSScriptRoot\setup_test.py "windows" $Version $SgwVersion
if($LASTEXITCODE -ne 0) {
    throw "Setup failed!"
}

Push-Location $QE_TESTS_DIR
uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json -m cbl
$saved_exit = $LASTEXITCODE
Pop-Location

if($saved_exit -ne 0) {
    throw "Testing failed!"
}
