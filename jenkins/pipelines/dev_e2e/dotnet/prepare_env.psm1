$env:DOTNET_ROOT="$HOME/.dotnet8"
$env:DOTNET_SDK_VERSION="8.0.4xx"

Invoke-WebRequest https://raw.githubusercontent.com/couchbaselabs/couchbase-mobile-tools/refs/heads/master/dotnet_testing_env/prepare_dotnet.psm1 -OutFile $PSScriptRoot/prepare_dotnet.psm1
Import-Module $PSScriptRoot/prepare_dotnet.psm1 -Force