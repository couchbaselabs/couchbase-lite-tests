param(
    [Parameter(Mandatory=$true, Position=0)][string]$DatasetVersion
)

$DatasetBaseDir = Join-Path $PSScriptRoot "..\..\..\dataset\server"
$DatasetDbsDir = Join-Path $DatasetBaseDir "dbs" 
$DatasetDbsDir = Join-Path $DatasetDbsDir $DatasetVersion
$DatasetBlobDir = Join-Path $DatasetBaseDir "blobs"
$AssetsDir = Join-Path $PSScriptRoot "..\assets"

# Change to the assets directory and clean up
Push-Location $AssetsDir

Remove-Item -Recurse -Force "dbs" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Name "dbs"

Remove-Item -Recurse -Force "blobs" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Name "blobs"

# Copy databases and blobs
Write-Host "Copying databases from $DatasetDbsDir"
Copy-Item -Force "$DatasetDbsDir\*" dbs -Verbose

Write-Host "Copying blobs from $DatasetBlobDir"
Copy-Item -Force "$DatasetBlobDir\*" blobs -Verbose

Pop-Location