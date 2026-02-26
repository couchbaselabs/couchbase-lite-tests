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

    # Determine if we're in dev_e2e or QE based on current directory
    $currentDir = (Get-Location).Path
    if ($currentDir -like "*\dev_e2e*") {
        $SRC_DIR = (Resolve-Path $PSScriptRoot\..\..\..\tests\dev_e2e).Path
    } elseif ($currentDir -like "*\QE*") {
        $SRC_DIR = (Resolve-Path $PSScriptRoot\..\..\..\tests\QE).Path
    } else {
        # Fallback: try to detect from the script directory structure
        $scriptDir = $PSScriptRoot
        if ($scriptDir -like "*\QE\*") {
            $SRC_DIR = (Resolve-Path $PSScriptRoot\..\..\..\tests\QE).Path
        } else {
            $SRC_DIR = (Resolve-Path $PSScriptRoot\..\..\..\tests\dev_e2e).Path
        }
    }
    
    $DST_DIR = "$SRC_DIR\$env:TS_ARTIFACTS_DIR"
    if (-not (Test-Path -Path $DST_DIR)) {
        New-Item -ItemType Directory -Path $DST_DIR | Out-Null
    }

    Write-Host "Moving artifacts to $DST_DIR"

    if (Test-Path "$SRC_DIR\session.log") {
        Move-Item -Path "$SRC_DIR\session.log" -Destination "$DST_DIR\session.log" -Force
    }
    if (Test-Path "$SRC_DIR\http_log") {
        Move-Item -Path "$SRC_DIR\http_log" -Destination "$DST_DIR\http_log" -Force
    }
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
Set-Variable -Name DEV_E2E_PIPELINES_DIR -Value (Join-Path -Path $PIPELINES_DIR -ChildPath "dev_e2e") -Option ReadOnly
Set-Variable -Name QE_TESTS_DIR -Value (Join-Path -Path $TESTS_DIR -ChildPath "QE") -Option ReadOnly
Set-Variable -Name QE_PIPELINES_DIR -Value (Join-Path -Path $PIPELINES_DIR -ChildPath "QE") -Option ReadOnly
Set-Variable -Name DEV_E2E_TESTS_DIR -Value (Join-Path -Path $TESTS_DIR -ChildPath "dev_e2e") -Option ReadOnly
Set-Variable -Name AWS_ENVIRONMENT_DIR -Value (Join-Path -Path $ENVIRONMENT_DIR -ChildPath "aws") -Option ReadOnly

$content = @"
PIPELINES_DIR: $PIPELINES_DIR
TESTS_DIR: $TESTS_DIR
ENVIRONMENT_DIR: $ENVIRONMENT_DIR
SHARED_PIPELINES_DIR: $SHARED_PIPELINES_DIR
DEV_E2E_PIPELINES_DIR: $DEV_E2E_PIPELINES_DIR
DEV_E2E_TESTS_DIR: $DEV_E2E_TESTS_DIR
QE_TESTS_DIR: $QE_TESTS_DIR
QE_PIPELINES_DIR: $QE_PIPELINES_DIR
AWS_ENVIRONMENT_DIR: $AWS_ENVIRONMENT_DIR
"@

Write-Box -Content $content -Title "Defining the following values:"

Export-ModuleMember -Variable PIPELINES_DIR, TESTS_DIR, `
ENVIRONMENT_DIR, SHARED_PIPELINES_DIR, DEV_E2E_PIPELINES_DIR, `
DEV_E2E_TESTS_DIR, QE_PIPELINES_DIR, QE_TESTS_DIR, AWS_ENVIRONMENT_DIR `
-Func New-Venv, Stop-Venv, Move-Artifacts
