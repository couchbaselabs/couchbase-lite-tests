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
Start-Process .gradlew.bat -ArgumentList "jettyStart -PbuildNumber="${BUILD_NUMBER}" -NoNewWindow -RedirectStandardOutput server.log  -RedirectStandardError server.err
Pop-Location

Write-Host "Start Server & SG"
Push-Location environment
& .\start_environment.py

Pop-Location
Copy-Item .\jenkins\pipelines\java\webservice\config_java_webservice.json -Destination tests

Write-Host "Configure tests"
$serverUrl = Get-Content .\servers\jak\webservice\app\server.url
Push-Location tests
Add-Content config.desktop_java.json "    `"test-servers`": [`"$serverUrl`"]"
Add-Content config.desktop_java.json '}'
Get-Content config.desktop_java.json

Write-Host "Running tests on desktop test server at $SERVER_IP"
& python3.10 -m venv venv
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
./venv/Scripts/activate.ps1
pip install -r requirements.txt

Write-Host "Run tests"
& pytest -v --no-header -W ignore::DeprecationWarning --config config_java_webservice.json

