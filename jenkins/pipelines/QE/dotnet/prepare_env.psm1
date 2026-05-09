$env:DOTNET_SDK_VERSION = "10.0.2xx"
$env:DOTNET_RUNTIME_VERSION = "8.0"
$env:DOTNET_ROOT="$HOME/.dotnet10"

Invoke-WebRequest https://raw.githubusercontent.com/couchbaselabs/couchbase-mobile-tools/refs/heads/master/dotnet_testing_env/prepare_dotnet.psm1 -OutFile $PSScriptRoot/prepare_dotnet.psm1
Import-Module $PSScriptRoot/prepare_dotnet.psm1 -Force