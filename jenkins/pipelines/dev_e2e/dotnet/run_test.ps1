param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter()][string]$PrivateKeyPath
)

Import-Module $PSScriptRoot/../../shared/config.psm1 -Force
Import-Module $PSScriptRoot/prepare_env.psm1 -Force
$ErrorActionPreference = "Stop" 

Install-DotNet

Stop-Venv
New-Venv venv
. venv\Scripts\activate.ps1
trap { Stop-Venv; break }
uv pip install -r $AWS_ENVIRONMENT_DIR\requirements.txt
$python_args = @("windows", $Version, $SgwVersion)
if ($null -ne $PrivateKeyPath) {
    $python_args += "--private_key"
    $python_args += $PrivateKeyPath
}

python $PSScriptRoot\setup_test.py @python_args
if($LASTEXITCODE -ne 0) {
    throw "Setup failed!"
}

Push-Location $DEV_E2E_TESTS_DIR
try {
    uv pip install -r requirements.txt
    pytest -v --no-header --config config.json
    $saved_exit = $LASTEXITCODE
    deactivate
} finally {
    Pop-Location
}

# FIXME: Find another way to do this so this is not hardcoded here
taskkill /F /IM "testserver.cli.exe"
if($saved_exit -ne 0) {
    throw "Testing failed!"
}