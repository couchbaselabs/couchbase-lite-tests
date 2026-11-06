param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$SgwVersion,
    [Parameter()][string]$DatasetVersion = "4.0",
    [Parameter()][string]$TestFilter = "",
    [Parameter()][switch]$SetupOnly
)

Import-Module $PSScriptRoot/../../shared/config.psm1 -Force
$ErrorActionPreference = "Stop"

uv run dotnetenv install "10.0"

uv run $PSScriptRoot\setup_test.py "windows" $Version $SgwVersion
if($LASTEXITCODE -ne 0) {
    throw "Setup failed!"
}

if ($SetupOnly) {
    Write-Host "Setup completed. Exiting due to -SetupOnly flag."
    exit 0
}

# Every test that needs a test server. Tests whose other min_* markers this
# topology can't satisfy are skipped by the required_topology plugin.
$pytestArgs = @('-v', '--no-header', '--config', 'config.json', '--dataset-version', $DatasetVersion, '-m', 'min_test_servers')
if ($TestFilter) {
    $pytestArgs += @('-k', $TestFilter, '--no-result-upload')
}

Push-Location $FUNCTIONAL_TESTS_DIR
try {
    uv run pytest @pytestArgs
    $saved_exit = $LASTEXITCODE
} finally {
    Pop-Location
}

# FIXME: Find another way to do this so this is not hardcoded here
taskkill /F /IM "testserver.cli.exe"
if($saved_exit -ne 0) {
    throw "Testing failed!"
}
