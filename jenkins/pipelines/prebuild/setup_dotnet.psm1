Import-Module $PSScriptRoot/../dev_e2e/dotnet/prepare_env.psm1 -Force

Install-DotNet -Version $env:DOTNET_SDK_VERSION