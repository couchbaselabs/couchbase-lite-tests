param(
    [Parameter(Mandatory=$true)][string]$Edition,
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$Build,
    [Parameter(Mandatory=$true)][string]$DatasetVersion
)

$DOWNLOAD_DIR="$PSScriptRoot\..\downloaded"
$BUILD_DIR="$PSScriptRoot\..\build"
$LIB_DIR="$PSScriptRoot\..\lib"

# Prepare Environment:
& $PSScriptRoot\prepare_env.ps1 $DatasetVersion

# Download CBL
& $PSScriptRoot\download_cbl.ps1 $Edition $Version $Build

# Build
New-Item -ErrorAction Ignore -ItemType Directory $BUILD_DIR
Push-Location $BUILD_DIR
try {
    & "C:\Program Files\CMake\bin\cmake.exe" -G "Visual Studio 17 2022" -A x64 -DCMAKE_PREFIX_PATH="${DOWNLOAD_DIR}/libcblite-${Version}" -DCMAKE_BUILD_TYPE=Release ..
    if($LASTEXITCODE -ne 0) {
        throw "Cmake failed!"
    } 

    & "C:\Program Files\CMake\bin\cmake.exe" --build . --target install --config Release --parallel 12
    if($LASTEXITCODE -ne 0) {
        throw "Build failed!"
    } 

    # Copy libcblite
    Copy-Item "$LIB_DIR\libcblite\bin\cblite.dll" out\bin

    # Copy assets
    Copy-Item -ErrorAction Ignore -Recurse assets out\bin
} finally {
    Pop-Location
}