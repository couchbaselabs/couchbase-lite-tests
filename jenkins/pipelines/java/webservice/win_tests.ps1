param (
    [Parameter(Mandatory=$true)]
    [string]$version,

    [Parameter(Mandatory=$true)]
    [string]$buildNumber

    [Parameter(Mandatory=$false)]
    [string]$sgUrl,
)

# Force the Couchbase Lite Java-ktx version
Push-Location servers\jak
"$version" | Out-File cbl-version.txt

Write-Host "Build and start the Java Webservice Test Server"
Set-Location webservice
& .\gradlew.bat --no-daemon appStop
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .\server.log, .\app\server.url
$temp = New-TemporaryFile
Start-Process .\gradlew.bat -ArgumentList "--no-daemon jettyStart -PbuildNumber=${buildNumber}" -RedirectStandardInput $temp -RedirectStandardOutput server.log -RedirectStandardError server.err -NoNewWindow
Pop-Location

Write-Host "Start Environment"
& .\jenkins\pipelines\shared\setup_backend.ps1 $sgUrl

Write-Host "Wait for the Test Server..."
$n = 0
$serverUrl = ""
$urlFile = .\servers\jak\webservice\app\server.url
while ($true) {
    if ($n -gt 30) {
        Write-Host "Cannot get server URL: Aborting"
        exit 5
    }
    $n++

    Start-Sleep -Seconds 1

    if (!(Test-Path $urlFile -ErrorAction SilentlyContinue)) {
       continue
    }

    $serverUrl = Get-Content $urlFile
    if ([string]::IsNullOrWhiteSpace($serverUrl)) {
       continue
    }

    break
}

Write-Host "Configure tests"
Copy-Item .\jenkins\pipelines\java\webservice\config_java_webservice.json -Destination tests
Push-Location tests
Add-Content config_java_webservice.json "    `"test-servers`": [`"$serverUrl`"]"
Add-Content config_java_webservice.json '}'
Get-Content config_java_webservice.json

Write-Host "Running tests on desktop test server at $SERVER_URL"
& python3.10 -m venv venv
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
.\venv\Scripts\activate.ps1
pip install -r requirements.txt

Write-Host "Run tests"
& pytest -v --no-header -W ignore::DeprecationWarning --config config_java_webservice.json

