param (
    [Parameter(Mandatory=$true)]
    [string]$edition,

    [Parameter(Mandatory=$true)]
    [string]$version,

    [Parameter(Mandatory=$true)]
    [string]$buildNumber
)

# Force the Couchbase Lite Java version
Push-Location servers\jak
"$version" | Out-File cbl-version.txt

Write-Host "Build Java Desktop Test Server"
Set-Location desktop
& .\gradlew.bat --no-daemon jar -PbuildNumber="${buildNumber}"

Write-Host "Start the Test Server"
if (Test-Path -Path .\server.pid){
    $serverId = Get-Content .\server.pid
    Stop-Process -Id $serverId
}
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue server.log, server.url, server.pid
$app = Start-Process java -ArgumentList "-jar .\app\build\libs\CBLTestServer-Java-Desktop-${version}-${buildNumber}.jar server" -PassThru -NoNewWindow -RedirectStandardOutput server.log  -RedirectStandardError server.err
$app.Id | Out-File server.pid
Pop-Location

Write-Host "Start Server & SG"
Push-Location environment
& .\start_environment.py

Pop-Location
Copy-Item .\jenkins\pipelines\java\desktop\config_java_desktop.json -Destination tests

Write-Host "Configure tests"
$serverUrl = Get-Content .\servers\jak\desktop\server.url
Push-Location tests
Add-Content config_java_desktop.json "    `"test-servers`": [`"$serverUrl`"]"
Add-Content config_java_desktop.json '}'
Get-Content config_java_desktop.json

Write-Host "Running tests on desktop test server at $SERVER_IP"
& python3.10 -m venv venv
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
./venv/Scripts/activate.ps1
pip install -r requirements.txt

Write-Host "Run tests"
& pytest -v --no-header -W ignore::DeprecationWarning --config config_java_desktop.json

