Import-Module $PSScriptRoot/prepare_env.psm1 -Force

$ServerExe = Get-ChildItem -Recurse -Path $PSScriptRoot\..\testserver.cli\bin\Release\ -Include testserver.cli.exe | Select-Object -First 1 -ExpandProperty FullName
if(-not ($ServerExe)) {
    Write-Error "Unable to find executable, please run dotnet publish first"
    exit 1
}

Banner -Text "Launching $ServerExe..."
Start-Process $ServerExe