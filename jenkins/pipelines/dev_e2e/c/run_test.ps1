param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$DatasetVersion,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter()][string]$PrivateKeyPath
)

$ErrorActionPreference = "Stop" 

Import-Module $PSScriptRoot\..\..\shared\config.psm1 -Force

Stop-Venv
New-Venv venv
.\venv\Scripts\activate
trap { Stop-Venv; break }
uv pip install -r $AWS_ENVIRONMENT_DIR\requirements.txt
$python_args = @("windows", $Version, $DatasetVersion, $SgwVersion)
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
    pytest -v --no-header -W ignore::DeprecationWarning --config config.json
    $saved_exit = $LASTEXITCODE
    deactivate
} finally {
    Pop-Location
}

if($saved_exit -ne 0) {
    throw "Testing failed!"
}