Import-Module $PSScriptRoot\prepare_env.psm1 -Force

$DOTNET_VERSION = Get-DotnetVersion

Banner -Text "Executing build for .NET $DOTNET_VERSION WinUI"

# Build
Push-Location $PSScriptRoot\..\..\..\servers\dotnet\testserver\
& $env:LOCALAPPDATA\Microsoft\dotnet\dotnet publish .\testserver.csproj -c Release -f net8.0-windows10.0.19041.0 -v n
Pop-Location