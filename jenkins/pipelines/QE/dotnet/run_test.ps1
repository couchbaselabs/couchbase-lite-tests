param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion
)

Import-Module $PSScriptRoot/../../shared/config.psm1 -Force
Import-Module $PSScriptRoot/prepare_env.psm1 -Force
$ErrorActionPreference = "Stop"

Install-DotNet

uv run --group orchestrator $PSScriptRoot\setup_test.py "windows" $Version $SgwVersion
if($LASTEXITCODE -ne 0) {
    throw "Setup failed!"
}

Push-Location $QE_TESTS_DIR
uv run pytest -v --no-header --config config.json -m cbl
$saved_exit = $LASTEXITCODE
Pop-Location

# FIXME: Find another way to do this so this is not hardcoded here
taskkill /F /IM "testserver.cli.exe"
if($saved_exit -ne 0) {
    throw "Testing failed!"
}
