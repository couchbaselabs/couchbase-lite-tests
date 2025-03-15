Invoke-WebRequest https://raw.githubusercontent.com/couchbaselabs/couchbase-mobile-tools/refs/heads/master/dotnet_testing_env/prepare_dotnet.psm1 -OutFile $PSScriptRoot/prepare_dotnet.psm1
Import-Module $PSScriptRoot/prepare_dotnet.psm1 -Force

function Copy-Datasets {
    param (
        [Parameter(Mandatory=$true)][string]$Version
    )
    Banner -Text "Copying dataset resources v$Version"

    Push-Location $PSScriptRoot/../../../servers/dotnet/testserver.cli
    Copy-Item -Force $PSScriptRoot/../../../dataset/server/dbs/$Version/*.zip . -Verbose
    Copy-Item -Recurse -Force $PSScriptRoot/../../../dataset/server/blobs . -Verbose
    Pop-Location
}