param (
    [Parameter(Mandatory = $true)]
    [string]$version,

    [Parameter(Mandatory = $true)]
    [string]$buildNumber,

    [Parameter(Mandatory = $true)]
    [string]$datasetVersion,

    [Parameter(Mandatory = $false)]
    [string]$sgUrl
)

$ErrorActionPreference = "Stop"
[System.Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Microsoft\jdk-17.0.13.11-hotspot")

$status = 1
$cblVersion = "${version}-${buildNumber}"

Push-Location servers\jak
& .\etc\jenkins\copy_assets.ps1 ..\..\dataset\server assets
$serverVersion = Get-Content version.txt

Set-Location desktop

Write-Host "Windows Desktop: Stop any existing Test Server"
if (Test-Path -Path .\server.pid)
{
    $serverId = Get-Content .\server.pid
    Stop-Process -Id $serverId -Force -ErrorAction SilentlyContinue
}

Write-Host "Windows Desktop: Build the Test Server"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue app\build
& .\gradlew.bat --no-daemon jar -PcblVersion="${cblVersion}" -PdatasetVersion="${datasetVersion}"

try
{
    Write-Host "Windows Desktop: Start the Test Server"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue server.log, server.url, server.pid
    $app = Start-Process java -ArgumentList "-jar app\build\libs\CBLTestServer-Java-Desktop-${serverVersion}_${cblVersion}.jar server" -PassThru -NoNewWindow -RedirectStandardOutput server.log  -RedirectStandardError server.err
    $app.Id | Out-File server.pid
    Write-Host "Windows Desktop: Server started: $($app.ProcessName), $($app.Id)"
    Pop-Location

    Write-Host "Windows Desktop: Start the environment"
    & .\jenkins\pipelines\shared\setup_backend.ps1 "$sgUrl"

    Write-Host "Windows Desktop: Wait for the Test Server..."
    $urlFile = "servers\jak\desktop\server.url"
    $serverUrl = ""
    $n = 0
    while ($true)
    {
        if ($n -gt 30)
        {
            Write-Host "Cannot get server URL: Aborting"
            exit 5
        }
        $n++

        Start-Sleep -Seconds 1

        if (!(Test-Path $urlFile -ErrorAction SilentlyContinue))
        {
            continue
        }

        $serverUrl = Get-Content $urlFile
        if ( [string]::IsNullOrWhiteSpace($serverUrl))
        {
            continue
        }

        break
    }

    Write-Host "Windows Desktop: Configure the tests"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue tests\config_java_desktop.json
    Copy-Item .\jenkins\pipelines\java\desktop\config_java_desktop.json -Destination tests
    Push-Location tests
    Add-Content config_java_desktop.json "    `"test-servers`": [`"$serverUrl`"]"
    Add-Content config_java_desktop.json '}'
    Get-Content config_java_desktop.json

    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue venv, http_log, testserver.log
    & python3.10 -m venv venv
    Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
    .\venv\Scripts\activate.ps1
    pip install -r requirements.txt

    Write-Host "Windows Desktop: Run the tests"
    & pytest --maxfail=7 -W ignore::DeprecationWarning --config config_java_desktop.json
    $status = $LASTEXITCODE

    deactivate
    Write-Host "Windows Desktop: Tests complete"
}

# Shutdown the server
# When run from the Jenkins pipeline, his script will not exit
# if the server is still running
finally
{
    Write-Host "Windows Desktop: Cleaning up ($status)"

    Pop-Location
    Set-Location servers\jak\desktop

    if (Test-Path -Path .\server.pid)
    {
        $serverId = Get-Content .\server.pid
        Write-Host "Windows Desktop: Stopping server $serverId"
        Stop-Process -Id $serverId -Force -ErrorAction SilentlyContinue
        Remove-Item server.pid
    }

    Write-Host "Windows Desktop: Exiting"
    Exit $status
}
