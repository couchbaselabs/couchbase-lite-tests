param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion
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

Push-Location $QE_TESTS_DIR
try {
    if ($null -eq $env:TS_ARTIFACTS_DIR -or $env:TS_ARTIFACTS_DIR -eq "") {
        throw "TS_ARTIFACTS_DIR environment variable is not set!"
    }

    $artifactDir = Join-Path -Path $QE_TESTS_DIR -ChildPath $env:TS_ARTIFACTS_DIR
    if (-not (Test-Path $artifactDir)) {
        New-Item -ItemType Directory -Path $artifactDir | Out-Null
    }

    uv pip install -r requirements.txt
    pytest -v --no-header -W ignore::DeprecationWarning --config config.json -m cbl --junitxml="$artifactDir\results.xml"
    $saved_exit = $LASTEXITCODE

    deactivate
} finally {
    Pop-Location
}

if($saved_exit -ne 0) { throw "Testing failed!" }
