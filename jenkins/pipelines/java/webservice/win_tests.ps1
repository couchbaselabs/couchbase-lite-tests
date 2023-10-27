param (
    [Parameter(Mandatory=$true)]
    [string]$edition,

    [Parameter(Mandatory=$true)]
    [string]$version,

    [Parameter(Mandatory=$true)]
    [string]$buildNumber
)

# Force the Couchbase Lite Java-ktx version
Push-Location servers\jak
"$VERSION" | Out-File cbl-version.txt

Write-Host "Build and start the Java Webservice Test Server"
Set-Location webservice
& .\gradlew.bat --no-daemon appStop
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .\server.log, .\app\server.url
$temp = New-TemporaryFile
Start-Process .\gradlew.bat -ArgumentList "--no-daemon jettyStart -PbuildNumber=${buildNumber}" -RedirectStandardInput $temp -RedirectStandardOutput server.log -RedirectStandardError server.err -NoNewWindow
Pop-Location

Write-Host "Start Server & SG"
Push-Location environment
& .\start_environment.py

Write-Host "Wait for the Test Server..."
Pop-Location
$n = 0
$serverUrl = Get-Content .\servers\jak\webservice\app\server.url
while ([string]::IsNullOrWhiteSpace($serverUrl) {
    if ($n -gt 10) {
        Write-Host "Cannot get server URL: Aborting"
        exit 5
    }
    Start-Seep -Seconds 2
    $serverUrl = Get-Content .\servers\jak\webservice\app\server.url
    $n++
}

Write-Host "Configure tests"
Copy-Item .\jenkins\pipelines\java\webservice\config_java_webservice.json -Destination tests
Push-Location tests
Add-Content config.desktop_java.json "    `"test-servers`": [`"$serverUrl`"]"
Add-Content config.desktop_java.json '}'
Get-Content config.desktop_java.json

Write-Host "Running tests on desktop test server at $SERVER_URL"
& python3.10 -m venv venv
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
./venv/Scripts/activate.ps1
pip install -r requirements.txt

Write-Host "Run tests"
& pytest -v --no-header -W ignore::DeprecationWarning --config config_java_webservice.json

