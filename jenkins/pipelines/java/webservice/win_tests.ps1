param (
    [Parameter(Mandatory = $true)]
    [string]$version,

    [Parameter(Mandatory = $true)]
    [string]$buildNumber,

    [Parameter(Mandatory = $false)]
    [string]$sgUrl
)

$ErrorActionPreference = "Stop"
$status = 0

# Force the Couchbase Lite Java version
Push-Location servers\jak
"$version" | Out-File cbl-version.txt

Write-Host "Windows Web Service: Build and start the Test Server"
Set-Location webservice
& .\gradlew.bat --no-daemon appStop
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue server.log, app\server.url
$temp = New-TemporaryFile
# I dunno.  This seems to prevent a hang at the end of this script...
"" > $temp
"" >> $temp
"" >> $temp
"" >> $temp
Start-Process .\gradlew.bat -ArgumentList "--no-daemon jettyStart -PbuildNumber=${buildNumber}" -WindowStyle Hidden -RedirectStandardInput $temp -RedirectStandardOutput server.log -RedirectStandardError server.err

try
{
    Pop-Location

    Write-Host "Windows Web Service: Start the environment"
    & .\jenkins\pipelines\shared\setup_backend.ps1 $sgUrl

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
    Remove-Item -ErrorAction SilentlyContinue tests\config_java_webservice.json
    Copy-Item jenkins\pipelines\java\webservice\config_java_webservice.json -Destination tests
    Push-Location tests
    Add-Content config_java_webservice.json "    `"test-servers`": [`"$serverUrl`"]"
    Add-Content config_java_webservice.json '}'
    Get-Content config_java_webservice.json

    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue venv
    & python3.10 -m venv venv
    Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
    .\venv\Scripts\activate.ps1
    pip install -r requirements.txt

    Write-Host "Windows Web Service: Run the tests"
    & pytest --maxfail=7 -W ignore::DeprecationWarning --config config_java_webservice.json
    $status = $LASTEXITCODE

    Write-Host "Windows Web Service: Tests complete!"
    deactivate
}

# Shutdown any child processes
# If any remain, this script will not exit when run from the Jenkins pipeline
finally
{
    $childProcesses = Get-Process | Where-Object {$_.Parent.Id -eq $PID}
    Write-Host "Windows Web Service: Killing child processes $childProcesses"
    $childProcesses | Stop-Process -Force

    Write-Host "Windows Web Service: Exiting"
    Exit $status
}

