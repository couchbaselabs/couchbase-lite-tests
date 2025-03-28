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

Set-Location webservice

Write-Host "Windows Web Service: Stop any existing Test Server"
& .\gradlew.bat --no-daemon appStop -PcblVersion="${cblVersion}" -PdatasetVersion="${datasetVersion}"

try
{
    $temp = New-TemporaryFile
    Write-Host "Windows Web Service: Build and start the Test Server"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue app\build, server.log, app\server.url
    $app = Start-Process .\gradlew.bat -ArgumentList "--no-daemon jettyStart -PcblVersion=${cblVersion} -PdatasetVersion=${DATASET_VERSION}" -PassThru -WindowStyle Hidden -RedirectStandardInput $temp -RedirectStandardOutput server.log -RedirectStandardError server.err
    Write-Host "Windows Web Service: Server started: $($app.ProcessName), $($app.Id)"
    Pop-Location

    Write-Host "Windows Web Service: Start the environment"
    & .\jenkins\pipelines\shared\setup_backend.ps1 "$sgUrl"

    Write-Host "Windows Web Service: Wait for the Test Server..."
    $urlFile = "servers\jak\webservice\app\server.url"
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

    Write-Host "Windows Web Service: Configure the tests"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue tests\dev_e2e\config_java_webservice.json
    Copy-Item jenkins\pipelines\java\webservice\config_java_webservice.json -Destination tests
    Push-Location tests\dev_e2e
    Add-Content config_java_webservice.json "    `"test-servers`": [`"$serverUrl`"]"
    Add-Content config_java_webservice.json '}'
    Get-Content config_java_webservice.json

    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue venv, http_log, testserver.log
    & python3.10 -m venv venv
    Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
    .\venv\Scripts\activate.ps1
    pip install -r requirements.txt

    Write-Host "Windows Web Service: Run the tests"
    & pytest --maxfail=7 -W ignore::DeprecationWarning --config config_java_webservice.json
    $status = $LASTEXITCODE

    deactivate
    Write-Host "Windows Web Service: Tests complete"
}

# Shutdown the server
# When run from the Jenkins pipeline, his script will not exit
# if the server is still running
finally
{
    Write-Host "Windows Web Service: Cleaning up ($status)"

    Pop-Location
    Set-Location servers\jak\webservice

    if ( $null -ne $app )
    {
        Write-Host "Windows Web Service: Stopping process tree $($app.ProcessName), $($app.Id)"
        taskkill.exe /f /t /PID $($app.Id)
    }

    Write-Host "Windows Web Service: Exiting"
    Exit $status
}
