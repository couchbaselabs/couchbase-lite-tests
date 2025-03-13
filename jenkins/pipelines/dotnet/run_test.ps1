param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$Dataset,
    [Parameter(Mandatory=$true)][string]$SgwUrl,
    [Parameter()][string]$PrivateKeyPath
)

Import-Module $PSScriptRoot/prepare_env.psm1 -Force
$ErrorActionPreference = "Stop" 

#Install-DotNet
#Install-Maui
#Copy-Datasets -Version $Dataset

python -m venv venv
.\venv\Scripts\activate
pip install -r $PSScriptRoot\..\..\..\environment\aws\requirements.txt
$python_args = @("windows", $Version, $SgwUrl)
if ($null -ne $PrivateKeyPath) {
    $python_args += "--private_key"
    $python_args += $PrivateKeyPath
}

python .\setup_test.py @python_args

Push-Location $PSScriptRoot\..\..\..\tests
pip install -r requirements.txt
pytest -v --no-header --config config.json
$saved_exit = $LASTEXITCODE
deactivate
Pop-Location

if($saved_exit -ne 0) {
    throw "Testing failed!"
}