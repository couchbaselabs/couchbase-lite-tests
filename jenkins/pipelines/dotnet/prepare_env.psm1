Write-Host "Hello Jenkins, can you hear me?!"

Invoke-WebRequest https://raw.githubusercontent.com/couchbaselabs/couchbase-mobile-tools/refs/heads/master/dotnet_testing_env/prepare_dotnet.psm1 -OutFile prepare_dotnet.psm1

Write-Host "You should have downloaded that..."

Import-Module $PSScriptRoot/prepare_dotnet.psm1 -Force

function Copy-Datasets {
    Banner -Text "Copying dataset resources"

    Push-Location $PSScriptRoot/../../../servers/dotnet/testserver/Resources/Raw
    Copy-Item -Force $PSScriptRoot/../../../dataset/server/dbs/*.zip . -Verbose
    Copy-Item -Recurse -Force $PSScriptRoot/../../../dataset/server/blobs . -Verbose
    Pop-Location
}