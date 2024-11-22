param (
    [Parameter(Mandatory = $true)]
    [string]$version,

    [Parameter(Mandatory = $true)]
    [string]$buildNumber,

    [Parameter(Mandatory = $false)]
    [string]$sgUrl
)

$ErrorActionPreference = "Stop"
[System.Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Microsoft\jdk-17.0.13.11-hotspot")

$cblVersion = "${version}-${buildNumber}"

Write-Host "Windows Web Service: Shutdown the Test Server"
Push-Location servers\jak\webservice
& .\gradlew.bat --no-daemon appStop -PcblVersion="${cblVersion}"
Pop-Location

Write-Host "Windows Web Service: Shutdown the environment"
Push-Location environment
& docker compose down
