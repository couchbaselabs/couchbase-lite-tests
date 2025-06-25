$env:PYTHONPATH = "$PSScriptRoot\..\..\..\"
Import-Module $PSScriptRoot\..\..\..\shared\config.psm1 -Global
Push-Location $AWS_ENVIRONMENT_DIR
Move-Artifacts

function Cleanup {
    Stop-Venv
    Pop-Location
}

trap {
    Cleanup
    break
}

Stop-Venv
New-Venv venv
.\venv\Scripts\activate
uv pip install -r requirements.txt
python .\stop_backend.py --topology topology_setup\topology.json
Cleanup