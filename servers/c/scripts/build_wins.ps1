param(
    [Parameter(Mandatory=$true)][string]$Edition,
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$false)][string]$BuildNum = ""
)

$DOWNLOAD_DIR="$PSScriptRoot\..\downloaded"
$BUILD_DIR="$PSScriptRoot\..\build"
$LIB_DIR="$PSScriptRoot\..\lib"

# Download CBL
if ($BuildNum -eq "") {
    & $PSScriptRoot\download_cbl.ps1 $Edition $Version
} else {
    & $PSScriptRoot\download_cbl.ps1 $Edition $Version $BuildNum
}

# Build
New-Item -ErrorAction Ignore -ItemType Directory $BUILD_DIR
Push-Location $BUILD_DIR
try {
    & "C:\Program Files\CMake\bin\cmake.exe" -A x64 -DCMAKE_PREFIX_PATH="${DOWNLOAD_DIR}/libcblite-${Version}" -DCMAKE_BUILD_TYPE=Release ..
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