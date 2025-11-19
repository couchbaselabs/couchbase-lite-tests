param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion
)
$ErrorActionPreference = "Stop"  
Import-Module $PSScriptRoot\..\..\..\shared\config.psm1 -Force

Stop-Venv
New-Venv venv
.\venv\Scripts\activate
trap { Stop-Venv; break }
uv pip install -r $AWS_ENVIRONMENT_DIR\requirements.txt
python $PSScriptRoot\setup_test.py $Version $SgwVersion

Push-Location $QE_TESTS_DIR
try {
    uv pip install -r requirements.txt
    pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json -m cbl
    $saved_exit = $LASTEXITCODE
    deactivate
} finally {
    Pop-Location
}

if($saved_exit -ne 0) {
    throw "Testing failed!"
}