param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$DatasetVersion,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter()][string]$PrivateKeyPath
)
$ErrorActionPreference = "Stop"  
Import-Module $PSScriptRoot\..\..\..\shared\config.psm1 -Force

python -m venv venv
.\venv\Scripts\activate
pip install -r $AWS_ENVIRONMENT_DIR\requirements.txt
$python_args = @($Version, $DatasetVersion, $SgwVersion)
if ($null -ne $PrivateKeyPath) {
    $python_args += "--private_key"
    $python_args += $PrivateKeyPath
}

python $PSScriptRoot\setup_test.py @python_args

Push-Location $DEV_E2E_TESTS_DIR
pip install -r requirements.txt
pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json
$saved_exit = $LASTEXITCODE
deactivate
Pop-Location

if($saved_exit -ne 0) {
    throw "Testing failed!"
}