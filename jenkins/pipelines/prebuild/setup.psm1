if (-not $env:TS_PLATFORM) {
    Write-Error "Error: TS_PLATFORM environment variable is not set."
    exit 1
}

Import-Module $PSScriptRoot/../shared/config.psm1 -Force
if ($env:TS_PLATFORM -like "dotnet*") {
    Import-Module "$PSScriptRoot\setup_dotnet.psm1" -Force
}
