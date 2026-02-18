param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter(Mandatory=$true)][string]$OutputDir
)

$ErrorActionPreference = "Stop"

Import-Module $PSScriptRoot\..\..\shared\config.psm1 -Force

Stop-Venv
New-Venv venv
.\venv\Scripts\activate
trap { Stop-Venv; break }

uv pip install -r $AWS_ENVIRONMENT_DIR\requirements.txt
python $PSScriptRoot\setup_test.py "windows" $Version $SgwVersion
if($LASTEXITCODE -ne 0) { throw "Setup failed!" }

if(-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

Push-Location $QE_TESTS_DIR
try {
    uv pip install -r requirements.txt
    pytest -v --no-header -W ignore::DeprecationWarning --config config.json -m cbl --junitxml="$OutputDir\results.xml"
    $saved_exit = $LASTEXITCODE

    if(Test-Path "session.log") {
        Copy-Item "session.log" "$OutputDir\session.log" -Force
    }

    if(Test-Path "http_log") {
        Copy-Item "http_log" "$OutputDir\http_log" -Recurse -Force
    }

    deactivate
} finally {
    Pop-Location
}

if($saved_exit -ne 0) { throw "Testing failed!" }
