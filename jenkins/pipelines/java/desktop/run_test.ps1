param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$DatasetVersion,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter()][string]$PrivateKeyPath
)
$ErrorActionPreference = "Stop" 

python -m venv venv
.\venv\Scripts\activate
pip install -r $PSScriptRoot\..\..\..\environment\aws\requirements.txt
$python_args = @("windows", $Version, $DatasetVersion, $SgwVersion)
if ($null -ne $PrivateKeyPath) {
    $python_args += "--private_key"
    $python_args += $PrivateKeyPath
}

python $PSScriptRoot\setup_test.py @python_args

Push-Location $PSScriptRoot\..\..\..\tests\dev_e2e
pip install -r requirements.txt
pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json
$saved_exit = $LASTEXITCODE
deactivate
Pop-Location

if($saved_exit -ne 0) {
    throw "Testing failed!"
}