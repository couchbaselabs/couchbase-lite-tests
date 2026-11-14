# This script should be imported at the beginning of testing and teardown scripts

function Install-Uv {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "Installing uv..."
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    }
}

function Move-Artifacts {
    if($null -eq $env:TS_ARTIFACTS_DIR) {
        Write-Host "Warning: TS_ARTIFACTS_DIR environment variable is not set. Artifacts will not be moved."
        return
    }

    # Artifacts are written to the directory pytest ran from (the functional suite).
    $SRC_DIR = (Resolve-Path $PSScriptRoot\..\..\..\tests\functional).Path

    $DST_DIR = "$SRC_DIR\$env:TS_ARTIFACTS_DIR"
    if (-not (Test-Path -Path $DST_DIR)) {
        New-Item -ItemType Directory -Path $DST_DIR | Out-Null
    }

    Write-Host "Moving artifacts to $DST_DIR"

    # The workspace can persist between builds, so drop an earlier build's session log first
    Remove-Item "$DST_DIR\session.log*" -Force -ErrorAction SilentlyContinue
    if (Test-Path "$SRC_DIR\session.log") {
        Move-Item -Path "$SRC_DIR\session.log" -Destination "$DST_DIR\session.log" -Force
        # session.log is the full LogSlurp aggregate and can reach ~200 MB: gzip it, as config.sh
        # does. This must never stop the teardown, so keep the raw log if it fails.
        try {
            $in = [System.IO.File]::OpenRead("$DST_DIR\session.log")
            try {
                $out = [System.IO.Compression.GZipStream]::new(
                    [System.IO.File]::Create("$DST_DIR\session.log.gz"),
                    [System.IO.Compression.CompressionMode]::Compress)
                try { $in.CopyTo($out) } finally { $out.Dispose() }
            } finally {
                $in.Dispose()
            }
            Remove-Item "$DST_DIR\session.log"
        } catch {
            Write-Host "Warning: failed to gzip session.log; leaving it uncompressed: $_"
            Remove-Item "$DST_DIR\session.log.gz" -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path "$SRC_DIR\http_log") {
        Move-Item -Path "$SRC_DIR\http_log" -Destination "$DST_DIR\http_log" -Force
    }

    # SGW diagnostics downloaded by run_sgcollects() (via --sgcollect-on-test-failure) into
    # the test dir when a test fails; moving them here gets them archived (and later purged)
    # by Jenkins retention. Files are named "<safe_host>-sgcollectinfo-*.zip" (see
    # SyncGateway.run_sgcollect() in cbltest). Purge zips left by earlier builds first -- the
    # workspace persists and zips have unique names, so they'd accumulate into every build's
    # archive. Mirrors config.sh's Bash implementation.
    Get-ChildItem -Path $DST_DIR -Filter "*-sgcollectinfo-*.zip" -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem -Path $SRC_DIR -Filter "*-sgcollectinfo-*.zip" -ErrorAction SilentlyContinue |
        Move-Item -Destination $DST_DIR -Force

    # CBS diagnostics downloaded by run_cbcollects() (see CouchbaseServer.collect_logs() in
    # cbltest). Files are named "cbcollect-<safe_host>-*.zip". Same reasoning as above.
    Get-ChildItem -Path $DST_DIR -Filter "cbcollect-*.zip" -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem -Path $SRC_DIR -Filter "cbcollect-*.zip" -ErrorAction SilentlyContinue |
        Move-Item -Destination $DST_DIR -Force
}

function Find-Dir {
    param (
        [string]$TargetDir
    )
    $currentDir = Get-Item -Path $PSScriptRoot
    while ($currentDir -ne $currentDir.Root) {
        $targetPath = Join-Path -Path $currentDir.FullName -ChildPath $TargetDir
        if (Test-Path $targetPath -PathType Container) {
            return $targetPath
        }
        $currentDir = $currentDir.Parent
    }
    Write-Error "Error: '$TargetDir' directory not found in any parent directories."
    exit 1
}

function Write-Box {
    param (
        [string]$Content,
        [string]$Title
    )
    $lines = $Content -replace "`r`n", "`n" -split "`n"
    $maxLength = ($lines | Measure-Object -Property Length -Maximum).Maximum
    $border = "-" * ($maxLength + 4)
    $titlePadding = [math]::Floor(($maxLength - $Title.Length) / 2)
    Write-Host (" " * $titlePadding + $Title)
    Write-Host $border
    foreach ($line in $lines) {
        Write-Host ("| {0,-$maxLength} |" -f $line)
    }
    Write-Host $border
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Set-Variable -Name PIPELINES_DIR -Value (Find-Dir -TargetDir "pipelines") -Option ReadOnly
Set-Variable -Name TESTS_DIR -Value (Find-Dir -TargetDir "tests") -Option ReadOnly
Set-Variable -Name ENVIRONMENT_DIR -Value (Find-Dir -TargetDir "environment") -Option ReadOnly

Set-Variable -Name SHARED_PIPELINES_DIR -Value (Join-Path -Path $PIPELINES_DIR -ChildPath "shared") -Option ReadOnly
Set-Variable -Name FUNCTIONAL_TESTS_DIR -Value (Join-Path -Path $TESTS_DIR -ChildPath "functional") -Option ReadOnly
Set-Variable -Name AWS_ENVIRONMENT_DIR -Value (Join-Path -Path $ENVIRONMENT_DIR -ChildPath "aws") -Option ReadOnly

$content = @"
PIPELINES_DIR: $PIPELINES_DIR
TESTS_DIR: $TESTS_DIR
ENVIRONMENT_DIR: $ENVIRONMENT_DIR
SHARED_PIPELINES_DIR: $SHARED_PIPELINES_DIR
FUNCTIONAL_TESTS_DIR: $FUNCTIONAL_TESTS_DIR
AWS_ENVIRONMENT_DIR: $AWS_ENVIRONMENT_DIR
"@

Write-Box -Content $content -Title "Defining the following values:"

Export-ModuleMember -Variable PIPELINES_DIR, TESTS_DIR, `
ENVIRONMENT_DIR, SHARED_PIPELINES_DIR, `
FUNCTIONAL_TESTS_DIR, AWS_ENVIRONMENT_DIR `
-Func New-Venv, Stop-Venv, Move-Artifacts
