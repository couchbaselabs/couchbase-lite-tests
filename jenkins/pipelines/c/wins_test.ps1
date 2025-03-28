param(
    [Parameter(Mandatory=$true)][string]$Edition,
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$Build,
    [Parameter(Mandatory=$true)][string]$DatasetVersion,
    [Parameter(Mandatory=$true)][string]$SgwUrl
)

$TestServerDir = "$PSScriptRoot\..\..\..\servers\c"
$SharedDir="$PSScriptRoot\..\shared"
$TestsDir = "$PSScriptRoot\..\..\..\tests\dev_e2e"

Write-Host "Build Test Server"
Push-Location $TestServerDir
& .\scripts\build_wins.ps1 -Edition $Edition -Version $Version -Build $Build -DatasetVersion $DatasetVersion

$saved_exit = 0
try {
    # Run Test Server
    Write-Host "Run Test Server"
    Push-Location "$TestServerDir\build\out\bin"
    if (Test-Path "testserver.pid") {
        Remove-Item "testserver.pid"
    }
    $process = Start-Process -NoNewWindow -FilePath ".\testserver.exe" `
        -RedirectStandardOutput "testserver.log" `
        -RedirectStandardError "testserver.err" `
        -PassThru
    $process.Id | Out-File -FilePath "testserver.pid" -Force
    Pop-Location

    # Start environment
    Write-Host "Start environment"
    Push-Location $SharedDir
    .\setup_backend.ps1 -SgwUrl $SgwUrl
    Pop-Location

    # Run tests
    Write-Host "Run tests"
    Push-Location $TestsDir

    python -m venv venv
    .\venv\Scripts\activate
    pip install -r requirements.txt

    # Remove and copy the config.c.json file
    Remove-Item -Force "config.c.json" -ErrorAction Ignore
    Copy-Item "$PSScriptRoot\config.c.json" .

    # Run pytest
    pytest -v --no-header --config config.c.json
    $saved_exit = $LASTEXITCODE
    deactivate

    Pop-Location
} finally {
    # Stop test server
    Write-Host "Ensure the test server is stopped"
    Push-Location "$TestServerDir\build\out\bin"
    if (Test-Path "testserver.pid") {
        $ProcessID = Get-Content "testserver.pid"
        try {
            Stop-Process -Id $ProcessID -Force -ErrorAction Stop
            Write-Host "Test server stopped successfully."
        } catch {
            Write-Warning "Failed to stop test server with PID $ProcessID. It might already be stopped."
        }
        Remove-Item "testserver.pid" -Force
    } else {
        Write-Warning "testserver.pid file does not exist."
    }
    Pop-Location
}

# Throw error if tests failed
if ($saved_exit -ne 0) {
    throw "Testing failed!"
}