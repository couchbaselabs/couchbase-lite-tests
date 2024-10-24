param (
    [Parameter()]
    [string]
    $SgwUrl = ""
)

function Write-Banner {
    param (
        [Parameter(Mandatory=$true)]
        [string]
        $Text
    )
    Write-Host
    Write-Host -ForegroundColor Green "===== $Text ====="
    Write-Host
}

Write-Banner "Stopping existing environment"
Push-Location $PSScriptRoot\..\..\..\environment
docker compose down # Just in case it didn't get shut down cleanly

Write-Banner "Building Couchbase Server Image"
docker compose build cbl-test-cbs

Write-Banner "Building logslurp Image"
docker compose build cbl-test-logslurp

if($SgwUrl -ne "") {
    Write-Banner "Building Sync Gateway Image"
    docker compose build cbl-test-sg --build-arg SG_DEB="$SgwUrl"
}

Write-Banner "Starting Backend"
python start_environment.py
Pop-Location