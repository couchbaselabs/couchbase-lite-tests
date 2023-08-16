param(
    [Parameter(Mandatory=$true)][string]$Editionm,
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$false)][string]$BuildNum
)

$DOWNLOAD_DIR="$PSScriptRoot\..\downloaded"
$ASSETS_DIR="$PSScriptRoot\..\assets"
$BUILD_DIR="$PSScriptRoot\..\build"

# Copy Assets
Push-Location $ASSETS_DIR
Copy-Item -ErrorAction Ignore $PSScriptRoot\..\..\..\dataset\*.cblite2.zip dataset
Copy-Item -ErrorAction Ignore $PSScriptRoot\..\..\..\environment\sg\cert\cert.* cert
Pop-Location

# Download and Unzip CBL
Remove-Item -Recurse -Force -ErrorAction Ignore $DOWNLOAD_DIR
New-Item -ItemType Directory $DOWNLOAD_DIR

if ($BuildNum -eq $null) {
    $ZIP_FILENAME="couchbase-lite-c-$Edition-$Version-$BuildNum-windows-x86_64.zip"
    Invoke-WebRequest http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-c/${Version}/${BuildNum}/${ZIP_FILENAME} -OutFile "$DOWNLOAD_DIR\$ZIP_FILENAME"
    
} else {
    $ZIP_FILENAME="couchbase-lite-c-$Edition-$Version-windows-x86_64.zip"
    Invoke-WebRequest https://packages.couchbase.com/releases/couchbase-lite-c/${Version}/${ZIP_FILENAME} -OutFile "$DOWNLOAD_DIR\$ZIP_FILENAME"
}

Push-Location $DOWNLOAD_DIR
7z x -y $ZIP_FILENAME
Remove-Item $ZIP_FILENAME
Pop-Location

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
    Copy-Item "$DOWNLOAD_DIR\libcblite-$VERSION\bin\cblite.dll" out\bin

    # Copy assets
    Copy-Item -ErrorAction Ignore assets out\bin
} finally {
    Pop-Location
}