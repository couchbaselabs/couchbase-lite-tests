param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter()][string]$DatasetVersion = "4.0",
    [Parameter()][string]$TestName = ""
)

$ErrorActionPreference = "Stop"

Import-Module $PSScriptRoot\..\..\shared\config.psm1 -Force

if ([string]::IsNullOrWhiteSpace($DatasetVersion)) { $DatasetVersion = "4.0" }
if ($TestName -eq "null") { $TestName = "" }

uv run $PSScriptRoot\setup_test.py "windows" $Version $SgwVersion
if($LASTEXITCODE -ne 0) {
    throw "Setup failed!"
}

Push-Location $QE_TESTS_DIR
try {
    $pytestArgs = @(
        "-v", "--no-header",
        "-W", "ignore::DeprecationWarning",
        "--config", "config.json",
        "--dataset-version", $DatasetVersion,
        "-m", "cbl"
    )

    if (-not [string]::IsNullOrWhiteSpace($TestName)) {
        if ($TestName -like "*.py*") {
            $pytestArgs += $TestName
        } else {
            $pytestArgs += @("-k", $TestName)
        }
    }

    Write-Host "pytest $($pytestArgs -join ' ')"
    uv run pytest @pytestArgs
    $saved_exit = $LASTEXITCODE
} finally {
    Pop-Location
}

if($saved_exit -eq 5) {
    Write-Host "ERROR: no tests collected. TestName='$TestName' matched nothing under -m cbl."
} elseif($saved_exit -eq 4) {
    Write-Host "ERROR: pytest usage error. Check the expression: '$TestName'"
}
if($saved_exit -ne 0) {
    throw "Testing failed!"
}