if (-not $env:TS_PLATFORM) {
    Write-Error "Error: TS_PLATFORM environment variable is not set."
    exit 1
}

Import-Module $PSScriptRoot/../shared/config.psm1 -Force
if ($env:TS_PLATFORM -like "dotnet*") {
    . "$PSScriptRoot\setup_dotnet.ps1"
}