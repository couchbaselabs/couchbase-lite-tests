param (
    [Parameter(Mandatory=$true)]
    [string]$edition,

    [Parameter(Mandatory=$true)]
    [string]$version,

    [Parameter(Mandatory=$true)]
    [string]$buildNumber
)

# Force the Couchbase Lite Java-ktx version
Push-Location servers/jak
"$VERSION" | Out-File cbl-version.txt

Write-Host "Build Java Desktop Test Server"
Set-Location desktop
Start-Process '.\gradlew.bat --no-daemon jar -PbuildNumber="${BUILD_NUMBER}"' -Wait

Write-Host "Start the Test Server"
Start-Process 'java -jar ./app/build/libs/CBLTestServer-Java-Desktop-3.2.0-SNAPSHOT.jar' > log.txt
Pop-Location

Write-Host "Start Server/SGW"
Push-Location environment
Start-Process '.\start_environment.py' -Wait

Pop-Location
Copy-Item "jenkins\pipelines\java\config.desktop_java.json" -Destination tests

Write-Host "Configure tests"
$SERVER_IP = & "perl -ne'next unless /IP\s+Address:\s+(\d{1,3}(\.\d{1,3}){3})/; print qq{$1}' < servers/jak/desktop/log.txt"
Push-Location tests
Add-Content config.desktop_java.json '    "test-servers": ["http://'"$SERVER_IP"':8080"]'
Add-Content config.desktop_java.json '}'
Get-Content config.desktop_java.json

Write-Host "Running tests on desktop test server at $SERVER_IP"
Start-Process 'python3.10 -m venv venv'  -Wait
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
. .\venv\bin\Activate.ps1
pip install -r requirements.txt

Write-Host "Run tests"
Start-Process '.\pytest -v --no-header -W ignore::DeprecationWarning --config config.desktop_java.json' -Wait

