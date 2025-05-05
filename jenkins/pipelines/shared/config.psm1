# This script should be imported at the beginning of testing and teardown scripts

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

Set-Variable -Name PIPELINES_DIR -Value (Find-Dir -TargetDir "pipelines") -Option ReadOnly
Set-Variable -Name TESTS_DIR -Value (Find-Dir -TargetDir "tests") -Option ReadOnly
Set-Variable -Name ENVIRONMENT_DIR -Value (Find-Dir -TargetDir "environment") -Option ReadOnly

Set-Variable -Name SHARED_PIPELINES_DIR -Value (Join-Path -Path $PIPELINES_DIR -ChildPath "shared") -Option ReadOnly
Set-Variable -Name DEV_E2E_PIPELINES_DIR -Value (Join-Path -Path $PIPELINES_DIR -ChildPath "dev_e2e") -Option ReadOnly
Set-Variable -Name DEV_E2E_TESTS_DIR -Value (Join-Path -Path $TESTS_DIR -ChildPath "dev_e2e") -Option ReadOnly
Set-Variable -Name AWS_ENVIRONMENT_DIR -Value (Join-Path -Path $ENVIRONMENT_DIR -ChildPath "aws") -Option ReadOnly

$content = @"
PIPELINES_DIR: $PIPELINES_DIR
TESTS_DIR: $TESTS_DIR
ENVIRONMENT_DIR: $ENVIRONMENT_DIR
SHARED_PIPELINES_DIR: $SHARED_PIPELINES_DIR
DEV_E2E_PIPELINES_DIR: $DEV_E2E_PIPELINES_DIR
DEV_E2E_TESTS_DIR: $DEV_E2E_TESTS_DIR
AWS_ENVIRONMENT_DIR: $AWS_ENVIRONMENT_DIR
"@

Write-Box -Content $content -Title "Defining the following values:"

Export-ModuleMember -Variable PIPELINES_DIR, TESTS_DIR, `
ENVIRONMENT_DIR, SHARED_PIPELINES_DIR, DEV_E2E_PIPELINES_DIR, `
DEV_E2E_TESTS_DIR, AWS_ENVIRONMENT_DIR