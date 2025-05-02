param (
    [Parameter(Mandatory = $true)]
    [string]$src,

    [Parameter(Mandatory = $true)]
    [string]$dst
)

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$dst/3.2"
New-Item -ItemType Directory -Path "$dst/3.2" -Force
Copy-Item -Path "$src/blobs" -Destination "$dst/3.2" -Recurse
Copy-Item -Path "$src/dbs/3.2" -Destination "$dst/3.2/dbs" -Recurse

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$dst/4.0"
New-Item -ItemType Directory -Path "$dst/4.0" -Force
Copy-Item -Path "$src/blobs" -Destination "$dst/4.0" -Recurse
Copy-Item -Path "$src/dbs/4.0" -Destination "$dst/4.0/dbs" -Recurse

