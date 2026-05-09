Import-Module $PSScriptRoot/prepare_env.psm1 -Force

Install-DotNet -Version $env:DOTNET_SDK_VERSION