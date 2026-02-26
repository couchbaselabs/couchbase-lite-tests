param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter()][string]$DatasetVersion = "4.0"
)

Import-Module $PSScriptRoot/../../shared/config.psm1 -Force
Import-Module $PSScriptRoot/prepare_env.psm1 -Force
$ErrorActionPreference = "Stop"

Install-DotNet -Version "9.0"
Install-DotNetRuntime -Version "8.0"

uv run --group orchestrator $PSScriptRoot\setup_test.py "windows" $Version $SgwVersion
if($LASTEXITCODE -ne 0) {
    throw "Setup failed!"
}

Push-Location $DEV_E2E_TESTS_DIR
try {
    uv run pytest -v --no-header --config config.json --dataset-version $DatasetVersion
    $saved_exit = $LASTEXITCODE
} finally {
    Pop-Location
}

# FIXME: Find another way to do this so this is not hardcoded here
taskkill /F /IM "testserver.cli.exe"
if($saved_exit -ne 0) {
    throw "Testing failed!"
}
