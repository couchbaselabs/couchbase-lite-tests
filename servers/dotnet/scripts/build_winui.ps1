
# Copy dataset
Push-Location $PSScriptRoot\..\Resources\Raw
Copy-Item $PSScriptRoot\..\..\..\dataset\server\dbs\*.zip .
Copy-Item $PSScriptRoot\..\..\..\dataset\server\blobs . -Recurse
Pop-Location

# Build
dotnet publish .\testserver.csproj -c Release -f net7.0-windows10.0.19041.0