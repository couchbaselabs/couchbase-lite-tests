Import-Module $PSScriptRoot\..\..\shared\config.psm1 -Global
Push-Location $AWS_ENVIRONMENT_DIR
Move-Artifacts

uv run --group orchestrator .\stop_backend.py --topology topology_setup\topology.json
Pop-Location
