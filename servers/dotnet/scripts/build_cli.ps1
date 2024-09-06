Import-Module $PSScriptRoot/prepare_env.psm1 -Force

$DOTNET_VERSION = Get-DotnetVersion

Install-DotNet

Banner -Text "Copying Datasets"

Push-Location $PSScriptRoot/../testserver.cli/Resources/
Copy-Item -Force $PSScriptRoot/../../../dataset/server/dbs/*.zip .
Copy-Item -Recurse -Force $PSScriptRoot/../../../dataset/server/blobs .
Pop-Location

Banner -Text "Executing build for .NET $DOTNET_VERSION CLI"

# Build
Push-Location $PSScriptRoot\..\testserver.cli
& $env:LOCALAPPDATA\Microsoft\dotnet\dotnet publish .\testserver.cli.csproj -c Release -f net8.0
Pop-Location