param (
    [Parameter(Mandatory = $true)]
    [string]$version,

    [Parameter(Mandatory = $true)]
    [string]$buildNumber,

    [Parameter(Mandatory = $false)]
    [string]$sgUrl
)

$ErrorActionPreference = "Stop"

# Force the Couchbase Lite Java version
Push-Location servers\jak
"$version" | Out-File cbl-version.txt

Write-Host "Windows Desktop: Build the Test Server"
Set-Location desktop
& .\gradlew.bat --no-daemon jar -PbuildNumber="${buildNumber}"

Write-Host "Windows Desktop: Start the Test Server"
if (Test-Path -Path .\server.pid)
{
    $serverId = Get-Content .\server.pid
    Stop-Process -Id $serverId -ErrorAction SilentlyContinue
}
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue server.log, server.url, server.pid
$app = Start-Process java -ArgumentList "-jar app\build\libs\CBLTestServer-Java-Desktop-${version}-${buildNumber}.jar server" -PassThru -NoNewWindow -RedirectStandardOutput server.log  -RedirectStandardError server.err
$app.Id | Out-File server.pid

try
{
    Pop-Location

    Write-Host "Windows Desktop: Start the environment"
    & .\jenkins\pipelines\shared\setup_backend.ps1 $sgUrl

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
    Remove-Item -ErrorAction SilentlyContinue tests\config_java_desktop.json
    Copy-Item .\jenkins\pipelines\java\desktop\config_java_desktop.json -Destination tests
    Push-Location tests
    Add-Content config_java_desktop.json "    `"test-servers`": [`"$serverUrl`"]"
    Add-Content config_java_desktop.json '}'
    Get-Content config_java_desktop.json

    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue venv
    & python3.10 -m venv venv
    Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
    .\venv\Scripts\activate.ps1
    pip install -r requirements.txt

    Write-Host "Windows Desktop: Run the tests"
    & pytest --maxfail=7 -W ignore::DeprecationWarning --config config_java_desktop.json

    Write-Host "Windows Desktop: Tests complete!"
    deactivate
}

# Shutdown any child processes
# If any remain, this script will not exit when run from the Jenkins pipeline
finally
{
    $childProcesses = Get-Process | Where-Object {$_.Parent.Id -eq $PID}
    Write-Host "Windows Desktop: Killing child processes $childProcesses"
    $childProcesses | Stop-Process -Force

    Write-Host "Windows Desktop: Exiting"
    Exit
}

