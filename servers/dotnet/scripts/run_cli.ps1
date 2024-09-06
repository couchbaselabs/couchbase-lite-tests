Import-Module $PSScriptRoot/prepare_env.psm1 -Force

$ServerExe = Get-ChildItem -Recurse -Path $PSScriptRoot\..\testserver.cli\bin\Release\ -Include testserver.cli.exe | Select-Object -First 1 -ExpandProperty FullName
if(-not ($ServerExe)) {
    Write-Error "Unable to find executable, please run dotnet publish first"
    exit 1
}

Banner -Text "Copying Datasets"

Push-Location $PSScriptRoot/../testserver.cli/Resources/
Copy-Item -Force $PSScriptRoot/../../../dataset/server/dbs/*.zip .
Copy-Item -Recurse -Force $PSScriptRoot/../../../dataset/server/blobs .
Pop-Location

Banner -Text "Launching $ServerExe..."
Start-Process $ServerExe