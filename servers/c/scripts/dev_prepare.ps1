param(
    [Parameter(Mandatory=$true)][string]$Edition,
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$false)][string]$BuildNum
)

$DOWNLOAD_DIR="$PSScriptRoot\..\downloaded"
$ASSETS_DIR="$PSScriptRoot\..\assets"
$LIB_DIR="$PSScriptRoot\..\lib"

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
Remove-Item -Recurse -Force -ErrorAction Ignore "$LIB_DIR\libcblite"
Copy-Item -ErrorAction Ignore -Recurse libcblite-${Version} "$LIB_DIR\libcblite"
Pop-Location

Remove-Item -Recurse -Force -ErrorAction Ignore "$DOWNLOAD_DIR"