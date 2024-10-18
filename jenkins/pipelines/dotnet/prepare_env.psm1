Invoke-WebRequest https://raw.githubusercontent.com/couchbaselabs/couchbase-mobile-tools/refs/heads/master/dotnet_testing_env/prepare_dotnet.psm1 -OutFile prepare_dotnet.psm1
Import-Module $PSScriptRoot/prepare_dotnet.psm1 -Force

function Copy-Datasets {
    Banner -Text "Copying dataset resources"

    New-Item -ItemType Directory -Path $PSScriptRoot/../testserver/Resources/Raw -ErrorAction Ignore
    Push-Location $PSScriptRoot/../testserver/Resources/Raw
    Copy-Item -Force $PSScriptRoot/../../../dataset/server/dbs/*.zip .
    Copy-Item -Recurse -Force $PSScriptRoot/../../../dataset/server/blobs .
    Pop-Location
}