param(
    [Parameter(Mandatory=$true)][string]$Edition,
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$BuildNum
)

$DOWNLOAD_DIR="$PSScriptRoot\..\downloaded"
$LIB_DIR="$PSScriptRoot\..\lib"

# Download and Unzip CBL
Remove-Item -Recurse -Force -ErrorAction Ignore $DOWNLOAD_DIR
New-Item -ItemType Directory $DOWNLOAD_DIR

if ($BuildNum -eq "0") {
    $ZIP_FILENAME="couchbase-lite-c-$Edition-$Version-windows-x86_64.zip"
    Invoke-WebRequest https://packages.couchbase.com/releases/couchbase-lite-c/${Version}/${ZIP_FILENAME} -OutFile "$DOWNLOAD_DIR\$ZIP_FILENAME"
} else {
    $ZIP_FILENAME="couchbase-lite-c-$Edition-$Version-$BuildNum-windows-x86_64.zip"
    Invoke-WebRequest http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-c/${Version}/${BuildNum}/${ZIP_FILENAME} -OutFile "$DOWNLOAD_DIR\$ZIP_FILENAME"
}

Push-Location $DOWNLOAD_DIR
Remove-Item -Recurse -Force -ErrorAction Ignore "$LIB_DIR\libcblite"
Expand-Archive -Path "$DOWNLOAD_DIR\$ZIP_FILENAME" -DestinationPath "$LIB_DIR" -Force
Rename-Item -Path "$LIB_DIR\libcblite-${Version}" -NewName "libcblite"
Pop-Location

Remove-Item -Recurse -Force -ErrorAction Ignore "$DOWNLOAD_DIR"