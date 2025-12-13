
$target = Join-Path $PSScriptRoot 'prepare_dotnet.psm1'

if (-not (Test-Path -Path $target)) {
	Invoke-WebRequest \
		-Uri https://raw.githubusercontent.com/couchbaselabs/couchbase-mobile-tools/refs/heads/master/dotnet_testing_env/prepare_dotnet.psm1 \
		-OutFile $target
} else {
	Write-Host "Using existing prepare_dotnet.psm1 at $target"
}

$mod = Import-Module $target -Force