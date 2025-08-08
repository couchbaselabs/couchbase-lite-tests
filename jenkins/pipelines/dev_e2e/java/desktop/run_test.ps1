param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter()][string]$PrivateKeyPath
)
$ErrorActionPreference = "Stop" 
Import-Module $PSScriptRoot\..\..\..\shared\config.psm1 -Force
$env:UV_PYTHON = "3.10"

$python_args = @($Version, $SgwVersion)
if ($null -ne $PrivateKeyPath) {
    $python_args += "--private_key"
    $python_args += $PrivateKeyPath
}

uv run --project $AWS_ENVIRONMENT_DIR/pyproject.toml $PSScriptRoot\setup_test.py @python_args
if($LASTEXITCODE -ne 0) {
    throw "Setup failed!"
}

Push-Location $DEV_E2E_TESTS_DIR
try {
    uv run pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json
    $saved_exit = $LASTEXITCODE
} finally {
    Pop-Location
}

if($saved_exit -ne 0) {
    throw "Testing failed!"
}