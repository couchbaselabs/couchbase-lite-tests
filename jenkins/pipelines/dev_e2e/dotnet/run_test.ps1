param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter()][string]$PrivateKeyPath
)

Import-Module $PSScriptRoot/../../shared/config.psm1 -Force
Import-Module $PSScriptRoot/prepare_env.psm1 -Force
$ErrorActionPreference = "Stop" 
$env:UV_PYTHON = "3.10"

Install-DotNet

$python_args = @("windows", $Version, $SgwVersion)
if ($null -ne $PrivateKeyPath) {
    $python_args += "--private_key"
    $python_args += $PrivateKeyPath
}

uv run --project $AWS_ENVIRONMENT_DIR/pyproject.toml python $PSScriptRoot\setup_test.py @python_args
if($LASTEXITCODE -ne 0) {
    throw "Setup failed!"
}

Push-Location $DEV_E2E_TESTS_DIR
try {
    uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json
    $saved_exit = $LASTEXITCODE
} finally {
    Pop-Location
}

# FIXME: Find another way to do this so this is not hardcoded here
taskkill /F /IM "testserver.cli.exe"
if($saved_exit -ne 0) {
    throw "Testing failed!"
}