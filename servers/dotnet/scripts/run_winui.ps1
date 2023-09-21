Write-Host "Removing existing package..."
powershell -Command "Get-AppxPackage bf1b9964-631c-4489-91fa-a04e7f3f3765* | Remove-AppxPackage"

$InstallScript = Get-ChildItem -Recurse -Path .\bin\Release\ -Include Install.ps1 | Select-Object -First 1 -ExpandProperty FullName
if(-not ($InstallScript)) {
    Write-Error "Unable to find install script, please run dotnet publish first"
    exit 1
}

Write-Host "Found $InstallScript, running..."
powershell $InstallScript -Force

Invoke-Expression "start shell:AppsFolder\bf1b9964-631c-4489-91fa-a04e7f3f3765_nw4t8ysxwwgx8!App"